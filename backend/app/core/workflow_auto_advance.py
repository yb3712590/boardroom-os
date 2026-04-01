from __future__ import annotations

from app.config import get_settings
from app.core.runtime import run_leased_ticket_runtime
from app.core.ticket_handlers import run_scheduler_tick
from app.db.repository import ControlPlaneRepository


def workflow_has_open_approval(
    repository: ControlPlaneRepository,
    workflow_id: str,
) -> bool:
    return any(approval["workflow_id"] == workflow_id for approval in repository.list_open_approvals())


def workflow_has_open_incident(
    repository: ControlPlaneRepository,
    workflow_id: str,
) -> bool:
    return any(incident["workflow_id"] == workflow_id for incident in repository.list_open_incidents())


def auto_advance_workflow_to_next_stop(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    idempotency_key_prefix: str,
    max_steps: int,
    max_dispatches: int | None = None,
) -> None:
    settings = get_settings()
    effective_max_dispatches = max_dispatches or settings.scheduler_max_dispatches
    for step_index in range(max_steps):
        if workflow_has_open_approval(repository, workflow_id) or workflow_has_open_incident(
            repository,
            workflow_id,
        ):
            return

        _, version_before = repository.get_cursor_and_version()
        run_scheduler_tick(
            repository,
            idempotency_key=f"{idempotency_key_prefix}:{step_index}:scheduler",
            max_dispatches=effective_max_dispatches,
        )
        run_leased_ticket_runtime(repository)
        _, version_after = repository.get_cursor_and_version()

        if workflow_has_open_approval(repository, workflow_id) or workflow_has_open_incident(
            repository,
            workflow_id,
        ):
            return
        if version_after == version_before:
            return
