from __future__ import annotations

from typing import Any

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
)
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_project_init_scope_ticket_id,
    is_project_init_scope_preset,
    supports_ceo_create_ticket_preset,
)
from app.core.output_schemas import OUTPUT_SCHEMA_REGISTRY
from app.core.persona_profiles import (
    build_high_overlap_rejection_reason,
    find_same_role_high_overlap_conflict,
)
from app.core.staffing_catalog import resolve_mainline_staffing_combo
from app.db.repository import ControlPlaneRepository


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
            conflict = find_same_role_high_overlap_conflict(
                role_type=action.payload.role_type,
                skill_profile=template.get("skill_profile") or {},
                personality_profile=template.get("personality_profile") or {},
                aesthetic_profile=template.get("aesthetic_profile") or {},
                employees=repository.list_employee_projections(
                    states=["ACTIVE"],
                    board_approved_only=True,
                ),
            )
            if conflict is not None:
                rejected_actions.append(
                    _action_entry(
                        action,
                        build_high_overlap_rejection_reason(
                            role_type=action.payload.role_type,
                            conflict=conflict,
                        ),
                    )
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
            if ticket["status"] not in {"FAILED", "TIMED_OUT"}:
                rejected_actions.append(
                    _action_entry(action, f"Ticket status {ticket['status']} is not retryable on the current mainline.")
                )
                continue
            accepted_actions.append(_action_entry(action, "Ticket is on a retryable terminal state."))
            continue

        if action.action_type == CEOActionType.CREATE_TICKET:
            if (action.payload.output_schema_ref, 1) not in OUTPUT_SCHEMA_REGISTRY:
                rejected_actions.append(_action_entry(action, "output_schema_ref is not registered."))
                continue
            if not supports_ceo_create_ticket_preset(
                role_profile_ref=action.payload.role_profile_ref,
                output_schema_ref=action.payload.output_schema_ref,
            ):
                rejected_actions.append(
                    _action_entry(action, "role_profile_ref and output_schema_ref are not on the current limited CEO execution path.")
                )
                continue
            if is_project_init_scope_preset(
                role_profile_ref=action.payload.role_profile_ref,
                output_schema_ref=action.payload.output_schema_ref,
            ):
                if action.payload.node_id != PROJECT_INIT_SCOPE_NODE_ID:
                    rejected_actions.append(
                        _action_entry(
                            action,
                            f"Project-init kickoff ticket must use node_id {PROJECT_INIT_SCOPE_NODE_ID}.",
                        )
                    )
                    continue
                expected_ticket_id = build_project_init_scope_ticket_id(action.payload.workflow_id)
                if repository.get_current_node_projection(
                    action.payload.workflow_id,
                    PROJECT_INIT_SCOPE_NODE_ID,
                ) is not None:
                    rejected_actions.append(
                        _action_entry(action, "Project-init kickoff node already exists in the current workflow.")
                    )
                    continue
                if repository.get_current_ticket_projection(expected_ticket_id) is not None:
                    rejected_actions.append(
                        _action_entry(action, "Project-init kickoff ticket already exists in projection state.")
                    )
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
