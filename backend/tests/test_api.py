from __future__ import annotations

import json

from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
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


def _project_init_payload(goal: str, budget_cap: int = 500000) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": ["Keep governance explicit."],
        "budget_cap": budget_cap,
        "deadline_at": None,
    }


def _seed_worker(
    client,
    *,
    employee_id: str,
    role_type: str = "frontend_engineer",
    provider_id: str = "prov_openai_compat",
    role_profile_refs: list[str] | None = None,
) -> None:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO employee_projection (
                employee_id,
                role_type,
                skill_profile_json,
                personality_profile_json,
                aesthetic_profile_json,
                state,
                board_approved,
                provider_id,
                role_profile_refs_json,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_id,
                role_type,
                "{}",
                "{}",
                "{}",
                "ACTIVE",
                1,
                provider_id,
                json.dumps(role_profile_refs or ["ui_designer_primary"], sort_keys=True),
                "2026-03-28T10:00:00+08:00",
                1,
            ),
        )




def _ticket_complete_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    include_review_request: bool = True,
    compiled_context_bundle_ref: str = "ctx://homepage/visual-v1",
    compile_manifest_ref: str = "manifest://homepage/visual-v1",
) -> dict:
    payload = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "completed_by": "emp_frontend_2",
        "completion_summary": "Visual milestone is blocked for board review.",
        "artifact_refs": ["art://homepage/option-a.png", "art://homepage/option-b.png"],
        "idempotency_key": f"ticket-complete:{workflow_id}:{ticket_id}",
    }
    if include_review_request:
        payload["review_request"] = {
            "review_type": "VISUAL_MILESTONE",
            "priority": "high",
            "title": "Review homepage visual milestone",
            "subtitle": "Two candidate hero directions are ready for board selection.",
            "blocking_scope": "NODE_ONLY",
            "trigger_reason": "Visual milestone hit a board-gated release checkpoint.",
            "why_now": "Downstream homepage implementation should not proceed before direction lock.",
            "recommended_action": "APPROVE",
            "recommended_option_id": "option_a",
            "recommendation_summary": "Option A has the clearest hierarchy and strongest first impression.",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "High-contrast review candidate.",
                    "artifact_refs": ["art://homepage/option-a.png"],
                    "pros": ["Strong first-screen hierarchy"],
                    "cons": ["Slightly more aggressive contrast"],
                    "risks": ["Needs careful brand calibration"],
                },
                {
                    "option_id": "option_b",
                    "label": "Option B",
                    "summary": "Lower contrast fallback.",
                    "artifact_refs": ["art://homepage/option-b.png"],
                    "pros": ["Safer visual tone"],
                    "cons": ["Weaker first impression"],
                    "risks": ["May undersignal product confidence"],
                },
            ],
            "evidence_summary": [
                {
                    "evidence_id": "ev_homepage_checker",
                    "source_type": "CHECKER_FINDING",
                    "headline": "Checker prefers Option A",
                    "summary": "Option A is more legible and directional under current constraints.",
                    "source_ref": "chk://homepage/visual-review",
                }
            ],
            "maker_checker_summary": {
                "maker_employee_id": "emp_frontend_2",
                "checker_employee_id": "emp_checker_1",
                "review_status": "APPROVED_WITH_NOTES",
                "top_findings": [
                    {
                        "finding_id": "finding_hero_contrast",
                        "severity": "medium",
                        "headline": "Option B lacks contrast in the hero section",
                    }
                ],
            },
            "risk_summary": {
                "user_risk": "LOW",
                "engineering_risk": "LOW",
                "schedule_risk": "MEDIUM",
                "budget_risk": "LOW",
            },
            "budget_impact": {
                "tokens_spent_so_far": 1200,
                "tokens_if_approved_estimate_range": {"min_tokens": 200, "max_tokens": 500},
                "tokens_if_rework_estimate_range": {"min_tokens": 600, "max_tokens": 1200},
                "estimate_confidence": "medium",
                "budget_risk": "LOW",
            },
            "developer_inspector_refs": {
                "compiled_context_bundle_ref": compiled_context_bundle_ref,
                "compile_manifest_ref": compile_manifest_ref,
            },
            "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
            "draft_selected_option_id": "option_a",
            "comment_template": "",
            "inbox_title": "Review homepage visual milestone",
            "inbox_summary": "Visual milestone is blocked for board review.",
            "badges": ["visual", "board_gate"],
        }
    return payload


def _ticket_create_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    role_profile_ref: str = "ui_designer_primary",
    lease_timeout_sec: int = 600,
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
) -> dict:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": attempt_no,
        "role_profile_ref": role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/brand-guide.md"],
        "context_query_plan": {
            "keywords": ["homepage", "brand", "visual"],
            "semantic_queries": ["approved visual direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": [
            "Must satisfy approved visual direction",
            "Must produce 2 options",
            "Must include rationale and risks",
        ],
        "output_schema_ref": "ui_milestone_review",
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact", "write_artifact", "image_gen"],
        "allowed_write_set": ["artifacts/ui/homepage/*", "reports/review/*"],
        "lease_timeout_sec": lease_timeout_sec,
        "retry_budget": retry_budget,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": "2026-03-28T18:00:00+08:00",
        "escalation_policy": {
            "on_timeout": on_timeout,
            "on_schema_error": on_schema_error,
            "on_repeat_failure": "escalate_ceo",
            "timeout_repeat_threshold": timeout_repeat_threshold,
            "timeout_backoff_multiplier": timeout_backoff_multiplier,
            "timeout_backoff_cap_multiplier": timeout_backoff_cap_multiplier,
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }


def _ticket_start_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    started_by: str = "emp_frontend_2",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "started_by": started_by,
        "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}",
    }


def _ticket_lease_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "leased_by": leased_by,
        "lease_timeout_sec": lease_timeout_sec,
        "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}:{leased_by}",
    }


