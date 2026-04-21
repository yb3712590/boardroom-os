from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
    CEOCreateTicketAction,
    CEOCreateTicketPayload,
    CEORequestMeetingAction,
    CEORequestMeetingPayload,
    CEONoAction,
    CEONoActionPayload,
)
from app.core.ceo_prompts import build_ceo_shadow_rendered_payload
from app.core.ceo_snapshot_contracts import (
    capability_plan_view,
    controller_state_view,
    replan_focus_view,
)
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED
from app.core.execution_targets import (
    employee_supports_execution_contract,
    infer_execution_contract_payload,
)
from app.core.provider_openai_compat import (
    OpenAICompatProviderConfig,
    OpenAICompatProviderError,
    invoke_openai_compat_response,
    load_openai_compat_result_payload,
)
from app.core.provider_claude_code import ClaudeCodeProviderConfig, ClaudeCodeProviderError, invoke_claude_code_response
from app.core.output_schemas import (
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.core.runtime_node_views import (
    MATERIALIZATION_STATE_MATERIALIZED,
)
from app.core.runtime_node_lifecycle import (
    resolve_runtime_node_lifecycle,
)
from app.core.workflow_completion import ticket_has_delivery_mainline_evidence
from app.core.workflow_progression import (
    build_project_init_kickoff_spec,
)
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate
from app.core.runtime_provider_config import (
    RuntimeProviderAdapterKind,
    ROLE_BINDING_CEO_SHADOW,
    find_provider_entry,
    provider_effective_mode,
    resolve_provider_failover_selections,
    resolve_provider_selection,
    RuntimeProviderConfigStore,
    resolve_runtime_provider_config,
    runtime_provider_effective_mode,
    runtime_provider_health_summary,
)
from app.core.workflow_controller import backlog_followup_key_to_node_id as controller_backlog_followup_key_to_node_id
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class CEOProposalResult:
    action_batch: CEOActionBatch
    effective_mode: str
    provider_health_summary: str
    model: str | None
    preferred_provider_id: str | None = None
    preferred_model: str | None = None
    actual_provider_id: str | None = None
    actual_model: str | None = None
    selection_reason: str | None = None
    policy_reason: str | None = None
    provider_response_id: str | None = None
    fallback_reason: str | None = None


PROVIDER_FAILOVER_FAILURE_KINDS = {"PROVIDER_RATE_LIMITED", "UPSTREAM_UNAVAILABLE"}
MAINLINE_DETERMINISTIC_TRIGGER_TYPES = {
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    "APPROVAL_RESOLVED",
    "TICKET_COMPLETED",
    "TICKET_FAILED",
    "TICKET_TIMED_OUT",
    "SCHEDULER_IDLE_MAINTENANCE",
}
MAINLINE_MUTATING_DETERMINISTIC_ACTIONS = {
    CEOActionType.CREATE_TICKET.value,
    CEOActionType.HIRE_EMPLOYEE.value,
    CEOActionType.REQUEST_MEETING.value,
}


class CEOProposalContractError(ValueError):
    def __init__(
        self,
        *,
        source_component: str,
        reason_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.source_component = source_component
        self.reason_code = reason_code
        self.details = dict(details or {})
        super().__init__(f"{source_component}[{reason_code}]: {message}")


def _raise_proposal_contract_error(
    *,
    source_component: str,
    reason_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    raise CEOProposalContractError(
        source_component=source_component,
        reason_code=reason_code,
        message=message,
        details=details,
    )


def build_no_action_batch(reason: str) -> CEOActionBatch:
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEONoAction(
                action_type="NO_ACTION",
                payload=CEONoActionPayload(reason=reason),
            )
        ],
    )


def _is_mainline_deterministic_trigger(snapshot: dict[str, Any]) -> bool:
    trigger = snapshot.get("trigger") or {}
    return str(trigger.get("trigger_type") or "").strip() in MAINLINE_DETERMINISTIC_TRIGGER_TYPES


def _mainline_deterministic_mutating_actions(action_batch: CEOActionBatch) -> list[str]:
    action_types: list[str] = []
    for action in action_batch.actions:
        action_type = str(
            action.action_type.value if hasattr(action.action_type, "value") else action.action_type
        ).strip()
        if action_type in MAINLINE_MUTATING_DETERMINISTIC_ACTIONS:
            action_types.append(action_type)
    return action_types


def _maybe_raise_mainline_deterministic_fallback_blocked(
    *,
    snapshot: dict[str, Any],
    action_batch: CEOActionBatch,
    fallback_reason: str,
    effective_mode: str,
) -> None:
    if not _is_mainline_deterministic_trigger(snapshot):
        return
    blocked_action_types = _mainline_deterministic_mutating_actions(action_batch)
    if not blocked_action_types:
        return
    trigger = snapshot.get("trigger") or {}
    _raise_proposal_contract_error(
        source_component="mainline_deterministic_fallback",
        reason_code="mutating_fallback_blocked",
        message=(
            "Automatic CEO mainline trigger cannot use deterministic fallback for mutating actions: "
            f"{', '.join(blocked_action_types)}."
        ),
        details={
            "trigger_type": str(trigger.get("trigger_type") or "").strip(),
            "trigger_ref": str(trigger.get("trigger_ref") or "").strip() or None,
            "effective_mode": effective_mode,
            "fallback_reason": fallback_reason,
            "blocked_action_types": blocked_action_types,
        },
    )


def _should_fallback_to_project_init_kickoff(snapshot: dict) -> bool:
    trigger = snapshot.get("trigger") or {}
    ticket_summary = snapshot.get("ticket_summary") or {}
    return (
        str(trigger.get("trigger_type") or "") == EVENT_BOARD_DIRECTIVE_RECEIVED
        and int(ticket_summary.get("total") or 0) == 0
        and not snapshot.get("approvals")
        and not snapshot.get("incidents")
    )

def _select_default_assignee(
    snapshot: dict,
    *,
    role_profile_ref: str,
    output_schema_ref: str,
) -> str | None:
    execution_contract = infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if execution_contract is None:
        return None

    employees = sorted(
        snapshot.get("employees") or [],
        key=lambda item: str(item.get("employee_id") or ""),
    )
    for employee in employees:
        if str(employee.get("state") or "") != "ACTIVE":
            continue
        if not employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            continue
        return str(employee["employee_id"])
    return None


def _build_project_init_kickoff_batch(snapshot: dict, reason: str) -> CEOActionBatch:
    workflow = snapshot.get("workflow") or {}
    kickoff_spec = build_project_init_kickoff_spec(workflow)
    assignee_employee_id = _select_default_assignee(
        snapshot,
        role_profile_ref=str(kickoff_spec["role_profile_ref"]),
        output_schema_ref=str(kickoff_spec["output_schema_ref"]),
    )
    if assignee_employee_id is None:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.project_init_kickoff",
            reason_code="assignee_missing",
            message="Project-init kickoff could not resolve an active assignee.",
            details={"workflow_id": str(workflow.get("workflow_id") or "").strip()},
        )
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEOCreateTicketAction(
                action_type=CEOActionType.CREATE_TICKET,
                payload=CEOCreateTicketPayload(
                    workflow_id=str(workflow["workflow_id"]),
                    node_id=str(kickoff_spec["node_id"]),
                    role_profile_ref=str(kickoff_spec["role_profile_ref"]),
                    output_schema_ref=str(kickoff_spec["output_schema_ref"]),
                    execution_contract=infer_execution_contract_payload(
                        role_profile_ref=str(kickoff_spec["role_profile_ref"]),
                        output_schema_ref=str(kickoff_spec["output_schema_ref"]),
                    ),
                    dispatch_intent={
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": (
                            "Keep the first governance document on the current live frontend owner."
                            if str(kickoff_spec["output_schema_ref"]) == "architecture_brief"
                            else "Use the active frontend delivery owner for the kickoff scope consensus ticket."
                        ),
                    },
                    summary=str(kickoff_spec["summary"]),
                    parent_ticket_id=None,
                ),
            )
        ],
    )


