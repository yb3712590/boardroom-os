from __future__ import annotations

from app.core.constants import TICKET_STATUS_COMPLETED, TICKET_STATUS_FAILED, TICKET_STATUS_PENDING
from app.core.runtime_provider_config import (
    OPENAI_COMPAT_PROVIDER_ID,
    RuntimeProviderConfigEntry,
    RuntimeProviderStoredConfig,
)
from app.scheduler_runner import run_scheduler_once


def _project_init_payload(goal: str) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": [
            "Keep governance explicit.",
            "Do not move workflow truth into the browser.",
        ],
        "budget_cap": 500000,
        "deadline_at": None,
    }


def _meeting_request_payload(
    workflow_id: str,
    *,
    topic: str = "Decide the homepage runtime contract",
    max_rounds: int = 4,
    meeting_type: str = "TECHNICAL_DECISION",
    participant_employee_ids: list[str] | None = None,
    recorder_employee_id: str = "emp_frontend_2",
    idempotency_key: str = "meeting-request:test",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "meeting_type": meeting_type,
        "topic": topic,
        "participant_employee_ids": participant_employee_ids or ["emp_frontend_2", "emp_checker_1"],
        "recorder_employee_id": recorder_employee_id,
        "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/runtime-contract.md"],
        "max_rounds": max_rounds,
        "idempotency_key": idempotency_key,
    }


def _ticket_lease_payload(
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    *,
    leased_by: str = "emp_checker_1",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "leased_by": leased_by,
        "lease_timeout_sec": 600,
        "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}:{leased_by}",
    }


def _ticket_start_payload(
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    *,
    started_by: str = "emp_checker_1",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "started_by": started_by,
        "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}:{started_by}",
    }


def _maker_checker_result_submit_payload(
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    *,
    review_status: str = "APPROVED_WITH_NOTES",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_checker_1",
        "result_status": "completed",
        "schema_version": "maker_checker_verdict_v1",
        "payload": {
            "summary": "Checker approved the technical decision meeting output.",
            "review_status": review_status,
            "findings": [],
        },
        "artifact_refs": [],
        "written_artifacts": [],
        "assumptions": [],
        "issues": [],
        "confidence": 0.9,
        "needs_escalation": False,
        "summary": "Checker verdict submitted.",
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:{review_status.lower()}",
    }


def _create_workflow(client, goal: str = "Meeting room workflow") -> str:
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload(goal))
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    return response.json()["causation_hint"].split(":", 1)[1]


def _set_fake_live_provider(client) -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=OPENAI_COMPAT_PROVIDER_ID,
                    adapter_kind="openai_compat",
                    label="OpenAI Compat",
                    enabled=True,
                    base_url="https://api.example.test/v1",
                    api_key="sk-test-secret",
                    model="gpt-5.3-codex",
                    timeout_sec=30.0,
                    reasoning_effort="medium",
                )
            ],
            role_bindings=[],
        )
    )


def test_meeting_request_creates_open_meeting_projection_and_ticket(client, set_ticket_time):
    set_ticket_time("2026-04-05T10:00:00+08:00")
    workflow_id = _create_workflow(client, goal="Open a technical decision meeting")

    response = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            idempotency_key="meeting-request:create-open-meeting",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["causation_hint"].startswith("meeting:")

    meeting_id = response.json()["causation_hint"].split(":", 1)[1]
    meeting_projection = client.get(f"/api/v1/projections/meetings/{meeting_id}")
    repository = client.app.state.repository
    meeting = meeting_projection.json()["data"]
    source_ticket = repository.get_current_ticket_projection(meeting["source_ticket_id"])
    with repository.connection() as connection:
        created_payload = repository.get_latest_ticket_created_payload(
            connection,
            meeting["source_ticket_id"],
        )
    meeting_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] in {"MEETING_REQUESTED", "MEETING_STARTED"}
        and (event.get("payload") or {}).get("meeting_id") == meeting_id
    ]

    assert meeting_projection.status_code == 200
    assert meeting["meeting_id"] == meeting_id
    assert meeting["meeting_type"] == "TECHNICAL_DECISION"
    assert meeting["status"] == "OPEN"
    assert meeting["current_round"] is None
    assert meeting["review_pack_id"] is None
    assert len(meeting["participants"]) == 2
    assert source_ticket is not None
    assert source_ticket["status"] == TICKET_STATUS_PENDING
    assert created_payload is not None
    assert created_payload["graph_contract"] == {"lane_kind": "execution"}
    assert meeting["source_graph_node_id"] == meeting["source_node_id"]
    assert meeting_events
    assert {
        (event.get("payload") or {}).get("source_graph_node_id")
        for event in meeting_events
    } == {meeting["source_graph_node_id"]}


