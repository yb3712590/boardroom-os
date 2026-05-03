from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.deliverable_contract import (
    ConvergencePolicy,
    DeliverableContract,
    DeliverableEvaluation,
    DeliverableEvaluationPolicy,
    compile_closeout_evidence_pack,
    compile_deliverable_contract,
    checker_contract_gate,
    evaluate_deliverable_contract,
)
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)
from app.core.workspace_path_contracts import (
    CloseoutFinalRefStatus,
    classify_closeout_final_artifact_ref,
)

ACTIVE_TICKET_STATUSES = {
    "PENDING",
    "LEASED",
    "EXECUTING",
    "BLOCKED_FOR_BOARD_REVIEW",
    "REWORK_REQUIRED",
    "CANCEL_REQUESTED",
}
DELIVERY_MAINLINE_STAGES = {"BUILD", "CHECK", "REVIEW"}
DELIVERY_MAINLINE_OUTPUT_SCHEMA_STAGE = {
    SOURCE_CODE_DELIVERY_SCHEMA_REF: "BUILD",
    DELIVERY_CHECK_REPORT_SCHEMA_REF: "CHECK",
    UI_MILESTONE_REVIEW_SCHEMA_REF: "REVIEW",
}
PASSING_DELIVERY_CHECK_STATUSES = {"PASS", "PASS_WITH_NOTES"}
APPROVED_REVIEW_STATUSES = {"APPROVED", "APPROVED_WITH_NOTES"}
BLOCKING_REVIEW_STATUSES = {"CHANGES_REQUIRED", "ESCALATED"}
FAIL_CLOSED_MARKERS = {
    "FAIL_CLOSED",
    "NOT APPROVED FOR COMPLETION",
}


@dataclass(frozen=True)
class WorkflowCloseoutCompletion:
    closeout_ticket: dict[str, Any]
    closeout_terminal_event: dict[str, Any]