def _eligible_meeting_candidates(snapshot: dict) -> list[dict]:
    replan_focus = replan_focus_view(snapshot)
    return [
        item
        for item in replan_focus.get("meeting_candidates") or []
        if bool(item.get("eligible"))
    ]


def _build_request_meeting_batch(candidate: dict, reason: str) -> CEOActionBatch:
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEORequestMeetingAction(
                action_type=CEOActionType.REQUEST_MEETING,
                payload=CEORequestMeetingPayload(
                    workflow_id=str(candidate["workflow_id"]),
                    meeting_type="TECHNICAL_DECISION",
                    source_graph_node_id=str(candidate["source_graph_node_id"]),
                    source_ticket_id=str(candidate["source_ticket_id"]),
                    topic=str(candidate["topic"]),
                    participant_employee_ids=list(candidate.get("participant_employee_ids") or []),
                    recorder_employee_id=str(candidate["recorder_employee_id"]),
                    input_artifact_refs=list(candidate.get("input_artifact_refs") or []),
                    reason=str(candidate["reason"]),
                ),
            )
        ],
    )


def _normalize_dependency_gate_refs(raw_refs: Any) -> list[str]:
    normalized_refs: list[str] = []
    seen_refs: set[str] = set()
    for item in list(raw_refs or []):
        normalized_ref = str(item).strip()
        if not normalized_ref or normalized_ref in seen_refs:
            continue
        seen_refs.add(normalized_ref)
        normalized_refs.append(normalized_ref)
    return normalized_refs


