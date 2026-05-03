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
    graph_nodes: list[dict[str, JsonValue]] = Field(default_factory=list)
    graph_edges: list[dict[str, JsonValue]] = Field(default_factory=list)
    runtime_nodes: list[dict[str, JsonValue]] = Field(default_factory=list)
    ticket_lineage: list[dict[str, JsonValue]] = Field(default_factory=list)
    replacements: list[dict[str, JsonValue]] = Field(default_factory=list)
    superseded_refs: list[str] = Field(default_factory=list)
    cancelled_refs: list[str] = Field(default_factory=list)
    graph_reduction_issues: list[dict[str, JsonValue]] = Field(default_factory=list)
    blocked_reasons: list[dict[str, JsonValue]] = Field(default_factory=list)
    completed_ticket_ids: list[str] = Field(default_factory=list)
    completed_node_refs: list[str] = Field(default_factory=list)
    stale_orphan_pending_refs: list[str] = Field(default_factory=list)
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


class ProgressionGraphEvaluation(StrictModel):
    current_ticket_ids_by_node_ref: dict[str, str] = Field(default_factory=dict)
    effective_node_refs: list[str] = Field(default_factory=list)
    effective_edges: list[dict[str, JsonValue]] = Field(default_factory=list)
    ready_ticket_ids: list[str] = Field(default_factory=list)
    ready_node_refs: list[str] = Field(default_factory=list)
    blocked_ticket_ids: list[str] = Field(default_factory=list)
    blocked_node_refs: list[str] = Field(default_factory=list)
    in_flight_ticket_ids: list[str] = Field(default_factory=list)
    in_flight_node_refs: list[str] = Field(default_factory=list)
    completed_ticket_ids: list[str] = Field(default_factory=list)
    completed_node_refs: list[str] = Field(default_factory=list)
    graph_complete: bool = False
    stale_orphan_pending_refs: list[str] = Field(default_factory=list)
    graph_reduction_issues: list[dict[str, JsonValue]] = Field(default_factory=list)


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

_INACTIVE_GRAPH_STATUSES = {"CANCELLED", "SUPERSEDED"}
_IN_FLIGHT_STATUSES = {"LEASED", "EXECUTING"}
_COMPLETED_STATUSES = {"COMPLETED"}


def _record_ref(value: Any) -> str:
    return str(value or "").strip()


def _node_ref_from_record(record: dict[str, JsonValue]) -> str:
    return (
        _record_ref(record.get("node_ref"))
        or _record_ref(record.get("graph_node_id"))
        or _record_ref(record.get("node_id"))
    )


def _edge_source_ref(edge: dict[str, JsonValue]) -> str:
    return (
        _record_ref(edge.get("source_node_ref"))
        or _record_ref(edge.get("source_graph_node_id"))
        or _record_ref(edge.get("source_node_id"))
    )


def _edge_target_ref(edge: dict[str, JsonValue]) -> str:
    return (
        _record_ref(edge.get("target_node_ref"))
        or _record_ref(edge.get("target_graph_node_id"))
        or _record_ref(edge.get("target_node_id"))
    )


def _ticket_id_from_record(record: dict[str, JsonValue]) -> str:
    return _record_ref(record.get("ticket_id"))


def _runtime_current_ticket_id(record: dict[str, JsonValue]) -> str:
    return (
        _record_ref(record.get("latest_ticket_id"))
        or _record_ref(record.get("current_ticket_id"))
        or _record_ref(record.get("ticket_id"))
    )


def _status_from_record(record: dict[str, JsonValue], key: str) -> str:
    return _record_ref(record.get(key)).upper()


def _replacement_new_ref(record: dict[str, JsonValue]) -> str:
    return (
        _record_ref(record.get("new_node_ref"))
        or _record_ref(record.get("new_graph_node_id"))
        or _record_ref(record.get("new_node_id"))
    )


def _replacement_old_ref(record: dict[str, JsonValue]) -> str:
    return (
        _record_ref(record.get("old_node_ref"))
        or _record_ref(record.get("old_graph_node_id"))
        or _record_ref(record.get("old_node_id"))
    )


def _replacement_new_ticket_id(record: dict[str, JsonValue]) -> str:
    return _record_ref(record.get("new_ticket_id"))


def _replacement_old_ticket_id(record: dict[str, JsonValue]) -> str:
    return _record_ref(record.get("old_ticket_id"))


def _inactive_refs(snapshot: ProgressionSnapshot) -> set[str]:
    return {
        *_stable_unique_strings(snapshot.cancelled_refs),
        *_stable_unique_strings(snapshot.superseded_refs),
    }


def _node_alias_refs(record: dict[str, JsonValue], node_ref: str) -> set[str]:
    return {
        ref
        for ref in {
            node_ref,
            _record_ref(record.get("graph_node_id")),
            _record_ref(record.get("node_id")),
            _record_ref(record.get("runtime_node_id")),
        }
        if ref
    }


def _append_graph_reduction_issue(
    issues: list[dict[str, JsonValue]],
    *,
    issue_code: str,
    node_ref: str,
    detail: str,
    related_ticket_id: str | None = None,
) -> None:
    issues.append(
        {
            "issue_code": issue_code,
            "node_ref": node_ref,
            "detail": detail,
            "related_ticket_id": related_ticket_id,
            "recoverable": False,
        }
    )


