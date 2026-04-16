from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

from pydantic import ValidationError

from app.contracts.advisory import GraphPatch
from app.core.constants import (
    EVENT_GRAPH_PATCH_APPLIED,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_SUPERSEDED,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
)
from app.db.repository import ControlPlaneRepository

_PATH_EDGE_TYPES = {"PARENT_OF", "DEPENDS_ON"}
_MUTABLE_EDGE_TYPES = {"PARENT_OF", "DEPENDS_ON", "REVIEWS"}


class GraphPatchReducerUnavailableError(RuntimeError):
    pass


def _raise_graph_patch_unavailable(reason: str) -> None:
    raise GraphPatchReducerUnavailableError(f"graph unavailable: {reason}")


@dataclass(frozen=True)
class GraphPatchEventRecord:
    event_id: str
    sequence_no: int
    patch: GraphPatch


@dataclass
class GraphPatchOverlay:
    frozen_node_ids: set[str] = field(default_factory=set)
    focus_node_ids: set[str] = field(default_factory=set)
    node_status_overrides: dict[str, str] = field(default_factory=dict)
    effective_edge_keys: set[tuple[str, str, str]] = field(default_factory=set)


def _load_graph_patch_event_records_with_connection(
    connection,
    *,
    workflow_id: str,
    limit: int | None,
) -> list[GraphPatchEventRecord]:
    if limit is not None:
        rows = list(
            connection.execute(
                """
                SELECT event_id, sequence_no, payload_json
                FROM (
                    SELECT event_id, sequence_no, payload_json
                    FROM events
                    WHERE workflow_id = ? AND event_type = ?
                    ORDER BY sequence_no DESC
                    LIMIT ?
                )
                ORDER BY sequence_no ASC
                """,
                (workflow_id, EVENT_GRAPH_PATCH_APPLIED, limit),
            ).fetchall()
        )
    else:
        rows = list(
            connection.execute(
                """
                SELECT event_id, sequence_no, payload_json
                FROM events
                WHERE workflow_id = ? AND event_type = ?
                ORDER BY sequence_no ASC
                """,
                (workflow_id, EVENT_GRAPH_PATCH_APPLIED),
            ).fetchall()
        )
    records: list[GraphPatchEventRecord] = []
    for row in rows:
        event_id = str(row["event_id"])
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError as exc:
            _raise_graph_patch_unavailable(
                f"graph patch event {event_id} carries invalid JSON: {exc.msg}."
            )
        if not isinstance(payload, dict):
            _raise_graph_patch_unavailable(
                f"graph patch event {event_id} must carry an object payload."
            )
        try:
            patch = GraphPatch.model_validate(payload)
        except ValidationError as exc:
            _raise_graph_patch_unavailable(
                f"graph patch event {event_id} failed validation: {exc.errors()[0]['msg']}."
            )
        records.append(
            GraphPatchEventRecord(
                event_id=event_id,
                sequence_no=int(row["sequence_no"]),
                patch=patch,
            )
        )
    return records


def load_graph_patch_event_records(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    connection=None,
    limit: int | None = None,
) -> list[GraphPatchEventRecord]:
    repository.initialize()
    if connection is not None:
        records = _load_graph_patch_event_records_with_connection(
            connection,
            workflow_id=workflow_id,
            limit=limit,
        )
    else:
        with repository.connection() as owned_connection:
            records = _load_graph_patch_event_records_with_connection(
                owned_connection,
                workflow_id=workflow_id,
                limit=limit,
            )
    if limit is not None and len(records) > limit:
        return records[-limit:]
    return records


def graph_patch_target_node_ids(patch: GraphPatch) -> tuple[str, ...]:
    touched_node_ids = {
        *patch.freeze_node_ids,
        *patch.unfreeze_node_ids,
        *patch.focus_node_ids,
        *patch.remove_node_ids,
        *(item.old_node_id for item in patch.replacements),
        *(item.new_node_id for item in patch.replacements),
        *(item.source_node_id for item in patch.edge_additions),
        *(item.target_node_id for item in patch.edge_additions),
        *(item.source_node_id for item in patch.edge_removals),
        *(item.target_node_id for item in patch.edge_removals),
    }
    return tuple(sorted(node_id for node_id in touched_node_ids if node_id))


def _validate_known_nodes(
    *,
    event_id: str,
    referenced_node_ids: Iterable[str],
    known_node_ids: set[str],
) -> None:
    unknown_node_ids = sorted({node_id for node_id in referenced_node_ids if node_id not in known_node_ids})
    if unknown_node_ids:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} references unknown node ids: {', '.join(unknown_node_ids)}."
        )


