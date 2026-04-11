from __future__ import annotations

from app.contracts.commands import IncidentFollowupAction, IncidentResolveCommand
from app.config import get_settings
from app.core.ceo_scheduler import SCHEDULER_IDLE_MAINTENANCE_TRIGGER
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.constants import (
    EVENT_TICKET_FAILED,
    INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
    INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
    INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
    INCIDENT_TYPE_STAFFING_CONTAINMENT,
    PROVIDER_PAUSE_FAILURE_KINDS,
)
from app.core.runtime import run_leased_ticket_runtime
from app.core.ticket_handlers import run_scheduler_tick
from app.core.workflow_controller import workflow_controller_effect
from app.core.workflow_autopilot import ensure_workflow_atomic_chain_report, workflow_uses_ceo_board_delegate
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


def _maybe_auto_resolve_open_approval(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    idempotency_key_prefix: str,
    step_index: int,
) -> bool:
    workflow = repository.get_workflow_projection(workflow_id)
    if not workflow_uses_ceo_board_delegate(workflow):
        return False

    approval = next(
        (item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id),
        None,
    )
    if approval is None:
        return False

    from app.core.approval_handlers import handle_ceo_delegate_approve

    ack = handle_ceo_delegate_approve(
        repository,
        approval,
        idempotency_key_prefix=f"{idempotency_key_prefix}:{step_index}:ceo-delegate-approve",
    )
    return ack.status.value in {"ACCEPTED", "DUPLICATE"}


def _provider_incident_should_retry_source_ticket(
    repository: ControlPlaneRepository,
    incident: dict[str, object],
) -> bool:
    ticket_id = str(incident.get("ticket_id") or "").strip()
    if not ticket_id:
        return False

    with repository.connection() as connection:
        latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
    if latest_terminal_event is None:
        return False
    if latest_terminal_event["event_type"] != EVENT_TICKET_FAILED:
        return False
    failure_kind = str((latest_terminal_event.get("payload") or {}).get("failure_kind") or "")
    return failure_kind in PROVIDER_PAUSE_FAILURE_KINDS


def _recommended_incident_followup_action(
    repository: ControlPlaneRepository,
    incident: dict[str, object],
) -> IncidentFollowupAction:
    incident_type = str(incident.get("incident_type") or "")
    if incident_type == INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION:
        return IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT
    if incident_type == INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
        return IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE
    if incident_type == INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
        if _provider_incident_should_retry_source_ticket(repository, incident):
            return IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE
        return IncidentFollowupAction.RESTORE_ONLY
    if incident_type == INCIDENT_TYPE_STAFFING_CONTAINMENT:
        return IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT
    return IncidentFollowupAction.RESTORE_ONLY


def _maybe_auto_resolve_open_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    idempotency_key_prefix: str,
    step_index: int,
) -> bool:
    workflow = repository.get_workflow_projection(workflow_id)
    if not workflow_uses_ceo_board_delegate(workflow):
        return False

    incident = next(
        (item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id),
        None,
    )
    if incident is None:
        return False

    from app.core.ticket_handlers import handle_incident_resolve

    incident_id = str(incident["incident_id"])
    ack = handle_incident_resolve(
        repository,
        IncidentResolveCommand(
            incident_id=incident_id,
            resolved_by="ceo_delegate",
            resolution_summary="CEO 自动恢复当前 incident，并重试最近失败任务，保持主线继续执行。",
            followup_action=_recommended_incident_followup_action(repository, incident),
            idempotency_key=(
                f"{idempotency_key_prefix}:{step_index}:ceo-delegate-incident-resolve:{incident_id}"
            ),
        ),
    )
    return ack.status.value in {"ACCEPTED", "DUPLICATE"}


def _maybe_write_autopilot_chain_report(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
) -> None:
    ensure_workflow_atomic_chain_report(repository, workflow_id=workflow_id)


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
        _maybe_write_autopilot_chain_report(repository, workflow_id=workflow_id)
        snapshot = build_ceo_shadow_snapshot(
            repository,
            workflow_id=workflow_id,
            trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            trigger_ref=f"{idempotency_key_prefix}:{step_index}:controller-probe",
        )
        if (
            workflow_controller_effect(snapshot) in {"ARCHITECT_REQUIRED", "MEETING_REQUIRED", "STAFFING_REQUIRED"}
            and int((snapshot.get("ticket_summary") or {}).get("active_count") or 0) == 0
        ):
            return
        if workflow_has_open_incident(repository, workflow_id):
            if _maybe_auto_resolve_open_incident(
                repository,
                workflow_id=workflow_id,
                idempotency_key_prefix=idempotency_key_prefix,
                step_index=step_index,
            ):
                continue
            return
        if workflow_has_open_approval(repository, workflow_id):
            if _maybe_auto_resolve_open_approval(
                repository,
                workflow_id=workflow_id,
                idempotency_key_prefix=idempotency_key_prefix,
                step_index=step_index,
            ):
                continue
            return

        _, version_before = repository.get_cursor_and_version()
        run_scheduler_tick(
            repository,
            idempotency_key=f"{idempotency_key_prefix}:{step_index}:scheduler",
            max_dispatches=effective_max_dispatches,
        )
        run_leased_ticket_runtime(repository)
        _, version_after = repository.get_cursor_and_version()
        _maybe_write_autopilot_chain_report(repository, workflow_id=workflow_id)

        if workflow_has_open_incident(repository, workflow_id):
            if _maybe_auto_resolve_open_incident(
                repository,
                workflow_id=workflow_id,
                idempotency_key_prefix=idempotency_key_prefix,
                step_index=step_index,
            ):
                continue
            return
        if workflow_has_open_approval(repository, workflow_id):
            if _maybe_auto_resolve_open_approval(
                repository,
                workflow_id=workflow_id,
                idempotency_key_prefix=idempotency_key_prefix,
                step_index=step_index,
            ):
                continue
            return
        if version_after == version_before:
            return
    _maybe_write_autopilot_chain_report(repository, workflow_id=workflow_id)