def evaluate_progression_graph(snapshot: ProgressionSnapshot) -> ProgressionGraphEvaluation:
    has_structured_nodes = bool(snapshot.graph_nodes or snapshot.runtime_nodes)
    inactive_refs = _inactive_refs(snapshot)
    stale_orphan_refs = set(_stable_unique_strings(snapshot.stale_orphan_pending_refs))
    candidate_nodes_by_ref: dict[str, list[dict[str, JsonValue]]] = {}
    runtime_nodes_by_ref: dict[str, dict[str, JsonValue]] = {}
    runtime_current_ticket_ids_by_ref: dict[str, str] = {}
    graph_reduction_issues = [dict(item) for item in snapshot.graph_reduction_issues]
    current_ticket_ids_by_node_ref: dict[str, str] = {}

    for runtime_node in snapshot.runtime_nodes:
        node_ref = _node_ref_from_record(runtime_node)
        if not node_ref:
            continue
        runtime_nodes_by_ref[node_ref] = dict(runtime_node)
        latest_ticket_id = _runtime_current_ticket_id(runtime_node)
        if latest_ticket_id:
            runtime_current_ticket_ids_by_ref[node_ref] = latest_ticket_id

    for node in snapshot.graph_nodes:
        node_ref = _node_ref_from_record(node)
        if not node_ref:
            continue
        normalized_node = dict(node)
        candidate_nodes_by_ref.setdefault(node_ref, []).append(normalized_node)
        ticket_id = _ticket_id_from_record(node)
        if _status_from_record(node, "node_status") in _INACTIVE_GRAPH_STATUSES:
            inactive_refs.update(_node_alias_refs(normalized_node, node_ref))
            if ticket_id:
                inactive_refs.add(ticket_id)
        if _status_from_record(node, "ticket_status") in _INACTIVE_GRAPH_STATUSES:
            inactive_refs.update(_node_alias_refs(normalized_node, node_ref))
            if ticket_id:
                inactive_refs.add(ticket_id)

    replacement_records = [dict(item) for item in snapshot.replacements]
    for edge in snapshot.graph_edges:
        if _record_ref(edge.get("edge_type")).upper() != "REPLACES":
            continue
        replacement_records.append(
            {
                "old_node_ref": _edge_target_ref(edge),
                "new_node_ref": _edge_source_ref(edge),
                "old_ticket_id": _record_ref(edge.get("target_ticket_id")),
                "new_ticket_id": _record_ref(edge.get("source_ticket_id")),
            }
        )
    replacement_current_ticket_ids_by_ref: dict[str, str] = {}
    for replacement in replacement_records:
        old_ref = _replacement_old_ref(replacement)
        new_ref = _replacement_new_ref(replacement)
        old_ticket_id = _replacement_old_ticket_id(replacement)
        new_ticket_id = _replacement_new_ticket_id(replacement)
        if old_ref:
            inactive_refs.add(old_ref)
        if old_ticket_id:
            inactive_refs.add(old_ticket_id)
        if new_ref and new_ticket_id:
            replacement_current_ticket_ids_by_ref[new_ref] = new_ticket_id

    node_by_ref: dict[str, dict[str, JsonValue]] = {}
    for node_ref, candidates in sorted(candidate_nodes_by_ref.items()):
        active_candidates = [
            candidate
            for candidate in candidates
            if not (
                _node_alias_refs(candidate, node_ref) & inactive_refs
                or _ticket_id_from_record(candidate) in inactive_refs
            )
        ]
        if not active_candidates:
            continue
        explicit_ticket_id = (
            runtime_current_ticket_ids_by_ref.get(node_ref)
            or replacement_current_ticket_ids_by_ref.get(node_ref)
        )
        selected_node: dict[str, JsonValue] | None = None
        if explicit_ticket_id:
            for candidate in active_candidates:
                if _ticket_id_from_record(candidate) == explicit_ticket_id:
                    selected_node = candidate
                    break
            if selected_node is None:
                issue_code = (
                    "graph.current_pointer.runtime_latest_missing"
                    if node_ref in runtime_current_ticket_ids_by_ref
                    else "graph.current_pointer.replacement_current_missing"
                )
                _append_graph_reduction_issue(
                    graph_reduction_issues,
                    issue_code=issue_code,
                    node_ref=node_ref,
                    detail=(
                        f"Graph lane {node_ref} points to current ticket "
                        f"{explicit_ticket_id}, but that ticket is not present in the structured snapshot."
                    ),
                    related_ticket_id=explicit_ticket_id,
                )
                continue
        elif len(active_candidates) == 1:
            selected_node = active_candidates[0]
        else:
            candidate_ticket_ids = _stable_unique_strings(
                [_ticket_id_from_record(candidate) for candidate in active_candidates]
            )
            _append_graph_reduction_issue(
                graph_reduction_issues,
                issue_code="graph.current_pointer.missing_explicit",
                node_ref=node_ref,
                detail=(
                    f"Graph lane {node_ref} has multiple candidate tickets but no explicit "
                    "runtime current pointer or replacement edge."
                ),
                related_ticket_id=",".join(candidate_ticket_ids) or None,
            )
            continue
        if selected_node is None:
            continue
        node_by_ref[node_ref] = selected_node
        selected_ticket_id = _ticket_id_from_record(selected_node)
        if selected_ticket_id:
            current_ticket_ids_by_node_ref[node_ref] = selected_ticket_id

    effective_node_refs: list[str] = []
    ready_ticket_ids: list[str] = []
    ready_node_refs: list[str] = []
    blocked_ticket_ids: list[str] = []
    blocked_node_refs: list[str] = []
    in_flight_ticket_ids: list[str] = []
    in_flight_node_refs: list[str] = []
    completed_ticket_ids: list[str] = []
    completed_node_refs: list[str] = []

    explicit_blocked_ticket_ids = (
        set()
        if has_structured_nodes
        else set(_stable_unique_strings(snapshot.blocked_ticket_ids))
    )
    explicit_blocked_node_refs = (
        set()
        if has_structured_nodes
        else set(_stable_unique_strings(snapshot.blocked_node_refs))
    )
    explicit_in_flight_ticket_ids = (
        set()
        if has_structured_nodes
        else set(_stable_unique_strings(snapshot.in_flight_ticket_ids))
    )
    explicit_in_flight_node_refs = (
        set()
        if has_structured_nodes
        else set(_stable_unique_strings(snapshot.in_flight_node_refs))
    )
    explicit_completed_ticket_ids = set(_stable_unique_strings(snapshot.completed_ticket_ids))
    explicit_completed_node_refs = set(_stable_unique_strings(snapshot.completed_node_refs))
    blocked_ticket_ids_from_reasons: set[str] = set()
    blocked_node_refs_from_reasons: set[str] = set()
    for reason in snapshot.blocked_reasons:
        blocked_ticket_ids_from_reasons.update(
            _stable_unique_strings(list(reason.get("ticket_ids") or []))
            if isinstance(reason.get("ticket_ids"), list)
            else []
        )
        node_values = reason.get("node_refs")
        if not isinstance(node_values, list):
            node_values = reason.get("node_ids")
        blocked_node_refs_from_reasons.update(
            _stable_unique_strings(list(node_values or []))
            if isinstance(node_values, list)
            else []
        )

    for node_ref, node in sorted(node_by_ref.items()):
        ticket_id = _ticket_id_from_record(node)
        node_alias_refs = _node_alias_refs(node, node_ref)
        if node_alias_refs & inactive_refs or ticket_id in inactive_refs:
            continue
        if node_alias_refs & stale_orphan_refs or ticket_id in stale_orphan_refs:
            continue
        runtime_node = runtime_nodes_by_ref.get(node_ref) or {}
        effective_node_refs.append(node_ref)
        ticket_status = _status_from_record(node, "ticket_status")
        node_status = _status_from_record(node, "node_status") or _status_from_record(runtime_node, "status")
        blocking_reason_code = (
            _record_ref(node.get("blocking_reason_code"))
            or _record_ref(runtime_node.get("blocking_reason_code"))
        )
        is_blocked = (
            ticket_id in explicit_blocked_ticket_ids
            or ticket_id in blocked_ticket_ids_from_reasons
            or bool(node_alias_refs & explicit_blocked_node_refs)
            or bool(node_alias_refs & blocked_node_refs_from_reasons)
            or bool(blocking_reason_code)
            or ticket_status == "BLOCKED_FOR_BOARD_REVIEW"
            or node_status == "BLOCKED_FOR_BOARD_REVIEW"
        )
        is_in_flight = (
            ticket_id in explicit_in_flight_ticket_ids
            or bool(node_alias_refs & explicit_in_flight_node_refs)
            or ticket_status in _IN_FLIGHT_STATUSES
            or node_status == "EXECUTING"
        )
        is_completed = (
            ticket_id in explicit_completed_ticket_ids
            or bool(node_alias_refs & explicit_completed_node_refs)
            or ticket_status in _COMPLETED_STATUSES
            or node_status in _COMPLETED_STATUSES
        )

        if is_blocked:
            if ticket_id:
                blocked_ticket_ids.append(ticket_id)
            blocked_node_refs.append(node_ref)
        if is_in_flight:
            if ticket_id:
                in_flight_ticket_ids.append(ticket_id)
            in_flight_node_refs.append(node_ref)
            continue
        if is_blocked:
            continue
        if is_completed:
            if ticket_id:
                completed_ticket_ids.append(ticket_id)
            completed_node_refs.append(node_ref)
            continue
        if ticket_status == "PENDING" or node_status == "PENDING":
            if ticket_id:
                ready_ticket_ids.append(ticket_id)
            ready_node_refs.append(node_ref)

    effective_edges: list[dict[str, JsonValue]] = []
    for edge in snapshot.graph_edges:
        source_ref = _edge_source_ref(edge)
        target_ref = _edge_target_ref(edge)
        source_ticket_id = _record_ref(edge.get("source_ticket_id"))
        target_ticket_id = _record_ref(edge.get("target_ticket_id"))
        if (
            source_ref in inactive_refs
            or target_ref in inactive_refs
            or source_ticket_id in inactive_refs
            or target_ticket_id in inactive_refs
        ):
            continue
        if source_ref not in effective_node_refs or target_ref not in effective_node_refs:
            continue
        if _record_ref(edge.get("edge_type")).upper() == "REPLACES":
            continue
        effective_edges.append(dict(edge))

    graph_complete = (
        bool(effective_node_refs)
        and not ready_ticket_ids
        and not blocked_ticket_ids
        and not in_flight_ticket_ids
        and set(effective_node_refs) == set(completed_node_refs)
    )

    return ProgressionGraphEvaluation(
        current_ticket_ids_by_node_ref={
            key: current_ticket_ids_by_node_ref[key]
            for key in sorted(current_ticket_ids_by_node_ref)
            if key not in inactive_refs
            and key not in stale_orphan_refs
            and current_ticket_ids_by_node_ref[key] not in inactive_refs
            and current_ticket_ids_by_node_ref[key] not in stale_orphan_refs
        },
        effective_node_refs=_stable_unique_strings(effective_node_refs),
        effective_edges=sorted(
            effective_edges,
            key=lambda item: (
                _record_ref(item.get("edge_type")),
                _edge_source_ref(item),
                _edge_target_ref(item),
            ),
        ),
        ready_ticket_ids=_stable_unique_strings(ready_ticket_ids),
        ready_node_refs=_stable_unique_strings(ready_node_refs),
        blocked_ticket_ids=_stable_unique_strings(blocked_ticket_ids),
        blocked_node_refs=_stable_unique_strings(blocked_node_refs),
        in_flight_ticket_ids=_stable_unique_strings(in_flight_ticket_ids),
        in_flight_node_refs=_stable_unique_strings(in_flight_node_refs),
        completed_ticket_ids=_stable_unique_strings(completed_ticket_ids),
        completed_node_refs=_stable_unique_strings(completed_node_refs),
        graph_complete=graph_complete,
        stale_orphan_pending_refs=_stable_unique_strings(list(stale_orphan_refs)),
        graph_reduction_issues=graph_reduction_issues,
    )


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


