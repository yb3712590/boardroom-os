from __future__ import annotations

import json
from datetime import datetime

import tests.test_api as api_test_helpers
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)
from app.core.role_hooks import (
    HookGateResult,
    HookGateStatus,
    RoleHookSpec,
    evaluate_ticket_required_hook_gate,
    open_required_hook_gate_incident,
    scan_and_open_required_hook_gate_incidents,
    replay_required_hook_receipts,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.constants import EVENT_TICKET_CREATED
from tests.test_api import _incident_resolve_payload
from tests.test_api import (
    _delivery_check_report_result_submit_payload,
    _maker_checker_result_submit_payload,
    _ticket_result_submit_payload,
)
from tests.test_project_workspace_hooks import (
    _closeout_result_submit_payload,
    _governance_result_submit_payload,
    _project_init_payload,
    _source_code_delivery_result_submit_payload,
    _ticket_create_payload,
    _ticket_lease_payload,
    _ticket_start_payload,
)


def _create_and_start_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    output_schema_ref: str,
) -> None:
    create_payload = _ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id)
    create_payload["output_schema_ref"] = output_schema_ref
    lease_owner = "emp_frontend_2"
    if output_schema_ref == ARCHITECTURE_BRIEF_SCHEMA_REF:
        create_payload["allowed_write_set"] = ["10-project/docs/*"]
        create_payload["delivery_stage"] = "BUILD"
    elif output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        create_payload["delivery_stage"] = "BUILD"
    elif output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        create_payload["role_profile_ref"] = "checker_primary"
        create_payload["allowed_write_set"] = [f"reports/check/{ticket_id}/*"]
        create_payload["delivery_stage"] = "CHECK"
        lease_owner = "emp_checker_1"
    elif output_schema_ref == UI_MILESTONE_REVIEW_SCHEMA_REF:
        create_payload["allowed_write_set"] = [
            "artifacts/ui/homepage/*",
            f"reports/review/{ticket_id}/*",
        ]
        create_payload["delivery_stage"] = "REVIEW"
    elif output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF:
        create_payload["role_profile_ref"] = "checker_primary"
        create_payload["allowed_write_set"] = [f"reports/review/{ticket_id}/*"]
        create_payload["delivery_stage"] = "REVIEW"
        lease_owner = "emp_checker_1"
    elif output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        create_payload["allowed_write_set"] = [f"20-evidence/closeout/{ticket_id}/*"]
        create_payload["input_artifact_refs"] = ["art://runtime/tkt_build_001/source-code.tsx"]
        create_payload["delivery_stage"] = "CLOSEOUT"
    api_test_helpers._ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref=str(create_payload.get("role_profile_ref") or ""),
        output_schema_ref=output_schema_ref,
    )
    create_response = client.post("/api/v1/commands/ticket-create", json=create_payload)
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    lease_payload = _ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id)
    lease_payload["leased_by"] = lease_owner
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=lease_payload,
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    start_payload = _ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id)
    start_payload["started_by"] = lease_owner
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=start_payload,
    )
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"


def _receipt_root(client, workflow_id: str, ticket_id: str):
    from app.config import get_settings

    return (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
    )


def _assert_command_accepted(response) -> None:
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"


def _assert_receipt_exists(path) -> None:
    assert path.is_file(), f"expected hook receipt to exist before deletion: {path}"


def test_required_hook_gate_reports_missing_artifact_capture_for_review_evidence_ticket(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Review evidence should block until artifact capture is materialized."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_review_hook_scope_001"
    node_id = "node_review_hook_scope_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    _assert_command_accepted(submit_response)

    artifact_capture_path = _receipt_root(client, workflow_id, ticket_id) / "artifact-capture.json"
    _assert_receipt_exists(artifact_capture_path)
    artifact_capture_path.unlink()

    repository = client.app.state.repository
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
        )

    assert result.gate_mode == "required"
    assert result.applicability == "workspace_managed_review_evidence"
    assert result.status == HookGateStatus.BLOCKED
    assert result.required_hook_ids == ["artifact_capture"]
    assert result.checked_hook_ids == ["artifact_capture"]
    assert result.missing_hook_ids == ["artifact_capture"]
    assert result.reason_code == "REQUIRED_HOOK_PENDING:artifact_capture"
    assert result.incident_fingerprint is not None


