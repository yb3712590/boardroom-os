from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from typing import Any, Mapping

from app.contracts.commands import DeveloperInspectorRefs


def _json_preview(value: Any, *, limit: int = 320) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(serialized) <= limit:
        return serialized
    return f"{serialized[: limit - 3]}..."


def _text_preview(value: Any, *, limit: int = 320) -> str:
    text = str(value or "").strip().replace("\r", "")
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _message_preview(content_payload: Any) -> str:
    if isinstance(content_payload, Mapping):
        if isinstance(content_payload.get("text"), str):
            return _text_preview(content_payload["text"])
        return _json_preview(content_payload)
    return _text_preview(content_payload)


def _context_block_summary(block: Mapping[str, Any]) -> str:
    content_payload = block.get("content_payload")
    if isinstance(content_payload, Mapping):
        if isinstance(content_payload.get("text"), str):
            return _text_preview(content_payload["text"])
        if isinstance(content_payload.get("content_url"), str):
            return _text_preview(content_payload.get("content_url"))
    return _message_preview(content_payload)


def build_ticket_context_markdown(
    compiled_execution_package: Mapping[str, Any],
    *,
    developer_inspector_refs: DeveloperInspectorRefs | None = None,
) -> str:
    meta = dict(compiled_execution_package.get("meta") or {})
    execution = dict(compiled_execution_package.get("execution") or {})
    org_context = dict(compiled_execution_package.get("org_context") or {})
    responsibility_boundary = dict(org_context.get("responsibility_boundary") or {})
    rendered_execution_payload = dict(compiled_execution_package.get("rendered_execution_payload") or {})
    messages = list(rendered_execution_payload.get("messages") or [])
    context_blocks = list(
        (compiled_execution_package.get("atomic_context_bundle") or {}).get("context_blocks") or []
    )

    lines = [
        f"# Ticket Context Archive: {meta.get('ticket_id') or 'unknown-ticket'}",
        "",
        "## Ticket",
        f"- Workflow ID: `{meta.get('workflow_id') or 'unknown'}`",
        f"- Ticket ID: `{meta.get('ticket_id') or 'unknown'}`",
        f"- Node ID: `{meta.get('node_id') or 'unknown'}`",
        f"- Role Profile: `{execution.get('role_profile_ref') or 'unknown'}`",
        f"- Output Schema: `{execution.get('output_schema_ref') or 'unknown'}`",
        "",
        "## Execution Contract",
        f"- Delivery Stage: `{responsibility_boundary.get('delivery_stage') or execution.get('delivery_stage') or 'N/A'}`",
        f"- Parent Ticket ID: `{execution.get('parent_ticket_id') or 'N/A'}`",
        f"- Dependency Ticket Refs: `{', '.join(execution.get('dependency_ticket_refs') or []) or 'N/A'}`",
        f"- Allowed Write Set: `{', '.join(execution.get('allowed_write_set') or []) or 'N/A'}`",
        "",
        "## Org Context",
        f"- Responsibility Output Schema: `{responsibility_boundary.get('output_schema_ref') or 'unknown'}`",
        f"- Downstream Reviewer: `{((org_context.get('downstream_reviewer') or {}).get('role_profile_ref')) or 'N/A'}`",
        f"- Current Blocking Reason: `{((org_context.get('escalation_path') or {}).get('current_blocking_reason')) or 'N/A'}`",
        f"- Collaborator Count: `{len(org_context.get('collaborators') or [])}`",
        "",
        "## Developer Inspector Refs",
    ]

    if developer_inspector_refs is None:
        lines.append("- None")
    else:
        if developer_inspector_refs.compiled_context_bundle_ref is not None:
            lines.append(f"- Compiled Context Bundle: `{developer_inspector_refs.compiled_context_bundle_ref}`")
        if developer_inspector_refs.compile_manifest_ref is not None:
            lines.append(f"- Compile Manifest: `{developer_inspector_refs.compile_manifest_ref}`")
        if developer_inspector_refs.rendered_execution_payload_ref is not None:
            lines.append(
                f"- Rendered Execution Payload: `{developer_inspector_refs.rendered_execution_payload_ref}`"
            )

    lines.extend(["", "## Context Blocks"])
    if not context_blocks:
        lines.append("- None")
    for index, block in enumerate(context_blocks, start=1):
        block_mapping = dict(block or {})
        lines.extend(
            [
                f"### Block {index}",
                f"- Source Ref: `{block_mapping.get('source_ref') or 'N/A'}`",
                f"- Content Type: `{block_mapping.get('content_type') or 'unknown'}`",
                f"- Preview: {_context_block_summary(block_mapping)}",
                "",
            ]
        )

    lines.append("## Rendered Messages")
    if not messages:
        lines.append("- None")
    for index, message in enumerate(messages, start=1):
        message_mapping = dict(message or {})
        lines.extend(
            [
                f"### Message {index}",
                f"- Role: `{message_mapping.get('role') or 'unknown'}`",
                f"- Channel: `{message_mapping.get('channel') or 'unknown'}`",
                f"- Content Type: `{message_mapping.get('content_type') or 'unknown'}`",
                f"- Preview: {_message_preview(message_mapping.get('content_payload'))}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_ticket_context_markdown(
    archive_root: Path,
    compiled_execution_package: Mapping[str, Any],
    *,
    developer_inspector_refs: DeveloperInspectorRefs | None = None,
) -> Path:
    meta = dict(compiled_execution_package.get("meta") or {})
    ticket_id = str(meta.get("ticket_id") or "").strip()
    if not ticket_id:
        raise ValueError("compiled_execution_package.meta.ticket_id is required.")

    archive_root.mkdir(parents=True, exist_ok=True)
    target_path = archive_root / f"{ticket_id}.md"
    temp_path = target_path.with_name(f"{target_path.name}.{uuid4().hex}.tmp")
    body = build_ticket_context_markdown(
        compiled_execution_package,
        developer_inspector_refs=developer_inspector_refs,
    )
    try:
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(target_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return target_path
