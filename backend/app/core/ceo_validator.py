from __future__ import annotations

from typing import Any

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
)
from app.core.output_schemas import OUTPUT_SCHEMA_REGISTRY
from app.core.staffing_catalog import resolve_mainline_staffing_combo
from app.db.repository import ControlPlaneRepository


_SUPPORTED_ROLE_PROFILES = {
    "ui_designer_primary",
    "frontend_engineer_primary",
    "checker_primary",
}


def _action_entry(action, reason: str) -> dict[str, Any]:
    action_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
    return {
        "action_type": action_type,
        "payload": action.payload.model_dump(mode="json"),
        "reason": reason,
    }


def validate_ceo_action_batch(
    repository: ControlPlaneRepository,
    *,
    action_batch: CEOActionBatch,
) -> dict[str, list[dict[str, Any]]]:
    accepted_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []

    for action in action_batch.actions:
        if action.action_type == CEOActionType.NO_ACTION:
            accepted_actions.append(_action_entry(action, "Shadow no-op is always allowed."))
            continue

        workflow = repository.get_workflow_projection(action.payload.workflow_id)
        if workflow is None:
            rejected_actions.append(_action_entry(action, "Target workflow does not exist."))
            continue

        if action.action_type == CEOActionType.HIRE_EMPLOYEE:
            template, staffing_reason = resolve_mainline_staffing_combo(
                action.payload.role_type,
                action.payload.role_profile_refs,
            )
            if staffing_reason is not None:
                rejected_actions.append(_action_entry(action, staffing_reason))
                continue
            if (
                action.payload.employee_id_hint
                and repository.get_employee_projection(action.payload.employee_id_hint) is not None
            ):
                rejected_actions.append(
                    _action_entry(action, "Suggested employee_id_hint already exists in the current roster.")
                )
                continue
            accepted_actions.append(
                _action_entry(
                    action,
                    f"Mainline staffing template {template['template_id']} is valid for shadow hire.",
                )
            )
            continue

        if action.action_type == CEOActionType.RETRY_TICKET:
            ticket = repository.get_current_ticket_projection(action.payload.ticket_id)
            if ticket is None:
                rejected_actions.append(_action_entry(action, "Target ticket does not exist."))
                continue
            if ticket["workflow_id"] != action.payload.workflow_id or ticket["node_id"] != action.payload.node_id:
                rejected_actions.append(_action_entry(action, "Target ticket does not match workflow or node."))
                continue
            if ticket["status"] not in {"FAILED", "TIMED_OUT", "CANCELLED", "CANCEL_REQUESTED"}:
                rejected_actions.append(
                    _action_entry(action, f"Ticket status {ticket['status']} is not retryable on the current mainline.")
                )
                continue
            accepted_actions.append(_action_entry(action, "Ticket is on a retryable terminal state."))
            continue

        if action.action_type == CEOActionType.CREATE_TICKET:
            if action.payload.role_profile_ref not in _SUPPORTED_ROLE_PROFILES:
                rejected_actions.append(
                    _action_entry(action, "role_profile_ref is not on the current local MVP staffing path.")
                )
                continue
            if (action.payload.output_schema_ref, 1) not in OUTPUT_SCHEMA_REGISTRY:
                rejected_actions.append(_action_entry(action, "output_schema_ref is not registered."))
                continue
            if repository.get_current_node_projection(action.payload.workflow_id, action.payload.node_id) is not None:
                rejected_actions.append(_action_entry(action, "node_id already exists in the current workflow."))
                continue
            accepted_actions.append(_action_entry(action, "Ticket proposal is structurally valid for shadow review."))
            continue

        if action.action_type == CEOActionType.ESCALATE_TO_BOARD:
            accepted_actions.append(
                _action_entry(action, "Board escalation proposal is structurally valid for shadow review.")
            )
            continue

        rejected_actions.append(_action_entry(action, "Unsupported CEO action type."))

    return {
        "accepted_actions": accepted_actions,
        "rejected_actions": rejected_actions,
    }
