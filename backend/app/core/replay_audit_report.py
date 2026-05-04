from __future__ import annotations

import hashlib
import json
from typing import Any

from app.contracts.replay import ReplayAuditReport, ReplayCaseResult, ReplayImportManifest

REPLAY_AUDIT_REPORT_VERSION = "replay-audit-report.v1"
ISSUE_TAXONOMY = [
    "provider failure",
    "runtime bug",
    "product defect",
    "contract gap",
    "replay/import issue",
]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _diagnostic(reason_code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "classification": "replay audit",
        "message": message,
        **details,
    }


def _diagnostic_codes(result: ReplayCaseResult) -> list[str]:
    return sorted({str(item.get("reason_code") or "") for item in result.diagnostics})


def _flatten_evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []

    def _walk(item: Any) -> None:
        if isinstance(item, str):
            normalized = item
            if item.startswith("tkt_"):
                normalized = f"ticket://{item}"
            if normalized.startswith(("art://", "pa://", "attempt:", "ticket://")) and normalized not in refs:
                refs.append(normalized)
            return
        if isinstance(item, list):
            for child in item:
                _walk(child)
            return
        if isinstance(item, dict):
            for child in item.values():
                _walk(child)

    _walk(value)
    return refs


def _case_issue_type(result: ReplayCaseResult) -> str:
    classification = str(result.issue_classification or "")
    case_id = result.case_id
    if classification == "replay/import issue":
        return "replay/import issue"
    if classification == "contract gap replay evidence":
        return "contract gap"
    if classification == "graph progression replay evidence":
        return "runtime bug"
    if classification == "closeout replay evidence":
        return "contract gap"
    if "product" in classification:
        return "product defect"
    if "provider" in classification:
        return "provider failure"
    return "runtime bug"


def _case_issue_domain(result: ReplayCaseResult) -> str:
    case_id = result.case_id
    if case_id.startswith("provider-failure"):
        return "provider failure"
    if case_id.startswith("contract-gap") or case_id.startswith("closeout"):
        return "contract gap"
    if case_id.startswith("graph-progression"):
        return "runtime bug"
    if "product" in str(result.issue_classification or ""):
        return "product defect"
    return _case_issue_type(result)


def _case_disposition(result: ReplayCaseResult) -> str:
    if result.audit_disposition.get("disposition"):
        return str(result.audit_disposition["disposition"])
    if result.status == "READY":
        return "replay_evidence_recorded"
    if result.issue_classification == "replay/import issue":
        return "legacy_replay_import_issue_recorded"
    return "failed_closed"


def _issue_from_case(result: ReplayCaseResult, manifest: ReplayImportManifest) -> dict[str, Any]:
    return {
        "case_id": result.case_id,
        "status": result.status,
        "issue_type": _case_issue_type(result),
        "issue_domain": _case_issue_domain(result),
        "issue_classification": result.issue_classification,
        "event_range": result.event_range,
        "evidence_refs": _flatten_evidence_refs(
            {
                "evidence_refs": result.evidence_refs,
                "attempt_refs": result.attempt_refs,
                "raw_archive_refs": result.raw_archive_refs,
                "source_ticket_context": result.source_ticket_context,
                "graph_pointer_summary": result.graph_pointer_summary,
                "policy_proposal": result.policy_proposal,
                "effective_edge_summary": result.effective_edge_summary,
                "closeout_tickets": result.closeout_tickets,
            }
        ),
        "checkpoint_hash": {
            "manifest_hash": manifest.manifest_hash,
            "event_log_hash": manifest.input_hashes.get("event_log_hash"),
            "artifact_index_hash": manifest.input_hashes.get("artifact_index_hash"),
            "db_sha256": manifest.input_hashes.get("db_sha256"),
        },
        "diagnostics": _diagnostic_codes(result),
        "disposition": _case_disposition(result),
    }


def _case_by_id(case_results: list[ReplayCaseResult]) -> dict[str, ReplayCaseResult]:
    return {result.case_id: result for result in case_results}


def _acceptance_status(
    *,
    status: str,
    evidence: str,
    command_or_report: str,
    diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "evidence": evidence,
        "command_or_report": command_or_report,
        "diagnostics": diagnostics or [],
    }