def test_meeting_projection_exposes_source_graph_node_id(client):
    workflow_id = _create_workflow(client, goal="Meeting projection should expose graph identity")
    repository = client.app.state.repository
    with repository.connection() as connection:
        node_row = connection.execute(
            """
            SELECT * FROM node_projection
            WHERE workflow_id = ?
            ORDER BY updated_at ASC, node_id ASC
            LIMIT 1
            """,
            (workflow_id,),
        ).fetchone()
        assert node_row is not None
        node_projection = repository._convert_node_projection_row(node_row)
        meeting_id = "mtg_projection_graph_identity"
        repository.create_meeting_projection(
            connection,
            meeting_id=meeting_id,
            workflow_id=workflow_id,
            meeting_type="TECHNICAL_DECISION",
            topic="Keep the meeting projection graph-first",
            normalized_topic="keep the meeting projection graph first",
            status="OPEN",
            source_ticket_id=str(node_projection["latest_ticket_id"]),
            source_graph_node_id=str(node_projection["node_id"]),
            source_node_id="node_stale_legacy_meeting_subject",
            opened_at=node_projection["updated_at"],
            updated_at=node_projection["updated_at"],
            recorder_employee_id="emp_frontend_2",
            participants=[
                {
                    "employee_id": "emp_frontend_2",
                    "role_type": "frontend_engineer",
                    "meeting_responsibility": "recorder",
                    "is_recorder": True,
                }
            ],
        )

    response = client.get("/api/v1/projections/meetings/mtg_projection_graph_identity")

    assert response.status_code == 200
    meeting = response.json()["data"]
    assert meeting["source_node_id"] == "node_stale_legacy_meeting_subject"
    assert meeting["source_graph_node_id"] == str(node_projection["node_id"])


def test_meeting_request_rejects_duplicate_open_topic(client, set_ticket_time):
    set_ticket_time("2026-04-05T10:05:00+08:00")
    workflow_id = _create_workflow(client, goal="Reject duplicate meeting topic")

    first = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            topic="Lock the runtime contract",
            idempotency_key="meeting-request:duplicate:first",
        ),
    )
    duplicate = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            topic="Lock the runtime contract",
            idempotency_key="meeting-request:duplicate:second",
        ),
    )

    assert first.status_code == 200
    assert first.json()["status"] == "ACCEPTED"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "REJECTED"
    assert "already has an open meeting" in (duplicate.json()["reason"] or "")


def test_scheduler_runner_executes_meeting_rounds_and_routes_to_checker(client, set_ticket_time):
    set_ticket_time("2026-04-05T10:10:00+08:00")
    workflow_id = _create_workflow(client, goal="Execute a technical decision meeting")
    request_response = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            idempotency_key="meeting-request:execute-rounds",
        ),
    )
    meeting_id = request_response.json()["causation_hint"].split(":", 1)[1]

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:meeting-room-rounds",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    meeting_response = client.get(f"/api/v1/projections/meetings/{meeting_id}")
    meeting = meeting_response.json()["data"]
    source_ticket = repository.get_current_ticket_projection(meeting["source_ticket_id"])
    current_node = repository.get_current_node_projection(workflow_id, meeting["source_node_id"])
    checker_ticket = repository.get_current_ticket_projection(current_node["latest_ticket_id"])
    meeting_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"].startswith("MEETING_")
        and (event.get("payload") or {}).get("meeting_id") == meeting_id
    ]

    assert source_ticket is not None
    assert source_ticket["status"] == TICKET_STATUS_COMPLETED
    assert checker_ticket is not None
    assert checker_ticket["ticket_id"] != source_ticket["ticket_id"]
    assert checker_ticket["status"] == TICKET_STATUS_PENDING
    assert meeting_response.status_code == 200
    assert meeting["status"] == "CLOSED"
    assert len(meeting["rounds"]) == 4
    assert [round_item["round_type"] for round_item in meeting["rounds"]] == [
        "POSITION",
        "CHALLENGE",
        "PROPOSAL",
        "CONVERGENCE",
    ]
    assert any(event["event_type"] == "MEETING_ROUND_COMPLETED" for event in meeting_events)
    assert meeting["consensus_summary"]
    assert meeting["decision_record"]["format"] == "ADR_V1"
    assert meeting["decision_record"]["decision"]
    assert meeting["decision_record"]["archived_context_refs"] == [
        f"art://runtime/{meeting['source_ticket_id']}/meeting-digest.json"
    ]


