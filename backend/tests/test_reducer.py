from __future__ import annotations

import json
from datetime import datetime

from app.core.constants import (
    ACTOR_STATUS_ACTIVE,
    ACTOR_STATUS_DEACTIVATED,
    ACTOR_STATUS_REPLACED,
    ACTOR_STATUS_SUSPENDED,
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    CIRCUIT_BREAKER_STATE_CLOSED,
    CIRCUIT_BREAKER_STATE_OPEN,
    EVENT_EMPLOYEE_FROZEN,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_EMPLOYEE_RESTORED,
    EVENT_ACTOR_DEACTIVATED,
    EVENT_ACTOR_ENABLED,
    EVENT_ACTOR_REPLACED,
    EVENT_ACTOR_SUSPENDED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_INCIDENT_OPENED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_ASSIGNED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
    EVENT_TICKET_LEASE_GRANTED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
)
from app.core.reducer import (
    rebuild_actor_projections,
    rebuild_assignment_projections,
    rebuild_employee_projections,
    rebuild_incident_projections,
    rebuild_lease_projections,
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
    assert projections[0]["tenant_id"] == "tenant_default"
    assert projections[0]["workspace_id"] == "ws_default"
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


def test_reducer_rebuilds_employee_projection_through_hire_replace_freeze_and_restore():
    hired_event = {
        "sequence_no": 1,
        "event_type": EVENT_EMPLOYEE_HIRED,
        "workflow_id": "wf_staffing",
        "occurred_at": datetime.fromisoformat("2026-04-01T10:00:00+08:00"),
        "payload_json": json.dumps(
            {
                "employee_id": "emp_frontend_backup",
                "role_type": "frontend_engineer",
                "skill_profile": {"primary_domain": "frontend"},
                "personality_profile": {"style": "maker"},
                "aesthetic_profile": {"preference": "minimal"},
                "state": "ACTIVE",
                "board_approved": True,
                "provider_id": "prov_openai_compat",
                "role_profile_refs": ["frontend_engineer_primary"],
            }
        ),
    }
    replaced_event = {
        "sequence_no": 2,
        "event_type": EVENT_EMPLOYEE_REPLACED,
        "workflow_id": "wf_staffing",
        "occurred_at": datetime.fromisoformat("2026-04-01T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "employee_id": "emp_frontend_2",
                "replacement_employee_id": "emp_frontend_backup",
            }
        ),
    }
    frozen_event = {
        "sequence_no": 3,
        "event_type": EVENT_EMPLOYEE_FROZEN,
        "workflow_id": "wf_staffing",
        "occurred_at": datetime.fromisoformat("2026-04-01T10:10:00+08:00"),
        "payload_json": json.dumps(
            {
                "employee_id": "emp_frontend_backup",
                "reason": "Pause new work after repeated rework.",
            }
        ),
    }
    restored_event = {
        "sequence_no": 4,
        "event_type": EVENT_EMPLOYEE_RESTORED,
        "workflow_id": "wf_staffing",
        "occurred_at": datetime.fromisoformat("2026-04-01T10:15:00+08:00"),
        "payload_json": json.dumps(
            {
                "employee_id": "emp_frontend_backup",
                "reason": "Return worker after pause.",
            }
        ),
    }

    projections = rebuild_employee_projections([hired_event, replaced_event, frozen_event, restored_event])
    by_id = {projection["employee_id"]: projection for projection in projections}

    assert by_id["emp_frontend_2"]["state"] == "REPLACED"
    assert by_id["emp_frontend_2"]["board_approved"] is False
    assert by_id["emp_frontend_backup"]["state"] == "ACTIVE"
    assert by_id["emp_frontend_backup"]["role_profile_refs"] == ["frontend_engineer_primary"]
    assert by_id["emp_frontend_backup"]["provider_id"] == "prov_openai_compat"