def _normalize_provider_action_batch_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        _raise_proposal_contract_error(
            source_component="provider_action_batch",
            reason_code="batch_not_object",
            message="Provider output must be a JSON object.",
            details={"payload_type": type(raw_payload).__name__},
        )

    raw_actions = raw_payload.get("actions")
    if not isinstance(raw_actions, list):
        _raise_proposal_contract_error(
            source_component="provider_action_batch",
            reason_code="actions_not_list",
            message="Provider action batch must include an actions list.",
            details={"actions_type": type(raw_actions).__name__},
        )

    normalized_actions: list[dict[str, Any]] = []
    for index, action in enumerate(raw_actions):
        if not isinstance(action, dict):
            _raise_proposal_contract_error(
                source_component="provider_action_batch",
                reason_code="action_not_object",
                message="Each provider action must be a JSON object.",
                details={"action_index": index, "action_type": type(action).__name__},
            )
        action_type_field = action.get("action_type")
        legacy_alias_action_type_field = action.get("type")
        action_type = str(action_type_field or "").strip()
        if legacy_alias_action_type_field is not None:
            _raise_proposal_contract_error(
                source_component="provider_action_batch",
                reason_code="action_type_legacy_alias",
                message="Each provider action must use action_type. The legacy type alias is not allowed.",
                details={
                    "action_index": index,
                    "type": str(legacy_alias_action_type_field),
                },
            )
        if not action_type:
            _raise_proposal_contract_error(
                source_component="provider_action_batch",
                reason_code="action_type_missing",
                message="Each provider action must include action_type.",
                details={"action_index": index},
            )
        if "payload" not in action:
            _raise_proposal_contract_error(
                source_component="provider_action_batch",
                reason_code="payload_missing",
                message=f"{action_type} must include payload.",
                details={"action_index": index, "action_type": action_type},
            )
        action_payload = action.get("payload")
        if not isinstance(action_payload, dict):
            _raise_proposal_contract_error(
                source_component="provider_action_batch",
                reason_code="payload_not_object",
                message=f"{action_type} payload must be a JSON object.",
                details={
                    "action_index": index,
                    "action_type": action_type,
                    "payload_type": type(action_payload).__name__,
                },
            )
        normalized_actions.append(
            {
                "action_type": action_type,
                "payload": action_payload,
            }
        )
    return {
        "summary": str(raw_payload.get("summary") or "CEO shadow action batch").strip() or "CEO shadow action batch",
        "actions": normalized_actions,
    }


def _backlog_followup_key_to_node_id(ticket_key: str) -> str:
    return controller_backlog_followup_key_to_node_id(ticket_key)