def ticket_lineage_ticket_ids(
    ticket_id: str,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> list[str]:
    lineage_ticket_ids: list[str] = []
    current_ticket_id = str(ticket_id or "").strip()
    seen_ticket_ids: set[str] = set()
    while current_ticket_id and current_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(current_ticket_id)
        lineage_ticket_ids.append(current_ticket_id)
        created_spec = created_specs_by_ticket.get(current_ticket_id) or {}
        current_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
    return lineage_ticket_ids


def _ticket_lineage_ticket_ids(
    ticket_id: str,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> list[str]:
    return ticket_lineage_ticket_ids(ticket_id, created_specs_by_ticket)


def _is_redundant_active_closeout_ticket(
    ticket: dict[str, Any],
    *,
    closeout_ticket: dict[str, Any],
    closeout_completed_at: datetime,
    created_spec: dict[str, Any] | None,
) -> bool:
    ticket_id = str(ticket.get("ticket_id") or "")
    if ticket_id == str(closeout_ticket.get("ticket_id") or ""):
        return False
    if str(ticket.get("status") or "") not in ACTIVE_TICKET_STATUSES:
        return False
    if str(ticket.get("node_id") or "") != str(closeout_ticket.get("node_id") or ""):
        return False
    if str((created_spec or {}).get("output_schema_ref") or "") != DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return False
    updated_at = ticket.get("updated_at")
    if not isinstance(updated_at, datetime):
        return False
    return updated_at <= closeout_completed_at


def _is_redundant_active_delivery_ticket(
    ticket: dict[str, Any],
    *,
    tickets: list[dict[str, Any]],
    closeout_completed_at: datetime,
    closeout_lineage_ticket_ids: set[str],
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> bool:
    if str(ticket.get("status") or "") not in ACTIVE_TICKET_STATUSES:
        return False
    updated_at = ticket.get("updated_at")
    if not isinstance(updated_at, datetime) or updated_at > closeout_completed_at:
        return False
    node_id = str(ticket.get("node_id") or "").strip()
    if not node_id:
        return False
    delivery_stage = delivery_mainline_stage_for_ticket(created_spec, created_specs_by_ticket)
    if delivery_stage not in DELIVERY_MAINLINE_STAGES:
        return False
    ticket_id = str(ticket.get("ticket_id") or "")
    lineage_ticket_ids = _ticket_lineage_ticket_ids(ticket_id, created_specs_by_ticket)
    if any(
        ancestor_ticket_id in closeout_lineage_ticket_ids
        and str((created_specs_by_ticket.get(ancestor_ticket_id) or {}).get("node_id") or "").strip() == node_id
        and delivery_mainline_stage_for_ticket(
            created_specs_by_ticket.get(ancestor_ticket_id),
            created_specs_by_ticket,
        )
        == delivery_stage
        for ancestor_ticket_id in lineage_ticket_ids[1:]
    ):
        return True
    for completed_ticket in tickets:
        completed_ticket_id = str(completed_ticket.get("ticket_id") or "")
        if completed_ticket_id == ticket_id:
            continue
        if str(completed_ticket.get("status") or "") != "COMPLETED":
            continue
        if str(completed_ticket.get("node_id") or "").strip() != node_id:
            continue
        completed_updated_at = completed_ticket.get("updated_at")
        if not isinstance(completed_updated_at, datetime) or completed_updated_at > closeout_completed_at:
            continue
        completed_stage = delivery_mainline_stage_for_ticket(
            created_specs_by_ticket.get(completed_ticket_id),
            created_specs_by_ticket,
        )
        if completed_stage == delivery_stage:
            return True
    return False


def _normalized_delivery_stage(created_spec: dict[str, Any] | None) -> str:
    if not isinstance(created_spec, dict):
        return ""
    return str(created_spec.get("delivery_stage") or "").strip().upper()


def _resolved_maker_ticket_spec(
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(created_spec, dict):
        return None
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
    if isinstance(maker_ticket_spec, dict) and maker_ticket_spec:
        return maker_ticket_spec
    maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
    if not maker_ticket_id:
        return None
    return created_specs_by_ticket.get(maker_ticket_id)


def delivery_mainline_stage_for_ticket(
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> str | None:
    delivery_stage = _normalized_delivery_stage(created_spec)
    if delivery_stage in DELIVERY_MAINLINE_STAGES:
        return delivery_stage
    output_schema_ref = str((created_spec or {}).get("output_schema_ref") or "")
    inferred_stage = DELIVERY_MAINLINE_OUTPUT_SCHEMA_STAGE.get(output_schema_ref)
    if inferred_stage is not None:
        return inferred_stage
    if (
        isinstance(created_spec, dict)
        and output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF
    ):
        maker_ticket_spec = _resolved_maker_ticket_spec(created_spec, created_specs_by_ticket)
        maker_delivery_stage = delivery_mainline_stage_for_ticket(maker_ticket_spec, created_specs_by_ticket)
        if maker_delivery_stage in DELIVERY_MAINLINE_STAGES:
            return maker_delivery_stage
    return None


def ticket_has_delivery_mainline_evidence(
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> bool:
    return delivery_mainline_stage_for_ticket(created_spec, created_specs_by_ticket) is not None


def workflow_has_delivery_mainline_evidence(
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> bool:
    return any(
        ticket_has_delivery_mainline_evidence(created_spec, created_specs_by_ticket)
        for created_spec in created_specs_by_ticket.values()
    )


def _closeout_gate_issue(
    *,
    reason_code: str,
    ticket_id: str | None = None,
    output_schema_ref: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {"reason_code": reason_code}
    if ticket_id:
        issue["ticket_id"] = ticket_id
    if output_schema_ref:
        issue["output_schema_ref"] = output_schema_ref
    if details:
        issue["details"] = details
    return issue


def _terminal_payload(terminal_event: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(terminal_event, dict):
        return {}
    payload = terminal_event.get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def _ticket_sort_key(ticket: dict[str, Any]) -> tuple[datetime, str]:
    updated_at = ticket.get("updated_at")
    if not isinstance(updated_at, datetime):
        updated_at = datetime.min
    return updated_at, str(ticket.get("ticket_id") or "")


def _latest_ticket_ids_by_node(tickets: list[dict[str, Any]]) -> set[str]:
    latest_by_node: dict[str, dict[str, Any]] = {}
    for ticket in tickets:
        node_id = str(ticket.get("node_id") or "").strip()
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        if not node_id or not ticket_id:
            continue
        previous = latest_by_node.get(node_id)
        if previous is None or _ticket_sort_key(previous) <= _ticket_sort_key(ticket):
            latest_by_node[node_id] = ticket
    return {str(ticket.get("ticket_id") or "") for ticket in latest_by_node.values()}


def _payload_review_status(payload: dict[str, Any]) -> str:
    maker_checker_summary = payload.get("maker_checker_summary")
    if isinstance(maker_checker_summary, dict):
        nested_status = str(maker_checker_summary.get("review_status") or "").strip()
        if nested_status:
            return nested_status
    return str(payload.get("review_status") or "").strip()


def _blocking_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return []
    return [
        finding
        for finding in findings
        if isinstance(finding, dict) and bool(finding.get("blocking"))
    ]


def _delivery_check_issue(
    *,
    ticket_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    for candidate_payload in _payload_dicts_from_terminal_payload(payload):
        status = str(candidate_payload.get("status") or "").strip()
        blocking_findings = _blocking_findings(candidate_payload)
        if status and status not in PASSING_DELIVERY_CHECK_STATUSES:
            return _closeout_gate_issue(
                reason_code="delivery_check_failed",
                ticket_id=ticket_id,
                output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
                details={"status": status, "blocking_finding_count": len(blocking_findings)},
            )
        if _payload_contains_fail_closed_marker(candidate_payload):
            return _closeout_gate_issue(
                reason_code="delivery_check_failed",
                ticket_id=ticket_id,
                output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
                details={
                    "status": status,
                    "blocking_finding_count": len(blocking_findings),
                    "fail_closed_marker": True,
                },
            )
        if blocking_findings:
            return _closeout_gate_issue(
                reason_code="delivery_check_blocking_findings",
                ticket_id=ticket_id,
                output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
                details={"status": status, "blocking_finding_count": len(blocking_findings)},
            )
    return None


def _delivery_check_contract_evaluation(
    *,
    workflow_id: str,
    graph_version: str,
    ticket_id: str,
    payload: dict[str, Any],
) -> DeliverableEvaluation | None:
    blocking_findings = []
    candidate_payloads = _payload_dicts_from_terminal_payload(payload)
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, dict):
        candidate_payloads.append(nested_payload)
    for candidate_payload in candidate_payloads:
        status = str(candidate_payload.get("status") or "").strip()
        findings = [
            finding
            for finding in list(candidate_payload.get("findings") or [])
            if isinstance(finding, dict) and bool(finding.get("blocking"))
        ]
        for finding in findings:
            finding_id = str(finding.get("finding_id") or "").strip()
            if finding_id:
                blocking_findings.append(
                    {
                        "finding_id": finding_id,
                        "summary": str(finding.get("summary") or "").strip()
                        or "Delivery check report has a blocking finding.",
                    }
                )
        if status == "FAIL" and not blocking_findings:
            blocking_findings.append(
                {
                    "finding_id": "delivery_check_report_failed",
                    "summary": str(candidate_payload.get("summary") or "").strip()
                    or "Delivery check report returned FAIL.",
                }
            )
    if not blocking_findings:
        return None
    acceptance = [
        {
            "criterion_id": f"AC-{finding['finding_id']}",
            "description": finding["summary"],
        }
        for finding in blocking_findings
    ]
    required_evidence = [
        {
            "evidence_id": f"ev_{finding['finding_id']}",
            "evidence_kind": "risk_disposition",
            "acceptance_criteria_refs": [f"AC-{finding['finding_id']}"],
        }
        for finding in blocking_findings
    ]
    contract = compile_deliverable_contract(
        workflow_id=workflow_id,
        graph_version=graph_version,
        source_ticket_refs=[ticket_id],
        acceptance_criteria=acceptance,
        required_evidence=required_evidence,
        metadata={
            "round9c_legacy_input_compiler": True,
            "source": "workflow_completion.failed_delivery_check_report",
        },
    )
    return evaluate_deliverable_contract(
        contract,
        compile_closeout_evidence_pack(
            workflow_id=workflow_id,
            graph_version=graph_version,
            final_evidence_refs=[f"ticket://{ticket_id}/failed-delivery-report"],
            closeout_summary={
                "source": "workflow_completion.failed_delivery_check_report",
                "maker_ticket_id": ticket_id,
            },
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9c.failed_delivery_report"),
    )


def _checker_contract_gate_issue(
    *,
    workflow_id: str,
    graph_version: str,
    maker_ticket_id: str,
    maker_payload: dict[str, Any],
    checker_ticket_id: str,
    checker_payload: dict[str, Any],
) -> dict[str, Any] | None:
    evaluation = _delivery_check_contract_evaluation(
        workflow_id=workflow_id,
        graph_version=graph_version,
        ticket_id=maker_ticket_id,
        payload=maker_payload,
    )
    if evaluation is None:
        return None
    convergence_policy_payload = checker_payload.get("convergence_policy")
    convergence_policy = (
        ConvergencePolicy.model_validate(convergence_policy_payload)
        if isinstance(convergence_policy_payload, dict)
        else None
    )
    gate = checker_contract_gate(
        evaluation=evaluation,
        review_status=_payload_review_status(checker_payload),
        convergence_policy=convergence_policy,
        failed_delivery_report=True,
    )
    if gate.allowed:
        return None
    return _closeout_gate_issue(
        reason_code=gate.reason_code,
        ticket_id=checker_ticket_id,
        output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
        details={
            "maker_ticket_id": maker_ticket_id,
            "contract_id": gate.contract_id,
            "evaluation_fingerprint": gate.evaluation_fingerprint,
            "blocking_finding_count": gate.blocking_finding_count,
            "requires_convergence_policy": gate.requires_convergence_policy,
            "policy_ref": gate.policy_ref,
        },
    )


def _maker_checker_issue(
    *,
    ticket_id: str,
    payload: dict[str, Any],
    maker_output_schema_ref: str,
) -> dict[str, Any] | None:
    review_status = _payload_review_status(payload)
    blocking_findings = _blocking_findings(payload)
    if review_status in BLOCKING_REVIEW_STATUSES or blocking_findings:
        return _closeout_gate_issue(
            reason_code="delivery_check_blocking_findings",
            ticket_id=ticket_id,
            output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
            details={
                "review_status": review_status,
                "maker_output_schema_ref": maker_output_schema_ref,
                "blocking_finding_count": len(blocking_findings),
            },
        )
    return None


def _collect_artifact_refs_from_terminal_payload(payload: dict[str, Any]) -> set[str]:
    refs: set[str] = {
        str(ref).strip()
        for ref in list(payload.get("artifact_refs") or [])
        if str(ref).strip()
    }
    refs.update(
        str(ref).strip()
        for ref in list(payload.get("verification_evidence_refs") or [])
        if str(ref).strip()
    )
    for written_artifact in list(payload.get("written_artifacts") or []):
        if not isinstance(written_artifact, dict):
            continue
        artifact_ref = str(written_artifact.get("artifact_ref") or "").strip()
        if artifact_ref:
            refs.add(artifact_ref)
    for produced_asset in list(payload.get("produced_process_assets") or []):
        if not isinstance(produced_asset, dict):
            continue
        source_metadata = produced_asset.get("source_metadata")
        if not isinstance(source_metadata, dict):
            continue
        for field_name in (
            "artifact_ref",
            "source_artifact_ref",
        ):
            artifact_ref = str(source_metadata.get(field_name) or "").strip()
            if artifact_ref:
                refs.add(artifact_ref)
        for field_name in (
            "source_file_refs",
            "written_artifact_refs",
            "verification_evidence_refs",
        ):
            refs.update(
                str(ref).strip()
                for ref in list(source_metadata.get(field_name) or [])
                if str(ref).strip()
            )
    return refs


def _collect_schema_artifact_refs(
    *,
    output_schema_ref: str,
    created_specs_by_ticket: dict[str, dict[str, Any]],
    ticket_terminal_events_by_ticket: dict[str, dict[str, Any] | None],
) -> set[str]:
    refs: set[str] = set()
    for ticket_id, created_spec in created_specs_by_ticket.items():
        if str(created_spec.get("output_schema_ref") or "").strip() != output_schema_ref:
            continue
        refs.update(
            _collect_artifact_refs_from_terminal_payload(
                _terminal_payload(ticket_terminal_events_by_ticket.get(ticket_id))
            )
        )
    return refs


def _payload_dicts_from_terminal_payload(terminal_payload: dict[str, Any]) -> list[dict[str, Any]]:
    payloads = [terminal_payload]
    for written_artifact in list(terminal_payload.get("written_artifacts") or []):
        if not isinstance(written_artifact, dict):
            continue
        content_json = written_artifact.get("content_json")
        if isinstance(content_json, dict):
            payloads.append(content_json)
    return payloads


def _payload_contains_fail_closed_marker(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.upper()
        return any(marker in normalized for marker in FAIL_CLOSED_MARKERS)
    if isinstance(value, dict):
        return any(_payload_contains_fail_closed_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_payload_contains_fail_closed_marker(item) for item in value)
    return False


def _is_placeholder_final_artifact_ref(artifact_ref: str) -> bool:
    normalized = str(artifact_ref or "").strip().lower()
    return (
        normalized.endswith("/source.py")
        or "/placeholder/" in normalized
        or "placeholder" in normalized
    )


def _collect_closeout_final_artifact_refs(payloads: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for payload in payloads:
        refs.update(
            str(ref).strip()
            for ref in list(payload.get("final_artifact_refs") or [])
            if str(ref).strip()
        )
    return refs


def evaluate_closeout_deliverable_contract_preview(
    *,
    contract: DeliverableContract,
    closeout_terminal_payload: dict[str, Any],
    policy: DeliverableEvaluationPolicy | None = None,
) -> DeliverableEvaluation:
    closeout_payloads = _payload_dicts_from_terminal_payload(closeout_terminal_payload)
    evidence_pack = compile_closeout_evidence_pack(
        workflow_id=contract.workflow_id,
        graph_version=contract.graph_version,
        final_evidence_refs=list(_collect_closeout_final_artifact_refs(closeout_payloads)),
        closeout_summary={
            "payload_count": len(closeout_payloads),
            "source": "workflow_completion.closeout_preview",
        },
    )
    return evaluate_deliverable_contract(
        contract,
        evidence_pack,
        policy or DeliverableEvaluationPolicy(policy_ref="policy:round9a.closeout_preview"),
    )


def _has_documentation_evidence(payloads: list[dict[str, Any]]) -> bool:
    for payload in payloads:
        documentation_updates = payload.get("documentation_updates")
        if isinstance(documentation_updates, list) and documentation_updates:
            return True
    return False


def _closeout_payload_issue(
    *,
    closeout_ticket_id: str,
    closeout_terminal_payload: dict[str, Any],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    ticket_terminal_events_by_ticket: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    closeout_payloads = _payload_dicts_from_terminal_payload(closeout_terminal_payload)
    if any(_payload_contains_fail_closed_marker(payload) for payload in closeout_payloads):
        return _closeout_gate_issue(
            reason_code="closeout_payload_fail_closed",
            ticket_id=closeout_ticket_id,
            output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        )

    final_artifact_refs = _collect_closeout_final_artifact_refs(closeout_payloads)
    known_final_refs = _collect_schema_artifact_refs(
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )
    known_final_refs.update(
        _collect_schema_artifact_refs(
            output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
            created_specs_by_ticket=created_specs_by_ticket,
            ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
        )
    )
    known_final_refs.update(final_artifact_refs)
    placeholder_final_refs = {
        ref for ref in known_final_refs if _is_placeholder_final_artifact_ref(ref)
    }
    for artifact_ref in final_artifact_refs:
        final_ref_check = classify_closeout_final_artifact_ref(
            artifact_ref,
            current_artifact_refs=known_final_refs,
            superseded_artifact_refs=set(),
            placeholder_artifact_refs=placeholder_final_refs,
        )
        if final_ref_check.status != CloseoutFinalRefStatus.ACCEPTED:
            return _closeout_gate_issue(
                reason_code="closeout_illegal_final_artifact_ref",
                ticket_id=closeout_ticket_id,
                output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
                details={
                    "artifact_ref": artifact_ref,
                    "status": final_ref_check.status.value,
                    "kind": final_ref_check.kind.value,
                },
            )

    source_delivery_ticket_ids = {
        ticket_id
        for ticket_id, created_spec in created_specs_by_ticket.items()
        if str(created_spec.get("output_schema_ref") or "").strip() == SOURCE_CODE_DELIVERY_SCHEMA_REF
    }
    source_delivery_refs = _collect_schema_artifact_refs(
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )
    if source_delivery_ticket_ids and (not source_delivery_refs or not final_artifact_refs.intersection(source_delivery_refs)):
        return _closeout_gate_issue(
            reason_code="closeout_missing_source_delivery_evidence",
            ticket_id=closeout_ticket_id,
            output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
            details={"source_delivery_ticket_ids": sorted(source_delivery_ticket_ids)},
        )

    delivery_check_ticket_ids = {
        ticket_id
        for ticket_id, created_spec in created_specs_by_ticket.items()
        if str(created_spec.get("output_schema_ref") or "").strip() == DELIVERY_CHECK_REPORT_SCHEMA_REF
    }
    delivery_check_refs = _collect_schema_artifact_refs(
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )
    if delivery_check_ticket_ids and (not delivery_check_refs or not final_artifact_refs.intersection(delivery_check_refs)):
        return _closeout_gate_issue(
            reason_code="closeout_missing_qa_evidence",
            ticket_id=closeout_ticket_id,
            output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
            details={"delivery_check_ticket_ids": sorted(delivery_check_ticket_ids)},
        )

    if not _has_documentation_evidence(closeout_payloads):
        return _closeout_gate_issue(
            reason_code="closeout_missing_documentation_evidence",
            ticket_id=closeout_ticket_id,
            output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        )
    return None


def evaluate_workflow_closeout_gate_issue(
    *,
    tickets: list[dict[str, Any]],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    ticket_terminal_events_by_ticket: dict[str, dict[str, Any] | None],
    closeout_ticket: dict[str, Any] | None = None,
    closeout_terminal_event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    workflow_id = ""
    for ticket in tickets:
        workflow_id = str(ticket.get("workflow_id") or "").strip()
        if workflow_id:
            break
    if not workflow_id:
        for created_spec in created_specs_by_ticket.values():
            workflow_id = str(created_spec.get("workflow_id") or "").strip()
            if workflow_id:
                break
    graph_version = ""
    for created_spec in created_specs_by_ticket.values():
        graph_version = str(created_spec.get("graph_version") or "").strip()
        if graph_version:
            break
    graph_version = graph_version or "legacy-closeout-gate"
    latest_ticket_ids = _latest_ticket_ids_by_node(tickets)
    for ticket_id in sorted(latest_ticket_ids):
        created_spec = created_specs_by_ticket.get(ticket_id) or {}
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        terminal_payload = _terminal_payload(ticket_terminal_events_by_ticket.get(ticket_id))
        if output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
            issue = _delivery_check_issue(ticket_id=ticket_id, payload=terminal_payload)
            if issue is not None:
                return issue
            continue
        if output_schema_ref != MAKER_CHECKER_VERDICT_SCHEMA_REF:
            continue
        maker_ticket_spec = _resolved_maker_ticket_spec(created_spec, created_specs_by_ticket) or {}
        maker_output_schema_ref = str(maker_ticket_spec.get("output_schema_ref") or "").strip()
        maker_ticket_id = str((created_spec.get("maker_checker_context") or {}).get("maker_ticket_id") or "").strip()
        if maker_output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF and maker_ticket_id:
            maker_payload = _terminal_payload(ticket_terminal_events_by_ticket.get(maker_ticket_id))
            checker_review_status = _payload_review_status(terminal_payload)
            if checker_review_status in APPROVED_REVIEW_STATUSES or isinstance(
                terminal_payload.get("convergence_policy"),
                dict,
            ):
                issue = _checker_contract_gate_issue(
                    workflow_id=workflow_id or str(created_spec.get("workflow_id") or "workflow-unknown"),
                    graph_version=graph_version,
                    maker_ticket_id=maker_ticket_id,
                    maker_payload=maker_payload,
                    checker_ticket_id=ticket_id,
                    checker_payload=terminal_payload,
                )
                if issue is not None:
                    return issue
        issue = _maker_checker_issue(
            ticket_id=ticket_id,
            payload=terminal_payload,
            maker_output_schema_ref=maker_output_schema_ref,
        )
        if issue is not None:
            return issue

    if closeout_ticket is None or closeout_terminal_event is None:
        return None
    closeout_ticket_id = str(closeout_ticket.get("ticket_id") or "").strip()
    return _closeout_payload_issue(
        closeout_ticket_id=closeout_ticket_id,
        closeout_terminal_payload=_terminal_payload(closeout_terminal_event),
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )


def infer_workflow_current_stage(
    *,
    nodes: list[dict[str, Any]],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    closeout_completion: WorkflowCloseoutCompletion | None = None,
) -> str:
    if closeout_completion is not None:
        return "closeout"
    if not nodes:
        return "project_init"

    latest_node = max(
        nodes,
        key=lambda item: (
            item.get("updated_at") or datetime.min,
            str(item.get("node_id") or ""),
        ),
    )
    created_spec = created_specs_by_ticket.get(str(latest_node.get("latest_ticket_id") or ""))
    if created_spec is None:
        return "project_init"

    delivery_stage = delivery_mainline_stage_for_ticket(created_spec, created_specs_by_ticket)
    if delivery_stage:
        return delivery_stage.lower()

    output_schema_ref = str(created_spec.get("output_schema_ref") or "")
    if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF or output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return "plan"
    return "project_init"


def resolve_workflow_closeout_completion(
    *,
    tickets: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    has_open_approval: bool,
    has_open_incident: bool,
    created_specs_by_ticket: dict[str, dict[str, Any]],
    ticket_terminal_events_by_ticket: dict[str, dict[str, Any] | None],
) -> WorkflowCloseoutCompletion | None:
    if not nodes:
        return None
    if has_open_approval or has_open_incident:
        return None
    if not workflow_has_delivery_mainline_evidence(created_specs_by_ticket):
        return None

    closeout_candidates: list[tuple[datetime, str, dict[str, Any], dict[str, Any]]] = []
    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id") or "")
        created_spec = created_specs_by_ticket.get(ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "") != DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
            continue
        terminal_event = ticket_terminal_events_by_ticket.get(ticket_id)
        if not isinstance(terminal_event, dict):
            continue
        if str(terminal_event.get("event_type") or "") != "TICKET_COMPLETED":
            continue
        occurred_at = terminal_event.get("occurred_at")
        if not isinstance(occurred_at, datetime):
            continue
        closeout_candidates.append((occurred_at, ticket_id, ticket, terminal_event))

    if not closeout_candidates:
        return None

    closeout_completed_at, _, closeout_ticket, closeout_terminal_event = max(
        closeout_candidates,
        key=lambda item: (item[0], item[1]),
    )
    closeout_lineage_ticket_ids = set(
        _ticket_lineage_ticket_ids(str(closeout_ticket.get("ticket_id") or ""), created_specs_by_ticket)
    )
    if any(
        not _is_redundant_active_closeout_ticket(
            ticket,
            closeout_ticket=closeout_ticket,
            closeout_completed_at=closeout_completed_at,
            created_spec=created_specs_by_ticket.get(str(ticket.get("ticket_id") or "")),
        )
        and not _is_redundant_active_delivery_ticket(
            ticket,
            tickets=tickets,
            closeout_completed_at=closeout_completed_at,
            closeout_lineage_ticket_ids=closeout_lineage_ticket_ids,
            created_spec=created_specs_by_ticket.get(str(ticket.get("ticket_id") or "")),
            created_specs_by_ticket=created_specs_by_ticket,
        )
        for ticket in tickets
        if str(ticket.get("status") or "") in ACTIVE_TICKET_STATUSES
    ):
        return None
    if evaluate_workflow_closeout_gate_issue(
        tickets=tickets,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
        closeout_ticket=closeout_ticket,
        closeout_terminal_event=closeout_terminal_event,
    ) is not None:
        return None
    return WorkflowCloseoutCompletion(
        closeout_ticket=closeout_ticket,
        closeout_terminal_event=closeout_terminal_event,
    )
