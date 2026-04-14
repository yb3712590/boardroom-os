from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import get_settings
from app.core import project_workspaces
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.process_assets import (
    build_artifact_process_asset_ref,
    build_source_code_delivery_process_asset_ref,
)


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
        "output_schema_ref": "source_code_delivery",
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


def _active_worktree_index_path(workflow_id: str):
    return (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "workflow"
        / "active-worktree-index.md"
    )


def _checkout_path(workflow_id: str, ticket_id: str) -> Path:
    return (
        get_settings().project_workspace_root
        / workflow_id
        / "20-evidence"
        / "worktrees"
        / ticket_id
    )


def _receipt_root(client, workflow_id: str, ticket_id: str):
    return (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
    )


def _git_output(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


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


def test_ticket_start_allocates_checkout_and_compile_carries_checkout_truth(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Checkout truth demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_checkout_truth_001"
    node_id = "node_checkout_truth_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )

    assert start_response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    compiled_artifacts = compile_and_persist_execution_artifacts(repository, ticket)
    checkout_path = _checkout_path(workflow_id, ticket_id)

    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
    assert created_spec is not None
    assert created_spec["project_checkout_ref"] == f"worktree://{workflow_id}/{ticket_id}"
    assert created_spec["git_branch_ref"] == f"codex/{ticket_id}"
    assert checkout_path.is_dir()
    assert _git_output(checkout_path, "rev-parse", "--abbrev-ref", "HEAD") == f"codex/{ticket_id}"
    assert compiled_artifacts.compiled_execution_package.execution.project_checkout_ref == (
        f"worktree://{workflow_id}/{ticket_id}"
    )
    assert compiled_artifacts.compiled_execution_package.execution.project_checkout_path == str(checkout_path)
    assert compiled_artifacts.compiled_execution_package.execution.git_branch_ref == f"codex/{ticket_id}"

    checkout_receipt_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "worktree-checkout.json"
    )
    assert checkout_receipt_path.is_file()


def _source_code_delivery_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    include_documentation_updates: bool,
    include_git_evidence: bool,
    source_file_content: str = "export const workspaceBuild = true;\n",
    verification_stdout: str = "collected 1 item\n\n1 passed in 0.12s\n",
    verification_stderr: str = "",
) -> dict[str, object]:
    source_file_ref = f"art://workspace/{ticket_id}/source.ts"
    verification_ref = f"art://workspace/{ticket_id}/test-report.json"
    verification_path = f"20-evidence/tests/{ticket_id}/attempt-1/test-report.json"
    payload: dict[str, object] = {
        "summary": f"Source code delivery prepared for {ticket_id}.",
        "source_file_refs": [source_file_ref],
        "source_files": [
            {
                "artifact_ref": source_file_ref,
                "path": f"10-project/src/{ticket_id}.ts",
                "content": source_file_content,
            }
        ],
        "verification_runs": [
            {
                "artifact_ref": verification_ref,
                "path": verification_path,
                "runner": "pytest",
                "command": "pytest tests/test_project_workspace_hooks.py -q",
                "status": "passed",
                "exit_code": 0,
                "duration_sec": 1.2,
                "stdout": verification_stdout,
                "stderr": verification_stderr,
                "discovered_count": 1,
                "passed_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "failures": [],
            }
        ],
        "implementation_notes": ["Implementation stayed inside the approved scope lock."],
    }
    written_artifacts: list[dict[str, object]] = [
        {
            "path": f"10-project/src/{ticket_id}.ts",
            "artifact_ref": source_file_ref,
            "kind": "TEXT",
            "content_text": source_file_content,
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
            "path": verification_path,
            "artifact_ref": verification_ref,
            "kind": "JSON",
            "content_json": payload["verification_runs"][0],
        },
        {
            "path": f"20-evidence/git/{ticket_id}/attempt-1/git-closeout.json",
            "artifact_ref": f"art://workspace/{ticket_id}/git-commit.json",
            "kind": "JSON",
            "content_json": {"commit_sha": "abc1234", "branch_ref": f"codex/{ticket_id}"},
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
        "schema_version": "source_code_delivery_v1",
        "payload": payload,
        "artifact_refs": [],
        "written_artifacts": written_artifacts,
        "verification_evidence_refs": [verification_ref],
        "assumptions": ["Project workspace receipts are enabled."],
        "issues": [],
        "confidence": 0.91,
        "needs_escalation": False,
        "summary": "Structured source code delivery submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:source-code-delivery",
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


def _closeout_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    final_artifact_refs: list[str] | None = None,
    written_artifact_path: str | None = None,
) -> dict[str, object]:
    closeout_artifact_ref = f"art://runtime/{ticket_id}/delivery-closeout-package.json"
    payload = {
        "summary": f"Delivery closeout package prepared for {ticket_id}.",
        "final_artifact_refs": list(final_artifact_refs or [f"art://runtime/{ticket_id}/approved-final.json"]),
        "handoff_notes": [
            "Board-approved final option is captured in this closeout package.",
            "Final evidence remains linked back to the approved delivery artifacts.",
        ],
        "documentation_updates": [
            {
                "doc_ref": "10-project/docs/tracking/active-tasks.md",
                "status": "UPDATED",
                "summary": "Recorded the final closeout handoff state.",
            },
            {
                "doc_ref": "10-project/docs/history/memory-recent.md",
                "status": "NO_CHANGE_REQUIRED",
                "summary": "No new cross-ticket memory needed during closeout.",
            },
        ],
    }
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_frontend_2",
        "result_status": "completed",
        "schema_version": "delivery_closeout_package_v1",
        "payload": payload,
        "artifact_refs": [closeout_artifact_ref],
        "written_artifacts": [
            {
                "path": written_artifact_path or f"20-evidence/closeout/{ticket_id}/delivery-closeout-package.json",
                "artifact_ref": closeout_artifact_ref,
                "kind": "JSON",
                "content_json": payload,
            }
        ],
        "assumptions": ["Closeout package stays inside the approved delivery boundary."],
        "issues": [],
        "confidence": 0.9,
        "needs_escalation": False,
        "summary": "Structured delivery closeout package submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:closeout",
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
        json=_source_code_delivery_result_submit_payload(
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
        json=_source_code_delivery_result_submit_payload(
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
    checkout_path = _checkout_path(workflow_id, ticket_id)
    canonical_workspace_root = get_settings().project_workspace_root / workflow_id
    assert (checkout_path / "src" / f"{ticket_id}.ts").is_file()
    assert (checkout_path / "docs" / "tracking" / f"{ticket_id}-active.md").is_file()
    assert (checkout_path / "docs" / "history" / f"{ticket_id}-memory.md").is_file()
    assert not (canonical_workspace_root / "10-project" / "src" / f"{ticket_id}.ts").exists()
    assert (
        canonical_workspace_root
        / "20-evidence"
        / "tests"
        / ticket_id
        / "attempt-1"
        / "test-report.json"
    ).is_file()
    assert (
        canonical_workspace_root
        / "20-evidence"
        / "git"
        / ticket_id
        / "attempt-1"
        / "git-closeout.json"
    ).is_file()
    receipt = json.loads((dossier_root / "git-closeout.json").read_text(encoding="utf-8"))
    git_commit_record = receipt["git_commit_record"]
    assert git_commit_record["branch_ref"] == f"codex/{ticket_id}"
    assert git_commit_record["merge_status"] == "PENDING_REVIEW_GATE"
    assert git_commit_record["commit_sha"] != "abc1234"
    assert git_commit_record["commit_sha"] == _git_output(checkout_path, "rev-parse", "HEAD")
    assert _git_output(checkout_path, "status", "--short") == ""


def test_source_code_delivery_ticket_start_updates_active_worktree_index(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code worktree start demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_worktree_start_001"
    node_id = "node_code_worktree_start_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    index_path = _active_worktree_index_path(workflow_id)
    assert index_path.is_file()
    index_body = index_path.read_text(encoding="utf-8")
    assert "| ticket_id | node_id | worker | status | branch_ref | commit_sha | merge_status | updated_at |" in index_body
    assert ticket_id in index_body
    assert node_id in index_body
    assert "emp_frontend_2" in index_body
    assert "EXECUTING" in index_body
    assert f"codex/{ticket_id}" in index_body


def test_source_code_delivery_submit_updates_active_worktree_index_with_git_status(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code worktree submit demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_worktree_submit_001"
    node_id = "node_code_worktree_submit_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )

    index_path = _active_worktree_index_path(workflow_id)
    index_body = index_path.read_text(encoding="utf-8")
    assert ticket_id in index_body
    assert _git_output(_checkout_path(workflow_id, ticket_id), "rev-parse", "HEAD") in index_body
    assert "PENDING_REVIEW_GATE" in index_body


def test_source_code_delivery_submit_refreshes_doc_impact_view_from_receipts(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code doc impact materializer demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_doc_impact_001"
    node_id = "node_code_doc_impact_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
        ),
    )

    doc_impact_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "doc-impact.md"
    )
    body = doc_impact_path.read_text(encoding="utf-8")
    assert "- View Kind: `ticket_doc_impact`" in body
    assert "10-project/docs/tracking/active-tasks.md" in body
    assert "UPDATED" in body
    assert "NO_CHANGE_REQUIRED" in body


def test_sync_ticket_boardroom_views_overwrites_manual_doc_edits(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Ticket doc overwrite demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_doc_overwrite_001"
    node_id = "node_doc_overwrite_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )

    doc_impact_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "doc-impact.md"
    )
    doc_impact_path.write_text("# Broken\n\nmanual drift\n", encoding="utf-8")

    repository = client.app.state.repository
    project_workspaces.sync_ticket_boardroom_views(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
    )

    refreshed = doc_impact_path.read_text(encoding="utf-8")
    assert "# Broken" not in refreshed
    assert "- View Kind: `ticket_doc_impact`" in refreshed
    assert "`not_reported`" in refreshed


def test_governance_ticket_does_not_enter_active_worktree_index(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Governance worktree exclusion demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_governance_worktree_001"
    node_id = "node_governance_worktree_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "architecture_brief",
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:governance-worktree",
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_governance_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )

    index_path = _active_worktree_index_path(workflow_id)
    index_body = index_path.read_text(encoding="utf-8")
    assert ticket_id not in index_body
    assert "No active worktree recorded yet." in index_body


def test_source_code_delivery_requires_project_source_file_refs(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code source-file-ref demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_source_refs_001"
    node_id = "node_code_source_refs_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    payload = _source_code_delivery_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        include_documentation_updates=True,
        include_git_evidence=True,
    )
    payload["payload"]["source_file_refs"] = ["art://workspace/tkt_code_source_refs_001/active-task.md"]

    response = client.post("/api/v1/commands/ticket-result-submit", json=payload)

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "SCHEMA_ERROR"


def test_source_code_delivery_rejects_placeholder_source_content(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code placeholder gate demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_placeholder_001"
    node_id = "node_code_placeholder_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
            source_file_content="export const runtimeSourceDelivery = true;\n",
        ),
    )

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "SCHEMA_ERROR"


def test_source_code_delivery_rejects_minimal_verification_stub(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Source-code verification gate demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_code_verification_stub_001"
    node_id = "node_code_verification_stub_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_documentation_updates=True,
            include_git_evidence=True,
            verification_stdout="",
            verification_stderr="",
        ),
    )

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "SCHEMA_ERROR"


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
    receipt_root = _receipt_root(client, workflow_id, ticket_id)
    assert (receipt_root / "artifact-capture.json").is_file()


def test_closeout_ticket_create_uses_structured_document_workspace_bootstrap(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Closeout workspace bootstrap demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_closeout_workspace_bootstrap_001"
    node_id = "node_closeout_workspace_bootstrap_001"

    response = client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "delivery_closeout_package",
            "allowed_write_set": [f"20-evidence/closeout/{ticket_id}/*"],
            "input_artifact_refs": ["art://runtime/tkt_build_001/source-code.tsx"],
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:closeout-workspace-bootstrap",
        },
    )

    assert response.status_code == 200
    repository = client.app.state.repository
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
    assert created_spec is not None
    manifest_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert created_spec["deliverable_kind"] == "structured_document_delivery"
    assert created_spec["required_read_refs"] == manifest["canonical_doc_refs"]
    assert created_spec["doc_update_requirements"] == manifest["default_doc_update_requirements"]


