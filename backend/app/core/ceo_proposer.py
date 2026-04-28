from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
    CEOCreateTicketAction,
    CEOCreateTicketPayload,
    CEORequestMeetingAction,
    CEORequestMeetingPayload,
    CEORetryTicketAction,
    CEORetryTicketPayload,
    CEONoAction,
    CEONoActionPayload,
    CEOHireEmployeePayload,
    CEOEscalateToBoardPayload,
)
from app.contracts.commands import IncidentFollowupAction
from app.core.ceo_prompts import build_ceo_shadow_rendered_payload
from app.core.ceo_snapshot_contracts import (
    capability_plan_view,
    controller_state_view,
    replan_focus_view,
)
from app.core.constants import (
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
)
from app.core.execution_targets import (
    employee_supports_execution_contract,
    infer_execution_contract_payload,
)
from app.core.staffing_catalog import (
    STAFFING_CAP_REACHED_REASON_CODE,
    build_staffing_capacity_details,
    count_active_board_approved_staffing_matches,
    resolve_limited_ceo_staffing_combo,
)
from app.core.provider_openai_compat import (
    OpenAICompatProviderConfig,
    OpenAICompatProviderError,
    invoke_openai_compat_response,
    resolve_openai_compat_result_payload,
)
from app.core.provider_claude_code import ClaudeCodeProviderConfig, ClaudeCodeProviderError, invoke_claude_code_response
from app.core.output_schemas import (
    CEO_ACTION_BATCH_SCHEMA_REF,
    CEO_ACTION_BATCH_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    OUTPUT_SCHEMA_REGISTRY,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.core.runtime_node_views import (
    MATERIALIZATION_STATE_MATERIALIZED,
)
from app.core.runtime_node_lifecycle import (
    resolve_runtime_node_lifecycle,
)
from app.core.workflow_completion import (
    evaluate_workflow_closeout_gate_issue,
    ticket_has_delivery_mainline_evidence,
    ticket_lineage_ticket_ids,
)
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


@dataclass(frozen=True)
class _CompletedTicketGateResult:
    satisfies: bool
    reason_code: str | None = None
    details: dict[str, Any] | None = None


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
    trigger = snapshot.get("trigger") or {}
    if str(trigger.get("trigger_type") or "").strip() == EVENT_BOARD_DIRECTIVE_RECEIVED:
        return
    blocked_action_types = _mainline_deterministic_mutating_actions(action_batch)
    if not blocked_action_types:
        return
    if (
        str(trigger.get("trigger_type") or "").strip() == "SCHEDULER_IDLE_MAINTENANCE"
        and set(blocked_action_types) == {CEOActionType.HIRE_EMPLOYEE.value}
        and str(controller_state_view(snapshot).get("state") or "").strip()
        in {"ARCHITECT_REQUIRED", "STAFFING_REQUIRED"}
    ):
        return
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
        if role_profile_ref not in set(employee.get("role_profile_refs") or []):
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


def _payload_model_for_action_type(action_type: str):
    return {
        CEOActionType.CREATE_TICKET.value: CEOCreateTicketPayload,
        CEOActionType.RETRY_TICKET.value: CEORetryTicketPayload,
        CEOActionType.HIRE_EMPLOYEE.value: CEOHireEmployeePayload,
        CEOActionType.REQUEST_MEETING.value: CEORequestMeetingPayload,
        CEOActionType.ESCALATE_TO_BOARD.value: CEOEscalateToBoardPayload,
        CEOActionType.NO_ACTION.value: CEONoActionPayload,
    }.get(action_type)


def _validate_provider_action_payload(
    *,
    action_type: str,
    action_payload: dict[str, Any],
    action_index: int,
) -> dict[str, Any]:
    payload_model = _payload_model_for_action_type(action_type)
    if payload_model is None:
        _raise_proposal_contract_error(
            source_component="provider_action_batch",
            reason_code="unsupported_action_type",
            message=f"{action_type} is not supported on the CEO shadow path.",
            details={"action_index": action_index, "action_type": action_type},
        )
    try:
        return payload_model.model_validate(action_payload).model_dump(mode="json")
    except ValidationError as exc:
        _raise_proposal_contract_error(
            source_component="provider_action_batch",
            reason_code="payload_validation_failed",
            message=f"{action_type} payload does not match the required CEO shadow contract.",
            details={
                "action_index": action_index,
                "action_type": action_type,
                "errors": exc.errors(include_url=False),
            },
        )


def _resolve_followup_ticket_payload(
    *,
    followup_plan: dict[str, Any],
    plan_index: int,
) -> dict[str, Any]:
    ticket_payload = followup_plan.get("ticket_payload")
    if not isinstance(ticket_payload, dict):
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.backlog_followup",
            reason_code="plan_missing_fields",
            message="Backlog follow-up plan is missing ticket_payload.",
            details={"plan_index": plan_index, "missing_fields": ["ticket_payload"]},
        )
    try:
        return CEOCreateTicketPayload.model_validate(ticket_payload).model_dump(mode="json")
    except ValidationError as exc:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.backlog_followup",
            reason_code="plan_missing_fields",
            message="Backlog follow-up plan ticket_payload does not match the canonical CREATE_TICKET contract.",
            details={"plan_index": plan_index, "errors": exc.errors(include_url=False)},
        )


