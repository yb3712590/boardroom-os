from __future__ import annotations

import base64
import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.contracts.commands import DeliverableKind, GitPolicy, ProjectMethodologyProfile
from app.core.artifact_store import ArtifactStore
from app.core.output_schemas import (
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

WORKSPACE_REF_PREFIX = "workspace://"
WORKTREE_REF_PREFIX = "worktree://"
PROJECT_WORKSPACE_ARTIFACT_PREFIX = "art://project-workspace"
PROJECT_WORKSPACE_LOGICAL_PREFIX = "project-workspaces"
PROJECT_MAIN_BRANCH = "main"
PROJECT_GIT_USER_NAME = "user.boardroom"
PROJECT_GIT_USER_EMAIL = "boardroom-os@local"


@dataclass(frozen=True)
class ProjectWorkspaceBootstrap:
    workspace_ref: str
    workspace_root: Path
    methodology_profile: ProjectMethodologyProfile
    canonical_doc_refs: list[str]
    default_doc_update_requirements: list[str]


@dataclass(frozen=True)
class TicketWorkspaceBootstrap:
    project_workspace_ref: str
    project_methodology_profile: ProjectMethodologyProfile
    deliverable_kind: DeliverableKind
    canonical_doc_refs: list[str]
    required_read_refs: list[str]
    doc_update_requirements: list[str]
    git_policy: GitPolicy
    project_checkout_ref: str | None = None
    git_branch_ref: str | None = None


def build_project_workspace_ref(workflow_id: str) -> str:
    return f"{WORKSPACE_REF_PREFIX}{workflow_id}"


def build_project_checkout_ref(workflow_id: str, ticket_id: str) -> str:
    return f"{WORKTREE_REF_PREFIX}{workflow_id}/{ticket_id}"


def resolve_project_workspace_root(workflow_id: str) -> Path:
    return get_settings().project_workspace_root / workflow_id


def resolve_project_repo_root(workflow_id: str) -> Path:
    return resolve_project_workspace_root(workflow_id) / "10-project"


def resolve_project_worktree_root(workflow_id: str) -> Path:
    return resolve_project_workspace_root(workflow_id) / "20-evidence" / "worktrees"


def resolve_project_checkout_path(workflow_id: str, ticket_id: str) -> Path:
    return resolve_project_worktree_root(workflow_id) / ticket_id


def default_ticket_branch_ref(ticket_id: str) -> str:
    return f"codex/{ticket_id}"


def build_project_workspace_artifact_ref(workflow_id: str, relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").strip("/")
    return f"{PROJECT_WORKSPACE_ARTIFACT_PREFIX}/{workflow_id}/{normalized}"


def build_project_workspace_logical_path(workflow_id: str, relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").strip("/")
    return f"{PROJECT_WORKSPACE_LOGICAL_PREFIX}/{workflow_id}/{normalized}"


def load_project_workspace_manifest(workflow_id: str) -> dict[str, Any]:
    manifest_path = resolve_project_workspace_root(workflow_id) / "00-boardroom" / "workflow" / "workspace-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Project workspace manifest does not exist for workflow {workflow_id}.")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def project_workspace_manifest_exists(workflow_id: str) -> bool:
    manifest_path = resolve_project_workspace_root(workflow_id) / "00-boardroom" / "workflow" / "workspace-manifest.json"
    return manifest_path.exists()


def infer_deliverable_kind(output_schema_ref: str | None) -> DeliverableKind:
    normalized = str(output_schema_ref or "").strip()
    if normalized == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        return DeliverableKind.SOURCE_CODE_DELIVERY
    if normalized == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return DeliverableKind.STRUCTURED_DOCUMENT_DELIVERY
    if normalized in {
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        UI_MILESTONE_REVIEW_SCHEMA_REF,
        MAKER_CHECKER_VERDICT_SCHEMA_REF,
    }:
        return DeliverableKind.REVIEW_EVIDENCE
    return DeliverableKind.STRUCTURED_DOCUMENT_DELIVERY


def infer_git_policy(deliverable_kind: DeliverableKind) -> GitPolicy:
    if deliverable_kind == DeliverableKind.SOURCE_CODE_DELIVERY:
        return GitPolicy.PER_TICKET_COMMIT_REQUIRED
    return GitPolicy.NO_GIT_REQUIRED


def _run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _git_output(cwd: Path, *args: str) -> str:
    return _run_git(cwd, *args).stdout.strip()


def _git_command_succeeds(cwd: Path, *args: str) -> bool:
    return _run_git(cwd, *args, check=False).returncode == 0


def _normalize_workspace_relative_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip("/")


def _extract_written_artifact_field(item: Any, name: str) -> Any:
    if hasattr(item, name):
        return getattr(item, name)
    if isinstance(item, dict):
        return item.get(name)
    return None


def _workspace_file_bytes(kind: str, item: Any) -> bytes:
    normalized_kind = str(kind or "").upper()
    if normalized_kind == "JSON":
        return (json.dumps(_extract_written_artifact_field(item, "content_json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if normalized_kind in {"TEXT", "MARKDOWN"}:
        return str(_extract_written_artifact_field(item, "content_text") or "").encode("utf-8")
    return base64.b64decode(str(_extract_written_artifact_field(item, "content_base64") or ""))


def _write_workspace_written_artifact(target_path: Path, item: Any) -> None:
    kind = str(_extract_written_artifact_field(item, "kind") or "").upper()
    payload = _workspace_file_bytes(kind, item)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(payload)


def initialize_project_git_repository(workflow_id: str) -> Path:
    repo_root = resolve_project_repo_root(workflow_id)
    repo_root.mkdir(parents=True, exist_ok=True)
    if not (repo_root / ".git").exists():
        _run_git(repo_root, "init", "-b", PROJECT_MAIN_BRANCH)
    _run_git(repo_root, "config", "user.name", PROJECT_GIT_USER_NAME)
    _run_git(repo_root, "config", "user.email", PROJECT_GIT_USER_EMAIL)
    if not _git_command_succeeds(repo_root, "rev-parse", "--verify", "HEAD"):
        _run_git(repo_root, "add", "-A")
        if _git_output(repo_root, "status", "--short"):
            _run_git(repo_root, "commit", "-m", "chore: bootstrap project workspace")
    return repo_root


def ensure_project_checkout(
    *,
    workflow_id: str,
    ticket_id: str,
    branch_ref: str,
) -> Path:
    repo_root = initialize_project_git_repository(workflow_id)
    checkout_path = resolve_project_checkout_path(workflow_id, ticket_id)
    checkout_path.parent.mkdir(parents=True, exist_ok=True)
    if checkout_path.exists() and (checkout_path / ".git").exists():
        return checkout_path
    if _git_command_succeeds(repo_root, "show-ref", "--verify", f"refs/heads/{branch_ref}"):
        _run_git(repo_root, "worktree", "add", str(checkout_path), branch_ref)
    else:
        _run_git(repo_root, "worktree", "add", str(checkout_path), "-b", branch_ref, PROJECT_MAIN_BRANCH)
    return checkout_path


def remove_project_checkout(*, workflow_id: str, ticket_id: str) -> None:
    repo_root = resolve_project_repo_root(workflow_id)
    checkout_path = resolve_project_checkout_path(workflow_id, ticket_id)
    if not (repo_root / ".git").exists():
        return
    if checkout_path.exists():
        _run_git(repo_root, "worktree", "remove", "--force", str(checkout_path), check=False)
    _run_git(repo_root, "worktree", "prune", check=False)


def write_worktree_checkout_receipt(
    *,
    workflow_id: str,
    ticket_id: str,
    project_checkout_ref: str,
    project_checkout_path: Path,
    git_branch_ref: str,
) -> str:
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "worktree-checkout.json"
    )
    _write_json(
        receipt_path,
        {
            "ticket_id": ticket_id,
            "project_checkout_ref": project_checkout_ref,
            "project_checkout_path": str(project_checkout_path),
            "git_branch_ref": git_branch_ref,
        },
    )
    return str(receipt_path)


def load_worktree_checkout_receipt(workflow_id: str, ticket_id: str) -> dict[str, Any]:
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "worktree-checkout.json"
    )
    if not receipt_path.exists():
        return {}
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def update_ticket_git_closeout_notes(
    *,
    workflow_id: str,
    ticket_id: str,
    git_policy: str,
    git_branch_ref: str,
    project_checkout_ref: str | None,
    project_checkout_path: str | None,
    merge_status: str | None,
) -> str:
    relative_path = f"00-boardroom/tickets/{ticket_id}/git-closeout.md"
    lines = [
        "# Git Closeout",
        "",
        f"- Git policy: `{git_policy}`",
        "- Merge boundary: `review_gate`",
        f"- Branch ref: `{git_branch_ref}`",
    ]
    if project_checkout_ref:
        lines.append(f"- Checkout ref: `{project_checkout_ref}`")
    if project_checkout_path:
        lines.append(f"- Checkout path: `{project_checkout_path}`")
    if merge_status:
        lines.append(f"- Merge status: `{merge_status}`")
    _write_text(resolve_project_workspace_root(workflow_id) / relative_path, "\n".join(lines) + "\n")
    return relative_path


def build_effective_workspace_written_artifacts(
    written_artifacts: list[Any],
    *,
    git_commit_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    effective: list[dict[str, Any]] = []
    for item in written_artifacts:
        path = _normalize_workspace_relative_path(_extract_written_artifact_field(item, "path"))
        content_json = _extract_written_artifact_field(item, "content_json")
        if git_commit_record is not None and path.startswith("20-evidence/git/"):
            content_json = dict(git_commit_record)
        effective.append(
            {
                "path": path,
                "artifact_ref": str(_extract_written_artifact_field(item, "artifact_ref") or ""),
                "kind": str(_extract_written_artifact_field(item, "kind") or ""),
                "media_type": _extract_written_artifact_field(item, "media_type"),
                "content_json": content_json,
                "content_text": _extract_written_artifact_field(item, "content_text"),
                "content_base64": _extract_written_artifact_field(item, "content_base64"),
                "retention_class": _extract_written_artifact_field(item, "retention_class"),
                "retention_ttl_sec": _extract_written_artifact_field(item, "retention_ttl_sec"),
            }
        )
    return effective


def materialize_workspace_delivery_files(
    *,
    workflow_id: str,
    ticket_id: str,
    project_checkout_path: Path,
    written_artifacts: list[dict[str, Any]],
) -> None:
    workspace_root = resolve_project_workspace_root(workflow_id)
    checkout_root = project_checkout_path
    for item in written_artifacts:
        relative_path = _normalize_workspace_relative_path(item.get("path"))
        if not relative_path:
            continue
        if relative_path.startswith("10-project/"):
            target_path = checkout_root / relative_path.removeprefix("10-project/")
        elif relative_path.startswith(("00-boardroom/", "20-evidence/")):
            target_path = workspace_root / relative_path
        else:
            continue
        _write_workspace_written_artifact(target_path, item)


def commit_project_checkout(
    *,
    workflow_id: str,
    ticket_id: str,
    project_checkout_path: Path,
    git_branch_ref: str,
) -> dict[str, Any]:
    if _git_output(project_checkout_path, "status", "--short"):
        _run_git(project_checkout_path, "add", "-A")
        _run_git(project_checkout_path, "commit", "-m", f"feat: apply {ticket_id} workspace delivery")
    return {
        "commit_sha": _git_output(project_checkout_path, "rev-parse", "HEAD"),
        "branch_ref": git_branch_ref,
        "merge_status": "PENDING_REVIEW_GATE",
    }


def merge_ticket_branch_into_main(
    *,
    workflow_id: str,
    ticket_id: str,
    git_branch_ref: str,
) -> dict[str, Any]:
    repo_root = initialize_project_git_repository(workflow_id)
    source_commit_sha = _git_output(repo_root, "rev-parse", git_branch_ref)
    _run_git(repo_root, "switch", PROJECT_MAIN_BRANCH)
    merge_result = _run_git(
        repo_root,
        "merge",
        "--no-ff",
        "--no-edit",
        git_branch_ref,
        check=False,
    )
    if merge_result.returncode != 0:
        _run_git(repo_root, "merge", "--abort", check=False)
        raise RuntimeError(
            (merge_result.stderr or merge_result.stdout or f"Review gate merge failed for {ticket_id}.").strip()
        )
    return {
        "commit_sha": source_commit_sha,
        "branch_ref": git_branch_ref,
        "merge_status": "MERGED",
    }


def load_git_closeout_receipt(workflow_id: str, ticket_id: str) -> dict[str, Any]:
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "git-closeout.json"
    )
    if not receipt_path.exists():
        return {}
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return dict(payload.get("git_commit_record") or {}) if isinstance(payload, dict) else {}


def resolve_ticket_checkout_truth(
    workflow_id: str,
    ticket_id: str,
    created_spec: dict[str, Any] | None = None,
) -> dict[str, str]:
    created_spec = created_spec or {}
    receipt = load_worktree_checkout_receipt(workflow_id, ticket_id)
    branch_ref = str(
        receipt.get("git_branch_ref")
        or created_spec.get("git_branch_ref")
        or default_ticket_branch_ref(ticket_id)
    ).strip()
    checkout_ref = str(
        receipt.get("project_checkout_ref")
        or created_spec.get("project_checkout_ref")
        or build_project_checkout_ref(workflow_id, ticket_id)
    ).strip()
    checkout_path = str(
        receipt.get("project_checkout_path")
        or resolve_project_checkout_path(workflow_id, ticket_id)
    ).strip()
    return {
        "project_checkout_ref": checkout_ref,
        "project_checkout_path": checkout_path,
        "git_branch_ref": branch_ref,
    }


def update_git_closeout_status(
    *,
    workflow_id: str,
    ticket_id: str,
    git_branch_ref: str | None,
    merge_status: str,
) -> dict[str, Any]:
    git_commit_record = load_git_closeout_receipt(workflow_id, ticket_id)
    if not git_commit_record:
        git_commit_record = {}
    if git_branch_ref:
        git_commit_record["branch_ref"] = git_branch_ref
    elif not git_commit_record.get("branch_ref"):
        git_commit_record["branch_ref"] = default_ticket_branch_ref(ticket_id)
    git_commit_record["merge_status"] = merge_status
    write_git_closeout_receipt(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        git_commit_record=git_commit_record,
    )
    return git_commit_record


def finalize_workspace_ticket_git_status(
    *,
    workflow_id: str,
    ticket_id: str,
    created_spec: dict[str, Any] | None,
    merge_status: str,
) -> dict[str, Any]:
    truth = resolve_ticket_checkout_truth(workflow_id, ticket_id, created_spec)
    git_commit_record = update_git_closeout_status(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        git_branch_ref=truth["git_branch_ref"],
        merge_status=merge_status,
    )
    update_ticket_git_closeout_notes(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        git_policy=str((created_spec or {}).get("git_policy") or GitPolicy.PER_TICKET_COMMIT_REQUIRED.value),
        git_branch_ref=truth["git_branch_ref"],
        project_checkout_ref=truth["project_checkout_ref"],
        project_checkout_path=truth["project_checkout_path"],
        merge_status=merge_status,
    )
    if merge_status != "PENDING_REVIEW_GATE":
        remove_project_checkout(workflow_id=workflow_id, ticket_id=ticket_id)
    return git_commit_record


def _write_text(target_path: Path, content: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")


def _write_json(target_path: Path, payload: dict[str, Any]) -> None:
    _write_text(target_path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _mirror_text_artifact(
    repository: ControlPlaneRepository,
    *,
    artifact_store: ArtifactStore | None,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    relative_path: str,
    content: str,
    media_type: str,
    connection: sqlite3.Connection | None = None,
) -> str:
    if artifact_store is None:
        raise RuntimeError("Artifact store is required to mirror project workspace files.")
    artifact_ref = build_project_workspace_artifact_ref(workflow_id, relative_path)
    logical_path = build_project_workspace_logical_path(workflow_id, relative_path)
    materialized = artifact_store.materialize_text(
        logical_path,
        content,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        media_type=media_type,
    )
    if connection is not None:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            logical_path=logical_path,
            kind="MARKDOWN" if media_type == "text/markdown" else "TEXT",
            media_type=media_type,
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_relpath=materialized.storage_relpath,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=now_local(),
            retention_class_source="explicit",
            retention_policy_source="explicit_class",
            storage_backend=materialized.storage_backend,
            storage_object_key=materialized.storage_object_key,
            storage_delete_status=materialized.storage_delete_status,
        )
    else:
        with repository.transaction() as owned_connection:
            repository.save_artifact_record(
                owned_connection,
                artifact_ref=artifact_ref,
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                logical_path=logical_path,
                kind="MARKDOWN" if media_type == "text/markdown" else "TEXT",
                media_type=media_type,
                materialization_status="MATERIALIZED",
                lifecycle_status="ACTIVE",
                storage_relpath=materialized.storage_relpath,
                content_hash=materialized.content_hash,
                size_bytes=materialized.size_bytes,
                retention_class="PERSISTENT",
                expires_at=None,
                deleted_at=None,
                deleted_by=None,
                delete_reason=None,
                created_at=now_local(),
                retention_class_source="explicit",
                retention_policy_source="explicit_class",
                storage_backend=materialized.storage_backend,
                storage_object_key=materialized.storage_object_key,
                storage_delete_status=materialized.storage_delete_status,
            )
    return artifact_ref


def _materialize_workspace_text(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    relative_path: str,
    content: str,
    media_type: str,
    connection: sqlite3.Connection | None = None,
) -> str:
    workspace_root = resolve_project_workspace_root(workflow_id)
    _write_text(workspace_root / relative_path, content)
    return _mirror_text_artifact(
        repository,
        artifact_store=repository.artifact_store,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path=relative_path,
        content=content,
        media_type=media_type,
        connection=connection,
    )


def _bootstrap_agile_docs(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    north_star_goal: str,
) -> tuple[list[str], list[str]]:
    canonical_doc_refs = [
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/AGENTS.md",
            content="# AGENTS\n\nLoad the matching docs before making changes.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/ARCHITECTURE.md",
            content=f"# Architecture\n\n- Goal: {north_star_goal}\n- Current profile: AGILE\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/L0-context/project-brief.md",
            content=(
                "# Project Brief\n\n"
                f"- Goal: {north_star_goal}\n"
                "- Profile: AGILE\n"
                "- Workspace truth lives in this project directory.\n"
            ),
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/L0-context/boundaries.md",
            content="# Boundaries\n\n- Keep governance explicit.\n- Keep project docs and evidence auditable.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/tracking/task-index.md",
            content="# Task Index\n\n- No active ticket summary yet.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/tracking/active-tasks.md",
            content="# Active Tasks\n\n- This file will be updated by code-delivery tickets.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/history/context-baseline.md",
            content="# Context Baseline\n\n- Stable project rules live here.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/history/memory-recent.md",
            content="# Memory Recent\n\n- Recent implementation facts live here.\n",
            media_type="text/markdown",
        ),
    ]
    _materialize_workspace_text(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path="10-project/docs/README.md",
        content="# Docs Index\n\n- Start from L0-context and tracking.\n",
        media_type="text/markdown",
    )
    for relative_path in (
        "10-project/src/.gitkeep",
        "10-project/tests/.gitkeep",
        "20-evidence/tests/.gitkeep",
        "20-evidence/builds/.gitkeep",
        "20-evidence/reviews/.gitkeep",
        "20-evidence/git/.gitkeep",
        "20-evidence/releases/.gitkeep",
    ):
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path=relative_path,
            content="",
            media_type="text/plain",
        )
    return canonical_doc_refs, [
        "10-project/docs/tracking/active-tasks.md",
        "10-project/docs/history/memory-recent.md",
    ]


def _bootstrap_hybrid_docs(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    north_star_goal: str,
) -> tuple[list[str], list[str]]:
    canonical_doc_refs, default_doc_updates = _bootstrap_agile_docs(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        north_star_goal=north_star_goal,
    )
    canonical_doc_refs.extend(
        [
            _materialize_workspace_text(
                repository,
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                relative_path="10-project/docs/L0-context/phase-status.md",
                content="# Phase Status\n\n- Current phase: implementation\n",
                media_type="text/markdown",
            ),
            _materialize_workspace_text(
                repository,
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                relative_path="10-project/docs/traceability/req-to-design.md",
                content="# Traceability\n\n- Requirement to design mapping starts here.\n",
                media_type="text/markdown",
            ),
            _materialize_workspace_text(
                repository,
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                relative_path="10-project/docs/baselines/README.md",
                content="# Baselines\n\n- Store baseline snapshots here.\n",
                media_type="text/markdown",
            ),
        ]
    )
    return canonical_doc_refs, default_doc_updates


def _bootstrap_compliance_docs(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    north_star_goal: str,
) -> tuple[list[str], list[str]]:
    canonical_doc_refs = [
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/AGENTS.md",
            content="# AGENTS\n\nFollow phase gates and traceability before coding.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/ARCHITECTURE.md",
            content=f"# Architecture\n\n- Goal: {north_star_goal}\n- Current profile: COMPLIANCE\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/L0-context/project-charter.md",
            content="# Project Charter\n\n- Compliance-oriented project workspace.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/L0-context/traceability-index.md",
            content="# Traceability Index\n\n- Coverage summary goes here.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/L0-context/phase-status.md",
            content="# Phase Status\n\n- Current phase: requirements\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/01-requirements/srs/_summary.md",
            content="# SRS Summary\n\n| Requirement ID | Summary |\n|---|---|\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/03-implementation/change-log/current-change.md",
            content="# Current Change\n\n- Active change request notes.\n",
            media_type="text/markdown",
        ),
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path="10-project/docs/history/memory-recent.md",
            content="# Memory Recent\n\n- Recent compliance-relevant facts live here.\n",
            media_type="text/markdown",
        ),
    ]
    for relative_path in (
        "20-evidence/tests/.gitkeep",
        "20-evidence/builds/.gitkeep",
        "20-evidence/reviews/.gitkeep",
        "20-evidence/git/.gitkeep",
        "20-evidence/releases/.gitkeep",
    ):
        _materialize_workspace_text(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            relative_path=relative_path,
            content="",
            media_type="text/plain",
        )
    return canonical_doc_refs, [
        "10-project/docs/03-implementation/change-log/current-change.md",
        "10-project/docs/history/memory-recent.md",
    ]