def _has_structured_graph_input(snapshot: ProgressionSnapshot) -> bool:
    return bool(
        snapshot.graph_nodes
        or snapshot.graph_edges
        or snapshot.runtime_nodes
        or snapshot.ticket_lineage
        or snapshot.replacements
        or snapshot.superseded_refs
        or snapshot.cancelled_refs
        or snapshot.completed_ticket_ids
        or snapshot.completed_node_refs
        or snapshot.stale_orphan_pending_refs
    )


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


def _records_from_policy_section(section: dict[str, JsonValue], key: str) -> list[dict[str, JsonValue]]:
    value = section.get(key)
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _record_output_schema_ref(record: dict[str, JsonValue]) -> str:
    return (
        _record_ref(record.get("output_schema_ref"))
        or _record_ref(record.get("required_output_schema_ref"))
        or _record_ref(record.get("schema_ref"))
    )


def _completed_governance_output_refs(governance: dict[str, JsonValue]) -> set[str]:
    completed_refs: set[str] = set()
    completed_outputs = governance.get("completed_outputs")
    if isinstance(completed_outputs, dict):
        completed_refs.update(
            str(key).strip()
            for key, value in completed_outputs.items()
            if str(key).strip() and bool(value)
        )
    for record in _records_from_policy_section(governance, "completed_outputs"):
        schema_ref = _record_output_schema_ref(record)
        if schema_ref and (
            _record_ref(record.get("ticket_id"))
            or _record_ref(record.get("artifact_ref"))
            or _record_ref(record.get("output_ref"))
            or bool(record.get("approved", True))
        ):
            completed_refs.add(schema_ref)
    return completed_refs


