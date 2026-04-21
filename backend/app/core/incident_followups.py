from __future__ import annotations

from typing import Any

from app.contracts.commands import IncidentFollowupAction
from app.core.constants import (
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
    INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
)
from app.db.repository import ControlPlaneRepository


def resolve_ceo_shadow_source_ticket_context(
    repository: ControlPlaneRepository,
    incident: dict[str, Any],
    *,
    connection=None,
) -> dict[str, str | None]:
    if str(incident.get("incident_type") or "").strip() != INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED:
        return {
            "source_ticket_id": None,
            "source_ticket_status": None,
            "recommended_restore_action": None,
            "source_terminal_event_type": None,
        }

    payload = incident.get("payload") or {}
    trigger_type = str(payload.get("trigger_type") or "").strip()
    if trigger_type not in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
        return {
            "source_ticket_id": None,
            "source_ticket_status": None,
            "recommended_restore_action": None,
            "source_terminal_event_type": None,
        }

    source_ticket_id = (
        str(incident.get("ticket_id") or "").strip()
        or str(payload.get("ticket_id") or "").strip()
        or str(payload.get("trigger_ref") or "").strip()
        or None
    )
    if source_ticket_id is None:
        return {
            "source_ticket_id": None,
            "source_ticket_status": None,
            "recommended_restore_action": None,
            "source_terminal_event_type": None,
        }

    if connection is None:
        with repository.connection() as active_connection:
            current_ticket = repository.get_current_ticket_projection(source_ticket_id, connection=active_connection)
            latest_terminal_event = repository.get_latest_ticket_terminal_event(
                active_connection,
                source_ticket_id,
            )
    else:
        current_ticket = repository.get_current_ticket_projection(source_ticket_id, connection=connection)
        latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, source_ticket_id)

    source_ticket_status = str((current_ticket or {}).get("status") or "").strip() or None
    source_terminal_event_type = str((latest_terminal_event or {}).get("event_type") or "").strip() or None
    recommended_restore_action: str | None = None
    if source_terminal_event_type == EVENT_TICKET_TIMED_OUT:
        recommended_restore_action = IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value
    elif source_terminal_event_type == EVENT_TICKET_FAILED:
        recommended_restore_action = IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value
    elif trigger_type == EVENT_TICKET_TIMED_OUT:
        recommended_restore_action = IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value
        source_ticket_status = source_ticket_status or "TIMED_OUT"
        source_terminal_event_type = source_terminal_event_type or EVENT_TICKET_TIMED_OUT
    elif trigger_type == EVENT_TICKET_FAILED:
        recommended_restore_action = IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value
        source_ticket_status = source_ticket_status or "FAILED"
        source_terminal_event_type = source_terminal_event_type or EVENT_TICKET_FAILED

    return {
        "source_ticket_id": source_ticket_id,
        "source_ticket_status": source_ticket_status,
        "recommended_restore_action": recommended_restore_action,
        "source_terminal_event_type": source_terminal_event_type,
    }
