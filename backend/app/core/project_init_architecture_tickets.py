from __future__ import annotations

from typing import Any

from app.core.ceo_execution_presets import build_project_init_architecture_brief_ticket_specs
from app.core.constants import EVENT_TICKET_CREATED
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.time import now_local
from app.core.workflow_scope import default_workflow_scope
from app.db.repository import ControlPlaneRepository


def insert_project_init_architecture_tickets(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    workflow_profile: str,
    north_star_goal: str,
    board_brief_artifact_ref: str,
    command_id: str,
    command_key: str,
    occurred_at: Any | None = None,
) -> None:
    specs = build_project_init_architecture_brief_ticket_specs(
        {
            "workflow_id": workflow_id,
            "workflow_profile": workflow_profile,
            "north_star_goal": north_star_goal,
            "title": north_star_goal,
        },
        board_brief_artifact_ref=board_brief_artifact_ref,
    )
    event_time = occurred_at or now_local()
    with repository.transaction() as connection:
        workflow = repository.get_workflow_projection(workflow_id, connection=connection)
        tenant_id, workspace_id = default_workflow_scope()
        if workflow is not None:
            tenant_id = str(workflow.get("tenant_id") or tenant_id)
            workspace_id = str(workflow.get("workspace_id") or workspace_id)
        for spec in specs:
            repository.insert_event(
                connection,
                event_type=EVENT_TICKET_CREATED,
                actor_type="system",
                actor_id="system",
                workflow_id=workflow_id,
                idempotency_key=f"{command_key}:ticket-created:{spec['ticket_id']}",
                causation_id=command_id,
                correlation_id=workflow_id,
                payload={
                    **spec,
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                },
                occurred_at=event_time,
            )
        repository.refresh_projections(connection)
        build_ticket_graph_snapshot(repository, workflow_id, connection=connection)