def _build_backlog_followup_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch | None:
    workflow = snapshot.get("workflow") or {}
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if not workflow_id:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.backlog_followup",
            reason_code="workflow_id_missing",
            message="Backlog follow-up requires workflow.workflow_id.",
        )
    capability_plan = capability_plan_view(snapshot)
    followup_ticket_plans = list(capability_plan.get("followup_ticket_plans") or [])
    if not followup_ticket_plans:
        return None

    actions: list[dict[str, Any]] = []
    existing_ticket_ids_by_node_id = {
        str(plan.get("node_id") or "").strip(): str(plan.get("existing_ticket_id") or "").strip()
        for plan in followup_ticket_plans
        if str(plan.get("node_id") or "").strip() and str(plan.get("existing_ticket_id") or "").strip()
    }
    existing_node_ids = set(existing_ticket_ids_by_node_id)
    planned_ticket_keys = {
        str(plan.get("ticket_key") or "").strip()
        for plan in followup_ticket_plans
        if isinstance(plan, dict) and str(plan.get("ticket_key") or "").strip()
    }

    for index, followup_plan in enumerate(followup_ticket_plans):
        if not isinstance(followup_plan, dict):
            _raise_proposal_contract_error(
                source_component="deterministic_fallback.backlog_followup",
                reason_code="plan_not_object",
                message="Each followup ticket plan must be a JSON object.",
                details={"plan_index": index},
            )
        node_id = str(followup_plan.get("node_id") or "").strip()
        ticket_key = str(followup_plan.get("ticket_key") or "").strip()
        role_profile_ref = str(followup_plan.get("role_profile_ref") or "").strip()
        output_schema_ref = str(followup_plan.get("output_schema_ref") or "").strip()
        assignee_employee_id = str(followup_plan.get("assignee_employee_id") or "").strip()
        backlog_ticket_id = str(followup_plan.get("source_ticket_id") or "").strip()
        missing_fields = [
            field_name
            for field_name, field_value in (
                ("ticket_key", ticket_key),
                ("node_id", node_id),
                ("role_profile_ref", role_profile_ref),
                ("output_schema_ref", output_schema_ref),
                ("assignee_employee_id", assignee_employee_id),
                ("source_ticket_id", backlog_ticket_id),
            )
            if not field_value
        ]
        if missing_fields:
            _raise_proposal_contract_error(
                source_component="deterministic_fallback.backlog_followup",
                reason_code="plan_missing_fields",
                message="Backlog follow-up plan is missing required fields.",
                details={"plan_index": index, "missing_fields": missing_fields},
            )
        if node_id in existing_ticket_ids_by_node_id or node_id in existing_node_ids:
            continue

        dependency_gate_refs = _normalize_dependency_gate_refs(followup_plan.get("dependency_gate_refs"))
        ready_to_create = True
        for dependency_key in list(followup_plan.get("dependency_ticket_keys") or []):
            normalized_dependency_key = str(dependency_key).strip()
            if not normalized_dependency_key:
                _raise_proposal_contract_error(
                    source_component="deterministic_fallback.backlog_followup",
                    reason_code="dependency_key_empty",
                    message="Backlog follow-up dependency keys must be non-empty strings.",
                    details={"plan_index": index, "ticket_key": ticket_key},
                )
            dependency_node_id = _backlog_followup_key_to_node_id(normalized_dependency_key)
            dependency_ticket_id = existing_ticket_ids_by_node_id.get(dependency_node_id)
            if not dependency_ticket_id:
                if normalized_dependency_key not in planned_ticket_keys:
                    _raise_proposal_contract_error(
                        source_component="deterministic_fallback.backlog_followup",
                        reason_code="dependency_unresolved",
                        message="Backlog follow-up dependency does not match any known ticket plan or existing ticket.",
                        details={
                            "plan_index": index,
                            "ticket_key": ticket_key,
                            "dependency_ticket_key": normalized_dependency_key,
                        },
                    )
                ready_to_create = False
                break
            if dependency_ticket_id not in dependency_gate_refs:
                dependency_gate_refs.append(dependency_ticket_id)
        if not ready_to_create:
            continue

        execution_contract = infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        if execution_contract is None:
            _raise_proposal_contract_error(
                source_component="deterministic_fallback.backlog_followup",
                reason_code="execution_contract_unavailable",
                message="Backlog follow-up plan cannot resolve a valid execution contract.",
                details={"plan_index": index, "ticket_key": ticket_key},
            )

        task_name = str(followup_plan.get("task_name") or followup_plan.get("summary") or ticket_key).strip() or ticket_key
        task_scope = [
            str(item).strip()
            for item in list(followup_plan.get("scope") or [])
            if str(item).strip()
        ]
        scope_suffix = f"；范围：{'、'.join(task_scope)}" if task_scope else ""
        actions.append(
            {
                "action_type": CEOActionType.CREATE_TICKET,
                "payload": {
                    "workflow_id": workflow_id,
                    "node_id": node_id,
                    "role_profile_ref": role_profile_ref,
                    "output_schema_ref": output_schema_ref,
                    "execution_contract": execution_contract,
                    "dispatch_intent": {
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": (
                            "Follow the current capability plan and translate the approved backlog recommendation into an auditable implementation ticket."
                        ),
                        "dependency_gate_refs": dependency_gate_refs,
                    },
                    "summary": f"{ticket_key} {task_name}{scope_suffix}",
                    "parent_ticket_id": backlog_ticket_id,
                },
            }
        )

    if not actions:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.backlog_followup",
            reason_code="no_actions_built",
            message="Controller requested CREATE_TICKET for backlog fanout, but no followup ticket could be built.",
            details={"followup_ticket_plan_count": len(followup_ticket_plans)},
        )

    return CEOActionBatch.model_validate(
        {
            "summary": reason,
            "actions": actions,
        }
    )


