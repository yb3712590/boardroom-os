from __future__ import annotations

import json
from datetime import datetime

from app.core.constants import (
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_STARTED,
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_REWORK_REQUIRED,
)
from app.core.reducer import (
    rebuild_node_projections,
    rebuild_ticket_projections,
    rebuild_workflow_projections,
)


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


def test_reducer_rebuilds_ticket_and_node_projection_through_pending_executing_completed():
    created_event = {
        "sequence_no": 1,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "retry_budget": 2,
                "timeout_sla_sec": 1800,
                "priority": "high",
            }
        ),
    }
    started_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    completed_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_COMPLETED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "board_review_requested": False,
            }
        ),
    }

    pending_ticket = rebuild_ticket_projections([created_event])[0]
    pending_node = rebuild_node_projections([created_event])[0]
    assert pending_ticket["status"] == TICKET_STATUS_PENDING
    assert pending_ticket["retry_budget"] == 2
    assert pending_ticket["timeout_sla_sec"] == 1800
    assert pending_ticket["priority"] == "high"
    assert pending_node["status"] == NODE_STATUS_PENDING

    executing_ticket = rebuild_ticket_projections([created_event, started_event])[0]
    executing_node = rebuild_node_projections([created_event, started_event])[0]
    assert executing_ticket["status"] == TICKET_STATUS_EXECUTING
    assert executing_node["status"] == NODE_STATUS_EXECUTING

    ticket_projections = rebuild_ticket_projections([created_event, started_event, completed_event])
    node_projections = rebuild_node_projections([created_event, started_event, completed_event])

    assert ticket_projections == [
        {
            "ticket_id": "tkt_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "status": TICKET_STATUS_COMPLETED,
            "lease_owner": None,
            "lease_expires_at": None,
            "retry_count": 0,
            "retry_budget": 2,
            "timeout_sla_sec": 1800,
            "priority": "high",
            "blocking_reason_code": None,
            "updated_at": "2026-03-28T10:04:00+08:00",
            "version": 3,
        }
    ]
    assert node_projections == [
        {
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "latest_ticket_id": "tkt_001",
            "status": NODE_STATUS_COMPLETED,
            "blocking_reason_code": None,
            "updated_at": "2026-03-28T10:04:00+08:00",
            "version": 3,
        }
    ]


def test_reducer_rebuilds_blocked_then_approved_then_rework_states():
    created_event = {
        "sequence_no": 1,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "retry_budget": 2,
                "timeout_sla_sec": 1800,
                "priority": "high",
            }
        ),
    }
    started_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    completed_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_COMPLETED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "board_review_requested": True,
            }
        ),
    }
    board_required_event = {
        "sequence_no": 4,
        "event_type": EVENT_BOARD_REVIEW_REQUIRED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
            }
        ),
    }

    blocked_ticket = rebuild_ticket_projections(
        [created_event, started_event, completed_event, board_required_event]
    )[0]
    blocked_node = rebuild_node_projections(
        [created_event, started_event, completed_event, board_required_event]
    )[0]
    assert blocked_ticket["status"] == TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW
    assert blocked_ticket["blocking_reason_code"] == BLOCKING_REASON_BOARD_REVIEW_REQUIRED
    assert blocked_node["status"] == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW
    assert blocked_node["blocking_reason_code"] == BLOCKING_REASON_BOARD_REVIEW_REQUIRED

    approved_events = [
        created_event,
        started_event,
        completed_event,
        board_required_event,
        {
            "sequence_no": 5,
            "event_type": EVENT_BOARD_REVIEW_APPROVED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:06:00+08:00"),
            "payload_json": json.dumps(
                {
                    "ticket_id": "tkt_001",
                    "node_id": "node_homepage_visual",
                }
            ),
        },
    ]
    assert rebuild_ticket_projections(approved_events)[0]["status"] == TICKET_STATUS_COMPLETED
    assert rebuild_node_projections(approved_events)[0]["status"] == NODE_STATUS_COMPLETED

    rejected_events = [
        created_event,
        started_event,
        completed_event,
        board_required_event,
        {
            "sequence_no": 5,
            "event_type": EVENT_BOARD_REVIEW_REJECTED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:06:00+08:00"),
            "payload_json": json.dumps(
                {
                    "ticket_id": "tkt_001",
                    "node_id": "node_homepage_visual",
                    "decision_action": "REJECT",
                }
            ),
        },
    ]
    rejected_ticket = rebuild_ticket_projections(rejected_events)[0]
    rejected_node = rebuild_node_projections(rejected_events)[0]
    assert rejected_ticket["status"] == TICKET_STATUS_REWORK_REQUIRED
    assert rejected_ticket["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED
    assert rejected_node["status"] == NODE_STATUS_REWORK_REQUIRED
    assert rejected_node["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED

    modified_events = [
        created_event,
        started_event,
        completed_event,
        board_required_event,
        {
            "sequence_no": 5,
            "event_type": EVENT_BOARD_REVIEW_REJECTED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:06:00+08:00"),
            "payload_json": json.dumps(
                {
                    "ticket_id": "tkt_001",
                    "node_id": "node_homepage_visual",
                    "decision_action": "MODIFY_CONSTRAINTS",
                }
            ),
        },
    ]
    modified_ticket = rebuild_ticket_projections(modified_events)[0]
    modified_node = rebuild_node_projections(modified_events)[0]
    assert modified_ticket["status"] == TICKET_STATUS_REWORK_REQUIRED
    assert modified_ticket["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS
    assert modified_node["status"] == NODE_STATUS_REWORK_REQUIRED
    assert modified_node["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS
