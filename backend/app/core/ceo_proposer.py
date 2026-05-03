from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
    CEOCreateTicketAction,
    CEOCreateTicketPayload,
    CEORequestMeetingAction,
    CEORequestMeetingPayload,
    CEORetryTicketPayload,
    CEONoAction,
    CEONoActionPayload,
    CEOHireEmployeePayload,
    CEOEscalateToBoardPayload,
)
from app.core.ceo_prompts import build_ceo_shadow_rendered_payload
from app.core.ceo_snapshot_contracts import (
    capability_plan_view,
    controller_state_view,
    replan_focus_view,
)
from app.core.constants import (
    EVENT_BOARD_DIRECTIVE_RECEIVED,
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
    OUTPUT_SCHEMA_REGISTRY,
)
from app.core.workflow_progression import (
    build_project_init_kickoff_spec,
)
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
    provider_policy_ref: str | None = None
    provider_attempt_id: str | None = None
    provider_timeout_policy: dict[str, Any] = field(default_factory=dict)
    provider_failure_detail: dict[str, Any] = field(default_factory=dict)


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


def _ceo_provider_policy_ref(selection) -> str:
    model = str(selection.actual_model or selection.provider.model or "unknown-model")
    reasoning = str(selection.effective_reasoning_effort or "unknown-reasoning")
    return (
        f"provider-policy:{selection.provider.provider_id}:"
        f"{model}:{reasoning}:{selection.provider.adapter_kind}"
    )


def _ceo_provider_attempt_id(snapshot: dict[str, Any], selection, attempt_no: int = 1) -> str:
    workflow_id = str((snapshot.get("workflow") or {}).get("workflow_id") or "unknown-workflow")
    trigger_type = str((snapshot.get("trigger") or {}).get("trigger_type") or "unknown-trigger")
    return f"attempt:ceo-shadow:{workflow_id}:{trigger_type}:{selection.provider.provider_id}:{attempt_no}"


def _ceo_provider_timeout_policy(selection) -> dict[str, float | None]:
    provider = selection.provider
    if provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        return {
            "connect_timeout_sec": float(provider.connect_timeout_sec or provider.timeout_sec),
            "write_timeout_sec": float(provider.write_timeout_sec or provider.timeout_sec),
            "first_token_timeout_sec": float(provider.first_token_timeout_sec or provider.timeout_sec),
            "stream_idle_timeout_sec": float(provider.stream_idle_timeout_sec or provider.timeout_sec),
            "request_total_timeout_sec": (
                float(provider.request_total_timeout_sec)
                if provider.request_total_timeout_sec is not None
                else None
            ),
        }
    return {
        "connect_timeout_sec": None,
        "write_timeout_sec": None,
        "first_token_timeout_sec": None,
        "stream_idle_timeout_sec": None,
        "request_total_timeout_sec": float(provider.timeout_sec),
    }


def _ceo_provider_attempt_metadata(snapshot: dict[str, Any], selection) -> dict[str, Any]:
    return {
        "provider_policy_ref": _ceo_provider_policy_ref(selection),
        "provider_attempt_id": _ceo_provider_attempt_id(snapshot, selection),
        "provider_timeout_policy": _ceo_provider_timeout_policy(selection),
    }


def _ceo_openai_compat_config(selection, *, schema_entry: dict[str, Any]) -> OpenAICompatProviderConfig:
    provider = selection.provider
    timeout_policy = _ceo_provider_timeout_policy(selection)
    return OpenAICompatProviderConfig(
        base_url=str(provider.base_url or ""),
        api_key=str(provider.api_key or ""),
        model=str(selection.actual_model or provider.model or ""),
        timeout_sec=float(provider.timeout_sec),
        connect_timeout_sec=timeout_policy["connect_timeout_sec"],
        write_timeout_sec=timeout_policy["write_timeout_sec"],
        first_token_timeout_sec=timeout_policy["first_token_timeout_sec"],
        stream_idle_timeout_sec=timeout_policy["stream_idle_timeout_sec"],
        request_total_timeout_sec=timeout_policy["request_total_timeout_sec"],
        reasoning_effort=selection.effective_reasoning_effort,
        schema_name=CEO_ACTION_BATCH_SCHEMA_REF,
        schema_body=schema_entry["body"](),
        strict=False,
    )


