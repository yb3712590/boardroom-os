from __future__ import annotations

import json
from typing import Any

from app.contracts.commands import (
    BoardApproveCommand,
    BoardRejectCommand,
    CommandAckEnvelope,
    CommandAckStatus,
    ModifyConstraintsCommand,
    TicketCreateCommand,
)
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    EMPLOYEE_STATE_ACTIVE,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_TICKET_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
)
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    CONSENSUS_DOCUMENT_SCHEMA_VERSION,
    schema_id,
    validate_output_payload,
)
from app.core.runtime import run_leased_ticket_runtime
from app.core.staffing_containment import contain_employee_active_tickets
from app.core.ticket_handlers import run_scheduler_tick
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

SCOPE_APPROVAL_AUTO_ADVANCE_MAX_STEPS = 6
FOLLOWUP_OWNER_ROLE_TO_PROFILE = {
    "frontend_engineer": "ui_designer_primary",
}


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    reason: str,
    causation_hint: str | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=causation_hint,
    )


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    approval_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical board command was already accepted.",
        causation_hint=f"approval:{approval_id}",
    )


def _validate_open_approval(
    approval: dict[str, Any] | None,
    *,
    approval_id: str,
    review_pack_id: str,
    review_pack_version: int,
    command_target_version: int,
) -> str | None:
    if approval is None:
        return "Approval target not found."
    if approval["approval_id"] != approval_id or approval["review_pack_id"] != review_pack_id:
        return "Approval target does not match review pack."
    if approval["status"] != APPROVAL_STATUS_OPEN:
        return f"Approval is already resolved with status {approval['status']}."
    if approval["review_pack_version"] != review_pack_version:
        return "Review pack outdated. Reload review-room projection."
    if approval["command_target_version"] != command_target_version:
        return "Projection target outdated. Reload review-room projection."
    return None


def _validate_blocked_projection(
    repository: ControlPlaneRepository,
    approval: dict[str, Any],
) -> str | None:
    subject = approval["payload"].get("review_pack", {}).get("subject", {})
    workflow_id = approval["workflow_id"]
    ticket_id = subject.get("source_ticket_id")
    node_id = subject.get("source_node_id")
    if ticket_id is None or node_id is None:
        return None

    ticket_projection = repository.get_current_ticket_projection(ticket_id)
    node_projection = repository.get_current_node_projection(workflow_id, node_id)
    if ticket_projection is None or node_projection is None:
        return "Ticket or node projection for this approval is missing. Reload dashboard state."
    if ticket_projection["status"] != TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Ticket is not currently blocked for board review."
    if node_projection["status"] != NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Node is not currently blocked for board review."
    if ticket_projection["workflow_id"] != workflow_id or ticket_projection["node_id"] != node_id:
        return "Ticket projection does not match the approval target."
    if node_projection["latest_ticket_id"] != ticket_id:
        return "Node projection no longer points at this approval ticket."
    return None


def _apply_employee_change_approval(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> str | None:
    if approval["approval_type"] != "CORE_HIRE_APPROVAL":
        return None

    review_pack = approval["payload"].get("review_pack") or {}
    employee_change = review_pack.get("employee_change") or {}
    change_kind = str(employee_change.get("change_kind") or "")

    if change_kind == "EMPLOYEE_HIRE":
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-hired",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": employee_change["employee_id"],
                "role_type": employee_change["role_type"],
                "skill_profile": dict(employee_change.get("skill_profile") or {}),
                "personality_profile": dict(employee_change.get("personality_profile") or {}),
                "aesthetic_profile": dict(employee_change.get("aesthetic_profile") or {}),
                "state": EMPLOYEE_STATE_ACTIVE,
                "board_approved": True,
                "provider_id": employee_change.get("provider_id"),
                "role_profile_refs": list(employee_change.get("role_profile_refs") or []),
            },
            occurred_at=occurred_at,
        )
        return str(employee_change["employee_id"])

    if change_kind == "EMPLOYEE_REPLACE":
        replaced_employee_id = str(employee_change["employee_id"])
        replacement_employee_id = str(employee_change["replacement_employee_id"])
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-replacement-hired",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": replacement_employee_id,
                "role_type": employee_change["replacement_role_type"],
                "skill_profile": dict(employee_change.get("replacement_skill_profile") or {}),
                "personality_profile": dict(employee_change.get("replacement_personality_profile") or {}),
                "aesthetic_profile": dict(employee_change.get("replacement_aesthetic_profile") or {}),
                "state": EMPLOYEE_STATE_ACTIVE,
                "board_approved": True,
                "provider_id": employee_change.get("replacement_provider_id"),
                "role_profile_refs": list(employee_change.get("replacement_role_profile_refs") or []),
            },
            occurred_at=occurred_at,
        )
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_REPLACED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-replaced",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": replaced_employee_id,
                "replacement_employee_id": replacement_employee_id,
            },
            occurred_at=occurred_at,
        )
        contain_employee_active_tickets(
            repository,
            connection,
            employee_id=replaced_employee_id,
            action_kind=EVENT_EMPLOYEE_REPLACED,
            reason="Board-approved employee replacement removed the original assignee from active duty.",
            occurred_at=occurred_at,
            command_id=command_id,
            idempotency_key_base=idempotency_key,
            replacement_employee_id=replacement_employee_id,
        )
        return replacement_employee_id

    return None