def _ticket_fail_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    failure_kind: str = "RUNTIME_ERROR",
    failure_message: str = "Worker execution failed.",
    failure_detail: dict | None = None,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "failed_by": "emp_frontend_2",
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": failure_detail or {"step": "render", "exit_code": 1},
        "idempotency_key": f"ticket-fail:{workflow_id}:{ticket_id}:{failure_kind}",
    }


def _ticket_heartbeat_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    reported_by: str = "emp_frontend_2",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "reported_by": reported_by,
        "idempotency_key": f"ticket-heartbeat:{workflow_id}:{ticket_id}:{reported_by}",
    }


def _scheduler_tick_payload(workers: list[dict] | None = None, idempotency_key: str = "scheduler-tick:1") -> dict:
    payload = {
        "max_dispatches": 10,
        "idempotency_key": idempotency_key,
    }
    if workers is not None:
        payload["workers"] = workers
    return payload


def _incident_resolve_payload(
    incident_id: str,
    resolved_by: str = "emp_ops_1",
    resolution_summary: str = "Operator confirmed mitigation and reopened dispatch on the node.",
    idempotency_key: str | None = None,
    followup_action: str | None = None,
) -> dict:
    payload = {
        "incident_id": incident_id,
        "resolved_by": resolved_by,
        "resolution_summary": resolution_summary,
        "idempotency_key": idempotency_key or f"incident-resolve:{incident_id}",
    }
    if followup_action is not None:
        payload["followup_action"] = followup_action
    return payload


def _create_and_lease_ticket(
    client,
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
    role_profile_ref: str = "ui_designer_primary",
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
) -> None:
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            attempt_no=attempt_no,
            role_profile_ref=role_profile_ref,
            lease_timeout_sec=lease_timeout_sec,
            retry_budget=retry_budget,
            on_timeout=on_timeout,
            on_schema_error=on_schema_error,
            timeout_repeat_threshold=timeout_repeat_threshold,
            timeout_backoff_multiplier=timeout_backoff_multiplier,
            timeout_backoff_cap_multiplier=timeout_backoff_cap_multiplier,
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by=leased_by,
            lease_timeout_sec=lease_timeout_sec,
        ),
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"


def _create_lease_and_start_ticket(
    client,
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
    role_profile_ref: str = "ui_designer_primary",
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
) -> None:
    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        attempt_no=attempt_no,
        leased_by=leased_by,
        lease_timeout_sec=lease_timeout_sec,
        role_profile_ref=role_profile_ref,
        retry_budget=retry_budget,
        on_timeout=on_timeout,
        on_schema_error=on_schema_error,
        timeout_repeat_threshold=timeout_repeat_threshold,
        timeout_backoff_multiplier=timeout_backoff_multiplier,
        timeout_backoff_cap_multiplier=timeout_backoff_cap_multiplier,
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by=leased_by,
        ),
    )
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"


def _seed_review_request(
    client,
    workflow_id: str = "wf_seed",
    materialize_real_compile: bool = False,
    compiled_context_bundle_ref: str = "ctx://homepage/visual-v1",
    compile_manifest_ref: str = "manifest://homepage/visual-v1",
) -> dict:
    _create_lease_and_start_ticket(client, workflow_id=workflow_id)
    if materialize_real_compile:
        repository = client.app.state.repository
        ticket = repository.get_current_ticket_projection("tkt_visual_001")
        assert ticket is not None
        compile_and_persist_execution_artifacts(repository, ticket)
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(
            workflow_id=workflow_id,
            compiled_context_bundle_ref=compiled_context_bundle_ref,
            compile_manifest_ref=compile_manifest_ref,
        ),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"

    approvals = client.app.state.repository.list_open_approvals()
    assert len(approvals) == 1
    return approvals[0]


def test_startup_initializes_schema_and_wal_mode(client, db_path):
    assert db_path.exists()
    repository = client.app.state.repository
    assert repository.get_journal_mode() == "wal"


def test_startup_seeds_minimal_employee_roster(client):
    employees = client.app.state.repository.list_employee_projections(
        states=["ACTIVE"],
        board_approved_only=True,
    )

    assert [employee["employee_id"] for employee in employees] == [
        "emp_checker_1",
        "emp_frontend_2",
    ]
    assert employees[0]["role_profile_refs"] == ["checker_primary"]
    assert employees[1]["role_profile_refs"] == ["ui_designer_primary"]


def test_project_init_returns_real_command_ack(client):
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    assert response.status_code == 200
    body = response.json()
    assert body["command_id"].startswith("cmd_")
    assert body["idempotency_key"].startswith("project-init:")
    assert body["status"] == "ACCEPTED"
    assert body["received_at"]


