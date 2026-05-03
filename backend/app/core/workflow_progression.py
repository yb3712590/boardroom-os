from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.contracts.common import JsonValue, StrictModel
from app.core.ceo_execution_presets import (
    GOVERNANCE_DOCUMENT_CHAIN_ORDER,
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
    build_project_init_architecture_brief_ticket_specs as _build_project_init_architecture_brief_ticket_specs,
    build_autopilot_architecture_brief_summary,
    supports_ceo_create_ticket_preset,
)
from app.core.execution_targets import (
    employee_supports_execution_contract,
    infer_execution_contract_payload,
)
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate

AUTOPILOT_GOVERNANCE_CHAIN = "AUTOPILOT_GOVERNANCE_CHAIN"


class ProgressionActionType(StrEnum):
    CREATE_TICKET = "CREATE_TICKET"
    WAIT = "WAIT"
    REWORK = "REWORK"
    CLOSEOUT = "CLOSEOUT"
    INCIDENT = "INCIDENT"
    NO_ACTION = "NO_ACTION"


class ActionMetadata(StrictModel):
    reason_code: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    source_graph_version: str = Field(min_length=1)
    affected_node_refs: list[str] = Field(default_factory=list)
    expected_state_transition: str = Field(min_length=1)
    policy_ref: str = Field(min_length=1)


class ActionProposal(StrictModel):
    action_type: ProgressionActionType
    metadata: ActionMetadata
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ProgressionSnapshot(StrictModel):
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    node_refs: list[str] = Field(default_factory=list)
    ticket_refs: list[str] = Field(default_factory=list)
    ready_ticket_ids: list[str] = Field(default_factory=list)
    ready_node_refs: list[str] = Field(default_factory=list)
    blocked_ticket_ids: list[str] = Field(default_factory=list)
    blocked_node_refs: list[str] = Field(default_factory=list)
    in_flight_ticket_ids: list[str] = Field(default_factory=list)
    in_flight_node_refs: list[str] = Field(default_factory=list)
    incidents: list[dict[str, JsonValue]] = Field(default_factory=list)
    approvals: list[dict[str, JsonValue]] = Field(default_factory=list)
    actor_availability: dict[str, JsonValue] = Field(default_factory=dict)
    provider_availability: dict[str, JsonValue] = Field(default_factory=dict)


class ProgressionPolicy(StrictModel):
    policy_ref: str = Field(min_length=1)
    governance: dict[str, JsonValue] = Field(default_factory=dict)
    fanout: dict[str, JsonValue] = Field(default_factory=dict)
    closeout: dict[str, JsonValue] = Field(default_factory=dict)
    recovery: dict[str, JsonValue] = Field(default_factory=dict)
    create_ticket_candidates: list[dict[str, JsonValue]] = Field(default_factory=list)
    wait_reason_code: str = "progression.wait_for_blockers"
    no_action_reason_code: str = "progression.no_action"


_GOVERNANCE_ROLE_PRIORITY_BY_SCHEMA: dict[str, tuple[str, ...]] = {
    ARCHITECTURE_BRIEF_SCHEMA_REF: (
        "architect_primary",
    ),
    TECHNOLOGY_DECISION_SCHEMA_REF: (
        "architect_primary",
        "cto_primary",
    ),
    MILESTONE_PLAN_SCHEMA_REF: (
        "cto_primary",
    ),
    DETAILED_DESIGN_SCHEMA_REF: (
        "architect_primary",
    ),
    BACKLOG_RECOMMENDATION_SCHEMA_REF: (
        "cto_primary",
    ),
}

_DEFAULT_TRANSITION_BY_ACTION_TYPE: dict[ProgressionActionType, str] = {
    ProgressionActionType.CREATE_TICKET: "TICKET_CREATED",
    ProgressionActionType.WAIT: "WAITING_ON_BLOCKERS",
    ProgressionActionType.REWORK: "REWORK_REQUESTED",
    ProgressionActionType.CLOSEOUT: "CLOSEOUT_REQUESTED",
    ProgressionActionType.INCIDENT: "INCIDENT_OPENED",
    ProgressionActionType.NO_ACTION: "NO_STATE_CHANGE",
}


def _stable_unique_strings(values: list[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple, set)):
        stable_items = [_stable_value(item) for item in value]
        return sorted(
            stable_items,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, StrEnum):
        return value.value
    return value


