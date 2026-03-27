from __future__ import annotations

from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_COMPLETED,
    EVENT_WORKFLOW_CREATED,
)


def _project_init_payload(goal: str, budget_cap: int = 500000) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": ["Keep governance explicit."],
        "budget_cap": budget_cap,
        "deadline_at": None,
    }


def _ticket_complete_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    include_review_request: bool = True,
) -> dict:
    payload = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": "node_homepage_visual",
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
                "compiled_context_bundle_ref": "ctx://homepage/visual-v1",
                "compile_manifest_ref": "manifest://homepage/visual-v1",
            },
            "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
            "draft_selected_option_id": "option_a",
            "comment_template": "",
            "inbox_title": "Review homepage visual milestone",
            "inbox_summary": "Visual milestone is blocked for board review.",
            "badges": ["visual", "board_gate"],
        }
    return payload


def _seed_review_request(client, workflow_id: str = "wf_seed") -> dict:
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(workflow_id=workflow_id),
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


def test_inbox_projection_returns_empty_items(client):
    response = client.get("/api/v1/projections/inbox")

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_ticket_complete_without_review_request_does_not_open_approval(client):
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(include_review_request=False),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["causation_hint"] == "ticket:tkt_visual_001"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_COMPLETED) == 1
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REQUIRED) == 0
    assert client.app.state.repository.list_open_approvals() == []


def test_inbox_and_dashboard_reflect_open_approval(client):
    _seed_review_request(client)

    inbox_response = client.get("/api/v1/projections/inbox")
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert inbox_response.status_code == 200
    items = inbox_response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["route_target"]["view"] == "review_room"
    assert dashboard_response.json()["data"]["inbox_counts"]["approvals_pending"] == 1


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
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_APPROVED
    assert updated["payload"]["resolution"]["decision_action"] == "APPROVE"
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_APPROVED) == 1


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
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_REJECTED
    assert updated["payload"]["resolution"]["decision_action"] == "REJECT"
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REJECTED) == 1


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
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_MODIFIED_CONSTRAINTS
    assert updated["payload"]["resolution"]["decision_action"] == "MODIFY_CONSTRAINTS"


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
    client.post("/api/v1/commands/ticket-complete", json=_ticket_complete_payload())

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_COMPLETED" in body
    assert "BOARD_REVIEW_REQUIRED" in body
    assert "tkt_visual_001" in body
    assert "node_homepage_visual" in body


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
