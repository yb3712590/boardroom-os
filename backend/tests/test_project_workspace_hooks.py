from __future__ import annotations

import json

from app.config import get_settings
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.process_assets import build_artifact_process_asset_ref


def _project_init_payload(goal: str) -> dict[str, object]:
    return {
        "north_star_goal": goal,
        "hard_constraints": [
            "Keep governance explicit.",
            "Do not move workflow truth into the browser.",
        ],
        "budget_cap": 500000,
        "deadline_at": None,
        "project_methodology_profile": "AGILE",
    }


def _ticket_create_payload(*, workflow_id: str, ticket_id: str, node_id: str) -> dict[str, object]:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": 1,
        "role_profile_ref": "frontend_engineer_primary",
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": ["art://inputs/brief.md"],
        "context_query_plan": {
            "keywords": ["workspace", "bootstrap"],
            "semantic_queries": ["required docs"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result"],
        "output_schema_ref": "implementation_bundle",
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact", "write_artifact"],
        "allowed_write_set": [
            "10-project/src/*",
            "10-project/docs/*",
            "20-evidence/tests/*",
            "20-evidence/git/*",
        ],
        "retry_budget": 1,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": "2026-03-28T18:00:00+08:00",
        "escalation_policy": {
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }


def _ticket_lease_payload(*, workflow_id: str, ticket_id: str, node_id: str) -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "leased_by": "emp_frontend_2",
        "lease_timeout_sec": 600,
        "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}",
    }


def _ticket_start_payload(*, workflow_id: str, ticket_id: str, node_id: str) -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "started_by": "emp_frontend_2",
        "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}",
    }


def test_compile_persists_worker_preflight_receipt_and_required_reads(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Worker preflight receipt demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_preflight_build_001"
    node_id = "node_preflight_build_001"

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
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
        ),
    )
    assert lease_response.status_code == 200
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )
    assert start_response.status_code == 200

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    compiled_artifacts = compile_and_persist_execution_artifacts(repository, ticket)

    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
    assert created_spec is not None

    assert compiled_artifacts.compiled_execution_package.execution.required_read_refs == created_spec["required_read_refs"]
    for artifact_ref in created_spec["required_read_refs"]:
        assert build_artifact_process_asset_ref(artifact_ref) in (
            compiled_artifacts.compiled_execution_package.execution.input_process_asset_refs
        )

    receipt_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "worker-preflight.json"
    )
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["ticket_id"] == ticket_id
    assert receipt["required_read_refs"] == created_spec["required_read_refs"]


