from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import (
    ArtifactSha256,
    EvidenceVerificationBlocker,
    EvidenceVerificationBlockerCode,
    EvidenceVerificationResult,
    VerifiedArtifact,
    VerifiedEvidence,
    VerifiedEvidenceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.execution.work_product import (
    WorkProduct,
    WorkProductArtifactRef,
    WorkProductClaimDraftRef,
    WorkProductRef,
)
from boardroom_os.graph.ticket import TicketId

_VERIFY_ERRORS = (ValueError, ValidationError)
_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_CHECKED_AT = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
_GENERATED_AT = datetime(2026, 5, 21, 11, 30, tzinfo=UTC)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _criterion(
    acceptance_ref: str = "AC-BACKEND",
    *,
    statement: str | None = None,
    blocking: bool = True,
    required_artifact_type: str = "source_patch",
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement=statement or f"{acceptance_ref} must have verified evidence.",
        evidence_required=(EvidenceRequirement(value=required_artifact_type),),
        blocking=blocking,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="aggregate verified evidence"),
    )


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.checker-verdict"),
        source_type="natural_language",
        content_ref=ContractId(value="content.checker-verdict"),
        received_at=datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.checker-verdict"),
        board_directive_ref=ContractId(value="directive.checker-verdict"),
        project_goal="Review worker output without replacing evidence verification.",
        delivery_type="generated_project_package",
        non_goals=("Do not generate rework tickets in V2-050D.",),
        constraints=("Checker notes must not clear blockers.",),
        risks=("Checker could accidentally become another verifier.",),
        success_summary="Checker emits an auditable verdict from existing evidence facts.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    *,
    acceptance_contract_id: ContractId | None = None,
    status: ContractStatus | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=acceptance_contract_id
        or ContractId(value="contract.acceptance.checker-verdict"),
        project_charter_ref=ContractId(value="project.charter.checker-verdict"),
        status=status or ContractStatus.active(),
        criteria=criteria or (_criterion(),),
    )


def _verified_evidence(
    *,
    verified_evidence_id: str = "verified-evidence.backend",
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=verified_evidence_id),
        evidence_claim_ref=EvidenceClaimRef(value=f"claim.{verified_evidence_id}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence.backend"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.backend",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        acceptance_refs=acceptance_refs or (_acceptance_ref(),),
        source_surface_refs=(_source_surface_ref(),),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value="artifact.backend"),
                sha256=ArtifactSha256(value=_VALID_SHA256),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
                source_ref="work-product.backend",
                artifact_kind="source_patch",
            ),
        ),
        verified_at=datetime(2026, 5, 21, 11, 0, tzinfo=UTC),
    )


def _work_product(**overrides: object) -> WorkProduct:
    fields: dict[str, object] = {
        "work_product_id": WorkProductRef(value="work-product.backend"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.backend"),
        "ticket_ref": TicketId(value="ticket.backend"),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
        "artifact_refs": (
            WorkProductArtifactRef(value="artifact.backend.raw"),
            WorkProductArtifactRef(value="artifact.backend.parsed"),
        ),
        "claim_refs": (WorkProductClaimDraftRef(value="claim-draft.backend"),),
        "summary": "Backend work product.",
    }
    fields.update(overrides)
    return WorkProduct(**fields)


def _final_evidence_blocker(acceptance_ref: str = "AC-BACKEND") -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Evidence verification failed.",
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        related_ref="evidence-blocker.backend",
        source="evidence_verifier",
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


def _missing_final_evidence_table() -> FinalEvidenceTable:
    return _final_evidence_table(verified_evidence=())


def _failed_final_evidence_table() -> FinalEvidenceTable:
    return _final_evidence_table(verified_evidence=(), failed_blockers=(_final_evidence_blocker(),))


def _checker_note():
    from boardroom_os.checker.verdict import CheckerNote

    return CheckerNote(
        message="Implementation is acceptable; consider renaming a local variable later.",
        related_ref="work-product.backend",
    )


def _checker_blocker():
    from boardroom_os.checker.verdict import CheckerBlockerCode, CheckerVerdictBlocker

    return CheckerVerdictBlocker(
        code=CheckerBlockerCode.CHECKER_BLOCKER,
        message="Source diff does not match the work product summary.",
        acceptance_ref=None,
        related_ref="source-diff.backend",
        source="checker_manual_review",
    )


def _service_input(**overrides: object):
    from boardroom_os.checker.checker import CheckerServiceInput
    from boardroom_os.checker.verdict import SourceDiffRef

    fields = {
        "ticket_ref": TicketId(value="ticket.backend"),
        "work_product": _work_product(),
        "source_diff_ref": SourceDiffRef(value="source-diff.backend"),
        "active_acceptance_contract": _acceptance_contract(),
        "final_evidence_table": _final_evidence_table(),
        "notes": (),
        "checker_blockers": (),
        "checked_at": _CHECKED_AT,
    }
    fields.update(overrides)
    return CheckerServiceInput(**fields)


def _review(**overrides: object):
    from boardroom_os.checker.checker import CheckerService

    return CheckerService().review(_service_input(**overrides))


# Negative tests first.


def test_checker_service_rejects_inactive_acceptance_contract() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="active"):
        _service_input(active_acceptance_contract=_acceptance_contract(status=ContractStatus.draft()))