def test_system_initialized_is_written_only_once(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    duplicate = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    repository = client.app.state.repository
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"
    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1
    assert repository.count_events_by_type(EVENT_WORKFLOW_CREATED) == 1


def test_dashboard_returns_latest_active_workflow(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A", budget_cap=500000))
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP B", budget_cap=750000))

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["active_workflow"]["north_star_goal"] == "Ship MVP B"
    assert data["ops_strip"]["budget_total"] == 750000
    assert isinstance(data["pipeline_summary"]["phases"], list)


def test_dashboard_workforce_summary_reflects_seeded_roster_and_busy_worker(client, set_ticket_time):
    initial_response = client.get("/api/v1/projections/dashboard")

    assert initial_response.status_code == 200
    initial_summary = initial_response.json()["data"]["workforce_summary"]
    assert initial_summary["active_workers"] == 0
    assert initial_summary["idle_workers"] == 1
    assert initial_summary["active_checkers"] == 0

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)
    active_response = client.get("/api/v1/projections/dashboard")
    active_summary = active_response.json()["data"]["workforce_summary"]

    assert active_summary["active_workers"] == 1
    assert active_summary["idle_workers"] == 0
    assert active_summary["active_checkers"] == 0


def test_ticket_create_moves_ticket_and_node_to_pending(client):
    response = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["causation_hint"] == "ticket:tkt_visual_001"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_CREATED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["priority"] == "high"
    assert ticket_projection["retry_budget"] == 2
    assert ticket_projection["timeout_sla_sec"] == 1800
    assert node_projection["status"] == NODE_STATUS_PENDING
    assert node_projection["latest_ticket_id"] == "tkt_visual_001"


def test_ticket_lease_moves_ticket_to_leased_and_keeps_node_pending(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    response = client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_LEASED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert ticket_projection["lease_expires_at"].isoformat() == "2026-03-28T10:10:00+08:00"
    assert node_projection["status"] == NODE_STATUS_PENDING


def test_ticket_start_moves_ticket_and_node_to_executing(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_STARTED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_EXECUTING
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert ticket_projection["started_at"].isoformat() == "2026-03-28T10:05:00+08:00"
    assert ticket_projection["last_heartbeat_at"].isoformat() == "2026-03-28T10:05:00+08:00"
    assert ticket_projection["heartbeat_timeout_sec"] == 600
    assert ticket_projection["heartbeat_expires_at"].isoformat() == "2026-03-28T10:15:00+08:00"
    assert ticket_projection["lease_expires_at"].isoformat() == "2026-03-28T10:10:00+08:00"
    assert node_projection["status"] == NODE_STATUS_EXECUTING


def test_inbox_projection_returns_empty_items(client):
    response = client.get("/api/v1/projections/inbox")

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_ticket_start_is_rejected_before_ticket_create(client):
    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "created" in response.json()["reason"].lower()


def test_ticket_start_is_rejected_before_ticket_lease(client):
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "LEASED" in response.json()["reason"]


def test_ticket_complete_is_rejected_before_ticket_start(client):
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(include_review_request=False),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "PENDING" in response.json()["reason"]


def test_ticket_create_lease_and_start_are_idempotent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    first_create = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    duplicate_create = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    first_lease = client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())
    duplicate_lease = client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())
    set_ticket_time("2026-03-28T10:05:00+08:00")
    first_start = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())
    duplicate_start = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert first_create.json()["status"] == "ACCEPTED"
    assert duplicate_create.json()["status"] == "DUPLICATE"
    assert first_lease.json()["status"] == "ACCEPTED"
    assert duplicate_lease.json()["status"] == "DUPLICATE"
    assert first_start.json()["status"] == "ACCEPTED"
    assert duplicate_start.json()["status"] == "DUPLICATE"


def test_ticket_start_is_rejected_when_lease_owner_differs(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, leased_by="emp_checker_1")

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(started_by="emp_frontend_2"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "leased by emp_checker_1" in response.json()["reason"]


def test_ticket_start_is_rejected_when_lease_has_expired(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "expired" in response.json()["reason"].lower()


def test_ticket_heartbeat_refreshes_executing_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    set_ticket_time("2026-03-28T10:09:00+08:00")
    response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_HEARTBEAT_RECORDED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_EXECUTING
    assert ticket_projection["started_at"].isoformat() == "2026-03-28T10:00:00+08:00"
    assert ticket_projection["last_heartbeat_at"].isoformat() == "2026-03-28T10:09:00+08:00"
    assert ticket_projection["heartbeat_expires_at"].isoformat() == "2026-03-28T10:19:00+08:00"


def test_ticket_heartbeat_is_rejected_before_ticket_start(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)

    response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "EXECUTING" in response.json()["reason"]


def test_ticket_heartbeat_is_rejected_when_owner_differs(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, leased_by="emp_checker_1", role_profile_ref="checker_primary")

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-heartbeat",
        json=_ticket_heartbeat_payload(reported_by="emp_frontend_2"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "leased by emp_checker_1" in response.json()["reason"]


def test_ticket_heartbeat_is_rejected_when_window_has_expired(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "heartbeat" in response.json()["reason"].lower()
    assert "expired" in response.json()["reason"].lower()


def test_ticket_heartbeat_is_idempotent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    first = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())
    duplicate = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())

    assert first.status_code == 200
    assert first.json()["status"] == "ACCEPTED"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"


def test_ticket_lease_is_rejected_for_non_latest_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload(ticket_id="tkt_visual_001"))
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET latest_ticket_id = ?
            WHERE workflow_id = ? AND node_id = ?
            """,
            ("tkt_visual_002", "wf_seed", "node_homepage_visual"),
        )

    response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id="tkt_visual_001"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "no longer points" in response.json()["reason"].lower()


def test_ticket_lease_is_rejected_when_active_lease_belongs_to_other_owner(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, leased_by="emp_checker_1", lease_timeout_sec=600)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(leased_by="emp_frontend_2"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "currently leased by emp_checker_1" in response.json()["reason"]


def test_ticket_lease_can_be_reclaimed_after_expiry(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, leased_by="emp_checker_1", lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(leased_by="emp_frontend_2"),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_LEASED) == 2
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert ticket_projection["lease_expires_at"].isoformat() == "2026-03-28T10:12:00+08:00"


def test_ticket_complete_without_review_request_does_not_open_approval(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(include_review_request=False),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["causation_hint"] == "ticket:tkt_visual_001"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_COMPLETED) == 1
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REQUIRED) == 0
    assert client.app.state.repository.list_open_approvals() == []
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED
    assert node_projection["status"] == NODE_STATUS_COMPLETED


def test_ticket_fail_moves_ticket_to_failed_and_node_to_rework_when_retry_exhausted(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=0)

    response = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_FAILED) == 1
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 0
    assert ticket_projection["status"] == TICKET_STATUS_FAILED
    assert ticket_projection["lease_owner"] is None
    assert ticket_projection["lease_expires_at"] is None
    assert ticket_projection["last_failure_kind"] == "RUNTIME_ERROR"
    assert ticket_projection["last_failure_message"] == "Worker execution failed."
    assert ticket_projection["last_failure_fingerprint"]
    assert node_projection["status"] == NODE_STATUS_REWORK_REQUIRED


def test_ticket_fail_is_rejected_before_ticket_start(client):
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    response = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "EXECUTING" in response.json()["reason"]


def test_ticket_fail_is_rejected_for_non_latest_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET latest_ticket_id = ?
            WHERE workflow_id = ? AND node_id = ?
            """,
            ("tkt_other", "wf_seed", "node_homepage_visual"),
        )

    response = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "no longer points" in response.json()["reason"].lower()


