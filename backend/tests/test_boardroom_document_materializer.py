from __future__ import annotations

import pytest

from app.core.boardroom_document_materializer import (
    BoardroomViewDocument,
    BoardroomViewMeta,
    render_active_worktree_index_markdown,
    render_ticket_doc_impact_markdown,
)


def test_render_active_worktree_index_markdown_includes_metadata_header_and_rows() -> None:
    document = BoardroomViewDocument(
        meta=BoardroomViewMeta(
            view_kind="active_worktree_index",
            generated_at="2026-04-14T05:00:00Z",
            source_projection_version=42,
            source_refs=["ticket_projection:wf_demo", "receipt:worktree-checkout:tkt_demo"],
            stale_check_key="workflow:wf_demo:active_worktree_index:v42",
        ),
        title="Active Worktrees",
        sections={
            "entries": [
                {
                    "ticket_id": "tkt_demo",
                    "node_id": "node_demo",
                    "worker": "emp_frontend_2",
                    "status": "EXECUTING",
                    "branch_ref": "codex/tkt_demo",
                    "commit_sha": "",
                    "merge_status": "",
                    "updated_at": "2026-04-14T05:00:00Z",
                }
            ]
        },
    )

    markdown = render_active_worktree_index_markdown(document)

    assert "# Active Worktrees" in markdown
    assert "- View Kind: `active_worktree_index`" in markdown
    assert "- Source Projection Version: `42`" in markdown
    assert "- Stale Check Key: `workflow:wf_demo:active_worktree_index:v42`" in markdown
    assert "- Source Refs: `ticket_projection:wf_demo, receipt:worktree-checkout:tkt_demo`" in markdown
    assert "| ticket_id | node_id | worker | status | branch_ref | commit_sha | merge_status | updated_at |" in markdown
    assert "tkt_demo" in markdown


def test_render_ticket_doc_impact_markdown_requires_source_refs() -> None:
    document = BoardroomViewDocument(
        meta=BoardroomViewMeta(
            view_kind="ticket_doc_impact",
            generated_at="2026-04-14T05:00:00Z",
            source_projection_version=42,
            source_refs=[],
            stale_check_key="ticket:tkt_demo:doc_impact:v42",
        ),
        title="Doc Impact",
        sections={"required_updates": [], "reported_updates": []},
    )

    with pytest.raises(ValueError, match="source_refs"):
        render_ticket_doc_impact_markdown(document)
