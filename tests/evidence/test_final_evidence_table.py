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
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    EvidenceNamespaceRef,
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
    FinalEvidenceTableRef,
)
from boardroom_os.evidence.verifier import (
    ArtifactSha256,
    VerifiedArtifact,
    VerifiedEvidence,
    VerifiedEvidenceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose

_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_GENERATED_AT = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
_VERIFY_ERRORS = (ValueError, ValidationError)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _criterion(
    acceptance_ref: str = "AC-BACKEND",
    *,
    statement: str | None = None,
    blocking: bool = True,
    evidence_required: tuple[str, ...] = ("source_patch",),
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement=statement or f"{acceptance_ref} must have verified evidence.",
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
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="contract.acceptance.final-evidence"),
        project_charter_ref=ContractId(value="project.charter.final-evidence"),
        status={"value": "active"},
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
        verified_at=datetime(2026, 5, 21, 9, 45, tzinfo=UTC),
    )


def _blocker(acceptance_ref: str = "AC-BACKEND") -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Verifier produced a blocker for this acceptance ref.",
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        related_ref="evidence-blocker.backend",
        source="evidence_verifier",
    )


def _build_table(
    *,
    contract: AcceptanceContract | None = None,
    verified_evidence: tuple[VerifiedEvidence, ...] | None = None,
    failed_blockers: tuple[FinalEvidenceBlocker, ...] = (),
):
    return FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=contract or _acceptance_contract(),
            verified_evidence=verified_evidence if verified_evidence is not None else (_verified_evidence(),),
            failed_blockers=failed_blockers,
            generated_at=_GENERATED_AT,
        )
    )


def test_final_evidence_row_rejects_duplicate_verified_evidence_refs() -> None:
    duplicate_ref = VerifiedEvidenceRef(value="verified-evidence.backend")

    with pytest.raises(_VERIFY_ERRORS, match="duplicate|unique"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.SATISFIED,
            verified_evidence_refs=(duplicate_ref, duplicate_ref),
            blockers=(),
        )


def test_builder_rejects_duplicate_verified_evidence_refs_in_same_row() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="duplicate|unique"):
        _build_table(
            verified_evidence=(
                _verified_evidence(verified_evidence_id="verified-evidence.backend"),
                _verified_evidence(verified_evidence_id="verified-evidence.backend"),
            )
        )


def test_non_blocking_criterion_does_not_generate_row_or_affect_complete() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion(
                "AC-OPTIONAL",
                statement="Optional evidence is available for audit only.",
                blocking=False,
            ),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(acceptance_refs=(_acceptance_ref("AC-BACKEND"),)),
            _verified_evidence(
                verified_evidence_id="verified-evidence.optional",
                acceptance_refs=(_acceptance_ref("AC-OPTIONAL"),),
            ),
        ),
    )

    assert table.complete is True
    assert tuple(row.acceptance_ref.value for row in table.rows) == ("AC-BACKEND",)
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend"),
    )


def test_non_blocking_evidence_does_not_satisfy_blocking_row() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion(
                "AC-OPTIONAL",
                statement="Optional evidence is available for audit only.",
                blocking=False,
            ),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.optional",
                acceptance_refs=(_acceptance_ref("AC-OPTIONAL"),),
            ),
        ),
    )

    assert table.complete is False
    assert tuple(row.acceptance_ref.value for row in table.rows) == ("AC-BACKEND",)
    assert table.rows[0].status is FinalEvidenceStatus.MISSING
    assert table.rows[0].verified_evidence_refs == ()


def test_missing_required_artifact_type_keeps_blocking_row_missing() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion(
                "AC-BACKEND",
                evidence_required=("source_patch", "command_evidence"),
            ),
        )
    )

    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend-source",
                required_artifact_type="source_patch",
            ),
        ),
    )

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.MISSING
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend-source"),
    )
    assert table.rows[0].missing_required_artifact_types == (
        RequiredArtifactType(value="command_evidence"),
    )


def test_all_required_artifact_types_satisfy_blocking_row() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion(
                "AC-BACKEND",
                evidence_required=("source_patch", "command_evidence"),
            ),
        )
    )

    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend-source",
                required_artifact_type="source_patch",
            ),
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend-command",
                required_artifact_type="command_evidence",
            ),
        ),
    )

    assert table.complete is True
    assert table.rows[0].status is FinalEvidenceStatus.SATISFIED
    assert table.rows[0].missing_required_artifact_types == ()


def test_failed_evidence_table_serializes_blocker_audit_shape() -> None:
    table = _build_table(verified_evidence=(), failed_blockers=(_blocker(),))

    assert table.model_dump(mode="json") == {
        "version": 1,
        "final_evidence_table_id": {
            "value": "final-evidence-table.contract.acceptance.final-evidence"
        },
        "acceptance_contract_ref": {"value": "contract.acceptance.final-evidence"},
        "generated_at": "2026-05-21T10:00:00Z",
        "rows": [
            {
                "acceptance_ref": {"value": "AC-BACKEND"},
                "statement": "AC-BACKEND must have verified evidence.",
                "status": "failed",
                "verified_evidence_refs": [],
                "missing_required_artifact_types": [{"value": "source_patch"}],
                "blockers": [
                    {
                        "blocker_id": {
                            "value": "final-evidence-blocker.failed_evidence.AC-BACKEND.evidence-blocker.backend"
                        },
                        "code": "failed_evidence",
                        "message": "Verifier produced a blocker for this acceptance ref.",
                        "acceptance_ref": {"value": "AC-BACKEND"},
                        "related_ref": "evidence-blocker.backend",
                        "source": "evidence_verifier",
                    }
                ],
            }
        ],
        "complete": False,
    }