def test_reducer_rebuilds_actor_projection_from_independent_actor_events():
    events = [
        {
            "sequence_no": 1,
            "event_type": EVENT_EMPLOYEE_HIRED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T09:55:00+08:00"),
            "payload_json": json.dumps(
                {
                    "employee_id": "emp_backend_legacy",
                    "role_type": "backend_engineer",
                    "state": "ACTIVE",
                    "board_approved": True,
                    "role_profile_refs": ["backend_engineer_primary"],
                }
            ),
        },
        {
            "sequence_no": 2,
            "event_type": EVENT_ACTOR_ENABLED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T10:00:00+08:00"),
            "payload_json": json.dumps(
                {
                    "actor_id": "actor_backend_1",
                    "employee_id": "emp_backend_1",
                    "capability_set": [
                        "source.modify.backend",
                        "test.run.backend",
                        "evidence.write.test",
                    ],
                    "provider_preferences": {
                        "purpose": "implementation",
                        "preferred_provider_id": "prov_openai_compat",
                    },
                    "availability": {"max_concurrent_leases": 1},
                    "created_from_policy": "round7a-test",
                    "audit_reason": "Enable backend actor.",
                }
            ),
        },
        {
            "sequence_no": 3,
            "event_type": EVENT_ACTOR_SUSPENDED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T10:05:00+08:00"),
            "payload_json": json.dumps(
                {
                    "actor_id": "actor_backend_1",
                    "suspended_reason": "Provider quota containment.",
                    "capability_scope": ["source.modify.backend"],
                }
            ),
        },
        {
            "sequence_no": 4,
            "event_type": EVENT_ACTOR_ENABLED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T10:10:00+08:00"),
            "payload_json": json.dumps(
                {
                    "actor_id": "actor_backend_1",
                    "capability_set": [
                        "source.modify.backend",
                        "test.run.backend",
                        "evidence.write.test",
                        "evidence.write.git",
                    ],
                    "provider_preferences": {"purpose": "implementation"},
                    "availability": {"max_concurrent_leases": 2},
                    "created_from_policy": "manual-restore",
                    "audit_reason": "Restore backend actor.",
                }
            ),
        },
        {
            "sequence_no": 5,
            "event_type": EVENT_ACTOR_REPLACED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T10:15:00+08:00"),
            "payload_json": json.dumps(
                {
                    "actor_id": "actor_backend_1",
                    "replacement_actor_id": "actor_backend_2",
                    "replacement_reason": "Rotate executor after repeated rework.",
                    "replacement_plan": {"handoff_ticket_ids": ["tkt_123"]},
                }
            ),
        },
        {
            "sequence_no": 6,
            "event_type": EVENT_ACTOR_ENABLED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T10:16:00+08:00"),
            "payload_json": json.dumps(
                {
                    "actor_id": "actor_backend_2",
                    "employee_id": "emp_backend_2",
                    "capability_set": ["source.modify.backend", "test.run.backend"],
                    "provider_preferences": {"purpose": "implementation"},
                    "availability": {"max_concurrent_leases": 1},
                    "created_from_policy": "replacement",
                    "audit_reason": "Enable replacement actor.",
                }
            ),
        },
        {
            "sequence_no": 7,
            "event_type": EVENT_ACTOR_DEACTIVATED,
            "workflow_id": "wf_staffing",
            "occurred_at": datetime.fromisoformat("2026-04-01T10:20:00+08:00"),
            "payload_json": json.dumps(
                {
                    "actor_id": "actor_backend_2",
                    "deactivated_reason": "Retire temporary replacement.",
                    "active_lease_ids": ["lease_001"],
                    "affected_node_ids": ["node_backend"],
                    "replacement_plan": {"action": "REQUEST_HUMAN_DECISION"},
                }
            ),
        },
    ]

    projections = rebuild_actor_projections(events)
    by_id = {projection["actor_id"]: projection for projection in projections}

    assert "emp_backend_legacy" not in by_id
    assert by_id["actor_backend_1"] == {
        "actor_id": "actor_backend_1",
        "employee_id": "emp_backend_1",
        "status": ACTOR_STATUS_REPLACED,
        "capability_set": [
            "source.modify.backend",
            "test.run.backend",
            "evidence.write.test",
            "evidence.write.git",
        ],
        "provider_preferences": {"purpose": "implementation"},
        "availability": {"max_concurrent_leases": 2},
        "created_from_policy": "manual-restore",
        "deactivated_reason": None,
        "replaced_by_actor_id": "actor_backend_2",
        "replacement_reason": "Rotate executor after repeated rework.",
        "replacement_plan": {"handoff_ticket_ids": ["tkt_123"]},
        "lifecycle_reason": "Rotate executor after repeated rework.",
        "updated_at": "2026-04-01T10:15:00+08:00",
        "version": 5,
    }
    assert by_id["actor_backend_2"]["status"] == ACTOR_STATUS_DEACTIVATED
    assert by_id["actor_backend_2"]["deactivated_reason"] == "Retire temporary replacement."
    assert by_id["actor_backend_2"]["replacement_plan"] == {"action": "REQUEST_HUMAN_DECISION"}
    assert by_id["actor_backend_2"]["lifecycle_reason"] == "Retire temporary replacement."


