from __future__ import annotations

import json
from datetime import datetime

from app.contracts.advisory import BoardAdvisorySession
import app.core.runtime as runtime_module
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_OPEN,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_TIMED_OUT,
    INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
    INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from tests.test_api import (
    _approve_open_review,
    _artifact_storage_path,
    _create_lease_and_start_ticket,
    _delivery_closeout_package_result_submit_payload,
    _delivery_check_report_result_submit_payload,
    _ensure_scoped_workflow,
    _source_code_delivery_result_submit_payload,
    _maker_checker_result_submit_payload,
    _project_init_to_scope_approval,
    _seed_created_ticket,
    _seed_graph_patch_applied_event,
    _seed_review_request,
    _scheduler_tick_payload,
    _seed_worker,
    _suppress_ceo_shadow_side_effects,
    _ticket_result_submit_payload,
    _ticket_lease_payload,
    _ticket_start_payload,
)
from tests.test_scheduler_runner import (
    _build_mock_provider_responder,
    _ensure_runtime_provider_ready_for_ticket,
    _ticket_create_payload,
)


def _autopilot_project_init_payload(*, force_requirement_elicitation: bool = False) -> dict[str, object]:
    return {
        "north_star_goal": "做一个图书馆管理系统毕业设计",
        "hard_constraints": [
            "允许 CEO 代审当前项目。",
            "必须拆成大量原子任务。",
        ],
        "budget_cap": 500000,
        "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
        "force_requirement_elicitation": force_requirement_elicitation,
    }


def _persist_autopilot_workflow_profile(repository, workflow_id: str) -> None:
    with repository.transaction() as connection:
        row = connection.execute(
            """
            SELECT event_id, payload_json
            FROM events
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY sequence_no ASC
            LIMIT 1
            """,
            (workflow_id, "WORKFLOW_CREATED"),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["workflow_profile"] = "CEO_AUTOPILOT_FINE_GRAINED"
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload, sort_keys=True), row["event_id"]),
        )
        repository.refresh_projections(connection)


def test_project_init_persists_ceo_autopilot_profile(client):
    response = client.post(
        "/api/v1/commands/project-init",
        json=_autopilot_project_init_payload(),
    )
    assert response.status_code == 200
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    workflow = client.app.state.repository.get_workflow_projection(workflow_id)

    assert workflow is not None
    assert workflow["workflow_profile"] == "CEO_AUTOPILOT_FINE_GRAINED"


def test_workflow_uses_ceo_board_delegate_only_for_autopilot_profile():
    from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate

    assert workflow_uses_ceo_board_delegate({"workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"}) is True
    assert workflow_uses_ceo_board_delegate({"workflow_profile": "STANDARD"}) is False


def test_autopilot_project_init_auto_resolves_requirement_elicitation_and_restarts_with_architecture_brief(client):
    response = client.post(
        "/api/v1/commands/project-init",
        json=_autopilot_project_init_payload(force_requirement_elicitation=True),
    )

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")
    open_approvals = repository.list_open_approvals()
    created_events = [
        event
        for event in repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id and event["event_type"] == EVENT_TICKET_CREATED
    ]
    with repository.connection() as connection:
        approval_row = connection.execute(
            """
            SELECT * FROM approval_projection
            WHERE workflow_id = ? AND approval_type = ?
            ORDER BY created_at DESC, approval_id DESC
            LIMIT 1
            """,
            (workflow_id, "REQUIREMENT_ELICITATION"),
        ).fetchone()
        artifact_rows = connection.execute(
            """
            SELECT artifact_ref FROM artifact_index
            WHERE workflow_id = ? AND logical_path LIKE ?
            ORDER BY artifact_ref ASC
            """,
            (workflow_id, "%requirements-elicitation%"),
        ).fetchall()
        approval_projection = (
            repository.get_approval_by_id(connection, approval_row["approval_id"])
            if approval_row is not None
            else None
        )

    assert response.status_code == 200
    assert scope_ticket is None
    assert created_events
    assert created_events[0]["payload"]["output_schema_ref"] == "architecture_brief"
    assert created_events[0]["payload"]["node_id"] == "node_ceo_architecture_brief"
    assert approval_row is not None
    assert approval_row["status"] == APPROVAL_STATUS_APPROVED
    assert approval_row["resolved_by"] == "ceo_delegate"
    assert approval_projection is not None
    assert approval_projection["payload"]["review_pack"]["subject"]["source_graph_node_id"] == "node_ceo_architecture_brief"
    assert all(item["approval_type"] != "REQUIREMENT_ELICITATION" for item in open_approvals)
    assert artifact_rows


def test_standard_workflow_still_waits_at_requirement_elicitation_review(client):
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": "做一个图书馆管理系统毕业设计",
            "hard_constraints": ["保持治理明确。"],
            "budget_cap": 0,
            "force_requirement_elicitation": True,
        },
    )

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")
    open_approvals = repository.list_open_approvals()

    assert response.status_code == 200
    assert scope_ticket is None
    assert any(
        item["workflow_id"] == workflow_id
        and item["approval_type"] == "REQUIREMENT_ELICITATION"
        and item["status"] == APPROVAL_STATUS_OPEN
        for item in open_approvals
    )
    requirement_review = next(
        item
        for item in open_approvals
        if item["workflow_id"] == workflow_id
        and item["approval_type"] == "REQUIREMENT_ELICITATION"
        and item["status"] == APPROVAL_STATUS_OPEN
    )
    assert requirement_review["payload"]["review_pack"]["subject"]["source_graph_node_id"] == "node_ceo_architecture_brief"


def test_autopilot_auto_advance_resolves_generic_open_approval_via_ceo_delegate(client):
    workflow_id = "wf_autopilot_seed"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository

    _persist_autopilot_workflow_profile(repository, workflow_id)

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=approval["workflow_id"],
        idempotency_key_prefix=f"test-autopilot:{approval['approval_id']}",
        max_steps=2,
        max_dispatches=1,
    )

    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    ticket_projection = repository.get_current_ticket_projection("tkt_visual_001")

    assert updated is not None
    assert updated["status"] == APPROVAL_STATUS_APPROVED
    assert updated["resolved_by"] == "ceo_delegate"
    assert ticket_projection is not None
    assert ticket_projection["status"] == "COMPLETED"


