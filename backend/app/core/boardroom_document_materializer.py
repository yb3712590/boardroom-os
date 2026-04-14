from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


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