def _build_required_governance_ticket_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch | None:
    workflow_id = str((snapshot.get("workflow") or {}).get("workflow_id") or "").strip()
    capability_plan = capability_plan_view(snapshot)
    required_governance_ticket_plan = capability_plan.get("required_governance_ticket_plan")
    if not workflow_id or not isinstance(required_governance_ticket_plan, dict):
        return None

    node_id = str(required_governance_ticket_plan.get("node_id") or "").strip()
    role_profile_ref = str(required_governance_ticket_plan.get("role_profile_ref") or "").strip()
    output_schema_ref = str(required_governance_ticket_plan.get("output_schema_ref") or "").strip()
    assignee_employee_id = str(required_governance_ticket_plan.get("assignee_employee_id") or "").strip()
    parent_ticket_id = str(required_governance_ticket_plan.get("parent_ticket_id") or "").strip() or None
    summary = str(required_governance_ticket_plan.get("summary") or "").strip()
    selection_reason = str(required_governance_ticket_plan.get("selection_reason") or "").strip()
    missing_fields = [
        field_name
        for field_name, field_value in (
            ("node_id", node_id),
            ("role_profile_ref", role_profile_ref),
            ("output_schema_ref", output_schema_ref),
            ("assignee_employee_id", assignee_employee_id),
            ("summary", summary),
            ("selection_reason", selection_reason),
        )
        if not field_value
    ]
    if missing_fields:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.required_governance",
            reason_code="plan_missing_fields",
            message="Required governance ticket plan is missing required fields.",
            details={"missing_fields": missing_fields},
        )

    with repository.connection() as connection:
        node_view = resolve_runtime_node_lifecycle(
            repository,
            workflow_id,
            node_id,
            connection=connection,
        )
    if node_view.materialization_state == MATERIALIZATION_STATE_MATERIALIZED:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.required_governance",
            reason_code="node_already_materialized",
            message="Required governance node already exists, but controller still requested CREATE_TICKET.",
            details={"workflow_id": workflow_id, "node_id": node_id},
        )

    execution_contract = infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if execution_contract is None:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.required_governance",
            reason_code="execution_contract_unavailable",
            message="Required governance ticket plan cannot resolve a valid execution contract.",
            details={"workflow_id": workflow_id, "node_id": node_id},
        )

    return CEOActionBatch.model_validate(
        {
            "summary": reason,
            "actions": [
                {
                    "action_type": CEOActionType.CREATE_TICKET,
                    "payload": {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                        "role_profile_ref": role_profile_ref,
                        "output_schema_ref": output_schema_ref,
                        "execution_contract": execution_contract,
                        "dispatch_intent": {
                            "assignee_employee_id": assignee_employee_id,
                            "selection_reason": selection_reason,
                            "dependency_gate_refs": list(
                                required_governance_ticket_plan.get("dependency_gate_refs") or []
                            ),
                        },
                        "summary": summary,
                        "parent_ticket_id": parent_ticket_id,
                    },
                }
            ],
        }
    )


