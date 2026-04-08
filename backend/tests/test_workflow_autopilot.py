from __future__ import annotations

import json
from datetime import datetime

import app.core.runtime as runtime_module
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_OPEN,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
)
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from tests.test_api import (
    _approve_open_review,
    _artifact_storage_path,
    _create_lease_and_start_ticket,
    _delivery_closeout_package_result_submit_payload,
    _ensure_scoped_workflow,
    _implementation_bundle_result_submit_payload,
    _maker_checker_result_submit_payload,
    _project_init_to_scope_approval,
    _seed_created_ticket,
    _scope_followup_payload,
    _seed_review_request,
    _staged_scope_followup_tickets,
    _ticket_lease_payload,
    _ticket_start_payload,
)
from tests.test_scheduler_runner import _build_mock_provider_responder, _ticket_create_payload


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

    assert response.status_code == 200
    assert scope_ticket is None
    assert created_events
    assert created_events[0]["payload"]["output_schema_ref"] == "architecture_brief"
    assert created_events[0]["payload"]["node_id"] == "node_ceo_architecture_brief"
    assert approval_row is not None
    assert approval_row["status"] == APPROVAL_STATUS_APPROVED
    assert approval_row["resolved_by"] == "ceo_delegate"
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
            output_schema_ref="implementation_bundle",
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
    assert "implementation_bundle" in observed_schema_refs


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
            output_schema_ref="implementation_bundle",
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
            output_schema_ref="implementation_bundle",
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
    assert "implementation_bundle" in observed_schema_refs


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
        output_schema_ref="implementation_bundle",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_build_rework/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured implementation bundle.",
        ],
        delivery_stage="BUILD",
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_implementation_bundle_result_submit_payload(
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
                    "headline": "Implementation bundle drifted outside the locked scope.",
                    "summary": "Build bundle still includes extra non-MVP sections.",
                    "required_action": "Trim the implementation bundle back to the locked scope before downstream checks.",
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
    fix_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_implementation_bundle_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_autopilot_build_rework",
            submitted_by="emp_frontend_2",
            include_review_request=True,
            written_artifact_path="artifacts/ui/scope-followups/tkt_autopilot_build_rework/implementation-bundle.json",
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
                    "headline": "Implementation bundle still lacks a concise final handoff summary.",
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


def test_autopilot_workflow_writes_human_readable_atomic_chain_report_after_closeout(client, set_ticket_time):
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

    consensus_artifact_ref = scope_approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, scope_approval)
    payload["followup_tickets"] = _staged_scope_followup_tickets("tkt_autopilot_report")
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    _approve_open_review(client, scope_approval, idempotency_suffix="autopilot-report-scope")

    artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    artifact = repository.get_artifact_by_ref(artifact_ref)

    assert artifact is not None
    assert artifact["logical_path"] == f"reports/workflow-chain/{workflow_id}/workflow-chain-report.json"
    payload = json.loads(
        repository.artifact_store.read_bytes(
            artifact["storage_relpath"],
            storage_object_key=artifact.get("storage_object_key"),
        ).decode("utf-8")
    )
    assert payload["workflow_id"] == workflow_id
    assert payload["sections"][0]["section_id"] == "project_overview"
    assert any(item["dependency_gate_refs"] for item in payload["atomic_tasks"])


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
        output_schema_ref="implementation_bundle",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_no_review_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved delivery slice.",
            "Must produce a structured implementation bundle.",
        ],
        delivery_stage="BUILD",
    )
    build_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_implementation_bundle_result_submit_payload(
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
        allowed_write_set=["reports/closeout/tkt_autopilot_no_review_closeout/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the final delivery evidence.",
            "Must produce a structured closeout package.",
        ],
        parent_ticket_id="tkt_autopilot_no_review_build",
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
    closeout_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            **_delivery_closeout_package_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_autopilot_no_review_closeout",
                node_id="node_ceo_delivery_closeout",
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