def test_reducer_keeps_assignment_history_separate_from_lease_timeout():
    created_event = {
        "sequence_no": 1,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_assignment",
        "occurred_at": datetime.fromisoformat("2026-05-02T10:00:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_assignment_1",
                "node_id": "node_assignment_1",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "high",
            }
        ),
    }
    assigned_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_ASSIGNED,
        "workflow_id": "wf_assignment",
        "occurred_at": datetime.fromisoformat("2026-05-02T10:01:00+08:00"),
        "payload_json": json.dumps(
            {
                "assignment_id": "asg_actor_backend_1",
                "ticket_id": "tkt_assignment_1",
                "node_id": "node_assignment_1",
                "actor_id": "actor_backend_1",
                "required_capabilities": ["source.modify.backend", "test.run.backend"],
                "assignment_reason": "capability_match",
            }
        ),
    }
    lease_granted_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_LEASE_GRANTED,
        "workflow_id": "wf_assignment",
        "occurred_at": datetime.fromisoformat("2026-05-02T10:02:00+08:00"),
        "payload_json": json.dumps(
            {
                "lease_id": "lease_actor_backend_1_attempt_1",
                "assignment_id": "asg_actor_backend_1",
                "ticket_id": "tkt_assignment_1",
                "node_id": "node_assignment_1",
                "actor_id": "actor_backend_1",
                "lease_timeout_sec": 600,
                "lease_expires_at": "2026-05-02T10:12:00+08:00",
            }
        ),
    }
    timed_out_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_TIMED_OUT,
        "workflow_id": "wf_assignment",
        "occurred_at": datetime.fromisoformat("2026-05-02T10:13:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_assignment_1",
                "node_id": "node_assignment_1",
                "actor_id": "actor_backend_1",
                "assignment_id": "asg_actor_backend_1",
                "lease_id": "lease_actor_backend_1_attempt_1",
                "failure_kind": "TIMEOUT_SLA_EXCEEDED",
                "failure_message": "Lease expired before completion.",
                "failure_fingerprint": "timeout:fingerprint",
            }
        ),
    }

    assignment_projection = rebuild_assignment_projections(
        [created_event, assigned_event, lease_granted_event, timed_out_event]
    )[0]
    lease_projection = rebuild_lease_projections(
        [created_event, assigned_event, lease_granted_event, timed_out_event]
    )[0]
    ticket_projection = rebuild_ticket_projections(
        [created_event, assigned_event, lease_granted_event, timed_out_event]
    )[0]

    assert assignment_projection == {
        "assignment_id": "asg_actor_backend_1",
        "workflow_id": "wf_assignment",
        "ticket_id": "tkt_assignment_1",
        "node_id": "node_assignment_1",
        "actor_id": "actor_backend_1",
        "required_capabilities": ["source.modify.backend", "test.run.backend"],
        "status": "ASSIGNED",
        "assignment_reason": "capability_match",
        "assigned_at": "2026-05-02T10:01:00+08:00",
        "updated_at": "2026-05-02T10:01:00+08:00",
        "version": 2,
    }
    assert lease_projection == {
        "lease_id": "lease_actor_backend_1_attempt_1",
        "assignment_id": "asg_actor_backend_1",
        "workflow_id": "wf_assignment",
        "ticket_id": "tkt_assignment_1",
        "node_id": "node_assignment_1",
        "actor_id": "actor_backend_1",
        "status": "TIMED_OUT",
        "lease_timeout_sec": 600,
        "lease_expires_at": "2026-05-02T10:12:00+08:00",
        "started_at": None,
        "closed_at": "2026-05-02T10:13:00+08:00",
        "failure_kind": "TIMEOUT_SLA_EXCEEDED",
        "updated_at": "2026-05-02T10:13:00+08:00",
        "version": 4,
    }
    assert ticket_projection["status"] == TICKET_STATUS_TIMED_OUT
    assert ticket_projection["actor_id"] == "actor_backend_1"
    assert ticket_projection["assignment_id"] == "asg_actor_backend_1"
    assert ticket_projection["lease_id"] == "lease_actor_backend_1_attempt_1"
    assert ticket_projection["lease_owner"] is None
    assert ticket_projection["lease_expires_at"] is None


