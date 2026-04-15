from __future__ import annotations

from pathlib import Path

from app.contracts.commands import DeveloperInspectorRefs
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.ticket_context_archive import (
    build_ticket_context_markdown,
    is_ticket_context_stale,
    write_ticket_context_markdown,
)
from tests.test_context_compiler import (
    _configure_runtime_provider,
    _seed_governance_profile,
    _ticket_create_payload,
    _ticket_lease_payload,
)


def test_build_ticket_context_markdown_includes_review_sections(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _configure_runtime_provider(client)
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
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
    assert "## 治理切片" in markdown
    assert "## 技能绑定" in markdown
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
                "governance_profile_ref": "gp_live_demo",
            },
            "governance_mode_slice": {
                "governance_profile_ref": "gp_live_demo",
                "approval_mode": "AUTO_CEO",
                "audit_mode": "MINIMAL",
                "auto_approval_scope": ["scope:mainline_internal"],
                "expert_review_targets": ["checker", "board"],
                "audit_materialization_policy": {
                    "ticket_context_archive": False,
                    "full_timeline": False,
                    "closeout_evidence": True,
                },
            },
            "task_frame": {
                "task_category": "planning",
                "goal": "Produce a governed architecture brief.",
                "completion_definition": ["Return a structured architecture brief."],
                "failure_definition": ["Reject schema-invalid output."],
                "deliverable_kind": "structured_document_delivery",
            },
            "required_doc_surfaces": ["10-project/docs/tracking/active-tasks.md"],
            "context_layer_summary": {
                "w0_constitution": {
                    "label": "W0 Constitution",
                    "item_count": 1,
                    "notes": ["approval_mode=AUTO_CEO", "audit_mode=MINIMAL"],
                    "governance_profile_ref": "gp_live_demo",
                    "allowed_tool_count": None,
                    "allowed_write_set_count": None,
                },
                "w1_task_frame": {
                    "label": "W1 Task Frame",
                    "item_count": 1,
                    "notes": ["output_schema=architecture_brief"],
                    "governance_profile_ref": None,
                    "allowed_tool_count": None,
                    "allowed_write_set_count": None,
                },
                "w2_evidence": {
                    "label": "W2 Evidence Slice",
                    "item_count": 1,
                    "notes": ["required_read_refs=0"],
                    "governance_profile_ref": None,
                    "allowed_tool_count": None,
                    "allowed_write_set_count": None,
                },
                "w3_runtime_guard": {
                    "label": "W3 Runtime Guard",
                    "item_count": 1,
                    "notes": ["forced_skill_ids=0"],
                    "governance_profile_ref": None,
                    "allowed_tool_count": 0,
                    "allowed_write_set_count": 1,
                },
            },
            "skill_binding": {
                "binding_id": "sb_tkt_live_demo_1",
                "binding_version": 1,
                "task_category": "planning",
                "audit_mode": "MINIMAL",
                "forced_skill_ids": [],
                "resolved_skill_ids": ["planning_governance"],
                "binding_reason": "Structured governance delivery uses planning skills.",
                "binding_scope": "execution_package",
                "conflict_resolution": "no_conflict",
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
    assert "gp_live_demo" in body
    assert "planning_governance" in body
    assert "reports/architecture/tkt_live_demo/architecture-brief.audit.md" in body
    assert "Token 预算" in body


def test_ticket_context_markdown_includes_version_metadata_and_stale_status(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _configure_runtime_provider(client)
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    assert ticket is not None

    first = compile_and_persist_execution_artifacts(repository, ticket)
    set_ticket_time("2026-03-28T10:05:00+08:00")
    compile_and_persist_execution_artifacts(repository, ticket)

    assert is_ticket_context_stale(
        repository,
        ticket_id="tkt_compile_001",
        compile_request_id=first.compiled_execution_package.meta.compile_request_id,
        compiled_execution_package_version_ref=first.compiled_execution_package.meta.version_ref,
    )

    markdown = build_ticket_context_markdown(
        first.compiled_execution_package.model_dump(mode="json"),
        compile_manifest=first.compile_manifest.model_dump(mode="json"),
        terminal_state={
            "status": "COMPLETED",
            "result_status": "completed",
            "artifact_paths": [],
            "stale_against_latest": True,
        },
    )

    assert "Compile Request" in markdown
    assert str(first.compiled_execution_package.meta.version_ref) in markdown
    assert "Source Projection Version" in markdown
    assert "Stale Against Latest Package" in markdown
    assert "`是`" in markdown
