from dataclasses import dataclass
from typing import Mapping

from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.gates import (
    ContractGateResult,
    compile_evidence_obligations,
)
from boardroom_os.contracts.methodology import MethodologyProfile
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.project import ProjectCharter
from tests.fixtures.contracts.tiny_fullstack_contract import (
    build_tiny_fullstack_contract_fixture,
)

REQUIRED_ACCEPTANCE_REFS_BY_CATEGORY: Mapping[str, tuple[str, ...]] = {
    "api": (
        "AC-TINY-API-BOOK-CREATE",
        "AC-TINY-API-BOOK-LIST",
        "AC-TINY-API-CHECKOUT-RETURN",
        "AC-TINY-API-BOOK-DELETE",
    ),
    "ui": ("AC-TINY-UI-FETCH-BACKEND",),
    "persistence": ("AC-TINY-PERSISTENCE-SQLITE",),
    "run_test": ("AC-TINY-RUN-TEST-COMMANDS",),
}


@dataclass(frozen=True)
class TinyScenarioActiveContracts:
    project_charter: ProjectCharter
    methodology_profile: MethodologyProfile
    acceptance_contract: AcceptanceContract
    package_contract: PackageContract
    contract_gate: ContractGateResult
    required_acceptance_refs_by_category: Mapping[str, tuple[str, ...]]


def build_tiny_scenario_active_contracts() -> TinyScenarioActiveContracts:
    fixture = build_tiny_fullstack_contract_fixture()
    contracts = TinyScenarioActiveContracts(
        project_charter=fixture.project_charter,
        methodology_profile=fixture.methodology_profile,
        acceptance_contract=fixture.acceptance_contract,
        package_contract=fixture.package_contract,
        contract_gate=fixture.contract_gate,
        required_acceptance_refs_by_category=REQUIRED_ACCEPTANCE_REFS_BY_CATEGORY,
    )
    validate_tiny_scenario_active_contracts(
        project_charter=contracts.project_charter,
        acceptance_contract=contracts.acceptance_contract,
        package_contract=contracts.package_contract,
        contract_gate=contracts.contract_gate,
    )
    return contracts


def validate_tiny_scenario_active_contracts(
    *,
    project_charter: ProjectCharter,
    acceptance_contract: AcceptanceContract,
    package_contract: PackageContract,
    contract_gate: ContractGateResult,
) -> None:
    if acceptance_contract.status.value != "active":
        raise ValueError("active acceptance contract is required")
    if acceptance_contract.project_charter_ref != project_charter.project_charter_id:
        raise ValueError("acceptance contract must bind the project charter")
    if package_contract.project_charter_ref != project_charter.project_charter_id:
        raise ValueError("package contract must bind the project charter")
    if contract_gate.acceptance_contract_ref != acceptance_contract.acceptance_contract_id:
        raise ValueError("contract gate must bind the active acceptance contract")
    if contract_gate.package_contract_ref != package_contract.package_contract_id:
        raise ValueError("contract gate must bind the package contract")

    active_acceptance_refs = _active_acceptance_refs(acceptance_contract)
    _validate_required_acceptance_categories(active_acceptance_refs)
    _validate_package_surfaces_cover_active_refs(
        package_contract=package_contract,
        active_acceptance_refs=active_acceptance_refs,
    )
    _validate_contract_gate_covers_active_contracts(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
        contract_gate=contract_gate,
    )


def _active_acceptance_refs(acceptance_contract: AcceptanceContract) -> set[str]:
    return {
        criterion.acceptance_ref.value
        for criterion in acceptance_contract.blocking_criteria()
    }


def _validate_required_acceptance_categories(active_acceptance_refs: set[str]) -> None:
    missing_refs_by_category = {
        category: tuple(
            acceptance_ref
            for acceptance_ref in required_refs
            if acceptance_ref not in active_acceptance_refs
        )
        for category, required_refs in REQUIRED_ACCEPTANCE_REFS_BY_CATEGORY.items()
    }
    missing_refs_by_category = {
        category: refs
        for category, refs in missing_refs_by_category.items()
        if refs
    }
    if missing_refs_by_category:
        raise ValueError("missing required acceptance refs")


def _validate_package_surfaces_cover_active_refs(
    *,
    package_contract: PackageContract,
    active_acceptance_refs: set[str],
) -> None:
    package_surface_refs = {
        surface.source_surface_ref.value
        for surface in package_contract.source_surfaces
    }
    required_surface_refs = {
        "backend-api",
        "frontend-ui",
        "persistence",
        "tests",
        "docs",
        "run-manifest",
    }
    if not required_surface_refs.issubset(package_surface_refs):
        raise ValueError("package source surfaces must cover the full-stack package")

    package_acceptance_refs = {
        acceptance_ref.value
        for surface in package_contract.source_surfaces
        for acceptance_ref in surface.acceptance_refs
    }
    if not active_acceptance_refs.issubset(package_acceptance_refs):
        raise ValueError("package source surfaces must cover active blocking refs")
    if package_acceptance_refs - active_acceptance_refs:
        raise ValueError("package source surfaces must not reference inactive acceptance refs")


def _validate_contract_gate_covers_active_contracts(
    *,
    acceptance_contract: AcceptanceContract,
    package_contract: PackageContract,
    contract_gate: ContractGateResult,
) -> None:
    active_acceptance_refs = _active_acceptance_refs(acceptance_contract)
    gate_acceptance_refs = {
        acceptance_ref.value
        for acceptance_ref in contract_gate.acceptance_refs
    }
    if gate_acceptance_refs != active_acceptance_refs:
        raise ValueError("contract gate must cover active blocking refs")

    active_source_surface_refs = {
        source_surface_ref.value
        for criterion in acceptance_contract.blocking_criteria()
        for source_surface_ref in criterion.source_surface_refs
    }
    package_source_surface_refs = {
        source_surface.source_surface_ref.value
        for source_surface in package_contract.source_surfaces
    }
    gate_source_surface_refs = {
        source_surface_ref.value
        for source_surface_ref in contract_gate.source_surface_refs
    }
    if not active_source_surface_refs.issubset(gate_source_surface_refs):
        raise ValueError("contract gate must cover active source surface refs")
    if not gate_source_surface_refs.issubset(package_source_surface_refs):
        raise ValueError("contract gate source surfaces must belong to the package contract")

    expected_obligations = compile_evidence_obligations(acceptance_contract)
    if contract_gate.evidence_obligations != expected_obligations:
        raise ValueError("contract gate evidence obligations must match active contract")
