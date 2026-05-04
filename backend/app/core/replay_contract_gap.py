from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayCaseResult, ReplayImportManifest
from app.core.deliverable_contract import (
    ContractFinding,
    DeliverableEvaluationPolicy,
    EvidenceItem,
    EvidencePack,
    checker_contract_gate,
    compile_contract_rework_recovery_actions,
    compile_deliverable_contract,
    evaluate_deliverable_contract,
)
from app.core.workflow_progression import (
    ProgressionActionType,
    ProgressionPolicy,
    ProgressionSnapshot,
    decide_next_actions,
)


BR032_AUTH_MISMATCH_CASE_ID = "contract-gap-015-br032-auth-mismatch"
BR040_PLACEHOLDER_DELIVERY_CASE_ID = "contract-gap-015-br040-placeholder-delivery"
BR041_PLACEHOLDER_DELIVERY_CASE_ID = "contract-gap-015-br041-placeholder-delivery"
CONTRACT_GAP_REPLAY_EVIDENCE_CLASSIFICATION = "contract gap replay evidence"
REPLAY_IMPORT_ISSUE_CLASSIFICATION = "replay/import issue"


_CASE_CONFIGS: dict[str, dict[str, Any]] = {
    BR032_AUTH_MISMATCH_CASE_ID: {
        "br_id": "BR-032",
        "workflow_id": "wf_7f2902f3c8c6",
        "event_range": {"start_sequence_no": 5855, "end_sequence_no": 6299},
        "checker_ticket_id": "tkt_bc0404503ec8",
        "checker_node_id": "node_backlog_followup_br_032_m3_checker_gate",
        "approved_checker_ticket_id": "tkt_1b2b27220047",
        "producer_ticket_id": "tkt_c247833b2c60",
        "producer_node_id": "node_backlog_followup_br_031_m3_frontend_auth_nav",
        "source_surface_ref": "surface.br032.frontend_auth_contract",
        "acceptance_ref": "AC-BR032-auth-contract",
        "finding_ref": "BR032-F06",
        "reason_code": "auth_contract_mismatch",
        "required_capability": "source.modify.frontend",
        "checker_report_ref": "art://runtime/tkt_bc0404503ec8/delivery-check-report.json",
    },
    BR040_PLACEHOLDER_DELIVERY_CASE_ID: {
        "br_id": "BR-040",
        "workflow_id": "wf_7f2902f3c8c6",
        "event_range": {"start_sequence_no": 11400, "end_sequence_no": 11464},
        "producer_ticket_id": "tkt_2252a7a1f92e",
        "producer_node_id": "node_backlog_followup_br_040_m4_catalog_search_availability",
        "source_surface_ref": "surface.br040.catalog_search_availability",
        "acceptance_ref": "AC-BR040-placeholder-delivery",
        "required_capability": "source.modify.backend",
        "source_ref": "art://workspace/tkt_2252a7a1f92e/source.py",
        "test_ref": "art://workspace/tkt_2252a7a1f92e/test-report.json",
        "source_process_asset_ref": "pa://source-code-delivery/tkt_2252a7a1f92e@1",
        "evidence_pack_ref": "pa://evidence-pack/tkt_2252a7a1f92e@1",
    },
    BR041_PLACEHOLDER_DELIVERY_CASE_ID: {
        "br_id": "BR-041",
        "workflow_id": "wf_7f2902f3c8c6",
        "event_range": {"start_sequence_no": 9933, "end_sequence_no": 10016},
        "producer_ticket_id": "tkt_5707c310bc6d",
        "producer_node_id": "node_backlog_followup_br_041_m4_isbn_remove_inventory",
        "source_surface_ref": "surface.br041.isbn_remove_inventory",
        "acceptance_ref": "AC-BR041-placeholder-delivery",
        "required_capability": "source.modify.backend",
        "source_ref": "art://workspace/tkt_5707c310bc6d/source.py",
        "test_ref": "art://workspace/tkt_5707c310bc6d/test-report.json",
        "source_process_asset_ref": "pa://source-code-delivery/tkt_5707c310bc6d@1",
        "evidence_pack_ref": "pa://evidence-pack/tkt_5707c310bc6d@1",
    },
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _diagnostic(reason_code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "classification": details.pop("classification", CONTRACT_GAP_REPLAY_EVIDENCE_CLASSIFICATION),
        "message": message,
        **_json_safe(details),
    }


def _empty_result(
    *,
    case_id: str,
    manifest: ReplayImportManifest | None,
    diagnostics: list[dict[str, Any]],
    event_range: dict[str, int] | None = None,
) -> ReplayCaseResult:
    return ReplayCaseResult(
        case_id=case_id,
        status="FAILED",
        source_manifest_hash=manifest.manifest_hash if manifest is not None else "",
        event_range=event_range,
        provider_failure_kind=None,
        attempt_refs=[],
        raw_archive_refs=[],
        source_ticket_context={},
        provider_provenance={},
        retry_recovery_outcome={
            "recovery_outcome": "not_evaluated",
            "raw_transcript_used": False,
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        late_event_guard={
            "guard_passed": True,
            "current_pointer_source": "not_provider_replay",
        },
        diagnostics=diagnostics,
        issue_classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
    )


def failed_contract_gap_case_result(
    *,
    case_id: str,
    diagnostics: list[dict[str, Any]],
    manifest: ReplayImportManifest | None = None,
) -> ReplayCaseResult:
    config = _CASE_CONFIGS.get(case_id)
    event_range = dict(config["event_range"]) if config is not None else None
    return _empty_result(
        case_id=case_id,
        manifest=manifest,
        diagnostics=diagnostics,
        event_range=event_range,
    )


def _connect_replay_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _payload(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    raw = row["payload_json"] if isinstance(row, sqlite3.Row) else row.get("payload_json")
    if not raw:
        return {}
    return json.loads(str(raw))


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sequence_no": int(row["sequence_no"]),
        "event_id": str(row["event_id"]),
        "workflow_id": row["workflow_id"],
        "event_type": str(row["event_type"]),
        "occurred_at": str(row["occurred_at"]),
        "payload": _payload(row),
    }


def _fetch_events(
    connection: sqlite3.Connection,
    *,
    start_sequence_no: int,
    end_sequence_no: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT sequence_no, event_id, workflow_id, event_type, occurred_at, payload_json
        FROM events
        WHERE sequence_no BETWEEN ? AND ?
        ORDER BY sequence_no ASC
        """,
        (start_sequence_no, end_sequence_no),
    ).fetchall()
    return [_event_from_row(row) for row in rows]


def _event_range(events: list[dict[str, Any]]) -> dict[str, int] | None:
    if not events:
        return None
    sequence_numbers = [int(event["sequence_no"]) for event in events]
    return {"start_sequence_no": min(sequence_numbers), "end_sequence_no": max(sequence_numbers)}


def _events_for_ticket(events: list[dict[str, Any]], ticket_id: str) -> list[dict[str, Any]]:
    return [event for event in events if str((event["payload"] or {}).get("ticket_id") or "") == ticket_id]


def _last_event(
    events: list[dict[str, Any]],
    *,
    event_type: str,
    ticket_id: str | None = None,
) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event["event_type"] == event_type
        and (ticket_id is None or str((event["payload"] or {}).get("ticket_id") or "") == ticket_id)
    ]
    return matches[-1] if matches else None


def _artifact_exists(connection: sqlite3.Connection, artifact_ref: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM artifact_index WHERE artifact_ref = ? LIMIT 1",
        (artifact_ref,),
    ).fetchone()
    return row is not None


def _process_asset_exists(connection: sqlite3.Connection, process_asset_ref: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM process_asset_index WHERE process_asset_ref = ? LIMIT 1",
        (process_asset_ref,),
    ).fetchone()
    return row is not None


def _artifact_refs_for_ticket(connection: sqlite3.Connection, ticket_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT artifact_ref
        FROM artifact_index
        WHERE ticket_id = ?
        ORDER BY artifact_ref ASC
        """,
        (ticket_id,),
    ).fetchall()
    return [str(row["artifact_ref"]) for row in rows]


def _process_asset_refs_for_ticket(
    connection: sqlite3.Connection,
    ticket_id: str,
    *,
    kind: str | None = None,
) -> list[str]:
    if kind:
        rows = connection.execute(
            """
            SELECT process_asset_ref
            FROM process_asset_index
            WHERE producer_ticket_id = ?
              AND process_asset_kind = ?
            ORDER BY process_asset_ref ASC
            """,
            (ticket_id, kind),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT process_asset_ref
            FROM process_asset_index
            WHERE producer_ticket_id = ?
            ORDER BY process_asset_ref ASC
            """,
            (ticket_id,),
        ).fetchall()
    return [str(row["process_asset_ref"]) for row in rows]


def _process_asset_summary(connection: sqlite3.Connection, process_asset_ref: str) -> str:
    row = connection.execute(
        """
        SELECT summary
        FROM process_asset_index
        WHERE process_asset_ref = ?
        LIMIT 1
        """,
        (process_asset_ref,),
    ).fetchone()
    return str(row["summary"] or "") if row is not None else ""


def _evidence_pack_metadata(connection: sqlite3.Connection, process_asset_ref: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT source_metadata_json
        FROM process_asset_index
        WHERE process_asset_ref = ?
        LIMIT 1
        """,
        (process_asset_ref,),
    ).fetchone()
    if row is None or not row["source_metadata_json"]:
        return {}
    return json.loads(str(row["source_metadata_json"]))


def _completed_event_artifact_refs(events: list[dict[str, Any]], ticket_id: str) -> list[str]:
    completed = _last_event(events, event_type="TICKET_COMPLETED", ticket_id=ticket_id)
    refs = (completed or {}).get("payload", {}).get("artifact_refs")
    return [str(ref) for ref in refs] if isinstance(refs, list) else []


def _approved_review_status(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        review_status = str((event["payload"] or {}).get("review_status") or "").strip()
        if review_status:
            return review_status
    return "APPROVED_WITH_NOTES"


def _base_result_payload(config: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_id": config["case_id"],
        "br_id": config["br_id"],
        "event_range": _event_range(events),
        "source_ticket_context": {
            "workflow_id": config["workflow_id"],
            "br_id": config["br_id"],
        },
        "provider_failure_kind": None,
        "attempt_refs": [],
        "raw_archive_refs": [],
        "provider_provenance": {},
        "retry_recovery_outcome": {
            "recovery_outcome": "not_provider_failure",
            "raw_transcript_used": False,
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        "late_event_guard": {
            "guard_passed": True,
            "current_pointer_source": "structured_contract_replay",
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        "graph_terminal_override_used": False,
    }


def _contract_policy(case_id: str) -> DeliverableEvaluationPolicy:
    return DeliverableEvaluationPolicy(policy_ref=f"replay-contract-gap:{case_id}:policy")


def _finding_dict(finding: ContractFinding, *, finding_ref: str | None = None) -> dict[str, Any]:
    payload = finding.model_dump(mode="json")
    if finding_ref:
        payload["finding_ref"] = finding_ref
    return payload


def _proposal_from_actions(actions: list[dict[str, Any]], graph_version: str) -> dict[str, Any] | None:
    if not actions:
        return None
    snapshot = ProgressionSnapshot(
        workflow_id="wf_7f2902f3c8c6",
        graph_version=graph_version,
    )
    policy = ProgressionPolicy(
        policy_ref=f"replay-contract-gap-policy:{graph_version}",
        recovery={"actions": actions},
    )
    proposals = decide_next_actions(snapshot, policy)
    for proposal in proposals:
        if proposal.action_type in {ProgressionActionType.REWORK, ProgressionActionType.INCIDENT}:
            return proposal.model_dump(mode="json")
    return None


def _contract_gate_payload(gate: Any, *, failed_delivery_report: bool) -> dict[str, Any]:
    payload = gate.model_dump(mode="json")
    payload["failed_delivery_report"] = failed_delivery_report
    return payload


def _br032_result(
    *,
    manifest: ReplayImportManifest,
    connection: sqlite3.Connection,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayCaseResult:
    checker_report_ref = str(config["checker_report_ref"])
    report_asset_ref = (
        "pa://artifact/art%3A%2F%2Fruntime%2Ftkt_bc0404503ec8%2Fdelivery-check-report.json@1"
    )
    report_summary = _process_asset_summary(connection, report_asset_ref)
    if not _artifact_exists(connection, checker_report_ref):
        diagnostics.append(
            _diagnostic(
                "checker_report_ref_missing",
                "BR-032 replay cannot find the checker report artifact ref.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                artifact_ref=checker_report_ref,
            )
        )
    if "BR032-F06" not in report_summary:
        diagnostics.append(
            _diagnostic(
                "br032_f06_summary_missing",
                "BR-032 replay cannot find the structured BR032-F06 checker summary.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                process_asset_ref=report_asset_ref,
            )
        )

    contract = compile_deliverable_contract(
        workflow_id=str(config["workflow_id"]),
        graph_version="gv_11c_br032",
        acceptance_criteria=[
            {
                "criterion_id": config["acceptance_ref"],
                "description": "Frontend auth client must consume backend auth envelope, roles, frozen status, and reason code contract.",
            }
        ],
        required_source_surfaces=[
            {
                "surface_id": config["source_surface_ref"],
                "owning_capabilities": [config["required_capability"]],
                "acceptance_criteria_refs": [config["acceptance_ref"]],
                "required_evidence_kinds": ["source_inventory", "api_contract_test"],
            }
        ],
    )
    evidence_pack = EvidencePack(
        workflow_id=str(config["workflow_id"]),
        graph_version="gv_11c_br032",
        evidence=[
            EvidenceItem(
                evidence_ref=checker_report_ref,
                evidence_kind="maker_checker_verdict",
                acceptance_criteria_refs=[config["acceptance_ref"]],
                source_surface_refs=[config["source_surface_ref"]],
                producer_ticket_id=str(config["checker_ticket_id"]),
                producer_node_ref=str(config["checker_node_id"]),
                legality_status="ACCEPTED",
                current_pointer_status="CURRENT",
                metadata={"finding_ref": config["finding_ref"], "report_status": "FAIL"},
            ),
            EvidenceItem(
                evidence_ref="art://workspace/tkt_c247833b2c60/source/2-10-project%2Fsrc%2Ffrontend%2Fsrc%2Fapi%2Fauth.ts",
                evidence_kind="source_inventory",
                acceptance_criteria_refs=[config["acceptance_ref"]],
                source_surface_refs=[config["source_surface_ref"]],
                producer_ticket_id=str(config["producer_ticket_id"]),
                producer_node_ref=str(config["producer_node_id"]),
                legality_status="ACCEPTED",
                current_pointer_status="CURRENT",
            ),
        ],
        final_evidence_refs=[checker_report_ref],
    )
    evaluation = evaluate_deliverable_contract(contract, evidence_pack, _contract_policy(str(config["case_id"])))
    review_status = _approved_review_status(events)
    gate = checker_contract_gate(
        evaluation=evaluation,
        review_status=review_status,
        failed_delivery_report=True,
        scope_refs=[str(config["acceptance_ref"])],
    )
    actions = compile_contract_rework_recovery_actions(
        contract=contract,
        evaluation=evaluation,
        evidence_pack=evidence_pack,
        checker_ticket_id=str(config["checker_ticket_id"]),
        checker_node_ref=str(config["checker_node_id"]),
        current_graph_pointers=[
            {
                "source_surface_ref": config["source_surface_ref"],
                "producer_ticket_id": config["producer_ticket_id"],
                "producer_node_ref": config["producer_node_id"],
                "current_graph_pointer": {
                    "graph_node_id": config["producer_node_id"],
                    "latest_ticket_id": config["producer_ticket_id"],
                },
            }
        ],
    )
    proposal = _proposal_from_actions(actions, "gv_11c_br032")
    rework_target = dict(actions[0]["contract_rework_target"]) if actions else {}
    if gate.allowed is False:
        diagnostics.append(
            _diagnostic(
                "approved_with_notes_not_contract_satisfaction",
                "APPROVED_WITH_NOTES did not override the blocking BR-032 contract gap.",
                review_status=review_status,
                gate_reason_code=gate.reason_code,
            )
        )
    if actions:
        diagnostics.append(
            _diagnostic(
                "upstream_rework_target_selected",
                "BR-032 contract gap routes to the upstream frontend source surface.",
                target_ticket_id=actions[0].get("target_ticket_id"),
                target_node_ref=actions[0].get("node_ref"),
            )
        )
    payload = _base_result_payload({**config, "case_id": BR032_AUTH_MISMATCH_CASE_ID}, events)
    return ReplayCaseResult(
        **payload,
        status="READY" if not [d for d in diagnostics if d.get("classification") == REPLAY_IMPORT_ISSUE_CLASSIFICATION] else "FAILED",
        source_manifest_hash=manifest.manifest_hash,
        contract_findings=[
            _finding_dict(finding, finding_ref=str(config["finding_ref"]))
            for finding in evaluation.findings
            if finding.blocking
        ],
        rework_incident_outcome={
            "outcome": "rework_requested" if proposal and proposal["action_type"] == "REWORK" else "not_reworked",
            "reason_code": ((proposal or {}).get("metadata") or {}).get("reason_code"),
            "proposal": proposal,
        },
        evidence_refs={
            "checker_report_refs": [checker_report_ref],
            "backend_source_refs": [
                ref
                for ref in _artifact_refs_for_ticket(connection, "tkt_43324c290a3e")
                if "/source/" in ref or "/tests/" in ref
            ],
            "old_frontend_source_refs": [
                ref
                for ref in _artifact_refs_for_ticket(connection, "tkt_d9e52680a9c5")
                if "/source/" in ref
            ],
            "fixed_frontend_source_refs": [
                ref
                for ref in _artifact_refs_for_ticket(connection, str(config["producer_ticket_id"]))
                if "/source/" in ref or "/tests/" in ref
            ],
        },
        contract_gate=_contract_gate_payload(gate, failed_delivery_report=True),
        rework_target=rework_target,
        diagnostics=diagnostics,
        issue_classification=(
            REPLAY_IMPORT_ISSUE_CLASSIFICATION
            if [d for d in diagnostics if d.get("classification") == REPLAY_IMPORT_ISSUE_CLASSIFICATION]
            else CONTRACT_GAP_REPLAY_EVIDENCE_CLASSIFICATION
        ),
    )


def _placeholder_evidence_pack_metadata(
    *,
    connection: sqlite3.Connection,
    config: dict[str, Any],
) -> dict[str, Any]:
    evidence_pack_ref = str(config["evidence_pack_ref"])
    metadata = _evidence_pack_metadata(connection, evidence_pack_ref)
    verification_runs = [
        run for run in list(metadata.get("verification_runs") or []) if isinstance(run, dict)
    ]
    generic_runs = [
        run
        for run in verification_runs
        if str(run.get("command") or "") == "pytest tests -q"
        and int(run.get("passed_count") or 0) == 1
        and int(run.get("discovered_count") or 0) == 1
    ]
    return {
        "metadata": metadata,
        "verification_runs": verification_runs,
        "generic_runs": generic_runs,
    }


def _placeholder_result(
    *,
    manifest: ReplayImportManifest,
    connection: sqlite3.Connection,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayCaseResult:
    source_ref = str(config["source_ref"])
    test_ref = str(config["test_ref"])
    source_pa = str(config["source_process_asset_ref"])
    evidence_pack_ref = str(config["evidence_pack_ref"])
    for ref in (source_ref, test_ref):
        if not _artifact_exists(connection, ref):
            diagnostics.append(
                _diagnostic(
                    "placeholder_artifact_ref_missing",
                    "Placeholder replay cannot find an expected artifact ref.",
                    classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                    artifact_ref=ref,
                )
            )
    for ref in (source_pa, evidence_pack_ref):
        if not _process_asset_exists(connection, ref):
            diagnostics.append(
                _diagnostic(
                    "placeholder_process_asset_ref_missing",
                    "Placeholder replay cannot find an expected process asset ref.",
                    classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                    process_asset_ref=ref,
                )
            )
    metadata = _placeholder_evidence_pack_metadata(connection=connection, config=config)
    if metadata["generic_runs"]:
        diagnostics.append(
            _diagnostic(
                "placeholder_delivery_blocked",
                "Placeholder source.py and generic pytest evidence are blocked by deliverable contract.",
                source_ref=source_ref,
                test_ref=test_ref,
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "generic_test_evidence_missing",
                "Placeholder replay cannot find the generic pytest tests -q evidence.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                evidence_pack_ref=evidence_pack_ref,
            )
        )

    contract = compile_deliverable_contract(
        workflow_id=str(config["workflow_id"]),
        graph_version=f"gv_11c_{str(config['br_id']).lower().replace('-', '')}",
        acceptance_criteria=[
            {
                "criterion_id": config["acceptance_ref"],
                "description": "Placeholder source.py and generic one-test output cannot satisfy source delivery.",
            }
        ],
        required_source_surfaces=[
            {
                "surface_id": config["source_surface_ref"],
                "owning_capabilities": [config["required_capability"]],
                "acceptance_criteria_refs": [config["acceptance_ref"]],
                "required_evidence_kinds": ["source_inventory", "unit_test"],
            }
        ],
    )
    evidence_pack = EvidencePack(
        workflow_id=str(config["workflow_id"]),
        graph_version=f"gv_11c_{str(config['br_id']).lower().replace('-', '')}",
        evidence=[
            EvidenceItem(
                evidence_ref=source_ref,
                evidence_kind="source_inventory",
                acceptance_criteria_refs=[config["acceptance_ref"]],
                source_surface_refs=[config["source_surface_ref"]],
                producer_ticket_id=str(config["producer_ticket_id"]),
                producer_node_ref=str(config["producer_node_id"]),
                artifact_kind="WORKSPACE_SOURCE",
                legality_status="PLACEHOLDER",
                current_pointer_status="CURRENT",
                placeholder=True,
                metadata={"placeholder_reasons": ["source.py placeholder"]},
            ),
            EvidenceItem(
                evidence_ref=test_ref,
                evidence_kind="unit_test",
                acceptance_criteria_refs=[config["acceptance_ref"]],
                source_surface_refs=[config["source_surface_ref"]],
                producer_ticket_id=str(config["producer_ticket_id"]),
                producer_node_ref=str(config["producer_node_id"]),
                artifact_kind="TEST_EVIDENCE",
                legality_status="ACCEPTED",
                current_pointer_status="CURRENT",
                metadata={
                    "stdout_fallback": True,
                    "no_business_assertions": True,
                    "placeholder_reasons": ["generic 1 passed"],
                },
            ),
        ],
        final_evidence_refs=[source_ref, test_ref],
    )
    evaluation = evaluate_deliverable_contract(contract, evidence_pack, _contract_policy(str(config["br_id"])))
    review_status = _approved_review_status(events)
    gate = checker_contract_gate(
        evaluation=evaluation,
        review_status=review_status,
        failed_delivery_report=True,
        scope_refs=[str(config["acceptance_ref"])],
    )
    actions = compile_contract_rework_recovery_actions(
        contract=contract,
        evaluation=evaluation,
        evidence_pack=evidence_pack,
        checker_ticket_id=f"checker:{config['producer_ticket_id']}",
        checker_node_ref=str(config["producer_node_id"]),
        current_graph_pointers=[
            {
                "source_surface_ref": config["source_surface_ref"],
                "producer_ticket_id": config["producer_ticket_id"],
                "producer_node_ref": config["producer_node_id"],
                "current_graph_pointer": {
                    "graph_node_id": config["producer_node_id"],
                    "latest_ticket_id": config["producer_ticket_id"],
                },
            }
        ],
    )
    proposal = _proposal_from_actions(actions, f"gv_11c_{str(config['br_id']).lower().replace('-', '')}")
    rework_target = dict(actions[0]["contract_rework_target"]) if actions else {}
    if gate.allowed is False:
        diagnostics.append(
            _diagnostic(
                "approved_with_notes_not_contract_satisfaction",
                "APPROVED_WITH_NOTES did not override the blocking placeholder contract gap.",
                review_status=review_status,
                gate_reason_code=gate.reason_code,
            )
        )
    completed_artifact_refs = _completed_event_artifact_refs(events, str(config["producer_ticket_id"]))
    payload = _base_result_payload({**config, "case_id": _case_id_for_br(str(config["br_id"]))}, events)
    import_failures = [d for d in diagnostics if d.get("classification") == REPLAY_IMPORT_ISSUE_CLASSIFICATION]
    return ReplayCaseResult(
        **payload,
        status="READY" if not import_failures else "FAILED",
        source_manifest_hash=manifest.manifest_hash,
        contract_findings=[_finding_dict(finding) for finding in evaluation.findings if finding.blocking],
        rework_incident_outcome={
            "outcome": "rework_requested" if proposal and proposal["action_type"] == "REWORK" else "not_reworked",
            "reason_code": ((proposal or {}).get("metadata") or {}).get("reason_code"),
            "proposal": proposal,
        },
        evidence_refs={
            "ticket_artifact_refs": completed_artifact_refs,
            "placeholder_source_refs": [source_ref],
            "placeholder_test_refs": [test_ref],
            "source_process_asset_refs": [source_pa],
            "evidence_pack_refs": [evidence_pack_ref],
            "generic_test_commands": [run.get("command") for run in metadata["generic_runs"]],
        },
        contract_gate=_contract_gate_payload(gate, failed_delivery_report=True),
        rework_target=rework_target,
        diagnostics=diagnostics,
        issue_classification=(
            REPLAY_IMPORT_ISSUE_CLASSIFICATION if import_failures else CONTRACT_GAP_REPLAY_EVIDENCE_CLASSIFICATION
        ),
    )


def _case_id_for_br(br_id: str) -> str:
    if br_id == "BR-040":
        return BR040_PLACEHOLDER_DELIVERY_CASE_ID
    if br_id == "BR-041":
        return BR041_PLACEHOLDER_DELIVERY_CASE_ID
    return BR032_AUTH_MISMATCH_CASE_ID


def replay_contract_gap_case(
    *,
    manifest: ReplayImportManifest,
    replay_db_path: str | Path,
    case_id: str,
) -> ReplayCaseResult:
    config = _CASE_CONFIGS.get(case_id)
    if config is None:
        return _empty_result(
            case_id=case_id,
            manifest=manifest,
            diagnostics=[
                _diagnostic(
                    "replay_case_unknown",
                    "Replay contract gap case id is not registered.",
                    classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                    case_id=case_id,
                )
            ],
        )
    diagnostics: list[dict[str, Any]] = []
    if manifest.status != "READY":
        diagnostics.append(
            _diagnostic(
                "manifest_not_ready",
                "Replay contract gap requires a READY ReplayImportManifest.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                manifest_status=manifest.status,
            )
        )

    db_path = Path(replay_db_path)
    if not db_path.is_file():
        diagnostics.append(
            _diagnostic(
                "replay_db_missing",
                "Replay contract gap requires an imported replay DB.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                replay_db_path=str(db_path),
            )
        )
        return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

    try:
        connection = _connect_replay_db(db_path)
    except sqlite3.Error as exc:
        diagnostics.append(
            _diagnostic(
                "replay_db_invalid",
                "Replay contract gap DB cannot be opened read-only.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        )
        return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

    with connection:
        events = _fetch_events(
            connection,
            start_sequence_no=int(config["event_range"]["start_sequence_no"]),
            end_sequence_no=int(config["event_range"]["end_sequence_no"]),
        )
        if not events:
            diagnostics.append(
                _diagnostic(
                    "replay_case_events_missing",
                    "Replay contract gap case range has no events.",
                    classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                    event_range=config["event_range"],
                )
            )
            return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])
        config = {**config, "case_id": case_id}
        if case_id == BR032_AUTH_MISMATCH_CASE_ID:
            return _br032_result(
                manifest=manifest,
                connection=connection,
                config=config,
                events=events,
                diagnostics=diagnostics,
            )
        return _placeholder_result(
            manifest=manifest,
            connection=connection,
            config=config,
            events=events,
            diagnostics=diagnostics,
        )
