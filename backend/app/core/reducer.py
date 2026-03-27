from __future__ import annotations

import json
from collections.abc import Iterable

from app.core.constants import (
    DEFAULT_BOARD_GATE_STATE,
    DEFAULT_WORKFLOW_STAGE,
    DEFAULT_WORKFLOW_STATUS,
    EVENT_WORKFLOW_CREATED,
)


def rebuild_workflow_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict] = {}

    for event in events:
        payload = json.loads(event["payload_json"])
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