def test_required_hook_gate_reports_missing_required_hook_for_workspace_source_delivery(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source delivery should block when a required hook receipt is missing."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_gate_missing_001"
    node_id = "node_hook_gate_missing_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )
    _assert_command_accepted(submit_response)

    git_receipt_path = _receipt_root(client, workflow_id, ticket_id) / "git-closeout.json"
    _assert_receipt_exists(git_receipt_path)
    git_receipt_path.unlink()

    repository = client.app.state.repository
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
        )

    assert result.gate_mode == "required"
    assert result.applicability == "workspace_managed_source_code_delivery"
    assert result.status == HookGateStatus.BLOCKED
    assert result.required_hook_ids == ["worker_postrun", "evidence_capture", "git_closeout"]
    assert result.missing_hook_ids == ["git_closeout"]
    assert result.reason_code == "REQUIRED_HOOK_PENDING:git_closeout"
    assert result.incident_fingerprint is not None


def test_required_hook_gate_reports_missing_artifact_capture_for_governance_ticket(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Governance tickets should block when artifact capture is missing."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_gov_hook_artifact_capture_001"
    node_id = "node_gov_hook_artifact_capture_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_governance_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    _assert_command_accepted(submit_response)

    artifact_capture_path = _receipt_root(client, workflow_id, ticket_id) / "artifact-capture.json"
    _assert_receipt_exists(artifact_capture_path)
    artifact_capture_path.unlink()

    repository = client.app.state.repository
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
        )

    assert result.gate_mode == "required"
    assert result.status == HookGateStatus.BLOCKED
    assert result.required_hook_ids == ["artifact_capture"]
    assert result.missing_hook_ids == ["artifact_capture"]
    assert result.reason_code == "REQUIRED_HOOK_PENDING:artifact_capture"


def test_required_hook_gate_reports_missing_artifact_capture_for_delivery_check_report(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Delivery check review evidence should also block on missing artifact capture."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_delivery_check_hook_001"
    node_id = "node_delivery_check_hook_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_check_report_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    _assert_command_accepted(submit_response)

    artifact_capture_path = _receipt_root(client, workflow_id, ticket_id) / "artifact-capture.json"
    _assert_receipt_exists(artifact_capture_path)
    artifact_capture_path.unlink()

    repository = client.app.state.repository
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
        )

    assert result.gate_mode == "required"
    assert result.applicability == "workspace_managed_review_evidence"
    assert result.status == HookGateStatus.BLOCKED
    assert result.required_hook_ids == ["artifact_capture"]
    assert result.missing_hook_ids == ["artifact_capture"]
    assert result.reason_code == "REQUIRED_HOOK_PENDING:artifact_capture"


