from __future__ import annotations

import hashlib
import json

from app.contracts.commands import CommandAckEnvelope, CommandAckStatus, ProjectInitCommand
from app.core.constants import (
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_WORKFLOW_CREATED,
    SYSTEM_INITIALIZED_KEY,
)
from app.core.ids import new_prefixed_id
from app.core.reducer import rebuild_workflow_projections
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _command_base_key(payload: ProjectInitCommand) -> str:
    normalized = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"project-init:{digest}"


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
            repository.replace_workflow_projections(
                connection,
                rebuild_workflow_projections(repository.list_all_events(connection)),
            )
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
            payload=payload.model_dump(mode="json"),
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
            },
            occurred_at=received_at,
        )

        repository.replace_workflow_projections(
            connection,
            rebuild_workflow_projections(repository.list_all_events(connection)),
        )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=command_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"workflow:{workflow_id}",
    )