def test_autopilot_auto_advance_resolves_provider_incident_and_retries_latest_failure(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.4")

    workflow_id = "wf_autopilot_provider_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot provider recovery",
    )
    repository = client.app.state.repository

    _persist_autopilot_workflow_profile(repository, workflow_id)

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_provider_failure",
            node_id="node_autopilot_provider_failure",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    lease_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json={
            "max_dispatches": 10,
            "idempotency_key": "scheduler-tick:autopilot-provider-incident-seed",
        },
    )
    leased_ticket = repository.get_current_ticket_projection("tkt_autopilot_provider_failure")
    assert leased_ticket is not None

    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": leased_ticket["ticket_id"],
            "node_id": leased_ticket["node_id"],
            "started_by": leased_ticket["lease_owner"],
            "idempotency_key": f"ticket-start:{workflow_id}:{leased_ticket['ticket_id']}",
        },
    )
    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": workflow_id,
            "ticket_id": leased_ticket["ticket_id"],
            "node_id": leased_ticket["node_id"],
            "failed_by": leased_ticket["lease_owner"],
            "failure_kind": "UPSTREAM_UNAVAILABLE",
            "failure_message": "Provider transport failed unexpectedly.",
            "failure_detail": {
                "provider_id": "prov_openai_compat",
                "provider_status_code": 503,
            },
            "idempotency_key": f"ticket-fail:{workflow_id}:{leased_ticket['ticket_id']}:provider",
        },
    )
    incident = repository.list_open_incidents()[0]

    provider_responder, observed_schema_refs = _build_mock_provider_responder()
    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", provider_responder)

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:provider-incident",
        max_steps=4,
        max_dispatches=10,
    )

    recovered_incident = repository.get_incident_projection(incident["incident_id"])
    node_projection = repository.get_current_node_projection(workflow_id, leased_ticket["node_id"])
    followup_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"
    assert recovered_incident is not None
    assert recovered_incident["status"] == "CLOSED"
    assert recovered_incident["circuit_breaker_state"] == "CLOSED"
    assert recovered_incident["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE"
    )
    assert recovered_incident["payload"]["resolved_by"] == "ceo_delegate"
    assert node_projection is not None
    assert node_projection["status"] == "COMPLETED"
    assert followup_ticket is not None
    assert followup_ticket["ticket_id"] != leased_ticket["ticket_id"]
    assert followup_ticket["retry_count"] == 1
    assert followup_ticket["status"] == "COMPLETED"
    assert "source_code_delivery" in observed_schema_refs


def test_autopilot_ticket_fail_with_pending_retry_does_not_open_ceo_shadow_pipeline_incident(
    client,
    monkeypatch,
):
    workflow_id = "wf_autopilot_failed_ticket_retry_guard"
    import app.core.ceo_proposer as ceo_proposer_module
    from app.core.provider_openai_compat import OpenAICompatProviderResult

    monkeypatch.setattr(
        ceo_proposer_module,
        "invoke_openai_compat_response",
        lambda config, rendered_payload: OpenAICompatProviderResult(
            output_text=json.dumps(ceo_proposer_module.build_no_action_batch("No action needed.").model_dump(mode="json")),
            response_id="resp_retry_guard",
        ),
    )

    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot failed ticket retry should not open a shadow incident.",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)
    _seed_worker(
        client,
        employee_id="emp_frontend_retry_guard",
        role_profile_refs=["frontend_engineer_primary"],
    )
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="architecture_brief",
    )

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_failed_ticket_retry_guard",
            node_id="node_ceo_architecture_brief",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="architecture_brief",
            allowed_write_set=["reports/governance/tkt_autopilot_failed_ticket_retry_guard/*"],
        ),
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_failed_ticket_retry_guard",
            node_id="node_ceo_architecture_brief",
            leased_by="emp_frontend_retry_guard",
        ),
    )
    leased_ticket = repository.get_current_ticket_projection("tkt_autopilot_failed_ticket_retry_guard")
    assert leased_ticket is not None
    current_node = repository.get_current_node_projection(workflow_id, "node_ceo_architecture_brief")
    current_runtime_node = repository.get_runtime_node_projection(workflow_id, "node_ceo_architecture_brief")
    assert current_node is not None
    assert current_runtime_node is not None

    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=leased_ticket["ticket_id"],
            node_id=leased_ticket["node_id"],
            started_by=leased_ticket["lease_owner"],
            expected_ticket_version=int(leased_ticket["version"]),
            expected_node_version=int(current_node["version"]),
            expected_runtime_node_version=int(current_runtime_node["version"]),
        ),
    )
    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": workflow_id,
            "ticket_id": leased_ticket["ticket_id"],
            "node_id": leased_ticket["node_id"],
            "failed_by": leased_ticket["lease_owner"],
            "failure_kind": "PROVIDER_BAD_RESPONSE",
            "failure_message": "Provider returned truncated JSON.",
            "idempotency_key": f"ticket-fail:{workflow_id}:{leased_ticket['ticket_id']}:retry-guard",
        },
    )

    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]
    node_projection = repository.get_current_node_projection(workflow_id, "node_ceo_architecture_brief")
    assert node_projection is not None
    retry_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        retry_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"
    assert retry_ticket is not None
    assert retry_ticket["ticket_id"] != leased_ticket["ticket_id"]
    assert retry_ticket["retry_count"] == 1
    assert retry_ticket["status"] in {"PENDING", "LEASED", "EXECUTING"}
    assert retry_created_spec["allowed_write_set"] == [
        f"reports/governance/{retry_ticket['ticket_id']}/*"
    ]
    assert open_incidents == []


