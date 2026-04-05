from __future__ import annotations

import sqlite3
from datetime import datetime

from app.contracts.commands import (
    ArtifactCleanupCommand,
    ArtifactDeleteCommand,
    CommandAckEnvelope,
    CommandAckStatus,
    TicketArtifactImportUploadCommand,
)
from app.core.artifact_store import ArtifactStore
from app.core.artifacts import (
    ARTIFACT_LIFECYCLE_ACTIVE,
    ARTIFACT_LIFECYCLE_DELETED,
    ARTIFACT_LIFECYCLE_EXPIRED,
    resolve_artifact_lifecycle_status,
)
from app.core.constants import (
    EVENT_ARTIFACT_CLEANUP_COMPLETED,
    EVENT_ARTIFACT_DELETED,
    EVENT_ARTIFACT_EXPIRED,
    EVENT_ARTIFACT_IMPORTED,
    NODE_STATUS_EXECUTING,
    TICKET_STATUS_EXECUTING,
)
from app.core.ids import new_prefixed_id
from app.core.ticket_artifacts import (
    cleanup_materialized_artifacts,
    match_allowed_write_set,
    prepare_imported_upload_artifact,
    save_prepared_artifact_record,
)
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _artifact_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    status: CommandAckStatus,
    artifact_ref: str,
    reason: str | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=status,
        received_at=received_at,
        reason=reason,
        causation_hint=f"artifact:{artifact_ref}",
    )


def _cleanup_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    status: CommandAckStatus,
    reason: str | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=status,
        received_at=received_at,
        reason=reason,
        causation_hint="artifact:cleanup",
    )


def handle_ticket_artifact_import_upload(
    repository: ControlPlaneRepository,
    payload: TicketArtifactImportUploadCommand,
    artifact_store: ArtifactStore | None = None,
    *,
    imported_by: str = "local_api",
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    resolved_artifact_store = artifact_store or repository.artifact_store
    materialized_artifacts = []

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.DUPLICATE,
                artifact_ref=payload.artifact_ref,
                reason="An identical ticket-artifact-import-upload command was already accepted.",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason="Ticket must exist before importing an uploaded artifact.",
            )
        if current_node.get("latest_ticket_id") != payload.ticket_id:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason="Node projection no longer points at this ticket.",
            )
        if (
            current_ticket.get("workflow_id") != payload.workflow_id
            or current_ticket.get("node_id") != payload.node_id
        ):
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if (
            current_ticket.get("status") != TICKET_STATUS_EXECUTING
            or current_node.get("status") != NODE_STATUS_EXECUTING
        ):
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason=(
                    f"Ticket {payload.ticket_id} can only import uploaded artifacts while ticket/node "
                    f"status is EXECUTING/EXECUTING; current status is "
                    f"{current_ticket.get('status')}/{current_node.get('status')}."
                ),
            )

        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)
        if created_spec is None:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason="Ticket create spec is missing for uploaded artifact import.",
            )
        allowed_write_set = list(created_spec.get("allowed_write_set") or [])
        if not match_allowed_write_set(payload.path, allowed_write_set):
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason="Uploaded artifact path is outside the allowed write set.",
            )
        if repository.get_artifact_by_ref(payload.artifact_ref, connection=connection) is not None:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason=f"Artifact {payload.artifact_ref} already exists.",
            )

        try:
            prepared_artifact, materialized_artifact = prepare_imported_upload_artifact(
                repository=repository,
                artifact_store=resolved_artifact_store,
                artifact_ref=payload.artifact_ref,
                path=payload.path,
                kind=payload.kind,
                media_type=payload.media_type,
                upload_session_id=payload.upload_session_id,
                retention_class=payload.retention_class,
                retention_ttl_sec=payload.retention_ttl_sec,
                created_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
            )
            materialized_artifacts.append(materialized_artifact)
            consumed = repository.consume_artifact_upload_session(
                connection,
                session_id=payload.upload_session_id,
                consumed_at=received_at,
                consumed_by_artifact_ref=payload.artifact_ref,
            )
            if not consumed:
                raise ValueError(
                    f"Artifact upload session '{payload.upload_session_id}' is not available for consumption."
                )
            save_prepared_artifact_record(
                repository,
                connection,
                prepared_artifact=prepared_artifact,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                created_at=received_at,
            )
            event_row = repository.insert_event(
                connection,
                event_type=EVENT_ARTIFACT_IMPORTED,
                actor_type="worker" if imported_by != "local_api" else "operator",
                actor_id=imported_by,
                workflow_id=payload.workflow_id,
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=payload.workflow_id,
                payload={
                    "ticket_id": payload.ticket_id,
                    "node_id": payload.node_id,
                    "artifact_ref": payload.artifact_ref,
                    "logical_path": payload.path,
                    "upload_session_id": payload.upload_session_id,
                },
                occurred_at=received_at,
            )
            if event_row is None:
                return _artifact_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    status=CommandAckStatus.DUPLICATE,
                    artifact_ref=payload.artifact_ref,
                    reason="An identical ticket-artifact-import-upload command was already accepted.",
                )
            repository.refresh_projections(connection)
        except ValueError as exc:
            cleanup_materialized_artifacts(resolved_artifact_store, materialized_artifacts)
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason=str(exc),
            )
        except sqlite3.IntegrityError:
            cleanup_materialized_artifacts(resolved_artifact_store, materialized_artifacts)
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason="Artifact ref already exists in artifact index.",
            )
        except Exception:
            cleanup_materialized_artifacts(resolved_artifact_store, materialized_artifacts)
            raise

    return _artifact_ack(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        received_at=received_at,
        status=CommandAckStatus.ACCEPTED,
        artifact_ref=payload.artifact_ref,
    )


