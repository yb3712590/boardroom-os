from pydantic import BaseModel, ConfigDict, field_serializer

from boardroom_os.contracts.acceptance import AcceptanceContract, AcceptanceCriterion
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef


class ContractGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptance_contract_ref: ContractId
    package_contract_ref: ContractId
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    evidence_obligations: tuple[EvidenceObligation, ...]

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(
        self,
        values: tuple[AcceptanceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("source_surface_refs")
    def _serialize_source_surface_refs(
        self,
        values: tuple[SourceSurfaceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("evidence_obligations")
    def _serialize_evidence_obligations(
        self,
        values: tuple[EvidenceObligation, ...],
    ) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]


def compile_evidence_obligations(
    acceptance_contract: AcceptanceContract,
) -> tuple[EvidenceObligation, ...]:
    obligations: list[EvidenceObligation] = []
    for criterion in acceptance_contract.blocking_criteria():
        obligations.extend(_obligations_for_criterion(criterion))
    return tuple(obligations)


def validate_contract_gate(
    *,
    acceptance_contract: AcceptanceContract | None,
    package_contract: PackageContract | None,
    evidence_obligations: tuple[EvidenceObligation, ...] | None = None,
) -> ContractGateResult:
    if acceptance_contract is None or acceptance_contract.status.value != "active":
        raise ValueError("active acceptance contract is required")
    if package_contract is None:
        raise ValueError("package contract is required")

    _validate_package_acceptance_refs_belong_to_active_contract(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
    )
    _validate_criterion_source_surfaces_belong_to_package_contract(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
    )

    expected_obligations = compile_evidence_obligations(acceptance_contract)
    compiled_obligations = evidence_obligations
    if compiled_obligations is None:
        compiled_obligations = expected_obligations
    _validate_blocking_criteria_have_blocking_obligations(
        acceptance_contract=acceptance_contract,
        evidence_obligations=compiled_obligations,
    )
    if compiled_obligations != expected_obligations:
        raise ValueError("evidence obligations must match active contract")

    return ContractGateResult(
        acceptance_contract_ref=acceptance_contract.acceptance_contract_id,
        package_contract_ref=package_contract.package_contract_id,
        acceptance_refs=_blocking_acceptance_refs(acceptance_contract),
        source_surface_refs=_blocking_source_surface_refs(acceptance_contract),
        evidence_obligations=compiled_obligations,
    )


def _obligations_for_criterion(
    criterion: AcceptanceCriterion,
) -> tuple[EvidenceObligation, ...]:
    return tuple(
        EvidenceObligation(
            evidence_obligation_id=EvidenceObligationRef(
                value=f"obl-{criterion.acceptance_ref.value}-{requirement.value}"
            ),
            acceptance_refs=(criterion.acceptance_ref,),
            source_surface_refs=criterion.source_surface_refs,
            required_artifact_type=RequiredArtifactType(value=requirement.value),
            required_verifier=RequiredVerifier(value=criterion.verification_strategy.value),
            blocking=True,
        )
        for requirement in criterion.evidence_required
    )


def _blocking_acceptance_refs(
    acceptance_contract: AcceptanceContract,
) -> tuple[AcceptanceRef, ...]:
    return tuple(criterion.acceptance_ref for criterion in acceptance_contract.blocking_criteria())


def _blocking_source_surface_refs(
    acceptance_contract: AcceptanceContract,
) -> tuple[SourceSurfaceRef, ...]:
    refs: list[SourceSurfaceRef] = []
    seen: set[str] = set()
    for criterion in acceptance_contract.blocking_criteria():
        for source_surface_ref in criterion.source_surface_refs:
            if source_surface_ref.value not in seen:
                refs.append(source_surface_ref)
                seen.add(source_surface_ref.value)
    return tuple(refs)


def _validate_package_acceptance_refs_belong_to_active_contract(
    *,
    acceptance_contract: AcceptanceContract,
    package_contract: PackageContract,
) -> None:
    active_refs = {criterion.acceptance_ref.value for criterion in acceptance_contract.criteria}
    for surface in package_contract.source_surfaces:
        for acceptance_ref in surface.acceptance_refs:
            if acceptance_ref.value not in active_refs:
                raise ValueError("acceptance_ref must belong to active contract")


def _validate_criterion_source_surfaces_belong_to_package_contract(
    *,
    acceptance_contract: AcceptanceContract,
    package_contract: PackageContract,
) -> None:
    package_surface_refs = {
        surface.source_surface_ref.value
        for surface in package_contract.source_surfaces
    }
    for criterion in acceptance_contract.blocking_criteria():
        for source_surface_ref in criterion.source_surface_refs:
            if source_surface_ref.value not in package_surface_refs:
                raise ValueError("source_surface_ref must belong to package contract")


def _validate_blocking_criteria_have_blocking_obligations(
    *,
    acceptance_contract: AcceptanceContract,
    evidence_obligations: tuple[EvidenceObligation, ...],
) -> None:
    obligation_acceptance_refs = {
        acceptance_ref.value
        for obligation in evidence_obligations
        if obligation.blocking
        for acceptance_ref in obligation.acceptance_refs
    }
    for criterion in acceptance_contract.blocking_criteria():
        if criterion.acceptance_ref.value not in obligation_acceptance_refs:
            raise ValueError("blocking criterion requires blocking obligation")
