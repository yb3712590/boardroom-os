from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerNote,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictStatus,
    SourceDiffRef,
)
from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    EvidenceClaim,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
    FallbackLineageMarker,
)
from boardroom_os.evidence.fallback_registry import (
    FallbackDecisionRecord,
    evaluate_fallback_claim,
)
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
    FinalEvidenceTableRef,
)
from boardroom_os.evidence.verifier import (
    ArtifactSha256,
    FallbackDecisionRecordedRef,
    VerifiedArtifact,
    VerifiedEvidence,
    VerifiedEvidenceRef,
)
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose, FallbackKind, FallbackPolicy
from boardroom_os.execution.package import FallbackPolicyRef
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId, TicketStatus
from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError
from boardroom_os.reducers.errors import TicketReducerError
from boardroom_os.reducers.ticket_reducer import (
    TicketCheckSnapshot,
    TicketCompletionSnapshot,
    TicketReducer,
    TicketReducerPayloadResolver,
    TicketRefPayload,
)

_VERIFY_ERRORS = (ValueError, ValidationError)
_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_GENERATED_AT = datetime(2026, 5, 22, 9, 0, tzinfo=UTC)
_CHECKED_AT = datetime(2026, 5, 22, 9, 30, tzinfo=UTC)


def _ticket_ref(value: str = "ticket.backend") -> TicketId:
    return TicketId(value=value)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _provider_attempt_ref(value: str = "provider-attempt.backend") -> ProviderAttemptRef:
    return ProviderAttemptRef(value=value)


def _work_product_ref(value: str = "work-product.backend") -> WorkProductRef:
    return WorkProductRef(value=value)


def _criterion(
    acceptance_ref: str = "AC-BACKEND",
    *,
    statement: str | None = None,
    required_artifact_type: str = "source_patch",
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement=statement or f"{acceptance_ref} must have verified evidence.",
        evidence_required=(EvidenceRequirement(value=required_artifact_type),),
        blocking=True,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="aggregate verified evidence"),
    )


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.completion-gate"),
        source_type="natural_language",
        content_ref=ContractId(value="content.completion-gate"),
        received_at=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.completion-gate"),
        board_directive_ref=ContractId(value="directive.completion-gate"),
        project_goal="Complete tickets only after verified evidence and checker approval.",
        delivery_type="generated_project_package",
        non_goals=("Do not rewrite the ticket reducer.",),
        constraints=("Completion gate must fail closed.",),
        risks=("Checker approval could bypass evidence if not gated.",),
        success_summary="A reducer-safe completion snapshot is generated from formal evidence.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    *,
    acceptance_contract_id: ContractId | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=acceptance_contract_id
        or ContractId(value="contract.acceptance.completion-gate"),
        project_charter_ref=ContractId(value="project.charter.completion-gate"),
        status={"value": "active"},
        criteria=criteria or (_criterion(),),
    )


def _verified_artifact(
    *,
    artifact_ref: str = "artifact.backend",
    producer_attempt_ref: ProviderAttemptRef | None = None,
    source_ref: str = "work-product.backend",
) -> VerifiedArtifact:
    return VerifiedArtifact(
        artifact_ref=EvidenceArtifactRef(value=artifact_ref),
        sha256=ArtifactSha256(value=_VALID_SHA256),
        producer_attempt_ref=producer_attempt_ref or _provider_attempt_ref(),
        source_ref=source_ref,
        artifact_kind="source_patch",
    )


def _verified_evidence(
    *,
    verified_evidence_id: str = "verified-evidence.backend",
    evidence_claim_ref: str | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    source_ref: str = "work-product.backend",
) -> VerifiedEvidence:
    resolved_attempt_ref = producer_attempt_ref or _provider_attempt_ref()
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=verified_evidence_id),
        evidence_claim_ref=EvidenceClaimRef(value=evidence_claim_ref or f"claim.{verified_evidence_id}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence.backend"),
        producer_attempt_ref=resolved_attempt_ref,
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref=source_ref,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        acceptance_refs=acceptance_refs or (_acceptance_ref(),),
        source_surface_refs=(_source_surface_ref(),),
        verified_artifacts=(
            _verified_artifact(
                producer_attempt_ref=resolved_attempt_ref,
                source_ref=source_ref,
            ),
        ),
        verified_at=datetime(2026, 5, 22, 9, 15, tzinfo=UTC),
    )


