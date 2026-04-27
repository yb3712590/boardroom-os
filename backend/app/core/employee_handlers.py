from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    EmployeeFreezeCommand,
    EmployeeHireRequestCommand,
    EmployeeReplaceRequestCommand,
    EmployeeRestoreCommand,
)
from app.core.constants import (
    EMPLOYEE_STATE_ACTIVE,
    EMPLOYEE_STATE_FROZEN,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_FROZEN,
    EVENT_EMPLOYEE_RESTORED,
)
from app.core.ids import new_prefixed_id
from app.core.employee_reuse import build_role_already_covered_details
from app.core.persona_profiles import (
    build_high_overlap_rejection_reason,
    find_same_role_high_overlap_conflict,
    normalize_persona_profiles,
)
from app.core.staffing_containment import (
    contain_employee_active_tickets,
    restore_employee_requeued_tickets,
)
from app.core.staffing_catalog import (
    resolve_board_workforce_staffing_combo,
    resolve_limited_ceo_staffing_combo,
)
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    reason: str,
    causation_hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=causation_hint,
        details=details,
    )


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    causation_hint: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical employee governance command was already accepted.",
        causation_hint=causation_hint,
    )


def _build_employee_change_review_pack(
    *,
    workflow_id: str,
    title: str,
    subtitle: str,
    change_kind: str,
    employee_change: dict[str, Any],
    trigger_reason: str,
    why_now: str,
    recommendation_summary: str,
    occurred_at,
) -> dict[str, Any]:
    return {
        "meta": {
            "review_pack_version": 1,
            "workflow_id": workflow_id,
            "review_type": "CORE_HIRE_APPROVAL",
            "created_at": occurred_at.isoformat(),
            "priority": "high",
        },
        "subject": {
            "title": title,
            "subtitle": subtitle,
            "change_kind": change_kind,
            "employee_id": employee_change.get("employee_id"),
            "replacement_employee_id": employee_change.get("replacement_employee_id"),
        },
        "trigger": {
            "trigger_event_id": None,
            "trigger_reason": trigger_reason,
            "why_now": why_now,
        },
        "recommendation": {
            "recommended_action": "APPROVE",
            "recommended_option_id": "approve_employee_change",
            "summary": recommendation_summary,
        },
        "options": [
            {
                "option_id": "approve_employee_change",
                "label": "Approve staffing change",
                "summary": recommendation_summary,
                "artifact_refs": [],
                "pros": ["Unblocks current workflow staffing."],
                "cons": [],
                "risks": [],
            }
        ],
        "evidence_summary": [],
        "decision_form": {
            "allowed_actions": ["APPROVE", "REJECT"],
            "command_target_version": 0,
            "requires_comment_on_reject": True,
            "requires_constraint_patch_on_modify": False,
        },
        "employee_change": employee_change,
    }


def build_employee_hired_event_payload(
    *,
    employee_id: str,
    role_type: str,
    role_profile_refs: list[str],
    normalized_profiles: dict[str, dict[str, Any]],
    provider_id: str | None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "role_type": role_type,
        "skill_profile": normalized_profiles["skill_profile"],
        "personality_profile": normalized_profiles["personality_profile"],
        "aesthetic_profile": normalized_profiles["aesthetic_profile"],
        "state": EMPLOYEE_STATE_ACTIVE,
        "board_approved": True,
        "provider_id": provider_id,
        "role_profile_refs": list(role_profile_refs),
    }


def record_employee_hired_event(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    employee_id: str,
    role_type: str,
    role_profile_refs: list[str],
    normalized_profiles: dict[str, dict[str, Any]],
    provider_id: str | None,
    actor_type: str,
    actor_id: str,
    occurred_at,
    idempotency_key: str,
    causation_id: str | None,
    correlation_id: str | None,
) -> None:
    repository.insert_event(
        connection,
        event_type=EVENT_EMPLOYEE_HIRED,
        actor_type=actor_type,
        actor_id=actor_id,
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=causation_id,
        correlation_id=correlation_id,
        payload=build_employee_hired_event_payload(
            employee_id=employee_id,
            role_type=role_type,
            role_profile_refs=role_profile_refs,
            normalized_profiles=normalized_profiles,
            provider_id=provider_id,
        ),
        occurred_at=occurred_at,
    )


