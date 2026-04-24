from __future__ import annotations

import json
from typing import Any

from app.contracts.ceo_actions import CEOActionBatch, CEOActionType
from app.contracts.commands import EmployeeHireRequestCommand, MeetingRequestCommand
from app.config import get_settings
from app.core.ceo_execution_presets import build_ceo_create_ticket_command
from app.core.persona_profiles import build_seeded_persona_variant
from app.core.runtime_provider_config import resolve_runtime_provider_config
from app.core.staffing_catalog import resolve_limited_ceo_staffing_combo
from app.db.repository import ControlPlaneRepository


def _action_key(*, action_type: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "action_type": action_type,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _executed_entry(
    *,
    action_type: str,
    payload: dict[str, Any],
    execution_status: str,
    reason: str,
    command_status: str | None = None,
    causation_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "payload": payload,
        "execution_status": execution_status,
        "reason": reason,
        "command_status": command_status,
        "causation_hint": causation_hint,
    }


def execute_ceo_action_batch(
    repository: ControlPlaneRepository,
    *,
    action_batch: CEOActionBatch,
    accepted_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime_provider_config = resolve_runtime_provider_config()
    accepted_keys = {
        _action_key(action_type=str(item["action_type"]), payload=dict(item.get("payload") or {})): item
        for item in accepted_actions
    }
    executed_actions: list[dict[str, Any]] = []

    for action in action_batch.actions:
        action_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
        payload = action.payload.model_dump(mode="json")
        if _action_key(action_type=action_type, payload=payload) not in accepted_keys:
            continue

        if action.action_type == CEOActionType.NO_ACTION:
            executed_actions.append(
                _executed_entry(
                    action_type=action_type,
                    payload=payload,
                    execution_status="PASSTHROUGH",
                    reason=str(action.payload.reason),
                )
            )
            continue

        if action.action_type == CEOActionType.ESCALATE_TO_BOARD:
            executed_actions.append(
                _executed_entry(
                    action_type=action_type,
                    payload=payload,
                    execution_status="DEFERRED_SHADOW_ONLY",
                    reason="Board escalation stays in shadow mode during this limited CEO execution round.",
                )
            )
            continue

        if action.action_type == CEOActionType.CREATE_TICKET:
            from app.core.ticket_handlers import handle_ticket_create

            workflow = repository.get_workflow_projection(action.payload.workflow_id)
            if workflow is None:
                executed_actions.append(
                    _executed_entry(
                        action_type=action_type,
                        payload=payload,
                        execution_status="FAILED",
                        reason=f"Workflow {action.payload.workflow_id} was not found for limited CEO execution.",
                    )
                )
                continue
            command = build_ceo_create_ticket_command(
                workflow=workflow,
                payload=action.payload,
                repository=repository,
            )
            ack = handle_ticket_create(repository, command)
            executed_actions.append(
                _executed_entry(
                    action_type=action_type,
                    payload={**payload, "ticket_id": command.ticket_id},
                    execution_status=("EXECUTED" if ack.status.value == "ACCEPTED" else "DUPLICATE" if ack.status.value == "DUPLICATE" else "FAILED"),
                    reason=ack.reason or f"Limited CEO ticket create returned {ack.status.value}.",
                    command_status=ack.status.value,
                    causation_hint=ack.causation_hint,
                )
            )
            continue

        if action.action_type == CEOActionType.RETRY_TICKET:
            from app.core.ticket_handlers import handle_retry_ticket_from_ceo

            ack = handle_retry_ticket_from_ceo(
                repository,
                workflow_id=action.payload.workflow_id,
                ticket_id=action.payload.ticket_id,
                node_id=action.payload.node_id,
                reason=action.payload.reason,
                idempotency_key=f"ceo-retry-ticket:{action.payload.workflow_id}:{action.payload.ticket_id}",
            )
            executed_actions.append(
                _executed_entry(
                    action_type=action_type,
                    payload=payload,
                    execution_status=("EXECUTED" if ack.status.value == "ACCEPTED" else "DUPLICATE" if ack.status.value == "DUPLICATE" else "FAILED"),
                    reason=ack.reason or f"Limited CEO retry returned {ack.status.value}.",
                    command_status=ack.status.value,
                    causation_hint=ack.causation_hint,
                )
            )
            continue

        if action.action_type == CEOActionType.HIRE_EMPLOYEE:
            from app.core.employee_handlers import handle_ceo_direct_employee_hire

            template, staffing_reason = resolve_limited_ceo_staffing_combo(
                action.payload.role_type,
                action.payload.role_profile_refs,
            )
            if staffing_reason is not None or template is None:
                executed_actions.append(
                    _executed_entry(
                        action_type=action_type,
                        payload=payload,
                        execution_status="FAILED",
                        reason=staffing_reason or "Mainline staffing template could not be resolved.",
                    )
                )
                continue
            employee_id = action.payload.employee_id_hint or str(template["employee_id_hint"])
            variant_seed = get_settings().ceo_staffing_variant_seed
            resolved_profiles = (
                build_seeded_persona_variant(
                    action.payload.role_type,
                    variant_key=employee_id,
                    seed=variant_seed,
                    skill_profile=template.get("skill_profile"),
                    personality_profile=template.get("personality_profile"),
                    aesthetic_profile=template.get("aesthetic_profile"),
                )
                if variant_seed is not None
                else {
                    "skill_profile": dict(template.get("skill_profile") or {}),
                    "personality_profile": dict(template.get("personality_profile") or {}),
                    "aesthetic_profile": dict(template.get("aesthetic_profile") or {}),
                }
            )
            ack = handle_ceo_direct_employee_hire(
                repository,
                EmployeeHireRequestCommand(
                    workflow_id=action.payload.workflow_id,
                    employee_id=employee_id,
                    role_type=action.payload.role_type,
                    role_profile_refs=list(action.payload.role_profile_refs),
                    skill_profile=dict(resolved_profiles.get("skill_profile") or {}),
                    personality_profile=dict(resolved_profiles.get("personality_profile") or {}),
                    aesthetic_profile=dict(resolved_profiles.get("aesthetic_profile") or {}),
                    provider_id=(
                        action.payload.provider_id
                        or runtime_provider_config.default_provider_id
                        or template.get("provider_id")
                    ),
                    request_summary=action.payload.request_summary,
                    idempotency_key=f"ceo-hire-request:{action.payload.workflow_id}:{employee_id}",
                ),
            )
            executed_actions.append(
                _executed_entry(
                    action_type=action_type,
                    payload={**payload, "employee_id": employee_id},
                    execution_status=("EXECUTED" if ack.status.value == "ACCEPTED" else "DUPLICATE" if ack.status.value == "DUPLICATE" else "FAILED"),
                    reason=ack.reason or f"Limited CEO hire request returned {ack.status.value}.",
                    command_status=ack.status.value,
                    causation_hint=ack.causation_hint,
                )
            )
            continue

        if action.action_type == CEOActionType.REQUEST_MEETING:
            from app.core.meeting_handlers import handle_meeting_request

            ack = handle_meeting_request(
                repository,
                MeetingRequestCommand(
                    workflow_id=action.payload.workflow_id,
                    meeting_type=action.payload.meeting_type,
                    topic=action.payload.topic,
                    participant_employee_ids=list(action.payload.participant_employee_ids),
                    recorder_employee_id=action.payload.recorder_employee_id,
                    input_artifact_refs=list(action.payload.input_artifact_refs),
                    max_rounds=4,
                    idempotency_key=(
                        f"ceo-meeting-request:{action.payload.workflow_id}:"
                        f"{str(action.payload.source_graph_node_id or '').strip() or action.payload.source_ticket_id}:{action.payload.source_ticket_id}"
                    ),
                ),
            )
            executed_actions.append(
                _executed_entry(
                    action_type=action_type,
                    payload=payload,
                    execution_status=(
                        "EXECUTED"
                        if ack.status.value == "ACCEPTED"
                        else "DUPLICATE"
                        if ack.status.value == "DUPLICATE"
                        else "FAILED"
                    ),
                    reason=ack.reason or f"Limited CEO meeting request returned {ack.status.value}.",
                    command_status=ack.status.value,
                    causation_hint=ack.causation_hint,
                )
            )
            continue

        executed_actions.append(
            _executed_entry(
                action_type=action_type,
                payload=payload,
                execution_status="FAILED",
                reason="Unsupported CEO action type during limited execution.",
            )
        )

    summary = {
        "attempted_action_count": len(executed_actions),
        "executed_action_count": sum(1 for item in executed_actions if item["execution_status"] == "EXECUTED"),
        "duplicate_action_count": sum(1 for item in executed_actions if item["execution_status"] == "DUPLICATE"),
        "passthrough_action_count": sum(1 for item in executed_actions if item["execution_status"] == "PASSTHROUGH"),
        "deferred_action_count": sum(
            1 for item in executed_actions if item["execution_status"] == "DEFERRED_SHADOW_ONLY"
        ),
        "failed_action_count": sum(1 for item in executed_actions if item["execution_status"] == "FAILED"),
    }
    return {
        "executed_actions": executed_actions,
        "execution_summary": summary,
    }