def test_autopilot_auto_advance_restores_provider_incident_when_source_ticket_already_completed(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.4")

    workflow_id = "wf_autopilot_provider_restore_only"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot provider restore only",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    create_source_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_provider_source_completed",
            node_id="node_autopilot_provider_source_completed",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    lease_source_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json={
            "max_dispatches": 10,
            "idempotency_key": "scheduler-tick:autopilot-provider-restore-only-source",
        },
    )
    source_ticket = repository.get_current_ticket_projection("tkt_autopilot_provider_source_completed")
    assert source_ticket is not None

    start_source_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": source_ticket["ticket_id"],
            "node_id": source_ticket["node_id"],
            "started_by": source_ticket["lease_owner"],
            "idempotency_key": f"ticket-start:{workflow_id}:{source_ticket['ticket_id']}",
        },
    )

    incident_id = "inc_autopilot_provider_source_completed"
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="runtime",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": source_ticket["ticket_id"],
                "node_id": source_ticket["node_id"],
                "provider_id": "prov_openai_compat",
                "incident_type": "PROVIDER_EXECUTION_PAUSED",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "provider:prov_openai_compat",
                "pause_reason": "UPSTREAM_UNAVAILABLE",
                "latest_failure_kind": "UPSTREAM_UNAVAILABLE",
                "latest_failure_message": "Provider transport failed after a successful fallback run.",
                "latest_failure_fingerprint": "UPSTREAM_UNAVAILABLE",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="runtime",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": source_ticket["ticket_id"],
                "node_id": source_ticket["node_id"],
                "provider_id": "prov_openai_compat",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "provider:prov_openai_compat",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_COMPLETED,
            actor_type="worker",
            actor_id=str(source_ticket["lease_owner"]),
            workflow_id=workflow_id,
            idempotency_key=f"test-ticket-completed:{workflow_id}:{source_ticket['ticket_id']}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "ticket_id": source_ticket["ticket_id"],
                "node_id": source_ticket["node_id"],
                "completion_summary": "Primary provider failed, fallback succeeded, ticket still completed.",
                "artifact_refs": [],
                "produced_process_assets": [],
                "documentation_updates": [],
                "board_review_requested": False,
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:01+08:00"),
        )
        repository.refresh_projections(connection)

    create_blocked_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_provider_blocked",
            node_id="node_autopilot_provider_blocked",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )

    provider_responder, observed_schema_refs = _build_mock_provider_responder()
    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", provider_responder)

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:provider-restore-only",
        max_steps=4,
        max_dispatches=10,
    )

    recovered_incident = repository.get_incident_projection(incident_id)
    blocked_ticket = repository.get_current_ticket_projection("tkt_autopilot_provider_blocked")

    assert create_source_response.status_code == 200
    assert create_source_response.json()["status"] == "ACCEPTED"
    assert lease_source_response.status_code == 200
    assert lease_source_response.json()["status"] == "ACCEPTED"
    assert start_source_response.status_code == 200
    assert start_source_response.json()["status"] == "ACCEPTED"
    assert create_blocked_response.status_code == 200
    assert create_blocked_response.json()["status"] == "ACCEPTED"
    assert recovered_incident is not None
    assert recovered_incident["status"] == "RECOVERING"
    assert recovered_incident["circuit_breaker_state"] == "CLOSED"
    assert recovered_incident["payload"]["followup_action"] == "RESTORE_ONLY"
    assert blocked_ticket is not None
    assert blocked_ticket["status"] == "COMPLETED"
    assert "source_code_delivery" in observed_schema_refs


def test_autopilot_auto_advance_opens_ticket_graph_unavailable_incident_and_stops(
    client,
    monkeypatch,
):
    workflow_id = "wf_autopilot_graph_unavailable"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot graph incident should be explicit.",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    import app.core.workflow_auto_advance as workflow_auto_advance_module

    def _raise_graph_unavailable(*args, **kwargs):
        raise RuntimeError("ticket graph unavailable from ceo snapshot")

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "build_ceo_shadow_snapshot",
        _raise_graph_unavailable,
    )

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:graph-unavailable",
        max_steps=2,
        max_dispatches=10,
    )
    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:graph-unavailable-repeat",
        max_steps=2,
        max_dispatches=10,
    )

    open_incidents = [item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id]
    incident_opened_events = [
        event
        for event in repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id and event["event_type"] == EVENT_INCIDENT_OPENED
    ]
    breaker_opened_events = [
        event
        for event in repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id and event["event_type"] == EVENT_CIRCUIT_BREAKER_OPENED
    ]

    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "TICKET_GRAPH_UNAVAILABLE"
    assert open_incidents[0]["payload"]["source_component"] == "ceo_shadow_snapshot"
    assert open_incidents[0]["payload"]["source_stage"] == "ticket_graph_snapshot"
    assert open_incidents[0]["payload"]["error_class"] == "RuntimeError"
    assert "ticket graph unavailable" in open_incidents[0]["payload"]["error_message"]
    assert len(incident_opened_events) == 1
    assert len(breaker_opened_events) == 1
    assert open_incidents[0]["status"] == "OPEN"
    assert open_incidents[0]["circuit_breaker_state"] == "OPEN"