def _phase7_acceptance(
    *,
    manifest: ReplayImportManifest,
    case_results: list[ReplayCaseResult],
) -> dict[str, dict[str, Any]]:
    cases = _case_by_id(case_results)
    provider = cases.get("provider-failure-015-malformed-sse")
    closeout = cases.get("closeout-015-manual-m103-contract-gate")
    return {
        "015 import": _acceptance_status(
            status=manifest.status,
            evidence=manifest.manifest_hash,
            command_or_report="replay-import-015/replay-import-manifest.json",
            diagnostics=[str(item.get("reason_code") or "") for item in manifest.import_diagnostics],
        ),
        "provider failure": _acceptance_status(
            status=provider.status if provider is not None else "FAILED",
            evidence=provider.case_id if provider is not None else "missing",
            command_or_report="replay-provider-015/replay-case-result.json",
            diagnostics=_diagnostic_codes(provider) if provider is not None else ["case_result_missing"],
        ),
        "BR-032": _acceptance_status(
            status=cases.get("contract-gap-015-br032-auth-mismatch").status
            if cases.get("contract-gap-015-br032-auth-mismatch") is not None
            else "FAILED",
            evidence="contract-gap-015-br032-auth-mismatch",
            command_or_report="replay-contract-gap-015/br032.json",
        ),
        "BR-040/BR-041": _acceptance_status(
            status=(
                "READY"
                if all(
                    (cases.get(case_id) is not None and cases[case_id].status == "READY")
                    for case_id in (
                        "contract-gap-015-br040-placeholder-delivery",
                        "contract-gap-015-br041-placeholder-delivery",
                    )
                )
                else "FAILED"
            ),
            evidence="contract-gap-015-br040-placeholder-delivery; contract-gap-015-br041-placeholder-delivery",
            command_or_report="replay-contract-gap-015/br040.json; replay-contract-gap-015/br041.json",
        ),
        "orphan pending": _acceptance_status(
            status=cases.get("graph-progression-015-orphan-pending-br060").status
            if cases.get("graph-progression-015-orphan-pending-br060") is not None
            else "FAILED",
            evidence="graph-progression-015-orphan-pending-br060",
            command_or_report="replay-graph-progression-015/orphan-pending.json",
        ),
        "contract closeout": _acceptance_status(
            status=closeout.status if closeout is not None else "FAILED",
            evidence=closeout.case_id if closeout is not None else "missing",
            command_or_report="replay-closeout-015/closeout.json",
            diagnostics=_diagnostic_codes(closeout) if closeout is not None else ["case_result_missing"],
        ),
        "audit report": _acceptance_status(
            status="READY",
            evidence="replay-audit-report.v1",
            command_or_report="replay-audit-015/replay-audit-report.json",
        ),
    }


def _report_hash_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    payload.pop("report_hash", None)
    return payload


def build_replay_audit_report(
    *,
    manifest: ReplayImportManifest,
    case_results: list[ReplayCaseResult],
) -> ReplayAuditReport:
    issues = [_issue_from_case(result, manifest) for result in case_results]
    diagnostics = [
        _diagnostic(
            "provider_replay_import_issue_retained",
            "Provider case remains failed because legacy 015 replay lacks raw archive refs.",
            case_id="provider-failure-015-malformed-sse",
        )
        for result in case_results
        if result.case_id == "provider-failure-015-malformed-sse" and result.status == "FAILED"
    ]
    closeout_import_issues = [
        result
        for result in case_results
        if result.case_id == "closeout-015-manual-m103-contract-gate" and result.status == "FAILED"
    ]
    if closeout_import_issues:
        diagnostics.append(
            _diagnostic(
                "closeout_legacy_manual_recovery_rejected",
                "Legacy manual closeout recovery is retained as replay/import issue, not contract evidence.",
                case_id="closeout-015-manual-m103-contract-gate",
            )
        )
    report_payload: dict[str, Any] = {
        "status": "READY",
        "report_version": REPLAY_AUDIT_REPORT_VERSION,
        "source_manifest_hash": manifest.manifest_hash,
        "source_event_range": manifest.event_range,
        "checkpoint_hashes": {
            "manifest_hash": manifest.manifest_hash,
            "idempotency_key": manifest.idempotency_key,
            "db_sha256": manifest.input_hashes.get("db_sha256"),
            "event_log_hash": manifest.input_hashes.get("event_log_hash"),
            "artifact_index_hash": manifest.input_hashes.get("artifact_index_hash"),
            "registered_artifact_tree_sha256": manifest.input_hashes.get("registered_artifact_tree_sha256"),
        },
        "issue_taxonomy": ISSUE_TAXONOMY,
        "issues": issues,
        "case_results": [result.model_dump(mode="json") for result in case_results],
        "phase7_acceptance": _phase7_acceptance(manifest=manifest, case_results=case_results),
        "diagnostics": diagnostics,
        "report_hash": "",
    }
    report_payload["report_hash"] = _sha256(_report_hash_payload(report_payload))
    return ReplayAuditReport.model_validate(report_payload)