def _final_evidence_table(
    *,
    contract: AcceptanceContract | None = None,
    verified_evidence: tuple[VerifiedEvidence, ...] | None = None,
    failed_blockers: tuple[FinalEvidenceBlocker, ...] = (),
) -> FinalEvidenceTable:
    return FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=contract or _acceptance_contract(),
            verified_evidence=verified_evidence
            if verified_evidence is not None
            else (_verified_evidence(),),
            failed_blockers=failed_blockers,
            generated_at=_GENERATED_AT,
        )
    )


def _checker_verdict(
    *,
    ticket_ref: TicketId | None = None,
    work_product_ref: WorkProductRef | None = None,
    table: FinalEvidenceTable | None = None,
    acceptance_contract_ref: ContractId | None = None,
    status: CheckerVerdictStatus = CheckerVerdictStatus.APPROVED,
    notes: tuple[CheckerNote, ...] = (),
    blockers: tuple[CheckerVerdictBlocker, ...] = (),
) -> CheckerVerdict:
    resolved_table = table or _final_evidence_table()
    return CheckerVerdict(
        ticket_ref=ticket_ref or _ticket_ref(),
        work_product_ref=work_product_ref or _work_product_ref(),
        source_diff_ref=SourceDiffRef(value="source-diff.backend"),
        acceptance_contract_ref=acceptance_contract_ref or resolved_table.acceptance_contract_ref,
        final_evidence_table_ref=resolved_table.final_evidence_table_id,
        status=status,
        notes=notes,
        blockers=blockers,
        checked_at=_CHECKED_AT,
    )


def _checker_note() -> CheckerNote:
    return CheckerNote(
        message="Checker approved with non-blocking note.",
        related_ref="source-diff.backend",
    )


def _checker_blocker() -> CheckerVerdictBlocker:
    return CheckerVerdictBlocker(
        code=CheckerBlockerCode.CHECKER_BLOCKER,
        message="Source diff does not match evidence.",
        acceptance_ref=_acceptance_ref(),
        related_ref="source-diff.backend",
        source="checker",
    )


def _gate_input(**overrides: object) -> "CompletionGateInput":
    from boardroom_os.reducers.completion_gate import CompletionGateInput

    evidence = _verified_evidence()
    table = _final_evidence_table(verified_evidence=(evidence,))
    fields: dict[str, object] = {
        "ticket_ref": _ticket_ref(),
        "final_evidence_table": table,
        "checker_verdict": _checker_verdict(table=table),
        "verified_evidence": (evidence,),
        "provider_attempt_refs": (_provider_attempt_ref(),),
        "work_product_submitted_refs": (_work_product_ref(),),
        "fallback_decision_records": (),
    }
    fields.update(overrides)
    return CompletionGateInput(**fields)


def test_gate_input_requires_typed_final_evidence_table() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGateInput

    valid_input = _gate_input().model_dump()
    valid_input["final_evidence_table"] = {"complete": True}

    with pytest.raises(_VERIFY_ERRORS, match="final_evidence_table"):
        CompletionGateInput(**valid_input)


def test_gate_rejects_incomplete_final_evidence_table() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    evidence = _verified_evidence(acceptance_refs=(_acceptance_ref("AC-BACKEND"),))
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-FRONTEND", statement="Frontend must have verified evidence."),
        )
    )
    table = _final_evidence_table(contract=contract, verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="complete"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
            )
        )


def test_gate_rejects_failed_final_evidence_row() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    blocker = FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Evidence verification failed.",
        acceptance_ref=_acceptance_ref(),
        related_ref="evidence-blocker.backend",
        source="evidence_verifier",
    )
    table = _final_evidence_table(verified_evidence=(), failed_blockers=(blocker,))

    with pytest.raises(CompletionGateError, match="satisfied"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(),
            )
        )


def test_gate_rejects_missing_final_evidence_row() -> None:
    missing_row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="Backend acceptance must have evidence.",
        status=FinalEvidenceStatus.MISSING,
        verified_evidence_refs=(),
        missing_required_artifact_types=(RequiredArtifactType(value="source_patch"),),
    )
    table = FinalEvidenceTable(
        final_evidence_table_id=FinalEvidenceTableRef(
            value="final-evidence-table.contract.acceptance.completion-gate"
        ),
        acceptance_contract_ref=ContractId(value="contract.acceptance.completion-gate"),
        generated_at=_GENERATED_AT,
        rows=(missing_row,),
    )

    with pytest.raises(CompletionGateError, match="complete"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(),
            )
        )