def test_autopilot_auto_advance_opens_placeholder_gate_incident_without_silent_fallback(client, monkeypatch):
    workflow_id = "wf_autopilot_placeholder_gate_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot should surface planned placeholder stagnation as an explicit incident.",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_gate_parent",
        node_id="node_placeholder_gate_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_COMPLETED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-completed:{workflow_id}:tkt_placeholder_gate_parent",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "ticket_id": "tkt_placeholder_gate_parent",
                "node_id": "node_placeholder_gate_parent",
            },
            occurred_at=datetime.fromisoformat("2026-04-17T09:40:00+08:00"),
        )
        repository.refresh_projections(connection)

    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_placeholder_gate_target"],
        add_nodes=[
            {
                "node_id": "node_placeholder_gate_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_placeholder_gate_parent",
                "dependency_node_ids": [],
            }
        ],
    )
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id)
    with repository.transaction() as connection:
        repository.create_board_advisory_session(
            connection,
            BoardAdvisorySession(
                session_id="adv_placeholder_gate_focus",
                workflow_id=workflow_id,
                approval_id="apr_placeholder_gate_focus",
                review_pack_id="rp_placeholder_gate_focus",
                trigger_type="CONSTRAINT_CHANGE",
                source_version=graph_snapshot.graph_version,
                governance_profile_ref="gp_placeholder_gate_focus",
                affected_nodes=["node_placeholder_gate_target"],
                working_turns=[],
                decision_pack_refs=[],
                board_decision=None,
                latest_patch_proposal_ref=None,
                latest_patch_proposal=None,
                approved_patch_ref="gp_placeholder_gate_patch",
                approved_patch=None,
                patched_graph_version=graph_snapshot.graph_version,
                latest_timeline_index_ref=None,
                latest_transcript_archive_artifact_ref=None,
                timeline_archive_version_int=None,
                focus_node_ids=["node_placeholder_gate_target"],
                latest_analysis_run_id=None,
                latest_analysis_status=None,
                latest_analysis_incident_id=None,
                latest_analysis_error=None,
                latest_analysis_trace_artifact_ref=None,
                status="APPLIED",
            ),
        )
        repository.refresh_projections(connection)

    import app.core.workflow_auto_advance as workflow_auto_advance_module

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "workflow_controller_effect",
        lambda snapshot: "NO_IMMEDIATE_FOLLOWUP",
    )

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:placeholder-gate",
        max_steps=2,
        max_dispatches=1,
    )

    open_incidents = [
        item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id
    ]
    incident_opened_events = [
        event
        for event in repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id and event["event_type"] == EVENT_INCIDENT_OPENED
    ]

    assert len(open_incidents) == 1
    incident = open_incidents[0]
    assert incident["incident_type"] == INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED
    assert incident["node_id"] == "node_placeholder_gate_target"
    assert incident["ticket_id"] is None
    assert incident["payload"]["reason_code"] == "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
    assert incident["payload"]["graph_version"] == graph_snapshot.graph_version
    assert incident["payload"]["materialization_hint"] == "create_ticket"
    assert incident["payload"]["trigger_type"] == "SCHEDULER_IDLE_MAINTENANCE"
    assert incident["payload"]["trigger_ref"].endswith(":0:controller-probe")
    assert len(incident_opened_events) == 1
    placeholder_projection = repository.get_planned_placeholder_projection(
        workflow_id,
        "node_placeholder_gate_target",
    )
    assert placeholder_projection is not None
    assert placeholder_projection["status"] == "BLOCKED"
    assert placeholder_projection["open_incident_id"] == incident["incident_id"]
    assert placeholder_projection["reason_code"] == "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
    assert repository.get_current_ticket_projection("tkt_placeholder_gate_target") is None
    runtime_node = repository.get_current_node_projection(workflow_id, "node_placeholder_gate_target")
    assert runtime_node is None


def test_autopilot_placeholder_gate_incident_is_idempotent_while_open(client, monkeypatch):
    workflow_id = "wf_autopilot_placeholder_gate_dedupe"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot should not reopen the same placeholder gate incident while it is still open.",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_gate_dedupe_parent",
        node_id="node_placeholder_gate_dedupe_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_COMPLETED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=(
                f"test-seed-ticket-completed:{workflow_id}:tkt_placeholder_gate_dedupe_parent"
            ),
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "ticket_id": "tkt_placeholder_gate_dedupe_parent",
                "node_id": "node_placeholder_gate_dedupe_parent",
            },
            occurred_at=datetime.fromisoformat("2026-04-17T09:41:00+08:00"),
        )
        repository.refresh_projections(connection)

    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_placeholder_gate_dedupe_target"],
        add_nodes=[
            {
                "node_id": "node_placeholder_gate_dedupe_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_placeholder_gate_dedupe_parent",
                "dependency_node_ids": [],
            }
        ],
    )
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id)
    with repository.transaction() as connection:
        repository.create_board_advisory_session(
            connection,
            BoardAdvisorySession(
                session_id="adv_placeholder_gate_dedupe",
                workflow_id=workflow_id,
                approval_id="apr_placeholder_gate_dedupe",
                review_pack_id="rp_placeholder_gate_dedupe",
                trigger_type="CONSTRAINT_CHANGE",
                source_version=graph_snapshot.graph_version,
                governance_profile_ref="gp_placeholder_gate_dedupe",
                affected_nodes=["node_placeholder_gate_dedupe_target"],
                working_turns=[],
                decision_pack_refs=[],
                board_decision=None,
                latest_patch_proposal_ref=None,
                latest_patch_proposal=None,
                approved_patch_ref="gp_placeholder_gate_dedupe_patch",
                approved_patch=None,
                patched_graph_version=graph_snapshot.graph_version,
                latest_timeline_index_ref=None,
                latest_transcript_archive_artifact_ref=None,
                timeline_archive_version_int=None,
                focus_node_ids=["node_placeholder_gate_dedupe_target"],
                latest_analysis_run_id=None,
                latest_analysis_status=None,
                latest_analysis_incident_id=None,
                latest_analysis_error=None,
                latest_analysis_trace_artifact_ref=None,
                status="APPLIED",
            ),
        )
        repository.refresh_projections(connection)

    import app.core.workflow_auto_advance as workflow_auto_advance_module

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "workflow_controller_effect",
        lambda snapshot: "NO_IMMEDIATE_FOLLOWUP",
    )

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:placeholder-gate-dedupe:first",
        max_steps=2,
        max_dispatches=1,
    )
    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:placeholder-gate-dedupe:second",
        max_steps=2,
        max_dispatches=1,
    )

    open_incidents = [
        item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id
    ]
    incident_opened_events = [
        event
        for event in repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id
        and event["event_type"] == EVENT_INCIDENT_OPENED
        and (event.get("payload") or {}).get("incident_type")
        == INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED
    ]

    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED
    assert len(incident_opened_events) == 1
    placeholder_projection = repository.get_planned_placeholder_projection(
        workflow_id,
        "node_placeholder_gate_dedupe_target",
    )
    assert placeholder_projection is not None
    assert placeholder_projection["status"] == "BLOCKED"