def _resolve_required_governance_ticket_payload(required_governance_ticket_plan: dict[str, Any]) -> dict[str, Any]:
    ticket_payload = required_governance_ticket_plan.get("ticket_payload")
    if not isinstance(ticket_payload, dict):
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.required_governance",
            reason_code="plan_missing_fields",
            message="Required governance ticket plan is missing ticket_payload.",
            details={"missing_fields": ["ticket_payload"]},
        )
    try:
        return CEOCreateTicketPayload.model_validate(ticket_payload).model_dump(mode="json")
    except ValidationError as exc:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.required_governance",
            reason_code="plan_missing_fields",
            message="Required governance ticket plan ticket_payload does not match the canonical CREATE_TICKET contract.",
            details={"errors": exc.errors(include_url=False)},
        )


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
                "payload": _validate_provider_action_payload(
                    action_type=action_type,
                    action_payload=action_payload,
                    action_index=index,
                ),
            }
        )
    return {
        "summary": str(raw_payload.get("summary") or "CEO shadow action batch").strip() or "CEO shadow action batch",
        "actions": normalized_actions,
    }


def _backlog_followup_key_to_node_id(ticket_key: str) -> str:
    return controller_backlog_followup_key_to_node_id(ticket_key)


def _backlog_retry_budget(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(created_spec.get("retry_budget") or current_ticket.get("retry_budget") or 0)


def _backlog_retry_count(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(current_ticket.get("retry_count") or created_spec.get("retry_count") or 0)


def _recommended_backlog_followup_action(
    *,
    ticket_status: str,
    terminal_event_type: str | None,
) -> str | None:
    normalized_terminal_event_type = str(terminal_event_type or "").strip()
    if normalized_terminal_event_type == EVENT_TICKET_TIMED_OUT or ticket_status == "TIMED_OUT":
        return IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value
    if normalized_terminal_event_type == EVENT_TICKET_FAILED or ticket_status == "FAILED":
        return IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value
    return None


def _can_retry_existing_backlog_followup_ticket(
    *,
    current_ticket: dict[str, Any],
    created_spec: dict[str, Any],
    latest_terminal_event: dict[str, Any],
) -> bool:
    retry_budget = _backlog_retry_budget(current_ticket, created_spec)
    retry_count = _backlog_retry_count(current_ticket, created_spec)
    if retry_count >= retry_budget:
        return False

    terminal_event_type = str(latest_terminal_event.get("event_type") or "").strip()
    escalation_policy = created_spec.get("escalation_policy") or {}
    if terminal_event_type == EVENT_TICKET_TIMED_OUT:
        return escalation_policy.get("on_timeout") == "retry"
    if terminal_event_type == EVENT_TICKET_FAILED:
        failure_kind = str(
            latest_terminal_event.get("payload", {}).get("failure_kind")
            or current_ticket.get("last_failure_kind")
            or ""
        ).strip()
        if failure_kind == "SCHEMA_ERROR":
            return escalation_policy.get("on_schema_error") == "retry"
        return True
    return False


def _build_existing_backlog_followup_retry_action(
    repository: ControlPlaneRepository,
    *,
    connection,
    workflow_id: str,
    node_id: str,
    ticket_key: str,
    existing_ticket_id: str,
    completed_ticket_gate_rejection: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    current_ticket = repository.get_current_ticket_projection(existing_ticket_id, connection=connection)
    if current_ticket is None:
        return None
    if (
        str(current_ticket.get("workflow_id") or "").strip() != workflow_id
        or str(current_ticket.get("node_id") or "").strip() != node_id
    ):
        return None

    source_ticket_status = str(current_ticket.get("status") or "").strip()
    if source_ticket_status not in {"FAILED", "TIMED_OUT"}:
        return None

    created_spec = repository.get_latest_ticket_created_payload(connection, existing_ticket_id)
    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, existing_ticket_id)
    terminal_event_type = str((latest_terminal_event or {}).get("event_type") or "").strip() or None
    recommended_followup_action = _recommended_backlog_followup_action(
        ticket_status=source_ticket_status,
        terminal_event_type=terminal_event_type,
    )
    failure_kind = str(
        ((latest_terminal_event or {}).get("payload") or {}).get("failure_kind")
        or current_ticket.get("last_failure_kind")
        or ""
    ).strip() or None

    if (
        created_spec is not None
        and latest_terminal_event is not None
        and _can_retry_existing_backlog_followup_ticket(
            current_ticket=current_ticket,
            created_spec=created_spec,
            latest_terminal_event=latest_terminal_event,
        )
    ):
        return CEORetryTicketAction(
            action_type=CEOActionType.RETRY_TICKET,
            payload=CEORetryTicketPayload(
                workflow_id=workflow_id,
                ticket_id=existing_ticket_id,
                node_id=node_id,
                reason=(
                    "Continue approved backlog follow-up by retrying the existing ticket instead of creating a parallel ticket."
                ),
            ),
        ).model_dump(mode="json")

    if recommended_followup_action is not None:
        error_details: dict[str, Any] = {
            "source_ticket_id": existing_ticket_id,
            "node_id": node_id,
            "ticket_key": ticket_key,
            "source_ticket_status": source_ticket_status,
            "failure_kind": failure_kind,
            "recommended_followup_action": recommended_followup_action,
        }
        if completed_ticket_gate_rejection is not None:
            error_details["completed_ticket_gate_rejection"] = dict(completed_ticket_gate_rejection)
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.backlog_followup",
            reason_code="restore_needed",
            message="Existing backlog follow-up ticket needs restore/retry recovery instead of a new fallback ticket.",
            details=error_details,
        )

    return None


def _latest_completed_ticket_id_for_node(
    connection,
    *,
    workflow_id: str,
    node_id: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ?
          AND node_id = ?
          AND status = 'COMPLETED'
        ORDER BY updated_at DESC, ticket_id DESC
        LIMIT 1
        """,
        (workflow_id, node_id),
    ).fetchone()
    return None if row is None else str(row["ticket_id"])


def _completed_ticket_gate_failure(
    *,
    reason_code: str,
    completed_ticket_id: str,
    terminal_failed_ticket_id: str,
    node_id: str,
    **extra_details: Any,
) -> _CompletedTicketGateResult:
    details = {
        "completed_ticket_id": completed_ticket_id,
        "terminal_failed_ticket_id": terminal_failed_ticket_id,
        "node_id": node_id,
        "reason_code": reason_code,
    }
    details.update(extra_details)
    return _CompletedTicketGateResult(
        satisfies=False,
        reason_code=reason_code,
        details=details,
    )


def _terminal_payload_delivery_evidence_refs(payload: dict[str, Any]) -> list[str]:
    refs = _normalize_dependency_gate_refs(payload.get("artifact_refs"))
    for ref in _normalize_dependency_gate_refs(payload.get("verification_evidence_refs")):
        if ref not in refs:
            refs.append(ref)
    for written_artifact in list(payload.get("written_artifacts") or []):
        if not isinstance(written_artifact, dict):
            continue
        artifact_ref = str(written_artifact.get("artifact_ref") or "").strip()
        if artifact_ref and artifact_ref not in refs:
            refs.append(artifact_ref)
    return refs


def _inactive_materialized_artifact_refs(connection, artifact_refs: list[str]) -> list[str]:
    if not artifact_refs:
        return []
    placeholders = ", ".join("?" for _ in artifact_refs)
    rows = connection.execute(
        f"""
        SELECT artifact_ref, lifecycle_status, materialization_status
        FROM artifact_index
        WHERE artifact_ref IN ({placeholders})
        """,
        tuple(artifact_refs),
    ).fetchall()
    invalid_refs: list[str] = []
    for row in rows:
        if str(row["lifecycle_status"] or "") != "ACTIVE" or str(row["materialization_status"] or "") != "MATERIALIZED":
            invalid_refs.append(str(row["artifact_ref"]))
    return invalid_refs


def _created_specs_for_ticket_lineage(
    repository: ControlPlaneRepository,
    connection,
    ticket_id: str,
) -> dict[str, dict[str, Any]]:
    created_specs_by_ticket: dict[str, dict[str, Any]] = {}
    current_ticket_id = str(ticket_id or "").strip()
    seen_ticket_ids: set[str] = set()
    while current_ticket_id and current_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(current_ticket_id)
        created_spec = repository.get_latest_ticket_created_payload(connection, current_ticket_id)
        if not isinstance(created_spec, dict):
            break
        created_specs_by_ticket[current_ticket_id] = created_spec
        current_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
    return created_specs_by_ticket


def _ticket_payload_explicitly_supersedes_completed_ticket(
    payload: dict[str, Any],
    completed_ticket_id: str,
) -> bool:
    scalar_fields = {
        "replaces_ticket_id",
        "replacement_of_ticket_id",
        "supersedes_ticket_id",
        "superseded_ticket_id",
        "invalidates_ticket_id",
    }
    list_fields = {
        "replaces_ticket_ids",
        "replacement_of_ticket_ids",
        "supersedes_ticket_ids",
        "superseded_ticket_ids",
        "invalidates_ticket_ids",
        "invalidated_ticket_ids",
    }
    for field_name in scalar_fields:
        if str(payload.get(field_name) or "").strip() == completed_ticket_id:
            return True
    for field_name in list_fields:
        if completed_ticket_id in _normalize_dependency_gate_refs(payload.get(field_name)):
            return True
    for replacement in list(payload.get("replacements") or []):
        if not isinstance(replacement, dict):
            continue
        old_ticket_id = str(
            replacement.get("old_ticket_id")
            or replacement.get("source_ticket_id")
            or replacement.get("replaced_ticket_id")
            or replacement.get("superseded_ticket_id")
            or ""
        ).strip()
        if old_ticket_id == completed_ticket_id:
            return True
    return False


def _graph_patch_supersedes_completed_ticket(
    connection,
    *,
    workflow_id: str,
    completed_created_spec: dict[str, Any],
    failed_created_spec: dict[str, Any],
) -> bool:
    completed_node_id = str(completed_created_spec.get("node_id") or "").strip()
    failed_node_id = str(failed_created_spec.get("node_id") or "").strip()
    if not completed_node_id or not failed_node_id or completed_node_id == failed_node_id:
        return False
    rows = connection.execute(
        """
        SELECT payload_json
        FROM events
        WHERE workflow_id = ?
          AND event_type = ?
        ORDER BY sequence_no ASC
        """,
        (workflow_id, EVENT_GRAPH_PATCH_APPLIED),
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            continue
        for replacement in list(payload.get("replacements") or []):
            if not isinstance(replacement, dict):
                continue
            if (
                str(replacement.get("old_node_id") or "").strip() == completed_node_id
                and str(replacement.get("new_node_id") or "").strip() == failed_node_id
            ):
                return True
    return False


def _evaluate_completed_ticket_followup_dependency_gate(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    node_id: str,
    completed_ticket_id: str,
    planned_output_schema_ref: str,
    terminal_failed_ticket_id: str,
) -> _CompletedTicketGateResult:
    normalized_workflow_id = str(workflow_id or "").strip()
    normalized_node_id = str(node_id or "").strip()
    normalized_completed_ticket_id = str(completed_ticket_id or "").strip()
    normalized_failed_ticket_id = str(terminal_failed_ticket_id or "").strip()
    completed_ticket = repository.get_current_ticket_projection(normalized_completed_ticket_id, connection=connection)
    if completed_ticket is None:
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_missing",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
        )
    if str(completed_ticket.get("status") or "").strip() != "COMPLETED":
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_not_completed",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
            completed_ticket_status=str(completed_ticket.get("status") or "").strip(),
        )
    if str(completed_ticket.get("workflow_id") or "").strip() != normalized_workflow_id:
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_workflow_mismatch",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
            completed_ticket_workflow_id=str(completed_ticket.get("workflow_id") or "").strip(),
        )
    if str(completed_ticket.get("node_id") or "").strip() != normalized_node_id:
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_node_mismatch",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
            completed_ticket_node_id=str(completed_ticket.get("node_id") or "").strip(),
        )

    completed_created_spec = repository.get_latest_ticket_created_payload(connection, normalized_completed_ticket_id)
    if not isinstance(completed_created_spec, dict):
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_created_spec_missing",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
        )
    completed_output_schema_ref = str(completed_created_spec.get("output_schema_ref") or "").strip()
    if completed_output_schema_ref != str(planned_output_schema_ref or "").strip():
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_schema_mismatch",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
            completed_output_schema_ref=completed_output_schema_ref,
            planned_output_schema_ref=str(planned_output_schema_ref or "").strip(),
        )

    terminal_event = repository.get_latest_ticket_terminal_event(connection, normalized_completed_ticket_id)
    if not isinstance(terminal_event, dict) or str(terminal_event.get("event_type") or "").strip() != EVENT_TICKET_COMPLETED:
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_missing_terminal_event",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
        )
    terminal_payload = terminal_event.get("payload") or {}
    if not isinstance(terminal_payload, dict):
        terminal_payload = {}
    evidence_refs = _terminal_payload_delivery_evidence_refs(terminal_payload)
    if not evidence_refs:
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_missing_delivery_evidence",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
        )
    invalid_artifact_refs = _inactive_materialized_artifact_refs(connection, evidence_refs)
    if invalid_artifact_refs:
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_artifact_invalid",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
            invalid_artifact_refs=invalid_artifact_refs,
        )

    failed_created_spec = repository.get_latest_ticket_created_payload(connection, normalized_failed_ticket_id)
    failed_created_spec = failed_created_spec if isinstance(failed_created_spec, dict) else {}
    if failed_created_spec:
        lineage_specs = _created_specs_for_ticket_lineage(repository, connection, normalized_failed_ticket_id)
        failed_lineage_ticket_ids = ticket_lineage_ticket_ids(normalized_failed_ticket_id, lineage_specs)
        if normalized_completed_ticket_id in failed_lineage_ticket_ids[1:]:
            return _completed_ticket_gate_failure(
                reason_code="completed_ticket_lineage_invalidated",
                completed_ticket_id=normalized_completed_ticket_id,
                terminal_failed_ticket_id=normalized_failed_ticket_id,
                node_id=normalized_node_id,
            )
        if _ticket_payload_explicitly_supersedes_completed_ticket(failed_created_spec, normalized_completed_ticket_id):
            return _completed_ticket_gate_failure(
                reason_code="completed_ticket_superseded",
                completed_ticket_id=normalized_completed_ticket_id,
                terminal_failed_ticket_id=normalized_failed_ticket_id,
                node_id=normalized_node_id,
            )
        if _graph_patch_supersedes_completed_ticket(
            connection,
            workflow_id=normalized_workflow_id,
            completed_created_spec=completed_created_spec,
            failed_created_spec=failed_created_spec,
        ):
            return _completed_ticket_gate_failure(
                reason_code="completed_ticket_superseded",
                completed_ticket_id=normalized_completed_ticket_id,
                terminal_failed_ticket_id=normalized_failed_ticket_id,
                node_id=normalized_node_id,
            )
    failed_terminal_event = repository.get_latest_ticket_terminal_event(connection, normalized_failed_ticket_id)
    failed_terminal_payload = (failed_terminal_event or {}).get("payload") if isinstance(failed_terminal_event, dict) else {}
    if isinstance(failed_terminal_payload, dict) and _ticket_payload_explicitly_supersedes_completed_ticket(
        failed_terminal_payload,
        normalized_completed_ticket_id,
    ):
        return _completed_ticket_gate_failure(
            reason_code="completed_ticket_superseded",
            completed_ticket_id=normalized_completed_ticket_id,
            terminal_failed_ticket_id=normalized_failed_ticket_id,
            node_id=normalized_node_id,
        )

    return _CompletedTicketGateResult(satisfies=True)


def _completed_ticket_satisfies_followup_dependency_gate(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    node_id: str,
    completed_ticket_id: str,
    planned_output_schema_ref: str,
    terminal_failed_ticket_id: str,
) -> bool:
    return _evaluate_completed_ticket_followup_dependency_gate(
        repository,
        connection,
        workflow_id=workflow_id,
        node_id=node_id,
        completed_ticket_id=completed_ticket_id,
        planned_output_schema_ref=planned_output_schema_ref,
        terminal_failed_ticket_id=terminal_failed_ticket_id,
    ).satisfies


def _prefer_completed_ticket_when_existing_terminal_failed(
    repository: ControlPlaneRepository,
    *,
    connection,
    workflow_id: str,
    existing_ticket_ids_by_node_id: dict[str, str],
    planned_output_schema_refs_by_node_id: dict[str, str],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    resolved: dict[str, str] = {}
    completed_ticket_rejection_details_by_node_id: dict[str, dict[str, Any]] = {}
    for node_id, existing_ticket_id in existing_ticket_ids_by_node_id.items():
        current_ticket = repository.get_current_ticket_projection(existing_ticket_id, connection=connection)
        if current_ticket is None:
            resolved[node_id] = existing_ticket_id
            continue
        if str(current_ticket.get("status") or "").strip() not in {"FAILED", "TIMED_OUT"}:
            resolved[node_id] = existing_ticket_id
            continue
        completed_ticket_id = _latest_completed_ticket_id_for_node(
            connection,
            workflow_id=workflow_id,
            node_id=node_id,
        )
        if not completed_ticket_id:
            resolved[node_id] = existing_ticket_id
            continue
        gate_result = _evaluate_completed_ticket_followup_dependency_gate(
            repository,
            connection,
            workflow_id=workflow_id,
            node_id=node_id,
            completed_ticket_id=completed_ticket_id,
            planned_output_schema_ref=planned_output_schema_refs_by_node_id.get(node_id, ""),
            terminal_failed_ticket_id=existing_ticket_id,
        )
        if gate_result.satisfies:
            resolved[node_id] = completed_ticket_id
        else:
            resolved[node_id] = existing_ticket_id
            if gate_result.details is not None:
                completed_ticket_rejection_details_by_node_id[node_id] = dict(gate_result.details)
    return resolved, completed_ticket_rejection_details_by_node_id




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
    retry_actions: list[dict[str, Any]] = []
    existing_ticket_ids_by_node_id = {
        str(((plan.get("ticket_payload") or {}).get("node_id") or "")).strip(): str(plan.get("existing_ticket_id") or "").strip()
        for plan in followup_ticket_plans
        if str(((plan.get("ticket_payload") or {}).get("node_id") or "")).strip()
        and str(plan.get("existing_ticket_id") or "").strip()
    }
    planned_output_schema_refs_by_node_id = {
        str(((plan.get("ticket_payload") or {}).get("node_id") or "")).strip(): str(
            ((plan.get("ticket_payload") or {}).get("output_schema_ref") or "")
        ).strip()
        for plan in followup_ticket_plans
        if str(((plan.get("ticket_payload") or {}).get("node_id") or "")).strip()
    }
    existing_node_ids = set(existing_ticket_ids_by_node_id)
    planned_ticket_keys = {
        str(plan.get("ticket_key") or "").strip()
        for plan in followup_ticket_plans
        if isinstance(plan, dict) and str(plan.get("ticket_key") or "").strip()
    }

    with repository.connection() as connection:
        (
            existing_ticket_ids_by_node_id,
            completed_ticket_rejection_details_by_node_id,
        ) = _prefer_completed_ticket_when_existing_terminal_failed(
            repository,
            connection=connection,
            workflow_id=workflow_id,
            existing_ticket_ids_by_node_id=existing_ticket_ids_by_node_id,
            planned_output_schema_refs_by_node_id=planned_output_schema_refs_by_node_id,
        )
        for index, followup_plan in enumerate(followup_ticket_plans):
            if not isinstance(followup_plan, dict):
                _raise_proposal_contract_error(
                    source_component="deterministic_fallback.backlog_followup",
                    reason_code="plan_not_object",
                    message="Each followup ticket plan must be a JSON object.",
                    details={"plan_index": index},
                )
            ticket_key = str(followup_plan.get("ticket_key") or "").strip()
            ticket_payload = _resolve_followup_ticket_payload(
                followup_plan=followup_plan,
                plan_index=index,
            )
            node_id = str(ticket_payload.get("node_id") or "").strip()
            missing_fields = [
                field_name
                for field_name, field_value in (
                    ("ticket_key", ticket_key),
                    ("node_id", node_id),
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

            existing_ticket_id = existing_ticket_ids_by_node_id.get(node_id)
            if existing_ticket_id:
                retry_action = _build_existing_backlog_followup_retry_action(
                    repository,
                    connection=connection,
                    workflow_id=workflow_id,
                    node_id=node_id,
                    ticket_key=ticket_key,
                    existing_ticket_id=existing_ticket_id,
                    completed_ticket_gate_rejection=completed_ticket_rejection_details_by_node_id.get(node_id),
                )
                if retry_action is not None:
                    retry_actions.append(retry_action)
                continue
            if node_id in existing_node_ids:
                continue

            dispatch_intent = dict(ticket_payload.get("dispatch_intent") or {})
            dependency_gate_refs = _normalize_dependency_gate_refs(dispatch_intent.get("dependency_gate_refs"))
            ready_to_create = True
            for dependency_key in list(followup_plan.get("blocked_by_plan_keys") or []):
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

            ticket_payload["dispatch_intent"] = {
                **dispatch_intent,
                "dependency_gate_refs": dependency_gate_refs,
            }
            actions.append(
                {
                    "action_type": CEOActionType.CREATE_TICKET,
                    "payload": ticket_payload,
                }
            )

    if retry_actions:
        return CEOActionBatch.model_validate(
            {
                "summary": reason,
                "actions": retry_actions,
            }
        )

    if not actions:
        return None

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

    ticket_payload = _resolve_required_governance_ticket_payload(required_governance_ticket_plan)
    node_id = str(ticket_payload.get("node_id") or "").strip()

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

    return CEOActionBatch.model_validate(
        {
            "summary": reason,
            "actions": [
                {
                    "action_type": CEOActionType.CREATE_TICKET,
                    "payload": ticket_payload,
                }
            ],
        }
    )


def _build_capability_hire_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch | None:
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
    active_board_approved_employees = repository.list_employee_projections(
        states=["ACTIVE"],
        board_approved_only=True,
    )
    template, staffing_reason = resolve_limited_ceo_staffing_combo(role_type, role_profile_refs)
    if staffing_reason is not None or template is None:
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.capability_hire",
            reason_code="STAFFING_TEMPLATE_UNSUPPORTED",
            message=staffing_reason or "Controller requested unsupported HIRE_EMPLOYEE staffing template.",
        )
    active_matching_count = count_active_board_approved_staffing_matches(
        role_type=role_type,
        role_profile_refs=role_profile_refs,
        employees=active_board_approved_employees,
    )
    max_active_count = int(template["max_active_count"])
    if active_matching_count >= max_active_count:
        details = build_staffing_capacity_details(
            reason_code=STAFFING_CAP_REACHED_REASON_CODE,
            role_type=role_type,
            role_profile_refs=role_profile_refs,
            active_matching_count=active_matching_count,
            max_active_count=max_active_count,
            template_id=str(template["template_id"]),
        )
        _raise_proposal_contract_error(
            source_component="deterministic_fallback.capability_hire",
            reason_code=STAFFING_CAP_REACHED_REASON_CODE,
            message=(
                "Controller requested HIRE_EMPLOYEE, but the staffing capacity cap is already reached "
                f"for {role_type}."
            ),
            details=details,
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
    fallback_parent_ticket_id: str | None = None
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = created_specs_by_ticket[ticket_id]
        if not ticket_has_delivery_mainline_evidence(created_spec, created_specs_by_ticket):
            continue
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF:
            maker_checker_context = created_spec.get("maker_checker_context") or {}
            maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
            if maker_ticket_id:
                return maker_ticket_id
        if fallback_parent_ticket_id is None:
            fallback_parent_ticket_id = ticket_id
    return fallback_parent_ticket_id


def _snapshot_followup_ticket_plans(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    replan_focus = snapshot.get("replan_focus")
    if not isinstance(replan_focus, dict):
        return []
    capability_plan = replan_focus.get("capability_plan")
    if not isinstance(capability_plan, dict):
        return []
    followup_ticket_plans = capability_plan.get("followup_ticket_plans")
    if not isinstance(followup_ticket_plans, list):
        return []
    return [plan for plan in followup_ticket_plans if isinstance(plan, dict)]


def _has_incomplete_followup_ticket_plans(
    *,
    snapshot: dict[str, Any],
    workflow_id: str,
    connection,
) -> bool:
    followup_ticket_plans = _snapshot_followup_ticket_plans(snapshot)
    if not followup_ticket_plans:
        return False
    for followup_plan in followup_ticket_plans:
        existing_ticket_id = str(followup_plan.get("existing_ticket_id") or "").strip()
        if not existing_ticket_id:
            return True
        row = connection.execute(
            """
            SELECT status
            FROM ticket_projection
            WHERE workflow_id = ? AND ticket_id = ?
            """,
            (workflow_id, existing_ticket_id),
        ).fetchone()
        if row is None or str(row["status"] or "").strip() != "COMPLETED":
            return True
    return False


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


def _workflow_closeout_gate_issue(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> dict[str, Any] | None:
    rows = connection.execute(
        """
        SELECT *
        FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, ticket_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    tickets = [repository._convert_ticket_projection_row(row) for row in rows]
    created_specs_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
        for ticket in tickets
    }
    ticket_terminal_events_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_terminal_event(connection, str(ticket["ticket_id"]))
        for ticket in tickets
    }
    return evaluate_workflow_closeout_gate_issue(
        tickets=tickets,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )


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
    replan_focus = snapshot.get("replan_focus")
    capability_plan = (
        replan_focus.get("capability_plan")
        if isinstance(replan_focus, dict)
        else {}
    )
    snapshot_closeout_gate_issue = (
        capability_plan.get("closeout_gate_issue")
        if isinstance(capability_plan, dict)
        else None
    )
    if isinstance(snapshot_closeout_gate_issue, dict) and snapshot_closeout_gate_issue:
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
        if _has_incomplete_followup_ticket_plans(
            snapshot=snapshot,
            workflow_id=workflow_id,
            connection=connection,
        ):
            return None
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
        if _workflow_closeout_gate_issue(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        ) is not None:
            return None
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
    if recommended_action == "HIRE_EMPLOYEE":
        return _build_capability_hire_batch(repository, snapshot, reason)
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
            closeout_batch = _build_autopilot_closeout_batch(repository, snapshot, reason)
            if closeout_batch is not None:
                return closeout_batch
            return build_no_action_batch(
                "All currently eligible backlog follow-up plans are already materialized or waiting on graph reduction."
            )
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
    closeout_batch = _build_autopilot_closeout_batch(repository, snapshot, reason)
    if closeout_batch is not None:
        return closeout_batch
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
        schema_entry = OUTPUT_SCHEMA_REGISTRY[(CEO_ACTION_BATCH_SCHEMA_REF, CEO_ACTION_BATCH_SCHEMA_VERSION)]
        if current_selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
            provider_result = invoke_openai_compat_response(
                OpenAICompatProviderConfig(
                    base_url=str(current_selection.provider.base_url or ""),
                    api_key=str(current_selection.provider.api_key or ""),
                    model=str(current_selection.actual_model or current_selection.provider.model or ""),
                    timeout_sec=current_selection.provider.timeout_sec,
                    reasoning_effort=current_selection.effective_reasoning_effort,
                    schema_name=CEO_ACTION_BATCH_SCHEMA_REF,
                    schema_body=schema_entry["body"](),
                    strict=False,
                ),
                rendered_payload,
            )
            raw_payload = resolve_openai_compat_result_payload(
                provider_result,
                payload_resolver=_normalize_provider_action_batch_payload,
            ).payload
        else:
            provider_result = invoke_claude_code_response(
                ClaudeCodeProviderConfig(
                    command_path=str(current_selection.provider.command_path or ""),
                    model=str(current_selection.actual_model or current_selection.provider.model or ""),
                    timeout_sec=current_selection.provider.timeout_sec,
                ),
                rendered_payload,
            )
            raw_payload = json.loads(provider_result.output_text)
        try:
            payload = _normalize_provider_action_batch_payload(raw_payload)
            return CEOActionBatch.model_validate(payload), provider_result
        except CEOProposalContractError as exc:
            exc.details.setdefault("provider_response_id", provider_result.response_id)
            raise

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