def bootstrap_project_workspace(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    north_star_goal: str,
    methodology_profile: ProjectMethodologyProfile,
) -> ProjectWorkspaceBootstrap:
    workspace_root = resolve_project_workspace_root(workflow_id)
    for relative_dir in (
        "00-boardroom/workflow",
        "00-boardroom/tickets",
        "00-boardroom/workspaces",
        "00-boardroom/agents",
        "00-boardroom/hooks",
        "10-project/docs",
        "20-evidence",
    ):
        (workspace_root / relative_dir).mkdir(parents=True, exist_ok=True)

    if methodology_profile == ProjectMethodologyProfile.COMPLIANCE:
        canonical_doc_refs, default_doc_updates = _bootstrap_compliance_docs(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            north_star_goal=north_star_goal,
        )
    elif methodology_profile == ProjectMethodologyProfile.HYBRID:
        canonical_doc_refs, default_doc_updates = _bootstrap_hybrid_docs(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            north_star_goal=north_star_goal,
        )
    else:
        canonical_doc_refs, default_doc_updates = _bootstrap_agile_docs(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            north_star_goal=north_star_goal,
        )

    workspace_ref = build_project_workspace_ref(workflow_id)
    manifest = {
        "workflow_id": workflow_id,
        "project_workspace_ref": workspace_ref,
        "project_workspace_root": str(workspace_root),
        "project_methodology_profile": methodology_profile.value,
        "canonical_doc_refs": canonical_doc_refs,
        "default_doc_update_requirements": default_doc_updates,
    }
    manifest_content = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _materialize_workspace_text(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path="00-boardroom/workflow/methodology-profile.md",
        content=f"# Methodology Profile\n\n- {methodology_profile.value}\n",
        media_type="text/markdown",
    )
    _materialize_workspace_text(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path="00-boardroom/workflow/phase-status.md",
        content="# Phase Status\n\n- Current phase: project-init\n",
        media_type="text/markdown",
    )
    _materialize_workspace_text(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path="00-boardroom/workflow/hook-policy.md",
        content=(
            "# Hook Policy\n\n"
            "- project-bootstrap\n"
            "- worker-preflight\n"
            "- worker-postrun\n"
            "- evidence-capture\n"
            "- git-closeout\n"
        ),
        media_type="text/markdown",
    )
    _materialize_workspace_text(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path="00-boardroom/workflow/active-worktree-index.md",
        content="# Active Worktrees\n\n- No active worktree recorded yet.\n",
        media_type="text/markdown",
    )
    _materialize_workspace_text(
        repository,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        relative_path="00-boardroom/workflow/workspace-manifest.json",
        content=manifest_content,
        media_type="text/plain",
    )
    initialize_project_git_repository(workflow_id)
    return ProjectWorkspaceBootstrap(
        workspace_ref=workspace_ref,
        workspace_root=workspace_root,
        methodology_profile=methodology_profile,
        canonical_doc_refs=canonical_doc_refs,
        default_doc_update_requirements=default_doc_updates,
    )