def test_autopilot_auto_advance_reruns_ceo_shadow_pipeline_incident(client, monkeypatch):
    workflow_id = "wf_autopilot_ceo_shadow_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot should rerun CEO shadow incidents explicitly.",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    incident_id = "inc_autopilot_ceo_shadow_1"
    fingerprint = f"{workflow_id}:SCHEDULER_IDLE_MAINTENANCE:scheduler:ceo:proposal:JSONDecodeError"
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "incident_type": INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": fingerprint,
                "trigger_type": "SCHEDULER_IDLE_MAINTENANCE",
                "trigger_ref": "scheduler:ceo",
                "source_stage": "proposal",
                "error_class": "JSONDecodeError",
                "error_message": "Invalid provider payload.",
                "failure_fingerprint": fingerprint,
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "circuit_breaker_state": "OPEN",
                "fingerprint": fingerprint,
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    import app.core.ticket_handlers as ticket_handlers_module

    rerun_calls: list[tuple[str, str, str | None]] = []

    def _fake_rerun(repository, *, workflow_id, trigger_type, trigger_ref, runtime_provider_store=None):
        rerun_calls.append((workflow_id, trigger_type, trigger_ref))
        return {
            "workflow_id": workflow_id,
            "trigger_type": trigger_type,
            "trigger_ref": trigger_ref,
            "accepted_actions": [],
            "rejected_actions": [],
            "executed_actions": [],
            "execution_summary": {
                "attempted_action_count": 0,
                "executed_action_count": 0,
                "duplicate_action_count": 0,
                "passthrough_action_count": 0,
                "deferred_action_count": 0,
                "failed_action_count": 0,
            },
            "effective_mode": "LOCAL_DETERMINISTIC",
            "provider_health_summary": "UNAVAILABLE",
            "fallback_reason": "deterministic mode",
            "deterministic_fallback_used": False,
            "deterministic_fallback_reason": None,
        }

    monkeypatch.setattr(ticket_handlers_module, "run_ceo_shadow_for_trigger", _fake_rerun)

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:ceo-shadow-incident",
        max_steps=2,
        max_dispatches=1,
    )

    recovered_incident = repository.get_incident_projection(incident_id)

    assert rerun_calls == [(workflow_id, "SCHEDULER_IDLE_MAINTENANCE", "scheduler:ceo")]
    assert recovered_incident is not None
    assert recovered_incident["status"] == "CLOSED"
    assert recovered_incident["circuit_breaker_state"] == "CLOSED"


def test_autopilot_auto_advance_restores_source_ticket_ceo_shadow_incident_without_rerunning_shadow(
    client,
    monkeypatch,
    set_ticket_time,
):
    workflow_id = "wf_autopilot_ceo_shadow_ticket_incident"
    source_ticket_id = "tkt_autopilot_ceo_shadow_ticket_incident"
    source_node_id = "node_autopilot_ceo_shadow_ticket_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot should restore source-ticket CEO shadow incidents instead of rerunning proposer.",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        retry_budget=1,
    )
    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(
            idempotency_key=f"scheduler-tick:{workflow_id}:autopilot-source-timeout",
        ),
    )

    incident_id = "inc_autopilot_ceo_shadow_ticket_incident"
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_TIMED_OUT,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-ticket-timeout:{workflow_id}:{source_ticket_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "ticket_id": source_ticket_id,
                "node_id": source_node_id,
                "failure_kind": "TIMEOUT_SLA_EXCEEDED",
                "failure_message": "Ticket exceeded timeout SLA.",
                "failure_detail": {"timeout_sla_sec": 1800},
                "failure_fingerprint": f"{workflow_id}:{source_node_id}:TIMEOUT_SLA_EXCEEDED",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:31:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "incident_type": INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
                "ticket_id": source_ticket_id,
                "node_id": source_node_id,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": f"{workflow_id}:TICKET_TIMED_OUT:{source_ticket_id}:proposal:JSONDecodeError",
                "trigger_type": "TICKET_TIMED_OUT",
                "trigger_ref": source_ticket_id,
                "source_stage": "proposal",
                "error_class": "JSONDecodeError",
                "error_message": "Invalid provider payload.",
                "failure_fingerprint": f"{workflow_id}:TICKET_TIMED_OUT:{source_ticket_id}:proposal:JSONDecodeError",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:32:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": source_ticket_id,
                "node_id": source_node_id,
                "circuit_breaker_state": "OPEN",
                "fingerprint": f"{workflow_id}:TICKET_TIMED_OUT:{source_ticket_id}:proposal:JSONDecodeError",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:32:00+08:00"),
        )
        repository.refresh_projections(connection)

    import app.core.ticket_handlers as ticket_handlers_module

    resolved_actions: list[str] = []
    rerun_calls: list[tuple[str, str, str | None]] = []

    def _fake_handle_incident_resolve(repository, payload):
        resolved_actions.append(payload.followup_action.value)
        return type("Ack", (), {"status": type("Status", (), {"value": "ACCEPTED"})()})()

    def _fake_rerun(repository, *, workflow_id, trigger_type, trigger_ref, runtime_provider_store=None):
        rerun_calls.append((workflow_id, trigger_type, trigger_ref))
        return {}

    monkeypatch.setattr(ticket_handlers_module, "handle_incident_resolve", _fake_handle_incident_resolve)
    monkeypatch.setattr(ticket_handlers_module, "run_ceo_shadow_for_trigger", _fake_rerun)

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:ceo-shadow-ticket-incident",
        max_steps=1,
        max_dispatches=1,
    )

    assert resolved_actions == ["RESTORE_AND_RETRY_LATEST_TIMEOUT"]
    assert rerun_calls == []


