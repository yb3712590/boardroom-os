from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.contracts.common import JsonValue, StrictModel


DELIVERABLE_CONTRACT_VERSION = "v1"


class ContractFindingSeverity(StrEnum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"


class ContractEvaluationStatus(StrEnum):
    SATISFIED = "SATISFIED"
    BLOCKED = "BLOCKED"


DEFAULT_ALLOWED_EVIDENCE_KINDS = {
    "api_contract_test",
    "git_closeout",
    "integration_test",
    "maker_checker_verdict",
    "performance_check",
    "risk_disposition",
    "runtime_smoke",
    "security_check",
    "source_inventory",
    "unit_test",
}


class AcceptanceCriterion(StrictModel):
    criterion_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    locked_scope_refs: list[str] = Field(default_factory=list)
    priority: str = "MUST"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RequiredSourceSurface(StrictModel):
    surface_id: str = Field(min_length=1)
    path_patterns: list[str] = Field(default_factory=list)
    owning_capabilities: list[str] = Field(default_factory=list)
    expected_behavior: str = ""
    acceptance_criteria_refs: list[str] = Field(default_factory=list)
    required_evidence_kinds: list[str] = Field(default_factory=list)
    minimum_non_placeholder_evidence: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RequiredEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    evidence_kind: str = Field(min_length=1)
    acceptance_criteria_refs: list[str] = Field(default_factory=list)
    source_surface_refs: list[str] = Field(default_factory=list)
    required: bool = True
    minimum_count: int = 1
    review_gate_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CloseoutObligation(StrictModel):
    obligation_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    required_evidence_refs: list[str] = Field(default_factory=list)
    required_acceptance_criteria_refs: list[str] = Field(default_factory=list)
    final_evidence_table_required: bool = True
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DeliverableContract(StrictModel):
    contract_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    source_prd_refs: list[str] = Field(default_factory=list)
    source_charter_refs: list[str] = Field(default_factory=list)
    source_ticket_refs: list[str] = Field(default_factory=list)
    locked_scope: list[dict[str, JsonValue]] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    required_source_surfaces: list[RequiredSourceSurface] = Field(default_factory=list)
    required_evidence: list[RequiredEvidence] = Field(default_factory=list)
    required_review_gates: list[dict[str, JsonValue]] = Field(default_factory=list)
    placeholder_rules: list[dict[str, JsonValue]] = Field(default_factory=list)
    supersede_rules: list[dict[str, JsonValue]] = Field(default_factory=list)
    closeout_requirements: list[CloseoutObligation] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DeliverableEvidence(StrictModel):
    evidence_ref: str = Field(min_length=1)
    evidence_kind: str = Field(min_length=1)
    acceptance_criteria_refs: list[str] = Field(default_factory=list)
    source_surface_refs: list[str] = Field(default_factory=list)
    producer_ticket_id: str | None = None
    artifact_kind: str | None = None
    legality_status: str | None = None
    supersedes_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DeliverableEvidencePack(StrictModel):
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    evidence: list[DeliverableEvidence] = Field(default_factory=list)
    final_evidence_refs: list[str] = Field(default_factory=list)
    source_surface_evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    review_gate_results: list[dict[str, JsonValue]] = Field(default_factory=list)
    supersede_summary: list[dict[str, JsonValue]] = Field(default_factory=list)
    closeout_summary: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DeliverableEvaluationPolicy(StrictModel):
    policy_ref: str = Field(min_length=1)
    allowed_evidence_kinds: list[str] = Field(
        default_factory=lambda: sorted(DEFAULT_ALLOWED_EVIDENCE_KINDS)
    )
    require_acceptance_criteria: bool = True
    require_final_evidence: bool = True
    fail_unknown_evidence_kind: bool = True
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ContractFinding(StrictModel):
    finding_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    severity: ContractFindingSeverity
    blocking: bool
    summary: str = Field(min_length=1)
    acceptance_criteria_refs: list[str] = Field(default_factory=list)
    required_evidence_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_surface_refs: list[str] = Field(default_factory=list)
    suggested_rework_targets: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DeliverableEvaluation(StrictModel):
    contract_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_ref: str = Field(min_length=1)
    status: ContractEvaluationStatus
    evaluation_fingerprint: str = Field(min_length=1)
    findings: list[ContractFinding] = Field(default_factory=list)
    blocking_finding_count: int = 0
    acceptance_criteria_count: int = 0
    required_evidence_count: int = 0
    final_evidence_ref_count: int = 0
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(_plain(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _stable_hash(value: Any, *, length: int = 12) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:length]


def _stable_unique_strings(values: list[Any] | tuple[Any, ...] | set[Any] | None) -> list[str]:
    return sorted({str(value).strip() for value in list(values or []) if str(value).strip()})


def _stable_dicts(values: list[Any] | None) -> list[dict[str, JsonValue]]:
    normalized: list[dict[str, JsonValue]] = []
    for value in list(values or []):
        if not isinstance(value, dict):
            continue
        item = _plain(value)
        if isinstance(item, dict) and item:
            normalized.append(item)
    return sorted(normalized, key=_stable_json)


def _normalize_acceptance_criterion(value: Any) -> tuple[AcceptanceCriterion, bool] | None:
    explicit_id = False
    if isinstance(value, str):
        description = value.strip()
        if not description:
            return None
        criterion_id = f"AC-{_stable_hash({'description': description}, length=10)}"
        return (
            AcceptanceCriterion(
                criterion_id=criterion_id,
                description=description,
            ),
            explicit_id,
        )
    if not isinstance(value, dict):
        return None
    description = str(value.get("description") or value.get("summary") or "").strip()
    if not description:
        return None
    raw_criterion_id = str(
        value.get("criterion_id") or value.get("acceptance_id") or value.get("id") or ""
    ).strip()
    explicit_id = bool(raw_criterion_id)
    criterion_id = raw_criterion_id or f"AC-{_stable_hash({'description': description}, length=10)}"
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return (
        AcceptanceCriterion(
            criterion_id=criterion_id,
            description=description,
            source_refs=_stable_unique_strings(value.get("source_refs") if isinstance(value.get("source_refs"), list) else []),
            locked_scope_refs=_stable_unique_strings(
                value.get("locked_scope_refs") if isinstance(value.get("locked_scope_refs"), list) else []
            ),
            priority=str(value.get("priority") or "MUST").strip() or "MUST",
            metadata=_plain(metadata),
        ),
        explicit_id,
    )


def _normalize_required_source_surface(value: Any) -> RequiredSourceSurface | None:
    if not isinstance(value, dict):
        return None
    surface_id = str(value.get("surface_id") or value.get("id") or "").strip()
    if not surface_id:
        return None
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return RequiredSourceSurface(
        surface_id=surface_id,
        path_patterns=_stable_unique_strings(
            value.get("path_patterns") or value.get("paths")
            if isinstance(value.get("path_patterns") or value.get("paths"), list)
            else []
        ),
        owning_capabilities=_stable_unique_strings(
            value.get("owning_capabilities") or value.get("required_capabilities")
            if isinstance(value.get("owning_capabilities") or value.get("required_capabilities"), list)
            else []
        ),
        expected_behavior=str(value.get("expected_behavior") or "").strip(),
        acceptance_criteria_refs=_stable_unique_strings(
            value.get("acceptance_criteria_refs") or value.get("acceptance_refs")
            if isinstance(value.get("acceptance_criteria_refs") or value.get("acceptance_refs"), list)
            else []
        ),
        required_evidence_kinds=_stable_unique_strings(
            value.get("required_evidence_kinds") or value.get("required_evidence")
            if isinstance(value.get("required_evidence_kinds") or value.get("required_evidence"), list)
            else []
        ),
        minimum_non_placeholder_evidence=_stable_unique_strings(
            value.get("minimum_non_placeholder_evidence")
            if isinstance(value.get("minimum_non_placeholder_evidence"), list)
            else []
        ),
        required_tests=_stable_unique_strings(
            value.get("required_tests") or value.get("required_checks")
            if isinstance(value.get("required_tests") or value.get("required_checks"), list)
            else []
        ),
        metadata=_plain(metadata),
    )


def _normalize_required_evidence(value: Any) -> RequiredEvidence | None:
    if not isinstance(value, dict):
        return None
    evidence_kind = str(value.get("evidence_kind") or value.get("kind") or "").strip()
    if not evidence_kind:
        return None
    evidence_id = str(value.get("evidence_id") or value.get("id") or "").strip()
    evidence_id = evidence_id or f"ev_{evidence_kind}_{_stable_hash(value, length=10)}"
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    minimum_count = value.get("minimum_count", 1)
    if not isinstance(minimum_count, int) or isinstance(minimum_count, bool) or minimum_count < 1:
        minimum_count = 1
    return RequiredEvidence(
        evidence_id=evidence_id,
        evidence_kind=evidence_kind,
        acceptance_criteria_refs=_stable_unique_strings(
            value.get("acceptance_criteria_refs") or value.get("acceptance_refs")
            if isinstance(value.get("acceptance_criteria_refs") or value.get("acceptance_refs"), list)
            else []
        ),
        source_surface_refs=_stable_unique_strings(
            value.get("source_surface_refs") or value.get("surface_refs")
            if isinstance(value.get("source_surface_refs") or value.get("surface_refs"), list)
            else []
        ),
        required=bool(value.get("required", True)),
        minimum_count=minimum_count,
        review_gate_refs=_stable_unique_strings(
            value.get("review_gate_refs") if isinstance(value.get("review_gate_refs"), list) else []
        ),
        metadata=_plain(metadata),
    )


def _normalize_closeout_obligation(value: Any) -> CloseoutObligation | None:
    if isinstance(value, str):
        summary = value.strip()
        if not summary:
            return None
        return CloseoutObligation(
            obligation_id=f"closeout_{_stable_hash({'summary': summary}, length=10)}",
            summary=summary,
        )
    if not isinstance(value, dict):
        return None
    summary = str(value.get("summary") or value.get("description") or "").strip()
    obligation_id = str(value.get("obligation_id") or value.get("id") or "").strip()
    if not obligation_id or not summary:
        return None
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return CloseoutObligation(
        obligation_id=obligation_id,
        summary=summary,
        required_evidence_refs=_stable_unique_strings(
            value.get("required_evidence_refs") if isinstance(value.get("required_evidence_refs"), list) else []
        ),
        required_acceptance_criteria_refs=_stable_unique_strings(
            value.get("required_acceptance_criteria_refs")
            if isinstance(value.get("required_acceptance_criteria_refs"), list)
            else []
        ),
        final_evidence_table_required=bool(value.get("final_evidence_table_required", True)),
        metadata=_plain(metadata),
    )


def compile_deliverable_contract(
    *,
    workflow_id: str,
    graph_version: str,
    source_prd_refs: list[Any] | None = None,
    source_charter_refs: list[Any] | None = None,
    source_ticket_refs: list[Any] | None = None,
    locked_scope: list[Any] | None = None,
    acceptance_criteria: list[Any] | None = None,
    required_source_surfaces: list[Any] | None = None,
    required_evidence: list[Any] | None = None,
    required_review_gates: list[Any] | None = None,
    placeholder_rules: list[Any] | None = None,
    supersede_rules: list[Any] | None = None,
    closeout_requirements: list[Any] | None = None,
    contract_version: str = DELIVERABLE_CONTRACT_VERSION,
    metadata: dict[str, JsonValue] | None = None,
) -> DeliverableContract:
    normalized_acceptance_with_origin = [
        item
        for item in (_normalize_acceptance_criterion(value) for value in list(acceptance_criteria or []))
        if item is not None
    ]
    normalized_acceptance = [
        item
        for item, _ in sorted(
            normalized_acceptance_with_origin,
            key=lambda pair: (0 if pair[1] else 1, pair[0].criterion_id),
        )
    ]
    normalized_surfaces = [
        item
        for item in (_normalize_required_source_surface(value) for value in list(required_source_surfaces or []))
        if item is not None
    ]
    normalized_evidence = [
        item
        for item in (_normalize_required_evidence(value) for value in list(required_evidence or []))
        if item is not None
    ]
    normalized_closeout = [
        item
        for item in (_normalize_closeout_obligation(value) for value in list(closeout_requirements or []))
        if item is not None
    ]
    contract_body = {
        "contract_version": str(contract_version).strip() or DELIVERABLE_CONTRACT_VERSION,
        "workflow_id": str(workflow_id).strip(),
        "graph_version": str(graph_version).strip(),
        "source_prd_refs": _stable_unique_strings(source_prd_refs),
        "source_charter_refs": _stable_unique_strings(source_charter_refs),
        "source_ticket_refs": _stable_unique_strings(source_ticket_refs),
        "locked_scope": _stable_dicts(locked_scope),
        "acceptance_criteria": [item.model_dump(mode="json") for item in normalized_acceptance],
        "required_source_surfaces": [
            item.model_dump(mode="json")
            for item in sorted(normalized_surfaces, key=lambda item: item.surface_id)
        ],
        "required_evidence": [
            item.model_dump(mode="json")
            for item in sorted(normalized_evidence, key=lambda item: item.evidence_id)
        ],
        "required_review_gates": _stable_dicts(required_review_gates),
        "placeholder_rules": _stable_dicts(placeholder_rules),
        "supersede_rules": _stable_dicts(supersede_rules),
        "closeout_requirements": [
            item.model_dump(mode="json")
            for item in sorted(normalized_closeout, key=lambda item: item.obligation_id)
        ],
        "metadata": _plain(metadata or {}),
    }
    contract_hash = _stable_hash(contract_body)
    contract_id = f"dc_{contract_body['workflow_id']}_{contract_body['contract_version']}_{contract_hash}"
    return DeliverableContract.model_validate({"contract_id": contract_id, **contract_body})


def compile_ticket_acceptance_deliverable_contract(
    *,
    workflow_id: str,
    graph_version: str,
    ticket_payloads: list[dict[str, JsonValue]],
    source_prd_refs: list[Any] | None = None,
    locked_scope: list[Any] | None = None,
    contract_version: str = DELIVERABLE_CONTRACT_VERSION,
) -> DeliverableContract:
    acceptance: list[Any] = []
    source_ticket_refs: list[str] = []
    for ticket_payload in ticket_payloads:
        ticket_id = str(ticket_payload.get("ticket_id") or "").strip()
        if ticket_id:
            source_ticket_refs.append(ticket_id)
        raw_acceptance = ticket_payload.get("acceptance_criteria")
        if isinstance(raw_acceptance, list):
            acceptance.extend(raw_acceptance)
    return compile_deliverable_contract(
        workflow_id=workflow_id,
        graph_version=graph_version,
        source_prd_refs=source_prd_refs,
        source_ticket_refs=source_ticket_refs,
        locked_scope=locked_scope,
        acceptance_criteria=acceptance,
        contract_version=contract_version,
    )


def compile_closeout_evidence_pack(
    *,
    workflow_id: str,
    graph_version: str,
    final_evidence_refs: list[Any] | None = None,
    evidence: list[dict[str, JsonValue]] | None = None,
    closeout_summary: dict[str, JsonValue] | None = None,
) -> DeliverableEvidencePack:
    return DeliverableEvidencePack.model_validate(
        {
            "workflow_id": workflow_id,
            "graph_version": graph_version,
            "final_evidence_refs": _stable_unique_strings(final_evidence_refs),
            "evidence": sorted(list(evidence or []), key=_stable_json),
            "closeout_summary": _plain(closeout_summary or {}),
        }
    )


def _finding(
    *,
    reason_code: str,
    summary: str,
    acceptance_criteria_refs: list[Any] | None = None,
    required_evidence_refs: list[Any] | None = None,
    evidence_refs: list[Any] | None = None,
    source_surface_refs: list[Any] | None = None,
    metadata: dict[str, JsonValue] | None = None,
    blocking: bool = True,
) -> ContractFinding:
    normalized = {
        "reason_code": reason_code,
        "acceptance_criteria_refs": _stable_unique_strings(acceptance_criteria_refs),
        "required_evidence_refs": _stable_unique_strings(required_evidence_refs),
        "evidence_refs": _stable_unique_strings(evidence_refs),
        "source_surface_refs": _stable_unique_strings(source_surface_refs),
        "metadata": _plain(metadata or {}),
        "blocking": blocking,
    }
    return ContractFinding(
        finding_id=f"cf_{reason_code}_{_stable_hash(normalized)}",
        reason_code=reason_code,
        severity=ContractFindingSeverity.BLOCKER if blocking else ContractFindingSeverity.WARNING,
        blocking=blocking,
        summary=summary,
        acceptance_criteria_refs=normalized["acceptance_criteria_refs"],
        required_evidence_refs=normalized["required_evidence_refs"],
        evidence_refs=normalized["evidence_refs"],
        source_surface_refs=normalized["source_surface_refs"],
        metadata=normalized["metadata"],
    )


def _required_evidence_is_satisfied(
    required: RequiredEvidence,
    evidence_pack: DeliverableEvidencePack,
) -> bool:
    if not required.required:
        return True
    matching = [
        evidence
        for evidence in evidence_pack.evidence
        if evidence.evidence_kind == required.evidence_kind
        and (
            not required.acceptance_criteria_refs
            or set(required.acceptance_criteria_refs).issubset(set(evidence.acceptance_criteria_refs))
        )
        and (
            not required.source_surface_refs
            or set(required.source_surface_refs).issubset(set(evidence.source_surface_refs))
        )
    ]
    return len(matching) >= required.minimum_count


def evaluate_deliverable_contract(
    contract: DeliverableContract,
    evidence_pack: DeliverableEvidencePack,
    policy: DeliverableEvaluationPolicy,
) -> DeliverableEvaluation:
    findings: list[ContractFinding] = []
    if policy.require_acceptance_criteria and not contract.acceptance_criteria:
        findings.append(
            _finding(
                reason_code="missing_acceptance_criteria",
                summary="Deliverable contract has no acceptance criteria.",
                metadata={"contract_id": contract.contract_id},
            )
        )

    allowed_evidence_kinds = set(_stable_unique_strings(policy.allowed_evidence_kinds))
    if policy.fail_unknown_evidence_kind:
        unknown_evidence = [
            evidence
            for evidence in evidence_pack.evidence
            if evidence.evidence_kind not in allowed_evidence_kinds
        ]
        if unknown_evidence:
            findings.append(
                _finding(
                    reason_code="unknown_evidence_kind",
                    summary="Evidence pack contains evidence kinds outside the deliverable policy allowlist.",
                    acceptance_criteria_refs=[
                        ref
                        for evidence in unknown_evidence
                        for ref in evidence.acceptance_criteria_refs
                    ],
                    evidence_refs=[evidence.evidence_ref for evidence in unknown_evidence],
                    metadata={
                        "unknown_evidence_kinds": _stable_unique_strings(
                            [evidence.evidence_kind for evidence in unknown_evidence]
                        )
                    },
                )
            )

    missing_required_evidence = [
        required
        for required in contract.required_evidence
        if not _required_evidence_is_satisfied(required, evidence_pack)
    ]
    if missing_required_evidence:
        findings.append(
            _finding(
                reason_code="missing_required_evidence",
                summary="Evidence pack does not satisfy all required deliverable evidence.",
                acceptance_criteria_refs=[
                    ref
                    for required in missing_required_evidence
                    for ref in required.acceptance_criteria_refs
                ],
                required_evidence_refs=[required.evidence_id for required in missing_required_evidence],
                source_surface_refs=[
                    ref
                    for required in missing_required_evidence
                    for ref in required.source_surface_refs
                ],
                metadata={
                    "missing_evidence_kinds": _stable_unique_strings(
                        [required.evidence_kind for required in missing_required_evidence]
                    )
                },
            )
        )

    if policy.require_final_evidence and not evidence_pack.final_evidence_refs:
        findings.append(
            _finding(
                reason_code="empty_final_evidence",
                summary="Evidence pack has no final evidence refs for closeout.",
                metadata={"workflow_id": evidence_pack.workflow_id},
            )
        )

    blocking_count = sum(1 for finding in findings if finding.blocking)
    status = (
        ContractEvaluationStatus.BLOCKED
        if blocking_count
        else ContractEvaluationStatus.SATISFIED
    )
    fingerprint_body = {
        "contract": contract,
        "evidence_pack": evidence_pack,
        "policy": policy,
        "finding_ids": [finding.finding_id for finding in findings],
        "status": status.value,
    }
    return DeliverableEvaluation(
        contract_id=contract.contract_id,
        contract_version=contract.contract_version,
        workflow_id=contract.workflow_id,
        graph_version=contract.graph_version,
        policy_ref=policy.policy_ref,
        status=status,
        evaluation_fingerprint=f"de_{contract.contract_id}_{_stable_hash(fingerprint_body)}",
        findings=findings,
        blocking_finding_count=blocking_count,
        acceptance_criteria_count=len(contract.acceptance_criteria),
        required_evidence_count=len(contract.required_evidence),
        final_evidence_ref_count=len(evidence_pack.final_evidence_refs),
    )