def test_single_blocking_criterion_is_satisfied_by_verified_evidence() -> None:
    table = _build_table()

    assert table.complete is True
    assert table.final_evidence_table_id == FinalEvidenceTableRef(
        value="final-evidence-table.contract.acceptance.final-evidence"
    )
    assert table.rows[0].acceptance_ref == _acceptance_ref()
    assert table.rows[0].status is FinalEvidenceStatus.SATISFIED
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend"),
    )
    assert table.rows[0].blockers == ()


def test_multiple_blocking_criteria_are_all_satisfied() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-FRONTEND", statement="Frontend has verified evidence."),
            _criterion("AC-COMMAND", statement="Commands have verified evidence."),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend",
                acceptance_refs=(_acceptance_ref("AC-BACKEND"),),
            ),
            _verified_evidence(
                verified_evidence_id="verified-evidence.frontend",
                acceptance_refs=(_acceptance_ref("AC-FRONTEND"),),
            ),
            _verified_evidence(
                verified_evidence_id="verified-evidence.command",
                acceptance_refs=(_acceptance_ref("AC-COMMAND"),),
            ),
        ),
    )

    assert table.complete is True
    assert tuple(row.acceptance_ref.value for row in table.rows) == (
        "AC-BACKEND",
        "AC-FRONTEND",
        "AC-COMMAND",
    )
    assert all(row.status is FinalEvidenceStatus.SATISFIED for row in table.rows)


def test_verified_evidence_can_cover_multiple_acceptance_refs() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-COMMAND", statement="Commands have verified evidence."),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend-and-command",
                acceptance_refs=(
                    _acceptance_ref("AC-BACKEND"),
                    _acceptance_ref("AC-COMMAND"),
                ),
            ),
        ),
    )

    assert table.complete is True
    assert tuple(row.verified_evidence_refs for row in table.rows) == (
        (VerifiedEvidenceRef(value="verified-evidence.backend-and-command"),),
        (VerifiedEvidenceRef(value="verified-evidence.backend-and-command"),),
    )


def test_missing_criterion_produces_incomplete_table() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-FRONTEND", statement="Frontend has verified evidence."),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(acceptance_refs=(_acceptance_ref("AC-BACKEND"),)),
        ),
    )

    assert table.complete is False
    statuses = {row.acceptance_ref.value: row.status for row in table.rows}
    assert statuses == {
        "AC-BACKEND": FinalEvidenceStatus.SATISFIED,
        "AC-FRONTEND": FinalEvidenceStatus.MISSING,
    }


def test_failed_evidence_produces_incomplete_table() -> None:
    table = _build_table(verified_evidence=(), failed_blockers=(_blocker(),))

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.FAILED
    assert table.rows[0].blockers == (_blocker(),)


def test_verified_evidence_and_failed_blocker_preserve_audit_refs() -> None:
    table = _build_table(failed_blockers=(_blocker(),))

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.FAILED
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend"),
    )
    assert table.rows[0].blockers == (_blocker(),)


def test_final_evidence_table_serializes_as_audit_friendly_json() -> None:
    table = _build_table()

    assert table.model_dump(mode="json") == {
        "version": 1,
        "final_evidence_table_id": {
            "value": "final-evidence-table.contract.acceptance.final-evidence"
        },
        "acceptance_contract_ref": {"value": "contract.acceptance.final-evidence"},
        "generated_at": "2026-05-21T10:00:00Z",
        "rows": [
            {
                "acceptance_ref": {"value": "AC-BACKEND"},
                "statement": "AC-BACKEND must have verified evidence.",
                "status": "satisfied",
                "verified_evidence_refs": [{"value": "verified-evidence.backend"}],
                "missing_required_artifact_types": [],
                "blockers": [],
            }
        ],
        "complete": True,
    }


def test_complete_is_derived_from_rows() -> None:
    table = _build_table(verified_evidence=())

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.MISSING


def test_final_evidence_table_uses_deterministic_contract_id() -> None:
    table = _build_table()

    assert table.final_evidence_table_id.value == (
        "final-evidence-table.contract.acceptance.final-evidence"
    )


def test_final_evidence_table_can_be_namespaced_for_rework_round() -> None:
    contract = _acceptance_contract()
    evidence = _verified_evidence(acceptance_refs=(_acceptance_ref(),))
    namespace = EvidenceNamespaceRef(
        value="rework-evidence.run-v2-100d.rework-cycle.v2-100d.rework-attempt.v2-100d.1.g42"
    )

    table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=contract,
            verified_evidence=(evidence,),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
            evidence_namespace_ref=namespace,
        )
    )

    assert table.evidence_namespace_ref == namespace
    assert table.final_evidence_table_id.value == (
        f"final-evidence-table.{contract.acceptance_contract_id.value}.{namespace.value}"
    )