def _build_capability_hire_batch(snapshot: dict, reason: str) -> CEOActionBatch | None:
    workflow_id = str((snapshot.get("workflow") or {}).get("workflow_id") or "").strip()
    capability_plan = capability_plan_view(snapshot)
    recommended_hire = capability_plan.get("recommended_hire")
    if not workflow_id:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.capability_hire",
            reason_code="workflow_id_missing",
            message="Capability hire fallback requires workflow.workflow_id.",
        )
    if not isinstance(recommended_hire, dict):
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.capability_hire",
            reason_code="recommended_hire_missing",
            message="Controller requested HIRE_EMPLOYEE, but capability_plan.recommended_hire is missing.",
        )
    role_type = str(recommended_hire.get("role_type") or "").strip()
    role_profile_refs = [
        str(item).strip()
        for item in list(recommended_hire.get("role_profile_refs") or [])
        if str(item).strip()
    ]
    request_summary = str(recommended_hire.get("request_summary") or "").strip() or (
        f"Hire {role_type} so the current capability plan can continue."
    )
    missing_fields = []
    if not role_type:
        missing_fields.append("role_type")
    if not role_profile_refs:
        missing_fields.append("role_profile_refs")
    if missing_fields:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.capability_hire",
            reason_code="recommended_hire_incomplete",
            message="recommended_hire is incomplete.",
            details={"missing_fields": missing_fields},
        )
    return CEOActionBatch(
        summary=reason,
        actions=[
            {
                "action_type": CEOActionType.HIRE_EMPLOYEE,
                "payload": {
                    "workflow_id": workflow_id,
                    "role_type": role_type,
                    "role_profile_refs": role_profile_refs,
                    "request_summary": request_summary,
                },
            }
        ],
    )


def _resolve_autopilot_closeout_parent_ticket_id(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> str | None:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ? AND status = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id, "COMPLETED"),
    ).fetchall()
    created_specs_by_ticket = {
        str(row["ticket_id"]): repository.get_latest_ticket_created_payload(connection, str(row["ticket_id"])) or {}
        for row in rows
    }
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = created_specs_by_ticket[ticket_id]
        if not ticket_has_delivery_mainline_evidence(created_spec, created_specs_by_ticket):
            continue
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref == "maker_checker_verdict":
            maker_checker_context = created_spec.get("maker_checker_context") or {}
            maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
            if maker_ticket_id:
                return maker_ticket_id
        return ticket_id
    return None


def _workflow_has_existing_closeout_ticket(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> bool:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id,),
    ).fetchall()
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "").strip() == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
            return True
    return False


def _build_autopilot_closeout_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch | None:
    workflow = snapshot.get("workflow") or {}
    if not workflow_uses_ceo_board_delegate(workflow):
        return None
    if snapshot.get("approvals") or snapshot.get("incidents"):
        return None

    ticket_summary = snapshot.get("ticket_summary") or {}
    if int(ticket_summary.get("active_count") or 0) > 0:
        return None

    nodes = list(snapshot.get("nodes") or [])
    if not nodes or any(str(node.get("status") or "") != "COMPLETED" for node in nodes):
        return None

    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if not workflow_id:
        return None

    closeout_node_id = "node_ceo_delivery_closeout"
    closeout_role_profile_ref = "frontend_engineer_primary"
    assignee_employee_id = _select_default_assignee(
        snapshot,
        role_profile_ref=closeout_role_profile_ref,
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    )
    if assignee_employee_id is None:
        return None

    with repository.connection() as connection:
        if _workflow_has_existing_closeout_ticket(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        ):
            return None
        parent_ticket_id = _resolve_autopilot_closeout_parent_ticket_id(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
    if parent_ticket_id is None:
        return None

    goal = str(workflow.get("north_star_goal") or workflow.get("title") or "the current workflow").strip()
    summary = f"Prepare the final delivery closeout package for {goal}."
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEOCreateTicketAction(
                action_type=CEOActionType.CREATE_TICKET,
                payload=CEOCreateTicketPayload(
                    workflow_id=workflow_id,
                    node_id=closeout_node_id,
                    role_profile_ref=closeout_role_profile_ref,
                    output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
                    execution_contract=infer_execution_contract_payload(
                        role_profile_ref=closeout_role_profile_ref,
                        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
                    ),
                    dispatch_intent={
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": "Collect final delivery evidence and handoff notes into one auditable closeout package.",
                    },
                    summary=summary,
                    parent_ticket_id=parent_ticket_id,
                ),
            )
        ],
    )