def _approved_meeting_requirement_refs(governance: dict[str, JsonValue]) -> set[str]:
    approved_refs: set[str] = set()
    for record in _records_from_policy_section(governance, "approved_meeting_evidence"):
        review_status = _record_ref(record.get("review_status")).upper()
        if review_status and review_status not in {"APPROVED", "APPROVED_WITH_NOTES"}:
            continue
        requirement_ref = _record_ref(record.get("requirement_ref"))
        if requirement_ref:
            approved_refs.add(requirement_ref)
        source_ticket_id = _record_ref(record.get("source_ticket_id"))
        required_meeting_type = _record_ref(record.get("required_meeting_type"))
        if source_ticket_id and required_meeting_type:
            approved_refs.add(f"{source_ticket_id}:{required_meeting_type}")
    return approved_refs


def _proposal_node_ref(record: dict[str, JsonValue], ticket_payload: dict[str, JsonValue] | None = None) -> str:
    ticket_payload = ticket_payload or {}
    return (
        _record_ref(record.get("node_ref"))
        or _record_ref(record.get("graph_node_id"))
        or _record_ref(record.get("node_id"))
        or _record_ref(ticket_payload.get("node_ref"))
        or _record_ref(ticket_payload.get("node_id"))
    )


def _create_ticket_policy_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
    *,
    reason_code: str,
    candidate_ref: str,
    ticket_payload: dict[str, JsonValue],
    affected_node_refs: list[str],
    idempotency_components: dict[str, Any],
    extra_payload: dict[str, JsonValue] | None = None,
) -> ActionProposal:
    payload: dict[str, JsonValue] = {
        "candidate_ref": candidate_ref,
        "ticket_payload": dict(ticket_payload),
    }
    if extra_payload:
        payload.update(dict(extra_payload))
    return ActionProposal(
        action_type=ProgressionActionType.CREATE_TICKET,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.CREATE_TICKET,
            reason_code=reason_code,
            source_graph_version=snapshot.graph_version,
            affected_node_refs=affected_node_refs,
            expected_state_transition="TICKET_CREATED",
            policy_ref=policy.policy_ref,
            idempotency_components=idempotency_components,
        ),
        payload=payload,
    )