def test_closeout_ticket_requires_final_artifact_refs_to_match_known_delivery_evidence(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Closeout final artifact gate demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_closeout_final_artifact_gate_001"
    node_id = "node_closeout_final_artifact_gate_001"
    known_final_artifact_ref = "art://runtime/tkt_build_001/source-code.tsx"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "delivery_closeout_package",
            "allowed_write_set": [f"20-evidence/closeout/{ticket_id}/*"],
            "input_artifact_refs": [known_final_artifact_ref],
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:closeout-final-artifact-gate",
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_closeout_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            final_artifact_refs=["art://runtime/tkt_unknown_build/source-code.tsx"],
        ),
    )

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"


def test_closeout_ticket_result_submit_materializes_workspace_evidence_files(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Closeout workspace evidence demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_closeout_workspace_evidence_001"
    node_id = "node_closeout_workspace_evidence_001"
    known_final_artifact_ref = "art://runtime/tkt_build_001/source-code.tsx"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "delivery_closeout_package",
            "allowed_write_set": [f"20-evidence/closeout/{ticket_id}/*"],
            "input_artifact_refs": [known_final_artifact_ref],
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:closeout-workspace-evidence",
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_closeout_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            final_artifact_refs=[known_final_artifact_ref],
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    receipt_root = _receipt_root(client, workflow_id, ticket_id)
    assert (receipt_root / "artifact-capture.json").is_file()
    assert (receipt_root / "documentation-sync.json").is_file()
    closeout_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "20-evidence"
        / "closeout"
        / ticket_id
        / "delivery-closeout-package.json"
    )
    assert closeout_path.is_file()
    closeout_payload = json.loads(closeout_path.read_text(encoding="utf-8"))
    assert closeout_payload["final_artifact_refs"] == [known_final_artifact_ref]