def test_gate_rejects_duplicate_provider_attempt_refs() -> None:
    provider_attempt_ref = _provider_attempt_ref()

    with pytest.raises(CompletionGateError, match="unique"):
        CompletionGate().build_completion_snapshot(
            _gate_input(provider_attempt_refs=(provider_attempt_ref, provider_attempt_ref))
        )


def test_gate_rejects_checker_rework_or_escalate_verdicts() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    table = _final_evidence_table()

    for status in (
        CheckerVerdictStatus.REWORK_REQUIRED,
        CheckerVerdictStatus.ESCALATE,
    ):
        with pytest.raises(CompletionGateError, match="checker"):
            CompletionGate().build_completion_snapshot(
                _gate_input(
                    final_evidence_table=table,
                    checker_verdict=_checker_verdict(
                        table=table,
                        status=status,
                        blockers=(_checker_blocker(),),
                    ),
                )
            )


def test_gate_rejects_checker_blockers_even_if_status_is_approved() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    table = _final_evidence_table()
    verdict = _checker_verdict(table=table).model_copy(
        update={"blockers": (_checker_blocker(),)}
    )

    with pytest.raises(CompletionGateError, match="blockers"):
        CompletionGate().build_completion_snapshot(_gate_input(checker_verdict=verdict))


def test_gate_rejects_empty_provider_attempt_refs() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    with pytest.raises(CompletionGateError, match="provider attempt"):
        CompletionGate().build_completion_snapshot(
            _gate_input(provider_attempt_refs=())
        )


def test_gate_rejects_verified_evidence_attempt_missing_from_provider_attempt_refs() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    evidence = _verified_evidence(
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.other")
    )
    table = _final_evidence_table(verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="producer_attempt_ref"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
                provider_attempt_refs=(_provider_attempt_ref(),),
            )
        )


def test_gate_rejects_missing_submitted_work_product_ref() -> None:
    from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateError

    with pytest.raises(CompletionGateError, match="work product"):
        CompletionGate().build_completion_snapshot(
            _gate_input(work_product_submitted_refs=(WorkProductRef(value="work-product.other"),))
        )


def _fallback_policy() -> FallbackPolicy:
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
        kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
        allowed_acceptance_refs=(_acceptance_ref("AC-HASH-MANIFEST"),),
    )


def _fallback_claim(
    *,
    evidence_claim_id: str = "claim.fallback.hash-manifest",
    expected_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    required_artifact_type: RequiredArtifactType | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
) -> EvidenceClaim:
    resolved_attempt_ref = producer_attempt_ref or _provider_attempt_ref("provider-attempt.fallback")
    return EvidenceClaim(
        evidence_claim_id=EvidenceClaimRef(value=evidence_claim_id),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence.hash-manifest"),
        producer_attempt_ref=resolved_attempt_ref,
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.backend",
        expected_purpose=expected_purpose,
        required_artifact_type=required_artifact_type or RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=acceptance_refs or (_acceptance_ref("AC-HASH-MANIFEST"),),
        source_surface_refs=(_source_surface_ref(),),
        artifact_refs=(EvidenceArtifactRef(value="artifact.hash-manifest"),),
        fallback_marker=FallbackLineageMarker(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
            fallback_kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
            producer_attempt_ref=resolved_attempt_ref,
        ),
        summary="Fallback hash manifest claim.",
    )


def _fallback_decision_record(
    *,
    claim: EvidenceClaim | None = None,
) -> FallbackDecisionRecord:
    from boardroom_os.evidence.fallback_registry import FallbackPolicyRegistry

    return evaluate_fallback_claim(
        claim=claim or _fallback_claim(),
        registry=FallbackPolicyRegistry(policies=(_fallback_policy(),)),
        evaluated_at=_GENERATED_AT,
    )