def _employee_causation_hint(employee_id: str) -> str:
    return f"employee:{employee_id}"


def _resolve_employee_hire_request(
    repository: ControlPlaneRepository,
    connection,
    *,
    payload: EmployeeHireRequestCommand,
    command_id: str,
    received_at,
    staffing_combo_resolver: Callable[[str, list[str] | tuple[str, ...]], tuple[dict[str, Any] | None, str | None]],
) -> tuple[dict[str, Any] | None, CommandAckEnvelope | None]:
    workflow = repository.get_workflow_projection(payload.workflow_id, connection=connection)
    if workflow is None:
        return None, _rejected_ack(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            received_at=received_at,
            reason=f"Workflow {payload.workflow_id} was not found.",
        )

    _, staffing_reason = staffing_combo_resolver(payload.role_type, payload.role_profile_refs)
    if staffing_reason is not None:
        return None, _rejected_ack(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            received_at=received_at,
            reason=staffing_reason,
        )

    existing_employee = repository.get_employee_projection(payload.employee_id, connection=connection)
    if existing_employee is not None:
        return None, _rejected_ack(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            received_at=received_at,
            reason=f"Employee {payload.employee_id} already exists in roster state.",
            causation_hint=_employee_causation_hint(payload.employee_id),
        )

    normalized_profiles = normalize_persona_profiles(
        payload.role_type,
        skill_profile=payload.skill_profile,
        personality_profile=payload.personality_profile,
        aesthetic_profile=payload.aesthetic_profile,
    )
    conflict = find_same_role_high_overlap_conflict(
        role_type=payload.role_type,
        skill_profile=normalized_profiles["skill_profile"],
        personality_profile=normalized_profiles["personality_profile"],
        aesthetic_profile=normalized_profiles["aesthetic_profile"],
        employees=repository.list_employee_projections(
            connection=connection,
            states=[EMPLOYEE_STATE_ACTIVE],
            board_approved_only=True,
        ),
    )
    if conflict is not None:
        details = build_role_already_covered_details(
            role_type=payload.role_type,
            role_profile_refs=payload.role_profile_refs,
            reuse_candidate_employee_id=str(conflict["employee_id"]),
        )
        return None, _rejected_ack(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            received_at=received_at,
            reason=build_high_overlap_rejection_reason(
                role_type=payload.role_type,
                conflict=conflict,
            ),
            details=details,
        )

    return {"normalized_profiles": normalized_profiles}, None


def handle_ceo_direct_employee_hire(
    repository: ControlPlaneRepository,
    payload: EmployeeHireRequestCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=_employee_causation_hint(payload.employee_id),
            )

        resolved_request, rejected_ack = _resolve_employee_hire_request(
            repository,
            connection,
            payload=payload,
            command_id=command_id,
            received_at=received_at,
            staffing_combo_resolver=resolve_limited_ceo_staffing_combo,
        )
        if rejected_ack is not None:
            return rejected_ack
        assert resolved_request is not None

        record_employee_hired_event(
            repository,
            connection,
            workflow_id=payload.workflow_id,
            employee_id=payload.employee_id,
            role_type=payload.role_type,
            role_profile_refs=list(payload.role_profile_refs),
            normalized_profiles=resolved_request["normalized_profiles"],
            provider_id=payload.provider_id,
            actor_type="ceo",
            actor_id="ceo",
            occurred_at=received_at,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=_employee_causation_hint(payload.employee_id),
    )


