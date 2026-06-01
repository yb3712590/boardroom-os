from __future__ import annotations

from pathlib import Path

import pytest

from boardroom_os.closeout.gate import (
    CloseoutCommandEvidenceBinding,
    CloseoutGate,
    CloseoutGateBlockerCode,
    CloseoutGateVerdict,
)
from boardroom_os.contracts.types import ContractId
from tests.closeout.test_closeout_gate import _ready_input


def _without_command_evidence(gate_input, command_id: str):
    remaining_runs = tuple(
        run for run in gate_input.verification_runs if run.command_id.value != command_id
    )
    remaining_run_refs = {run.verification_run_id.value for run in remaining_runs}
    remaining_evidence = tuple(
        evidence
        for evidence in gate_input.verified_evidence
        if any(ref.value in remaining_run_refs for ref in evidence.verification_run_refs)
    )
    remaining_evidence_refs = tuple(
        evidence.verified_evidence_id for evidence in remaining_evidence
    )
    final_evidence_table = gate_input.final_evidence_table.model_copy(
        update={
            "rows": tuple(
                row.model_copy(update={"verified_evidence_refs": remaining_evidence_refs})
                for row in gate_input.final_evidence_table.rows
            )
        }
    )
    source_inventory = gate_input.source_inventory.model_copy(
        update={
            "entries": tuple(
                entry.model_copy(update={"evidence_refs": remaining_evidence_refs})
                for entry in gate_input.source_inventory.entries
            )
        }
    )
    workspace_evidence_bundle = gate_input.workspace_evidence_bundle.model_copy(
        update={
            "source_inventory_ref": source_inventory.source_inventory_id,
            "final_evidence_table_ref": final_evidence_table.final_evidence_table_id,
            "verification_run_refs": tuple(run.verification_run_id for run in remaining_runs),
            "verified_evidence_refs": remaining_evidence_refs,
        }
    )
    return gate_input.model_copy(
        update={
            "source_inventory": source_inventory,
            "workspace_evidence_bundle": workspace_evidence_bundle,
            "final_evidence_table": final_evidence_table,
            "verification_runs": remaining_runs,
            "verified_evidence": remaining_evidence,
            "final_command_bindings": tuple(
                binding
                for binding in gate_input.final_command_bindings
                if binding.command_id.value != command_id
            ),
        }
    )


def _command_evidence_blockers(result):
    return tuple(
        blocker
        for blocker in result.blockers
        if blocker.code is CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL
    )


def test_closeout_gate_blocks_when_run_manifest_command_lacks_final_evidence() -> None:
    gate_input = _without_command_evidence(_ready_input(), "run-app")

    result = CloseoutGate().evaluate(gate_input)

    assert {command.command_id.value for command in gate_input.run_manifest.commands} == {
        "run-app",
        "test-app",
    }
    assert {binding.command_id.value for binding in gate_input.final_command_bindings} == {
        "test-app",
    }
    assert result.verdict is CloseoutGateVerdict.BLOCKED
    blockers = _command_evidence_blockers(result)
    assert blockers
    assert any(blocker.related_ref == "run-app" for blocker in blockers)
    assert any("RUN_MANIFEST_COMMAND_UNVERIFIED" in blocker.message for blocker in blockers)


def _tiny_failure_gate_input():
    ready = _ready_input()
    manifest_commands = {command.command_id.value: command for command in ready.run_manifest.commands}
    run_command = manifest_commands["run-app"]
    test_command = manifest_commands["test-app"]
    run_manifest = ready.run_manifest.model_copy(
        update={
            "commands": (
                run_command.model_copy(
                    update={
                        "command_id": ContractId(value="run-backend"),
                        "label": "Run backend API",
                        "command": ("python", "-m", "uvicorn", "backend.app:app"),
                    }
                ),
                run_command.model_copy(
                    update={
                        "command_id": ContractId(value="run-frontend"),
                        "label": "Run frontend UI",
                        "command": ("python", "-m", "http.server", "5173", "--directory", "frontend"),
                    }
                ),
                test_command.model_copy(update={"command_id": ContractId(value="test-backend")}),
                test_command.model_copy(update={"command_id": ContractId(value="test-integration")}),
            )
        }
    )
    backend_run = ready.verification_runs[0].model_copy(
        update={
            "verification_run_id": type(ready.verification_runs[0].verification_run_id)(
                value="verification-run.tiny.test-backend"
            ),
            "command_id": ContractId(value="test-backend"),
        }
    )
    integration_run = ready.verification_runs[0].model_copy(
        update={
            "verification_run_id": type(ready.verification_runs[0].verification_run_id)(
                value="verification-run.tiny.test-integration"
            ),
            "command_id": ContractId(value="test-integration"),
        }
    )
    workspace_evidence_bundle = ready.workspace_evidence_bundle.model_copy(
        update={
            "verification_run_refs": (
                backend_run.verification_run_id,
                integration_run.verification_run_id,
            )
        }
    )
    final_command_bindings = (
        CloseoutCommandEvidenceBinding(
            verification_run_ref=backend_run.verification_run_id,
            run_manifest_ref=run_manifest.run_manifest_id,
            package_contract_ref=ready.package_contract.package_contract_id,
            command_id=ContractId(value="test-backend"),
            binding_kind=test_command.kind,
        ),
        CloseoutCommandEvidenceBinding(
            verification_run_ref=integration_run.verification_run_id,
            run_manifest_ref=run_manifest.run_manifest_id,
            package_contract_ref=ready.package_contract.package_contract_id,
            command_id=ContractId(value="test-integration"),
            binding_kind=test_command.kind,
        ),
    )
    return ready.model_copy(
        update={
            "run_manifest": run_manifest,
            "workspace_evidence_bundle": workspace_evidence_bundle,
            "verification_runs": (backend_run, integration_run),
            "final_command_bindings": final_command_bindings,
        }
    )


def test_v2_080_tiny_failure_package_is_blocked_when_run_commands_lack_evidence() -> None:
    gate_input = _tiny_failure_gate_input()

    result = CloseoutGate().evaluate(gate_input)

    assert {command.command_id.value for command in gate_input.run_manifest.commands} == {
        "run-backend",
        "run-frontend",
        "test-backend",
        "test-integration",
    }
    assert {run.command_id.value for run in gate_input.verification_runs} == {
        "test-backend",
        "test-integration",
    }
    assert result.verdict is CloseoutGateVerdict.BLOCKED
    blockers = _command_evidence_blockers(result)
    assert {blocker.related_ref for blocker in blockers} >= {
        "run-backend",
        "run-frontend",
    }
    assert all("RUN_MANIFEST_COMMAND_UNVERIFIED" in blocker.message for blocker in blockers)


def test_existing_verification_runs_do_not_substitute_for_unverified_manifest_commands() -> None:
    gate_input = _without_command_evidence(_ready_input(), "run-app")

    result = CloseoutGate().evaluate(gate_input)

    blockers = _command_evidence_blockers(result)
    assert result.verdict is CloseoutGateVerdict.BLOCKED
    assert blockers
    assert all(blocker.related_ref != gate_input.run_manifest.run_manifest_id.value for blocker in blockers)
    assert any(blocker.related_ref == "run-app" for blocker in blockers)
