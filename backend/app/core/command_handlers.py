from __future__ import annotations

import hashlib
import json

from app.config import get_settings
from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    ProjectInitCommand,
    TicketCreateCommand,
)
from app.core.constants import (
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_WORKFLOW_CREATED,
    SYSTEM_INITIALIZED_KEY,
)
from app.core.ids import new_prefixed_id
from app.core.runtime import run_leased_ticket_runtime
from app.core.ticket_handlers import handle_ticket_create, run_scheduler_tick
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

PROJECT_INIT_SCOPE_NODE_ID = "node_scope_decision"
PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS = 6


def _command_base_key(payload: ProjectInitCommand) -> str:
    normalized = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"project-init:{digest}"


def _project_init_scope_ticket_id(workflow_id: str) -> str:
    return f"tkt_{workflow_id}_scope_decision"


def _build_project_init_auto_review_request(ticket_id: str) -> dict:
    return {
        "review_type": "MEETING_ESCALATION",
        "priority": "high",
        "title": "Review scope decision consensus",
        "subtitle": "Initial scope decision is ready for board lock-in.",
        "blocking_scope": "WORKFLOW",
        "trigger_reason": "Project init produced the first scope decision that needs explicit board confirmation.",
        "why_now": "Execution should not widen before the first scope lock is approved.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "consensus_scope_lock",
        "recommendation_summary": "The narrowest scope that still ships the workflow is ready for board review.",
        "options": [
            {
                "option_id": "consensus_scope_lock",
                "label": "Lock consensus scope",
                "summary": "Proceed with the converged scope and follow-up tickets.",
                "artifact_refs": [],
                "pros": ["Keeps delivery scope stable"],
                "cons": ["Defers non-critical stretch ideas"],
                "risks": ["Some polish moves slip to later rounds"],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_scope_consensus",
                "source_type": "CONSENSUS_DOCUMENT",
                "headline": "Generated scope consensus document",
                "summary": "The first scope decision is ready for board review.",
                "source_ref": None,
            }
        ],
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
        "draft_selected_option_id": "consensus_scope_lock",
        "comment_template": "",
        "inbox_title": "Review scope decision consensus",
        "inbox_summary": "A consensus document is ready for board review.",
        "badges": ["meeting", "board_gate", "scope"],
        "developer_inspector_refs": {
            "compiled_context_bundle_ref": f"ctx://compile/{ticket_id}",
            "compile_manifest_ref": f"manifest://compile/{ticket_id}",
            "rendered_execution_payload_ref": f"render://compile/{ticket_id}",
        },
    }


def _create_project_init_brief_artifact(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    payload: ProjectInitCommand,
) -> str:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise RuntimeError("Artifact store is required to create the project-init brief artifact.")

    artifact_ref = f"art://project-init/{workflow_id}/board-brief.md"
    logical_path = f"inputs/project-init/{workflow_id}/board-brief.md"
    deadline = payload.deadline_at.isoformat() if payload.deadline_at is not None else "None"
    content = "\n".join(
        [
            f"# Board Brief for {workflow_id}",
            "",
            f"- North star goal: {payload.north_star_goal}",
            f"- Budget cap: {payload.budget_cap}",
            f"- Deadline: {deadline}",
            "",
            "## Hard constraints",
            *(f"- {constraint}" for constraint in payload.hard_constraints),
            "",
        ]
    )
    materialized = artifact_store.materialize_text(
        logical_path,
        content,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        media_type="text/markdown",
    )
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=PROJECT_INIT_SCOPE_NODE_ID,
            logical_path=logical_path,
            kind="MARKDOWN",
            media_type="text/markdown",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_backend=materialized.storage_backend,
            storage_relpath=materialized.storage_relpath,
            storage_object_key=materialized.storage_object_key,
            storage_delete_status=materialized.storage_delete_status,
            storage_delete_error=None,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="PERSISTENT",
            retention_class_source="explicit",
            retention_ttl_sec=None,
            retention_policy_source="explicit_class",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=now_local(),
        )
    return artifact_ref


