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
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
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
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType

_VERIFY_ERRORS = (ValueError, ValidationError)
_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_GENERATED_AT = datetime(2026, 5, 21, 9, 30, tzinfo=UTC)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _criterion(
    acceptance_ref: str = "AC-BACKEND",
    *,
    blocking: bool = True,
    evidence_required: tuple[str, ...] = ("source_patch",),
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement=f"{acceptance_ref} must have verified evidence.",
        evidence_required=tuple(
            EvidenceRequirement(value=artifact_type)
            for artifact_type in evidence_required
        ),
        blocking=blocking,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="aggregate verified evidence"),
    )


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.final-evidence"),
        source_type="natural_language",
        content_ref=ContractId(value="content.final-evidence"),
        received_at=datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.final-evidence"),
        board_directive_ref=ContractId(value="directive.final-evidence"),
        project_goal="Aggregate verified evidence into a final evidence table.",
        delivery_type="generated_project_package",
        non_goals=("Do not verify raw claims in the table builder.",),
        constraints=("Final evidence table must fail closed.",),
        risks=("Missing evidence must not reach closeout.",),
        success_summary="Every blocking criterion has verified evidence.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    *,
    status: ContractStatus | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="contract.acceptance.final-evidence"),
        project_charter_ref=ContractId(value="project.charter.final-evidence"),
        status=status or ContractStatus.active(),
        criteria=criteria or (_criterion(),),
    )


def _verified_evidence(
    *,
    verified_evidence_id: str = "verified-evidence.backend",
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    required_artifact_type: str = "source_patch",
) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=verified_evidence_id),
        evidence_claim_ref=EvidenceClaimRef(value=f"claim.{verified_evidence_id}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence.backend"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.backend",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
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
        verified_at=datetime(2026, 5, 21, 9, 10, tzinfo=UTC),
    )


def _blocker(
    acceptance_ref: str = "AC-BACKEND",
    *,
    related_ref: str = "evidence-blocker.backend",
):
    from boardroom_os.evidence.table import (
        FinalEvidenceBlocker,
        FinalEvidenceBlockerCode,
    )

    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Verified evidence failed before final aggregation.",
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        related_ref=related_ref,
        source="evidence_verifier",
    )


def _build_table(**overrides: object):
    from boardroom_os.evidence.table import FinalEvidenceTableBuilder, FinalEvidenceTableInput

    fields = {
        "active_acceptance_contract": _acceptance_contract(),
        "verified_evidence": (_verified_evidence(),),
        "failed_blockers": (),
        "generated_at": _GENERATED_AT,
    }
    fields.update(overrides)
    return FinalEvidenceTableBuilder().build(FinalEvidenceTableInput(**fields))


def test_final_evidence_table_rejects_inactive_acceptance_contract() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="active"):
        _build_table(active_acceptance_contract=_acceptance_contract(status=ContractStatus.draft()))


def test_final_evidence_table_rejects_empty_acceptance_map() -> None:
    valid_contract = _acceptance_contract()
    contract_fields = {
        field_name: getattr(valid_contract, field_name)
        for field_name in AcceptanceContract.model_fields
    }
    contract_fields.update(
        {
            "status": ContractStatus.active(),
            "criteria": (_criterion("AC-OPTIONAL", blocking=False),),
        }
    )
    contract_without_blocking_criteria = AcceptanceContract.model_construct(**contract_fields)

    with pytest.raises(_VERIFY_ERRORS, match="acceptance map|blocking"):
        _build_table(active_acceptance_contract=contract_without_blocking_criteria)


def test_final_evidence_table_marks_blocking_criterion_missing() -> None:
    table = _build_table(verified_evidence=())

    assert table.complete is False
    assert len(table.rows) == 1
    assert table.rows[0].status.value == "missing"
    assert table.rows[0].verified_evidence_refs == ()
    assert table.rows[0].missing_required_artifact_types == (
        RequiredArtifactType(value="source_patch"),
    )
    assert table.rows[0].blockers == ()


def test_final_evidence_table_keeps_row_missing_until_all_required_artifact_types_exist() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion(
                "AC-BACKEND",
                evidence_required=("source_patch", "command_evidence"),
            ),
        )
    )

    table = _build_table(
        active_acceptance_contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend-source",
                required_artifact_type="source_patch",
            ),
        ),
    )

    assert table.complete is False
    assert table.rows[0].status.value == "missing"
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend-source"),
    )
    assert table.rows[0].missing_required_artifact_types == (
        RequiredArtifactType(value="command_evidence"),
    )