def handle_employee_hire_request(
    repository: ControlPlaneRepository,
    payload: EmployeeHireRequestCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=f"approval:{existing_event['event_id']}",
            )

        resolved_request, rejected_ack = _resolve_employee_hire_request(
            repository,
            connection,
            payload=payload,
            command_id=command_id,
            received_at=received_at,
            staffing_combo_resolver=resolve_board_workforce_staffing_combo,
        )
        if rejected_ack is not None:
            return rejected_ack
        assert resolved_request is not None

        approval = repository.create_approval_request(
            connection,
            workflow_id=payload.workflow_id,
            approval_type="CORE_HIRE_APPROVAL",
            requested_by="staffing-router",
            review_pack=_build_employee_change_review_pack(
                workflow_id=payload.workflow_id,
                title=f"Approve hire: {payload.employee_id}",
                subtitle=payload.request_summary,
                change_kind="EMPLOYEE_HIRE",
                employee_change={
                    "change_kind": "EMPLOYEE_HIRE",
                    "employee_id": payload.employee_id,
                    "role_type": payload.role_type,
                    "role_profile_refs": list(payload.role_profile_refs),
                    "skill_profile": resolved_request["normalized_profiles"]["skill_profile"],
                    "personality_profile": resolved_request["normalized_profiles"]["personality_profile"],
                    "aesthetic_profile": resolved_request["normalized_profiles"]["aesthetic_profile"],
                    "provider_id": payload.provider_id,
                },
                trigger_reason="Core staffing changes require explicit board approval.",
                why_now=payload.request_summary,
                recommendation_summary=payload.request_summary,
                occurred_at=received_at,
            ),
            available_actions=["APPROVE", "REJECT"],
            draft_defaults={
                "selected_option_id": "approve_employee_change",
                "comment_template": "",
            },
            inbox_title=f"Approve hire: {payload.employee_id}",
            inbox_summary=payload.request_summary,
            badges=["staffing", "core_hire"],
            priority="high",
            occurred_at=received_at,
            idempotency_key=payload.idempotency_key,
        )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{approval['approval_id']}",
    )


def handle_employee_replace_request(
    repository: ControlPlaneRepository,
    payload: EmployeeReplaceRequestCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=f"approval:{existing_event['event_id']}",
            )

        workflow = repository.get_workflow_projection(payload.workflow_id, connection=connection)
        if workflow is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Workflow {payload.workflow_id} was not found.",
            )

        current_employee = repository.get_employee_projection(payload.replaced_employee_id, connection=connection)
        if current_employee is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.replaced_employee_id} does not exist.",
                causation_hint=f"employee:{payload.replaced_employee_id}",
            )
        if str(current_employee.get("state") or "") != EMPLOYEE_STATE_ACTIVE:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.replaced_employee_id} is not active and cannot be replaced.",
                causation_hint=f"employee:{payload.replaced_employee_id}",
            )

        _, staffing_reason = resolve_board_workforce_staffing_combo(
            payload.replacement_role_type,
            payload.replacement_role_profile_refs,
        )
        if staffing_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=staffing_reason,
                causation_hint=f"employee:{payload.replaced_employee_id}",
            )

        current_role_type = str(current_employee.get("role_type") or "").strip()
        current_role_profile_refs = list(current_employee.get("role_profile_refs") or [])
        _, current_staffing_reason = resolve_board_workforce_staffing_combo(
            current_role_type,
            current_role_profile_refs,
        )
        if current_staffing_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=(
                    f"Employee {payload.replaced_employee_id} is not on the current local MVP staffing path "
                    "and cannot be replaced from the thin staffing loop."
                ),
                causation_hint=f"employee:{payload.replaced_employee_id}",
            )
        if current_role_type != payload.replacement_role_type:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=(
                    f"Replacement must keep the same role_type as {payload.replaced_employee_id} on the current local MVP staffing path."
                ),
                causation_hint=f"employee:{payload.replaced_employee_id}",
            )

        replacement_employee = repository.get_employee_projection(
            payload.replacement_employee_id,
            connection=connection,
        )
        if replacement_employee is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.replacement_employee_id} already exists in roster state.",
                causation_hint=f"employee:{payload.replacement_employee_id}",
            )

        normalized_profiles = normalize_persona_profiles(
            payload.replacement_role_type,
            skill_profile=payload.replacement_skill_profile,
            personality_profile=payload.replacement_personality_profile,
            aesthetic_profile=payload.replacement_aesthetic_profile,
        )
        conflict = find_same_role_high_overlap_conflict(
            role_type=payload.replacement_role_type,
            skill_profile=normalized_profiles["skill_profile"],
            personality_profile=normalized_profiles["personality_profile"],
            aesthetic_profile=normalized_profiles["aesthetic_profile"],
            employees=repository.list_employee_projections(
                connection=connection,
                states=[EMPLOYEE_STATE_ACTIVE],
                board_approved_only=True,
            ),
            exclude_employee_ids=[payload.replaced_employee_id],
        )
        if conflict is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=build_high_overlap_rejection_reason(
                    role_type=payload.replacement_role_type,
                    conflict=conflict,
                ),
                causation_hint=f"employee:{payload.replaced_employee_id}",
            )

        approval = repository.create_approval_request(
            connection,
            workflow_id=payload.workflow_id,
            approval_type="CORE_HIRE_APPROVAL",
            requested_by="staffing-router",
            review_pack=_build_employee_change_review_pack(
                workflow_id=payload.workflow_id,
                title=f"Approve replacement: {payload.replaced_employee_id}",
                subtitle=payload.request_summary,
                change_kind="EMPLOYEE_REPLACE",
                employee_change={
                    "change_kind": "EMPLOYEE_REPLACE",
                    "employee_id": payload.replaced_employee_id,
                    "replacement_employee_id": payload.replacement_employee_id,
                    "replacement_role_type": payload.replacement_role_type,
                    "replacement_role_profile_refs": list(payload.replacement_role_profile_refs),
                    "replacement_skill_profile": normalized_profiles["skill_profile"],
                    "replacement_personality_profile": normalized_profiles["personality_profile"],
                    "replacement_aesthetic_profile": normalized_profiles["aesthetic_profile"],
                    "replacement_provider_id": payload.replacement_provider_id,
                },
                trigger_reason="Replacing a core worker requires explicit board approval.",
                why_now=payload.request_summary,
                recommendation_summary=payload.request_summary,
                occurred_at=received_at,
            ),
            available_actions=["APPROVE", "REJECT"],
            draft_defaults={
                "selected_option_id": "approve_employee_change",
                "comment_template": "",
            },
            inbox_title=f"Approve replacement: {payload.replaced_employee_id}",
            inbox_summary=payload.request_summary,
            badges=["staffing", "core_hire", "replacement"],
            priority="high",
            occurred_at=received_at,
            idempotency_key=payload.idempotency_key,
        )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{approval['approval_id']}",
    )


