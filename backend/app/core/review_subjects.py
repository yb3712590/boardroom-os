from __future__ import annotations

from typing import Any, Mapping

from app.core.graph_identity import (
    GraphIdentityResolutionError,
    apply_legacy_graph_contract_compat,
    resolve_ticket_graph_identity,
)
from app.db.repository import ControlPlaneRepository


class ReviewSubjectResolutionError(RuntimeError):
    pass


def resolve_review_subject_identity(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    subject: Mapping[str, Any] | None,
    connection=None,
) -> tuple[str | None, str | None, str | None]:
    if connection is None:
        with repository.connection() as owned_connection:
            return resolve_review_subject_identity(
                repository,
                workflow_id=workflow_id,
                subject=subject,
                connection=owned_connection,
            )
    normalized_subject = dict(subject or {})
    source_ticket_id = str(normalized_subject.get("source_ticket_id") or "").strip() or None
    source_graph_node_id = str(normalized_subject.get("source_graph_node_id") or "").strip() or None
    source_node_id = str(normalized_subject.get("source_node_id") or "").strip() or None
    if source_graph_node_id:
        return source_ticket_id, source_graph_node_id, source_node_id

    if source_ticket_id:
        created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id) or {}
        created_spec = apply_legacy_graph_contract_compat(created_spec)
        runtime_node_id = source_node_id
        if not runtime_node_id:
            ticket_projection = repository.get_current_ticket_projection(source_ticket_id, connection=connection)
            runtime_node_id = (
                str(ticket_projection.get("node_id") or "").strip()
                if ticket_projection is not None
                else None
            )
        try:
            identity = resolve_ticket_graph_identity(
                ticket_id=source_ticket_id,
                created_spec=created_spec,
                runtime_node_id=runtime_node_id,
            )
        except GraphIdentityResolutionError as exc:
            raise ReviewSubjectResolutionError(
                f"review subject for workflow {workflow_id} cannot resolve source_graph_node_id: {exc}"
            ) from exc
        return source_ticket_id, identity.graph_node_id, source_node_id or identity.runtime_node_id

    if source_node_id:
        return None, source_node_id, source_node_id

    raise ReviewSubjectResolutionError(
        f"review subject for workflow {workflow_id} is missing source_graph_node_id and stable compat identifiers."
    )