def test_governance_document_requires_declared_artifact_ref(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Governance artifact contract demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_governance_artifact_contract_001"
    node_id = "node_governance_artifact_contract_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "architecture_brief",
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:governance-contract",
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    payload = _governance_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
    )
    payload["artifact_refs"] = []

    response = client.post("/api/v1/commands/ticket-result-submit", json=payload)

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"


def test_governance_document_requires_written_artifact_for_declared_ref(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Governance artifact alignment demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_governance_artifact_alignment_001"
    node_id = "node_governance_artifact_alignment_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "architecture_brief",
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:governance-alignment",
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))
    client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id))

    payload = _governance_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
    )
    payload["written_artifacts"][0]["artifact_ref"] = f"art://runtime/{ticket_id}/other-architecture-brief.json"

    response = client.post("/api/v1/commands/ticket-result-submit", json=payload)

    assert response.status_code == 200
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection(ticket_id)
    assert ticket is not None
    assert ticket["status"] == "FAILED"
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"


def test_governance_document_writes_human_readable_audit_markdown(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Governance audit markdown demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_governance_audit_markdown_001"
    node_id = "node_governance_audit_markdown_001"

    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(workflow_id=workflow_id, ticket_id=ticket_id, node_id=node_id),
            "output_schema_ref": "architecture_brief",
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}:governance-audit-md",
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

    audit_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "10-project"
        / "docs"
        / f"{ticket_id}-architecture-brief.audit.md"
    )
    assert audit_path.is_file()
    body = audit_path.read_text(encoding="utf-8")
    assert "## 摘要" in body
    assert "## 关键决策" in body
    assert "## 关键约束" in body
    assert "## 各节要点" in body
    assert "linked_artifact_refs" not in body
    assert "content_json" not in body

    repository = client.app.state.repository
    artifacts = repository.list_ticket_artifacts(ticket_id)
    logical_paths = {str(item.get("logical_path") or "") for item in artifacts}
    assert f"10-project/docs/{ticket_id}-architecture-brief.audit.md" in logical_paths