def build_deterministic_fallback_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch:
    controller_state = controller_state_view(snapshot)
    recommended_action = str(controller_state.get("recommended_action") or "").strip()
    capability_plan = capability_plan_view(snapshot)
    closeout_batch = _build_autopilot_closeout_batch(repository, snapshot, reason)
    if closeout_batch is not None:
        return closeout_batch
    if recommended_action == "HIRE_EMPLOYEE":
        return _build_capability_hire_batch(snapshot, reason)
    if recommended_action == "REQUEST_MEETING":
        eligible_meeting_candidates = _eligible_meeting_candidates(snapshot)
        if len(eligible_meeting_candidates) != 1:
            _raise_proposal_contract_error(
                source_component="deterministic_fallback.request_meeting",
                reason_code="eligible_candidate_missing",
                message="Controller requested REQUEST_MEETING, but there is not exactly one eligible meeting candidate.",
                details={"eligible_candidate_count": len(eligible_meeting_candidates)},
            )
        candidate = {
            **eligible_meeting_candidates[0],
            "workflow_id": str((snapshot.get("workflow") or {}).get("workflow_id") or ""),
        }
        return _build_request_meeting_batch(
            candidate,
            reason=(
                "Open one bounded technical decision meeting because the controller state requires it before implementation fanout."
            ),
        )
    if recommended_action == "CREATE_TICKET":
        if isinstance(capability_plan.get("required_governance_ticket_plan"), dict):
            required_governance_ticket_batch = _build_required_governance_ticket_batch(
                repository,
                snapshot,
                reason,
            )
            if required_governance_ticket_batch is not None:
                return required_governance_ticket_batch
        followup_ticket_plans = list(capability_plan.get("followup_ticket_plans") or [])
        if followup_ticket_plans:
            backlog_followup_batch = _build_backlog_followup_batch(repository, snapshot, reason)
            if backlog_followup_batch is not None:
                return backlog_followup_batch
        if _should_fallback_to_project_init_kickoff(snapshot):
            return _build_project_init_kickoff_batch(snapshot, reason)
        _raise_proposal_contract_error(
            source_component="deterministic_fallback",
            reason_code="create_ticket_route_missing",
            message="Controller requested CREATE_TICKET, but no deterministic create-ticket route was available.",
            details={"controller_state": controller_state},
        )
    if _should_fallback_to_project_init_kickoff(snapshot):
        return _build_project_init_kickoff_batch(snapshot, reason)
    if recommended_action == "NO_ACTION":
        return build_no_action_batch(reason)
    _raise_proposal_contract_error(
        source_component="deterministic_fallback",
        reason_code="unsupported_recommended_action",
        message="Controller recommended_action is unsupported on the deterministic CEO path.",
        details={"recommended_action": recommended_action, "controller_state": controller_state},
    )