def _create_project_init_scope_ticket(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    command_key: str,
    payload: ProjectInitCommand,
    tenant_id: str,
    workspace_id: str,
) -> None:
    ticket_id = _project_init_scope_ticket_id(workflow_id)
    brief_artifact_ref = _create_project_init_brief_artifact(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        payload=payload,
    )
    semantic_queries = [payload.north_star_goal]
    semantic_queries.extend(constraint for constraint in payload.hard_constraints[:1] if constraint)
    create_ack = handle_ticket_create(
        repository,
        TicketCreateCommand(
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            node_id=PROJECT_INIT_SCOPE_NODE_ID,
            parent_ticket_id=None,
            attempt_no=1,
            role_profile_ref="ui_designer_primary",
            constraints_ref="project_init_scope_lock",
            input_artifact_refs=[brief_artifact_ref],
            context_query_plan={
                "keywords": ["scope", "constraints", "board review"],
                "semantic_queries": semantic_queries,
                "max_context_tokens": 3000,
            },
            acceptance_criteria=[
                "Must produce a consensus document",
                "Must include follow-up tickets",
            ],
            output_schema_ref="consensus_document",
            output_schema_version=1,
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=["reports/meeting/*"],
            retry_budget=1,
            priority="high",
            timeout_sla_sec=1800,
            deadline_at=payload.deadline_at,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            auto_review_request=_build_project_init_auto_review_request(ticket_id),
            escalation_policy={
                "on_timeout": "retry",
                "on_schema_error": "retry",
                "on_repeat_failure": "escalate_ceo",
            },
            idempotency_key=f"{command_key}:scope-ticket-create",
        ),
    )
    if create_ack.status not in {CommandAckStatus.ACCEPTED, CommandAckStatus.DUPLICATE}:
        raise RuntimeError(f"Project-init scope ticket was not accepted: {create_ack.reason}")


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


def _auto_advance_project_init_to_first_review(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    command_key: str,
) -> None:
    settings = get_settings()
    for step_index in range(PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS):
        if _workflow_has_open_approval(repository, workflow_id) or _workflow_has_open_incident(
            repository, workflow_id
        ):
            return

        _, version_before = repository.get_cursor_and_version()
        run_scheduler_tick(
            repository,
            idempotency_key=f"{command_key}:auto-advance:{step_index}:scheduler",
            max_dispatches=settings.scheduler_max_dispatches,
        )
        run_leased_ticket_runtime(repository)
        _, version_after = repository.get_cursor_and_version()

        if _workflow_has_open_approval(repository, workflow_id) or _workflow_has_open_incident(
            repository, workflow_id
        ):
            return
        if version_after == version_before:
            return


def handle_project_init(
    repository: ControlPlaneRepository,
    payload: ProjectInitCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    command_key = _command_base_key(payload)
    workflow_event_key = f"{command_key}:workflow-created"
    directive_event_key = f"{command_key}:board-directive"

    with repository.transaction() as connection:
        tenant_id = payload.tenant_id or DEFAULT_TENANT_ID
        workspace_id = payload.workspace_id or DEFAULT_WORKSPACE_ID
        repository.insert_event(
            connection,
            event_type=EVENT_SYSTEM_INITIALIZED,
            actor_type="system",
            actor_id="system",
            workflow_id=None,
            idempotency_key=SYSTEM_INITIALIZED_KEY,
            causation_id=None,
            correlation_id=None,
            payload={"status": "initialized"},
            occurred_at=received_at,
        )

        existing_workflow_event = repository.get_event_by_idempotency_key(
            connection,
            workflow_event_key,
        )
        if existing_workflow_event is not None:
            repository.refresh_projections(connection)
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=command_key,
                status=CommandAckStatus.DUPLICATE,
                received_at=received_at,
                reason="An identical project-init command was already accepted.",
                causation_hint=f"workflow:{existing_workflow_event['workflow_id']}",
            )

        workflow_id = new_prefixed_id("wf")
        repository.insert_event(
            connection,
            event_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
            actor_type="board",
            actor_id="board",
            workflow_id=workflow_id,
            idempotency_key=directive_event_key,
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                **payload.model_dump(mode="json"),
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            },
            occurred_at=received_at,
        )
        repository.insert_event(
            connection,
            event_type=EVENT_WORKFLOW_CREATED,
            actor_type="system",
            actor_id="system",
            workflow_id=workflow_id,
            idempotency_key=workflow_event_key,
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                **payload.model_dump(mode="json"),
                "title": payload.north_star_goal,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            },
            occurred_at=received_at,
        )

        repository.refresh_projections(connection)

    _create_project_init_scope_ticket(
        repository,
        workflow_id=workflow_id,
        command_key=command_key,
        payload=payload,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    _auto_advance_project_init_to_first_review(
        repository,
        workflow_id=workflow_id,
        command_key=command_key,
    )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=command_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"workflow:{workflow_id}",
    )
