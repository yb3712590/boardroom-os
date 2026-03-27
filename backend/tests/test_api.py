from __future__ import annotations

from app.core.constants import EVENT_SYSTEM_INITIALIZED, EVENT_WORKFLOW_CREATED


def _project_init_payload(goal: str, budget_cap: int = 500000) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": ["Keep governance explicit."],
        "budget_cap": budget_cap,
        "deadline_at": None,
    }


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


def test_review_room_route_is_reserved_and_stable(client):
    response = client.get("/api/v1/projections/review-room/brp_missing")

    assert response.status_code == 404
    assert "reserved" in response.json()["detail"]


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