def test_checker_service_rejects_contract_mismatch() -> None:
    other_contract = _acceptance_contract(
        acceptance_contract_id=ContractId(value="contract.acceptance.other"),
        criteria=(_criterion("AC-FRONTEND", statement="Frontend evidence is complete."),),
    )
    with pytest.raises(_VERIFY_ERRORS, match="contract"):
        _service_input(active_acceptance_contract=other_contract)


def test_checker_service_rejects_work_product_ticket_mismatch() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="ticket"):
        _service_input(work_product=_work_product(ticket_ref=TicketId(value="ticket.other")))


def test_checker_service_rejects_acceptance_contract_dict() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="AcceptanceContract|active_acceptance_contract"):
        _service_input(active_acceptance_contract={"acceptance_contract_id": "contract.acceptance.fake"})


def test_checker_service_rejects_final_evidence_table_dict() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="FinalEvidenceTable|final_evidence_table"):
        _service_input(final_evidence_table={"final_evidence_table_id": "final-evidence-table.fake"})


def test_checker_service_rejects_work_product_dict() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="WorkProduct|work_product"):
        _service_input(work_product={"work_product_id": "work-product.fake"})


def test_checker_service_rejects_missing_source_diff_ref() -> None:
    from boardroom_os.checker.verdict import SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="empty|source_diff"):
        _service_input(source_diff_ref=SourceDiffRef(value=""))


def test_checker_service_rejects_source_diff_ref_dict() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="SourceDiffRef|source_diff_ref"):
        _service_input(source_diff_ref={"value": "source-diff.backend"})


def test_checker_service_rejects_evidence_claim_inputs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|evidence_claims"):
        _service_input(evidence_claims=("claim.fake",))


def test_checker_service_rejects_verified_evidence_inputs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|verified_evidence"):
        _service_input(verified_evidence=(_verified_evidence(),))


def test_checker_service_rejects_verification_result_inputs() -> None:
    blocker = EvidenceVerificationBlocker(
        code=EvidenceVerificationBlockerCode.MISSING_ARTIFACT,
        message="claim artifact_ref is missing from artifact manifest",
        related_ref="artifact.missing",
    )
    with pytest.raises(_VERIFY_ERRORS, match="extra|evidence_verification_results"):
        _service_input(evidence_verification_results=(EvidenceVerificationResult(blockers=(blocker,)),))


def test_checker_service_rejects_final_evidence_blocker_inputs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|final_evidence_blockers"):
        _service_input(final_evidence_blockers=(_final_evidence_blocker(),))


def test_checker_service_rejects_force_approved_override() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|force_approved"):
        _service_input(force_approved=True)


def test_checker_service_rejects_acceptance_override() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|acceptance_override"):
        _service_input(acceptance_override=(AcceptanceRef(value="AC-OVERRIDE"),))


def test_checker_service_rejects_constructed_empty_source_diff_ref() -> None:
    from boardroom_os.checker.verdict import SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="source_diff_ref|empty"):
        _service_input(source_diff_ref=SourceDiffRef.model_construct(value=""))


def test_checker_service_rejects_constructed_work_product_without_artifacts() -> None:
    malformed_work_product = _work_product().model_copy(update={"artifact_refs": ()})

    with pytest.raises(_VERIFY_ERRORS, match="artifact_refs"):
        _service_input(work_product=malformed_work_product)


def test_checker_service_rejects_constructed_work_product_without_claims() -> None:
    malformed_work_product = _work_product().model_copy(update={"claim_refs": ()})

    with pytest.raises(_VERIFY_ERRORS, match="claim_refs"):
        _service_input(work_product=malformed_work_product)