def test_reducer_rebuilds_ticket_and_node_lifecycle_projection():
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
    assigned_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_ASSIGNED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:02:30+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "actor_id": "emp_frontend_2",
                "assignment_id": "asg_wf_123_tkt_001_emp_frontend_2",
                "required_capabilities": ["source.modify.frontend"],
                "assignment_reason": "capability_match",
            }
        ),
    }
    leased_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_LEASE_GRANTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "actor_id": "emp_frontend_2",
                "assignment_id": "asg_wf_123_tkt_001_emp_frontend_2",
                "lease_id": "lease_wf_123_tkt_001_emp_frontend_2_1",
                "lease_timeout_sec": 600,
                "lease_expires_at": "2026-03-28T10:13:00+08:00",
            }
        ),
    }
    started_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "started_by": "emp_frontend_2",
                "actor_id": "emp_frontend_2",
                "assignment_id": "asg_wf_123_tkt_001_emp_frontend_2",
                "lease_id": "lease_wf_123_tkt_001_emp_frontend_2_1",
            }
        ),
    }
    completed_event = {
        "sequence_no": 5,
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

    leased_ticket = rebuild_ticket_projections([created_event, assigned_event, leased_event])[0]
    leased_node = rebuild_node_projections([created_event, assigned_event, leased_event])[0]
    assert leased_ticket["status"] == TICKET_STATUS_LEASED
    assert leased_ticket["actor_id"] == "emp_frontend_2"
    assert leased_ticket["assignment_id"] == "asg_wf_123_tkt_001_emp_frontend_2"
    assert leased_ticket["lease_id"] == "lease_wf_123_tkt_001_emp_frontend_2_1"
    assert leased_ticket["lease_owner"] is None
    assert leased_ticket["lease_expires_at"] == "2026-03-28T10:13:00+08:00"
    assert leased_ticket["heartbeat_timeout_sec"] == 600
    assert leased_node["status"] == NODE_STATUS_PENDING

    executing_ticket = rebuild_ticket_projections([created_event, assigned_event, leased_event, started_event])[0]
    executing_node = rebuild_node_projections([created_event, assigned_event, leased_event, started_event])[0]
    assert executing_ticket["status"] == TICKET_STATUS_EXECUTING
    assert executing_ticket["actor_id"] == "emp_frontend_2"
    assert executing_ticket["assignment_id"] == "asg_wf_123_tkt_001_emp_frontend_2"
    assert executing_ticket["lease_id"] == "lease_wf_123_tkt_001_emp_frontend_2_1"
    assert executing_ticket["lease_owner"] is None
    assert executing_ticket["lease_expires_at"] == "2026-03-28T10:13:00+08:00"
    assert executing_ticket["started_at"] == "2026-03-28T10:04:00+08:00"
    assert executing_ticket["last_heartbeat_at"] == "2026-03-28T10:04:00+08:00"
    assert executing_ticket["heartbeat_expires_at"] == "2026-03-28T10:14:00+08:00"
    assert executing_node["status"] == NODE_STATUS_EXECUTING

    ticket_projections = rebuild_ticket_projections(
        [created_event, assigned_event, leased_event, started_event, completed_event]
    )
    node_projections = rebuild_node_projections(
        [created_event, assigned_event, leased_event, started_event, completed_event]
    )

    assert ticket_projections == [
        {
            "ticket_id": "tkt_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "status": TICKET_STATUS_COMPLETED,
            "lease_owner": None,
            "actor_id": "emp_frontend_2",
            "assignment_id": "asg_wf_123_tkt_001_emp_frontend_2",
            "lease_id": "lease_wf_123_tkt_001_emp_frontend_2_1",
            "lease_expires_at": None,
            "started_at": None,
            "last_heartbeat_at": None,
            "heartbeat_expires_at": None,
            "heartbeat_timeout_sec": 600,
            "retry_count": 0,
            "retry_budget": 2,
            "timeout_sla_sec": 1800,
            "priority": "high",
            "last_failure_kind": None,
            "last_failure_message": None,
            "last_failure_fingerprint": None,
            "blocking_reason_code": None,
            "updated_at": "2026-03-28T10:05:00+08:00",
            "version": 5,
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
            "version": 5,
        }
    ]


def test_reducer_rebuilds_heartbeat_refresh_and_clears_runtime_activity_fields():
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
                "lease_timeout_sec": 600,
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
    heartbeat_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_HEARTBEAT_RECORDED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:08:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "reported_by": "emp_frontend_2",
                "heartbeat_expires_at": "2026-03-28T10:18:00+08:00",
            }
        ),
    }
    timed_out_event = {
        "sequence_no": 5,
        "event_type": EVENT_TICKET_TIMED_OUT,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:20:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "failure_kind": "HEARTBEAT_TIMEOUT",
                "failure_message": "Ticket missed the required heartbeat window.",
                "failure_fingerprint": "fp_heartbeat_001",
            }
        ),
    }

    heartbeat_ticket = rebuild_ticket_projections(
        [created_event, leased_event, started_event, heartbeat_event]
    )[0]
    timed_out_ticket = rebuild_ticket_projections(
        [created_event, leased_event, started_event, heartbeat_event, timed_out_event]
    )[0]

    assert heartbeat_ticket["status"] == TICKET_STATUS_EXECUTING
    assert heartbeat_ticket["started_at"] == "2026-03-28T10:04:00+08:00"
    assert heartbeat_ticket["last_heartbeat_at"] == "2026-03-28T10:08:00+08:00"
    assert heartbeat_ticket["heartbeat_expires_at"] == "2026-03-28T10:18:00+08:00"
    assert heartbeat_ticket["heartbeat_timeout_sec"] == 600

    assert timed_out_ticket["status"] == TICKET_STATUS_TIMED_OUT
    assert timed_out_ticket["started_at"] is None
    assert timed_out_ticket["last_heartbeat_at"] is None
    assert timed_out_ticket["heartbeat_expires_at"] is None
    assert timed_out_ticket["heartbeat_timeout_sec"] == 600


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