def _governance_gate_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> ActionProposal | None:
    governance = dict(policy.governance)
    completed_output_refs = _completed_governance_output_refs(governance)
    for gate in sorted(
        _records_from_policy_section(governance, "required_gates"),
        key=lambda item: (
            _record_ref(item.get("gate_ref")),
            _record_ref(item.get("source_ticket_id")),
            _proposal_node_ref(item),
        ),
    ):
        if bool(gate.get("satisfied")):
            continue
        required_output_schema_ref = _record_ref(gate.get("required_output_schema_ref"))
        if (
            "satisfied" not in gate
            and required_output_schema_ref
            and required_output_schema_ref in completed_output_refs
        ):
            continue
        existing_ticket_id = _record_ref(gate.get("existing_ticket_id"))
        node_ref = _proposal_node_ref(gate)
        gate_ref = _record_ref(gate.get("gate_ref")) or f"gate:{node_ref or required_output_schema_ref}"
        if existing_ticket_id:
            return ActionProposal(
                action_type=ProgressionActionType.WAIT,
                metadata=build_action_metadata(
                    action_type=ProgressionActionType.WAIT,
                    reason_code="progression.wait.governance_gate_existing_ticket",
                    source_graph_version=snapshot.graph_version,
                    affected_node_refs=[node_ref] if node_ref else [],
                    expected_state_transition="WAITING_ON_GOVERNANCE_GATE",
                    policy_ref=policy.policy_ref,
                    idempotency_components={
                        "gate_ref": gate_ref,
                        "existing_ticket_id": existing_ticket_id,
                    },
                ),
                payload={
                    "wake_condition": "governance_gate_ticket_completed",
                    "governance_gate": dict(gate),
                },
            )
        ticket_payload = gate.get("ticket_payload")
        if not isinstance(ticket_payload, dict):
            continue
        reason_code = (
            "progression.governance.architect_gate_required"
            if _record_ref(gate.get("gate_type")).upper() == "ARCHITECT_GOVERNANCE"
            else "progression.governance.gate_required"
        )
        return _create_ticket_policy_proposal(
            snapshot,
            policy,
            reason_code=reason_code,
            candidate_ref=gate_ref,
            ticket_payload=dict(ticket_payload),
            affected_node_refs=[node_ref] if node_ref else [],
            idempotency_components={
                "gate_ref": gate_ref,
                "required_output_schema_ref": required_output_schema_ref,
                "ticket_payload": ticket_payload,
            },
            extra_payload={"governance_gate": dict(gate)},
        )
    return None


def _governance_chain_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> ActionProposal | None:
    governance = dict(policy.governance)
    chain_order = [
        str(item).strip()
        for item in list(governance.get("chain_order") or [])
        if str(item).strip()
    ]
    if not chain_order:
        return None
    completed_output_refs = _completed_governance_output_refs(governance)
    next_schema_ref = next(
        (schema_ref for schema_ref in chain_order if schema_ref not in completed_output_refs),
        None,
    )
    if next_schema_ref is None:
        return None
    ticket_plans = _records_from_policy_section(governance, "chain_ticket_plans")
    ticket_plans.extend(_records_from_policy_section(governance, "ticket_plans"))
    for plan in sorted(
        ticket_plans,
        key=lambda item: (_record_ref(item.get("output_schema_ref")), _proposal_node_ref(item)),
    ):
        if _record_ref(plan.get("output_schema_ref")) != next_schema_ref:
            continue
        existing_ticket_id = _record_ref(plan.get("existing_ticket_id"))
        ticket_payload = plan.get("ticket_payload")
        node_ref = _proposal_node_ref(plan, ticket_payload if isinstance(ticket_payload, dict) else None)
        candidate_ref = _record_ref(plan.get("candidate_ref")) or f"governance:{next_schema_ref}"
        if existing_ticket_id:
            return ActionProposal(
                action_type=ProgressionActionType.WAIT,
                metadata=build_action_metadata(
                    action_type=ProgressionActionType.WAIT,
                    reason_code="progression.wait.governance_followup_existing_ticket",
                    source_graph_version=snapshot.graph_version,
                    affected_node_refs=[node_ref] if node_ref else [],
                    expected_state_transition="WAITING_ON_GOVERNANCE_FOLLOWUP",
                    policy_ref=policy.policy_ref,
                    idempotency_components={
                        "candidate_ref": candidate_ref,
                        "existing_ticket_id": existing_ticket_id,
                    },
                ),
                payload={
                    "wake_condition": "governance_followup_ticket_completed",
                    "governance_followup": dict(plan),
                },
            )
        if not isinstance(ticket_payload, dict):
            return None
        return _create_ticket_policy_proposal(
            snapshot,
            policy,
            reason_code="progression.governance.followup_required",
            candidate_ref=candidate_ref,
            ticket_payload=dict(ticket_payload),
            affected_node_refs=[node_ref] if node_ref else [],
            idempotency_components={
                "candidate_ref": candidate_ref,
                "output_schema_ref": next_schema_ref,
                "ticket_payload": ticket_payload,
            },
            extra_payload={"governance_followup": dict(plan)},
        )
    return None


