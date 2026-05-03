from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from app.contracts.common import JsonValue, StrictModel
from app.core.workspace_path_contracts import CAPABILITY_WRITE_SURFACES


DELIVERABLE_CONTRACT_VERSION = "v1"


class ContractFindingSeverity(StrEnum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"


class ContractEvaluationStatus(StrEnum):
    SATISFIED = "SATISFIED"
    BLOCKED = "BLOCKED"


APPROVED_CHECKER_REVIEW_STATUSES = {"APPROVED", "APPROVED_WITH_NOTES"}


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

EVIDENCE_LEGALITY_ACCEPTED = "ACCEPTED"
EVIDENCE_LEGALITY_SUPERSEDED = "SUPERSEDED"
EVIDENCE_LEGALITY_PLACEHOLDER = "PLACEHOLDER"
EVIDENCE_LEGALITY_ARCHIVE = "ARCHIVE"
EVIDENCE_LEGALITY_UNKNOWN_REF = "UNKNOWN_REF"
EVIDENCE_LEGALITY_STALE_CURRENT_POINTER = "STALE_CURRENT_POINTER"
EVIDENCE_LEGALITY_ILLEGAL_KIND = "ILLEGAL_KIND"

CURRENT_POINTER_CURRENT = "CURRENT"

_INVALID_EVIDENCE_LEGALITY_STATUSES = {
    EVIDENCE_LEGALITY_SUPERSEDED,
    EVIDENCE_LEGALITY_PLACEHOLDER,
    EVIDENCE_LEGALITY_ARCHIVE,
    EVIDENCE_LEGALITY_UNKNOWN_REF,
    EVIDENCE_LEGALITY_STALE_CURRENT_POINTER,
    EVIDENCE_LEGALITY_ILLEGAL_KIND,
}

_INVALID_CURRENT_POINTER_STATUSES = {
    EVIDENCE_LEGALITY_SUPERSEDED,
    EVIDENCE_LEGALITY_ARCHIVE,
    "STALE",
    "UNKNOWN",
    EVIDENCE_LEGALITY_STALE_CURRENT_POINTER,
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


class EvidenceItem(StrictModel):
    evidence_ref: str = Field(min_length=1)
    evidence_kind: str = Field(min_length=1)
    acceptance_criteria_refs: list[str] = Field(default_factory=list)
    source_surface_refs: list[str] = Field(default_factory=list)
    producer_ticket_id: str | None = None
    producer_node_ref: str | None = None
    artifact_kind: str | None = None
    legality_status: str | None = None
    current_pointer_status: str | None = None
    current_artifact_ref: str | None = None
    supersedes_refs: list[str] = Field(default_factory=list)
    superseded_by_refs: list[str] = Field(default_factory=list)
    placeholder: bool = False
    archive: bool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EvidencePack(StrictModel):
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    final_evidence_refs: list[str] = Field(default_factory=list)
    source_surface_evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    review_gate_results: list[dict[str, JsonValue]] = Field(default_factory=list)
    supersede_summary: list[dict[str, JsonValue]] = Field(default_factory=list)
    closeout_summary: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


DeliverableEvidence = EvidenceItem
DeliverableEvidencePack = EvidencePack


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


class ConvergenceAllowedGap(StrictModel):
    finding_id: str | None = None
    reason_code: str | None = None
    risk_disposition: str = Field(min_length=1)
    approver_ref: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    expires_at: datetime | None = None
    scope_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_gap_identity_and_boundary(self) -> "ConvergenceAllowedGap":
        finding_id = str(self.finding_id or "").strip()
        reason_code = str(self.reason_code or "").strip()
        if not finding_id and not reason_code:
            raise ValueError("Convergence allowed gaps require finding_id or reason_code.")
        if self.expires_at is None and not self.scope_refs:
            raise ValueError("Convergence allowed gaps require expires_at or scope_refs.")
        object.__setattr__(self, "finding_id", finding_id or None)
        object.__setattr__(self, "reason_code", reason_code or None)
        object.__setattr__(self, "scope_refs", _stable_unique_strings(self.scope_refs))
        return self


class ConvergencePolicy(StrictModel):
    policy_ref: str = Field(min_length=1)
    allow_failed_delivery_report: bool
    allowed_gaps: list[ConvergenceAllowedGap] = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CheckerContractGateResult(StrictModel):
    allowed: bool
    reason_code: str = Field(min_length=1)
    review_status: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    evaluation_fingerprint: str = Field(min_length=1)
    blocking_findings: list[ContractFinding] = Field(default_factory=list)
    blocking_finding_count: int = 0
    allowed_gap_refs: list[str] = Field(default_factory=list)
    requires_convergence_policy: bool = False
    policy_ref: str | None = None
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
    return sorted(
        {
            str(value).strip()
            for value in list(values or [])
            if value is not None and str(value).strip()
        }
    )


def _stable_dicts(values: list[Any] | None) -> list[dict[str, JsonValue]]:
    normalized: list[dict[str, JsonValue]] = []
    for value in list(values or []):
        if not isinstance(value, dict):
            continue
        item = _plain(value)
        if isinstance(item, dict) and item:
            normalized.append(item)
    return sorted(normalized, key=_stable_json)


def _asset_ref(value: dict[str, Any], fallback_prefix: str, index: int) -> str:
    for key in ("asset_ref", "ref", "scope_ref", "decision_ref", "design_ref", "backlog_ref"):
        candidate = str(value.get(key) or "").strip()
        if candidate:
            return candidate
    return f"{fallback_prefix}:{index}"


def _metadata_list(metadata: dict[str, JsonValue] | None, key: str) -> list[dict[str, Any]]:
    values = (metadata or {}).get(key)
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def _surface_id_from_refs(*refs: str) -> str:
    for ref in refs:
        normalized = str(ref or "").strip()
        if normalized:
            return f"surface.{_stable_hash({'ref': normalized}, length=10)}"
    return f"surface.{_stable_hash({'empty': True}, length=10)}"


def _capability_path_patterns(capabilities: list[str]) -> list[str]:
    patterns: list[str] = []
    for capability in capabilities:
        for pattern in CAPABILITY_WRITE_SURFACES.get(capability, ()):
            normalized = str(pattern).replace("{ticket_id}", "*")
            if normalized not in patterns:
                patterns.append(normalized)
    return sorted(patterns)


def _append_unique(target: list[str], values: list[Any] | tuple[Any, ...] | set[Any] | None) -> None:
    for value in _stable_unique_strings(values):
        if value not in target:
            target.append(value)


def _surface_bucket(
    surfaces: dict[str, dict[str, Any]],
    surface_id: str,
) -> dict[str, Any]:
    if surface_id not in surfaces:
        surfaces[surface_id] = {
            "surface_id": surface_id,
            "path_patterns": [],
            "owning_capabilities": [],
            "expected_behavior": "",
            "acceptance_criteria_refs": [],
            "required_evidence_kinds": [],
            "minimum_non_placeholder_evidence": [],
            "required_tests": [],
            "metadata": {
                "locked_scope_refs": [],
                "governance_decision_refs": [],
                "architecture_design_asset_refs": [],
                "backlog_recommendation_refs": [],
            },
        }
    return surfaces[surface_id]


def _merge_surface_payload(
    bucket: dict[str, Any],
    payload: dict[str, Any],
    *,
    metadata_ref_key: str | None = None,
    metadata_ref: str | None = None,
) -> None:
    _append_unique(
        bucket["acceptance_criteria_refs"],
        payload.get("acceptance_criteria_refs") or payload.get("acceptance_refs")
        if isinstance(payload.get("acceptance_criteria_refs") or payload.get("acceptance_refs"), list)
        else [],
    )
    capability_values: list[Any] = []
    for key in ("owning_capabilities", "required_capabilities"):
        value = payload.get(key)
        if isinstance(value, list):
            capability_values.extend(value)
    capability_values.append(payload.get("capability"))
    capabilities = _stable_unique_strings(capability_values)
    _append_unique(bucket["owning_capabilities"], capabilities)
    path_patterns = _stable_unique_strings(
        payload.get("path_patterns") or payload.get("paths")
        if isinstance(payload.get("path_patterns") or payload.get("paths"), list)
        else []
    )
    _append_unique(bucket["path_patterns"], path_patterns)
    _append_unique(bucket["path_patterns"], _capability_path_patterns(capabilities))
    _append_unique(
        bucket["required_evidence_kinds"],
        payload.get("required_evidence_kinds") or payload.get("required_evidence")
        if isinstance(payload.get("required_evidence_kinds") or payload.get("required_evidence"), list)
        else [],
    )
    _append_unique(
        bucket["minimum_non_placeholder_evidence"],
        payload.get("minimum_non_placeholder_evidence")
        if isinstance(payload.get("minimum_non_placeholder_evidence"), list)
        else [],
    )
    _append_unique(
        bucket["required_tests"],
        payload.get("required_tests") or payload.get("required_checks")
        if isinstance(payload.get("required_tests") or payload.get("required_checks"), list)
        else [],
    )
    expected_behavior = str(payload.get("expected_behavior") or payload.get("summary") or "").strip()
    if expected_behavior and not bucket["expected_behavior"]:
        bucket["expected_behavior"] = expected_behavior
    if metadata_ref_key and metadata_ref:
        metadata = bucket["metadata"]
        refs = metadata.setdefault(metadata_ref_key, [])
        if metadata_ref not in refs:
            refs.append(metadata_ref)


def _compile_required_source_surfaces_from_inputs(
    *,
    locked_scope: list[Any] | None,
    acceptance_criteria: list[AcceptanceCriterion],
    metadata: dict[str, JsonValue] | None,
) -> list[RequiredSourceSurface]:
    surfaces: dict[str, dict[str, Any]] = {}

    for index, value in enumerate(list(locked_scope or [])):
        if not isinstance(value, dict):
            continue
        surface_id = str(value.get("surface_id") or "").strip() or _surface_id_from_refs(
            str(value.get("scope_ref") or ""),
            str(value.get("ref") or ""),
        )
        bucket = _surface_bucket(surfaces, surface_id)
        _merge_surface_payload(
            bucket,
            value,
            metadata_ref_key="locked_scope_refs",
            metadata_ref=_asset_ref(value, "scope", index),
        )

    for key, ref_key, fallback in (
        ("governance_decisions", "governance_decision_refs", "decision"),
        ("architecture_design_assets", "architecture_design_asset_refs", "design"),
        ("backlog_recommendations", "backlog_recommendation_refs", "backlog"),
    ):
        for index, value in enumerate(_metadata_list(metadata, key)):
            surface_id = str(value.get("surface_id") or "").strip() or _surface_id_from_refs(
                str(value.get("asset_ref") or ""),
                str(value.get("ref") or ""),
            )
            bucket = _surface_bucket(surfaces, surface_id)
            _merge_surface_payload(
                bucket,
                value,
                metadata_ref_key=ref_key,
                metadata_ref=_asset_ref(value, fallback, index),
            )

    for value in _metadata_list(metadata, "allowed_write_set"):
        surface_id = str(value.get("surface_id") or "").strip() or _surface_id_from_refs(
            str(value.get("capability") or ""),
            str(value.get("path") or ""),
        )
        bucket = _surface_bucket(surfaces, surface_id)
        _merge_surface_payload(bucket, value)

    acceptance_ids = [item.criterion_id for item in acceptance_criteria]
    for bucket in surfaces.values():
        if not bucket["acceptance_criteria_refs"]:
            bucket["acceptance_criteria_refs"] = list(acceptance_ids)
        for key in (
            "path_patterns",
            "owning_capabilities",
            "acceptance_criteria_refs",
            "required_evidence_kinds",
            "minimum_non_placeholder_evidence",
            "required_tests",
        ):
            bucket[key] = _stable_unique_strings(bucket[key])
        for metadata_key, metadata_refs in list(bucket["metadata"].items()):
            bucket["metadata"][metadata_key] = _stable_unique_strings(metadata_refs)

    return [
        surface
        for surface in (_normalize_required_source_surface(value) for value in surfaces.values())
        if surface is not None
    ]


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
    compiled_surfaces = _compile_required_source_surfaces_from_inputs(
        locked_scope=locked_scope,
        acceptance_criteria=normalized_acceptance,
        metadata=metadata,
    )
    surfaces_by_id: dict[str, RequiredSourceSurface] = {}
    for surface in [*compiled_surfaces, *normalized_surfaces]:
        surfaces_by_id[surface.surface_id] = surface
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
            for item in sorted(surfaces_by_id.values(), key=lambda item: item.surface_id)
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


def _blocking_contract_findings(evaluation: DeliverableEvaluation) -> list[ContractFinding]:
    return [finding for finding in evaluation.findings if finding.blocking]


def _finding_scope_refs(finding: ContractFinding) -> set[str]:
    refs: set[str] = set()
    refs.update(finding.acceptance_criteria_refs)
    refs.update(finding.required_evidence_refs)
    refs.update(finding.source_surface_refs)
    return refs


def _allowed_gap_applies_to_finding(
    allowed_gap: ConvergenceAllowedGap,
    finding: ContractFinding,
    *,
    checked_at: datetime,
    scope_refs: set[str],
) -> bool:
    if allowed_gap.expires_at is not None:
        comparable_checked_at = checked_at
        comparable_expires_at = allowed_gap.expires_at
        if comparable_checked_at.tzinfo is None and comparable_expires_at.tzinfo is not None:
            comparable_checked_at = comparable_checked_at.replace(tzinfo=comparable_expires_at.tzinfo)
        elif comparable_checked_at.tzinfo is not None and comparable_expires_at.tzinfo is None:
            comparable_expires_at = comparable_expires_at.replace(tzinfo=comparable_checked_at.tzinfo)
        if comparable_checked_at > comparable_expires_at:
            return False
    if allowed_gap.finding_id is not None and allowed_gap.finding_id != finding.finding_id:
        return False
    if allowed_gap.reason_code is not None and allowed_gap.reason_code != finding.reason_code:
        return False
    if allowed_gap.scope_refs:
        finding_scopes = _finding_scope_refs(finding)
        finding_acceptance_scopes = set(finding.acceptance_criteria_refs)
        requested_scopes = scope_refs or finding_acceptance_scopes or finding_scopes
        allowed_scopes = set(allowed_gap.scope_refs)
        if not requested_scopes or not requested_scopes.issubset(allowed_scopes):
            return False
        if finding_acceptance_scopes and not finding_acceptance_scopes.issubset(allowed_scopes):
            return False
    return True


def _convergence_allowed_gap_for_finding(
    convergence_policy: ConvergencePolicy,
    finding: ContractFinding,
    *,
    checked_at: datetime,
    scope_refs: set[str],
) -> ConvergenceAllowedGap | None:
    for allowed_gap in convergence_policy.allowed_gaps:
        if _allowed_gap_applies_to_finding(
            allowed_gap,
            finding,
            checked_at=checked_at,
            scope_refs=scope_refs,
        ):
            return allowed_gap
    return None


def checker_contract_gate(
    *,
    evaluation: DeliverableEvaluation,
    review_status: str,
    convergence_policy: ConvergencePolicy | dict[str, Any] | None = None,
    failed_delivery_report: bool = False,
    scope_refs: list[str] | None = None,
    checked_at: datetime | None = None,
) -> CheckerContractGateResult:
    normalized_review_status = str(review_status or "").strip()
    blocking_findings = _blocking_contract_findings(evaluation)
    checked_at = checked_at or datetime.now().astimezone()
    resolved_policy = (
        ConvergencePolicy.model_validate(convergence_policy)
        if isinstance(convergence_policy, dict)
        else convergence_policy
    )
    policy_ref = resolved_policy.policy_ref if resolved_policy is not None else None

    if normalized_review_status not in APPROVED_CHECKER_REVIEW_STATUSES:
        return CheckerContractGateResult(
            allowed=False,
            reason_code="checker_verdict_not_approved",
            review_status=normalized_review_status or "UNKNOWN",
            contract_id=evaluation.contract_id,
            evaluation_fingerprint=evaluation.evaluation_fingerprint,
            blocking_findings=blocking_findings,
            blocking_finding_count=len(blocking_findings),
            requires_convergence_policy=False,
            policy_ref=policy_ref,
        )

    if not blocking_findings:
        return CheckerContractGateResult(
            allowed=True,
            reason_code="contract_satisfied",
            review_status=normalized_review_status,
            contract_id=evaluation.contract_id,
            evaluation_fingerprint=evaluation.evaluation_fingerprint,
            blocking_findings=[],
            blocking_finding_count=0,
            requires_convergence_policy=False,
            policy_ref=policy_ref,
        )

    if failed_delivery_report and (
        resolved_policy is None or not resolved_policy.allow_failed_delivery_report
    ):
        return CheckerContractGateResult(
            allowed=False,
            reason_code="convergence_policy_required",
            review_status=normalized_review_status,
            contract_id=evaluation.contract_id,
            evaluation_fingerprint=evaluation.evaluation_fingerprint,
            blocking_findings=blocking_findings,
            blocking_finding_count=len(blocking_findings),
            requires_convergence_policy=True,
            policy_ref=policy_ref,
        )

    allowed_gap_refs: list[str] = []
    remaining_findings: list[ContractFinding] = []
    requested_scope_refs = set(_stable_unique_strings(scope_refs))
    if resolved_policy is None:
        remaining_findings = list(blocking_findings)
    else:
        for finding in blocking_findings:
            allowed_gap = _convergence_allowed_gap_for_finding(
                resolved_policy,
                finding,
                checked_at=checked_at,
                scope_refs=requested_scope_refs,
            )
            if allowed_gap is None:
                remaining_findings.append(finding)
                continue
            allowed_gap_refs.append(finding.finding_id)

    if remaining_findings:
        return CheckerContractGateResult(
            allowed=False,
            reason_code="deliverable_contract_blocked",
            review_status=normalized_review_status,
            contract_id=evaluation.contract_id,
            evaluation_fingerprint=evaluation.evaluation_fingerprint,
            blocking_findings=remaining_findings,
            blocking_finding_count=len(remaining_findings),
            allowed_gap_refs=allowed_gap_refs,
            requires_convergence_policy=True,
            policy_ref=policy_ref,
        )

    return CheckerContractGateResult(
        allowed=True,
        reason_code="convergence_policy_allowed",
        review_status=normalized_review_status,
        contract_id=evaluation.contract_id,
        evaluation_fingerprint=evaluation.evaluation_fingerprint,
        blocking_findings=[],
        blocking_finding_count=0,
        allowed_gap_refs=allowed_gap_refs,
        requires_convergence_policy=False,
        policy_ref=policy_ref,
    )


def _normalized_evidence_legality_status(evidence: EvidenceItem) -> str:
    status = str(evidence.legality_status or "").strip().upper()
    if status:
        return status
    if evidence.placeholder:
        return EVIDENCE_LEGALITY_PLACEHOLDER
    if evidence.archive:
        return EVIDENCE_LEGALITY_ARCHIVE
    return EVIDENCE_LEGALITY_ACCEPTED


def _normalized_current_pointer_status(evidence: EvidenceItem) -> str:
    return str(evidence.current_pointer_status or CURRENT_POINTER_CURRENT).strip().upper()


def _evidence_ref_basename(evidence: EvidenceItem) -> str:
    return evidence.evidence_ref.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def _metadata_bool(evidence: EvidenceItem, *keys: str) -> bool:
    return any(bool(evidence.metadata.get(key)) for key in keys)


def _metadata_has_items(evidence: EvidenceItem, key: str) -> bool:
    value = evidence.metadata.get(key)
    return isinstance(value, list) and bool(value)


def _evidence_invalid_reasons(evidence: EvidenceItem) -> list[str]:
    reasons: list[str] = []
    legality_status = _normalized_evidence_legality_status(evidence)
    current_pointer_status = _normalized_current_pointer_status(evidence)
    if legality_status in _INVALID_EVIDENCE_LEGALITY_STATUSES:
        reasons.append(legality_status)
    if current_pointer_status in _INVALID_CURRENT_POINTER_STATUSES:
        pointer_reason = {
            "STALE": EVIDENCE_LEGALITY_STALE_CURRENT_POINTER,
            "UNKNOWN": EVIDENCE_LEGALITY_UNKNOWN_REF,
            EVIDENCE_LEGALITY_STALE_CURRENT_POINTER: EVIDENCE_LEGALITY_STALE_CURRENT_POINTER,
            EVIDENCE_LEGALITY_SUPERSEDED: EVIDENCE_LEGALITY_SUPERSEDED,
            EVIDENCE_LEGALITY_ARCHIVE: EVIDENCE_LEGALITY_ARCHIVE,
        }.get(current_pointer_status, current_pointer_status)
        if pointer_reason not in reasons:
            reasons.append(pointer_reason)
    if evidence.placeholder and EVIDENCE_LEGALITY_PLACEHOLDER not in reasons:
        reasons.append(EVIDENCE_LEGALITY_PLACEHOLDER)
    if evidence.archive and EVIDENCE_LEGALITY_ARCHIVE not in reasons:
        reasons.append(EVIDENCE_LEGALITY_ARCHIVE)
    if evidence.superseded_by_refs and EVIDENCE_LEGALITY_SUPERSEDED not in reasons:
        reasons.append(EVIDENCE_LEGALITY_SUPERSEDED)
    if _evidence_ref_basename(evidence) == "source.py" and EVIDENCE_LEGALITY_PLACEHOLDER not in reasons:
        reasons.append(EVIDENCE_LEGALITY_PLACEHOLDER)
    if (
        _metadata_bool(
            evidence,
            "stdout_fallback",
            "runtime_fallback_stdout",
            "provider_fallback",
            "no_business_assertions",
        )
        or _metadata_has_items(evidence, "placeholder_reasons")
    ) and EVIDENCE_LEGALITY_PLACEHOLDER not in reasons:
        reasons.append(EVIDENCE_LEGALITY_PLACEHOLDER)
    return sorted(reasons)


def _evidence_can_satisfy_contract(evidence: EvidenceItem) -> bool:
    return not _evidence_invalid_reasons(evidence)


def _contract_satisfying_evidence(evidence_pack: EvidencePack) -> list[EvidenceItem]:
    return [
        evidence
        for evidence in evidence_pack.evidence
        if _evidence_can_satisfy_contract(evidence)
    ]


def _required_evidence_is_satisfied(
    required: RequiredEvidence,
    evidence_pack: EvidencePack,
) -> bool:
    if not required.required:
        return True
    matching = [
        evidence
        for evidence in _contract_satisfying_evidence(evidence_pack)
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


def _required_evidence_for_surfaces(contract: DeliverableContract) -> list[RequiredEvidence]:
    required: list[RequiredEvidence] = []
    existing_keys = {
        (
            item.evidence_kind,
            tuple(item.acceptance_criteria_refs),
            tuple(item.source_surface_refs),
        )
        for item in contract.required_evidence
    }
    for surface in contract.required_source_surfaces:
        for evidence_kind in surface.required_evidence_kinds:
            key = (
                evidence_kind,
                tuple(surface.acceptance_criteria_refs),
                (surface.surface_id,),
            )
            if key in existing_keys:
                continue
            required.append(
                RequiredEvidence(
                    evidence_id=f"ev_{surface.surface_id}_{evidence_kind}_{_stable_hash(key, length=8)}",
                    evidence_kind=evidence_kind,
                    acceptance_criteria_refs=list(surface.acceptance_criteria_refs),
                    source_surface_refs=[surface.surface_id],
                )
            )
    return sorted(required, key=lambda item: item.evidence_id)


def _required_acceptance_surface_evidence(contract: DeliverableContract) -> dict[tuple[str, str], set[str]]:
    required: dict[tuple[str, str], set[str]] = {}
    for surface in contract.required_source_surfaces:
        for acceptance_ref in surface.acceptance_criteria_refs:
            key = (acceptance_ref, surface.surface_id)
            required.setdefault(key, set()).update(surface.required_evidence_kinds)
    return required


def _satisfied_evidence_kinds_for_acceptance_surface(
    *,
    evidence_pack: EvidencePack,
    acceptance_ref: str,
    surface_ref: str,
) -> set[str]:
    return {
        evidence.evidence_kind
        for evidence in _contract_satisfying_evidence(evidence_pack)
        if acceptance_ref in evidence.acceptance_criteria_refs
        and surface_ref in evidence.source_surface_refs
    }


def evaluate_deliverable_contract(
    contract: DeliverableContract,
    evidence_pack: EvidencePack,
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

    invalid_evidence = [
        evidence
        for evidence in evidence_pack.evidence
        if _evidence_invalid_reasons(evidence)
    ]
    if invalid_evidence:
        findings.append(
            _finding(
                reason_code="invalid_evidence_for_contract",
                summary="Evidence pack contains placeholder, superseded, archive, unknown, illegal, or stale-pointer evidence.",
                acceptance_criteria_refs=[
                    ref
                    for evidence in invalid_evidence
                    for ref in evidence.acceptance_criteria_refs
                ],
                evidence_refs=[evidence.evidence_ref for evidence in invalid_evidence],
                source_surface_refs=[
                    ref
                    for evidence in invalid_evidence
                    for ref in evidence.source_surface_refs
                ],
                metadata={
                    "invalid_statuses": _stable_unique_strings(
                        [
                            reason
                            for evidence in invalid_evidence
                            for reason in _evidence_invalid_reasons(evidence)
                        ]
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

    acceptance_surface_missing: list[dict[str, Any]] = []
    for (acceptance_ref, surface_ref), required_kinds in sorted(
        _required_acceptance_surface_evidence(contract).items()
    ):
        satisfied_kinds = _satisfied_evidence_kinds_for_acceptance_surface(
            evidence_pack=evidence_pack,
            acceptance_ref=acceptance_ref,
            surface_ref=surface_ref,
        )
        missing_kinds = sorted(required_kinds.difference(satisfied_kinds))
        if missing_kinds:
            acceptance_surface_missing.append(
                {
                    "acceptance_ref": acceptance_ref,
                    "surface_ref": surface_ref,
                    "missing_evidence_kinds": missing_kinds,
                }
            )
    if acceptance_surface_missing:
        findings.append(
            _finding(
                reason_code="acceptance_missing_required_evidence",
                summary="Critical acceptance criteria are missing required source, test, check, git, or closeout evidence.",
                acceptance_criteria_refs=[
                    item["acceptance_ref"] for item in acceptance_surface_missing
                ],
                source_surface_refs=[
                    item["surface_ref"] for item in acceptance_surface_missing
                ],
                metadata={
                    "missing_by_acceptance_surface": acceptance_surface_missing,
                    "missing_evidence_kinds": _stable_unique_strings(
                        [
                            kind
                            for item in acceptance_surface_missing
                            for kind in item["missing_evidence_kinds"]
                        ]
                    ),
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
        required_evidence_count=len(contract.required_evidence) + len(_required_evidence_for_surfaces(contract)),
        final_evidence_ref_count=len(evidence_pack.final_evidence_refs),
    )