def test_reducer_rebuilds_timeout_retry_backoff_and_incident_projection():
    retry_created_event = {
        "sequence_no": 1,
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
                "lease_timeout_sec": 900,
                "timeout_sla_sec": 2700,
                "priority": "high",
                "parent_ticket_id": "tkt_001",
                "escalation_policy": {
                    "on_timeout": "retry",
                    "on_schema_error": "retry",
                    "on_repeat_failure": "escalate_ceo",
                    "timeout_repeat_threshold": 2,
                    "timeout_backoff_multiplier": 1.5,
                    "timeout_backoff_cap_multiplier": 2.0,
                },
            }
        ),
    }
    leased_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_LEASED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:36:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "leased_by": "emp_frontend_2",
                "lease_timeout_sec": 900,
                "lease_expires_at": "2026-03-28T10:51:00+08:00",
            }
        ),
    }
    incident_opened_event = {
        "sequence_no": 3,
        "event_type": EVENT_INCIDENT_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:18:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
                "timeout_streak_count": 2,
            }
        ),
    }
    breaker_opened_event = {
        "sequence_no": 4,
        "event_type": EVENT_CIRCUIT_BREAKER_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:18:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "node_id": "node_homepage_visual",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            }
        ),
    }

    ticket = rebuild_ticket_projections([retry_created_event, leased_event])[0]
    incidents = rebuild_incident_projections([incident_opened_event, breaker_opened_event])

    assert ticket["timeout_sla_sec"] == 2700
    assert ticket["heartbeat_timeout_sec"] == 900
    assert incidents == [
        {
            "incident_id": "inc_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "ticket_id": "tkt_002",
            "provider_id": None,
            "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
            "status": "OPEN",
            "severity": "high",
            "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            "circuit_breaker_state": "OPEN",
            "opened_at": "2026-03-28T11:18:00+08:00",
            "closed_at": None,
            "payload": {
                "incident_id": "inc_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
                "timeout_streak_count": 2,
            },
            "updated_at": "2026-03-28T11:18:00+08:00",
            "version": 4,
        }
    ]