def test_autopilot_internal_delivery_rework_loop_converges_after_threshold(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_autopilot_build_rework_cap"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot rework convergence",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_build_rework",
        node_id="node_autopilot_build_rework",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_build_rework/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    with _suppress_ceo_shadow_side_effects():
        maker_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_autopilot_build_rework",
                node_id="node_autopilot_build_rework",
                include_review_request=True,
            ),
        )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    first_checker_ticket_id = repository.get_current_node_projection(
        workflow_id,
        "node_autopilot_build_rework",
    )["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=first_checker_ticket_id,
            node_id="node_autopilot_build_rework",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=first_checker_ticket_id,
            node_id="node_autopilot_build_rework",
            started_by="emp_checker_1",
        ),
    )
    with _suppress_ceo_shadow_side_effects():
        first_checker_result = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_maker_checker_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id=first_checker_ticket_id,
                node_id="node_autopilot_build_rework",
                review_status="CHANGES_REQUIRED",
                findings=[
                    {
                        "finding_id": "finding_build_scope_cap",
                        "severity": "high",
                        "category": "SCOPE_DISCIPLINE",
                        "headline": "Source code delivery drifted outside the locked scope.",
                        "summary": "Build bundle still includes extra non-MVP sections.",
                        "required_action": "Trim the source code delivery back to the locked scope before downstream checks.",
                        "blocking": True,
                    }
                ],
                idempotency_key=f"ticket-result-submit:{workflow_id}:{first_checker_ticket_id}:changes-required",
            ),
        )
    assert first_checker_result.status_code == 200
    assert first_checker_result.json()["status"] == "ACCEPTED"

    fix_ticket_id = repository.get_current_node_projection(
        workflow_id,
        "node_autopilot_build_rework",
    )["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_autopilot_build_rework",
            leased_by="emp_frontend_2",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_autopilot_build_rework",
            started_by="emp_frontend_2",
        ),
    )
    with _suppress_ceo_shadow_side_effects():
        fix_result = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id=fix_ticket_id,
                node_id="node_autopilot_build_rework",
                submitted_by="emp_frontend_2",
                include_review_request=True,
                written_artifact_path=f"artifacts/ui/scope-followups/{fix_ticket_id}/source-code.tsx",
                idempotency_key=f"ticket-result-submit:{workflow_id}:{fix_ticket_id}:implementation",
            ),
        )
    assert fix_result.status_code == 200
    assert fix_result.json()["status"] == "ACCEPTED"

    second_checker_ticket_id = repository.get_current_node_projection(
        workflow_id,
        "node_autopilot_build_rework",
    )["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=second_checker_ticket_id,
            node_id="node_autopilot_build_rework",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=second_checker_ticket_id,
            node_id="node_autopilot_build_rework",
            started_by="emp_checker_1",
        ),
    )
    with _suppress_ceo_shadow_side_effects():
        second_checker_result = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_maker_checker_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id=second_checker_ticket_id,
                node_id="node_autopilot_build_rework",
                review_status="CHANGES_REQUIRED",
                findings=[
                    {
                        "finding_id": "finding_build_scope_cap_followup",
                        "severity": "high",
                        "category": "DELIVERY_CLARITY",
                        "headline": "Source code delivery still lacks a concise final handoff summary.",
                        "summary": "The second pass fixed the scope issue, but the handoff notes are still too diffuse.",
                        "required_action": "Compress the handoff summary to the final MVP deliverable only.",
                        "blocking": True,
                    }
                ],
                idempotency_key=f"ticket-result-submit:{workflow_id}:{second_checker_ticket_id}:changes-required-again",
            ),
        )

    node_projection = repository.get_current_node_projection(workflow_id, "node_autopilot_build_rework")
    latest_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])

    assert second_checker_result.status_code == 200
    assert second_checker_result.json()["status"] == "ACCEPTED"
    assert node_projection is not None
    assert node_projection["status"] == "COMPLETED"
    assert latest_ticket is not None
    assert latest_ticket["ticket_id"] == second_checker_ticket_id
    assert latest_ticket["status"] == "COMPLETED"
    assert repository.list_open_incidents() == []
    assert repository.list_open_approvals() == []


def test_late_profile_flip_does_not_retrofit_standard_scope_chain_into_autopilot_report(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, scope_approval = _project_init_to_scope_approval(client)
    repository = client.app.state.repository

    with repository.transaction() as connection:
        row = connection.execute(
            """
            SELECT event_id, payload_json
            FROM events
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY sequence_no ASC
            LIMIT 1
            """,
            (workflow_id, "WORKFLOW_CREATED"),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["workflow_profile"] = "CEO_AUTOPILOT_FINE_GRAINED"
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload, sort_keys=True), row["event_id"]),
        )
        repository.refresh_projections(connection)

    _approve_open_review(client, scope_approval, idempotency_suffix="autopilot-report-scope")

    artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    artifact = repository.get_artifact_by_ref(artifact_ref)

    assert artifact is None


def test_autopilot_closeout_without_visual_milestone_still_writes_chain_report_and_marks_workflow_completed(
    client,
):
    workflow_id = "wf_autopilot_closeout_without_review"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout without visual milestone",
    )
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_no_review_build",
        node_id="node_autopilot_no_review_build",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_no_review_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    with _suppress_ceo_shadow_side_effects():
        build_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_autopilot_no_review_build",
                node_id="node_autopilot_no_review_build",
            ),
        )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_no_review_closeout",
        node_id="node_ceo_delivery_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        delivery_stage="CLOSEOUT",
        allowed_write_set=["20-evidence/closeout/tkt_autopilot_no_review_closeout/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the final delivery evidence.",
            "Must produce a structured closeout package.",
        ],
        parent_ticket_id="tkt_autopilot_no_review_build",
        input_artifact_refs=["art://runtime/tkt_autopilot_no_review_build/source-code.tsx"],
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_no_review_closeout",
            node_id="node_ceo_delivery_closeout",
            leased_by="emp_frontend_2",
        ),
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_no_review_closeout",
            node_id="node_ceo_delivery_closeout",
            started_by="emp_frontend_2",
        ),
    )
    with _suppress_ceo_shadow_side_effects():
        closeout_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json={
                **_delivery_closeout_package_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id="tkt_autopilot_no_review_closeout",
                    node_id="node_ceo_delivery_closeout",
                    final_artifact_refs=["art://runtime/tkt_autopilot_no_review_build/source-code.tsx"],
                ),
                "idempotency_key": (
                    "ticket-result-submit:wf_autopilot_closeout_without_review:"
                    "tkt_autopilot_no_review_closeout:closeout"
                ),
            },
        )

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:no-review-closeout",
        max_steps=1,
        max_dispatches=1,
    )

    artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    artifact = repository.get_artifact_by_ref(artifact_ref)
    workflow = repository.get_workflow_projection(workflow_id)

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert closeout_response.status_code == 200
    assert closeout_response.json()["status"] == "ACCEPTED"
    assert artifact is not None
    assert workflow is not None
    assert workflow["status"] == "COMPLETED"
    assert workflow["current_stage"] == "closeout"


