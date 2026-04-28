from __future__ import annotations

from typing import Any

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
)
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_project_init_scope_ticket_id,
    is_project_init_governance_kickoff,
    is_project_init_scope_preset,
    supports_ceo_create_ticket_preset,
)
from app.core.ceo_snapshot_contracts import capability_plan_view, controller_state_view, replan_focus_view
from app.core.constants import EMPLOYEE_STATE_ACTIVE
from app.core.execution_targets import (
    infer_execution_contract_payload,
    employee_supports_execution_contract,
)
from app.core.employee_reuse import build_role_already_covered_details
from app.core.output_schemas import (
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    OUTPUT_SCHEMA_REGISTRY,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.core.persona_profiles import (
    build_seeded_persona_variant,
    build_high_overlap_rejection_reason,
    find_same_role_high_overlap_conflict,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.config import get_settings
from app.core.staffing_catalog import (
    STAFFING_CAPACITY_HIRE_ALLOWED_REASON_CODE,
    STAFFING_CAP_REACHED_REASON_CODE,
    build_staffing_capacity_details,
    count_active_board_approved_staffing_matches,
    resolve_available_staffing_employee_id,
    resolve_limited_ceo_staffing_combo,
    staffing_capacity_is_available,
)
from app.core.runtime_node_views import (
    MATERIALIZATION_STATE_MATERIALIZED,
    build_runtime_graph_node_views,
)
from app.core.runtime_node_lifecycle import (
    resolve_runtime_node_lifecycle,
)
from app.db.repository import ControlPlaneRepository


def _action_entry(action, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    action_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
    entry = {
        "action_type": action_type,
        "payload": action.payload.model_dump(mode="json"),
        "reason": reason,
    }
    if details is not None:
        entry["details"] = details
    return entry


def _snapshot_allows_capacity_hire(
    snapshot: dict[str, Any] | None,
    *,
    role_type: str,
    role_profile_refs: list[str],
    capacity_details: dict[str, Any],
) -> bool:
    if snapshot is None or not staffing_capacity_is_available(capacity_details):
        return False
    controller_state = controller_state_view(snapshot)
    if str(controller_state.get("recommended_action") or "").strip() != "HIRE_EMPLOYEE":
        return False
    capability_plan = capability_plan_view(snapshot)
    recommended_hire = capability_plan.get("recommended_hire")
    if not isinstance(recommended_hire, dict):
        return False
    normalized_refs = sorted(str(item).strip() for item in role_profile_refs if str(item).strip())
    recommended_refs = sorted(
        str(item).strip()
        for item in list(recommended_hire.get("role_profile_refs") or [])
        if str(item).strip()
    )
    if str(recommended_hire.get("role_type") or "").strip() != str(role_type or "").strip():
        return False
    if recommended_refs != normalized_refs:
        return False
    for gap in list(capability_plan.get("ready_ticket_staffing_gaps") or []):
        if not isinstance(gap, dict):
            continue
        if str(gap.get("reason_code") or "").strip() not in {"NO_ACTIVE_ROLE_WORKER", "WORKER_BUSY"}:
            continue
        if str(gap.get("role_type") or "").strip() != str(role_type or "").strip():
            continue
        gap_ref = str(gap.get("required_role_profile_ref") or "").strip()
        if gap_ref and gap_ref in normalized_refs:
            return True
    return False


def validate_ceo_action_batch(
    repository: ControlPlaneRepository,
    *,
    action_batch: CEOActionBatch,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    accepted_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []

    for action in action_batch.actions:
        if action.action_type == CEOActionType.NO_ACTION:
            if snapshot is not None:
                controller_state = controller_state_view(snapshot)
                expected_action = str(controller_state.get("recommended_action") or "").strip()
                if expected_action and expected_action != "NO_ACTION":
                    rejected_actions.append(
                        _action_entry(
                            action,
                            (
                                "NO_ACTION is not allowed because controller_state.recommended_action is "
                                f"{expected_action}."
                            ),
                        )
                    )
                    continue
            accepted_actions.append(_action_entry(action, "Shadow no-op is always allowed."))
            continue

        workflow = repository.get_workflow_projection(action.payload.workflow_id)
        if workflow is None:
            rejected_actions.append(_action_entry(action, "Target workflow does not exist."))
            continue

        if action.action_type == CEOActionType.HIRE_EMPLOYEE:
            template, staffing_reason = resolve_limited_ceo_staffing_combo(
                action.payload.role_type,
                action.payload.role_profile_refs,
            )
            if staffing_reason is not None:
                rejected_actions.append(_action_entry(action, staffing_reason))
                continue
            all_employees = repository.list_employee_projections()
            active_matching_count = count_active_board_approved_staffing_matches(
                role_type=action.payload.role_type,
                role_profile_refs=action.payload.role_profile_refs,
                employees=all_employees,
            )
            max_active_count = int(template["max_active_count"])
            if (
                action.payload.employee_id_hint
                and repository.get_employee_projection(action.payload.employee_id_hint) is not None
            ):
                rejected_actions.append(
                    _action_entry(action, "Suggested employee_id_hint already exists in the current roster.")
                )
                continue
            employee_id = resolve_available_staffing_employee_id(
                employee_id_hint=action.payload.employee_id_hint,
                template=template,
                existing_employee_ids=[employee["employee_id"] for employee in all_employees],
            )
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
            capacity_details = build_staffing_capacity_details(
                reason_code=STAFFING_CAPACITY_HIRE_ALLOWED_REASON_CODE,
                role_type=action.payload.role_type,
                role_profile_refs=action.payload.role_profile_refs,
                active_matching_count=active_matching_count,
                max_active_count=max_active_count,
                template_id=str(template["template_id"]),
                resolved_employee_id=employee_id,
            )
            capacity_hire_allowed = _snapshot_allows_capacity_hire(
                snapshot,
                role_type=action.payload.role_type,
                role_profile_refs=action.payload.role_profile_refs,
                capacity_details=capacity_details,
            )
            conflict = find_same_role_high_overlap_conflict(
                role_type=action.payload.role_type,
                skill_profile=resolved_profiles.get("skill_profile") or {},
                personality_profile=resolved_profiles.get("personality_profile") or {},
                aesthetic_profile=resolved_profiles.get("aesthetic_profile") or {},
                employees=repository.list_employee_projections(
                    states=["ACTIVE"],
                    board_approved_only=True,
                ),
            )
            if conflict is not None and not capacity_hire_allowed:
                details = build_role_already_covered_details(
                    role_type=action.payload.role_type,
                    role_profile_refs=action.payload.role_profile_refs,
                    reuse_candidate_employee_id=str(conflict["employee_id"]),
                )
                rejected_actions.append(
                    _action_entry(
                        action,
                        build_high_overlap_rejection_reason(
                            role_type=action.payload.role_type,
                            conflict=conflict,
                        ),
                        details,
                    )
                )
                continue
            if active_matching_count >= max_active_count:
                details = build_staffing_capacity_details(
                    reason_code=STAFFING_CAP_REACHED_REASON_CODE,
                    role_type=action.payload.role_type,
                    role_profile_refs=action.payload.role_profile_refs,
                    active_matching_count=active_matching_count,
                    max_active_count=max_active_count,
                    template_id=str(template["template_id"]),
                )
                rejected_actions.append(
                    _action_entry(
                        action,
                        (
                            "Staffing capacity cap is reached for "
                            f"{action.payload.role_type} on the current limited CEO staffing path."
                        ),
                        details,
                    )
                )
                continue
            accepted_actions.append(
                _action_entry(
                    action,
                    f"Mainline staffing template {template['template_id']} is valid for shadow hire.",
                    capacity_details if capacity_hire_allowed else None,
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

        if action.action_type == CEOActionType.REQUEST_MEETING:
            if snapshot is None:
                rejected_actions.append(
                    _action_entry(action, "Meeting requests require the current CEO snapshot for validation.")
                )
                continue
            candidate = next(
                (
                    item
                    for item in replan_focus_view(snapshot).get("meeting_candidates") or []
                    if str(item.get("source_ticket_id") or "") == action.payload.source_ticket_id
                    and str(item.get("source_graph_node_id") or "") == action.payload.source_graph_node_id
                ),
                None,
            )
            if candidate is None:
                rejected_actions.append(
                    _action_entry(action, "Requested meeting does not match any snapshot meeting candidate.")
                )
                continue
            if not bool(candidate.get("eligible")):
                rejected_actions.append(
                    _action_entry(
                        action,
                        str(candidate.get("eligibility_reason") or "Snapshot candidate is not eligible."),
                    )
                )
                continue
            if action.payload.meeting_type != "TECHNICAL_DECISION":
                rejected_actions.append(
                    _action_entry(action, "Only TECHNICAL_DECISION meetings are on the current limited CEO path.")
                )
                continue
            if action.payload.topic != str(candidate.get("topic") or ""):
                rejected_actions.append(
                    _action_entry(action, "Meeting topic must match the snapshot candidate exactly.")
                )
                continue
            if list(action.payload.participant_employee_ids) != list(candidate.get("participant_employee_ids") or []):
                rejected_actions.append(
                    _action_entry(action, "Meeting participants must match the snapshot candidate exactly.")
                )
                continue
            if action.payload.recorder_employee_id != str(candidate.get("recorder_employee_id") or ""):
                rejected_actions.append(
                    _action_entry(action, "Meeting recorder must match the snapshot candidate exactly.")
                )
                continue
            if list(action.payload.input_artifact_refs) != list(candidate.get("input_artifact_refs") or []):
                rejected_actions.append(
                    _action_entry(action, "Meeting input_artifact_refs must match the snapshot candidate exactly.")
                )
                continue
            if repository.get_current_ticket_projection(action.payload.source_ticket_id) is None:
                rejected_actions.append(_action_entry(action, "Source ticket does not exist anymore."))
                continue
            graph_snapshot = build_ticket_graph_snapshot(repository, action.payload.workflow_id)
            runtime_views = build_runtime_graph_node_views(
                repository,
                action.payload.workflow_id,
                graph_snapshot=graph_snapshot,
            )
            source_view = runtime_views.get(action.payload.source_graph_node_id)
            if source_view is None or source_view.materialization_state != MATERIALIZATION_STATE_MATERIALIZED:
                rejected_actions.append(_action_entry(action, "Source graph node does not exist anymore."))
                continue
            if str(source_view.ticket_id or "") != action.payload.source_ticket_id:
                rejected_actions.append(
                    _action_entry(action, "Source graph node no longer points at the requested ticket.")
                )
                continue
            accepted_actions.append(
                _action_entry(action, "Meeting request matches one eligible snapshot candidate.")
            )
            continue

        if action.action_type == CEOActionType.CREATE_TICKET:
            if snapshot is not None and action.payload.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
                closeout_gate_issue = capability_plan_view(snapshot).get("closeout_gate_issue")
                if isinstance(closeout_gate_issue, dict) and closeout_gate_issue:
                    rejected_actions.append(
                        _action_entry(
                            action,
                            "CREATE_TICKET is blocked because the closeout gate is not satisfied.",
                            details={"closeout_gate_issue": closeout_gate_issue},
                        )
                    )
                    continue
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
            expected_execution_contract = infer_execution_contract_payload(
                role_profile_ref=action.payload.role_profile_ref,
                output_schema_ref=action.payload.output_schema_ref,
            )
            payload_execution_contract = (
                action.payload.execution_contract.model_dump(mode="json")
                if action.payload.execution_contract is not None
                else None
            )
            if payload_execution_contract is None:
                rejected_actions.append(_action_entry(action, "CREATE_TICKET requires execution_contract."))
                continue
            if payload_execution_contract != expected_execution_contract:
                rejected_actions.append(
                    _action_entry(
                        action,
                        "execution_contract does not match the current limited CEO execution target contract.",
                    )
                )
                continue
            if action.payload.dispatch_intent is None:
                rejected_actions.append(_action_entry(action, "CREATE_TICKET requires dispatch_intent."))
                continue
            assignee_employee_id = str(action.payload.dispatch_intent.assignee_employee_id or "").strip()
            assignee = repository.get_employee_projection(assignee_employee_id)
            if assignee is None:
                rejected_actions.append(
                    _action_entry(
                        action,
                        f"dispatch_intent.assignee_employee_id {assignee_employee_id} does not exist.",
                    )
                )
                continue
            if str(assignee.get("state") or "") != EMPLOYEE_STATE_ACTIVE:
                rejected_actions.append(
                    _action_entry(
                        action,
                        f"dispatch_intent.assignee_employee_id {assignee_employee_id} is not active.",
                    )
                )
                continue
            if not employee_supports_execution_contract(
                employee=assignee,
                execution_contract=payload_execution_contract,
            ):
                rejected_actions.append(
                    _action_entry(
                        action,
                        (
                            "dispatch_intent.assignee_employee_id "
                            f"{assignee_employee_id} does not satisfy required capability tags."
                        ),
                    )
                )
                continue
            if is_project_init_scope_preset(
                role_profile_ref=action.payload.role_profile_ref,
                output_schema_ref=action.payload.output_schema_ref,
            ) or is_project_init_governance_kickoff(
                node_id=action.payload.node_id,
                output_schema_ref=action.payload.output_schema_ref,
                parent_ticket_id=action.payload.parent_ticket_id,
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
                project_init_node_view = resolve_runtime_node_lifecycle(
                    repository,
                    action.payload.workflow_id,
                    PROJECT_INIT_SCOPE_NODE_ID,
                )
                if project_init_node_view.materialization_state == MATERIALIZATION_STATE_MATERIALIZED:
                    rejected_actions.append(
                        _action_entry(action, "Project-init kickoff node already exists in the current workflow.")
                    )
                    continue
                if repository.get_current_ticket_projection(expected_ticket_id) is not None:
                    rejected_actions.append(
                        _action_entry(action, "Project-init kickoff ticket already exists in projection state.")
                    )
                    continue
            node_view = resolve_runtime_node_lifecycle(
                repository,
                action.payload.workflow_id,
                action.payload.node_id,
            )
            if node_view.materialization_state == MATERIALIZATION_STATE_MATERIALIZED:
                rejected_actions.append(_action_entry(action, "node_id already exists in the current workflow."))
                continue
            if snapshot is not None:
                required_governance_ticket_plan = (
                    capability_plan_view(snapshot).get("required_governance_ticket_plan")
                )
                if isinstance(required_governance_ticket_plan, dict):
                    planned_payload = required_governance_ticket_plan.get("ticket_payload") or {}
                    matching_required_governance_plan = (
                        str(planned_payload.get("node_id") or "") == action.payload.node_id
                        and str(planned_payload.get("role_profile_ref") or "")
                        == action.payload.role_profile_ref
                        and str(planned_payload.get("output_schema_ref") or "")
                        == action.payload.output_schema_ref
                    )
                    planned_dispatch_intent = planned_payload.get("dispatch_intent") or {}
                    planned_assignee_employee_id = str(
                        planned_dispatch_intent.get("assignee_employee_id") or ""
                    ).strip()
                    planned_parent_ticket_id = str(
                        planned_payload.get("parent_ticket_id") or ""
                    ).strip()
                    if matching_required_governance_plan:
                        if planned_assignee_employee_id and planned_assignee_employee_id != assignee_employee_id:
                            rejected_actions.append(
                                _action_entry(
                                    action,
                                    "CREATE_TICKET assignee does not match the current capability_plan.required_governance_ticket_plan.",
                                )
                            )
                            continue
                        if planned_parent_ticket_id and planned_parent_ticket_id != str(
                            action.payload.parent_ticket_id or ""
                        ).strip():
                            rejected_actions.append(
                                _action_entry(
                                    action,
                                    "CREATE_TICKET parent_ticket_id does not match the current capability_plan.required_governance_ticket_plan.",
                                )
                            )
                            continue
                        accepted_actions.append(
                            _action_entry(
                                action,
                                "CREATE_TICKET matches the current capability_plan.required_governance_ticket_plan.",
                            )
                        )
                        continue
                    rejected_actions.append(
                        _action_entry(
                            action,
                            "CREATE_TICKET does not match the current capability_plan.required_governance_ticket_plan.",
                        )
                    )
                    continue
            if snapshot is not None and action.payload.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
                controller_state = controller_state_view(snapshot)
                controller_gate_state = str(controller_state.get("state") or "").strip()
                if controller_gate_state in {"GOVERNANCE_REQUIRED", "ARCHITECT_REQUIRED", "MEETING_REQUIRED"}:
                    rejected_actions.append(
                        _action_entry(
                            action,
                            str(controller_state.get("blocking_reason") or "Controller gate must be satisfied first."),
                        )
                    )
                    continue
                planned_followups = list(capability_plan_view(snapshot).get("followup_ticket_plans") or [])
                if planned_followups:
                    matching_plan = next(
                        (
                            item
                            for item in planned_followups
                            if str(((item.get("ticket_payload") or {}).get("node_id") or "")) == action.payload.node_id
                            and str(((item.get("ticket_payload") or {}).get("role_profile_ref") or ""))
                            == action.payload.role_profile_ref
                        ),
                        None,
                    )
                    if matching_plan is None:
                        rejected_actions.append(
                            _action_entry(
                                action,
                                "CREATE_TICKET does not match the current capability_plan followup ticket routing.",
                            )
                        )
                        continue
                    planned_assignee_employee_id = str(
                        (((matching_plan.get("ticket_payload") or {}).get("dispatch_intent") or {}).get(
                            "assignee_employee_id"
                        ) or "")
                    ).strip()
                    if planned_assignee_employee_id and planned_assignee_employee_id != assignee_employee_id:
                        rejected_actions.append(
                            _action_entry(
                                action,
                                "CREATE_TICKET assignee does not match the current capability_plan routing.",
                            )
                        )
                        continue
            accepted_actions.append(
                _action_entry(
                    action,
                    f"Ticket proposal is structurally valid and dispatches to {assignee_employee_id}.",
                )
            )
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