def _attach_provider_failure_metadata(exc: Exception, metadata: dict[str, Any]) -> None:
    if isinstance(exc, OpenAICompatProviderError):
        exc.failure_detail = {
            **dict(exc.failure_detail),
            "attempt_id": metadata["provider_attempt_id"],
            "provider_policy_ref": metadata["provider_policy_ref"],
            "provider_timeout_policy": dict(metadata["provider_timeout_policy"]),
        }
    elif isinstance(exc, ClaudeCodeProviderError):
        exc.failure_detail = {
            **dict(exc.failure_detail),
            "attempt_id": metadata["provider_attempt_id"],
            "provider_policy_ref": metadata["provider_policy_ref"],
            "provider_timeout_policy": dict(metadata["provider_timeout_policy"]),
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



def _progression_policy_create_ticket_proposals(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    proposals = snapshot.get("progression_policy_proposals")
    if not isinstance(proposals, list):
        try:
            proposals = capability_plan_view(snapshot).get("progression_policy_proposals") or []
        except ValueError:
            proposals = []
    resolved: list[dict[str, Any]] = []
    for proposal in list(proposals or []):
        if not isinstance(proposal, dict):
            continue
        action_type = str(proposal.get("action_type") or "").strip()
        if action_type not in {
            CEOActionType.CREATE_TICKET.value,
            "CLOSEOUT",
        }:
            continue
        payload = proposal.get("payload")
        if not isinstance(payload, dict):
            continue
        ticket_payload = payload.get("ticket_payload")
        if not isinstance(ticket_payload, dict):
            continue
        resolved.append(proposal)
    return resolved


def _build_policy_create_ticket_batch(snapshot: dict[str, Any], reason: str) -> CEOActionBatch | None:
    proposals = _progression_policy_create_ticket_proposals(snapshot)
    if not proposals:
        return None
    actions: list[dict[str, Any]] = []
    for proposal in proposals:
        ticket_payload = dict((proposal.get("payload") or {}).get("ticket_payload") or {})
        try:
            normalized_payload = CEOCreateTicketPayload.model_validate(ticket_payload).model_dump(mode="json")
        except ValidationError as exc:
            dispatch_intent = ticket_payload.get("dispatch_intent")
            if (
                isinstance(dispatch_intent, dict)
                and not str(dispatch_intent.get("assignee_employee_id") or "").strip()
            ):
                continue
            metadata = proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {}
            _raise_proposal_contract_error(
                source_component="progression_policy.create_ticket",
                reason_code="proposal_payload_invalid",
                message="Progression policy CREATE_TICKET proposal does not match the canonical CEO action contract.",
                details={
                    "policy_reason_code": str((metadata or {}).get("reason_code") or ""),
                    "errors": exc.errors(include_url=False),
                },
            )
        actions.append(
            {
                "action_type": CEOActionType.CREATE_TICKET,
                "payload": normalized_payload,
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
                "Open one bounded structured meeting because policy requires it before implementation fanout."
            ),
        )
    if recommended_action == "CREATE_TICKET":
        policy_create_ticket_batch = _build_policy_create_ticket_batch(snapshot, reason)
        if policy_create_ticket_batch is not None:
            return policy_create_ticket_batch
        if _should_fallback_to_project_init_kickoff(snapshot):
            return _build_project_init_kickoff_batch(snapshot, reason)
        return build_no_action_batch(
            "CREATE_TICKET progression requires a progression policy proposal."
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
        schema_entry = OUTPUT_SCHEMA_REGISTRY[(CEO_ACTION_BATCH_SCHEMA_REF, CEO_ACTION_BATCH_SCHEMA_VERSION)]
        metadata = _ceo_provider_attempt_metadata(snapshot, current_selection)
        if current_selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
            try:
                provider_result = invoke_openai_compat_response(
                    _ceo_openai_compat_config(current_selection, schema_entry=schema_entry),
                    rendered_payload,
                )
            except OpenAICompatProviderError as exc:
                _attach_provider_failure_metadata(exc, metadata)
                raise
            try:
                raw_payload = resolve_openai_compat_result_payload(provider_result).payload
            except OpenAICompatProviderError as exc:
                _attach_provider_failure_metadata(exc, metadata)
                raise
            except CEOProposalContractError as exc:
                exc.details.setdefault("provider_response_id", provider_result.response_id)
                exc.details.setdefault("attempt_id", metadata["provider_attempt_id"])
                exc.details.setdefault("provider_policy_ref", metadata["provider_policy_ref"])
                exc.details.setdefault("provider_timeout_policy", dict(metadata["provider_timeout_policy"]))
                raise
        else:
            try:
                provider_result = invoke_claude_code_response(
                    ClaudeCodeProviderConfig(
                        command_path=str(current_selection.provider.command_path or ""),
                        model=str(current_selection.actual_model or current_selection.provider.model or ""),
                        timeout_sec=current_selection.provider.timeout_sec,
                    ),
                    rendered_payload,
                )
            except ClaudeCodeProviderError as exc:
                _attach_provider_failure_metadata(exc, metadata)
                raise
            raw_payload = json.loads(provider_result.output_text)
        try:
            payload = _normalize_provider_action_batch_payload(raw_payload)
            return CEOActionBatch.model_validate(payload), provider_result, metadata
        except CEOProposalContractError as exc:
            exc.details.setdefault("provider_response_id", provider_result.response_id)
            exc.details.setdefault("attempt_id", metadata["provider_attempt_id"])
            exc.details.setdefault("provider_policy_ref", metadata["provider_policy_ref"])
            exc.details.setdefault("provider_timeout_policy", dict(metadata["provider_timeout_policy"]))
            raise

    try:
        action_batch, provider_result, provider_metadata = _invoke_selection(selection)
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
            provider_policy_ref=provider_metadata["provider_policy_ref"],
            provider_attempt_id=provider_metadata["provider_attempt_id"],
            provider_timeout_policy=dict(provider_metadata["provider_timeout_policy"]),
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
                    action_batch, provider_result, provider_metadata = _invoke_selection(failover_selection)
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
                        provider_policy_ref=provider_metadata["provider_policy_ref"],
                        provider_attempt_id=provider_metadata["provider_attempt_id"],
                        provider_timeout_policy=dict(provider_metadata["provider_timeout_policy"]),
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
