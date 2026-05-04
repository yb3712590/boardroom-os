from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from app.core.artifact_store import ArtifactStore
from app.core.boardroom_document_materializer import (
    BOARDROOM_DOCUMENT_VIEW_VERSION,
    BoardroomViewDocument,
    BoardroomViewMeta,
    materialize_document_views_from_process_assets,
    render_active_worktree_index_markdown,
    render_ticket_doc_impact_markdown,
)
from app.core.constants import (
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_WORKFLOW_CREATED,
)
from app.core.reducer import rebuild_process_asset_index
from app.db.repository import ControlPlaneRepository


def _event(sequence_no: int, event_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_no": sequence_no,
        "event_id": event_id,
        "event_type": event_type,
        "workflow_id": "wf_document_view",
        "occurred_at": datetime.fromisoformat(f"2026-05-04T10:{sequence_no:02d}:00+08:00"),
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def _repository_with_document_process_asset(
    tmp_path,
    *,
    artifact_ref: str = "art://runtime/tkt_document_view/governance-document.json",
    artifact_content: str = '{"summary":"Replay materialized governance document"}',
    extra_artifact_refs: list[str] | None = None,
    save_artifact: bool = True,
    process_asset_ref: str = "pa://governance-document/tkt_document_view@1",
    process_asset_kind: str = "GOVERNANCE_DOCUMENT",
    visibility_status: str = "CONSUMABLE",
    linked_process_asset_refs: list[str] | None = None,
) -> tuple[ControlPlaneRepository, ArtifactStore, str, str]:
    artifact_store = ArtifactStore(tmp_path / "artifacts")
    repository = ControlPlaneRepository(tmp_path / "document-view.db", 1000, artifact_store=artifact_store)
    repository.initialize()
    materialized = artifact_store.materialize_text(
        "reports/document-view/governance-document.json",
        artifact_content,
        media_type="application/json",
    )
    if save_artifact:
        with repository.transaction() as connection:
            repository.save_artifact_record(
                connection,
                artifact_ref=artifact_ref,
                workflow_id="wf_document_view",
                ticket_id="tkt_document_view",
                node_id="node_document_view",
                logical_path="reports/document-view/governance-document.json",
                kind="JSON",
                media_type="application/json",
                materialization_status="MATERIALIZED",
                lifecycle_status="ACTIVE",
                storage_backend=materialized.storage_backend,
                storage_relpath=materialized.storage_relpath,
                storage_object_key=materialized.storage_object_key,
                storage_delete_status=materialized.storage_delete_status,
                content_hash=materialized.content_hash,
                size_bytes=materialized.size_bytes,
                retention_class="PERSISTENT",
                expires_at=None,
                deleted_at=None,
                deleted_by=None,
                delete_reason=None,
                created_at=datetime.fromisoformat("2026-05-04T10:03:00+08:00"),
            )
            for index, extra_artifact_ref in enumerate(extra_artifact_refs or [], start=1):
                extra_materialized = artifact_store.materialize_text(
                    f"reports/document-view/evidence-{index}.json",
                    '{"summary":"Replay materialized evidence"}',
                    media_type="application/json",
                )
                repository.save_artifact_record(
                    connection,
                    artifact_ref=extra_artifact_ref,
                    workflow_id="wf_document_view",
                    ticket_id="tkt_document_view",
                    node_id="node_document_view",
                    logical_path=f"reports/document-view/evidence-{index}.json",
                    kind="JSON",
                    media_type="application/json",
                    materialization_status="MATERIALIZED",
                    lifecycle_status="ACTIVE",
                    storage_backend=extra_materialized.storage_backend,
                    storage_relpath=extra_materialized.storage_relpath,
                    storage_object_key=extra_materialized.storage_object_key,
                    storage_delete_status=extra_materialized.storage_delete_status,
                    content_hash=extra_materialized.content_hash,
                    size_bytes=extra_materialized.size_bytes,
                    retention_class="PERSISTENT",
                    expires_at=None,
                    deleted_at=None,
                    deleted_by=None,
                    delete_reason=None,
                    created_at=datetime.fromisoformat("2026-05-04T10:03:00+08:00"),
                )
    events = [
        _event(
            1,
            "evt_document_wf",
            EVENT_WORKFLOW_CREATED,
            {
                "north_star_goal": "Document materialization",
                "budget_cap": 500000,
                "deadline_at": None,
                "title": "Document materialization",
            },
        ),
        _event(
            2,
            "evt_document_ticket",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_document_view",
                "node_id": "node_document_view",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "normal",
            },
        ),
        _event(
            3,
            "evt_document_completed",
            EVENT_TICKET_COMPLETED,
            {
                "workflow_id": "wf_document_view",
                "ticket_id": "tkt_document_view",
                "node_id": "node_document_view",
                "produced_process_assets": [
                    {
                        "process_asset_ref": process_asset_ref,
                        "canonical_ref": process_asset_ref,
                        "version_int": 1,
                        "process_asset_kind": process_asset_kind,
                        "workflow_id": "wf_document_view",
                        "producer_ticket_id": "tkt_document_view",
                        "producer_node_id": "node_document_view",
                        "graph_version": "gv_3",
                        "visibility_status": visibility_status,
                        "linked_process_asset_refs": linked_process_asset_refs or [],
                        "summary": "Replay governance document",
                        "source_metadata": {
                            "source_artifact_ref": artifact_ref,
                            "linked_artifact_refs": [artifact_ref],
                            "source_process_asset_refs": linked_process_asset_refs or [],
                        },
                    }
                ],
            },
        ),
    ]
    with repository.transaction() as connection:
        repository.replace_process_asset_index(connection, rebuild_process_asset_index(events))
    return repository, artifact_store, process_asset_ref, artifact_ref


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