def test_checker_service_rejects_constructed_incomplete_table_with_satisfied_rows() -> None:
    malformed_table = _final_evidence_table().model_copy(update={"complete": False})

    with pytest.raises(_VERIFY_ERRORS, match="complete"):
        _service_input(final_evidence_table=malformed_table)


def test_checker_service_rejects_constructed_failed_row_without_blockers() -> None:
    table = _final_evidence_table()
    malformed_row = table.rows[0].model_copy(
        update={"status": FinalEvidenceStatus.FAILED, "blockers": ()}
    )
    malformed_table = table.model_copy(
        update={"rows": (malformed_row,), "complete": False}
    )

    with pytest.raises(_VERIFY_ERRORS, match="failed|blockers"):
        _service_input(final_evidence_table=malformed_table)


def test_checker_service_rejects_constructed_row_with_non_enum_status() -> None:
    table = _final_evidence_table()
    malformed_row = table.rows[0].model_copy(update={"status": "satisfied"})
    malformed_table = table.model_copy(
        update={"rows": (malformed_row,), "complete": False}
    )

    with pytest.raises(_VERIFY_ERRORS, match="status"):
        _service_input(final_evidence_table=malformed_table)


def test_checker_service_rejects_constructed_row_outside_acceptance_contract() -> None:
    table = _final_evidence_table()
    malformed_row = table.rows[0].model_copy(
        update={"acceptance_ref": AcceptanceRef(value="AC-OTHER")}
    )
    malformed_table = table.model_copy(update={"rows": (malformed_row,)})

    with pytest.raises(_VERIFY_ERRORS, match="acceptance"):
        _service_input(final_evidence_table=malformed_table)


def test_checker_review_rejects_copied_input_with_non_enum_row_status() -> None:
    from boardroom_os.checker.checker import CheckerService

    checker_input = _service_input()
    malformed_row = checker_input.final_evidence_table.rows[0].model_copy(
        update={"status": "satisfied"}
    )
    malformed_table = checker_input.final_evidence_table.model_copy(
        update={"rows": (malformed_row,), "complete": False}
    )
    malformed_input = checker_input.model_copy(update={"final_evidence_table": malformed_table})

    with pytest.raises(_VERIFY_ERRORS, match="status"):
        CheckerService().review(malformed_input)


def test_checker_review_rejects_copied_input_with_outside_acceptance_ref() -> None:
    from boardroom_os.checker.checker import CheckerService

    checker_input = _service_input()
    malformed_row = checker_input.final_evidence_table.rows[0].model_copy(
        update={"acceptance_ref": AcceptanceRef(value="AC-OTHER")}
    )
    malformed_table = checker_input.final_evidence_table.model_copy(
        update={"rows": (malformed_row,)}
    )
    malformed_input = checker_input.model_copy(update={"final_evidence_table": malformed_table})

    with pytest.raises(_VERIFY_ERRORS, match="acceptance"):
        CheckerService().review(malformed_input)


def test_incomplete_final_evidence_table_cannot_be_approved() -> None:
    verdict = _review(final_evidence_table=_missing_final_evidence_table())

    assert verdict.status.value == "rework_required"
    assert verdict.blockers


def test_missing_evidence_row_becomes_rework_blocker() -> None:
    verdict = _review(final_evidence_table=_missing_final_evidence_table())

    assert tuple(blocker.code.value for blocker in verdict.blockers) == ("final_evidence_missing",)
    assert verdict.blockers[0].acceptance_ref == AcceptanceRef(value="AC-BACKEND")


def test_failed_evidence_row_becomes_rework_blocker() -> None:
    verdict = _review(final_evidence_table=_failed_final_evidence_table())

    assert tuple(blocker.code.value for blocker in verdict.blockers) == ("final_evidence_failed",)
    assert verdict.blockers[0].acceptance_ref == AcceptanceRef(value="AC-BACKEND")
    assert verdict.blockers[0].related_ref == _final_evidence_blocker().blocker_id.value


def test_notes_cannot_clear_evidence_blocker() -> None:
    verdict = _review(final_evidence_table=_failed_final_evidence_table(), notes=(_checker_note(),))

    assert verdict.status.value == "rework_required"
    assert verdict.notes == (_checker_note(),)
    assert verdict.blockers