def test_ticket_fail_auto_retry_creates_new_attempt(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(failure_kind="SCHEMA_ERROR"),
    )

    repository = client.app.state.repository
    events = repository.list_events_for_testing()
    latest_ticket = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]
    new_ticket_projection = repository.get_current_ticket_projection(latest_ticket)
    failed_ticket_projection = repository.get_current_ticket_projection("tkt_visual_001")
    created_retry_events = [
        event
        for event in events
        if event["event_type"] == EVENT_TICKET_CREATED and event["payload"]["ticket_id"] != "tkt_visual_001"
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_FAILED) == 1
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1
    assert len(created_retry_events) == 1
    assert created_retry_events[0]["payload"]["parent_ticket_id"] == "tkt_visual_001"
    assert created_retry_events[0]["payload"]["attempt_no"] == 2
    assert created_retry_events[0]["payload"]["retry_count"] == 1
    assert failed_ticket_projection["status"] == TICKET_STATUS_FAILED
    assert new_ticket_projection["status"] == TICKET_STATUS_PENDING
    assert new_ticket_projection["retry_count"] == 1


def test_ticket_fail_is_idempotent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=0)

    first = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())
    duplicate = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())

    assert first.status_code == 200
    assert first.json()["status"] == "ACCEPTED"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"


def test_scheduler_tick_times_out_executing_ticket_and_creates_retry(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    response = client.post("/api/v1/commands/scheduler-tick", json=_scheduler_tick_payload())

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    latest_ticket = node_projection["latest_ticket_id"]
    latest_projection = repository.get_current_ticket_projection(latest_ticket)
    original_projection = repository.get_current_ticket_projection("tkt_visual_001")
    retry_events = repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED)
    timeout_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_TIMED_OUT
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_TIMED_OUT) == 1
    assert retry_events == 1
    assert timeout_events[-1]["payload"]["failure_kind"] == "TIMEOUT_SLA_EXCEEDED"
    assert original_projection["status"] == TICKET_STATUS_TIMED_OUT
    assert latest_ticket != "tkt_visual_001"
    assert latest_projection["status"] == TICKET_STATUS_LEASED
    assert latest_projection["lease_owner"] == "emp_frontend_2"
    assert latest_projection["retry_count"] == 1
    assert latest_projection["timeout_sla_sec"] == 2700
    assert latest_projection["heartbeat_timeout_sec"] == 900
    assert repository.count_events_by_type(EVENT_INCIDENT_OPENED) == 0
    assert repository.count_events_by_type(EVENT_CIRCUIT_BREAKER_OPENED) == 0


def test_scheduler_tick_times_out_executing_ticket_on_missed_heartbeat(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1, lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:heartbeat-timeout"),
    )

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    latest_ticket = node_projection["latest_ticket_id"]
    latest_projection = repository.get_current_ticket_projection(latest_ticket)
    original_projection = repository.get_current_ticket_projection("tkt_visual_001")
    timeout_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_TIMED_OUT
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_TIMED_OUT) == 1
    assert timeout_events[-1]["payload"]["failure_kind"] == "HEARTBEAT_TIMEOUT"
    assert original_projection["status"] == TICKET_STATUS_TIMED_OUT
    assert latest_ticket != "tkt_visual_001"
    assert latest_projection["status"] == TICKET_STATUS_LEASED
    assert latest_projection["retry_count"] == 1


def test_scheduler_tick_keeps_total_timeout_as_hard_cap_after_heartbeat_refresh(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1, lease_timeout_sec=1800)

    set_ticket_time("2026-03-28T10:25:00+08:00")
    heartbeat_response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T10:31:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:total-timeout-after-heartbeat"),
    )

    repository = client.app.state.repository
    timeout_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_TIMED_OUT
    ]
    original_projection = repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert timeout_events[-1]["payload"]["failure_kind"] == "TIMEOUT_SLA_EXCEEDED"
    assert original_projection["status"] == TICKET_STATUS_TIMED_OUT


