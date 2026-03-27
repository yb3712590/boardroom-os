from __future__ import annotations

import json
from collections.abc import Iterable

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
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_REWORK_REQUIRED,
)


def _event_payload(event: dict) -> dict:
    payload = event.get("payload")
    if payload is not None:
        return payload
    return json.loads(event["payload_json"])


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

        if event_type == EVENT_TICKET_COMPLETED:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                "ticket_id": ticket_id,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "status": TICKET_STATUS_COMPLETED,
                "lease_owner": None,
                "lease_expires_at": None,
                "retry_count": 0,
                "retry_budget": None,
                "timeout_sla_sec": None,
                "priority": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            projections[ticket_id] = {
                **projections.get(
                    ticket_id,
                    {
                        "ticket_id": ticket_id,
                        "workflow_id": event["workflow_id"],
                        "node_id": node_id,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "retry_count": 0,
                        "retry_budget": None,
                        "timeout_sla_sec": None,
                        "priority": None,
                    },
                ),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
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
                **projections.get(
                    ticket_id,
                    {
                        "ticket_id": ticket_id,
                        "workflow_id": event["workflow_id"],
                        "node_id": node_id,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "retry_count": 0,
                        "retry_budget": None,
                        "timeout_sla_sec": None,
                        "priority": None,
                    },
                ),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_COMPLETED,
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
                **projections.get(
                    ticket_id,
                    {
                        "ticket_id": ticket_id,
                        "workflow_id": event["workflow_id"],
                        "node_id": node_id,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "retry_count": 0,
                        "retry_budget": None,
                        "timeout_sla_sec": None,
                        "priority": None,
                    },
                ),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "status": TICKET_STATUS_REWORK_REQUIRED,
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

        if event_type == EVENT_TICKET_COMPLETED:
            if payload.get("board_review_requested"):
                continue
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            key = (workflow_id, node_id)
            projections[key] = {
                "workflow_id": workflow_id,
                "node_id": node_id,
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
                "workflow_id": workflow_id,
                "node_id": node_id,
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
                "workflow_id": workflow_id,
                "node_id": node_id,
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": blocking_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())