def bootstrap_ticket_dossier(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    summary: str,
    required_read_refs: list[str],
    doc_update_requirements: list[str],
    git_policy: GitPolicy | str,
    deliverable_kind: DeliverableKind | str,
    allowed_write_set: list[str],
    project_checkout_ref: str | None = None,
    git_branch_ref: str | None = None,
) -> None:
    resolved_git_policy = (
        git_policy if isinstance(git_policy, GitPolicy) else GitPolicy(str(git_policy))
    )
    resolved_deliverable_kind = (
        deliverable_kind
        if isinstance(deliverable_kind, DeliverableKind)
        else DeliverableKind(str(deliverable_kind))
    )
    dossier_root = resolve_project_workspace_root(workflow_id) / "00-boardroom" / "tickets" / ticket_id
    (dossier_root / "hook-receipts").mkdir(parents=True, exist_ok=True)
    required_reads_lines = "\n".join(f"- `{ref}`" for ref in required_read_refs) or "- None"
    doc_update_lines = "\n".join(f"- `{ref}`" for ref in doc_update_requirements) or "- None"
    write_set_lines = "\n".join(f"- `{item}`" for item in allowed_write_set) or "- None"
    files = {
        "00-boardroom/tickets/{ticket_id}/brief.md": (
            "# Ticket Brief\n\n"
            f"- Ticket ID: `{ticket_id}`\n"
            f"- Summary: {summary}\n"
            f"- Deliverable Kind: `{resolved_deliverable_kind.value}`\n"
        ),
        "00-boardroom/tickets/{ticket_id}/required-reads.md": (
            "# Required Reads\n\n"
            f"{required_reads_lines}\n"
        ),
        "00-boardroom/tickets/{ticket_id}/execution-log.md": "# Execution Log\n\n- Ticket execution has not started yet.\n",
        "00-boardroom/tickets/{ticket_id}/doc-impact.md": (
            "# Doc Impact\n\n"
            "## Required Updates\n"
            f"{doc_update_lines}\n"
        ),
        "00-boardroom/tickets/{ticket_id}/git-closeout.md": (
            "# Git Closeout\n\n"
            f"- Git policy: `{resolved_git_policy.value}`\n"
            "- Merge boundary: `review_gate`\n"
            f"- Branch ref: `{git_branch_ref or default_ticket_branch_ref(ticket_id)}`\n"
            f"- Checkout ref: `{project_checkout_ref or build_project_checkout_ref(workflow_id, ticket_id)}`\n"
        ),
        "00-boardroom/tickets/{ticket_id}/allowed-write-set.md": (
            "# Allowed Write Set\n\n"
            f"{write_set_lines}\n"
        ),
    }
    for relative_path_template, content in files.items():
        target_path = resolve_project_workspace_root(workflow_id) / relative_path_template.format(ticket_id=ticket_id)
        _write_text(target_path, content)


