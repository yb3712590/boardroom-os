from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

GRAPH_LANE_EXECUTION = "execution"
GRAPH_LANE_REVIEW = "review"
_REVIEW_SUFFIX = "::review"


class GraphIdentityResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TicketGraphIdentity:
    ticket_id: str
    runtime_node_id: str
    graph_node_id: str
    graph_lane_kind: str


def build_review_graph_node_id(runtime_node_id: str) -> str:
    normalized = str(runtime_node_id or "").strip()
    if not normalized:
        raise GraphIdentityResolutionError("graph identity requires a non-empty runtime node id.")
    return f"{normalized}{_REVIEW_SUFFIX}"


def is_review_graph_node_id(node_id: str) -> bool:
    return str(node_id or "").strip().endswith(_REVIEW_SUFFIX)


def _resolve_graph_contract_lane_kind(created_spec: dict[str, Any]) -> str | None:
    graph_contract = created_spec.get("graph_contract")
    if not isinstance(graph_contract, dict):
        return None
    lane_kind = str(graph_contract.get("lane_kind") or "").strip().lower()
    if lane_kind in {GRAPH_LANE_EXECUTION, GRAPH_LANE_REVIEW}:
        return lane_kind
    if lane_kind:
        raise GraphIdentityResolutionError(f"unsupported graph lane kind {lane_kind}.")
    return None
def resolve_graph_lane_kind(created_spec: dict[str, Any] | None) -> str:
    created_spec = created_spec or {}
    graph_contract_lane_kind = _resolve_graph_contract_lane_kind(created_spec)
    if graph_contract_lane_kind is not None:
        return graph_contract_lane_kind
    raise GraphIdentityResolutionError("graph identity requires graph_contract.lane_kind.")


def resolve_ticket_graph_identity(
    *,
    ticket_id: str,
    created_spec: dict[str, Any] | None,
    runtime_node_id: str | None = None,
) -> TicketGraphIdentity:
    created_spec = created_spec or {}
    normalized_ticket_id = str(ticket_id or "").strip()
    normalized_runtime_node_id = str(
        runtime_node_id or created_spec.get("node_id") or ""
    ).strip()
    if not normalized_ticket_id:
        raise GraphIdentityResolutionError("graph identity requires a non-empty ticket id.")
    if not normalized_runtime_node_id:
        raise GraphIdentityResolutionError(
            f"ticket {normalized_ticket_id} is missing its runtime node id."
        )
    graph_lane_kind = resolve_graph_lane_kind(created_spec)
    graph_node_id = (
        build_review_graph_node_id(normalized_runtime_node_id)
        if graph_lane_kind == GRAPH_LANE_REVIEW
        else normalized_runtime_node_id
    )
    return TicketGraphIdentity(
        ticket_id=normalized_ticket_id,
        runtime_node_id=normalized_runtime_node_id,
        graph_node_id=graph_node_id,
        graph_lane_kind=graph_lane_kind,
    )


def ensure_patch_targets_are_execution_node_ids(
    *,
    event_id: str,
    referenced_node_ids: Iterable[str],
    known_execution_node_ids: set[str],
) -> None:
    synthetic_review_lane_ids = sorted(
        {
            str(node_id).strip()
            for node_id in referenced_node_ids
            if is_review_graph_node_id(str(node_id).strip())
        }
    )
    if synthetic_review_lane_ids:
        raise GraphIdentityResolutionError(
            f"graph patch event {event_id} cannot target synthetic review lane ids: "
            f"{', '.join(synthetic_review_lane_ids)}."
        )
    unknown_execution_node_ids = sorted(
        {
            str(node_id).strip()
            for node_id in referenced_node_ids
            if str(node_id).strip() and str(node_id).strip() not in known_execution_node_ids
        }
    )
    if unknown_execution_node_ids:
        raise GraphIdentityResolutionError(
            f"graph patch event {event_id} references unknown execution node ids: "
            f"{', '.join(unknown_execution_node_ids)}."
        )