def test_required_hook_gate_registry_is_the_protocol_boundary(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("A test-only hook spec should enter the gate without graph changes."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_registry_001"
    node_id = "node_hook_registry_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )
    _assert_command_accepted(submit_response)

    repository = client.app.state.repository
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
            registry=[
                RoleHookSpec(
                    hook_id="test_protocol_hook",
                    lifecycle_event="RESULT_ACCEPTED",
                    deliverable_kind="source_code_delivery",
                    required_for_gate=True,
                    receipt_filename="test-protocol-hook.json",
                )
            ],
        )

    assert result.status == HookGateStatus.BLOCKED
    assert result.required_hook_ids == ["test_protocol_hook"]
    assert result.missing_hook_ids == ["test_protocol_hook"]
    assert result.reason_code == "REQUIRED_HOOK_PENDING:test_protocol_hook"


def test_replay_required_hook_receipts_restores_missing_receipts_idempotently(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Replay should restore only missing required hook receipts."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_replay_001"
    node_id = "node_hook_replay_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )
    _assert_command_accepted(submit_response)

    receipt_root = _receipt_root(client, workflow_id, ticket_id)
    postrun_path = receipt_root / "worker-postrun.json"
    evidence_path = receipt_root / "evidence-capture.json"
    _assert_receipt_exists(postrun_path)
    _assert_receipt_exists(evidence_path)
    original_postrun = json.loads(postrun_path.read_text(encoding="utf-8"))
    evidence_path.unlink()

    repository = client.app.state.repository
    first_result = replay_required_hook_receipts(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
    )
    second_result = replay_required_hook_receipts(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
    )

    assert first_result.replayed_hook_ids == ["evidence_capture"]
    assert second_result.replayed_hook_ids == []
    assert json.loads(postrun_path.read_text(encoding="utf-8")) == original_postrun
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["ticket_id"] == ticket_id


def test_replay_required_hook_receipts_restores_missing_review_evidence_receipt_idempotently(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Review evidence replay should restore missing artifact capture only once."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_review_hook_replay_001"
    node_id = "node_review_hook_replay_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    _assert_command_accepted(submit_response)

    receipt_root = _receipt_root(client, workflow_id, ticket_id)
    artifact_capture_path = receipt_root / "artifact-capture.json"
    _assert_receipt_exists(artifact_capture_path)
    artifact_capture_path.unlink()

    repository = client.app.state.repository
    first_result = replay_required_hook_receipts(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
    )
    second_result = replay_required_hook_receipts(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
    )

    assert first_result.replayed_hook_ids == ["artifact_capture"]
    assert second_result.replayed_hook_ids == []
    assert json.loads(artifact_capture_path.read_text(encoding="utf-8")) == {
        "ticket_id": ticket_id,
        "artifact_refs": [],
        "written_artifact_paths": [],
    }


def test_required_hook_gate_scan_opens_single_incident_for_missing_receipt(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Missing required hook receipts should open a formal incident."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_incident_001"
    node_id = "node_hook_incident_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )
    _assert_command_accepted(submit_response)

    git_closeout_path = _receipt_root(client, workflow_id, ticket_id) / "git-closeout.json"
    _assert_receipt_exists(git_closeout_path)
    git_closeout_path.unlink()

    repository = client.app.state.repository
    scan_and_open_required_hook_gate_incidents(
        repository,
        workflow_id=workflow_id,
        idempotency_key_base=f"hook-gate:{workflow_id}",
    )
    scan_and_open_required_hook_gate_incidents(
        repository,
        workflow_id=workflow_id,
        idempotency_key_base=f"hook-gate:{workflow_id}:repeat",
    )

    relevant_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item.get("ticket_id") == ticket_id
    ]

    assert len(relevant_incidents) == 1
    assert relevant_incidents[0]["incident_type"] == "REQUIRED_HOOK_GATE_BLOCKED"
    assert relevant_incidents[0]["ticket_id"] == ticket_id
    assert relevant_incidents[0]["node_id"] == node_id
    assert relevant_incidents[0]["payload"]["missing_hook_ids"] == ["git_closeout"]


def test_required_hook_gate_scan_uses_review_lane_runtime_truth_even_when_node_projection_is_stale(
    client,
) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Required hook gate scan must not trust stale shared node projection state."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    maker_ticket_id = "tkt_hook_review_scan_maker_001"
    checker_ticket_id: str | None = None
    node_id = "node_hook_review_scan_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=maker_ticket_id,
        node_id=node_id,
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=maker_ticket_id,
            node_id=node_id,
        ),
    )
    assert maker_response.status_code == 200

    repository = client.app.state.repository
    checker_ticket_id = "tkt_hook_review_scan_checker_001"
    with repository.transaction() as connection:
        checker_payload = _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
        )
        checker_payload["output_schema_ref"] = MAKER_CHECKER_VERDICT_SCHEMA_REF
        checker_payload["delivery_stage"] = "REVIEW"
        checker_payload["graph_contract"] = {"lane_kind": "review"}
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-created:{workflow_id}:{checker_ticket_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload=checker_payload,
            occurred_at=datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        )
        repository.refresh_projections(connection)
        connection.execute(
            """
            UPDATE node_projection
            SET latest_ticket_id = ?, version = version + 1
            WHERE workflow_id = ? AND node_id = ?
            """,
            (maker_ticket_id, workflow_id, node_id),
        )

    def _stub_evaluate_ticket_required_hook_gate(*args, ticket, created_spec, **kwargs):
        if str(ticket.get("ticket_id") or "") == checker_ticket_id:
            return HookGateResult(
                gate_mode="required",
                applicability="workspace_managed_review_evidence",
                required_hook_ids=["artifact_capture"],
                checked_hook_ids=["artifact_capture"],
                missing_hook_ids=["artifact_capture"],
                status=HookGateStatus.BLOCKED,
                reason_code="REQUIRED_HOOK_PENDING:artifact_capture",
                reason_detail="artifact capture is missing for the review lane ticket",
                incident_fingerprint=f"{workflow_id}:{checker_ticket_id}:artifact_capture",
            )
        return HookGateResult(
            gate_mode="required",
            applicability="workspace_managed_review_evidence",
            required_hook_ids=[],
            checked_hook_ids=[],
            missing_hook_ids=[],
            status=HookGateStatus.PASSED,
            reason_code="HOOK_GATE_PASSED",
            reason_detail=None,
            incident_fingerprint=None,
        )

    import app.core.role_hooks as role_hooks_module

    original_evaluate = role_hooks_module.evaluate_ticket_required_hook_gate
    role_hooks_module.evaluate_ticket_required_hook_gate = _stub_evaluate_ticket_required_hook_gate
    try:
        scan_result = scan_and_open_required_hook_gate_incidents(
            repository,
            workflow_id=workflow_id,
            idempotency_key_base=f"hook-scan-review-lane:{workflow_id}",
        )
    finally:
        role_hooks_module.evaluate_ticket_required_hook_gate = original_evaluate

    assert scan_result.opened_incident_ids
    incident = repository.get_incident_projection(scan_result.opened_incident_ids[0])
    assert incident is not None
    assert incident["incident_type"] == "REQUIRED_HOOK_GATE_BLOCKED"
    assert incident["ticket_id"] == checker_ticket_id
    assert incident["node_id"] == node_id
    assert incident["payload"]["missing_hook_ids"] == ["artifact_capture"]