def _workflow_has_open_approval(
    repository: ControlPlaneRepository,
    workflow_id: str,
) -> bool:
    return any(approval["workflow_id"] == workflow_id for approval in repository.list_open_approvals())


def _workflow_has_open_incident(
    repository: ControlPlaneRepository,
    workflow_id: str,
) -> bool:
    return any(incident["workflow_id"] == workflow_id for incident in repository.list_open_incidents())


def _dedupe_artifact_refs(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _build_scope_followup_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Approved scope follow-up implementation is ready for review."
    return {
        "review_type": "VISUAL_MILESTONE",
        "priority": "high",
        "title": "Review approved scope implementation",
        "subtitle": "The first visual execution pass under the locked scope is ready.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Board-approved scope follow-up reached a visual milestone review checkpoint.",
        "why_now": "Implementation should stay aligned with the approved scope before more build work piles on.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "option_a",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "option_a",
                "label": "Approved scope implementation",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Keeps implementation aligned with the approved scope lock."],
                "cons": ["Non-critical stretch ideas remain deferred."],
                "risks": ["Visual polish may still need a follow-up rework pass."],
            }
        ],
        "evidence_summary": [],
        "risk_summary": {
            "user_risk": "LOW",
            "engineering_risk": "MEDIUM",
            "schedule_risk": "LOW",
            "budget_risk": "LOW",
        },
        "budget_impact": {
            "tokens_spent_so_far": 0,
            "tokens_if_approved_estimate_range": {"min_tokens": 100, "max_tokens": 250},
            "tokens_if_rework_estimate_range": {"min_tokens": 350, "max_tokens": 700},
            "estimate_confidence": "medium",
            "budget_risk": "LOW",
        },
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "option_a",
        "comment_template": "",
        "inbox_title": "Review approved scope implementation",
        "inbox_summary": "A visual implementation pass is ready under the approved scope.",
        "badges": ["visual", "board_gate", "scope_followup"],
    }


def _build_scope_followup_allowed_write_set(ticket_id: str) -> list[str]:
    return [
        f"artifacts/ui/scope-followups/{ticket_id}/*",
        f"reports/review/{ticket_id}/*",
    ]