def test_autopilot_closeout_batch_blocks_failed_delivery_check_report(client):
    from app.core import ceo_proposer

    workflow_id = "wf_autopilot_failed_check_blocks_closeout"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout must respect failed delivery checks",
    )
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_failed_check_build",
        node_id="node_failed_check_build",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_failed_check_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    with _suppress_ceo_shadow_side_effects():
        build_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_failed_check_build",
                node_id="node_failed_check_build",
            ),
        )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_failed_check_report",
        node_id="node_failed_check_report",
        leased_by="emp_checker_1",
        role_profile_ref="checker_primary",
        output_schema_ref="delivery_check_report",
        allowed_write_set=["reports/check/tkt_failed_check_report/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must check final delivery evidence.",
            "Must fail closed when evidence is missing.",
        ],
        delivery_stage="CHECK",
        parent_ticket_id="tkt_failed_check_build",
    )
    with _suppress_ceo_shadow_side_effects():
        check_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_delivery_check_report_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_failed_check_report",
                node_id="node_failed_check_report",
                status="FAIL",
                findings=[
                    {
                        "finding_id": "finding_missing_runtime_evidence",
                        "summary": "Runtime, QA, and documentation evidence are missing.",
                        "blocking": True,
                    }
                ],
            ),
        )

    batch = ceo_proposer._build_autopilot_closeout_batch(
        repository,
        {
            "workflow": {
                "workflow_id": workflow_id,
                "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
                "north_star_goal": "Close out only after passing checks.",
            },
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0},
            "nodes": [
                {"node_id": "node_failed_check_build", "status": "COMPLETED"},
                {"node_id": "node_failed_check_report", "status": "COMPLETED"},
            ],
            "employees": [
                {
                    "employee_id": "emp_frontend_2",
                    "state": "ACTIVE",
                    "role_profile_refs": ["frontend_engineer_primary"],
                }
            ],
        },
        "Create closeout only after gate passes.",
    )

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert check_response.status_code == 200
    assert check_response.json()["status"] == "ACCEPTED"
    assert batch is None


def test_autopilot_closeout_fail_closed_payload_does_not_complete_workflow(client):
    workflow_id = "wf_autopilot_fail_closed_closeout"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout must not complete fail-closed packages",
    )
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_fail_closed_build",
        node_id="node_fail_closed_build",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_fail_closed_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    with _suppress_ceo_shadow_side_effects():
        build_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_fail_closed_build",
                node_id="node_fail_closed_build",
            ),
        )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_fail_closed_closeout",
        node_id="node_ceo_delivery_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        delivery_stage="CLOSEOUT",
        allowed_write_set=["20-evidence/closeout/tkt_fail_closed_closeout/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the final delivery evidence.",
            "Must produce a structured closeout package.",
        ],
        parent_ticket_id="tkt_fail_closed_build",
        input_artifact_refs=["art://runtime/tkt_fail_closed_build/source-code.tsx"],
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_fail_closed_closeout",
            node_id="node_ceo_delivery_closeout",
            leased_by="emp_frontend_2",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_fail_closed_closeout",
            node_id="node_ceo_delivery_closeout",
            started_by="emp_frontend_2",
        ),
    )
    closeout_payload = _delivery_closeout_package_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_fail_closed_closeout",
        node_id="node_ceo_delivery_closeout",
        final_artifact_refs=["art://runtime/tkt_fail_closed_build/source-code.tsx"],
        idempotency_key=f"ticket-result-submit:{workflow_id}:tkt_fail_closed_closeout:closeout",
    )
    closeout_payload["payload"]["summary"] = "FAIL_CLOSED: delivery is not approved for completion."
    closeout_payload["payload"]["handoff_notes"] = [
        "FAIL_CLOSED",
        "This package is not approved for completion.",
    ]
    closeout_payload["written_artifacts"][0]["content_json"] = closeout_payload["payload"]
    with _suppress_ceo_shadow_side_effects():
        closeout_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=closeout_payload,
        )

    workflow = repository.get_workflow_projection(workflow_id)
    artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert closeout_response.status_code == 200
    assert closeout_response.json()["status"] == "ACCEPTED"
    assert workflow is not None
    assert workflow["status"] != "COMPLETED"
    assert workflow["current_stage"] != "closeout"
    assert repository.get_artifact_by_ref(artifact_ref) is None


def test_workflow_completion_materializes_chain_report_before_completed_projection(client):
    workflow_id = "wf_autopilot_closeout_contract"
    closeout_ticket_id = "tkt_autopilot_contract_closeout"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout completion contract",
    )
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_contract_build",
        node_id="node_autopilot_contract_build",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_contract_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    with _suppress_ceo_shadow_side_effects():
        build_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_autopilot_contract_build",
                node_id="node_autopilot_contract_build",
            ),
        )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=closeout_ticket_id,
        node_id="node_ceo_delivery_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        delivery_stage="CLOSEOUT",
        allowed_write_set=[f"20-evidence/closeout/{closeout_ticket_id}/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the final delivery evidence.",
            "Must produce a structured closeout package.",
        ],
        parent_ticket_id="tkt_autopilot_contract_build",
        input_artifact_refs=["art://runtime/tkt_autopilot_contract_build/source-code.tsx"],
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=closeout_ticket_id,
            node_id="node_ceo_delivery_closeout",
            leased_by="emp_frontend_2",
        ),
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=closeout_ticket_id,
            node_id="node_ceo_delivery_closeout",
            started_by="emp_frontend_2",
        ),
    )
    with _suppress_ceo_shadow_side_effects():
        closeout_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json={
                **_delivery_closeout_package_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=closeout_ticket_id,
                    node_id="node_ceo_delivery_closeout",
                    final_artifact_refs=["art://runtime/tkt_autopilot_contract_build/source-code.tsx"],
                ),
                "idempotency_key": f"ticket-result-submit:{workflow_id}:{closeout_ticket_id}:closeout",
            },
        )

    artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    artifact = repository.get_artifact_by_ref(artifact_ref)
    workflow = repository.get_workflow_projection(workflow_id)

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert closeout_response.status_code == 200
    assert closeout_response.json()["status"] == "ACCEPTED"
    assert workflow is not None
    assert workflow["status"] == "COMPLETED"
    assert workflow["current_stage"] == "closeout"
    assert artifact is not None
    assert artifact["ticket_id"] == closeout_ticket_id