def test_checker_blocker_forces_rework_even_when_evidence_complete() -> None:
    verdict = _review(checker_blockers=(_checker_blocker(),))

    assert verdict.status.value == "rework_required"
    assert verdict.blockers == (_checker_blocker(),)


def test_approved_verdict_rejects_notes() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="approved"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(_checker_note(),),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_approved_verdict_rejects_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="approved"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(_checker_blocker(),),
            checked_at=_CHECKED_AT,
        )


def test_approved_with_notes_requires_notes() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="notes"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_approved_with_notes_rejects_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
            notes=(_checker_note(),),
            blockers=(_checker_blocker(),),
            checked_at=_CHECKED_AT,
        )


def test_rework_required_requires_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.REWORK_REQUIRED,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_escalate_requires_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.ESCALATE,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_checker_verdict_rejects_non_deterministic_id() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictRef, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="checker-verdict"):
        CheckerVerdict(
            checker_verdict_id=CheckerVerdictRef(value="checker-verdict.custom"),
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_checker_verdict_rejects_naive_checked_at() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="timezone"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(),
            checked_at=datetime(2026, 5, 21, 12, 0),
        )


def test_checker_note_rejects_missing_related_ref() -> None:
    from boardroom_os.checker.verdict import CheckerNote

    with pytest.raises(_VERIFY_ERRORS, match="Field required|field required|related_ref"):
        CheckerNote(message="Implementation is acceptable; add more context.")


def test_checker_note_rejects_override_fields() -> None:
    from boardroom_os.checker.verdict import CheckerNote

    with pytest.raises(_VERIFY_ERRORS, match="extra|override|blocking"):
        CheckerNote(
            message="Looks fine despite the blocker.",
            related_ref="work-product.backend",
            blocking=False,
            evidence_refs=("verified-evidence.fake",),
        )


def test_checker_blocker_rejects_empty_related_ref() -> None:
    from boardroom_os.checker.verdict import CheckerBlockerCode, CheckerVerdictBlocker

    with pytest.raises(_VERIFY_ERRORS, match="empty|related_ref"):
        CheckerVerdictBlocker(
            code=CheckerBlockerCode.CHECKER_BLOCKER,
            message="Blocking issue.",
            acceptance_ref=None,
            related_ref="",
            source="checker_manual_review",
        )


def test_checker_verdict_rejects_extra_evidence_refs() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="extra|evidence_refs"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
            evidence_refs=("verified-evidence.fake",),
        )


# Happy path tests.


def test_checker_service_approves_complete_evidence_without_notes() -> None:
    verdict = _review()

    assert verdict.status.value == "approved"
    assert verdict.notes == ()
    assert verdict.blockers == ()
    assert verdict.ticket_ref == TicketId(value="ticket.backend")
    assert verdict.work_product_ref == WorkProductRef(value="work-product.backend")
    assert verdict.acceptance_contract_ref == ContractId(value="contract.acceptance.checker-verdict")
    assert verdict.final_evidence_table_ref == _final_evidence_table().final_evidence_table_id


def test_checker_service_approves_complete_evidence_with_non_blocking_notes() -> None:
    verdict = _review(notes=(_checker_note(),))

    assert verdict.status.value == "approved_with_non_blocking_notes"
    assert verdict.notes == (_checker_note(),)
    assert verdict.blockers == ()


def test_checker_verdict_json_is_audit_friendly() -> None:
    verdict = _review(notes=(_checker_note(),))
    payload = verdict.model_dump(mode="json")

    assert payload == {
        "version": 1,
        "checker_verdict_id": {
            "value": "checker-verdict.ticket.backend.final-evidence-table.contract.acceptance.checker-verdict"
        },
        "ticket_ref": {"value": "ticket.backend"},
        "work_product_ref": {"value": "work-product.backend"},
        "source_diff_ref": {"value": "source-diff.backend"},
        "acceptance_contract_ref": {"value": "contract.acceptance.checker-verdict"},
        "final_evidence_table_ref": {
            "value": "final-evidence-table.contract.acceptance.checker-verdict"
        },
        "status": "approved_with_non_blocking_notes",
        "notes": [
            {
                "note_id": {"value": "checker-note.work-product.backend"},
                "message": "Implementation is acceptable; consider renaming a local variable later.",
                "related_ref": "work-product.backend",
            }
        ],
        "blockers": [],
        "checked_at": "2026-05-21T12:00:00Z",
    }
