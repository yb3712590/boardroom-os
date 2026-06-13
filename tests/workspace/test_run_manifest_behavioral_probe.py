from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import ContractId
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.workspace.run_manifest import (
    RunManifest,
    RunManifestBehaviorAssertion,
    RunManifestBehaviorAssertionKind,
    RunManifestBehaviorProbe,
    RunManifestBehaviorStep,
    RunManifestReadinessProbe,
    RunManifestServiceContract,
    build_run_manifest,
)
from tests.proving.test_run_manifest import _package_contract, _workspace_manifest

_VERIFY_ERRORS = (ValueError, ValidationError)


def _service_contract(*, command_id: str = "run-package") -> RunManifestServiceContract:
    return RunManifestServiceContract(
        command_id=ContractId(value=command_id),
        role="backend",
        env_bindings=(),
        readiness_probe=RunManifestReadinessProbe(
            method="GET",
            path="/health",
            expect_status=200,
        ),
    )


def _behavioral_probe(
    *,
    probe_id: str = "probe.checkout-flow",
    service_command_id: str = "run-package",
) -> RunManifestBehaviorProbe:
    return RunManifestBehaviorProbe(
        probe_id=ContractId(value=probe_id),
        service_command_id=ContractId(value=service_command_id),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-DECLARED-BEHAVIOR"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="step.open-status",
                method="GET",
                path="/status",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_EQUALS,
                        target="$.status",
                        expected="ok",
                    ),
                ),
            ),
        ),
    )


def test_run_manifest_accepts_behavioral_probe_bound_to_service_command() -> None:
    package_contract = _package_contract()
    service_contract = _service_contract()
    behavioral_probe = _behavioral_probe()

    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
        service_contracts=(service_contract,),
        behavioral_probes=(behavioral_probe,),
    )

    assert manifest.behavioral_probes == (behavioral_probe,)


def test_behavioral_probe_service_command_id_must_exist_in_service_contracts() -> None:
    package_contract = _package_contract()

    with pytest.raises(_VERIFY_ERRORS, match="behavioral probe|service contract"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(package_contract),
            package_contract=package_contract,
            service_contracts=(_service_contract(command_id="run-package"),),
            behavioral_probes=(_behavioral_probe(service_command_id="run-missing"),),
        )


def test_run_manifest_rejects_duplicate_behavioral_probe_ids() -> None:
    package_contract = _package_contract()

    with pytest.raises(_VERIFY_ERRORS, match="duplicate|behavioral probe"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(package_contract),
            package_contract=package_contract,
            service_contracts=(_service_contract(),),
            behavioral_probes=(
                _behavioral_probe(probe_id="probe.checkout-flow"),
                _behavioral_probe(probe_id="probe.checkout-flow"),
            ),
        )


def test_behavioral_step_rejects_invalid_path() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="path"):
        RunManifestBehaviorStep(
            step_id="step.invalid-path",
            method="GET",
            path="status",
            json_body=None,
            expect_status=200,
        )


def test_behavioral_probe_requires_steps() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="step"):
        RunManifestBehaviorProbe(
            probe_id=ContractId(value="probe.empty"),
            service_command_id=ContractId(value="run-package"),
            acceptance_refs=(AcceptanceRef(value="AC-AGENT-DECLARED-BEHAVIOR"),),
            steps=(),
        )


def test_explicit_empty_behavioral_probes_fail_closed_when_service_contracts_exist() -> None:
    package_contract = _package_contract()
    service_contract = _service_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
        service_contracts=(service_contract,),
        behavioral_probes=(_behavioral_probe(),),
    )

    with pytest.raises(_VERIFY_ERRORS, match="behavioral probe"):
        RunManifest.model_validate(manifest.model_dump() | {"behavioral_probes": ()})