def _fallback_verified_evidence(
    *,
    claim: EvidenceClaim | None = None,
    decision_record: FallbackDecisionRecord | None = None,
    recorded_ref: FallbackDecisionRecordedRef | None = None,
) -> VerifiedEvidence:
    resolved_claim = claim or _fallback_claim()
    resolved_record = decision_record or _fallback_decision_record(claim=resolved_claim)
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value="verified-evidence.fallback.hash-manifest"),
        evidence_claim_ref=resolved_claim.evidence_claim_id,
        evidence_obligation_ref=resolved_claim.evidence_obligation_ref,
        producer_attempt_ref=resolved_claim.producer_attempt_ref,
        source_kind=resolved_claim.source_kind,
        source_ref=resolved_claim.source_ref,
        expected_purpose=resolved_claim.expected_purpose,
        required_artifact_type=resolved_claim.required_artifact_type,
        acceptance_refs=resolved_claim.acceptance_refs,
        source_surface_refs=resolved_claim.source_surface_refs,
        verified_artifacts=(
            _verified_artifact(
                artifact_ref="artifact.hash-manifest",
                producer_attempt_ref=resolved_claim.producer_attempt_ref,
                source_ref=resolved_claim.source_ref,
            ),
        ),
        fallback_decision_record_ref=resolved_record.fallback_decision_record_id,
        fallback_decision_recorded_ref=recorded_ref
        or FallbackDecisionRecordedRef(value="event:fallback-decision-recorded.hash-manifest"),
        verified_at=datetime(2026, 5, 22, 9, 15, tzinfo=UTC),
    )


def _fallback_contract(*, required_artifact_type: str = "hash_manifest") -> AcceptanceContract:
    return _acceptance_contract(
        criteria=(
            _criterion(
                "AC-HASH-MANIFEST",
                statement="Hash manifest deterministic evidence is recorded.",
                required_artifact_type=required_artifact_type,
            ),
        )
    )


def test_gate_rejects_fallback_evidence_without_recorded_lineage_ref() -> None:
    claim = _fallback_claim()
    record = _fallback_decision_record(claim=claim)
    evidence = _fallback_verified_evidence(
        claim=claim,
        decision_record=record,
        recorded_ref=FallbackDecisionRecordedRef(value="event:fallback-decision-recorded.hash-manifest"),
    ).model_copy(update={"fallback_decision_recorded_ref": None})
    table = _final_evidence_table(contract=_fallback_contract(), verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="FALLBACK_DECISION_RECORDED|fallback"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
                provider_attempt_refs=(claim.producer_attempt_ref,),
                fallback_decision_records=(record,),
            )
        )


def test_gate_rejects_fallback_evidence_without_decision_record() -> None:
    claim = _fallback_claim()
    record = _fallback_decision_record(claim=claim)
    evidence = _fallback_verified_evidence(claim=claim, decision_record=record)
    table = _final_evidence_table(contract=_fallback_contract(), verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="decision record"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
                provider_attempt_refs=(claim.producer_attempt_ref,),
                fallback_decision_records=(),
            )
        )


def test_gate_rejects_fallback_decision_allowed_false() -> None:
    claim = _fallback_claim(expected_purpose=EvidencePurpose.IMPLEMENTATION)
    record = _fallback_decision_record(claim=claim)
    assert record.decision.allowed is False
    evidence = _fallback_verified_evidence(claim=claim, decision_record=record)
    table = _final_evidence_table(contract=_fallback_contract(), verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="allowed"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
                provider_attempt_refs=(claim.producer_attempt_ref,),
                fallback_decision_records=(record,),
            )
        )


def test_gate_rejects_fallback_decision_record_acceptance_refs_mismatch() -> None:
    claim = _fallback_claim()
    record = _fallback_decision_record(claim=claim).model_copy(
        update={"acceptance_refs": (_acceptance_ref("AC-OTHER"),)}
    )
    evidence = _fallback_verified_evidence(claim=claim, decision_record=record)
    table = _final_evidence_table(contract=_fallback_contract(), verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="acceptance_refs|fallback"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
                provider_attempt_refs=(claim.producer_attempt_ref,),
                fallback_decision_records=(record,),
            )
        )