def build_action_metadata(
    *,
    action_type: ProgressionActionType | str,
    reason_code: str,
    source_graph_version: str,
    affected_node_refs: list[str] | None = None,
    expected_state_transition: str | None = None,
    policy_ref: str,
    idempotency_components: dict[str, Any] | None = None,
) -> ActionMetadata:
    resolved_action_type = ProgressionActionType(action_type)
    resolved_affected_node_refs = _stable_unique_strings(list(affected_node_refs or []))
    resolved_transition = (
        str(expected_state_transition or "").strip()
        or _DEFAULT_TRANSITION_BY_ACTION_TYPE[resolved_action_type]
    )
    idempotency_payload = _stable_value(
        {
            "action_type": resolved_action_type.value,
            "reason_code": str(reason_code).strip(),
            "source_graph_version": str(source_graph_version).strip(),
            "affected_node_refs": resolved_affected_node_refs,
            "expected_state_transition": resolved_transition,
            "policy_ref": str(policy_ref).strip(),
            "components": idempotency_components or {},
        }
    )
    idempotency_digest = hashlib.sha256(
        json.dumps(
            idempotency_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return ActionMetadata(
        reason_code=str(reason_code).strip(),
        idempotency_key=(
            "progression:"
            f"{resolved_action_type.value}:"
            f"{str(source_graph_version).strip()}:"
            f"{str(policy_ref).strip()}:"
            f"{idempotency_digest}"
        ),
        source_graph_version=str(source_graph_version).strip(),
        affected_node_refs=resolved_affected_node_refs,
        expected_state_transition=resolved_transition,
        policy_ref=str(policy_ref).strip(),
    )


def _refs_from_records(records: list[dict[str, JsonValue]], *, ref_key: str, fallback_key: str) -> list[str]:
    refs: list[str] = []
    for record in records:
        node_ref = str(record.get(ref_key) or "").strip()
        if node_ref:
            refs.append(node_ref)
        fallback_ref = str(record.get(fallback_key) or "").strip()
        if fallback_ref:
            refs.append(fallback_ref)
    return _stable_unique_strings(refs)


def _ids_from_records(records: list[dict[str, JsonValue]], key: str) -> list[str]:
    return _stable_unique_strings([str(record.get(key) or "").strip() for record in records])


def _wait_proposal(snapshot: ProgressionSnapshot, policy: ProgressionPolicy) -> ActionProposal:
    affected_node_refs = _stable_unique_strings(
        [
            *snapshot.in_flight_node_refs,
            *_refs_from_records(snapshot.incidents, ref_key="node_ref", fallback_key="node_id"),
            *_refs_from_records(snapshot.approvals, ref_key="node_ref", fallback_key="node_id"),
        ]
    )
    blocked_by = {
        "approval_refs": _ids_from_records(snapshot.approvals, "approval_id"),
        "incident_refs": _ids_from_records(snapshot.incidents, "incident_id"),
        "in_flight_ticket_ids": _stable_unique_strings(snapshot.in_flight_ticket_ids),
    }
    return ActionProposal(
        action_type=ProgressionActionType.WAIT,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.WAIT,
            reason_code=policy.wait_reason_code,
            source_graph_version=snapshot.graph_version,
            affected_node_refs=affected_node_refs,
            expected_state_transition="WAITING_ON_BLOCKERS",
            policy_ref=policy.policy_ref,
            idempotency_components=blocked_by,
        ),
        payload={
            "wake_condition": "approval_or_incident_or_in_flight_resolved",
            "blocked_by": blocked_by,
        },
    )


def _create_ticket_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
    candidate: dict[str, JsonValue],
) -> ActionProposal:
    node_ref = str(candidate.get("node_ref") or candidate.get("node_id") or "").strip()
    candidate_ref = str(candidate.get("candidate_ref") or node_ref or "create_ticket").strip()
    ticket_payload = candidate.get("ticket_payload")
    if not isinstance(ticket_payload, dict):
        ticket_payload = {}
    return ActionProposal(
        action_type=ProgressionActionType.CREATE_TICKET,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.CREATE_TICKET,
            reason_code="progression.create_ticket_candidate",
            source_graph_version=snapshot.graph_version,
            affected_node_refs=[node_ref] if node_ref else [],
            expected_state_transition="TICKET_CREATED",
            policy_ref=policy.policy_ref,
            idempotency_components={
                "candidate_ref": candidate_ref,
                "ticket_payload": ticket_payload,
            },
        ),
        payload={
            "candidate_ref": candidate_ref,
            "ticket_payload": dict(ticket_payload),
        },
    )


def _no_action_proposal(snapshot: ProgressionSnapshot, policy: ProgressionPolicy) -> ActionProposal:
    return ActionProposal(
        action_type=ProgressionActionType.NO_ACTION,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.NO_ACTION,
            reason_code=policy.no_action_reason_code,
            source_graph_version=snapshot.graph_version,
            affected_node_refs=[],
            expected_state_transition="NO_STATE_CHANGE",
            policy_ref=policy.policy_ref,
            idempotency_components={
                "workflow_id": snapshot.workflow_id,
                "ready_ticket_ids": snapshot.ready_ticket_ids,
                "ready_node_refs": snapshot.ready_node_refs,
            },
        ),
        payload={"reason": "No structured policy action is currently eligible."},
    )


