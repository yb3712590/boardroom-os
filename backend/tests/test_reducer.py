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


def test_reducer_rebuilds_ticket_and_node_projection_through_pending_leased_executing_completed():
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
    leased_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_LEASED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "leased_by": "emp_frontend_2",
                "lease_expires_at": "2026-03-28T10:13:00+08:00",
            }
        ),
    }
    started_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    completed_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_COMPLETED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
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
    assert pending_ticket["lease_owner"] is None
    assert pending_ticket["lease_expires_at"] is None
    assert pending_node["status"] == NODE_STATUS_PENDING

    leased_ticket = rebuild_ticket_projections([created_event, leased_event])[0]
    leased_node = rebuild_node_projections([created_event, leased_event])[0]
    assert leased_ticket["status"] == TICKET_STATUS_LEASED
    assert leased_ticket["lease_owner"] == "emp_frontend_2"
    assert leased_ticket["lease_expires_at"] == "2026-03-28T10:13:00+08:00"
    assert leased_node["status"] == NODE_STATUS_PENDING

    executing_ticket = rebuild_ticket_projections([created_event, leased_event, started_event])[0]
    executing_node = rebuild_node_projections([created_event, leased_event, started_event])[0]
    assert executing_ticket["status"] == TICKET_STATUS_EXECUTING
    assert executing_ticket["lease_owner"] == "emp_frontend_2"
    assert executing_ticket["lease_expires_at"] == "2026-03-28T10:13:00+08:00"
    assert executing_node["status"] == NODE_STATUS_EXECUTING

    ticket_projections = rebuild_ticket_projections(
        [created_event, leased_event, started_event, completed_event]
    )
    node_projections = rebuild_node_projections(
        [created_event, leased_event, started_event, completed_event]
    )

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
            "last_failure_kind": None,
            "last_failure_message": None,
            "last_failure_fingerprint": None,
            "blocking_reason_code": None,
            "updated_at": "2026-03-28T10:05:00+08:00",
            "version": 4,
        }
    ]
    assert node_projections == [
        {
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "latest_ticket_id": "tkt_001",
            "status": NODE_STATUS_COMPLETED,
            "blocking_reason_code": None,
            "updated_at": "2026-03-28T10:05:00+08:00",
            "version": 4,
        }
    ]


def test_reducer_rebuilds_failed_then_retry_created_flow():
    created_event = {
        "sequence_no": 1,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "attempt_no": 1,
                "retry_count": 0,
                "retry_budget": 2,
                "timeout_sla_sec": 1800,
                "priority": "high",
                "parent_ticket_id": None,
            }
        ),
    }
    leased_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_LEASED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "leased_by": "emp_frontend_2",
                "lease_expires_at": "2026-03-28T10:13:00+08:00",
            }
        ),
    }
    started_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    failed_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_FAILED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "failure_kind": "SCHEMA_ERROR",
                "failure_message": "Schema validation failed.",
                "failure_fingerprint": "fp_schema_001",
            }
        ),
    }
    retry_scheduled_event = {
        "sequence_no": 5,
        "event_type": EVENT_TICKET_RETRY_SCHEDULED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "next_ticket_id": "tkt_002",
                "next_attempt_no": 2,
                "retry_count": 1,
            }
        ),
    }
    retry_created_event = {
        "sequence_no": 6,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "attempt_no": 2,
                "retry_count": 1,
                "retry_budget": 2,
                "timeout_sla_sec": 1800,
                "priority": "high",
                "parent_ticket_id": "tkt_001",
            }
        ),
    }

    failed_ticket = rebuild_ticket_projections([created_event, leased_event, started_event, failed_event])[0]
    failed_node = rebuild_node_projections([created_event, leased_event, started_event, failed_event])[0]
    assert failed_ticket["status"] == TICKET_STATUS_FAILED
    assert failed_ticket["lease_owner"] is None
    assert failed_ticket["last_failure_kind"] == "SCHEMA_ERROR"
    assert failed_ticket["last_failure_message"] == "Schema validation failed."
    assert failed_ticket["last_failure_fingerprint"] == "fp_schema_001"
    assert failed_node["status"] == NODE_STATUS_REWORK_REQUIRED

    tickets = rebuild_ticket_projections(
        [created_event, leased_event, started_event, failed_event, retry_scheduled_event, retry_created_event]
    )
    nodes = rebuild_node_projections(
        [created_event, leased_event, started_event, failed_event, retry_scheduled_event, retry_created_event]
    )
    old_ticket = next(item for item in tickets if item["ticket_id"] == "tkt_001")
    new_ticket = next(item for item in tickets if item["ticket_id"] == "tkt_002")

    assert old_ticket["status"] == TICKET_STATUS_FAILED
    assert new_ticket["status"] == TICKET_STATUS_PENDING
    assert new_ticket["retry_count"] == 1
    assert nodes[0]["latest_ticket_id"] == "tkt_002"
    assert nodes[0]["status"] == NODE_STATUS_PENDING