def _validate_mutable_node(
    *,
    event_id: str,
    node_id: str,
    operation: str,
    ticket_status_by_node_id: dict[str, str | None],
    node_status_by_node_id: dict[str, str | None],
) -> None:
    ticket_status = str(ticket_status_by_node_id.get(node_id) or "").strip().upper()
    node_status = str(node_status_by_node_id.get(node_id) or "").strip().upper()
    if ticket_status in {TICKET_STATUS_LEASED, TICKET_STATUS_EXECUTING} or node_status == NODE_STATUS_EXECUTING:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} cannot {operation} node {node_id} because it is executing."
        )
    if ticket_status == TICKET_STATUS_COMPLETED or node_status == NODE_STATUS_COMPLETED:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} cannot {operation} node {node_id} because it is completed."
        )
    if ticket_status == TICKET_STATUS_CANCELLED or node_status == NODE_STATUS_CANCELLED:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} cannot {operation} node {node_id} because it is already cancelled."
        )


def _validate_edge_membership(
    *,
    event_id: str,
    edge_key: tuple[str, str, str],
    current_edge_keys: set[tuple[str, str, str]],
    expected_present: bool,
) -> None:
    is_present = edge_key in current_edge_keys
    if expected_present and not is_present:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} cannot remove missing edge {edge_key[0]}:{edge_key[1]}->{edge_key[2]}."
        )
    if not expected_present and is_present:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} cannot add duplicate edge {edge_key[0]}:{edge_key[1]}->{edge_key[2]}."
        )