def _implementation_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    include_documentation_updates: bool,
    include_git_evidence: bool,
) -> dict[str, object]:
    bundle_ref = f"art://runtime/{ticket_id}/implementation-bundle.json"
    payload: dict[str, object] = {
        "summary": f"Implementation bundle prepared for {ticket_id}.",
        "deliverable_artifact_refs": [bundle_ref],
        "implementation_notes": ["Implementation stayed inside the approved scope lock."],
    }
    written_artifacts: list[dict[str, object]] = [
        {
            "path": f"10-project/src/{ticket_id}.ts",
            "artifact_ref": f"art://workspace/{ticket_id}/source.ts",
            "kind": "TEXT",
            "content_text": "export const workspaceBuild = true;\n",
        },
        {
            "path": f"10-project/docs/tracking/{ticket_id}-active.md",
            "artifact_ref": f"art://workspace/{ticket_id}/active-task.md",
            "kind": "TEXT",
            "content_text": "Updated active task summary.\n",
        },
        {
            "path": f"10-project/docs/history/{ticket_id}-memory.md",
            "artifact_ref": f"art://workspace/{ticket_id}/memory.md",
            "kind": "TEXT",
            "content_text": "Updated recent memory.\n",
        },
        {
            "path": f"20-evidence/tests/{ticket_id}-report.json",
            "artifact_ref": f"art://workspace/{ticket_id}/test-report.json",
            "kind": "JSON",
            "content_json": {"status": "passed", "command": "pytest tests/test_project_workspace_hooks.py -q"},
        },
        {
            "path": f"20-evidence/git/{ticket_id}-commit.json",
            "artifact_ref": f"art://workspace/{ticket_id}/git-commit.json",
            "kind": "JSON",
            "content_json": {"commit_sha": "abc1234", "branch_ref": f"codex/{ticket_id}"},
        },
        {
            "path": f"10-project/docs/{ticket_id}-implementation-bundle.json",
            "artifact_ref": bundle_ref,
            "kind": "JSON",
            "content_json": payload,
        },
    ]
    if include_documentation_updates:
        payload["documentation_updates"] = [
            {
                "doc_ref": "10-project/docs/tracking/active-tasks.md",
                "status": "UPDATED",
                "summary": "Updated the active task index after implementation.",
            },
            {
                "doc_ref": "10-project/docs/history/memory-recent.md",
                "status": "NO_CHANGE_REQUIRED",
                "summary": "No new cross-ticket memory had to be recorded.",
            },
        ]
    result = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_frontend_2",
        "result_status": "completed",
        "schema_version": "implementation_bundle_v1",
        "payload": payload,
        "artifact_refs": [bundle_ref],
        "written_artifacts": written_artifacts,
        "verification_evidence_refs": [f"art://workspace/{ticket_id}/test-report.json"],
        "assumptions": ["Project workspace receipts are enabled."],
        "issues": [],
        "confidence": 0.91,
        "needs_escalation": False,
        "summary": "Structured implementation bundle submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:implementation",
    }
    if include_git_evidence:
        result["git_commit_record"] = {
            "commit_sha": "abc1234",
            "branch_ref": f"codex/{ticket_id}",
            "merge_status": "PENDING_REVIEW_GATE",
        }
    return result


def _governance_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
) -> dict[str, object]:
    artifact_ref = f"art://runtime/{ticket_id}/architecture-brief.json"
    payload = {
        "title": f"Architecture brief for {ticket_id}",
        "summary": "Prepared a narrow governance document.",
        "document_kind_ref": "architecture_brief",
        "linked_document_refs": [],
        "linked_artifact_refs": [],
        "source_process_asset_refs": [],
        "decisions": ["Keep project workspace truth outside the event stream."],
        "constraints": ["Do not widen the MVP boundary."],
        "sections": [
            {
                "section_id": "sec_1",
                "label": "Context",
                "summary": "Why this ticket exists.",
                "content_markdown": "## Context\n\nKeep the scope narrow.",
            }
        ],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_1",
                "summary": "Prepare the next implementation ticket.",
                "target_role": "frontend_engineer",
            }
        ],
    }
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_frontend_2",
        "result_status": "completed",
        "schema_version": "architecture_brief_v1",
        "payload": payload,
        "artifact_refs": [artifact_ref],
        "written_artifacts": [
            {
                "path": f"10-project/docs/{ticket_id}-architecture-brief.json",
                "artifact_ref": artifact_ref,
                "kind": "JSON",
                "content_json": payload,
            }
        ],
        "assumptions": ["Governance tickets do not require git closeout."],
        "issues": [],
        "confidence": 0.88,
        "needs_escalation": False,
        "summary": "Structured governance document submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:governance",
    }


def test_source_code_delivery_requires_documentation_updates(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code gate demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_gate_001"
    node_id = "node_code_gate_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_implementation_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=False,
            include_git_evidence=False,
        ),
    )

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"


def test_source_code_delivery_writes_postrun_and_git_receipts(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code receipt demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_receipt_001"
    node_id = "node_code_receipt_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_implementation_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    dossier_root = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
    )
    assert (dossier_root / "worker-postrun.json").is_file()
    assert (dossier_root / "evidence-capture.json").is_file()
    assert (dossier_root / "git-closeout.json").is_file()


def test_structured_document_delivery_does_not_require_git_commit(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Governance no-git demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_governance_no_git_001"
    node_id = "node_governance_no_git_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "architecture_brief",
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:governance",
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_governance_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "COMPLETED"
