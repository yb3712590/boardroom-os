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
    EVENT_WORKFLOW_CREATED,
)
from app.core.time import now_local


def _project_init_payload(goal: str, budget_cap: int = 500000) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": ["Keep governance explicit."],
        "budget_cap": budget_cap,
        "deadline_at": None,
    }


def _seed_review_request(client, workflow_id: str = "wf_seed") -> dict:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        return repository.create_approval_request(
            connection,
            workflow_id=workflow_id,
            approval_type="VISUAL_MILESTONE",
            requested_by="system",
            review_pack={
                "meta": {
                    "review_pack_version": 1,
                    "workflow_id": workflow_id,
                    "review_type": "VISUAL_MILESTONE",
                    "created_at": now_local().isoformat(),
                    "priority": "high",
                },
                "subject": {
                    "title": "Review homepage visual milestone",
                    "source_node_id": "node_homepage_visual",
                    "blocking_scope": "NODE_ONLY",
                },
                "recommendation": {
                    "recommended_action": "APPROVE",
                    "recommended_option_id": "option_a",
                    "summary": "Option A is the strongest current draft.",
                },
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "High-contrast review candidate.",
                    },
                    {
                        "option_id": "option_b",
                        "label": "Option B",
                        "summary": "Lower contrast fallback.",
                    },
                ],
            },
            available_actions=["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
            draft_defaults={"selected_option_id": "option_a", "comment_template": ""},
            inbox_title="Review homepage visual milestone",
            inbox_summary="Visual milestone is blocked for board review.",
            badges=["visual", "board_gate"],
            priority="high",
            occurred_at=now_local(),
            idempotency_key=f"seed-review:{workflow_id}",
        )


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


def test_seed_review_request_emits_required_event(client):
    _seed_review_request(client, workflow_id="wf_event")

    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REQUIRED) == 1
