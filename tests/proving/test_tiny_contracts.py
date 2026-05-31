import pytest

from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.types import ContractStatus
from tests.proving.fixtures.tiny_fullstack_contracts import (
    REQUIRED_ACCEPTANCE_REFS_BY_CATEGORY,
    TinyScenarioActiveContracts,
    build_tiny_scenario_active_contracts,
    validate_tiny_scenario_active_contracts,
)


def _without_acceptance_category(
    contracts: TinyScenarioActiveContracts,
    category: str,
) -> AcceptanceContract:
    removed_refs = REQUIRED_ACCEPTANCE_REFS_BY_CATEGORY[category]
    return contracts.acceptance_contract.model_copy(
        update={
            "criteria": tuple(
                criterion
                for criterion in contracts.acceptance_contract.criteria
                if criterion.acceptance_ref.value not in removed_refs
            ),
        },
    )


def test_missing_api_refs_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()

    with pytest.raises(ValueError, match="missing required acceptance refs"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=_without_acceptance_category(contracts, "api"),
            package_contract=contracts.package_contract,
            contract_gate=contracts.contract_gate,
        )


def test_missing_ui_refs_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()

    with pytest.raises(ValueError, match="missing required acceptance refs"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=_without_acceptance_category(contracts, "ui"),
            package_contract=contracts.package_contract,
            contract_gate=contracts.contract_gate,
        )


def test_missing_persistence_refs_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()

    with pytest.raises(ValueError, match="missing required acceptance refs"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=_without_acceptance_category(contracts, "persistence"),
            package_contract=contracts.package_contract,
            contract_gate=contracts.contract_gate,
        )


def test_missing_run_test_refs_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()

    with pytest.raises(ValueError, match="missing required acceptance refs"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=_without_acceptance_category(contracts, "run_test"),
            package_contract=contracts.package_contract,
            contract_gate=contracts.contract_gate,
        )


def test_inactive_acceptance_contract_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()
    inactive_contract = contracts.acceptance_contract.model_copy(
        update={"status": ContractStatus.draft()},
    )

    with pytest.raises(ValueError, match="active acceptance contract is required"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=inactive_contract,
            package_contract=contracts.package_contract,
            contract_gate=contracts.contract_gate,
        )


def test_package_surfaces_missing_active_refs_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()
    removed_ref = "AC-TINY-UI-FETCH-BACKEND"
    package_contract = contracts.package_contract.model_copy(
        update={
            "source_surfaces": tuple(
                surface.model_copy(
                    update={
                        "acceptance_refs": tuple(
                            ref for ref in surface.acceptance_refs if ref.value != removed_ref
                        ),
                    },
                )
                for surface in contracts.package_contract.source_surfaces
            ),
        },
    )

    with pytest.raises(ValueError, match="package source surfaces must cover active blocking refs"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=contracts.acceptance_contract,
            package_contract=package_contract,
            contract_gate=contracts.contract_gate,
        )


def test_contract_gate_missing_evidence_obligation_rejected() -> None:
    contracts = build_tiny_scenario_active_contracts()
    contract_gate = contracts.contract_gate.model_copy(
        update={"evidence_obligations": contracts.contract_gate.evidence_obligations[:-1]},
    )

    with pytest.raises(ValueError, match="contract gate evidence obligations must match active contract"):
        validate_tiny_scenario_active_contracts(
            project_charter=contracts.project_charter,
            acceptance_contract=contracts.acceptance_contract,
            package_contract=contracts.package_contract,
            contract_gate=contract_gate,
        )


def test_fixture_builds_active_project_acceptance_and_package_contracts() -> None:
    contracts = build_tiny_scenario_active_contracts()
    active_refs = {
        criterion.acceptance_ref.value
        for criterion in contracts.acceptance_contract.blocking_criteria()
    }

    assert contracts.project_charter.delivery_type == "generated_project_package"
    assert contracts.acceptance_contract.status.value == "active"
    assert contracts.package_contract.project_charter_ref == contracts.project_charter.project_charter_id
    assert contracts.contract_gate.acceptance_contract_ref == contracts.acceptance_contract.acceptance_contract_id
    assert contracts.contract_gate.package_contract_ref == contracts.package_contract.package_contract_id
    assert contracts.required_acceptance_refs_by_category == REQUIRED_ACCEPTANCE_REFS_BY_CATEGORY
    assert "AC-TINY-API-BOOK-DELETE" in active_refs


def test_source_surfaces_cover_full_stack_package() -> None:
    contracts = build_tiny_scenario_active_contracts()

    surface_refs = {
        surface.source_surface_ref.value
        for surface in contracts.package_contract.source_surfaces
    }
    assert {
        "backend-api",
        "frontend-ui",
        "persistence",
        "tests",
        "docs",
        "run-manifest",
    }.issubset(surface_refs)

    active_refs = {
        criterion.acceptance_ref.value
        for criterion in contracts.acceptance_contract.blocking_criteria()
    }
    for surface in contracts.package_contract.source_surfaces:
        assert {ref.value for ref in surface.acceptance_refs}.issubset(active_refs)


def test_contract_gate_evidence_obligations_cover_all_blocking_evidence_required() -> None:
    contracts = build_tiny_scenario_active_contracts()

    obligation_pairs = {
        (acceptance_ref.value, obligation.required_artifact_type.value)
        for obligation in contracts.contract_gate.evidence_obligations
        for acceptance_ref in obligation.acceptance_refs
    }
    required_pairs = {
        (criterion.acceptance_ref.value, evidence_requirement.value)
        for criterion in contracts.acceptance_contract.blocking_criteria()
        for evidence_requirement in criterion.evidence_required
    }

    assert obligation_pairs == required_pairs
