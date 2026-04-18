from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from app.core.graph_identity import (
    GraphIdentityResolutionError,
    apply_legacy_graph_contract_compat,
    is_review_graph_node_id,
    resolve_ticket_graph_identity,
)
if TYPE_CHECKING:
    from app.db.repository import ControlPlaneRepository


class ReviewSubjectResolutionError(RuntimeError):
    pass


def resolve_execution_graph_target(
    *,
    source_graph_node_id: str,
    source_node_id: str | None,
) -> tuple[str, str]:
    normalized_graph_node_id = str(source_graph_node_id or "").strip()
    if not normalized_graph_node_id:
        raise ReviewSubjectResolutionError("review subject is missing source_graph_node_id.")
    if is_review_graph_node_id(normalized_graph_node_id):
        execution_graph_node_id = normalized_graph_node_id[: -len("::review")].strip()
        if not execution_graph_node_id:
            raise ReviewSubjectResolutionError(
                f"review subject graph node {normalized_graph_node_id} cannot resolve its execution lane target."
            )
        return execution_graph_node_id, execution_graph_node_id
    return normalized_graph_node_id, normalized_graph_node_id


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

    raise ReviewSubjectResolutionError(
        f"review subject for workflow {workflow_id} is missing source_graph_node_id and stable compat identifiers."
    )


def resolve_review_subject_execution_identity(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    subject: Mapping[str, Any] | None,
    connection=None,
) -> tuple[str | None, str, str]:
    source_ticket_id, source_graph_node_id, source_node_id = resolve_review_subject_identity(
        repository,
        workflow_id=workflow_id,
        subject=subject,
        connection=connection,
    )
    if source_graph_node_id is None:
        raise ReviewSubjectResolutionError(
            f"review subject for workflow {workflow_id} is missing source_graph_node_id."
        )
    execution_graph_node_id, execution_node_id = resolve_execution_graph_target(
        source_graph_node_id=source_graph_node_id,
        source_node_id=source_node_id,
    )
    return source_ticket_id, execution_graph_node_id, execution_node_id
