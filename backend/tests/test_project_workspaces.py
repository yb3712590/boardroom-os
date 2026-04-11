from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.config import get_settings


def _project_init_payload(
    goal: str,
    *,
    methodology_profile: str = "AGILE",
) -> dict[str, object]:
    return {
        "north_star_goal": goal,
        "hard_constraints": [
            "Keep governance explicit.",
            "Do not move workflow truth into the browser.",
        ],
        "budget_cap": 500000,
        "deadline_at": None,
        "project_methodology_profile": methodology_profile,
    }


def _git_output(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def test_project_init_creates_agile_project_workspace_layout(client) -> None:
    response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Workspace bootstrap demo"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]

    workspace_root = get_settings().project_workspace_root / workflow_id

    assert (workspace_root / "00-boardroom").is_dir()
    assert (workspace_root / "10-project").is_dir()
    assert (workspace_root / "20-evidence").is_dir()
    assert (workspace_root / "00-boardroom" / "workflow" / "workspace-manifest.json").is_file()
    assert (workspace_root / "00-boardroom" / "workflow" / "hook-policy.md").is_file()
    assert (workspace_root / "10-project" / "docs" / "L0-context" / "project-brief.md").is_file()
    assert (workspace_root / "10-project" / "docs" / "tracking" / "task-index.md").is_file()
    assert (workspace_root / "20-evidence" / "git").is_dir()


def test_project_init_bootstraps_git_repo_for_project_directory(client) -> None:
    response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Workspace git bootstrap demo"),
    )

    assert response.status_code == 200
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    project_root = get_settings().project_workspace_root / workflow_id / "10-project"

    assert (project_root / ".git").exists()
    assert _git_output(project_root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert _git_output(project_root, "config", "user.name") == "user.boardroom"
    assert _git_output(project_root, "config", "user.email") == "boardroom-os@local"
    assert _git_output(project_root, "rev-list", "--count", "HEAD") == "1"
    assert _git_output(project_root, "status", "--short") == ""


@pytest.mark.parametrize(
    ("methodology_profile", "expected_paths"),
    [
        (
            "HYBRID",
            [
                "10-project/docs/L0-context/phase-status.md",
                "10-project/docs/traceability/req-to-design.md",
                "10-project/docs/baselines/README.md",
            ],
        ),
        (
            "COMPLIANCE",
            [
                "10-project/docs/L0-context/project-charter.md",
                "10-project/docs/L0-context/traceability-index.md",
                "10-project/docs/01-requirements/srs/_summary.md",
                "10-project/docs/03-implementation/change-log/current-change.md",
            ],
        ),
    ],
)
def test_project_init_creates_profile_specific_workspace_layout(
    client,
    methodology_profile: str,
    expected_paths: list[str],
) -> None:
    response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload(
            f"{methodology_profile} workspace bootstrap demo",
            methodology_profile=methodology_profile,
        ),
    )

    assert response.status_code == 200
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    workspace_root = get_settings().project_workspace_root / workflow_id

    for relative_path in expected_paths:
        assert (workspace_root / relative_path).is_file()


def _ticket_create_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    output_schema_ref: str = "source_code_delivery",
) -> dict[str, object]:
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
        "output_schema_ref": output_schema_ref,
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


def test_ticket_create_bootstraps_dossier_and_workspace_truth(client) -> None:
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Ticket dossier bootstrap demo"),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    ticket_id = "tkt_workspace_build_001"
    node_id = "node_workspace_build_001"

    response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)

    assert created_spec is not None
    assert created_spec["project_workspace_ref"] == f"workspace://{workflow_id}"
    assert created_spec["project_methodology_profile"] == "AGILE"
    assert created_spec["deliverable_kind"] == "source_code_delivery"
    assert created_spec["project_checkout_ref"] == f"worktree://{workflow_id}/{ticket_id}"
    assert created_spec["git_branch_ref"] == f"codex/{ticket_id}"
    assert created_spec["canonical_doc_refs"]
    assert created_spec["required_read_refs"]
    assert created_spec["doc_update_requirements"] == [
        "10-project/docs/tracking/active-tasks.md",
        "10-project/docs/history/memory-recent.md",
    ]
    assert created_spec["git_policy"] == "per_ticket_commit_required"

    dossier_root = get_settings().project_workspace_root / workflow_id / "00-boardroom" / "tickets" / ticket_id
    assert (dossier_root / "brief.md").is_file()
    assert (dossier_root / "required-reads.md").is_file()
    assert (dossier_root / "execution-log.md").is_file()
    assert (dossier_root / "doc-impact.md").is_file()
    assert (dossier_root / "git-closeout.md").is_file()
    assert (dossier_root / "hook-receipts").is_dir()