def _meeting_requirement_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> ActionProposal | None:
    governance = dict(policy.governance)
    approved_refs = _approved_meeting_requirement_refs(governance)
    pending_requirements: list[dict[str, JsonValue]] = []
    affected_node_refs: list[str] = []
    for requirement in sorted(
        _records_from_policy_section(governance, "meeting_requirements"),
        key=lambda item: (
            _record_ref(item.get("requirement_ref")),
            _record_ref(item.get("source_ticket_id")),
            _proposal_node_ref(item),
        ),
    ):
        requirement_ref = _record_ref(requirement.get("requirement_ref"))
        source_ticket_id = _record_ref(requirement.get("source_ticket_id"))
        required_meeting_type = _record_ref(requirement.get("required_meeting_type"))
        requirement_keys = {
            ref
            for ref in {
                requirement_ref,
                f"{source_ticket_id}:{required_meeting_type}" if source_ticket_id and required_meeting_type else "",
            }
            if ref
        }
        if requirement_keys & approved_refs:
            continue
        pending_requirements.append(dict(requirement))
        node_ref = _proposal_node_ref(requirement)
        if node_ref:
            affected_node_refs.append(node_ref)
    if not pending_requirements:
        return None
    return ActionProposal(
        action_type=ProgressionActionType.WAIT,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.WAIT,
            reason_code="progression.wait.meeting_requirement",
            source_graph_version=snapshot.graph_version,
            affected_node_refs=affected_node_refs,
            expected_state_transition="WAITING_ON_MEETING_REQUIREMENT",
            policy_ref=policy.policy_ref,
            idempotency_components={"meeting_requirements": pending_requirements},
        ),
        payload={
            "wake_condition": "meeting_requirement_approved",
            "meeting_requirements": pending_requirements,
        },
    )