@pytest.mark.parametrize(
    ("evidence_update", "provider_attempt_refs", "expected_message"),
    (
        (
            {"evidence_claim_ref": EvidenceClaimRef(value="claim.other")},
            None,
            "evidence_claim_ref",
        ),
        (
            {"producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.other")},
            (ProviderAttemptRef(value="provider-attempt.other"),),
            "producer_attempt_ref",
        ),
        (
            {"required_artifact_type": RequiredArtifactType(value="other_artifact")},
            None,
            "required_artifact_type",
        ),
        (
            {"expected_purpose": EvidencePurpose.IMPLEMENTATION},
            None,
            "evaluated_purpose",
        ),
    ),
)
def test_gate_rejects_fallback_decision_record_scope_mismatches(
    evidence_update: dict[str, object],
    provider_attempt_refs: tuple[ProviderAttemptRef, ...] | None,
    expected_message: str,
) -> None:
    claim = _fallback_claim()
    record = _fallback_decision_record(claim=claim)
    evidence = _fallback_verified_evidence(claim=claim, decision_record=record).model_copy(
        update=evidence_update
    )
    table = _final_evidence_table(
        contract=_fallback_contract(
            required_artifact_type=evidence.required_artifact_type.value
        ),
        verified_evidence=(evidence,),
    )

    with pytest.raises(CompletionGateError, match=expected_message):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
                provider_attempt_refs=provider_attempt_refs or (claim.producer_attempt_ref,),
                fallback_decision_records=(record,),
            )
        )


def test_gate_rejects_primary_evidence_with_fallback_recorded_ref() -> None:
    evidence = _verified_evidence().model_copy(
        update={
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="event:fallback-decision-recorded.unexpected"
            )
        }
    )
    table = _final_evidence_table(verified_evidence=(evidence,))

    with pytest.raises(CompletionGateError, match="primary evidence"):
        CompletionGate().build_completion_snapshot(
            _gate_input(
                final_evidence_table=table,
                checker_verdict=_checker_verdict(table=table),
                verified_evidence=(evidence,),
            )
        )


@pytest.mark.parametrize(
    ("verdict_updates", "expected_message"),
    (
        ({"ticket_ref": _ticket_ref("ticket.other")}, "ticket_ref"),
        (
            {
                "final_evidence_table_ref": FinalEvidenceTableRef(
                    value="final-evidence-table.contract.acceptance.other"
                )
            },
            "final_evidence_table_ref",
        ),
        (
            {"acceptance_contract_ref": ContractId(value="contract.acceptance.other")},
            "acceptance_contract_ref",
        ),
    ),
)
def test_gate_rejects_checker_verdict_reference_mismatches(
    verdict_updates: dict[str, object],
    expected_message: str,
) -> None:
    table = _final_evidence_table()
    verdict = _checker_verdict(table=table).model_copy(update=verdict_updates)

    with pytest.raises(CompletionGateError, match=expected_message):
        CompletionGate().build_completion_snapshot(
            _gate_input(final_evidence_table=table, checker_verdict=verdict)
        )


def test_gate_rejects_unreferenced_fallback_decision_records() -> None:
    record = _fallback_decision_record()

    with pytest.raises(CompletionGateError, match="unreferenced"):
        CompletionGate().build_completion_snapshot(
            _gate_input(fallback_decision_records=(record,))
        )


def test_gate_builds_completion_snapshot_for_primary_verified_evidence() -> None:
    gate_input = _gate_input()
    result = CompletionGate().build_completion_snapshot(gate_input)

    assert result.provider_attempt_count == 1
    assert result.completion_snapshot == TicketCompletionSnapshot(
        ticket_id=_ticket_ref(),
        provider_attempt_count=1,
        evidence_complete=True,
        checker_approved=True,
        blocking_issue_refs=(),
    )
    assert result.final_evidence_table_ref == gate_input.final_evidence_table.final_evidence_table_id
    assert result.checker_verdict_ref == gate_input.checker_verdict.checker_verdict_id
    assert result.verified_evidence_refs == (VerifiedEvidenceRef(value="verified-evidence.backend"),)
    assert result.fallback_decision_record_refs == ()


def test_gate_allows_checker_approved_with_non_blocking_notes() -> None:
    table = _final_evidence_table()
    result = CompletionGate().build_completion_snapshot(
        _gate_input(
            final_evidence_table=table,
            checker_verdict=_checker_verdict(
                table=table,
                status=CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
                notes=(_checker_note(),),
            ),
        )
    )

    assert result.completion_snapshot.checker_approved is True
    assert result.completion_snapshot.blocking_issue_refs == ()