def handle_employee_freeze(
    repository: ControlPlaneRepository,
    payload: EmployeeFreezeCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=f"employee:{payload.employee_id}",
            )

        employee = repository.get_employee_projection(payload.employee_id, connection=connection)
        if employee is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.employee_id} does not exist.",
                causation_hint=f"employee:{payload.employee_id}",
            )
        if str(employee.get("state") or "") != EMPLOYEE_STATE_ACTIVE:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.employee_id} is not active.",
                causation_hint=f"employee:{payload.employee_id}",
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_FROZEN,
            actor_type="operator",
            actor_id=payload.frozen_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "employee_id": payload.employee_id,
                "reason": payload.reason,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=f"employee:{payload.employee_id}",
            )

        contain_employee_active_tickets(
            repository,
            connection,
            employee_id=payload.employee_id,
            action_kind=EVENT_EMPLOYEE_FROZEN,
            reason=payload.reason,
            occurred_at=received_at,
            command_id=command_id,
            idempotency_key_base=payload.idempotency_key,
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"employee:{payload.employee_id}",
    )


def handle_employee_restore(
    repository: ControlPlaneRepository,
    payload: EmployeeRestoreCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=f"employee:{payload.employee_id}",
            )

        employee = repository.get_employee_projection(payload.employee_id, connection=connection)
        if employee is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.employee_id} does not exist.",
                causation_hint=f"employee:{payload.employee_id}",
            )
        if str(employee.get("state") or "") != EMPLOYEE_STATE_FROZEN:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Employee {payload.employee_id} is not frozen.",
                causation_hint=f"employee:{payload.employee_id}",
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_RESTORED,
            actor_type="operator",
            actor_id=payload.restored_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "employee_id": payload.employee_id,
                "reason": payload.reason,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                causation_hint=f"employee:{payload.employee_id}",
            )

        restore_employee_requeued_tickets(
            repository,
            connection,
            employee_id=payload.employee_id,
            occurred_at=received_at,
            command_id=command_id,
            idempotency_key_base=payload.idempotency_key,
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"employee:{payload.employee_id}",
    )
