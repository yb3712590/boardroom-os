from __future__ import annotations

from datetime import datetime

from app.contracts.commands import (
    ArtifactCleanupCommand,
    ArtifactDeleteCommand,
    CommandAckEnvelope,
    CommandAckStatus,
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
)
from app.core.ids import new_prefixed_id
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