def test_ticket_graph_snapshot_surfaces_required_hook_pending_reason(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Ticket graph should expose explicit required hook blockers."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_graph_001"
    node_id = "node_hook_graph_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )
    _assert_command_accepted(submit_response)

    git_closeout_path = _receipt_root(client, workflow_id, ticket_id) / "git-closeout.json"
    _assert_receipt_exists(git_closeout_path)
    git_closeout_path.unlink()
    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)

    assert node_id in snapshot.index_summary.blocked_node_ids
    assert any(
        item.reason_code == "REQUIRED_HOOK_PENDING:git_closeout" and node_id in item.node_ids
        for item in snapshot.index_summary.blocked_reasons
    )


def test_incident_resolve_can_replay_required_hooks_and_close_gate(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Incident resolve should replay missing required hooks."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_resolve_001"
    node_id = "node_hook_resolve_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )
    _assert_command_accepted(submit_response)

    git_receipt_path = _receipt_root(client, workflow_id, ticket_id) / "git-closeout.json"
    _assert_receipt_exists(git_receipt_path)
    git_receipt_path.unlink()
    repository = client.app.state.repository
    scan_and_open_required_hook_gate_incidents(
        repository,
        workflow_id=workflow_id,
        idempotency_key_base=f"hook-resolve:{workflow_id}",
    )
    incident = next(
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item.get("ticket_id") == ticket_id
    )

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident["incident_id"],
            followup_action="REPLAY_REQUIRED_HOOKS",
        ),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert git_receipt_path.is_file()
    refreshed_incident = repository.get_incident_projection(incident["incident_id"])
    assert refreshed_incident is not None
    assert refreshed_incident["status"] == "RECOVERING"