def infer_ticket_workspace_bootstrap(ticket_payload: dict[str, Any]) -> TicketWorkspaceBootstrap:
    workflow_id = str(ticket_payload.get("workflow_id") or "").strip()
    if not workflow_id:
        raise ValueError("Ticket payload is missing workflow_id.")
    try:
        manifest = load_project_workspace_manifest(workflow_id)
    except FileNotFoundError:
        manifest = {
            "project_workspace_ref": build_project_workspace_ref(workflow_id),
            "project_methodology_profile": ProjectMethodologyProfile.AGILE.value,
            "canonical_doc_refs": [],
            "default_doc_update_requirements": [],
        }
    deliverable_kind = (
        DeliverableKind(str(ticket_payload["deliverable_kind"]))
        if ticket_payload.get("deliverable_kind") is not None
        else infer_deliverable_kind(ticket_payload.get("output_schema_ref"))
    )
    required_read_refs = list(ticket_payload.get("required_read_refs") or []) or list(
        manifest.get("canonical_doc_refs") or []
    )
    doc_update_requirements = list(ticket_payload.get("doc_update_requirements") or [])
    if not doc_update_requirements and (
        deliverable_kind == DeliverableKind.SOURCE_CODE_DELIVERY
        or str(ticket_payload.get("output_schema_ref") or "").strip() == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF
    ):
        doc_update_requirements = list(manifest.get("default_doc_update_requirements") or [])
    git_policy = (
        GitPolicy(str(ticket_payload["git_policy"]))
        if ticket_payload.get("git_policy") is not None
        else infer_git_policy(deliverable_kind)
    )
    is_workspace_managed_source_delivery = (
        deliverable_kind == DeliverableKind.SOURCE_CODE_DELIVERY
        and any(
            str(pattern or "").startswith(("10-project/", "20-evidence/", "00-boardroom/"))
            for pattern in list(ticket_payload.get("allowed_write_set") or [])
        )
    )
    ticket_id = str(ticket_payload.get("ticket_id") or "").strip()
    return TicketWorkspaceBootstrap(
        project_workspace_ref=str(ticket_payload.get("project_workspace_ref") or manifest["project_workspace_ref"]),
        project_methodology_profile=ProjectMethodologyProfile(
            str(
                ticket_payload.get("project_methodology_profile")
                or manifest["project_methodology_profile"]
            )
        ),
        deliverable_kind=deliverable_kind,
        canonical_doc_refs=list(ticket_payload.get("canonical_doc_refs") or []) or list(
            manifest.get("canonical_doc_refs") or []
        ),
        required_read_refs=required_read_refs,
        doc_update_requirements=doc_update_requirements,
        git_policy=git_policy,
        project_checkout_ref=(
            build_project_checkout_ref(workflow_id, ticket_id)
            if is_workspace_managed_source_delivery and ticket_id
            else None
        ),
        git_branch_ref=(
            default_ticket_branch_ref(ticket_id)
            if is_workspace_managed_source_delivery and ticket_id
            else None
        ),
    )


