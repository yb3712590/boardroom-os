from __future__ import annotations

import re
from typing import Any

from app.contracts.commands import IncidentFollowupAction
from app.core.constants import (
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
    INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
)
from app.db.repository import ControlPlaneRepository


_TICKET_ID_RE = re.compile(r"\bTicket\s+(tkt_[A-Za-z0-9_]+)\b")


def _source_ticket_id_from_incident_payload(incident: dict[str, Any]) -> str | None:
    payload = incident.get("payload") or {}
    trigger_ref = str(payload.get("trigger_ref") or "").strip()
    source_ticket_id = (
        str(incident.get("ticket_id") or "").strip()
        or str(payload.get("ticket_id") or "").strip()
        or (trigger_ref if trigger_ref.startswith("tkt_") else "")
    )
    if source_ticket_id:
        return source_ticket_id
    match = _TICKET_ID_RE.search(str(payload.get("error_message") or ""))
    return match.group(1) if match else None


def _restore_needed_without_source_ticket(incident: dict[str, Any]) -> bool:
    payload = incident.get("payload") or {}
    message = str(payload.get("error_message") or "")
    return "restore_needed" in message or "restore/retry recovery" in message


def _latest_terminal_ticket_id_for_incident(
    repository: ControlPlaneRepository,
    incident: dict[str, Any],
    *,
    connection=None,
) -> str | None:
    if not _restore_needed_without_source_ticket(incident):
        return None
    workflow_id = str(incident.get("workflow_id") or "").strip()
    if not workflow_id:
        return None

    def _query(active_connection) -> str | None:
        row = active_connection.execute(
            """
            SELECT ticket_id
            FROM ticket_projection
            WHERE workflow_id = ?
              AND status IN ('FAILED', 'TIMED_OUT')
            ORDER BY updated_at DESC, ticket_id DESC
            LIMIT 1
            """,
            (workflow_id,),
        ).fetchone()
        return None if row is None else str(row["ticket_id"])

    if connection is None:
        with repository.connection() as active_connection:
            return _query(active_connection)
    return _query(connection)


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
    source_ticket_id = _source_ticket_id_from_incident_payload(
        incident
    ) or _latest_terminal_ticket_id_for_incident(repository, incident, connection=connection)
    if trigger_type not in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT} and source_ticket_id is None:
        return {
            "source_ticket_id": None,
            "source_ticket_status": None,
            "recommended_restore_action": None,
            "source_terminal_event_type": None,
        }

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
