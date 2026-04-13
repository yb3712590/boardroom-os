from __future__ import annotations

from pathlib import Path

from app.contracts.commands import DeveloperInspectorRefs
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.ticket_context_archive import (
    build_ticket_context_markdown,
    write_ticket_context_markdown,
)
from tests.test_context_compiler import _ticket_create_payload, _ticket_lease_payload


def test_build_ticket_context_markdown_includes_review_sections(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compiled_artifacts = compile_and_persist_execution_artifacts(repository, ticket)

    markdown = build_ticket_context_markdown(
        compiled_artifacts.compiled_execution_package.model_dump(mode="json"),
        developer_inspector_refs=DeveloperInspectorRefs(
            compiled_context_bundle_ref="ctx://compile/tkt_compile_001",
            compile_manifest_ref="manifest://compile/tkt_compile_001",
            rendered_execution_payload_ref="render://compile/tkt_compile_001",
        ),
    )

    assert "# Ticket 执行卡片: tkt_compile_001" in markdown
    assert "## 基本信息" in markdown
    assert "## 输入上下文" in markdown
    assert "## 编译健康度" in markdown
    assert "## 输出信息" in markdown
    assert "source_ref" in markdown
    assert "tokens_before" in markdown
    assert "ctx://compile/tkt_compile_001" in markdown
    assert "render://compile/tkt_compile_001" in markdown


def test_write_ticket_context_markdown_persists_one_file_per_ticket(tmp_path: Path):
    archive_root = tmp_path / "ticket_context_archives"

    output_path = write_ticket_context_markdown(
        archive_root,
        {
            "meta": {
                "workflow_id": "wf_live_demo",
                "ticket_id": "tkt_live_demo",
                "node_id": "node_live_demo",
            },
            "execution": {
                "role_profile_ref": "architect_primary",
                "output_schema_ref": "architecture_brief",
                "allowed_write_set": ["reports/architecture/*"],
                "project_checkout_path": "D:/tmp/wf_live_demo/checkout/tkt_live_demo",
                "git_branch_ref": "codex/tkt_live_demo",
            },
            "org_context": {
                "responsibility_boundary": {
                    "delivery_stage": None,
                    "output_schema_ref": "architecture_brief",
                    "allowed_write_set": ["reports/architecture/*"],
                }
            },
            "atomic_context_bundle": {
                "token_budget": 3000,
                "context_blocks": [
                    {
                        "source_kind": "PROCESS_ASSET",
                        "content_mode": "INLINE_FULL",
                        "degradation_reason_code": None,
                        "source_ref": "art://project-init/wf_live_demo/board-brief.md",
                        "content_type": "TEXT",
                        "selector": {"selector_type": "SOURCE_REF", "selector_value": "art://project-init/wf_live_demo/board-brief.md"},
                        "content_payload": {
                            "text": "# Brief\n\nBuild an atomic architecture plan."
                        }
                    }
                ]
            },
            "governance": {
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "escalation_policy": {
                    "on_timeout": "retry",
                    "on_schema_error": "retry",
                    "on_repeat_failure": "escalate_ceo",
                },
            },
            "terminal_state": {
                "status": "COMPLETED",
                "result_status": "completed",
                "artifact_paths": [
                    "reports/architecture/tkt_live_demo/architecture-brief.json",
                    "reports/architecture/tkt_live_demo/architecture-brief.audit.md",
                ],
            },
            "compile_manifest": {
                "budget_plan": {"total_budget_tokens": 3000},
                "budget_actual": {"final_bundle_tokens": 420, "truncated_tokens": 0},
                "degradation": {"warnings": [], "is_degraded": False},
                "cache_report": {"cache_hit": False},
                "source_log": [
                    {
                        "source_ref": "art://project-init/wf_live_demo/board-brief.md",
                        "source_kind": "PROCESS_ASSET",
                        "content_mode": "INLINE_FULL",
                        "tokens_before": 120,
                        "tokens_after": 120,
                        "reason_code": None,
                        "status": "USED",
                    }
                ],
            },
            "rendered_execution_payload": {
                "messages": [
                    {
                        "role": "system",
                        "channel": "SYSTEM_CONTROLS",
                        "content_type": "TEXT",
                        "content_payload": {"text": "Use structured output."},
                    }
                ]
            },
        },
        developer_inspector_refs=DeveloperInspectorRefs(
            compiled_context_bundle_ref="ctx://compile/tkt_live_demo",
            compile_manifest_ref="manifest://compile/tkt_live_demo",
            rendered_execution_payload_ref="render://compile/tkt_live_demo",
        ),
    )

    assert output_path == archive_root / "tkt_live_demo.md"
    assert output_path.exists()
    body = output_path.read_text(encoding="utf-8")
    assert "architect_primary" in body
    assert "D:/tmp/wf_live_demo/checkout/tkt_live_demo" in body
    assert "reports/architecture/tkt_live_demo/architecture-brief.audit.md" in body
    assert "Token 预算" in body
