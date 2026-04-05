from __future__ import annotations

import hashlib
import json

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    ProjectInitCommand,
)
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED, EVENT_SYSTEM_INITIALIZED, EVENT_WORKFLOW_CREATED, SYSTEM_INITIALIZED_KEY
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_project_init_scope_ticket_id,
)
from app.core.ceo_scheduler import run_ceo_shadow_for_trigger
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.core.workflow_scope import default_workflow_scope
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from app.db.repository import ControlPlaneRepository

PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS = 6


def _command_base_key(payload: ProjectInitCommand) -> str:
    normalized = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"project-init:{digest}"


def _create_project_init_brief_artifact(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    payload: ProjectInitCommand,
) -> str:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise RuntimeError("Artifact store is required to create the project-init brief artifact.")

    artifact_ref = f"art://project-init/{workflow_id}/board-brief.md"
    logical_path = f"inputs/project-init/{workflow_id}/board-brief.md"
    deadline = payload.deadline_at.isoformat() if payload.deadline_at is not None else "None"
    content = "\n".join(
        [
            f"# Board Brief for {workflow_id}",
            "",
            f"- North star goal: {payload.north_star_goal}",
            f"- Budget cap: {payload.budget_cap}",
            f"- Deadline: {deadline}",
            "",
            "## Hard constraints",
            *(f"- {constraint}" for constraint in payload.hard_constraints),
            "",
        ]
    )
    materialized = artifact_store.materialize_text(
        logical_path,
        content,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        media_type="text/markdown",
    )
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=PROJECT_INIT_SCOPE_NODE_ID,
            logical_path=logical_path,
            kind="MARKDOWN",
            media_type="text/markdown",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_backend=materialized.storage_backend,
            storage_relpath=materialized.storage_relpath,
            storage_object_key=materialized.storage_object_key,
            storage_delete_status=materialized.storage_delete_status,
            storage_delete_error=None,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="PERSISTENT",
            retention_class_source="explicit",
            retention_ttl_sec=None,
            retention_policy_source="explicit_class",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=now_local(),
    )
    return artifact_ref


def _auto_advance_project_init_to_first_review(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    command_key: str,
) -> None:
    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix=f"{command_key}:auto-advance",
        max_steps=PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS,
    )


def handle_project_init(
    repository: ControlPlaneRepository,
    payload: ProjectInitCommand,
) -> CommandAckEnvelope:
    repository.initialize()

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    command_key = _command_base_key(payload)
    workflow_event_key = f"{command_key}:workflow-created"
    directive_event_key = f"{command_key}:board-directive"

    with repository.transaction() as connection:
        tenant_id, workspace_id = default_workflow_scope()
        repository.insert_event(
            connection,
            event_type=EVENT_SYSTEM_INITIALIZED,
            actor_type="system",
            actor_id="system",
            workflow_id=None,
            idempotency_key=SYSTEM_INITIALIZED_KEY,
            causation_id=None,
            correlation_id=None,
            payload={"status": "initialized"},
            occurred_at=received_at,
        )

        existing_workflow_event = repository.get_event_by_idempotency_key(
            connection,
            workflow_event_key,
        )
        if existing_workflow_event is not None:
            repository.refresh_projections(connection)
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=command_key,
                status=CommandAckStatus.DUPLICATE,
                received_at=received_at,
                reason="An identical project-init command was already accepted.",
                causation_hint=f"workflow:{existing_workflow_event['workflow_id']}",
            )

        workflow_id = new_prefixed_id("wf")
        repository.insert_event(
            connection,
            event_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
            actor_type="board",
            actor_id="board",
            workflow_id=workflow_id,
            idempotency_key=directive_event_key,
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                **payload.model_dump(mode="json"),
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            },
            occurred_at=received_at,
        )
        repository.insert_event(
            connection,
            event_type=EVENT_WORKFLOW_CREATED,
            actor_type="system",
            actor_id="system",
            workflow_id=workflow_id,
            idempotency_key=workflow_event_key,
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                **payload.model_dump(mode="json"),
                "title": payload.north_star_goal,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            },
            occurred_at=received_at,
        )

        repository.refresh_projections(connection)

    _create_project_init_brief_artifact(
        repository,
        workflow_id=workflow_id,
        ticket_id=build_project_init_scope_ticket_id(workflow_id),
        payload=payload,
    )
    run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
        trigger_ref=f"project-init:{workflow_id}",
    )
    _auto_advance_project_init_to_first_review(
        repository,
        workflow_id=workflow_id,
        command_key=command_key,
    )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=command_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"workflow:{workflow_id}",
    )
