from __future__ import annotations

import json
from pathlib import Path

from app.contracts.replay import ReplayCaseResult, ReplayImportManifest
from app.core.replay_audit_report import build_replay_audit_report
from app.replay_audit_report_cli import main as replay_audit_report_cli_main


def _manifest() -> ReplayImportManifest:
    return ReplayImportManifest(
        status="READY",
        manifest_version="replay-import-manifest.v1",
        input_db_path="D:/Projects/boardroom-os-replay/boardroom_os.db",
        artifact_root="D:/Projects/boardroom-os-replay/artifacts",
        log_refs=["run_report.json"],
        input_hashes={
            "db_sha256": "db-hash",
            "event_log_hash": "event-log-hash",
            "artifact_index_hash": "artifact-index-hash",
        },
        schema={"app_schema_version": "fixture"},
        event_range={"start_sequence_no": 1, "end_sequence_no": 15801},
        event_count=15801,
        workflow_ids=["wf_7f2902f3c8c6"],
        artifact_count=362,
        local_file_artifact_count=361,
        inline_db_artifact_count=1,
        import_diagnostics=[
            {
                "reason_code": "inline_db_artifact_recorded",
                "classification": "replay/import issue",
                "message": "INLINE_DB closeout artifact.",
            }
        ],
        idempotency_key="replay-import:fixture",
        manifest_hash="manifest-hash",
    )


def _case(
    case_id: str,
    *,
    status: str,
    classification: str,
    event_range: dict[str, int],
    diagnostics: list[dict] | None = None,
    evidence_refs: dict | None = None,
) -> ReplayCaseResult:
    return ReplayCaseResult(
        case_id=case_id,
        status=status,
        source_manifest_hash="manifest-hash",
        event_range=event_range,
        provider_failure_kind=None,
        attempt_refs=[],
        raw_archive_refs=[],
        source_ticket_context={"workflow_id": "wf_7f2902f3c8c6"},
        provider_provenance={},
        retry_recovery_outcome={
            "recovery_outcome": "not_provider_failure",
            "raw_transcript_used": False,
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        late_event_guard={"guard_passed": True},
        diagnostics=diagnostics or [],
        issue_classification=classification,
        evidence_refs=evidence_refs or {},
    )


def test_replay_audit_report_groups_cases_by_required_issue_taxonomy() -> None:
    manifest = _manifest()
    provider = _case(
        "provider-failure-015-malformed-sse",
        status="FAILED",
        classification="replay/import issue",
        event_range={"start_sequence_no": 9969, "end_sequence_no": 10016},
        diagnostics=[{"reason_code": "provider_raw_archive_ref_missing"}],
    )
    br032 = _case(
        "contract-gap-015-br032-auth-mismatch",
        status="READY",
        classification="contract gap replay evidence",
        event_range={"start_sequence_no": 5855, "end_sequence_no": 6299},
        evidence_refs={"checker_report_refs": ["art://runtime/tkt_bc0404503ec8/delivery-check-report.json"]},
    )
    graph = _case(
        "graph-progression-015-orphan-pending-br060",
        status="READY",
        classification="graph progression replay evidence",
        event_range={"start_sequence_no": 11791, "end_sequence_no": 11903},
        evidence_refs={"affected_ticket_ids": ["tkt_262f159fc931"]},
    )
    closeout = _case(
        "closeout-015-manual-m103-contract-gate",
        status="FAILED",
        classification="replay/import issue",
        event_range={"start_sequence_no": 15778, "end_sequence_no": 15801},
        diagnostics=[{"reason_code": "closeout_missing_final_evidence_table"}],
    )

    report = build_replay_audit_report(
        manifest=manifest,
        case_results=[provider, br032, graph, closeout],
    )

    assert report.status == "READY"
    assert report.source_manifest_hash == "manifest-hash"
    assert report.issue_taxonomy == [
        "provider failure",
        "runtime bug",
        "product defect",
        "contract gap",
        "replay/import issue",
    ]
    issues_by_case_id = {issue["case_id"]: issue for issue in report.issues}
    assert issues_by_case_id["provider-failure-015-malformed-sse"]["issue_type"] == "replay/import issue"
    assert issues_by_case_id["provider-failure-015-malformed-sse"]["issue_domain"] == "provider failure"
    assert issues_by_case_id["contract-gap-015-br032-auth-mismatch"]["issue_type"] == "contract gap"
    assert issues_by_case_id["graph-progression-015-orphan-pending-br060"]["issue_type"] == "runtime bug"
    assert "ticket://tkt_262f159fc931" in issues_by_case_id[
        "graph-progression-015-orphan-pending-br060"
    ]["evidence_refs"]
    assert issues_by_case_id["closeout-015-manual-m103-contract-gate"]["issue_type"] == "replay/import issue"
    assert report.phase7_acceptance["015 import"]["status"] == "READY"
    assert report.phase7_acceptance["provider failure"]["status"] == "FAILED"
    assert report.phase7_acceptance["contract closeout"]["status"] == "FAILED"
    assert report.phase7_acceptance["audit report"]["status"] == "READY"
    assert report.report_hash


def test_replay_audit_report_cli_writes_json(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest_path = tmp_path / "manifest.json"
    provider_path = tmp_path / "provider.json"
    br032_path = tmp_path / "br032.json"
    closeout_path = tmp_path / "closeout.json"
    report_path = tmp_path / "replay-audit-report.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    provider_path.write_text(
        _case(
            "provider-failure-015-malformed-sse",
            status="FAILED",
            classification="replay/import issue",
            event_range={"start_sequence_no": 9969, "end_sequence_no": 10016},
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    br032_path.write_text(
        _case(
            "contract-gap-015-br032-auth-mismatch",
            status="READY",
            classification="contract gap replay evidence",
            event_range={"start_sequence_no": 5855, "end_sequence_no": 6299},
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    closeout_path.write_text(
        _case(
            "closeout-015-manual-m103-contract-gate",
            status="FAILED",
            classification="replay/import issue",
            event_range={"start_sequence_no": 15778, "end_sequence_no": 15801},
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    exit_code = replay_audit_report_cli_main(
        [
            "--manifest",
            str(manifest_path),
            "--case-result",
            str(provider_path),
            "--case-result",
            str(br032_path),
            "--case-result",
            str(closeout_path),
            "--report-out",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "READY"
    assert payload["phase7_acceptance"]["audit report"]["status"] == "READY"