def _backlog_fanout_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> ActionProposal | None:
    fanout = dict(policy.fanout)
    handoff = fanout.get("backlog_implementation_handoff")
    if not isinstance(handoff, dict):
        return None
    source_ticket_id = _record_ref(handoff.get("source_ticket_id"))
    existing_ticket_ids_by_node_ref = {
        str(key).strip(): str(value).strip()
        for key, value in dict(fanout.get("existing_ticket_ids_by_node_ref") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    ticket_plans = [
        dict(item)
        for item in list(handoff.get("ticket_plans") or handoff.get("tickets") or [])
        if isinstance(item, dict)
    ]
    materialized_plan_keys = {
        _record_ref(plan.get("ticket_key"))
        for plan in ticket_plans
        if _record_ref(plan.get("ticket_key"))
        and (
            _record_ref(plan.get("existing_ticket_id"))
            or existing_ticket_ids_by_node_ref.get(_proposal_node_ref(plan))
        )
    }
    all_plan_keys = {
        _record_ref(plan.get("ticket_key"))
        for plan in ticket_plans
        if _record_ref(plan.get("ticket_key"))
    }
    for plan in sorted(
        ticket_plans,
        key=lambda item: (
            int(item.get("sequence_index") or 0),
            _record_ref(item.get("ticket_key")),
            _proposal_node_ref(item),
        ),
    ):
        ticket_key = _record_ref(plan.get("ticket_key"))
        ticket_payload = plan.get("ticket_payload")
        node_ref = _proposal_node_ref(plan, ticket_payload if isinstance(ticket_payload, dict) else None)
        if _record_ref(plan.get("existing_ticket_id")) or existing_ticket_ids_by_node_ref.get(node_ref):
            continue
        blocked_by_plan_keys = [
            str(item).strip()
            for item in list(plan.get("blocked_by_plan_keys") or [])
            if str(item).strip()
        ]
        if any(
            dependency_key in all_plan_keys and dependency_key not in materialized_plan_keys
            for dependency_key in blocked_by_plan_keys
        ):
            continue
        if not isinstance(ticket_payload, dict):
            continue
        candidate_ref = (
            _record_ref(plan.get("candidate_ref"))
            or f"backlog:{source_ticket_id or 'unknown'}:{ticket_key or node_ref or 'ticket'}"
        )
        return _create_ticket_policy_proposal(
            snapshot,
            policy,
            reason_code="progression.fanout.backlog_handoff_ticket",
            candidate_ref=candidate_ref,
            ticket_payload=dict(ticket_payload),
            affected_node_refs=[node_ref] if node_ref else [],
            idempotency_components={
                "candidate_ref": candidate_ref,
                "source_ticket_id": source_ticket_id,
                "ticket_key": ticket_key,
                "ticket_payload": ticket_payload,
            },
            extra_payload={
                "source_ticket_id": source_ticket_id,
                "source_graph_version": _record_ref(handoff.get("source_graph_version")),
                "fanout_plan": dict(plan),
            },
        )
    return None


def _graph_patch_fanout_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> ActionProposal | None:
    fanout = dict(policy.fanout)
    patch_plan = fanout.get("fanout_graph_patch_plan")
    if not isinstance(patch_plan, dict):
        return None
    source_ticket_id = _record_ref(patch_plan.get("source_ticket_id"))
    patch_ref = _record_ref(patch_plan.get("patch_ref"))
    existing_ticket_ids_by_node_ref = {
        str(key).strip(): str(value).strip()
        for key, value in dict(fanout.get("existing_ticket_ids_by_node_ref") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    ticket_plans = [
        dict(item)
        for item in list(patch_plan.get("ticket_plans") or patch_plan.get("tickets") or [])
        if isinstance(item, dict)
    ]
    materialized_plan_keys = {
        _record_ref(plan.get("ticket_key"))
        for plan in ticket_plans
        if _record_ref(plan.get("ticket_key"))
        and (
            _record_ref(plan.get("existing_ticket_id"))
            or existing_ticket_ids_by_node_ref.get(_proposal_node_ref(plan))
        )
    }
    all_plan_keys = {
        _record_ref(plan.get("ticket_key"))
        for plan in ticket_plans
        if _record_ref(plan.get("ticket_key"))
    }
    for plan in sorted(
        ticket_plans,
        key=lambda item: (
            int(item.get("sequence_index") or 0),
            _record_ref(item.get("ticket_key")),
            _proposal_node_ref(item),
        ),
    ):
        ticket_key = _record_ref(plan.get("ticket_key"))
        ticket_payload = plan.get("ticket_payload")
        node_ref = _proposal_node_ref(plan, ticket_payload if isinstance(ticket_payload, dict) else None)
        if _record_ref(plan.get("existing_ticket_id")) or existing_ticket_ids_by_node_ref.get(node_ref):
            continue
        blocked_by_plan_keys = [
            str(item).strip()
            for item in list(plan.get("blocked_by_plan_keys") or [])
            if str(item).strip()
        ]
        if any(
            dependency_key in all_plan_keys and dependency_key not in materialized_plan_keys
            for dependency_key in blocked_by_plan_keys
        ):
            continue
        if not isinstance(ticket_payload, dict):
            continue
        candidate_ref = (
            _record_ref(plan.get("candidate_ref"))
            or f"graph_patch:{patch_ref or source_ticket_id or 'unknown'}:{ticket_key or node_ref or 'ticket'}"
        )
        return _create_ticket_policy_proposal(
            snapshot,
            policy,
            reason_code="progression.fanout.graph_patch_ticket",
            candidate_ref=candidate_ref,
            ticket_payload=dict(ticket_payload),
            affected_node_refs=[node_ref] if node_ref else [],
            idempotency_components={
                "candidate_ref": candidate_ref,
                "patch_ref": patch_ref,
                "source_ticket_id": source_ticket_id,
                "ticket_key": ticket_key,
                "ticket_payload": ticket_payload,
            },
            extra_payload={
                "source_ticket_id": source_ticket_id,
                "source_graph_version": _record_ref(patch_plan.get("source_graph_version")),
                "fanout_graph_patch_plan": dict(patch_plan),
                "fanout_plan": dict(plan),
            },
        )
    return None


def _structured_policy_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> ActionProposal | None:
    return (
        _governance_gate_proposal(snapshot, policy)
        or _governance_chain_proposal(snapshot, policy)
        or _meeting_requirement_proposal(snapshot, policy)
        or _backlog_fanout_proposal(snapshot, policy)
        or _graph_patch_fanout_proposal(snapshot, policy)
    )


def _wait_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
    graph_evaluation: ProgressionGraphEvaluation | None = None,
) -> ActionProposal:
    graph_evaluation = graph_evaluation or evaluate_progression_graph(snapshot)
    use_structured_graph = _has_structured_graph_input(snapshot)
    in_flight_ticket_ids = (
        graph_evaluation.in_flight_ticket_ids
        if use_structured_graph
        else _stable_unique_strings(snapshot.in_flight_ticket_ids)
    )
    in_flight_node_refs = (
        graph_evaluation.in_flight_node_refs
        if use_structured_graph
        else _stable_unique_strings(snapshot.in_flight_node_refs)
    )
    reason_code = policy.wait_reason_code
    wake_condition = "approval_or_incident_or_in_flight_resolved"
    if snapshot.approvals:
        reason_code = "progression.wait.open_approval"
        wake_condition = "approval_resolved"
    elif snapshot.incidents:
        reason_code = "progression.wait.open_incident"
        wake_condition = "incident_resolved"
    elif in_flight_ticket_ids or in_flight_node_refs:
        reason_code = "progression.wait.in_flight_runtime"
        wake_condition = "runtime_ticket_finished"
    affected_node_refs = _stable_unique_strings(
        [
            *in_flight_node_refs,
            *_refs_from_records(snapshot.incidents, ref_key="node_ref", fallback_key="node_id"),
            *_refs_from_records(snapshot.approvals, ref_key="node_ref", fallback_key="node_id"),
        ]
    )
    blocked_by = {
        "approval_refs": _ids_from_records(snapshot.approvals, "approval_id"),
        "incident_refs": _ids_from_records(snapshot.incidents, "incident_id"),
        "in_flight_ticket_ids": _stable_unique_strings(in_flight_ticket_ids),
    }
    return ActionProposal(
        action_type=ProgressionActionType.WAIT,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.WAIT,
            reason_code=reason_code,
            source_graph_version=snapshot.graph_version,
            affected_node_refs=affected_node_refs,
            expected_state_transition="WAITING_ON_BLOCKERS",
            policy_ref=policy.policy_ref,
            idempotency_components=blocked_by,
        ),
        payload={
            "wake_condition": wake_condition,
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


def _no_action_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
    graph_evaluation: ProgressionGraphEvaluation | None = None,
) -> ActionProposal:
    graph_evaluation = graph_evaluation or evaluate_progression_graph(snapshot)
    use_structured_graph = _has_structured_graph_input(snapshot)
    blocked_ticket_ids = (
        graph_evaluation.blocked_ticket_ids
        if use_structured_graph
        else _stable_unique_strings(snapshot.blocked_ticket_ids)
    )
    blocked_node_refs = (
        graph_evaluation.blocked_node_refs
        if use_structured_graph
        else _stable_unique_strings(snapshot.blocked_node_refs)
    )
    reason_code = policy.no_action_reason_code
    reason = "No structured policy action is currently eligible."
    affected_node_refs: list[str] = []
    idempotency_context: dict[str, Any] = {
        "workflow_id": snapshot.workflow_id,
        "ready_ticket_ids": (
            graph_evaluation.ready_ticket_ids
            if use_structured_graph
            else _stable_unique_strings(snapshot.ready_ticket_ids)
        ),
        "ready_node_refs": (
            graph_evaluation.ready_node_refs
            if use_structured_graph
            else _stable_unique_strings(snapshot.ready_node_refs)
        ),
    }
    if graph_evaluation.graph_complete and graph_evaluation.stale_orphan_pending_refs:
        reason_code = "progression.stale_orphan_pending_ignored"
        reason = "Only stale or orphan pending refs remain outside the effective graph."
        affected_node_refs = list(graph_evaluation.stale_orphan_pending_refs)
        idempotency_context["stale_orphan_pending_refs"] = graph_evaluation.stale_orphan_pending_refs
    elif graph_evaluation.graph_complete:
        reason_code = "progression.graph_complete_no_closeout_in_8b"
        reason = "The effective graph is complete; closeout routing remains in Round 8D."
        affected_node_refs = list(graph_evaluation.completed_node_refs)
        idempotency_context["completed_ticket_ids"] = graph_evaluation.completed_ticket_ids
    elif blocked_ticket_ids or blocked_node_refs or snapshot.blocked_reasons:
        reason_code = "progression.blocked_no_recovery_action"
        reason = "Blocked graph nodes have no structured recovery action in Round 8B."
        affected_node_refs = list(blocked_node_refs)
        idempotency_context["blocked_ticket_ids"] = blocked_ticket_ids
        idempotency_context["blocked_node_refs"] = blocked_node_refs
    return ActionProposal(
        action_type=ProgressionActionType.NO_ACTION,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.NO_ACTION,
            reason_code=reason_code,
            source_graph_version=snapshot.graph_version,
            affected_node_refs=affected_node_refs,
            expected_state_transition="NO_STATE_CHANGE",
            policy_ref=policy.policy_ref,
            idempotency_components=idempotency_context,
        ),
        payload={"reason": reason},
    )


def _graph_reduction_issue_proposal(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
    graph_evaluation: ProgressionGraphEvaluation | None = None,
) -> ActionProposal:
    graph_evaluation = graph_evaluation or evaluate_progression_graph(snapshot)
    issues = [dict(item) for item in graph_evaluation.graph_reduction_issues]
    affected_node_refs = _stable_unique_strings(
        [
            _record_ref(item.get("node_ref"))
            or _record_ref(item.get("graph_node_id"))
            or _record_ref(item.get("node_id"))
            for item in issues
        ]
    )
    recoverable = all(bool(item.get("recoverable", True)) for item in issues)
    if recoverable:
        return ActionProposal(
            action_type=ProgressionActionType.WAIT,
            metadata=build_action_metadata(
                action_type=ProgressionActionType.WAIT,
                reason_code="progression.wait.graph_reduction_issue",
                source_graph_version=snapshot.graph_version,
                affected_node_refs=affected_node_refs,
                expected_state_transition="WAITING_ON_GRAPH_REDUCTION",
                policy_ref=policy.policy_ref,
                idempotency_components={"graph_reduction_issues": issues},
            ),
            payload={
                "wake_condition": "graph_reduction_issue_resolved",
                "graph_reduction_issues": issues,
            },
        )
    return ActionProposal(
        action_type=ProgressionActionType.INCIDENT,
        metadata=build_action_metadata(
            action_type=ProgressionActionType.INCIDENT,
            reason_code="progression.incident.graph_reduction_issue",
            source_graph_version=snapshot.graph_version,
            affected_node_refs=affected_node_refs,
            expected_state_transition="INCIDENT_OPENED",
            policy_ref=policy.policy_ref,
            idempotency_components={"graph_reduction_issues": issues},
        ),
        payload={
            "incident_type": "GRAPH_REDUCTION_ISSUE",
            "graph_reduction_issues": issues,
        },
    )


def decide_next_actions(
    snapshot: ProgressionSnapshot,
    policy: ProgressionPolicy,
) -> list[ActionProposal]:
    graph_evaluation = evaluate_progression_graph(snapshot)
    use_structured_graph = _has_structured_graph_input(snapshot)
    in_flight_ticket_ids = (
        graph_evaluation.in_flight_ticket_ids
        if use_structured_graph
        else _stable_unique_strings(snapshot.in_flight_ticket_ids)
    )
    in_flight_node_refs = (
        graph_evaluation.in_flight_node_refs
        if use_structured_graph
        else _stable_unique_strings(snapshot.in_flight_node_refs)
    )

    if snapshot.approvals or snapshot.incidents or in_flight_ticket_ids or in_flight_node_refs:
        return [_wait_proposal(snapshot, policy, graph_evaluation)]

    if graph_evaluation.graph_reduction_issues:
        return [_graph_reduction_issue_proposal(snapshot, policy, graph_evaluation)]

    structured_policy_proposal = _structured_policy_proposal(snapshot, policy)
    if structured_policy_proposal is not None:
        return [structured_policy_proposal]

    if policy.create_ticket_candidates:
        ordered_candidates = sorted(
            policy.create_ticket_candidates,
            key=lambda item: (
                str(item.get("candidate_ref") or ""),
                str(item.get("node_ref") or item.get("node_id") or ""),
            ),
        )
        return [_create_ticket_proposal(snapshot, policy, ordered_candidates[0])]

    return [_no_action_proposal(snapshot, policy, graph_evaluation)]


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
