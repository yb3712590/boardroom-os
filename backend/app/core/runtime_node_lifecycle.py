from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.runtime_node_views import (
    MATERIALIZATION_STATE_MATERIALIZED,
    MATERIALIZATION_STATE_MISSING,
    MATERIALIZATION_STATE_PLANNED,
    RuntimeNodeView,
    RuntimeNodeViewResolutionError,
    resolve_runtime_node_view,
)

if TYPE_CHECKING:
    import sqlite3

    from app.contracts.ticket_graph import TicketGraphSnapshot
    from app.db.repository import ControlPlaneRepository


REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED = "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
REASON_CODE_RUNTIME_NODE_MISSING = "RUNTIME_NODE_MISSING"
REASON_CODE_RUNTIME_NODE_TRUTH_CONFLICT = "RUNTIME_NODE_TRUTH_CONFLICT"


def build_runtime_node_lifecycle_reason(
    *,
    workflow_id: str,
    node_id: str,
    reason_code: str,
    operation: str,
    detail: str | None = None,
) -> str:
    normalized_workflow_id = str(workflow_id or "").strip() or "<unknown-workflow>"
    normalized_node_id = str(node_id or "").strip() or "<unknown-node>"
    normalized_operation = str(operation or "").strip() or "runtime-node-lifecycle"
    if reason_code == REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED:
        return (
            f"{reason_code}: runtime node {normalized_node_id} in workflow {normalized_workflow_id} "
            f"is still a planned placeholder during {normalized_operation}; create a real ticket "
            "for this node before continuing."
        )
    if reason_code == REASON_CODE_RUNTIME_NODE_MISSING:
        return (
            f"{reason_code}: runtime node {normalized_node_id} in workflow {normalized_workflow_id} "
            f"is missing during {normalized_operation}."
        )
    base = (
        f"{reason_code}: runtime node truth is inconsistent for {normalized_node_id} "
        f"in workflow {normalized_workflow_id} during {normalized_operation}."
    )
    if detail:
        return f"{base} {detail}"
    return base


class RuntimeNodeLifecycleError(RuntimeError):
    def __init__(
        self,
        *,
        workflow_id: str,
        node_id: str,
        reason_code: str,
        operation: str,
        detail: str | None = None,
    ) -> None:
        self.workflow_id = str(workflow_id or "").strip()
        self.node_id = str(node_id or "").strip()
        self.reason_code = str(reason_code or "").strip()
        self.operation = str(operation or "").strip()
        self.detail = str(detail or "").strip() or None
        super().__init__(
            build_runtime_node_lifecycle_reason(
                workflow_id=self.workflow_id,
                node_id=self.node_id,
                reason_code=self.reason_code,
                operation=self.operation,
                detail=self.detail,
            )
        )


def resolve_runtime_node_lifecycle(
    repository: "ControlPlaneRepository",
    workflow_id: str,
    node_id: str,
    *,
    graph_snapshot: "TicketGraphSnapshot" | None = None,
    connection: "sqlite3.Connection" | None = None,
) -> RuntimeNodeView:
    try:
        return resolve_runtime_node_view(
            repository,
            workflow_id,
            node_id,
            graph_snapshot=graph_snapshot,
            connection=connection,
        )
    except RuntimeNodeViewResolutionError as exc:
        raise RuntimeNodeLifecycleError(
            workflow_id=workflow_id,
            node_id=node_id,
            reason_code=REASON_CODE_RUNTIME_NODE_TRUTH_CONFLICT,
            operation="runtime-node-lifecycle-resolve",
            detail=str(exc),
        ) from exc


def require_materialized_runtime_node(
    repository: "ControlPlaneRepository",
    workflow_id: str,
    node_id: str,
    *,
    operation: str,
    graph_snapshot: "TicketGraphSnapshot" | None = None,
    connection: "sqlite3.Connection" | None = None,
) -> RuntimeNodeView:
    node_view = resolve_runtime_node_lifecycle(
        repository,
        workflow_id,
        node_id,
        graph_snapshot=graph_snapshot,
        connection=connection,
    )
    if node_view.materialization_state == MATERIALIZATION_STATE_MATERIALIZED:
        return node_view
    if node_view.materialization_state == MATERIALIZATION_STATE_PLANNED:
        raise RuntimeNodeLifecycleError(
            workflow_id=workflow_id,
            node_id=node_id,
            reason_code=REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED,
            operation=operation,
        )
    raise RuntimeNodeLifecycleError(
        workflow_id=workflow_id,
        node_id=node_id,
        reason_code=REASON_CODE_RUNTIME_NODE_MISSING,
        operation=operation,
    )


__all__ = [
    "REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED",
    "REASON_CODE_RUNTIME_NODE_MISSING",
    "REASON_CODE_RUNTIME_NODE_TRUTH_CONFLICT",
    "RuntimeNodeLifecycleError",
    "build_runtime_node_lifecycle_reason",
    "require_materialized_runtime_node",
    "resolve_runtime_node_lifecycle",
    "MATERIALIZATION_STATE_MATERIALIZED",
    "MATERIALIZATION_STATE_MISSING",
    "MATERIALIZATION_STATE_PLANNED",
]