def decide_next_actions(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> list[ActionProposal]:
    if snapshot.approvals or snapshot.incidents or snapshot.in_flight_ticket_ids or snapshot.in_flight_node_refs:
        return [_wait_proposal(snapshot, policy)]

    if policy.create_ticket_candidates:
        ordered_candidates = sorted(
            policy.create_ticket_candidates,
            key=lambda item: (
                str(item.get("candidate_ref") or ""),
                str(item.get("node_ref") or item.get("node_id") or ""),
            ),
        )
        return [_create_ticket_proposal(snapshot, policy, ordered_candidates[0])]

    return [_no_action_proposal(snapshot, policy)]


def resolve_workflow_progression_adapter(workflow: dict[str, Any] | None) -> str:
    if workflow_uses_ceo_board_delegate(workflow):
        return AUTOPILOT_GOVERNANCE_CHAIN
    return AUTOPILOT_GOVERNANCE_CHAIN


def build_project_init_kickoff_spec(workflow: dict[str, Any] | None) -> dict[str, Any]:
    workflow = workflow or {}
    adapter_id = resolve_workflow_progression_adapter(workflow)
    north_star_goal = str(workflow.get("north_star_goal") or workflow.get("title") or "").strip()
    return {
        "adapter_id": adapter_id,
        "node_id": PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
        "role_profile_ref": "architect_primary",
        "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
        "summary": build_autopilot_architecture_brief_summary(north_star_goal),
    }


def build_project_init_architecture_brief_ticket_specs(
    workflow: dict[str, Any] | None,
    *,
    board_brief_artifact_ref: str,
) -> list[dict[str, Any]]:
    return _build_project_init_architecture_brief_ticket_specs(
        workflow,
        board_brief_artifact_ref=board_brief_artifact_ref,
    )


def resolve_next_governance_schema(completed_ticket_ids_by_schema: dict[str, str]) -> str | None:
    for output_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        if not completed_ticket_ids_by_schema.get(output_schema_ref):
            return output_schema_ref
    return None


def governance_dependency_gate_refs(
    completed_ticket_ids_by_schema: dict[str, str],
    output_schema_ref: str,
) -> list[str]:
    if output_schema_ref not in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        return []
    dependency_gate_refs: list[str] = []
    for prerequisite_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER[
        : GOVERNANCE_DOCUMENT_CHAIN_ORDER.index(output_schema_ref)
    ]:
        ticket_id = str(completed_ticket_ids_by_schema.get(prerequisite_schema_ref) or "").strip()
        if ticket_id:
            dependency_gate_refs.append(ticket_id)
    return dependency_gate_refs


def governance_parent_ticket_id(
    completed_ticket_ids_by_schema: dict[str, str],
    output_schema_ref: str,
) -> str | None:
    dependency_gate_refs = governance_dependency_gate_refs(completed_ticket_ids_by_schema, output_schema_ref)
    return dependency_gate_refs[-1] if dependency_gate_refs else None


def build_governance_followup_node_id(output_schema_ref: str) -> str:
    return f"node_ceo_{output_schema_ref}"


def build_governance_followup_summary(output_schema_ref: str) -> str:
    label = output_schema_ref.replace("_", " ")
    return f"Prepare the {label} before implementation fanout continues."


def _resolve_governance_execution_plan(output_schema_ref: str) -> dict[str, Any] | None:
    for role_profile_ref in _GOVERNANCE_ROLE_PRIORITY_BY_SCHEMA.get(output_schema_ref, ()):
        if not supports_ceo_create_ticket_preset(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        ):
            continue
        execution_contract = infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        if execution_contract is None:
            continue
        return {
            "role_profile_ref": role_profile_ref,
            "output_schema_ref": output_schema_ref,
            "execution_contract": execution_contract,
        }
    return None


def select_governance_role_and_assignee(
    employees: list[dict[str, Any]],
    *,
    output_schema_ref: str,
) -> tuple[str | None, str | None]:
    execution_plan = _resolve_governance_execution_plan(output_schema_ref)
    if execution_plan is None:
        return None, None
    role_profile_ref = str(execution_plan["role_profile_ref"])
    execution_contract = dict(execution_plan["execution_contract"])

    for employee in sorted(employees, key=lambda item: str(item.get("employee_id") or "")):
        if str(employee.get("state") or "") != "ACTIVE":
            continue
        if role_profile_ref not in set(employee.get("role_profile_refs") or []):
            continue
        if not employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            continue
        return role_profile_ref, str(employee["employee_id"])
    return role_profile_ref, None
