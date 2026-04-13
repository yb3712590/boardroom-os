from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from app.contracts.commands import DeveloperInspectorRefs


def _display_text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "N/A"


def _display_tokens(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "-"


def _display_bool(value: Any) -> str:
    return "是" if bool(value) else "否"


def _display_list(values: list[Any] | tuple[Any, ...] | None) -> str:
    rendered = [str(item).strip() for item in values or [] if str(item).strip()]
    return ", ".join(rendered) if rendered else "N/A"


def _resolve_compile_manifest(
    compiled_execution_package: Mapping[str, Any],
    *,
    compile_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if compile_manifest is not None:
        return dict(compile_manifest)
    embedded = compiled_execution_package.get("compile_manifest")
    return dict(embedded or {}) if isinstance(embedded, Mapping) else {}


def _resolve_terminal_state(
    compiled_execution_package: Mapping[str, Any],
    *,
    terminal_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if terminal_state is not None:
        return dict(terminal_state)
    embedded = compiled_execution_package.get("terminal_state")
    return dict(embedded or {}) if isinstance(embedded, Mapping) else {}


def _build_context_rows(
    *,
    context_blocks: list[dict[str, Any]],
    compile_manifest: Mapping[str, Any],
) -> list[dict[str, str]]:
    block_by_ref = {
        str(block.get("source_ref") or "").strip(): dict(block)
        for block in context_blocks
        if str(block.get("source_ref") or "").strip()
    }
    rows: list[dict[str, str]] = []
    source_log = [
        dict(item)
        for item in list(compile_manifest.get("source_log") or [])
        if isinstance(item, Mapping)
    ]
    if source_log:
        for entry in source_log:
            source_ref = str(entry.get("source_ref") or "").strip() or "N/A"
            block = block_by_ref.get(source_ref, {})
            degraded = bool(
                block.get("degradation_reason_code")
                or str(entry.get("status") or "").upper() in {"TRUNCATED", "SUMMARIZED", "DROPPED", "MISSING"}
                or str(entry.get("content_mode") or block.get("content_mode") or "").upper() != "INLINE_FULL"
            )
            rows.append(
                {
                    "source_ref": source_ref,
                    "source_kind": _display_text(entry.get("source_kind") or block.get("source_kind")),
                    "tokens_before": _display_tokens(entry.get("tokens_before")),
                    "tokens_after": _display_tokens(entry.get("tokens_after")),
                    "content_mode": _display_text(entry.get("content_mode") or block.get("content_mode")),
                    "truncated_or_degraded": "yes" if degraded else "no",
                }
            )
        return rows

    for block in context_blocks:
        degraded = bool(
            block.get("degradation_reason_code")
            or str(block.get("content_mode") or "").upper() != "INLINE_FULL"
        )
        rows.append(
            {
                "source_ref": _display_text(block.get("source_ref")),
                "source_kind": _display_text(block.get("source_kind")),
                "tokens_before": "-",
                "tokens_after": "-",
                "content_mode": _display_text(block.get("content_mode")),
                "truncated_or_degraded": "yes" if degraded else "no",
            }
        )
    return rows


def _developer_inspector_lines(
    developer_inspector_refs: DeveloperInspectorRefs | None,
) -> list[str]:
    lines = ["## Developer Inspector Refs"]
    if developer_inspector_refs is None:
        lines.append("- None")
        return lines
    if developer_inspector_refs.compiled_context_bundle_ref is not None:
        lines.append(f"- Compiled Context Bundle: `{developer_inspector_refs.compiled_context_bundle_ref}`")
    if developer_inspector_refs.compile_manifest_ref is not None:
        lines.append(f"- Compile Manifest: `{developer_inspector_refs.compile_manifest_ref}`")
    if developer_inspector_refs.rendered_execution_payload_ref is not None:
        lines.append(f"- Rendered Execution Payload: `{developer_inspector_refs.rendered_execution_payload_ref}`")
    if len(lines) == 1:
        lines.append("- None")
    return lines


def build_ticket_context_markdown(
    compiled_execution_package: Mapping[str, Any],
    *,
    developer_inspector_refs: DeveloperInspectorRefs | None = None,
    compile_manifest: Mapping[str, Any] | None = None,
    terminal_state: Mapping[str, Any] | None = None,
) -> str:
    meta = dict(compiled_execution_package.get("meta") or {})
    execution = dict(compiled_execution_package.get("execution") or {})
    compiled_role = dict(compiled_execution_package.get("compiled_role") or {})
    org_context = dict(compiled_execution_package.get("org_context") or {})
    responsibility_boundary = dict(org_context.get("responsibility_boundary") or {})
    atomic_context_bundle = dict(compiled_execution_package.get("atomic_context_bundle") or {})
    resolved_compile_manifest = _resolve_compile_manifest(
        compiled_execution_package,
        compile_manifest=compile_manifest,
    )
    resolved_terminal_state = _resolve_terminal_state(
        compiled_execution_package,
        terminal_state=terminal_state,
    )
    context_blocks = [
        dict(block)
        for block in list(atomic_context_bundle.get("context_blocks") or [])
        if isinstance(block, Mapping)
    ]
    context_rows = _build_context_rows(
        context_blocks=context_blocks,
        compile_manifest=resolved_compile_manifest,
    )

    budget_plan = dict(resolved_compile_manifest.get("budget_plan") or {})
    budget_actual = dict(resolved_compile_manifest.get("budget_actual") or {})
    degradation = dict(resolved_compile_manifest.get("degradation") or {})
    cache_report = dict(resolved_compile_manifest.get("cache_report") or {})
    artifact_paths = [
        str(item).strip()
        for item in list(resolved_terminal_state.get("artifact_paths") or [])
        if str(item).strip()
    ]
    warning_lines = [
        str(item).strip()
        for item in list(degradation.get("warnings") or [])
        if str(item).strip()
    ]

    lines = [
        f"# Ticket 执行卡片: {meta.get('ticket_id') or 'unknown-ticket'}",
        "",
        "## 基本信息",
        f"- Workflow: `{meta.get('workflow_id') or 'unknown'}`",
        f"- Ticket: `{meta.get('ticket_id') or 'unknown'}`",
        f"- Node: `{meta.get('node_id') or 'unknown'}`",
        f"- Role: `{compiled_role.get('role_profile_ref') or execution.get('role_profile_ref') or 'unknown'}`",
        f"- Output Schema: `{execution.get('output_schema_ref') or responsibility_boundary.get('output_schema_ref') or 'unknown'}`",
        f"- 当前状态: `{resolved_terminal_state.get('status') or resolved_terminal_state.get('result_status') or 'EXECUTING'}`",
        "",
        "## 输入上下文",
        f"- 来源数: `{len(context_rows)}`",
        "",
        "| source_ref | source_kind | tokens_before | tokens_after | content_mode | truncated_or_degraded |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if context_rows:
        for row in context_rows:
            lines.append(
                f"| {row['source_ref']} | {row['source_kind']} | {row['tokens_before']} | "
                f"{row['tokens_after']} | {row['content_mode']} | {row['truncated_or_degraded']} |"
            )
    else:
        lines.append("| none | none | - | - | none | no |")

    lines.extend(
        [
            "",
            "## 编译健康度",
            f"- Token 预算: `{_display_tokens(budget_plan.get('total_budget_tokens'))}`",
            f"- 实际使用: `{_display_tokens(budget_actual.get('final_bundle_tokens'))}`",
            f"- Truncated Tokens: `{_display_tokens(budget_actual.get('truncated_tokens'))}`",
            f"- 降级: `{_display_bool(degradation.get('is_degraded'))}`",
            f"- Cache Hit: `{_display_bool(cache_report.get('cache_hit'))}`",
            "- Warnings:",
        ]
    )
    if warning_lines:
        lines.extend(f"  - {item}" for item in warning_lines)
    else:
        lines.append("  - 无")

    lines.extend(
        [
            "",
            "## 输出信息",
            f"- Allowed Write Set: `{_display_list(execution.get('allowed_write_set'))}`",
            f"- Project Checkout: `{execution.get('project_checkout_path') or 'N/A'}`",
            f"- Git Branch: `{execution.get('git_branch_ref') or 'N/A'}`",
            f"- Delivery Stage: `{responsibility_boundary.get('delivery_stage') or execution.get('delivery_stage') or 'N/A'}`",
            "- Artifact Paths:",
        ]
    )
    if artifact_paths:
        lines.extend(f"  - `{item}`" for item in artifact_paths)
    else:
        lines.append("  - N/A")

    lines.extend(
        [
            "",
            *_developer_inspector_lines(developer_inspector_refs),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_ticket_context_markdown(
    archive_root: Path,
    compiled_execution_package: Mapping[str, Any],
    *,
    developer_inspector_refs: DeveloperInspectorRefs | None = None,
    compile_manifest: Mapping[str, Any] | None = None,
    terminal_state: Mapping[str, Any] | None = None,
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
        compile_manifest=compile_manifest,
        terminal_state=terminal_state,
    )
    try:
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(target_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return target_path
