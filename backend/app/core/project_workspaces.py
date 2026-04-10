from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
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
PROJECT_WORKSPACE_ARTIFACT_PREFIX = "art://project-workspace"
PROJECT_WORKSPACE_LOGICAL_PREFIX = "project-workspaces"


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


def build_project_workspace_ref(workflow_id: str) -> str:
    return f"{WORKSPACE_REF_PREFIX}{workflow_id}"


def resolve_project_workspace_root(workflow_id: str) -> Path:
    return get_settings().project_workspace_root / workflow_id


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
    if normalized in {
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        UI_MILESTONE_REVIEW_SCHEMA_REF,
        MAKER_CHECKER_VERDICT_SCHEMA_REF,
    }:
        return DeliverableKind.REVIEW_EVIDENCE
    if normalized == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return DeliverableKind.CLOSEOUT_EVIDENCE
    return DeliverableKind.STRUCTURED_DOCUMENT_DELIVERY


def infer_git_policy(deliverable_kind: DeliverableKind) -> GitPolicy:
    if deliverable_kind == DeliverableKind.SOURCE_CODE_DELIVERY:
        return GitPolicy.PER_TICKET_COMMIT_REQUIRED
    return GitPolicy.NO_GIT_REQUIRED


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
    if not doc_update_requirements and deliverable_kind == DeliverableKind.SOURCE_CODE_DELIVERY:
        doc_update_requirements = list(manifest.get("default_doc_update_requirements") or [])
    git_policy = (
        GitPolicy(str(ticket_payload["git_policy"]))
        if ticket_payload.get("git_policy") is not None
        else infer_git_policy(deliverable_kind)
    )
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