def propose_ceo_action_batch(
    repository: ControlPlaneRepository,
    *,
    snapshot: dict,
    runtime_provider_store: RuntimeProviderConfigStore | None = None,
) -> CEOProposalResult:
    config = resolve_runtime_provider_config(runtime_provider_store)
    effective_mode, effective_reason = runtime_provider_effective_mode(config, repository)
    provider_health_summary = runtime_provider_health_summary(config, repository)
    selection = resolve_provider_selection(config, target_ref=ROLE_BINDING_CEO_SHADOW, employee_provider_id=None)
    if selection is None:
        action_batch = build_deterministic_fallback_batch(repository, snapshot, effective_reason)
        _maybe_raise_mainline_deterministic_fallback_blocked(
            snapshot=snapshot,
            action_batch=action_batch,
            fallback_reason=effective_reason,
            effective_mode=effective_mode,
        )
        return CEOProposalResult(
            action_batch=action_batch,
            effective_mode=effective_mode,
            provider_health_summary=provider_health_summary,
            model=(find_provider_entry(config, config.default_provider_id).model if find_provider_entry(config, config.default_provider_id) is not None else None),
            fallback_reason=effective_reason,
        )
    provider_mode, provider_reason = provider_effective_mode(selection.provider, repository)
    if not provider_mode.endswith("_LIVE"):
        action_batch = build_deterministic_fallback_batch(repository, snapshot, provider_reason)
        _maybe_raise_mainline_deterministic_fallback_blocked(
            snapshot=snapshot,
            action_batch=action_batch,
            fallback_reason=provider_reason,
            effective_mode=provider_mode,
        )
        return CEOProposalResult(
            action_batch=action_batch,
            effective_mode=provider_mode,
            provider_health_summary=provider_health_summary,
            model=selection.actual_model or selection.provider.model,
            preferred_provider_id=selection.preferred_provider_id,
            preferred_model=selection.preferred_model,
            actual_provider_id=selection.provider.provider_id,
            actual_model=selection.actual_model or selection.provider.model,
            selection_reason=selection.selection_reason,
            policy_reason=selection.policy_reason,
            fallback_reason=provider_reason,
        )

    def _invoke_selection(current_selection):
        rendered_payload = build_ceo_shadow_rendered_payload(snapshot)
        provider_result = (
            invoke_openai_compat_response(
                OpenAICompatProviderConfig(
                    base_url=str(current_selection.provider.base_url or ""),
                    api_key=str(current_selection.provider.api_key or ""),
                    model=str(current_selection.actual_model or current_selection.provider.model or ""),
                    timeout_sec=current_selection.provider.timeout_sec,
                    reasoning_effort=current_selection.effective_reasoning_effort,
                ),
                rendered_payload,
            )
            if current_selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT
            else invoke_claude_code_response(
                ClaudeCodeProviderConfig(
                    command_path=str(current_selection.provider.command_path or ""),
                    model=str(current_selection.actual_model or current_selection.provider.model or ""),
                    timeout_sec=current_selection.provider.timeout_sec,
                ),
                rendered_payload,
            )
        )
        raw_payload = (
            load_openai_compat_result_payload(provider_result)
            if current_selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT
            else json.loads(provider_result.output_text)
        )
        payload = _normalize_provider_action_batch_payload(raw_payload)
        return CEOActionBatch.model_validate(payload), provider_result

    try:
        action_batch, provider_result = _invoke_selection(selection)
        return CEOProposalResult(
            action_batch=action_batch,
            effective_mode=provider_mode,
            provider_health_summary=provider_health_summary,
            model=selection.actual_model or selection.provider.model,
            preferred_provider_id=selection.preferred_provider_id,
            preferred_model=selection.preferred_model,
            actual_provider_id=selection.provider.provider_id,
            actual_model=selection.actual_model or selection.provider.model,
            selection_reason=selection.selection_reason,
            policy_reason=selection.policy_reason,
            provider_response_id=provider_result.response_id,
        )
    except (OpenAICompatProviderError, ClaudeCodeProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
        terminal_exception: Exception = exc
        failure_kind = (
            exc.failure_kind if isinstance(exc, (OpenAICompatProviderError, ClaudeCodeProviderError)) else None
        )
        if failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
            for failover_selection in resolve_provider_failover_selections(
                config,
                repository,
                target_ref=ROLE_BINDING_CEO_SHADOW,
                primary_selection=selection,
            ):
                failover_mode, _ = provider_effective_mode(failover_selection.provider, repository)
                try:
                    action_batch, provider_result = _invoke_selection(failover_selection)
                    return CEOProposalResult(
                        action_batch=action_batch,
                        effective_mode=failover_mode,
                        provider_health_summary=provider_health_summary,
                        model=failover_selection.actual_model or failover_selection.provider.model,
                        preferred_provider_id=failover_selection.preferred_provider_id,
                        preferred_model=failover_selection.preferred_model,
                        actual_provider_id=failover_selection.provider.provider_id,
                        actual_model=failover_selection.actual_model or failover_selection.provider.model,
                        selection_reason=failover_selection.selection_reason,
                        policy_reason=failover_selection.policy_reason,
                        provider_response_id=provider_result.response_id,
                    )
                except (OpenAICompatProviderError, ClaudeCodeProviderError, ValueError, TypeError, json.JSONDecodeError) as failover_exc:
                    terminal_exception = failover_exc
                    failover_failure_kind = (
                        failover_exc.failure_kind
                        if isinstance(failover_exc, (OpenAICompatProviderError, ClaudeCodeProviderError))
                        else None
                    )
                    if failover_failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
                        continue
                    break
        raise terminal_exception
