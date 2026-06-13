from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import ContractId
from boardroom_os.workspace.run_manifest import (
    RunManifest,
    RunManifestEnvironmentBinding,
    RunManifestEnvironmentValueSource,
    RunManifestFrontendMode,
    RunManifestFrontendTopology,
    RunManifestReadinessProbe,
    RunManifestServiceContract,
    build_run_manifest,
)
from tests.proving.test_run_manifest import _package_contract, _workspace_manifest

_VERIFY_ERRORS = (ValueError, ValidationError)


def _readiness_probe() -> RunManifestReadinessProbe:
    return RunManifestReadinessProbe(
        method="GET",
        path="/health",
        expect_status=200,
    )


def _service_contract(
    *,
    command_id: str = "run-package",
    env: tuple[RunManifestEnvironmentBinding, ...] | None = None,
) -> RunManifestServiceContract:
    return RunManifestServiceContract(
        command_id=ContractId(value=command_id),
        role="backend",
        env_bindings=(
            RunManifestEnvironmentBinding(
                name="API_HOST",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
            ),
            RunManifestEnvironmentBinding(
                name="DATABASE_URL",
                value_source=RunManifestEnvironmentValueSource.LITERAL,
                literal_value="sqlite:///data/app.db",
            ),
        )
        if env is None
        else env,
        readiness_probe=_readiness_probe(),
    )


def test_run_manifest_accepts_service_contract_and_frontend_topology_for_run_commands() -> None:
    package_contract = _package_contract()
    service_contract = _service_contract()
    frontend_topology = RunManifestFrontendTopology(
        mode=RunManifestFrontendMode.STATIC_SERVER,
        service_command_id=ContractId(value="run-package"),
    )

    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
        service_contracts=(service_contract,),
        frontend_topology=frontend_topology,
    )

    assert manifest.service_contracts == (service_contract,)
    assert manifest.frontend_topology == frontend_topology


def test_service_contract_command_id_must_reference_run_command() -> None:
    package_contract = _package_contract()

    with pytest.raises(_VERIFY_ERRORS, match="RUN command|service contract"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(package_contract),
            package_contract=package_contract,
            service_contracts=(_service_contract(command_id="test-package"),),
        )


def test_run_manifest_rejects_duplicate_service_command_ids() -> None:
    package_contract = _package_contract()

    with pytest.raises(_VERIFY_ERRORS, match="duplicate|service"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(package_contract),
            package_contract=package_contract,
            service_contracts=(
                _service_contract(command_id="run-package"),
                _service_contract(command_id="run-package"),
            ),
        )


def test_frontend_topology_command_id_must_reference_run_command() -> None:
    package_contract = _package_contract()

    with pytest.raises(_VERIFY_ERRORS, match="frontend|RUN command"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(package_contract),
            package_contract=package_contract,
            frontend_topology=RunManifestFrontendTopology(
                mode=RunManifestFrontendMode.STATIC_SERVER,
                service_command_id=ContractId(value="test-package"),
            ),
        )


def test_environment_binding_name_must_be_uppercase_identifier() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="environment|uppercase|name"):
        RunManifestEnvironmentBinding(
            name="apiHost",
            value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
        )


def test_environment_binding_rejects_literal_on_runtime_source() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="literal"):
        RunManifestEnvironmentBinding(
            name="API_HOST",
            value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
            literal_value="127.0.0.1",
        )


def test_environment_binding_requires_literal_for_literal_source() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="literal"):
        RunManifestEnvironmentBinding(
            name="DATABASE_URL",
            value_source=RunManifestEnvironmentValueSource.LITERAL,
        )


def test_explicit_empty_service_contracts_fail_closed_for_run_manifest_with_run_commands() -> None:
    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )

    with pytest.raises(_VERIFY_ERRORS, match="service contract"):
        RunManifest.model_validate(manifest.model_dump() | {"service_contracts": ()})
