from __future__ import annotations

from typing import Any

from app.core.constants import (
    CIRCUIT_BREAKER_STATE_OPEN,
    EVENT_EMPLOYEE_FROZEN,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_CREATED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_TYPE_STAFFING_CONTAINMENT,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
)
from app.core.ids import new_prefixed_id
from app.db.repository import ControlPlaneRepository


def _dedupe_string_values(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _build_staffing_containment_context(
    *,
    employee_id: str,
    action_kind: str,
    reason: str,
    replacement_employee_id: str | None,
    occurred_at,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "action_kind": action_kind,
        "reason": reason,
        "replacement_employee_id": replacement_employee_id,
        "contained_at": occurred_at.isoformat(),
    }


def _build_staffing_recovery_context(
    *,
    employee_id: str,
    occurred_at,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "restored_at": occurred_at.isoformat(),
    }


def _requeue_leased_ticket(
    repository: ControlPlaneRepository,
    connection,
    *,
    ticket: dict[str, Any],
    command_id: str,
    occurred_at,
    employee_id: str,
    action_kind: str,
    reason: str,
    replacement_employee_id: str | None,
    idempotency_key_base: str,
) -> None:
    created_spec = repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"]))
    if created_spec is None:
        return

    updated_payload = dict(created_spec)
    updated_payload["excluded_employee_ids"] = _dedupe_string_values(
        list(updated_payload.get("excluded_employee_ids") or []) + [employee_id]
    )
    updated_payload["staffing_containment"] = _build_staffing_containment_context(
        employee_id=employee_id,
        action_kind=action_kind,
        reason=reason,
        replacement_employee_id=replacement_employee_id,
        occurred_at=occurred_at,
    )

    repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="system",
        actor_id="staffing-router",
        workflow_id=str(ticket["workflow_id"]),
        idempotency_key=f"{idempotency_key_base}:requeue:{ticket['ticket_id']}",
        causation_id=command_id,
        correlation_id=str(ticket["workflow_id"]),
        payload=updated_payload,
        occurred_at=occurred_at,
    )


def _contain_inflight_ticket(
    repository: ControlPlaneRepository,
    connection,
    *,
    ticket: dict[str, Any],
    command_id: str,
    occurred_at,
    employee_id: str,
    action_kind: str,
    reason: str,
    replacement_employee_id: str | None,
    idempotency_key_base: str,
) -> None:
    ticket_id = str(ticket["ticket_id"])
    workflow_id = str(ticket["workflow_id"])
    node_id = str(ticket["node_id"])
    containment_context = _build_staffing_containment_context(
        employee_id=employee_id,
        action_kind=action_kind,
        reason=reason,
        replacement_employee_id=replacement_employee_id,
        occurred_at=occurred_at,
    )

    if str(ticket["status"]) == TICKET_STATUS_EXECUTING:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CANCEL_REQUESTED,
            actor_type="system",
            actor_id="staffing-router",
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:cancel-requested:{ticket_id}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "ticket_id": ticket_id,
                "node_id": node_id,
                "cancelled_by": "staffing-router",
                "reason": reason,
                "staffing_containment": containment_context,
            },
            occurred_at=occurred_at,
        )

    incident_id = new_prefixed_id("inc")
    fingerprint = f"{workflow_id}:{node_id}:staffing-containment:{ticket_id}:{employee_id}"
    repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="staffing-router",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "incident_type": INCIDENT_TYPE_STAFFING_CONTAINMENT,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "node_id": node_id,
            "ticket_id": ticket_id,
            **containment_context,
        },
        occurred_at=occurred_at,
    )
    repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="staffing-router",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
            "node_id": node_id,
            "ticket_id": ticket_id,
            **containment_context,
        },
        occurred_at=occurred_at,
    )


def contain_employee_active_tickets(
    repository: ControlPlaneRepository,
    connection,
    *,
    employee_id: str,
    action_kind: str,
    reason: str,
    occurred_at,
    command_id: str,
    idempotency_key_base: str,
    replacement_employee_id: str | None = None,
) -> None:
    active_tickets = repository.list_ticket_projections_by_statuses(
        connection,
        [TICKET_STATUS_LEASED, TICKET_STATUS_EXECUTING, TICKET_STATUS_CANCEL_REQUESTED],
    )
    for ticket in active_tickets:
        actor_id = str(ticket.get("actor_id") or "").strip()
        actor_employee_id = ""
        if actor_id:
            actor = repository.get_actor_projection(actor_id, connection=connection)
            actor_employee_id = str((actor or {}).get("employee_id") or actor_id).strip()
        if actor_employee_id != employee_id:
            continue
        status = str(ticket["status"])
        if status == TICKET_STATUS_LEASED:
            _requeue_leased_ticket(
                repository,
                connection,
                ticket=ticket,
                command_id=command_id,
                occurred_at=occurred_at,
                employee_id=employee_id,
                action_kind=action_kind,
                reason=reason,
                replacement_employee_id=replacement_employee_id,
                idempotency_key_base=idempotency_key_base,
            )
            continue
        _contain_inflight_ticket(
            repository,
            connection,
            ticket=ticket,
            command_id=command_id,
            occurred_at=occurred_at,
            employee_id=employee_id,
            action_kind=action_kind,
            reason=reason,
            replacement_employee_id=replacement_employee_id,
            idempotency_key_base=idempotency_key_base,
        )


def restore_employee_requeued_tickets(
    repository: ControlPlaneRepository,
    connection,
    *,
    employee_id: str,
    occurred_at,
    command_id: str,
    idempotency_key_base: str,
) -> None:
    pending_tickets = repository.list_ticket_projections_by_statuses(
        connection,
        [TICKET_STATUS_PENDING],
    )
    for ticket in pending_tickets:
        created_spec = repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"]))
        if created_spec is None:
            continue
        containment = created_spec.get("staffing_containment") or {}
        if not isinstance(containment, dict):
            continue
        if str(containment.get("employee_id") or "") != employee_id:
            continue
        if str(containment.get("action_kind") or "") != EVENT_EMPLOYEE_FROZEN:
            continue

        previous_excluded_employee_ids = _dedupe_string_values(
            list(created_spec.get("excluded_employee_ids") or [])
        )
        if employee_id not in previous_excluded_employee_ids:
            continue

        updated_payload = dict(created_spec)
        updated_payload["excluded_employee_ids"] = [
            excluded_employee_id
            for excluded_employee_id in previous_excluded_employee_ids
            if excluded_employee_id != employee_id
        ]
        updated_payload["staffing_recovery"] = _build_staffing_recovery_context(
            employee_id=employee_id,
            occurred_at=occurred_at,
        )

        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="staffing-router",
            workflow_id=str(ticket["workflow_id"]),
            idempotency_key=f"{idempotency_key_base}:restore-requeue:{ticket['ticket_id']}",
            causation_id=command_id,
            correlation_id=str(ticket["workflow_id"]),
            payload=updated_payload,
            occurred_at=occurred_at,
        )
