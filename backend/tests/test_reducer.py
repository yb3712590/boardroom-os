from __future__ import annotations

import json
from datetime import datetime

from app.core.constants import EVENT_SYSTEM_INITIALIZED, EVENT_WORKFLOW_CREATED
from app.core.reducer import rebuild_workflow_projections


def test_reducer_rebuilds_projection_from_workflow_created_events():
    events = [
        {
            "sequence_no": 1,
            "event_type": EVENT_SYSTEM_INITIALIZED,
            "workflow_id": None,
            "occurred_at": datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
            "payload_json": json.dumps({"status": "initialized"}),
        },
        {
            "sequence_no": 2,
            "event_type": EVENT_WORKFLOW_CREATED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:01:00+08:00"),
            "payload_json": json.dumps(
                {
                    "north_star_goal": "Ship MVP A",
                    "budget_cap": 500000,
                    "deadline_at": None,
                    "title": "Ship MVP A",
                }
            ),
        },
    ]

    projections = rebuild_workflow_projections(events)

    assert len(projections) == 1
    assert projections[0]["workflow_id"] == "wf_123"
    assert projections[0]["north_star_goal"] == "Ship MVP A"
    assert projections[0]["version"] == 2


def test_repository_projection_matches_reducer_replay(client):
    client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": "Ship MVP A",
            "hard_constraints": ["Keep governance explicit."],
            "budget_cap": 500000,
            "deadline_at": None,
        },
    )
    client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": "Ship MVP B",
            "hard_constraints": ["Keep governance explicit."],
            "budget_cap": 750000,
            "deadline_at": None,
        },
    )

    repository = client.app.state.repository
    replayed = rebuild_workflow_projections(repository.list_events_for_testing())
    active_workflow = repository.get_active_workflow()

    assert any(item["workflow_id"] == active_workflow["workflow_id"] for item in replayed)
    assert max(item["version"] for item in replayed) == active_workflow["version"]