def test_workflow_chain_report_ensure_is_idempotent_across_auto_advance_and_harness_replay(client):
    from app.core.workflow_autopilot import ensure_workflow_atomic_chain_report

    workflow_id = "wf_autopilot_chain_report_idempotent"
    closeout_ticket_id = "tkt_autopilot_idempotent_closeout"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout chain report idempotency",
    )
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_idempotent_build",
        node_id="node_autopilot_idempotent_build",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_idempotent_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    with _suppress_ceo_shadow_side_effects():
        build_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_source_code_delivery_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_autopilot_idempotent_build",
                node_id="node_autopilot_idempotent_build",
            ),
        )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=closeout_ticket_id,
        node_id="node_ceo_delivery_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        delivery_stage="CLOSEOUT",
        allowed_write_set=[f"20-evidence/closeout/{closeout_ticket_id}/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the final delivery evidence.",
            "Must produce a structured closeout package.",
        ],
        parent_ticket_id="tkt_autopilot_idempotent_build",
        input_artifact_refs=["art://runtime/tkt_autopilot_idempotent_build/source-code.tsx"],
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=closeout_ticket_id,
            node_id="node_ceo_delivery_closeout",
            leased_by="emp_frontend_2",
        ),
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=closeout_ticket_id,
            node_id="node_ceo_delivery_closeout",
            started_by="emp_frontend_2",
        ),
    )
    with _suppress_ceo_shadow_side_effects():
        closeout_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json={
                **_delivery_closeout_package_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=closeout_ticket_id,
                    node_id="node_ceo_delivery_closeout",
                    final_artifact_refs=["art://runtime/tkt_autopilot_idempotent_build/source-code.tsx"],
                ),
                "idempotency_key": f"ticket-result-submit:{workflow_id}:{closeout_ticket_id}:closeout",
            },
        )
    artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    production_artifact = repository.get_artifact_by_ref(artifact_ref)

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:chain-report-idempotent",
        max_steps=1,
        max_dispatches=1,
    )
    replay_ref = ensure_workflow_atomic_chain_report(repository, workflow_id=workflow_id)
    replay_artifact = repository.get_artifact_by_ref(artifact_ref)
    with repository.connection() as connection:
        artifact_count = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM artifact_index
            WHERE artifact_ref = ? AND lifecycle_status = ?
            """,
            (artifact_ref, "ACTIVE"),
        ).fetchone()["total"]

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert closeout_response.status_code == 200
    assert closeout_response.json()["status"] == "ACCEPTED"
    assert production_artifact is not None
    assert replay_ref == artifact_ref
    assert replay_artifact is not None
    assert replay_artifact["artifact_ref"] == production_artifact["artifact_ref"]
    assert artifact_count == 1


def test_autopilot_closeout_chain_report_ignores_stale_node_projection(client, monkeypatch):
    from app.core.workflow_autopilot import _workflow_closeout_state
    from app.core.workflow_completion import WorkflowCloseoutCompletion

    workflow_id = "wf_autopilot_closeout_stale_node_projection"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout should ignore stale node projection truth",
    )
    _persist_autopilot_workflow_profile(repository, workflow_id)

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_stale_build",
        node_id="node_autopilot_stale_build",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_stale_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    build_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_stale_build",
            node_id="node_autopilot_stale_build",
        ),
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_stale_closeout",
        node_id="node_ceo_delivery_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        delivery_stage="CLOSEOUT",
        allowed_write_set=["20-evidence/closeout/tkt_autopilot_stale_closeout/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the final delivery evidence.",
            "Must produce a structured closeout package.",
        ],
        parent_ticket_id="tkt_autopilot_stale_build",
        input_artifact_refs=["art://runtime/tkt_autopilot_stale_build/source-code.tsx"],
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_stale_closeout",
            node_id="node_ceo_delivery_closeout",
            leased_by="emp_frontend_2",
        ),
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_stale_closeout",
            node_id="node_ceo_delivery_closeout",
            started_by="emp_frontend_2",
        ),
    )
    closeout_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            **_delivery_closeout_package_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_autopilot_stale_closeout",
                node_id="node_ceo_delivery_closeout",
                final_artifact_refs=["art://runtime/tkt_autopilot_stale_build/source-code.tsx"],
            ),
            "idempotency_key": (
                "ticket-result-submit:wf_autopilot_closeout_stale_node_projection:"
                "tkt_autopilot_stale_closeout:closeout"
            ),
        },
    )
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET status = ?, latest_ticket_id = ?, updated_at = ?
            WHERE workflow_id = ?
            """,
            (
                "PENDING",
                "tkt_autopilot_stale_legacy_shadow",
                datetime.fromisoformat("2026-04-06T10:59:59+08:00"),
                workflow_id,
            ),
        )

    observed_node_statuses: list[str] = []

    def _fake_resolve_workflow_closeout_completion(**kwargs):
        observed_node_statuses.extend(str(item.get("status") or "") for item in kwargs["nodes"])
        return WorkflowCloseoutCompletion(
            closeout_ticket={"ticket_id": "tkt_autopilot_stale_closeout"},
            closeout_terminal_event={"event_type": "TICKET_COMPLETED"},
        )

    monkeypatch.setattr(
        "app.core.workflow_autopilot.resolve_workflow_closeout_completion",
        _fake_resolve_workflow_closeout_completion,
    )

    with repository.connection() as connection:
        closeout_state = _workflow_closeout_state(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert closeout_response.status_code == 200
    assert closeout_response.json()["status"] == "ACCEPTED"
    assert closeout_state is not None
    assert closeout_state[0]["ticket_id"] == "tkt_autopilot_stale_closeout"
    assert observed_node_statuses
    assert all(status == "COMPLETED" for status in observed_node_statuses)