def handle_artifact_delete(
    repository: ControlPlaneRepository,
    payload: ArtifactDeleteCommand,
    artifact_store: ArtifactStore | None = None,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    resolved_artifact_store = artifact_store or repository.artifact_store

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.DUPLICATE,
                artifact_ref=payload.artifact_ref,
                reason="An identical artifact-delete command was already accepted.",
            )

        artifact = repository.get_artifact_by_ref(payload.artifact_ref, connection=connection)
        if artifact is None:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason=f"Artifact {payload.artifact_ref} was not found.",
            )

        lifecycle_status = resolve_artifact_lifecycle_status(artifact, at=received_at)
        if lifecycle_status == ARTIFACT_LIFECYCLE_DELETED:
            return _artifact_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.REJECTED,
                artifact_ref=payload.artifact_ref,
                reason=f"Artifact {payload.artifact_ref} is already deleted.",
            )

        if resolved_artifact_store is not None and (
            artifact.get("storage_relpath") or artifact.get("storage_object_key")
        ):
            try:
                resolved_artifact_store.delete(
                    str(artifact["storage_relpath"]) if artifact.get("storage_relpath") else None,
                    storage_object_key=(
                        str(artifact["storage_object_key"])
                        if artifact.get("storage_object_key")
                        else None
                    ),
                )
                repository.mark_artifact_storage_deleted(
                    connection,
                    artifact_ref=payload.artifact_ref,
                    storage_deleted_at=received_at,
                )
            except Exception as exc:
                repository.mark_artifact_storage_delete_failed(
                    connection,
                    artifact_ref=payload.artifact_ref,
                    error_message=str(exc),
                )
                return _artifact_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    status=CommandAckStatus.REJECTED,
                    artifact_ref=payload.artifact_ref,
                    reason=f"Artifact storage delete failed: {exc}",
                )

        repository.update_artifact_lifecycle(
            connection,
            artifact_ref=payload.artifact_ref,
            lifecycle_status=ARTIFACT_LIFECYCLE_DELETED,
            deleted_at=received_at,
            deleted_by=payload.deleted_by,
            delete_reason=payload.reason,
        )
        inserted = repository.insert_event(
            connection,
            event_type=EVENT_ARTIFACT_DELETED,
            actor_type="operator",
            actor_id=payload.deleted_by,
            workflow_id=artifact["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=artifact["workflow_id"],
            payload={
                "artifact_ref": payload.artifact_ref,
                "ticket_id": artifact["ticket_id"],
                "node_id": artifact["node_id"],
                "logical_path": artifact["logical_path"],
                "deleted_by": payload.deleted_by,
                "reason": payload.reason,
            },
            occurred_at=received_at,
        )
        if inserted is None:
            raise RuntimeError("Artifact delete idempotency conflict.")

    return _artifact_ack(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        received_at=received_at,
        status=CommandAckStatus.ACCEPTED,
        artifact_ref=payload.artifact_ref,
    )


def handle_artifact_cleanup(
    repository: ControlPlaneRepository,
    payload: ArtifactCleanupCommand,
    artifact_store: ArtifactStore | None = None,
    *,
    trigger: str = "manual_command",
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    resolved_artifact_store = artifact_store or repository.artifact_store

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _cleanup_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                status=CommandAckStatus.DUPLICATE,
                reason="An identical artifact-cleanup command was already accepted.",
            )

        artifacts = repository.list_artifacts_for_cleanup(connection, expires_before=received_at)
        expired_count = 0
        storage_deleted_count = 0
        already_cleared_count = 0
        delete_failed_count = 0

        for artifact in artifacts:
            lifecycle_status = resolve_artifact_lifecycle_status(artifact, at=received_at)

            if lifecycle_status == ARTIFACT_LIFECYCLE_EXPIRED and artifact.get("lifecycle_status") == ARTIFACT_LIFECYCLE_ACTIVE:
                expired_count += 1
                repository.update_artifact_lifecycle(
                    connection,
                    artifact_ref=str(artifact["artifact_ref"]),
                    lifecycle_status=ARTIFACT_LIFECYCLE_EXPIRED,
                    deleted_at=received_at,
                    deleted_by=payload.cleaned_by,
                    delete_reason="Expired by artifact cleanup.",
                )
                inserted = repository.insert_event(
                    connection,
                    event_type=EVENT_ARTIFACT_EXPIRED,
                    actor_type="operator",
                    actor_id=payload.cleaned_by,
                    workflow_id=artifact["workflow_id"],
                    idempotency_key=f"{payload.idempotency_key}:{artifact['artifact_ref']}:expired",
                    causation_id=command_id,
                    correlation_id=artifact["workflow_id"],
                    payload={
                        "artifact_ref": artifact["artifact_ref"],
                        "ticket_id": artifact["ticket_id"],
                        "node_id": artifact["node_id"],
                        "logical_path": artifact["logical_path"],
                        "cleaned_by": payload.cleaned_by,
                    },
                    occurred_at=received_at,
                )
                if inserted is None:
                    raise RuntimeError("Artifact expiry idempotency conflict.")
                if artifact.get("materialization_status") == "MATERIALIZED":
                    repository.mark_artifact_storage_delete_pending(
                        connection,
                        artifact_ref=str(artifact["artifact_ref"]),
                    )

            if artifact.get("storage_delete_status") == "DELETED":
                already_cleared_count += 1
                continue

            if resolved_artifact_store is not None and (
                artifact.get("storage_relpath") or artifact.get("storage_object_key")
            ):
                try:
                    resolved_artifact_store.delete(
                        str(artifact["storage_relpath"]) if artifact.get("storage_relpath") else None,
                        storage_object_key=(
                            str(artifact["storage_object_key"])
                            if artifact.get("storage_object_key")
                            else None
                        ),
                    )
                    repository.mark_artifact_storage_deleted(
                        connection,
                        artifact_ref=str(artifact["artifact_ref"]),
                        storage_deleted_at=received_at,
                    )
                    storage_deleted_count += 1
                except Exception as exc:
                    repository.mark_artifact_storage_delete_failed(
                        connection,
                        artifact_ref=str(artifact["artifact_ref"]),
                        error_message=str(exc),
                    )
                    delete_failed_count += 1
            elif artifact.get("storage_deleted_at") is not None:
                already_cleared_count += 1

        inserted = repository.insert_event(
            connection,
            event_type=EVENT_ARTIFACT_CLEANUP_COMPLETED,
            actor_type="operator",
            actor_id=payload.cleaned_by,
            workflow_id=None,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id="artifact-cleanup",
            payload={
                "cleaned_by": payload.cleaned_by,
                "trigger": trigger,
                "expired_count": expired_count,
                "storage_deleted_count": storage_deleted_count,
                "already_cleared_count": already_cleared_count,
                "delete_failed_count": delete_failed_count,
            },
            occurred_at=received_at,
        )
        if inserted is None:
            raise RuntimeError("Artifact cleanup idempotency conflict.")

    return _cleanup_ack(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        received_at=received_at,
        status=CommandAckStatus.ACCEPTED,
    )