def test_final_evidence_table_rejects_unknown_verified_evidence_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="unknown acceptance_ref"):
        _build_table(
            verified_evidence=(
                _verified_evidence(acceptance_refs=(AcceptanceRef(value="AC-UNKNOWN"),)),
            )
        )


def test_final_evidence_table_rejects_unknown_failed_blocker_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="failed blocker acceptance_ref"):
        _build_table(failed_blockers=(_blocker("AC-UNKNOWN"),))


def test_final_evidence_table_rejects_notes_input() -> None:
    from boardroom_os.evidence.table import FinalEvidenceTableInput

    with pytest.raises(_VERIFY_ERRORS, match="notes|extra"):
        FinalEvidenceTableInput(
            active_acceptance_contract=_acceptance_contract(),
            verified_evidence=(_verified_evidence(),),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
            notes=("human accepted risk",),
        )


def test_verified_evidence_cannot_clear_failed_evidence_blocker() -> None:
    table = _build_table(failed_blockers=(_blocker(),))

    assert table.complete is False
    assert table.rows[0].status.value == "failed"
    assert tuple(ref.value for ref in table.rows[0].verified_evidence_refs) == (
        "verified-evidence.backend",
    )
    assert table.rows[0].blockers == (_blocker(),)


def test_complete_table_cannot_contain_missing_rows() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.MISSING,
        verified_evidence_refs=(),
        missing_required_artifact_types=(RequiredArtifactType(value="source_patch"),),
        blockers=(),
    )
    with pytest.raises(_VERIFY_ERRORS, match="complete"):
        FinalEvidenceTable(
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row,),
            complete=True,
        )


def test_complete_table_cannot_contain_failed_rows() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.FAILED,
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        blockers=(_blocker(),),
    )
    with pytest.raises(_VERIFY_ERRORS, match="complete"):
        FinalEvidenceTable(
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row,),
            complete=True,
        )


def test_final_evidence_row_rejects_satisfied_without_verified_evidence_refs() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus

    with pytest.raises(_VERIFY_ERRORS, match="satisfied"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.SATISFIED,
            verified_evidence_refs=(),
            blockers=(),
        )


def test_final_evidence_row_rejects_satisfied_with_blockers() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus

    with pytest.raises(_VERIFY_ERRORS, match="satisfied"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.SATISFIED,
            verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
            blockers=(_blocker(),),
        )


def test_final_evidence_row_rejects_failed_without_blockers() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus

    with pytest.raises(_VERIFY_ERRORS, match="failed"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.FAILED,
            verified_evidence_refs=(),
            blockers=(),
        )


def test_final_evidence_table_rejects_duplicate_acceptance_rows() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.SATISFIED,
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        blockers=(),
    )
    with pytest.raises(_VERIFY_ERRORS, match="unique"):
        FinalEvidenceTable(
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row, row),
            complete=True,
        )


def test_final_evidence_table_rejects_claim_dict_as_verified_evidence() -> None:
    from boardroom_os.evidence.table import FinalEvidenceTableInput

    with pytest.raises(_VERIFY_ERRORS, match="VerifiedEvidence"):
        FinalEvidenceTableInput(
            active_acceptance_contract=_acceptance_contract(),
            verified_evidence=(
                {"evidence_claim_id": {"value": "claim.fake"}},
            ),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
        )


def test_final_evidence_table_rejects_verification_result_input() -> None:
    from boardroom_os.evidence.table import FinalEvidenceTableInput

    blocker = EvidenceVerificationBlocker(
        code=EvidenceVerificationBlockerCode.MISSING_ARTIFACT,
        message="claim artifact_ref is missing from artifact manifest",
        related_ref="artifact.missing",
    )
    with pytest.raises(_VERIFY_ERRORS, match="VerifiedEvidence"):
        FinalEvidenceTableInput(
            active_acceptance_contract=_acceptance_contract(),
            verified_evidence=(EvidenceVerificationResult(blockers=(blocker,)),),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
        )


def test_final_evidence_table_rejects_non_deterministic_table_id() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable, FinalEvidenceTableRef

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.SATISFIED,
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        blockers=(),
    )
    with pytest.raises(_VERIFY_ERRORS, match="final-evidence-table"):
        FinalEvidenceTable(
            final_evidence_table_id=FinalEvidenceTableRef(value="final-evidence-table.custom"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row,),
            complete=True,
        )
