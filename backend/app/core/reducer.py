from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.core.constants import (
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    DEFAULT_BOARD_GATE_STATE,
    DEFAULT_WORKFLOW_STAGE,
    DEFAULT_WORKFLOW_STATUS,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
)


def _event_payload(event: dict) -> dict:
    payload = event.get("payload")
    if payload is not None:
        return payload
    return json.loads(event["payload_json"])


def _base_ticket_projection(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": payload["ticket_id"],
        "workflow_id": event["workflow_id"],
        "node_id": payload["node_id"],
        "lease_owner": None,
        "lease_expires_at": None,
        "retry_count": payload.get("retry_count", 0),
        "retry_budget": payload.get("retry_budget"),
        "timeout_sla_sec": payload.get("timeout_sla_sec"),
        "priority": payload.get("priority"),
        "last_failure_kind": None,
        "last_failure_message": None,
        "last_failure_fingerprint": None,
        "blocking_reason_code": None,
    }


def _base_node_projection(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": event["workflow_id"],
        "node_id": payload["node_id"],
        "latest_ticket_id": payload["ticket_id"],
        "blocking_reason_code": None,
    }


def rebuild_workflow_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict] = {}

    for event in events:
        payload = _event_payload(event)
        if event["event_type"] != EVENT_WORKFLOW_CREATED:
            continue

        workflow_id = event["workflow_id"]
        projections[workflow_id] = {
            "workflow_id": workflow_id,
            "title": payload.get("title") or payload["north_star_goal"],
            "north_star_goal": payload["north_star_goal"],
            "current_stage": DEFAULT_WORKFLOW_STAGE,
            "status": DEFAULT_WORKFLOW_STATUS,
            "budget_total": payload["budget_cap"],
            "budget_used": 0,
            "board_gate_state": DEFAULT_BOARD_GATE_STATE,
            "deadline_at": payload.get("deadline_at"),
            "started_at": event["occurred_at"].isoformat(),
            "updated_at": event["occurred_at"].isoformat(),
            "version": event["sequence_no"],
        }

    return list(projections.values())


def rebuild_ticket_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]

        if event_type == EVENT_TICKET_CREATED:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                **_base_ticket_projection(event, payload),
                "status": TICKET_STATUS_PENDING,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_LEASED:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "status": TICKET_STATUS_LEASED,
                "lease_owner": payload.get("leased_by"),
                "lease_expires_at": payload.get("lease_expires_at"),
                "last_failure_kind": projections.get(ticket_id, {}).get("last_failure_kind"),
                "last_failure_message": projections.get(ticket_id, {}).get("last_failure_message"),
                "last_failure_fingerprint": projections.get(ticket_id, {}).get("last_failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_STARTED:
            ticket_id = payload["ticket_id"]
            node_id = payload["node_id"]
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_EXECUTING,
                "last_failure_kind": projections.get(ticket_id, {}).get("last_failure_kind"),
                "last_failure_message": projections.get(ticket_id, {}).get("last_failure_message"),
                "last_failure_fingerprint": projections.get(ticket_id, {}).get("last_failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_COMPLETED:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "status": TICKET_STATUS_COMPLETED,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_FAILED:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "status": TICKET_STATUS_FAILED,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_kind": payload.get("failure_kind"),
                "last_failure_message": payload.get("failure_message"),
                "last_failure_fingerprint": payload.get("failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_TIMED_OUT:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "status": TICKET_STATUS_TIMED_OUT,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_kind": payload.get("failure_kind"),
                "last_failure_message": payload.get("failure_message"),
                "last_failure_fingerprint": payload.get("failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_RETRY_SCHEDULED:
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_COMPLETED,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            blocking_reason = (
                BLOCKING_REASON_MODIFY_CONSTRAINTS
                if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                else BLOCKING_REASON_BOARD_REJECTED
            )
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_REWORK_REQUIRED,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": blocking_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())


def rebuild_node_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[tuple[str, str], dict] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]
        workflow_id = event["workflow_id"]

        if workflow_id is None:
            continue

        if event_type == EVENT_TICKET_CREATED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **_base_node_projection(event, payload),
                "status": NODE_STATUS_PENDING,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_LEASED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_STARTED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_EXECUTING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_COMPLETED:
            if payload.get("board_review_requested"):
                continue
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_RETRY_SCHEDULED:
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "blocking_reason_code": BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            blocking_reason = (
                BLOCKING_REASON_MODIFY_CONSTRAINTS
                if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                else BLOCKING_REASON_BOARD_REJECTED
            )
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": blocking_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())