def test_repeated_timeout_opens_incident_and_blocks_same_node_dispatch(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    first_timeout = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:first-timeout"),
    )
    assert first_timeout.status_code == 200
    assert first_timeout.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    retry_start = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )
    assert retry_start.status_code == 200
    assert retry_start.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T11:18:00+08:00")
    second_timeout = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:second-timeout"),
    )
    assert second_timeout.status_code == 200
    assert second_timeout.json()["status"] == "ACCEPTED"

    same_node_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_visual_003", attempt_no=3),
    )
    assert same_node_create.status_code == 200
    assert same_node_create.json()["status"] == "ACCEPTED"

    other_node_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_other_node_001", node_id="node_docs_visual"),
    )
    assert other_node_create.status_code == 200
    assert other_node_create.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T11:19:00+08:00")
    third_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-block"),
    )

    incident_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_INCIDENT_OPENED
    ]
    breaker_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_CIRCUIT_BREAKER_OPENED
    ]
    blocked_projection = repository.get_current_ticket_projection("tkt_visual_003")
    other_projection = repository.get_current_ticket_projection("tkt_other_node_001")

    assert third_tick.status_code == 200
    assert third_tick.json()["status"] == "ACCEPTED"
    assert len(incident_events) == 1
    assert len(breaker_events) == 1
    assert blocked_projection["status"] == TICKET_STATUS_PENDING
    assert blocked_projection["lease_owner"] is None
    assert other_projection["status"] == TICKET_STATUS_LEASED
    assert other_projection["lease_owner"] == "emp_frontend_2"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1


def test_incident_projection_dashboard_inbox_and_endpoint_reflect_open_timeout_incident(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:incident-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:incident-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["data"]["ops_strip"]["open_incidents"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["open_circuit_breakers"] == 1
    assert dashboard_response.json()["data"]["inbox_counts"]["incidents_pending"] == 1

    assert inbox_response.status_code == 200
    incident_items = [
        item for item in inbox_response.json()["data"]["items"] if item["item_type"] == "INCIDENT_ESCALATION"
    ]
    assert len(incident_items) == 1
    assert incident_items[0]["route_target"]["view"] == "incident_detail"
    assert incident_items[0]["route_target"]["incident_id"] == incident_id

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_id"] == incident_id
    assert incident_response.json()["data"]["incident"]["status"] == "OPEN"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "OPEN"


def test_incident_resolve_closes_breaker_and_removes_open_incident_from_dashboard_and_inbox(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id),
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    duplicate_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert dashboard_response.json()["data"]["ops_strip"]["open_incidents"] == 0
    assert dashboard_response.json()["data"]["ops_strip"]["open_circuit_breakers"] == 0
    assert dashboard_response.json()["data"]["inbox_counts"]["incidents_pending"] == 0
    assert inbox_response.json()["data"]["items"] == []
    assert incident_response.json()["data"]["incident"]["status"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["closed_at"] is not None
    assert incident_response.json()["data"]["incident"]["payload"]["resolved_by"] == "emp_ops_1"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == "RESTORE_ONLY"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] is None
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["status"] == "DUPLICATE"


def test_incident_resolve_can_restore_and_retry_latest_timeout_in_one_command(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-retry-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-retry-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]
    retry_scheduled_before = repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED)

    set_ticket_time("2026-03-28T11:20:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:restore-and-retry",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    latest_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    latest_ticket = repository.get_current_ticket_projection(latest_ticket_id)

    set_ticket_time("2026-03-28T11:21:00+08:00")
    tick_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-retry-third"),
    )
    leased_ticket = repository.get_current_ticket_projection(latest_ticket_id)

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert latest_ticket_id not in {"tkt_visual_001", second_ticket_id}
    assert latest_ticket["status"] == TICKET_STATUS_PENDING
    assert latest_ticket["retry_count"] == 2
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == retry_scheduled_before + 1
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == latest_ticket_id
    assert tick_response.status_code == 200
    assert tick_response.json()["status"] == "ACCEPTED"
    assert leased_ticket["status"] == TICKET_STATUS_LEASED


def test_incident_resolve_reopens_scheduler_dispatch_for_same_node(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-reopen-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-reopen-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:reopen"),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_visual_003",
            attempt_no=3,
            retry_budget=2,
        ),
    )

    set_ticket_time("2026-03-28T11:21:00+08:00")
    tick_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-reopen-third"),
    )
    ticket_projection = repository.get_current_ticket_projection("tkt_visual_003")

    assert tick_response.status_code == 200
    assert tick_response.json()["status"] == "ACCEPTED"
    assert ticket_projection is not None
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"


def test_incident_resolve_rejects_missing_or_closed_incidents(client, set_ticket_time):
    missing_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload("inc_missing", idempotency_key="incident-resolve:missing"),
    )

    assert missing_response.status_code == 200
    assert missing_response.json()["status"] == "REJECTED"

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:reject-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:reject-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    first_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:first-close"),
    )
    second_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:second-close"),
    )

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "ACCEPTED"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "REJECTED"