def test_reducer_rebuilds_closed_breaker_and_closed_incident_projection():
    incident_opened_event = {
        "sequence_no": 1,
        "event_type": EVENT_INCIDENT_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:18:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
                "timeout_streak_count": 2,
            }
        ),
    }
    breaker_opened_event = {
        "sequence_no": 2,
        "event_type": EVENT_CIRCUIT_BREAKER_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:18:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "node_id": "node_homepage_visual",
                "ticket_id": "tkt_002",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            }
        ),
    }
    breaker_closed_event = {
        "sequence_no": 3,
        "event_type": "CIRCUIT_BREAKER_CLOSED",
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:20:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "node_id": "node_homepage_visual",
                "ticket_id": "tkt_002",
                "circuit_breaker_state": "CLOSED",
                "resolved_by": "emp_ops_1",
                "resolution_summary": "Breaker manually reopened after mitigation.",
            }
        ),
    }
    incident_closed_event = {
        "sequence_no": 4,
        "event_type": "INCIDENT_CLOSED",
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:20:01+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "status": "CLOSED",
                "resolved_by": "emp_ops_1",
                "resolution_summary": "Breaker manually reopened after mitigation.",
            }
        ),
    }

    incidents = rebuild_incident_projections(
        [
            incident_opened_event,
            breaker_opened_event,
            breaker_closed_event,
            incident_closed_event,
        ]
    )

    assert incidents == [
        {
            "incident_id": "inc_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "ticket_id": "tkt_002",
            "provider_id": None,
            "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
            "status": "CLOSED",
            "severity": "high",
            "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            "circuit_breaker_state": "CLOSED",
            "opened_at": "2026-03-28T11:18:00+08:00",
            "closed_at": "2026-03-28T11:20:01+08:00",
            "payload": {
                "incident_id": "inc_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
                "status": "CLOSED",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
                "timeout_streak_count": 2,
                "resolved_by": "emp_ops_1",
                "resolution_summary": "Breaker manually reopened after mitigation.",
            },
            "updated_at": "2026-03-28T11:20:01+08:00",
            "version": 4,
        }
    ]


def test_reducer_rebuilds_provider_pause_incident_projection_and_close_payload():
    incident_opened_event = {
        "sequence_no": 1,
        "event_type": EVENT_INCIDENT_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_provider_001",
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "provider_id": "prov_openai_compat",
                "incident_type": "PROVIDER_EXECUTION_PAUSED",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "provider:prov_openai_compat",
                "pause_reason": "PROVIDER_RATE_LIMITED",
            }
        ),
    }
    breaker_opened_event = {
        "sequence_no": 2,
        "event_type": EVENT_CIRCUIT_BREAKER_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:00:10+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_provider_001",
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "provider_id": "prov_openai_compat",
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": "provider:prov_openai_compat",
            }
        ),
    }
    breaker_closed_event = {
        "sequence_no": 3,
        "event_type": EVENT_CIRCUIT_BREAKER_CLOSED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_provider_001",
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "provider_id": "prov_openai_compat",
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_CLOSED,
            }
        ),
    }
    incident_closed_event = {
        "sequence_no": 4,
        "event_type": EVENT_INCIDENT_CLOSED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:01+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_provider_001",
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "provider_id": "prov_openai_compat",
                "status": "CLOSED",
                "followup_action": "RESTORE_ONLY",
                "followup_ticket_id": None,
            }
        ),
    }

    incidents = rebuild_incident_projections(
        [
            incident_opened_event,
            breaker_opened_event,
            breaker_closed_event,
            incident_closed_event,
        ]
    )

    assert incidents == [
        {
            "incident_id": "inc_provider_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "ticket_id": "tkt_001",
            "provider_id": "prov_openai_compat",
            "incident_type": "PROVIDER_EXECUTION_PAUSED",
            "status": "CLOSED",
            "severity": "high",
            "fingerprint": "provider:prov_openai_compat",
            "circuit_breaker_state": "CLOSED",
            "opened_at": "2026-03-28T10:00:00+08:00",
            "closed_at": "2026-03-28T10:05:01+08:00",
            "payload": {
                "incident_id": "inc_provider_001",
                "ticket_id": "tkt_001",
                "node_id": "node_homepage_visual",
                "provider_id": "prov_openai_compat",
                "incident_type": "PROVIDER_EXECUTION_PAUSED",
                "status": "CLOSED",
                "severity": "high",
                "fingerprint": "provider:prov_openai_compat",
                "pause_reason": "PROVIDER_RATE_LIMITED",
                "followup_action": "RESTORE_ONLY",
                "followup_ticket_id": None,
            },
            "updated_at": "2026-03-28T10:05:01+08:00",
            "version": 4,
        }
    ]