def test_materialize_document_view_from_replayed_process_asset_and_artifact_content(tmp_path) -> None:
    repository, artifact_store, process_asset_ref, artifact_ref = _repository_with_document_process_asset(tmp_path)

    result = materialize_document_views_from_process_assets(
        repository,
        artifact_store,
        process_asset_refs=[process_asset_ref],
        source_event_range={"start_sequence_no": 1, "end_sequence_no": 3},
    )

    assert result["status"] == "READY"
    assert result["document_view_version"] == BOARDROOM_DOCUMENT_VIEW_VERSION
    assert result["source_event_range"] == {"start_sequence_no": 1, "end_sequence_no": 3}
    assert result["process_asset_refs"] == [process_asset_ref]
    assert result["artifact_refs"] == [artifact_ref]
    assert result["document_refs"][0].startswith("doc://materialized-view/process-asset/")
    document_ref = result["document_refs"][0]
    assert result["content_hashes"][document_ref]
    assert result["entries"][0]["process_asset_ref"] == process_asset_ref
    assert result["entries"][0]["artifact_refs"] == [artifact_ref]
    assert result["diagnostics"] == [
        {
            "reason_code": "materialized_document_hash_verified",
            "process_asset_ref": process_asset_ref,
            "document_ref": document_ref,
            "content_hash": result["content_hashes"][document_ref],
        }
    ]


def test_materialize_document_view_fails_closed_when_artifact_is_missing(tmp_path) -> None:
    repository, artifact_store, process_asset_ref, artifact_ref = _repository_with_document_process_asset(
        tmp_path,
        save_artifact=False,
    )

    result = materialize_document_views_from_process_assets(
        repository,
        artifact_store,
        process_asset_refs=[process_asset_ref],
        source_event_range={"start_sequence_no": 1, "end_sequence_no": 3},
    )

    assert result["status"] == "FAILED"
    assert result["diagnostics"][0]["reason_code"] == "missing_artifact"
    assert result["diagnostics"][0]["artifact_ref"] == artifact_ref


def test_materialize_document_view_collects_refs_from_artifact_json_content(tmp_path) -> None:
    evidence_ref = "art://runtime/tkt_document_view/evidence.json"
    repository, artifact_store, process_asset_ref, artifact_ref = _repository_with_document_process_asset(
        tmp_path,
        artifact_content=json.dumps(
            {
                "summary": "Replay materialized governance document",
                "linked_artifact_refs": [evidence_ref],
            },
            sort_keys=True,
        ),
        extra_artifact_refs=[evidence_ref],
    )

    result = materialize_document_views_from_process_assets(
        repository,
        artifact_store,
        process_asset_refs=[process_asset_ref],
        source_event_range={"start_sequence_no": 1, "end_sequence_no": 3},
    )

    assert result["status"] == "READY"
    assert result["artifact_refs"] == sorted([artifact_ref, evidence_ref])
    assert result["entries"][0]["artifact_refs"] == sorted([artifact_ref, evidence_ref])


def test_materialize_document_view_fails_closed_when_process_asset_is_invalid(tmp_path) -> None:
    repository, artifact_store, process_asset_ref, _artifact_ref = _repository_with_document_process_asset(
        tmp_path,
        process_asset_ref="not-a-process-asset-ref",
        process_asset_kind="UNKNOWN_KIND",
    )

    result = materialize_document_views_from_process_assets(
        repository,
        artifact_store,
        process_asset_refs=[process_asset_ref],
        source_event_range={"start_sequence_no": 1, "end_sequence_no": 3},
    )

    assert result["status"] == "FAILED"
    assert result["diagnostics"][0]["reason_code"] == "invalid_process_asset"
    assert result["diagnostics"][0]["process_asset_ref"] == process_asset_ref


def test_materialize_document_view_fails_closed_when_evidence_lineage_is_invalid(tmp_path) -> None:
    repository, artifact_store, process_asset_ref, _artifact_ref = _repository_with_document_process_asset(
        tmp_path,
        visibility_status="SUPERSEDED",
        linked_process_asset_refs=["pa://source-code-delivery/missing@1"],
    )

    result = materialize_document_views_from_process_assets(
        repository,
        artifact_store,
        process_asset_refs=[process_asset_ref],
        source_event_range={"start_sequence_no": 1, "end_sequence_no": 3},
    )

    reason_codes = [item["reason_code"] for item in result["diagnostics"]]
    assert result["status"] == "FAILED"
    assert reason_codes == ["evidence_lineage_break", "evidence_lineage_break"]