def _load_scope_consensus_payload(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    review_pack = approval["payload"].get("review_pack") or {}
    evidence_summary = review_pack.get("evidence_summary") or []
    artifact_ref = str((evidence_summary[0] or {}).get("source_ref") or "").strip() if evidence_summary else ""
    if not artifact_ref:
        raise ValueError("Scope review is missing the approved consensus artifact reference.")

    artifact = repository.get_artifact_by_ref(artifact_ref, connection=connection)
    if artifact is None:
        raise ValueError("Approved consensus artifact record is missing.")
    if repository.artifact_store is None:
        raise ValueError("Artifact store is required to read the approved consensus artifact.")

    try:
        body = repository.artifact_store.read_bytes(
            artifact.get("storage_relpath"),
            storage_object_key=artifact.get("storage_object_key"),
        )
    except Exception as exc:  # pragma: no cover - exact backend failure varies
        raise ValueError("Approved consensus artifact could not be read.") from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Approved consensus artifact is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Approved consensus artifact JSON root must be an object.")

    validate_output_payload(
        schema_ref=CONSENSUS_DOCUMENT_SCHEMA_REF,
        schema_version=CONSENSUS_DOCUMENT_SCHEMA_VERSION,
        submitted_schema_version=schema_id(
            CONSENSUS_DOCUMENT_SCHEMA_REF,
            CONSENSUS_DOCUMENT_SCHEMA_VERSION,
        ),
        payload=payload,
    )
    return artifact_ref, payload


def _build_scope_followup_ticket_payloads(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> list[dict[str, Any]]:
    review_pack = approval["payload"].get("review_pack") or {}
    subject = review_pack.get("subject") or {}
    source_ticket_id = str(subject.get("source_ticket_id") or "").strip()
    if not source_ticket_id:
        return []

    created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id)
    if created_spec is None:
        raise ValueError("Approved scope ticket spec could not be loaded.")
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
    if (
        str(created_spec.get("output_schema_ref") or "") != CONSENSUS_DOCUMENT_SCHEMA_REF
        and maker_ticket_id
    ):
        maker_created_spec = repository.get_latest_ticket_created_payload(connection, maker_ticket_id)
        if maker_created_spec is None:
            raise ValueError("Approved scope maker ticket spec could not be loaded.")
        created_spec = maker_created_spec
        source_ticket_id = maker_ticket_id
    if str(created_spec.get("output_schema_ref") or "") != CONSENSUS_DOCUMENT_SCHEMA_REF:
        return []

    consensus_artifact_ref, consensus_payload = _load_scope_consensus_payload(
        repository,
        connection,
        approval=approval,
    )
    workflow = repository.get_workflow_projection(approval["workflow_id"], connection=connection)
    tenant_id = (
        str(workflow.get("tenant_id") or DEFAULT_TENANT_ID)
        if workflow is not None
        else DEFAULT_TENANT_ID
    )
    workspace_id = (
        str(workflow.get("workspace_id") or DEFAULT_WORKSPACE_ID)
        if workflow is not None
        else DEFAULT_WORKSPACE_ID
    )
    input_artifact_refs = _dedupe_artifact_refs(
        [consensus_artifact_ref] + list(created_spec.get("input_artifact_refs") or [])
    )
    followup_items = list(consensus_payload.get("followup_tickets") or [])
    seen_ticket_ids: set[str] = set()
    seen_node_ids: set[str] = set()
    ticket_payloads: list[dict[str, Any]] = []

    for raw_followup in followup_items:
        followup = dict(raw_followup)
        followup_ticket_id = str(followup.get("ticket_id") or "").strip()
        owner_role = str(followup.get("owner_role") or "").strip()
        followup_summary = str(followup.get("summary") or "").strip()

        if followup_ticket_id in seen_ticket_ids:
            raise ValueError(
                f"Approved consensus contains duplicate follow-up ticket_id '{followup_ticket_id}'."
            )
        seen_ticket_ids.add(followup_ticket_id)

        role_profile_ref = FOLLOWUP_OWNER_ROLE_TO_PROFILE.get(owner_role)
        if role_profile_ref is None:
            raise ValueError(f"Unsupported approved follow-up owner_role '{owner_role}'.")
        if repository.get_current_ticket_projection(followup_ticket_id, connection=connection) is not None:
            raise ValueError(f"Follow-up ticket {followup_ticket_id} already exists in projection state.")

        node_id = f"node_followup_{followup_ticket_id.removeprefix('tkt_')}"
        if node_id in seen_node_ids:
            raise ValueError(f"Approved consensus contains duplicate follow-up node_id '{node_id}'.")
        seen_node_ids.add(node_id)
        if repository.get_current_node_projection(approval["workflow_id"], node_id, connection=connection) is not None:
            raise ValueError(f"Follow-up node {node_id} already exists in projection state.")

        ticket_command = TicketCreateCommand(
            ticket_id=followup_ticket_id,
            workflow_id=approval["workflow_id"],
            node_id=node_id,
            parent_ticket_id=source_ticket_id,
            attempt_no=1,
            role_profile_ref=role_profile_ref,
            constraints_ref="approved_scope_followup_visual",
            input_artifact_refs=input_artifact_refs,
            context_query_plan={
                "keywords": ["approved scope", "visual", "implementation"],
                "semantic_queries": [followup_summary],
                "max_context_tokens": 3000,
            },
            acceptance_criteria=[
                f"Must implement this approved scope follow-up: {followup_summary}",
                "Must stay inside the locked scope from the approved consensus document.",
                "Must produce a visual milestone review package.",
            ],
            output_schema_ref="ui_milestone_review",
            output_schema_version=1,
            allowed_tools=["read_artifact", "write_artifact", "image_gen"],
            allowed_write_set=_build_scope_followup_allowed_write_set(followup_ticket_id),
            retry_budget=1,
            priority="high",
            timeout_sla_sec=1800,
            deadline_at=created_spec.get("deadline_at"),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            auto_review_request=_build_scope_followup_review_request(followup_summary),
            escalation_policy={
                "on_timeout": "retry",
                "on_schema_error": "retry",
                "on_repeat_failure": "escalate_ceo",
            },
            idempotency_key=(
                f"board-approved-scope-followup:{approval['approval_id']}:{followup_ticket_id}"
            ),
        )
        ticket_payloads.append(ticket_command.model_dump(mode="json"))

    return ticket_payloads


def _insert_scope_followup_ticket_created_event(
    repository: ControlPlaneRepository,
    connection,
    *,
    command_id: str,
    occurred_at,
    workflow_id: str,
    idempotency_key: str,
    ticket_payload: dict[str, Any],
) -> str:
    event_row = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="system",
        actor_id="board-followup-router",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=ticket_payload,
        occurred_at=occurred_at,
    )
    if event_row is None:
        raise RuntimeError("Scope follow-up ticket creation idempotency conflict.")
    return str(ticket_payload["ticket_id"])