def _validate_path_dag(
    *,
    event_id: str,
    active_node_ids: set[str],
    edge_keys: set[tuple[str, str, str]],
) -> None:
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in active_node_ids}
    for edge_type, source_node_id, target_node_id in edge_keys:
        if edge_type not in _PATH_EDGE_TYPES:
            continue
        if source_node_id not in active_node_ids or target_node_id not in active_node_ids:
            continue
        if source_node_id == target_node_id:
            continue
        adjacency.setdefault(source_node_id, set()).add(target_node_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            _raise_graph_patch_unavailable(
                f"graph patch event {event_id} would introduce a cycle touching node {node_id}."
            )
        visiting.add(node_id)
        for child_node_id in sorted(adjacency.get(node_id, set())):
            visit(child_node_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(active_node_ids):
        visit(node_id)


def _validate_parent_orphans(
    *,
    event_id: str,
    active_node_ids: set[str],
    edge_keys: set[tuple[str, str, str]],
    allowed_root_node_ids: set[str],
) -> None:
    incoming_parent_edges: dict[str, int] = {node_id: 0 for node_id in active_node_ids}
    for edge_type, _, target_node_id in edge_keys:
        if edge_type != "PARENT_OF" or target_node_id not in active_node_ids:
            continue
        incoming_parent_edges[target_node_id] = incoming_parent_edges.get(target_node_id, 0) + 1
    orphan_node_ids = sorted(
        node_id
        for node_id in active_node_ids
        if incoming_parent_edges.get(node_id, 0) == 0 and node_id not in allowed_root_node_ids
    )
    if orphan_node_ids:
        _raise_graph_patch_unavailable(
            f"graph patch event {event_id} would orphan node ids: {', '.join(orphan_node_ids)}."
        )


def reduce_graph_patch_overlay(
    *,
    patch_records: list[GraphPatchEventRecord],
    known_node_ids: set[str],
    base_edge_keys: set[tuple[str, str, str]],
    ticket_status_by_node_id: dict[str, str | None],
    node_status_by_node_id: dict[str, str | None],
) -> GraphPatchOverlay:
    current_edge_keys = {
        edge_key
        for edge_key in base_edge_keys
        if edge_key[0] in _MUTABLE_EDGE_TYPES
    }
    allowed_root_node_ids = set(known_node_ids)
    for edge_type, _, target_node_id in base_edge_keys:
        if edge_type == "PARENT_OF":
            allowed_root_node_ids.discard(target_node_id)

    overlay = GraphPatchOverlay(effective_edge_keys=set(current_edge_keys))
    inactive_node_ids: set[str] = {
        node_id
        for node_id, node_status in node_status_by_node_id.items()
        if str(node_status or "").strip().upper() in {NODE_STATUS_CANCELLED, NODE_STATUS_SUPERSEDED}
    }
    replacement_edge_keys: set[tuple[str, str, str]] = set()

    for record in patch_records:
        patch = record.patch
        event_id = record.event_id
        _validate_known_nodes(
            event_id=event_id,
            referenced_node_ids=graph_patch_target_node_ids(patch),
            known_node_ids=known_node_ids,
        )
        active_node_ids = set(known_node_ids) - set(inactive_node_ids)
        for node_id in patch.remove_node_ids:
            if node_id not in active_node_ids:
                _raise_graph_patch_unavailable(
                    f"graph patch event {event_id} cannot remove inactive node {node_id}."
                )
            _validate_mutable_node(
                event_id=event_id,
                node_id=node_id,
                operation="remove",
                ticket_status_by_node_id=ticket_status_by_node_id,
                node_status_by_node_id=node_status_by_node_id,
            )
        for replacement in patch.replacements:
            if replacement.old_node_id not in active_node_ids:
                _raise_graph_patch_unavailable(
                    f"graph patch event {event_id} cannot replace inactive node {replacement.old_node_id}."
                )
            if replacement.new_node_id not in active_node_ids:
                _raise_graph_patch_unavailable(
                    f"graph patch event {event_id} cannot promote inactive node {replacement.new_node_id}."
                )
            _validate_mutable_node(
                event_id=event_id,
                node_id=replacement.old_node_id,
                operation="replace",
                ticket_status_by_node_id=ticket_status_by_node_id,
                node_status_by_node_id=node_status_by_node_id,
            )

        inactive_this_patch = {
            *patch.remove_node_ids,
            *(item.old_node_id for item in patch.replacements),
        }
        active_after_patch = active_node_ids - inactive_this_patch

        for edge in [*patch.edge_additions, *patch.edge_removals]:
            if edge.source_node_id not in active_node_ids or edge.target_node_id not in active_node_ids:
                _raise_graph_patch_unavailable(
                    f"graph patch event {event_id} references edge endpoint outside the active graph."
                )
        for edge in patch.edge_additions:
            if edge.source_node_id not in active_after_patch or edge.target_node_id not in active_after_patch:
                _raise_graph_patch_unavailable(
                    f"graph patch event {event_id} cannot add edges that target removed or superseded nodes."
                )

        for edge in patch.edge_removals:
            _validate_edge_membership(
                event_id=event_id,
                edge_key=(edge.edge_type, edge.source_node_id, edge.target_node_id),
                current_edge_keys=current_edge_keys,
                expected_present=True,
            )

        candidate_edge_keys = {
            edge_key
            for edge_key in current_edge_keys
            if edge_key[1] not in inactive_this_patch and edge_key[2] not in inactive_this_patch
        }
        for edge in patch.edge_removals:
            candidate_edge_keys.discard((edge.edge_type, edge.source_node_id, edge.target_node_id))
        for edge in patch.edge_additions:
            edge_key = (edge.edge_type, edge.source_node_id, edge.target_node_id)
            _validate_edge_membership(
                event_id=event_id,
                edge_key=edge_key,
                current_edge_keys=candidate_edge_keys,
                expected_present=False,
            )
            candidate_edge_keys.add(edge_key)

        _validate_path_dag(
            event_id=event_id,
            active_node_ids=active_after_patch,
            edge_keys=candidate_edge_keys,
        )
        _validate_parent_orphans(
            event_id=event_id,
            active_node_ids=active_after_patch,
            edge_keys=candidate_edge_keys,
            allowed_root_node_ids=allowed_root_node_ids,
        )

        inactive_node_ids.update(inactive_this_patch)
        current_edge_keys = candidate_edge_keys
        overlay.effective_edge_keys = set(candidate_edge_keys)

        for node_id in patch.remove_node_ids:
            overlay.node_status_overrides[node_id] = NODE_STATUS_CANCELLED
            overlay.frozen_node_ids.discard(node_id)
            overlay.focus_node_ids.discard(node_id)
        for replacement in patch.replacements:
            overlay.node_status_overrides[replacement.old_node_id] = NODE_STATUS_SUPERSEDED
            overlay.frozen_node_ids.discard(replacement.old_node_id)
            overlay.focus_node_ids.discard(replacement.old_node_id)
            replacement_edge_keys.add(
                ("REPLACES", replacement.new_node_id, replacement.old_node_id)
            )

        overlay.frozen_node_ids.update(
            node_id for node_id in patch.freeze_node_ids if node_id in active_after_patch
        )
        for node_id in patch.unfreeze_node_ids:
            overlay.frozen_node_ids.discard(node_id)
        overlay.focus_node_ids.update(
            node_id for node_id in patch.focus_node_ids if node_id in active_after_patch
        )

    overlay.frozen_node_ids.difference_update(inactive_node_ids)
    overlay.focus_node_ids.difference_update(inactive_node_ids)
    overlay.effective_edge_keys = set(current_edge_keys | replacement_edge_keys)
    return overlay