def test_reducer_rebuilds_repeated_failure_incident_projection_and_close_payload():
    incident_opened_event = {
        "sequence_no": 1,
        "event_type": EVENT_INCIDENT_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_failure_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:repeat-failure:fp_1",
                "failure_streak_count": 2,
                "latest_failure_kind": "RUNTIME_ERROR",
                "latest_failure_fingerprint": "fp_1",
            }
        ),
    }
    breaker_opened_event = {
        "sequence_no": 2,
        "event_type": EVENT_CIRCUIT_BREAKER_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:00:01+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_failure_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": "wf_123:node_homepage_visual:repeat-failure:fp_1",
            }
        ),
    }
    breaker_closed_event = {
        "sequence_no": 3,
        "event_type": EVENT_CIRCUIT_BREAKER_CLOSED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_failure_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_CLOSED,
            }
        ),
    }
    incident_closed_event = {
        "sequence_no": 4,
        "event_type": EVENT_INCIDENT_CLOSED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:05:01+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_failure_001",
                "ticket_id": "tkt_003",
                "node_id": "node_homepage_visual",
                "status": "CLOSED",
                "followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                "followup_ticket_id": "tkt_003",
            }
        ),
    }

    incidents = rebuild_incident_projections(
        [
            incident_opened_event,
            breaker_opened_event,
            breaker_closed_event,
            incident_closed_event,
        ]
    )

    assert incidents == [
        {
            "incident_id": "inc_failure_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "ticket_id": "tkt_003",
            "provider_id": None,
            "incident_type": "REPEATED_FAILURE_ESCALATION",
            "status": "CLOSED",
            "severity": "high",
            "fingerprint": "wf_123:node_homepage_visual:repeat-failure:fp_1",
            "circuit_breaker_state": "CLOSED",
            "opened_at": "2026-03-28T10:00:00+08:00",
            "closed_at": "2026-03-28T10:05:01+08:00",
            "payload": {
                "incident_id": "inc_failure_001",
                "ticket_id": "tkt_003",
                "node_id": "node_homepage_visual",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "CLOSED",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:repeat-failure:fp_1",
                "failure_streak_count": 2,
                "latest_failure_kind": "RUNTIME_ERROR",
                "latest_failure_fingerprint": "fp_1",
                "followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                "followup_ticket_id": "tkt_003",
            },
            "updated_at": "2026-03-28T10:05:01+08:00",
            "version": 4,
        }
    ]