def test_meeting_projection_backfills_review_pack_after_checker_approval(client, set_ticket_time):
    set_ticket_time("2026-04-05T10:20:00+08:00")
    workflow_id = _create_workflow(client, goal="Link meeting projection to board review")
    request_response = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            idempotency_key="meeting-request:link-review-pack",
        ),
    )
    meeting_id = request_response.json()["causation_hint"].split(":", 1)[1]

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:meeting-room-review-link",
        max_dispatches=10,
    )
    _set_fake_live_provider(client)

    repository = client.app.state.repository
    meeting = client.get(f"/api/v1/projections/meetings/{meeting_id}").json()["data"]
    checker_ticket_id = repository.get_current_node_projection(workflow_id, meeting["source_node_id"])["latest_ticket_id"]

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(workflow_id, checker_ticket_id, meeting["source_node_id"]),
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(workflow_id, checker_ticket_id, meeting["source_node_id"]),
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(workflow_id, checker_ticket_id, meeting["source_node_id"]),
    )

    refreshed = client.get(f"/api/v1/projections/meetings/{meeting_id}").json()["data"]
    approvals = repository.list_open_approvals()
    linked_approval = (
        repository.get_approval_by_review_pack_id(refreshed["review_pack_id"])
        if refreshed["review_pack_id"] is not None
        else None
    )

    assert lease_response.status_code == 200
    assert start_response.status_code == 200
    assert submit_response.status_code == 200
    assert approvals
    assert linked_approval is not None
    assert linked_approval["workflow_id"] == workflow_id
    assert refreshed["review_status"] == "BOARD_REVIEW_PENDING"


def test_meeting_projection_reads_decision_record_from_consensus_artifact(client, set_ticket_time):
    set_ticket_time("2026-04-05T10:25:00+08:00")
    workflow_id = _create_workflow(client, goal="Expose meeting ADR view")
    request_response = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            idempotency_key="meeting-request:decision-record-projection",
        ),
    )
    meeting_id = request_response.json()["causation_hint"].split(":", 1)[1]

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:meeting-room-decision-record",
        max_dispatches=10,
    )

    meeting = client.get(f"/api/v1/projections/meetings/{meeting_id}").json()["data"]

    assert meeting["decision_record"] is not None
    assert meeting["decision_record"]["format"] == "ADR_V1"
    assert "runtime contract" in meeting["decision_record"]["context"].lower()
    assert meeting["decision_record"]["archived_context_refs"] == [
        f"art://runtime/{meeting['source_ticket_id']}/meeting-digest.json"
    ]


def test_meeting_request_with_too_small_round_budget_fails_without_fake_completion(client, set_ticket_time):
    set_ticket_time("2026-04-05T10:30:00+08:00")
    workflow_id = _create_workflow(client, goal="Fail meeting when round budget is too small")
    request_response = client.post(
        "/api/v1/commands/meeting-request",
        json=_meeting_request_payload(
            workflow_id,
            max_rounds=2,
            idempotency_key="meeting-request:no-consensus",
        ),
    )
    meeting_id = request_response.json()["causation_hint"].split(":", 1)[1]

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:meeting-room-no-consensus",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    meeting = client.get(f"/api/v1/projections/meetings/{meeting_id}").json()["data"]
    source_ticket = repository.get_current_ticket_projection(meeting["source_ticket_id"])

    assert meeting["status"] == "NO_CONSENSUS"
    assert meeting["review_pack_id"] is None
    assert "round budget" in (meeting["no_consensus_reason"] or "").lower()
    assert source_ticket is not None
    assert source_ticket["status"] == TICKET_STATUS_FAILED