def test_incident_resolve_restore_and_retry_rejects_when_retry_budget_is_exhausted(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:budget-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:budget-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:budget-exhausted",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "retry budget" in response.json()["reason"].lower()
    assert incident_response.json()["data"]["incident"]["status"] == "OPEN"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1


def test_incident_resolve_restore_and_retry_rejects_when_source_ticket_spec_is_missing(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:missing-spec-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:missing-spec-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM events
            WHERE event_type = 'TICKET_CREATED' AND json_extract(payload_json, '$.ticket_id') = ?
            """,
            (second_ticket_id,),
        )

    set_ticket_time("2026-03-28T11:20:00+08:00")
    response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:missing-spec",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "created spec" in response.json()["reason"].lower()


def test_incident_resolve_restore_and_retry_rejects_when_latest_terminal_event_is_not_timeout(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:not-timeout-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:not-timeout-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_FAILED,
            actor_type="system",
            actor_id="test",
            workflow_id="wf_seed",
            idempotency_key="test:not-timeout-terminal",
            causation_id="cmd_test_not_timeout",
            correlation_id="wf_seed",
            payload={
                "ticket_id": second_ticket_id,
                "node_id": "node_homepage_visual",
                "failure_kind": "RUNTIME_ERROR",
                "failure_message": "Injected non-timeout terminal event for guard coverage.",
                "failure_detail": {},
                "failure_fingerprint": "test-not-timeout",
            },
            occurred_at=set_ticket_time("2026-03-28T11:19:00+08:00"),
        )
        repository.refresh_projections(connection)

    response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:not-timeout",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "latest terminal" in response.json()["reason"].lower()


def test_provider_failure_opens_provider_incident_blocks_same_provider_and_updates_dashboard(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)
    _seed_worker(
        client,
        employee_id="emp_frontend_backup",
        provider_id="prov_backup",
    )

    set_ticket_time("2026-03-28T10:05:00+08:00")
    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_kind="PROVIDER_RATE_LIMITED",
            failure_message="Provider quota exhausted.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_status_code": 429,
            },
        ),
    )

    repository = client.app.state.repository
    provider_incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    create_same_provider = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_provider_blocked",
            node_id="node_provider_blocked",
        ),
    )
    create_fallback = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_provider_fallback",
            node_id="node_provider_fallback",
        ),
    )
    blocked_lease = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            ticket_id="tkt_provider_blocked",
            node_id="node_provider_blocked",
        ),
    )

    set_ticket_time("2026-03-28T10:06:00+08:00")
    tick_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:provider-block"),
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{provider_incident_id}")

    blocked_ticket = repository.get_current_ticket_projection("tkt_provider_blocked")
    fallback_ticket = repository.get_current_ticket_projection("tkt_provider_fallback")

    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 0
    assert create_same_provider.status_code == 200
    assert create_same_provider.json()["status"] == "ACCEPTED"
    assert create_fallback.status_code == 200
    assert create_fallback.json()["status"] == "ACCEPTED"
    assert blocked_lease.status_code == 200
    assert blocked_lease.json()["status"] == "REJECTED"
    assert "currently paused" in blocked_lease.json()["reason"].lower()
    assert tick_response.status_code == 200
    assert tick_response.json()["status"] == "ACCEPTED"
    leased_tickets = [
        ticket
        for ticket in (blocked_ticket, fallback_ticket)
        if ticket is not None and ticket["status"] == TICKET_STATUS_LEASED
    ]
    pending_tickets = [
        ticket
        for ticket in (blocked_ticket, fallback_ticket)
        if ticket is not None and ticket["status"] == TICKET_STATUS_PENDING
    ]
    assert len(leased_tickets) == 1
    assert leased_tickets[0]["lease_owner"] == "emp_frontend_backup"
    assert len(pending_tickets) == 1
    assert pending_tickets[0]["lease_owner"] is None
    assert dashboard_response.json()["data"]["ops_strip"]["provider_health_summary"] == "DEGRADED"
    assert dashboard_response.json()["data"]["inbox_counts"]["provider_alerts"] == 1
    incident_items = [
        item for item in inbox_response.json()["data"]["items"] if item["item_type"] == "PROVIDER_INCIDENT"
    ]
    assert len(incident_items) == 1
    assert incident_response.json()["data"]["incident"]["provider_id"] == "prov_openai_compat"
    assert incident_response.json()["data"]["incident"]["incident_type"] == "PROVIDER_EXECUTION_PAUSED"
    assert incident_response.json()["data"]["incident"]["payload"]["pause_reason"] == "PROVIDER_RATE_LIMITED"


def test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_kind="UPSTREAM_UNAVAILABLE",
            failure_message="Provider upstream returned 503.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_status_code": 503,
            },
        ),
    )

    repository = client.app.state.repository
    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_provider_resume",
            node_id="node_provider_resume",
        ),
    )
    set_ticket_time("2026-03-28T10:06:00+08:00")
    blocked_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:provider-before-resolve"),
    )
    blocked_ticket = repository.get_current_ticket_projection("tkt_provider_resume")

    set_ticket_time("2026-03-28T10:07:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:provider-retry",
            followup_action="RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    followup_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    set_ticket_time("2026-03-28T10:08:00+08:00")
    resumed_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:provider-after-resolve"),
    )
    resumed_ticket = repository.get_current_ticket_projection("tkt_provider_resume")
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert blocked_tick.status_code == 200
    assert blocked_tick.json()["status"] == "ACCEPTED"
    assert blocked_ticket["status"] == TICKET_STATUS_PENDING
    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert followup_ticket_id != "tkt_visual_001"
    assert followup_ticket["status"] == TICKET_STATUS_PENDING
    assert followup_ticket["retry_count"] == 1
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == followup_ticket_id
    assert resumed_tick.status_code == 200
    assert resumed_tick.json()["status"] == "ACCEPTED"
    assert resumed_ticket["status"] == TICKET_STATUS_LEASED
    assert resumed_ticket["lease_owner"] == "emp_frontend_2"
    assert dashboard_response.json()["data"]["inbox_counts"]["provider_alerts"] == 0


def test_scheduler_tick_reclaims_expired_lease_and_dispatches_matching_worker(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, lease_timeout_sec=60, leased_by="emp_checker_1")

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(
            workers=[
                {"employee_id": "emp_frontend_2", "role_profile_refs": ["ui_designer_primary"]},
                {"employee_id": "emp_checker_1", "role_profile_refs": ["checker_primary"]},
            ],
            idempotency_key="scheduler-tick:expired-lease",
        ),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_LEASED) == 2
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"


def test_scheduler_tick_does_not_auto_start_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    set_ticket_time("2026-03-28T10:01:00+08:00")
    response = client.post("/api/v1/commands/scheduler-tick", json=_scheduler_tick_payload())
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert node_projection["status"] == NODE_STATUS_PENDING


def test_scheduler_tick_skips_busy_worker_and_role_mismatch(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_busy",
        ticket_id="tkt_busy",
        node_id="node_busy",
        role_profile_ref="ui_designer_primary",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_busy",
            ticket_id="tkt_pending",
            node_id="node_pending",
            role_profile_ref="ui_designer_primary",
        ),
    )

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(
            workers=[
                {"employee_id": "emp_frontend_2", "role_profile_refs": ["ui_designer_primary"]},
                {"employee_id": "emp_checker_1", "role_profile_refs": ["checker_primary"]},
            ],
            idempotency_key="scheduler-tick:busy",
        ),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_pending")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["lease_owner"] is None


def test_inbox_and_dashboard_reflect_open_approval(client):
    _seed_review_request(client)

    inbox_response = client.get("/api/v1/projections/inbox")
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert inbox_response.status_code == 200
    items = inbox_response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["route_target"]["view"] == "review_room"
    assert dashboard_response.json()["data"]["inbox_counts"]["approvals_pending"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["active_tickets"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["blocked_nodes"] == 1
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == [
        "node_homepage_visual"
    ]


def test_review_room_route_returns_existing_projection(client):
    approval = _seed_review_request(client)

    response = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["review_pack"]["meta"]["approval_id"] == approval["approval_id"]
    assert body["review_pack"]["subject"]["source_ticket_id"] == "tkt_visual_001"
    assert body["review_pack"]["trigger"]["trigger_event_id"].startswith("evt_")
    assert body["review_pack"]["decision_form"]["command_target_version"] >= 1
    assert body["available_actions"] == ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"]


def test_review_room_developer_inspector_returns_materialized_payloads(client):
    approval = _seed_review_request(client, materialize_real_compile=True)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )
    body = response.json()["data"]
    store = client.app.state.developer_inspector_store
    repository = client.app.state.repository
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_visual_001")
    latest_manifest = repository.get_latest_compile_manifest_by_ticket("tkt_visual_001")

    assert response.status_code == 200
    assert latest_bundle is not None
    assert latest_manifest is not None
    assert body["review_pack_id"] == approval["review_pack_id"]
    assert body["compiled_context_bundle_ref"] == "ctx://homepage/visual-v1"
    assert body["compile_manifest_ref"] == "manifest://homepage/visual-v1"
    assert body["availability"] == "ready"
    assert body["compiled_context_bundle"]["meta"]["bundle_id"] == latest_bundle["bundle_id"]
    assert body["compile_manifest"]["compile_meta"]["compile_id"] == latest_manifest["compile_id"]
    assert store.resolve_path("ctx://homepage/visual-v1").exists()
    assert store.resolve_path("manifest://homepage/visual-v1").exists()

def test_review_room_developer_inspector_returns_partial_when_refs_are_unmaterialized(client):
    approval = _seed_review_request(client)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )
    body = response.json()["data"]

    assert response.status_code == 200
    assert body["availability"] == "partial"
    assert body["compiled_context_bundle_ref"] == "ctx://homepage/visual-v1"
    assert body["compile_manifest_ref"] == "manifest://homepage/visual-v1"
    assert body["compiled_context_bundle"] is None
    assert body["compile_manifest"] is None


def test_review_room_developer_inspector_returns_404_for_missing_review_pack(client):
    response = client.get("/api/v1/projections/review-room/brp_missing/developer-inspector")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_ticket_complete_rejects_legacy_developer_inspector_payloads(client):
    _create_lease_and_start_ticket(client)
    payload = _ticket_complete_payload()
    payload["review_request"]["developer_inspector_payloads"] = {
        "compiled_context_bundle": {"meta": {"bundle_id": "legacy_bundle"}},
        "compile_manifest": {"compile_meta": {"compile_id": "legacy_manifest"}},
    }

    response = client.post("/api/v1/commands/ticket-complete", json=payload)

    assert response.status_code == 422
    assert "developer_inspector_payloads" in response.text

def test_ticket_complete_rejects_invalid_developer_inspector_ref(client):
    _create_lease_and_start_ticket(client)
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(
            compiled_context_bundle_ref="ctx://homepage/../escape",
        ),
    )

    assert response.status_code == 422
    assert "unsafe segment" in response.text


def test_missing_review_room_returns_404(client):
    response = client.get("/api/v1/projections/review-room/brp_missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_board_approve_command_resolves_open_approval(client):
    approval = _seed_review_request(client)

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:1",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_APPROVED
    assert updated["payload"]["resolution"]["decision_action"] == "APPROVE"
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_APPROVED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED
    assert ticket_projection["blocking_reason_code"] is None
    assert node_projection["status"] == NODE_STATUS_COMPLETED
    assert node_projection["blocking_reason_code"] is None
    assert dashboard_response.json()["data"]["ops_strip"]["active_tickets"] == 0
    assert dashboard_response.json()["data"]["ops_strip"]["blocked_nodes"] == 0
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == []


def test_board_reject_command_resolves_open_approval(client):
    approval = _seed_review_request(client, workflow_id="wf_reject")

    response = client.post(
        "/api/v1/commands/board-reject",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "board_comment": "Current direction is too weak.",
            "rejection_reasons": ["visual_impact_insufficient"],
            "idempotency_key": f"board-reject:{approval['approval_id']}:1",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_reject",
        "node_homepage_visual",
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_REJECTED
    assert updated["payload"]["resolution"]["decision_action"] == "REJECT"
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REJECTED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_REWORK_REQUIRED
    assert ticket_projection["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED
    assert node_projection["status"] == NODE_STATUS_REWORK_REQUIRED
    assert node_projection["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED
    assert dashboard_response.json()["data"]["ops_strip"]["active_tickets"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["blocked_nodes"] == 0
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == []


def test_modify_constraints_command_resolves_open_approval(client):
    approval = _seed_review_request(client, workflow_id="wf_modify")

    response = client.post(
        "/api/v1/commands/modify-constraints",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "constraint_patch": {
                "add_rules": ["Strengthen first-screen contrast and hierarchy"],
                "remove_rules": [],
                "replace_rules": [],
            },
            "board_comment": "Rework with stronger hierarchy.",
            "idempotency_key": f"board-modify:{approval['approval_id']}:1",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_modify",
        "node_homepage_visual",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_MODIFIED_CONSTRAINTS
    assert updated["payload"]["resolution"]["decision_action"] == "MODIFY_CONSTRAINTS"
    assert ticket_projection["status"] == TICKET_STATUS_REWORK_REQUIRED
    assert ticket_projection["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS
    assert node_projection["status"] == NODE_STATUS_REWORK_REQUIRED
    assert node_projection["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS


def test_stale_board_command_is_rejected_without_resolving_approval(client):
    approval = _seed_review_request(client, workflow_id="wf_stale")

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"] + 1,
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:stale",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_APPROVED) == 0


def test_ticket_create_is_rejected_when_node_is_blocked_for_board_review(client):
    _seed_review_request(client)

    response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_visual_002"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "BLOCKED_FOR_BOARD_REVIEW" in response.json()["reason"]


def test_ticket_create_is_rejected_when_node_is_completed(client):
    _create_lease_and_start_ticket(client)
    client.post("/api/v1/commands/ticket-complete", json=_ticket_complete_payload(include_review_request=False))

    response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_visual_002"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "COMPLETED" in response.json()["reason"]


def test_ticket_complete_is_allowed_after_rework_required(client):
    approval = _seed_review_request(client, workflow_id="wf_rework")
    reject_response = client.post(
        "/api/v1/commands/board-reject",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "board_comment": "Current direction is too weak.",
            "rejection_reasons": ["visual_impact_insufficient"],
            "idempotency_key": f"board-reject:{approval['approval_id']}:rework",
        },
    )
    assert reject_response.json()["status"] == "ACCEPTED"

    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_rework",
        ticket_id="tkt_visual_002",
        attempt_no=2,
    )
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(
            workflow_id="wf_rework",
            ticket_id="tkt_visual_002",
            include_review_request=False,
        ),
    )
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_rework",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert node_projection["latest_ticket_id"] == "tkt_visual_002"
    assert node_projection["status"] == NODE_STATUS_COMPLETED


def test_board_command_is_rejected_when_projection_is_not_currently_blocked(client):
    approval = _seed_review_request(client, workflow_id="wf_guard")
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE ticket_projection SET status = ?, blocking_reason_code = NULL WHERE ticket_id = ?",
            (TICKET_STATUS_COMPLETED, "tkt_visual_001"),
        )
        connection.execute(
            """
            UPDATE node_projection
            SET status = ?, blocking_reason_code = NULL
            WHERE workflow_id = ? AND node_id = ?
            """,
            (NODE_STATUS_COMPLETED, "wf_guard", "node_homepage_visual"),
        )

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:projection-guard",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "blocked for board review" in response.json()["reason"].lower()


def test_event_stream_returns_incremental_events_after_cursor(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]

    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP B"))

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "BOARD_DIRECTIVE_RECEIVED" in body
    assert "WORKFLOW_CREATED" in body
    assert "event: heartbeat" in body


def test_ticket_complete_stream_carries_ticket_and_review_events(client):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    _create_lease_and_start_ticket(client)
    client.post("/api/v1/commands/ticket-complete", json=_ticket_complete_payload())

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_CREATED" in body
    assert "TICKET_LEASED" in body
    assert "TICKET_STARTED" in body
    assert "TICKET_COMPLETED" in body
    assert "BOARD_REVIEW_REQUIRED" in body
    assert "tkt_visual_001" in body
    assert "node_homepage_visual" in body


def test_ticket_fail_and_retry_stream_carries_failure_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(failure_kind="SCHEMA_ERROR"),
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_FAILED" in body
    assert "TICKET_RETRY_SCHEDULED" in body


def test_scheduler_timeout_stream_carries_timeout_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post("/api/v1/commands/scheduler-tick", json=_scheduler_tick_payload(idempotency_key="scheduler-tick:stream"))

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_TIMED_OUT" in body
    assert "TICKET_RETRY_SCHEDULED" in body


def test_timeout_incident_stream_carries_incident_and_breaker_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:stream-incident-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:stream-incident-second"),
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "INCIDENT_OPENED" in body
    assert "CIRCUIT_BREAKER_OPENED" in body


def test_incident_resolve_stream_carries_breaker_closed_and_incident_closed_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:close-stream-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:close-stream-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:stream"),
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "CIRCUIT_BREAKER_CLOSED" in body
    assert "INCIDENT_CLOSED" in body


def test_invalid_project_init_returns_422_without_writing_events(client):
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": "",
            "hard_constraints": [],
            "budget_cap": -1,
            "deadline_at": None,
        },
    )

    repository = client.app.state.repository
    assert response.status_code == 422
    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 0


def test_ticket_complete_review_request_emits_required_event(client):
    _seed_review_request(client, workflow_id="wf_event")

    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_COMPLETED) == 1
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REQUIRED) == 1