def write_worker_preflight_receipt(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    required_read_refs: list[str],
    input_process_asset_refs: list[str],
    connection: sqlite3.Connection | None = None,
) -> str:
    receipt_payload = {
        "ticket_id": ticket_id,
        "required_read_refs": list(required_read_refs),
        "input_process_asset_refs": list(input_process_asset_refs),
    }
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "worker-preflight.json"
    )
    _write_json(receipt_path, receipt_payload)
    return str(receipt_path)


def write_worker_postrun_receipt(
    *,
    workflow_id: str,
    ticket_id: str,
    documentation_updates: list[dict[str, Any]],
) -> str:
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "worker-postrun.json"
    )
    _write_json(
        receipt_path,
        {
            "ticket_id": ticket_id,
            "documentation_updates": list(documentation_updates),
        },
    )
    return str(receipt_path)


def write_evidence_capture_receipt(
    *,
    workflow_id: str,
    ticket_id: str,
    verification_evidence_refs: list[str],
) -> str:
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "evidence-capture.json"
    )
    _write_json(
        receipt_path,
        {
            "ticket_id": ticket_id,
            "verification_evidence_refs": list(verification_evidence_refs),
        },
    )
    return str(receipt_path)


def write_git_closeout_receipt(
    *,
    workflow_id: str,
    ticket_id: str,
    git_commit_record: dict[str, Any],
) -> str:
    receipt_path = (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / "git-closeout.json"
    )
    _write_json(
        receipt_path,
        {
            "ticket_id": ticket_id,
            "git_commit_record": dict(git_commit_record),
        },
    )
    return str(receipt_path)