def test_reducer_rebuilds_timed_out_then_retry_created_flow():
    created_event = {
        "sequence_no": 1,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "attempt_no": 1,
                "retry_count": 0,
                "retry_budget": 2,
                "timeout_sla_sec": 1800,
                "priority": "high",
            }
        ),
    }
    leased_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_LEASED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "leased_by": "emp_frontend_2",
                "lease_expires_at": "2026-03-28T10:13:00+08:00",
            }
        ),
    }
    started_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    timed_out_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_TIMED_OUT,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:35:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "failure_kind": "TIMEOUT",
                "failure_message": "Ticket exceeded timeout SLA.",
                "failure_fingerprint": "fp_timeout_001",
            }
        ),
    }
    retry_scheduled_event = {
        "sequence_no": 5,
        "event_type": EVENT_TICKET_RETRY_SCHEDULED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:35:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "next_ticket_id": "tkt_002",
                "next_attempt_no": 2,
                "retry_count": 1,
            }
        ),
    }
    retry_created_event = {
        "sequence_no": 6,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:35:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "attempt_no": 2,
                "retry_count": 1,
                "retry_budget": 2,
                "timeout_sla_sec": 1800,
                "priority": "high",
                "parent_ticket_id": "tkt_001",
            }
        ),
    }

    tickets = rebuild_ticket_projections(
        [created_event, leased_event, started_event, timed_out_event, retry_scheduled_event, retry_created_event]
    )
    nodes = rebuild_node_projections(
        [created_event, leased_event, started_event, timed_out_event, retry_scheduled_event, retry_created_event]
    )
    old_ticket = next(item for item in tickets if item["ticket_id"] == "tkt_001")
    new_ticket = next(item for item in tickets if item["ticket_id"] == "tkt_002")

    assert old_ticket["status"] == TICKET_STATUS_TIMED_OUT
    assert old_ticket["last_failure_kind"] == "TIMEOUT"
    assert new_ticket["status"] == TICKET_STATUS_PENDING
    assert new_ticket["retry_count"] == 1
    assert nodes[0]["latest_ticket_id"] == "tkt_002"
    assert nodes[0]["status"] == NODE_STATUS_PENDING


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
    leased_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_LEASED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "leased_by": "emp_frontend_2",
                "lease_expires_at": "2026-03-28T10:13:00+08:00",
            }
        ),
    }
    started_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    completed_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_COMPLETED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "board_review_requested": True,
            }
        ),
    }
    board_required_event = {
        "sequence_no": 5,
        "event_type": EVENT_BOARD_REVIEW_REQUIRED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:06:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
            }
        ),
    }

    blocked_ticket = rebuild_ticket_projections(
        [created_event, leased_event, started_event, completed_event, board_required_event]
    )[0]
    blocked_node = rebuild_node_projections(
        [created_event, leased_event, started_event, completed_event, board_required_event]
    )[0]
    assert blocked_ticket["status"] == TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW
    assert blocked_ticket["lease_owner"] is None
    assert blocked_ticket["lease_expires_at"] is None
    assert blocked_ticket["blocking_reason_code"] == BLOCKING_REASON_BOARD_REVIEW_REQUIRED
    assert blocked_node["status"] == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW
    assert blocked_node["blocking_reason_code"] == BLOCKING_REASON_BOARD_REVIEW_REQUIRED

    approved_events = [
        created_event,
        leased_event,
        started_event,
        completed_event,
        board_required_event,
        {
            "sequence_no": 6,
            "event_type": EVENT_BOARD_REVIEW_APPROVED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:07:00+08:00"),
            "payload_json": json.dumps(
                {
                    "ticket_id": "tkt_001",
                    "node_id": "node_homepage_visual",
                }
            ),
        },
    ]
    approved_ticket = rebuild_ticket_projections(approved_events)[0]
    assert approved_ticket["status"] == TICKET_STATUS_COMPLETED
    assert approved_ticket["lease_owner"] is None
    assert approved_ticket["lease_expires_at"] is None
    assert rebuild_node_projections(approved_events)[0]["status"] == NODE_STATUS_COMPLETED

    rejected_events = [
        created_event,
        leased_event,
        started_event,
        completed_event,
        board_required_event,
        {
            "sequence_no": 6,
            "event_type": EVENT_BOARD_REVIEW_REJECTED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:07:00+08:00"),
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
    assert rejected_ticket["lease_owner"] is None
    assert rejected_ticket["lease_expires_at"] is None
    assert rejected_ticket["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED
    assert rejected_node["status"] == NODE_STATUS_REWORK_REQUIRED
    assert rejected_node["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED

    modified_events = [
        created_event,
        leased_event,
        started_event,
        completed_event,
        board_required_event,
        {
            "sequence_no": 6,
            "event_type": EVENT_BOARD_REVIEW_REJECTED,
            "workflow_id": "wf_123",
            "occurred_at": datetime.fromisoformat("2026-03-28T10:07:00+08:00"),
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
    assert modified_ticket["lease_owner"] is None
    assert modified_ticket["lease_expires_at"] is None
    assert modified_ticket["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS
    assert modified_node["status"] == NODE_STATUS_REWORK_REQUIRED
    assert modified_node["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS
