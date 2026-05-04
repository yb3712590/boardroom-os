from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, get_args
from uuid import uuid4

from app.contracts.process_assets import ProcessAssetKind


BOARDROOM_DOCUMENT_VIEW_VERSION = "boardroom-document-view.v1"

_PROCESS_ASSET_REF_PREFIX = "pa://"
_ARTIFACT_REF_KEYS = {
    "artifact_ref",
    "source_artifact_ref",
    "written_artifact_refs",
    "verification_evidence_refs",
    "final_artifact_refs",
    "linked_artifact_refs",
}
_PROCESS_ASSET_REF_KEYS = {
    "source_process_asset_refs",
    "linked_process_asset_refs",
}
_DOCUMENT_FAIL_CLOSED_REASON_CODES = {
    "invalid_process_asset",
    "process_asset_outside_event_range",
    "evidence_lineage_break",
    "missing_artifact",
    "artifact_not_materialized",
    "unregistered_storage_ref",
    "missing_content_hash",
    "storage_read_failed",
    "artifact_hash_mismatch",
}
_SUPPORTED_PROCESS_ASSET_KINDS = set(get_args(ProcessAssetKind))


@dataclass(frozen=True)
class BoardroomViewMeta:
    view_kind: str
    generated_at: str
    source_projection_version: int | None
    source_refs: list[str] = field(default_factory=list)
    stale_check_key: str | None = None


@dataclass(frozen=True)
class BoardroomViewDocument:
    meta: BoardroomViewMeta
    title: str
    sections: dict[str, Any] = field(default_factory=dict)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_unique(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _source_event_range_label(source_event_range: dict[str, int] | None) -> str:
    if source_event_range is None:
        return "replay-event-range:unknown"
    return (
        "replay-event-range:"
        f"{int(source_event_range['start_sequence_no'])}-{int(source_event_range['end_sequence_no'])}"
    )


def _event_range_contains_version(source_event_range: dict[str, int] | None, version: Any) -> bool:
    if source_event_range is None:
        return True
    try:
        sequence_no = int(version)
    except (TypeError, ValueError):
        return False
    return (
        int(source_event_range["start_sequence_no"])
        <= sequence_no
        <= int(source_event_range["end_sequence_no"])
    )


def _collect_refs(value: Any, target_keys: set[str]) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in target_keys:
                if isinstance(item, str):
                    refs.append(item)
                elif isinstance(item, list):
                    refs.extend(str(ref) for ref in item if str(ref).strip())
            refs.extend(_collect_refs(item, target_keys))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_collect_refs(item, target_keys))
    return refs