def test_gate_allows_allowed_deterministic_fallback_lineage() -> None:
    claim = _fallback_claim()
    record = _fallback_decision_record(claim=claim)
    evidence = _fallback_verified_evidence(claim=claim, decision_record=record)
    table = _final_evidence_table(contract=_fallback_contract(), verified_evidence=(evidence,))

    result = CompletionGate().build_completion_snapshot(
        _gate_input(
            final_evidence_table=table,
            checker_verdict=_checker_verdict(table=table),
            verified_evidence=(evidence,),
            provider_attempt_refs=(claim.producer_attempt_ref,),
            fallback_decision_records=(record,),
        )
    )

    assert result.provider_attempt_count == 1
    assert result.fallback_decision_record_refs == (record.fallback_decision_record_id,)
    assert result.completion_snapshot.evidence_complete is True


class InMemoryCompletionPayloadResolver(TicketReducerPayloadResolver):
    def __init__(
        self,
        *,
        created_payloads: dict[str, TicketCreatedPayload],
        ticket_refs: dict[str, TicketRefPayload] | None = None,
        completion_snapshots: dict[str, TicketCompletionSnapshot] | None = None,
    ) -> None:
        self._created_payloads = created_payloads
        self._ticket_refs = ticket_refs or {}
        self._completion_snapshots = completion_snapshots or {}

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self._created_payloads[payload_ref.value]

    def resolve_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        return self._ticket_refs[payload_ref.value]

    def resolve_work_product_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        return self._ticket_refs[payload_ref.value]

    def resolve_ticket_check(self, payload_ref: EventPayloadRef) -> TicketCheckSnapshot:
        raise KeyError(payload_ref.value)

    def resolve_ticket_completion(self, payload_ref: EventPayloadRef) -> TicketCompletionSnapshot:
        return self._completion_snapshots[payload_ref.value]


def _created_payload() -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=_ticket_ref(),
        purpose="Implement backend API surface",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
        depends_on=(),
        acceptance_refs=("AC-BACKEND",),
        source_surface_refs=("surface.backend",),
        evidence_obligations=("evidence.backend",),
        allowed_read_refs=("contract:completion-gate",),
        allowed_write_set=("10-project/backend/**",),
        attempt_count=0,
    )


def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value="project.completion-gate"),
        actor_ref=ActorRef(value=actor_ref),
        timestamp=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _created_event() -> EventRecord:
    return _event(
        event_id="evt.ticket.created",
        event_type=EventType.TICKET_CREATED,
        payload_ref="payload.ticket.created",
        graph_version=1,
        actor_ref="seat-architect",
    )


def _work_product_event() -> EventRecord:
    return _event(
        event_id="evt.work-product.submitted",
        event_type=EventType.WORK_PRODUCT_SUBMITTED,
        payload_ref="payload.work-product.submitted",
        graph_version=2,
        actor_ref="seat-worker",
    )


def _completed_event(graph_version: int = 3) -> EventRecord:
    return _event(
        event_id="evt.ticket.completed",
        event_type=EventType.TICKET_COMPLETED,
        payload_ref="payload.ticket.completed",
        graph_version=graph_version,
        actor_ref="seat-checker",
    )


def test_reducer_still_rejects_completion_without_work_product_history_after_gate_passes() -> None:
    gate_result = CompletionGate().build_completion_snapshot(_gate_input())
    resolver = InMemoryCompletionPayloadResolver(
        created_payloads={"payload.ticket.created": _created_payload()},
        completion_snapshots={"payload.ticket.completed": gate_result.completion_snapshot},
    )

    with pytest.raises(TicketReducerError, match="work product"):
        TicketReducer(resolver).reduce((_created_event(), _completed_event(graph_version=2)))


def test_ticket_reducer_completes_ticket_with_gate_snapshot_and_work_product_history() -> None:
    gate_result = CompletionGate().build_completion_snapshot(_gate_input())
    resolver = InMemoryCompletionPayloadResolver(
        created_payloads={"payload.ticket.created": _created_payload()},
        ticket_refs={"payload.work-product.submitted": TicketRefPayload(ticket_id=_ticket_ref())},
        completion_snapshots={"payload.ticket.completed": gate_result.completion_snapshot},
    )

    graph = TicketReducer(resolver).reduce(
        (
            _created_event(),
            _work_product_event(),
            _completed_event(graph_version=3),
        )
    )

    assert graph.graph_version == 3
    assert graph.nodes[_ticket_ref()].status is TicketStatus.COMPLETED
    assert graph.completed_nodes == (_ticket_ref(),)
