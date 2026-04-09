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

    assert "# Ticket Context Archive: tkt_compile_001" in markdown
    assert "## Execution Contract" in markdown
    assert "## Org Context" in markdown
    assert "## Context Blocks" in markdown
    assert "## Rendered Messages" in markdown
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
            },
            "org_context": {
                "responsibility_boundary": {
                    "delivery_stage": None,
                    "output_schema_ref": "architecture_brief",
                    "allowed_write_set": ["reports/architecture/*"],
                }
            },
            "atomic_context_bundle": {
                "context_blocks": [
                    {
                        "source_ref": "art://project-init/wf_live_demo/board-brief.md",
                        "content_type": "TEXT",
                        "content_payload": {
                            "text": "# Brief\n\nBuild an atomic architecture plan."
                        },
                    }
                ]
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
    assert "architect_primary" in output_path.read_text(encoding="utf-8")