def verify_artifact_storage_content_hash(
    repository: Any,
    artifact_store: Any | None,
    artifact_ref: str,
) -> dict[str, Any]:
    artifact = repository.get_artifact_by_ref(artifact_ref)
    if artifact is None:
        return {
            "artifact": None,
            "content_hash": None,
            "diagnostic": {
                "reason_code": "missing_artifact",
                "artifact_ref": artifact_ref,
                "message": "Document materialization requires an artifact_index row.",
            },
        }

    status = str(artifact.get("materialization_status") or "").strip()
    expected_content_hash = (
        str(artifact.get("content_hash")).strip()
        if artifact.get("content_hash") is not None
        else None
    )
    if status != "MATERIALIZED":
        return {
            "artifact": artifact,
            "content_hash": expected_content_hash,
            "diagnostic": {
                "reason_code": "artifact_not_materialized",
                "artifact_ref": artifact_ref,
                "materialization_status": status,
                "message": "Document materialization only reads storage for MATERIALIZED artifacts.",
            },
        }

    storage_relpath = str(artifact.get("storage_relpath") or "").strip() or None
    storage_object_key = str(artifact.get("storage_object_key") or "").strip() or None
    if storage_relpath is None and storage_object_key is None:
        return {
            "artifact": artifact,
            "content_hash": expected_content_hash,
            "diagnostic": {
                "reason_code": "unregistered_storage_ref",
                "artifact_ref": artifact_ref,
                "message": "Materialized artifact has no registered storage_relpath or storage_object_key.",
            },
        }
    if not expected_content_hash:
        return {
            "artifact": artifact,
            "content_hash": None,
            "diagnostic": {
                "reason_code": "missing_content_hash",
                "artifact_ref": artifact_ref,
                "message": "Materialized artifact is missing content_hash in artifact_index.",
            },
        }
    if artifact_store is None:
        return {
            "artifact": artifact,
            "content_hash": expected_content_hash,
            "diagnostic": {
                "reason_code": "storage_read_failed",
                "artifact_ref": artifact_ref,
                "message": "Artifact store is unavailable for document materialization.",
            },
        }

    try:
        content = artifact_store.read_bytes(
            storage_relpath,
            storage_object_key=storage_object_key,
        )
    except Exception as exc:
        return {
            "artifact": artifact,
            "content_hash": expected_content_hash,
            "diagnostic": {
                "reason_code": "storage_read_failed",
                "artifact_ref": artifact_ref,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        }

    actual_content_hash = hashlib.sha256(content).hexdigest()
    if actual_content_hash != expected_content_hash:
        return {
            "artifact": artifact,
            "content_hash": expected_content_hash,
            "content_refs": [],
            "diagnostic": {
                "reason_code": "artifact_hash_mismatch",
                "artifact_ref": artifact_ref,
                "expected_content_hash": expected_content_hash,
                "actual_content_hash": actual_content_hash,
            },
        }
    content_refs: list[str] = []
    media_type = str(artifact.get("media_type") or "").lower()
    kind = str(artifact.get("kind") or "").strip().upper()
    if kind == "JSON" or "json" in media_type:
        try:
            decoded = json.loads(content.decode("utf-8"))
            content_refs = _stable_unique(_collect_refs(decoded, _ARTIFACT_REF_KEYS))
        except (UnicodeDecodeError, json.JSONDecodeError):
            content_refs = []
    return {
        "artifact": artifact,
        "content_hash": expected_content_hash,
        "content_refs": content_refs,
        "diagnostic": None,
    }


def _render_replay_process_asset_markdown(
    *,
    process_asset: dict[str, Any],
    artifact_rows: list[dict[str, Any]],
    artifact_content_hashes: dict[str, str],
    source_event_range: dict[str, int] | None,
) -> str:
    lines = [
        "# Replay Materialized Process Asset View",
        "",
        "## View Metadata",
        f"- Document View Version: `{BOARDROOM_DOCUMENT_VIEW_VERSION}`",
        f"- Generated At: `{_source_event_range_label(source_event_range)}`",
        f"- Source Event Range: `{_source_event_range_label(source_event_range)}`",
        f"- Process Asset Ref: `{process_asset['process_asset_ref']}`",
        f"- Canonical Ref: `{process_asset.get('canonical_ref') or process_asset['process_asset_ref']}`",
        f"- Process Asset Kind: `{process_asset.get('process_asset_kind') or 'N/A'}`",
        f"- Workflow ID: `{process_asset.get('workflow_id') or 'N/A'}`",
        f"- Producer Ticket ID: `{process_asset.get('producer_ticket_id') or 'N/A'}`",
        f"- Producer Node ID: `{process_asset.get('producer_node_id') or 'N/A'}`",
        f"- Graph Version: `{process_asset.get('graph_version') or 'N/A'}`",
        f"- Source Projection Version: `{process_asset.get('version') or 'N/A'}`",
        f"- Visibility Status: `{process_asset.get('visibility_status') or 'N/A'}`",
        f"- Process Asset Content Hash: `{process_asset.get('content_hash') or 'N/A'}`",
        "",
        "## Summary",
        str(process_asset.get("summary") or "N/A"),
        "",
        "## Linked Process Assets",
    ]
    linked_refs = _stable_unique(list(process_asset.get("linked_process_asset_refs") or []))
    if linked_refs:
        lines.extend(f"- `{ref}`" for ref in linked_refs)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Artifact Evidence",
            "",
            "| artifact_ref | logical_path | kind | media_type | content_hash | size_bytes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if artifact_rows:
        for artifact in artifact_rows:
            artifact_ref = str(artifact.get("artifact_ref") or "").strip()
            lines.append(
                "| {artifact_ref} | {logical_path} | {kind} | {media_type} | {content_hash} | {size_bytes} |".format(
                    artifact_ref=artifact_ref or "N/A",
                    logical_path=str(artifact.get("logical_path") or "N/A"),
                    kind=str(artifact.get("kind") or "N/A"),
                    media_type=str(artifact.get("media_type") or "N/A"),
                    content_hash=artifact_content_hashes.get(artifact_ref) or "N/A",
                    size_bytes=str(artifact.get("size_bytes") if artifact.get("size_bytes") is not None else "N/A"),
                )
            )
    else:
        lines.append("| N/A | N/A | N/A | N/A | N/A | N/A |")

    source_metadata = dict(process_asset.get("source_metadata") or {})
    lines.extend(
        [
            "",
            "## Source Metadata",
            "```json",
            json.dumps(source_metadata, sort_keys=True, indent=2, default=str),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def materialize_document_views_from_process_assets(
    repository: Any,
    artifact_store: Any | None,
    *,
    process_asset_refs: list[str],
    source_event_range: dict[str, int] | None,
) -> dict[str, Any]:
    normalized_process_asset_refs = _stable_unique(list(process_asset_refs))
    diagnostics: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    document_refs: list[str] = []
    content_hashes: dict[str, str] = {}
    all_artifact_refs: list[str] = []

    for process_asset_ref in normalized_process_asset_refs:
        asset_diagnostics: list[dict[str, Any]] = []
        if not process_asset_ref.startswith(_PROCESS_ASSET_REF_PREFIX):
            asset_diagnostics.append(
                {
                    "reason_code": "invalid_process_asset",
                    "process_asset_ref": process_asset_ref,
                    "message": "Document materialization requires a canonical pa:// process asset ref.",
                }
            )

        process_asset = repository.get_process_asset_index_entry(process_asset_ref)
        if process_asset is None:
            asset_diagnostics.append(
                {
                    "reason_code": "invalid_process_asset",
                    "process_asset_ref": process_asset_ref,
                    "message": "Process asset is missing from process_asset_index.",
                }
            )
            diagnostics.extend(asset_diagnostics)
            continue

        process_asset_kind = str(process_asset.get("process_asset_kind") or "").strip()
        if process_asset_kind not in _SUPPORTED_PROCESS_ASSET_KINDS:
            asset_diagnostics.append(
                {
                    "reason_code": "invalid_process_asset",
                    "process_asset_ref": process_asset_ref,
                    "process_asset_kind": process_asset_kind,
                    "message": "Process asset kind is not part of the versioned process asset contract.",
                }
            )
        if not _event_range_contains_version(source_event_range, process_asset.get("version")):
            asset_diagnostics.append(
                {
                    "reason_code": "process_asset_outside_event_range",
                    "process_asset_ref": process_asset_ref,
                    "process_asset_version": process_asset.get("version"),
                    "source_event_range": dict(source_event_range) if source_event_range is not None else None,
                }
            )
        if str(process_asset.get("visibility_status") or "").strip() != "CONSUMABLE":
            asset_diagnostics.append(
                {
                    "reason_code": "evidence_lineage_break",
                    "process_asset_ref": process_asset_ref,
                    "visibility_status": process_asset.get("visibility_status"),
                    "message": "Only CONSUMABLE process assets can be materialized into replay document views.",
                }
            )

        source_metadata = dict(process_asset.get("source_metadata") or {})
        linked_process_asset_refs = _stable_unique(
            [
                *list(process_asset.get("linked_process_asset_refs") or []),
                *_collect_refs(source_metadata, _PROCESS_ASSET_REF_KEYS),
            ]
        )
        for linked_ref in linked_process_asset_refs:
            linked_asset = repository.get_process_asset_index_entry(linked_ref)
            if linked_asset is None or str(linked_asset.get("visibility_status") or "").strip() != "CONSUMABLE":
                asset_diagnostics.append(
                    {
                        "reason_code": "evidence_lineage_break",
                        "process_asset_ref": process_asset_ref,
                        "linked_process_asset_ref": linked_ref,
                        "message": "Linked process asset lineage is missing or not consumable.",
                    }
                )

        artifact_refs = _stable_unique(_collect_refs(source_metadata, _ARTIFACT_REF_KEYS))
        artifact_rows: list[dict[str, Any]] = []
        artifact_content_hashes: dict[str, str] = {}
        pending_artifact_refs = list(artifact_refs)
        seen_artifact_refs: set[str] = set()
        artifact_refs = []
        while pending_artifact_refs:
            artifact_ref = pending_artifact_refs.pop(0)
            if artifact_ref in seen_artifact_refs:
                continue
            seen_artifact_refs.add(artifact_ref)
            artifact_refs.append(artifact_ref)
            verification = verify_artifact_storage_content_hash(
                repository,
                artifact_store,
                artifact_ref,
            )
            diagnostic = verification.get("diagnostic")
            if diagnostic is not None:
                asset_diagnostics.append(dict(diagnostic))
                continue
            artifact = verification.get("artifact")
            if isinstance(artifact, dict):
                artifact_rows.append(artifact)
            content_hash = str(verification.get("content_hash") or "").strip()
            if content_hash:
                artifact_content_hashes[artifact_ref] = content_hash
            pending_artifact_refs.extend(
                ref
                for ref in list(verification.get("content_refs") or [])
                if str(ref).strip() and str(ref).strip() not in seen_artifact_refs
            )
        all_artifact_refs.extend(artifact_refs)

        diagnostics.extend(asset_diagnostics)
        if any(item.get("reason_code") in _DOCUMENT_FAIL_CLOSED_REASON_CODES for item in asset_diagnostics):
            continue

        markdown = _render_replay_process_asset_markdown(
            process_asset=process_asset,
            artifact_rows=sorted(
                artifact_rows,
                key=lambda item: str(item.get("artifact_ref") or ""),
            ),
            artifact_content_hashes=artifact_content_hashes,
            source_event_range=source_event_range,
        )
        document_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        document_ref = f"doc://materialized-view/process-asset/{_sha256({'process_asset_ref': process_asset_ref, 'content_hash': document_hash})}"
        document_refs.append(document_ref)
        content_hashes[document_ref] = document_hash
        entries.append(
            {
                "document_ref": document_ref,
                "process_asset_ref": process_asset_ref,
                "artifact_refs": _stable_unique(artifact_refs),
                "content_hash": document_hash,
                "document_view_version": BOARDROOM_DOCUMENT_VIEW_VERSION,
                "source_event_range": dict(source_event_range) if source_event_range is not None else None,
            }
        )
        diagnostics.append(
            {
                "reason_code": "materialized_document_hash_verified",
                "process_asset_ref": process_asset_ref,
                "document_ref": document_ref,
                "content_hash": document_hash,
            }
        )

    status = (
        "FAILED"
        if any(item.get("reason_code") in _DOCUMENT_FAIL_CLOSED_REASON_CODES for item in diagnostics)
        else "READY"
    )
    return {
        "status": status,
        "document_view_version": BOARDROOM_DOCUMENT_VIEW_VERSION,
        "source_event_range": dict(source_event_range) if source_event_range is not None else None,
        "process_asset_refs": normalized_process_asset_refs,
        "artifact_refs": _stable_unique(all_artifact_refs),
        "document_refs": document_refs,
        "content_hashes": content_hashes,
        "entries": entries,
        "diagnostics": diagnostics,
    }


def _require_source_refs(document: BoardroomViewDocument) -> None:
    if not document.meta.source_refs:
        raise ValueError(f"{document.meta.view_kind} requires non-empty source_refs.")


def _metadata_lines(document: BoardroomViewDocument) -> list[str]:
    _require_source_refs(document)
    return [
        f"# {document.title}",
        "",
        "## View Metadata",
        f"- View Kind: `{document.meta.view_kind}`",
        f"- Generated At: `{document.meta.generated_at}`",
        f"- Source Projection Version: `{document.meta.source_projection_version if document.meta.source_projection_version is not None else 'N/A'}`",
        f"- Source Refs: `{', '.join(document.meta.source_refs)}`",
        f"- Stale Check Key: `{document.meta.stale_check_key or 'N/A'}`",
    ]


def render_active_worktree_index_markdown(document: BoardroomViewDocument) -> str:
    lines = _metadata_lines(document)
    entries = [
        dict(item)
        for item in list(document.sections.get("entries") or [])
        if isinstance(item, dict)
    ]
    lines.extend(["", "## Active Worktrees"])
    if not entries:
        lines.append("- No active worktree recorded yet.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "",
            "| ticket_id | node_id | worker | status | branch_ref | commit_sha | merge_status | updated_at |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for entry in entries:
        lines.append(
            "| {ticket_id} | {node_id} | {worker} | {status} | {branch_ref} | {commit_sha} | {merge_status} | {updated_at} |".format(
                ticket_id=str(entry.get("ticket_id") or "").strip() or "N/A",
                node_id=str(entry.get("node_id") or "").strip() or "N/A",
                worker=str(entry.get("worker") or "").strip() or "N/A",
                status=str(entry.get("status") or "").strip() or "N/A",
                branch_ref=str(entry.get("branch_ref") or "").strip() or "N/A",
                commit_sha=str(entry.get("commit_sha") or "").strip() or "N/A",
                merge_status=str(entry.get("merge_status") or "").strip() or "N/A",
                updated_at=str(entry.get("updated_at") or "").strip() or "N/A",
            )
        )
    return "\n".join(lines) + "\n"


def render_ticket_brief_markdown(document: BoardroomViewDocument) -> str:
    lines = _metadata_lines(document)
    lines.extend(
        [
            "",
            "## Ticket Brief",
            f"- Ticket ID: `{document.sections.get('ticket_id') or 'N/A'}`",
            f"- Node ID: `{document.sections.get('node_id') or 'N/A'}`",
            f"- Status: `{document.sections.get('ticket_status') or 'N/A'}`",
            f"- Deliverable Kind: `{document.sections.get('deliverable_kind') or 'N/A'}`",
            f"- Summary: {str(document.sections.get('summary') or '').strip() or 'N/A'}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_ticket_required_reads_markdown(document: BoardroomViewDocument) -> str:
    lines = _metadata_lines(document)
    required_reads = [
        str(item).strip()
        for item in list(document.sections.get("required_read_refs") or [])
        if str(item).strip()
    ]
    lines.extend(["", "## Required Reads"])
    if required_reads:
        lines.extend(f"- `{item}`" for item in required_reads)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def render_ticket_doc_impact_markdown(document: BoardroomViewDocument) -> str:
    lines = _metadata_lines(document)
    required_updates = [
        str(item).strip()
        for item in list(document.sections.get("required_updates") or [])
        if str(item).strip()
    ]
    reported_updates = [
        dict(item)
        for item in list(document.sections.get("reported_updates") or [])
        if isinstance(item, dict)
    ]
    report_status = str(document.sections.get("report_status") or "").strip() or "not_reported"
    lines.extend(
        [
            "",
            "## Doc Impact",
            f"- Documentation Report Status: `{report_status}`",
            "",
            "## Required Updates",
        ]
    )
    if required_updates:
        lines.extend(f"- `{item}`" for item in required_updates)
    else:
        lines.append("- None")
    lines.extend(["", "## Reported Updates"])
    if reported_updates:
        for item in reported_updates:
            lines.append(
                f"- `{str(item.get('doc_ref') or '').strip() or 'N/A'}` "
                f"`{str(item.get('status') or '').strip() or 'N/A'}` "
                f"{str(item.get('summary') or '').strip() or 'N/A'}"
            )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def render_ticket_git_closeout_markdown(document: BoardroomViewDocument) -> str:
    lines = _metadata_lines(document)
    lines.extend(
        [
            "",
            "## Git Closeout",
            f"- Git policy: `{document.sections.get('git_policy') or 'N/A'}`",
            f"- Merge boundary: `{document.sections.get('merge_boundary') or 'review_gate'}`",
            f"- Branch ref: `{document.sections.get('branch_ref') or 'N/A'}`",
            f"- Checkout ref: `{document.sections.get('checkout_ref') or 'N/A'}`",
            f"- Checkout path: `{document.sections.get('checkout_path') or 'N/A'}`",
            f"- Commit SHA: `{document.sections.get('commit_sha') or 'N/A'}`",
            f"- Merge status: `{document.sections.get('merge_status') or 'N/A'}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_boardroom_view_markdown(
    target_path: Path,
    document: BoardroomViewDocument,
    *,
    renderer: Callable[[BoardroomViewDocument], str],
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    body = renderer(document)
    temp_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return target_path