def _active_worktree_index_path(workflow_id: str) -> Path:
    return resolve_project_workspace_root(workflow_id) / "00-boardroom" / "workflow" / "active-worktree-index.md"


def _latest_started_by(
    repository: ControlPlaneRepository,
    *,
    connection: sqlite3.Connection,
    ticket_id: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT actor_id, payload_json
        FROM events
        WHERE event_type = 'TICKET_STARTED' AND json_extract(payload_json, '$.ticket_id') = ?
        ORDER BY occurred_at DESC, event_id DESC
        LIMIT 1
        """,
        (ticket_id,),
    ).fetchone()
    if row is None:
        return None
    actor_id = str(row["actor_id"] or "").strip()
    if actor_id:
        return actor_id
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    started_by = str((payload or {}).get("started_by") or "").strip()
    return started_by or None


def is_workspace_managed_source_code_ticket(created_spec: dict[str, Any]) -> bool:
    if str(created_spec.get("deliverable_kind") or "") != DeliverableKind.SOURCE_CODE_DELIVERY.value:
        return False
    return any(
        str(pattern or "").startswith(("10-project/", "20-evidence/", "00-boardroom/"))
        for pattern in list(created_spec.get("allowed_write_set") or [])
    )


def resolve_source_code_ticket_from_chain(
    repository: ControlPlaneRepository,
    *,
    connection: sqlite3.Connection,
    ticket_id: str,
) -> str | None:
    current_ticket_id = str(ticket_id or "").strip()
    seen_ticket_ids: set[str] = set()
    while current_ticket_id and current_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(current_ticket_id)
        created_spec = repository.get_latest_ticket_created_payload(connection, current_ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "") == SOURCE_CODE_DELIVERY_SCHEMA_REF:
            return current_ticket_id
        current_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
    return None


def _serialize_worktree_index_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    serialized = str(value or "").strip()
    return serialized


def sync_active_worktree_index(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection: sqlite3.Connection | None = None,
) -> str:
    index_path = _active_worktree_index_path(workflow_id)
    if not project_workspace_manifest_exists(workflow_id):
        return str(index_path)

    owns_connection = connection is None
    context = repository.connection() if owns_connection else None
    resolved_connection = context.__enter__() if context is not None else connection
    try:
        assert resolved_connection is not None
        rows = resolved_connection.execute(
            """
            SELECT *
            FROM ticket_projection
            WHERE workflow_id = ?
            ORDER BY updated_at ASC, ticket_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        entries: list[dict[str, str]] = []
        for row in rows:
            ticket = repository._convert_ticket_projection_row(row)
            ticket_id = str(ticket["ticket_id"])
            created_spec = repository.get_latest_ticket_created_payload(resolved_connection, ticket_id) or {}
            if not is_workspace_managed_source_code_ticket(created_spec):
                continue

            status = str(ticket.get("status") or "").strip()
            worker = str(ticket.get("lease_owner") or "").strip() or (_latest_started_by(
                repository,
                connection=resolved_connection,
                ticket_id=ticket_id,
            ) or "")
            branch_ref = str(created_spec.get("git_branch_ref") or default_ticket_branch_ref(ticket_id))
            commit_sha = ""
            merge_status = ""
            display_status = ""

            if status == "EXECUTING":
                checkout_receipt = load_worktree_checkout_receipt(workflow_id, ticket_id)
                branch_ref = str(checkout_receipt.get("git_branch_ref") or branch_ref).strip()
                display_status = "EXECUTING"
            elif status == "COMPLETED":
                git_commit_record = load_git_closeout_receipt(workflow_id, ticket_id)
                branch_ref = str(git_commit_record.get("branch_ref") or branch_ref).strip()
                commit_sha = str(git_commit_record.get("commit_sha") or "").strip()
                merge_status = str(git_commit_record.get("merge_status") or "").strip()
                if merge_status != "PENDING_REVIEW_GATE":
                    continue
                display_status = "PENDING_REVIEW_GATE"
            else:
                continue

            entries.append(
                {
                    "ticket_id": ticket_id,
                    "node_id": str(ticket.get("node_id") or "").strip(),
                    "worker": worker,
                    "status": display_status,
                    "branch_ref": branch_ref,
                    "commit_sha": commit_sha,
                    "merge_status": merge_status,
                    "updated_at": _serialize_worktree_index_timestamp(ticket.get("updated_at")),
                }
            )

        if not entries:
            content = "# Active Worktrees\n\n- No active worktree recorded yet.\n"
        else:
            lines = [
                "# Active Worktrees",
                "",
                "| ticket_id | node_id | worker | status | branch_ref | commit_sha | merge_status | updated_at |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
            for entry in entries:
                lines.append(
                    "| {ticket_id} | {node_id} | {worker} | {status} | {branch_ref} | {commit_sha} | {merge_status} | {updated_at} |".format(
                        **entry
                    )
                )
            content = "\n".join(lines) + "\n"
        _write_text(index_path, content)
        return str(index_path)
    finally:
        if context is not None:
            context.__exit__(None, None, None)