def test_incident_resolve_can_replay_closeout_documentation_sync_hook(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Closeout tickets should replay documentation sync from terminal truth."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_closeout_resolve_001"
    node_id = "node_hook_closeout_resolve_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_closeout_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            final_artifact_refs=["art://runtime/tkt_build_001/source-code.tsx"],
        ),
    )
    _assert_command_accepted(submit_response)

    receipt_path = _receipt_root(client, workflow_id, ticket_id) / "documentation-sync.json"
    _assert_receipt_exists(receipt_path)
    receipt_path.unlink()
    repository = client.app.state.repository
    scan_and_open_required_hook_gate_incidents(
        repository,
        workflow_id=workflow_id,
        idempotency_key_base=f"hook-closeout-resolve:{workflow_id}",
    )
    incident = next(
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item.get("ticket_id") == ticket_id
    )

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident["incident_id"],
            followup_action="REPLAY_REQUIRED_HOOKS",
        ),
    )

    assert resolve_response.status_code == 200
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["ticket_id"] == ticket_id
    assert len(receipt["documentation_updates"]) == 2


def test_incident_resolve_rejects_when_artifact_capture_replay_lacks_terminal_written_artifacts(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Artifact capture replay must fail closed when terminal truth is incomplete."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_hook_artifact_capture_reject_001"
    node_id = "node_hook_artifact_capture_reject_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_governance_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    _assert_command_accepted(submit_response)

    receipt_path = _receipt_root(client, workflow_id, ticket_id) / "artifact-capture.json"
    _assert_receipt_exists(receipt_path)
    receipt_path.unlink()
    repository = client.app.state.repository
    with repository.transaction() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
        assert terminal_event is not None
        payload = dict(terminal_event["payload"] or {})
        payload.pop("written_artifacts", None)
        connection.execute(
            """
            UPDATE events
            SET payload_json = ?
            WHERE event_id = ?
            """,
            (json.dumps(payload, sort_keys=True), terminal_event["event_id"]),
        )
        repository.refresh_projections(connection)

    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        gate_result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
        )
    incident_id = open_required_hook_gate_incident(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        gate_result=gate_result,
        idempotency_key_base=f"hook-artifact-capture-reject:{workflow_id}",
    )

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="REPLAY_REQUIRED_HOOKS",
        ),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "REJECTED"
    refreshed_incident = repository.get_incident_projection(incident_id)
    assert refreshed_incident is not None
    assert refreshed_incident["status"] == "OPEN"


def test_incident_resolve_rejects_when_review_evidence_replay_lacks_terminal_written_artifacts(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Review evidence replay must fail closed when written artifacts disappear."),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_review_hook_reject_001"
    node_id = "node_review_hook_reject_001"
    _create_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    _assert_command_accepted(submit_response)

    receipt_path = _receipt_root(client, workflow_id, ticket_id) / "artifact-capture.json"
    _assert_receipt_exists(receipt_path)
    receipt_path.unlink()
    repository = client.app.state.repository
    with repository.transaction() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
        assert terminal_event is not None
        payload = dict(terminal_event["payload"] or {})
        payload.pop("written_artifacts", None)
        connection.execute(
            """
            UPDATE events
            SET payload_json = ?
            WHERE event_id = ?
            """,
            (json.dumps(payload, sort_keys=True), terminal_event["event_id"]),
        )
        repository.refresh_projections(connection)

    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        assert ticket is not None
        assert created_spec is not None
        gate_result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket,
            created_spec=created_spec,
            connection=connection,
        )
    incident_id = open_required_hook_gate_incident(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        gate_result=gate_result,
        idempotency_key_base=f"hook-review-evidence-reject:{workflow_id}",
    )

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="REPLAY_REQUIRED_HOOKS",
        ),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "REJECTED"
    refreshed_incident = repository.get_incident_projection(incident_id)
    assert refreshed_incident is not None
    assert refreshed_incident["status"] == "OPEN"