def test_reducer_rebuilds_cancel_requested_and_cancelled_states():
    created_event = {
        "sequence_no": 1,
        "event_type": EVENT_TICKET_CREATED,
        "workflow_id": "wf_cancel",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_cancel_001",
                "node_id": "node_cancel",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "high",
            }
        ),
    }
    leased_event = {
        "sequence_no": 2,
        "event_type": EVENT_TICKET_LEASED,
        "workflow_id": "wf_cancel",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:01:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_cancel_001",
                "node_id": "node_cancel",
                "leased_by": "emp_frontend_2",
                "lease_expires_at": "2026-03-28T10:11:00+08:00",
            }
        ),
    }
    started_event = {
        "sequence_no": 3,
        "event_type": EVENT_TICKET_STARTED,
        "workflow_id": "wf_cancel",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_cancel_001",
                "node_id": "node_cancel",
                "started_by": "emp_frontend_2",
            }
        ),
    }
    cancel_requested_event = {
        "sequence_no": 4,
        "event_type": EVENT_TICKET_CANCEL_REQUESTED,
        "workflow_id": "wf_cancel",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_cancel_001",
                "node_id": "node_cancel",
                "cancelled_by": "emp_ops_1",
                "reason": "Stop current attempt.",
            }
        ),
    }
    cancelled_event = {
        "sequence_no": 5,
        "event_type": EVENT_TICKET_CANCELLED,
        "workflow_id": "wf_cancel",
        "occurred_at": datetime.fromisoformat("2026-03-28T10:03:10+08:00"),
        "payload_json": json.dumps(
            {
                "ticket_id": "tkt_cancel_001",
                "node_id": "node_cancel",
                "cancelled_by": "emp_ops_1",
                "reason": "Cancellation confirmed.",
            }
        ),
    }

    tickets = rebuild_ticket_projections(
        [created_event, leased_event, started_event, cancel_requested_event, cancelled_event]
    )
    nodes = rebuild_node_projections(
        [created_event, leased_event, started_event, cancel_requested_event, cancelled_event]
    )

    assert tickets[0]["status"] == TICKET_STATUS_CANCELLED
    assert nodes[0]["status"] == NODE_STATUS_CANCELLED

    intermediate_tickets = rebuild_ticket_projections(
        [created_event, leased_event, started_event, cancel_requested_event]
    )
    intermediate_nodes = rebuild_node_projections(
        [created_event, leased_event, started_event, cancel_requested_event]
    )

    assert intermediate_tickets[0]["status"] == TICKET_STATUS_CANCEL_REQUESTED
    assert intermediate_nodes[0]["status"] == NODE_STATUS_CANCEL_REQUESTED


def test_reducer_rebuilds_recovering_incident_before_close():
    incident_opened_event = {
        "sequence_no": 1,
        "event_type": EVENT_INCIDENT_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:18:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "ticket_id": "tkt_002",
                "node_id": "node_homepage_visual",
                "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            }
        ),
    }
    breaker_opened_event = {
        "sequence_no": 2,
        "event_type": EVENT_CIRCUIT_BREAKER_OPENED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:18:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "node_id": "node_homepage_visual",
                "ticket_id": "tkt_002",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            }
        ),
    }
    breaker_closed_event = {
        "sequence_no": 3,
        "event_type": EVENT_CIRCUIT_BREAKER_CLOSED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:20:00+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "node_id": "node_homepage_visual",
                "ticket_id": "tkt_002",
                "circuit_breaker_state": "CLOSED",
            }
        ),
    }
    recovery_started_event = {
        "sequence_no": 4,
        "event_type": EVENT_INCIDENT_RECOVERY_STARTED,
        "workflow_id": "wf_123",
        "occurred_at": datetime.fromisoformat("2026-03-28T11:20:01+08:00"),
        "payload_json": json.dumps(
            {
                "incident_id": "inc_001",
                "ticket_id": "tkt_003",
                "node_id": "node_homepage_visual",
                "status": "RECOVERING",
                "followup_action": "RESTORE_AND_RETRY_LATEST_TIMEOUT",
                "followup_ticket_id": "tkt_003",
            }
        ),
    }

    incidents = rebuild_incident_projections(
        [
            incident_opened_event,
            breaker_opened_event,
            breaker_closed_event,
            recovery_started_event,
        ]
    )

    assert incidents == [
        {
            "incident_id": "inc_001",
            "workflow_id": "wf_123",
            "node_id": "node_homepage_visual",
            "ticket_id": "tkt_003",
            "provider_id": None,
            "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
            "status": "RECOVERING",
            "severity": "high",
            "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
            "circuit_breaker_state": "CLOSED",
            "opened_at": "2026-03-28T11:18:00+08:00",
            "closed_at": None,
            "payload": {
                "incident_id": "inc_001",
                "ticket_id": "tkt_003",
                "node_id": "node_homepage_visual",
                "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
                "status": "RECOVERING",
                "severity": "high",
                "fingerprint": "wf_123:node_homepage_visual:runtime-timeout",
                "followup_action": "RESTORE_AND_RETRY_LATEST_TIMEOUT",
                "followup_ticket_id": "tkt_003",
            },
            "updated_at": "2026-03-28T11:20:01+08:00",
            "version": 4,
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