def _auto_advance_scope_followup_to_next_stop(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    idempotency_key: str,
) -> None:
    for step_index in range(SCOPE_APPROVAL_AUTO_ADVANCE_MAX_STEPS):
        if _workflow_has_open_approval(repository, workflow_id) or _workflow_has_open_incident(
            repository,
            workflow_id,
        ):
            return

        _, version_before = repository.get_cursor_and_version()
        run_scheduler_tick(
            repository,
            idempotency_key=f"{idempotency_key}:scope-followup-auto-advance:{step_index}:scheduler",
            max_dispatches=1,
        )
        run_leased_ticket_runtime(repository)
        _, version_after = repository.get_cursor_and_version()

        if _workflow_has_open_approval(repository, workflow_id) or _workflow_has_open_incident(
            repository,
            workflow_id,
        ):
            return
        if version_after == version_before:
            return


def handle_board_approve(
    repository: ControlPlaneRepository,
    payload: BoardApproveCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    created_followup_ticket_ids: list[str] = []
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})
        try:
            followup_ticket_payloads = _build_scope_followup_ticket_payloads(
                repository,
                connection,
                approval=approval,
            )
        except ValueError as exc:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"approval:{payload.approval_id}",
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_APPROVED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "selected_option_id": payload.selected_option_id,
                "board_comment": payload.board_comment,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        employee_causation_hint = _apply_employee_change_approval(
            repository,
            connection,
            approval=approval,
            command_id=command_id,
            occurred_at=received_at,
            idempotency_key=payload.idempotency_key,
        )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_APPROVED,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "APPROVE",
                "selected_option_id": payload.selected_option_id,
                "board_comment": payload.board_comment,
            },
        )
        for index, followup_ticket_payload in enumerate(followup_ticket_payloads):
            created_followup_ticket_ids.append(
                _insert_scope_followup_ticket_created_event(
                    repository,
                    connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=approval["workflow_id"],
                    idempotency_key=f"{payload.idempotency_key}:scope-followup-create:{index}",
                    ticket_payload=followup_ticket_payload,
                )
            )
        repository.refresh_projections(connection)

    if created_followup_ticket_ids:
        _auto_advance_scope_followup_to_next_stop(
            repository,
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
        )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=(
            f"employee:{employee_causation_hint}"
            if employee_causation_hint is not None
            else (
                f"ticket:{created_followup_ticket_ids[0]}"
                if created_followup_ticket_ids
                else f"approval:{payload.approval_id}"
            )
        ),
    )


def handle_board_reject(
    repository: ControlPlaneRepository,
    payload: BoardRejectCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REJECTED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "board_comment": payload.board_comment,
                "rejection_reasons": payload.rejection_reasons,
                "decision_action": "REJECT",
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_REJECTED,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "REJECT",
                "board_comment": payload.board_comment,
                "rejection_reasons": payload.rejection_reasons,
            },
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{payload.approval_id}",
    )


def handle_modify_constraints(
    repository: ControlPlaneRepository,
    payload: ModifyConstraintsCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REJECTED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
                "decision_action": "MODIFY_CONSTRAINTS",
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "MODIFY_CONSTRAINTS",
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
            },
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{payload.approval_id}",
    )
