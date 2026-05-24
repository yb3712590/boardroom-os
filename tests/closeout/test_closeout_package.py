from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from boardroom_os.audit.git_version_audit import (
    GitCommandEvidenceBinding,
    git_version_audit_readiness,
    source_inventory_hash,
)
from boardroom_os.audit.process_audit import (
    build_process_audit_bundle,
    process_audit_readiness,
)
from boardroom_os.closeout.gate import (
    CloseoutGate,
    CloseoutGateBlocker,
    CloseoutGateBlockerCode,
    CloseoutGateResultRef,
    CloseoutGateVerdict,
    GitAuditReadiness,
)
from boardroom_os.closeout.package import (
    CloseoutPackage,
    CloseoutPackageBuilderInput,
    CloseoutPackageCheckedRef,
    CloseoutPackageError,
    CloseoutPackageVerdict,
    build_closeout_package,
)
from boardroom_os.events.types import ProjectRef
from boardroom_os.workspace.source_inventory import PackageCommitRef
from tests.closeout.test_git_version_audit import _builder_input as _git_version_audit_builder_input
from tests.closeout.test_git_version_audit import _build_bundle as _build_git_version_audit_bundle
from tests.closeout.test_process_audit_artifacts import _process_audit_builder_input
from tests.negative.test_closeout_fail_closed import _ready_input as _closeout_gate_ready_input

_GENERATED_AT = datetime(2026, 5, 24, 13, 0, tzinfo=UTC)


def _closeout_package_builder_input(**overrides: Any) -> CloseoutPackageBuilderInput:
    process_input = _process_audit_builder_input()
    closeout_gate_seed = _closeout_gate_ready_input()
    source_hash = source_inventory_hash(process_input.source_inventory)
    default_git_builder_input = _git_version_audit_builder_input(
        package_contract=process_input.package_contract,
        source_inventory=process_input.source_inventory,
        run_manifest=closeout_gate_seed.run_manifest,
        verification_runs=process_input.verification_runs,
        git_facts=_git_version_audit_builder_input().git_facts.model_copy(
            update={"source_inventory_hash": source_hash}
        ),
        command_evidence_bindings=tuple(
            GitCommandEvidenceBinding(
                binding_id=f"git-command-evidence-binding.{run.verification_run_id.value}",
                verification_run_ref=run.verification_run_id,
                run_manifest_ref=closeout_gate_seed.run_manifest.run_manifest_id,
                package_contract_ref=process_input.package_contract.package_contract_id,
                command_id=run.command_id,
                command=run.command,
                cwd=run.cwd,
                workspace_snapshot_ref=run.workspace_snapshot_ref,
                commit_sha=_git_version_audit_builder_input().git_facts.final_commit_sha,
                source_inventory_hash=source_hash,
            )
            for run in process_input.verification_runs
        ),
    )
    git_version_audit_bundle = overrides.pop(
        "git_version_audit_bundle",
        _build_git_version_audit_bundle(
            package_contract=process_input.package_contract,
            source_inventory=process_input.source_inventory,
            run_manifest=closeout_gate_seed.run_manifest,
            verification_runs=process_input.verification_runs,
            git_facts=default_git_builder_input.git_facts,
            command_evidence_bindings=default_git_builder_input.command_evidence_bindings,
        ),
    )
    git_audit_readiness = overrides.pop(
        "git_audit_readiness",
        git_version_audit_readiness(git_version_audit_bundle),
    )
    if "git_version_audit_bundle" not in overrides:
        process_input = _process_audit_builder_input(
            git_version_audit_bundle=git_version_audit_bundle,
            git_audit_readiness=git_audit_readiness,
        )
    process_audit_bundle = build_process_audit_bundle(process_input)
    process_audit_readiness_value = process_audit_readiness(process_audit_bundle)
    replay_bundle = process_input.replay_bundle
    replay_readiness = process_input.replay_readiness
    closeout_gate_input = closeout_gate_seed
    closeout_gate_input = closeout_gate_input.model_copy(
        update={
            "package_contract": process_input.package_contract,
            "source_inventory": process_input.source_inventory,
            "run_manifest": closeout_gate_input.run_manifest,
            "workspace_evidence_bundle": process_input.workspace_evidence_bundle,
            "final_evidence_table": process_input.final_evidence_table,
            "checker_verdict": process_input.checker_verdict,
            "verification_runs": process_input.verification_runs,
            "verified_evidence": process_input.verified_evidence,
            "provider_attempt_refs": process_input.provider_attempt_refs,
            "replay_readiness": replay_readiness,
            "git_audit_readiness": git_audit_readiness,
            "process_audit_readiness": process_audit_readiness_value,
        }
    )
    gate_result = CloseoutGate().evaluate(closeout_gate_input)
    values: dict[str, Any] = {
        "closeout_gate_result": gate_result,
        "source_inventory": process_input.source_inventory,
        "final_evidence_table": process_input.final_evidence_table,
        "replay_bundle": replay_bundle,
        "replay_readiness": replay_readiness,
        "process_audit_bundle": process_audit_bundle,
        "process_audit_readiness": process_audit_readiness_value,
        "git_version_audit_bundle": git_version_audit_bundle,
        "git_audit_readiness": git_audit_readiness,
        "graph_version": replay_bundle.attestations[0].event_window.last_graph_version,
        "generated_at": _GENERATED_AT,
    }
    values.update(overrides)
    return CloseoutPackageBuilderInput(**values)


def _build_package(**overrides: Any) -> CloseoutPackage:
    return build_closeout_package(_closeout_package_builder_input(**overrides))


def test_closeout_package_binds_passed_gate_and_all_audit_bundles() -> None:
    builder_input = _closeout_package_builder_input()
    package = build_closeout_package(builder_input)

    assert package.version == 1
    assert package.verdict is CloseoutPackageVerdict.PASSED
    assert package.closeout_gate_result_ref == builder_input.closeout_gate_result.closeout_gate_result_id
    assert package.source_inventory_ref == builder_input.source_inventory.source_inventory_id
    assert package.final_evidence_table_ref == builder_input.final_evidence_table.final_evidence_table_id
    assert package.acceptance_summary_ref == builder_input.final_evidence_table.final_evidence_table_id
    assert package.replay_bundle_ref == builder_input.replay_bundle.replay_bundle_id
    assert package.process_audit_bundle_ref == builder_input.process_audit_bundle.process_audit_bundle_id
    assert package.git_version_audit_bundle_ref == builder_input.git_version_audit_bundle.git_version_audit_bundle_id
    assert package.package_commit_ref == builder_input.source_inventory.package_commit_ref


def test_closeout_package_checked_refs_are_stable_and_complete() -> None:
    builder_input = _closeout_package_builder_input()
    package = build_closeout_package(builder_input)
    checked_refs = [ref.value for ref in package.checked_refs]

    assert len(checked_refs) == len(set(checked_refs))
    assert checked_refs == [ref.value for ref in build_closeout_package(builder_input).checked_refs]
    required_refs = {
        builder_input.closeout_gate_result.closeout_gate_result_id.value,
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.final_evidence_table.final_evidence_table_id.value,
        builder_input.replay_bundle.replay_bundle_id.value,
        builder_input.process_audit_bundle.process_audit_bundle_id.value,
        builder_input.git_version_audit_bundle.git_version_audit_bundle_id.value,
        builder_input.source_inventory.package_commit_ref.value,
        builder_input.git_audit_readiness.final_commit_sha.value,
        builder_input.git_audit_readiness.source_inventory_hash.value,
        builder_input.replay_readiness.summary_hash.value,
        *(path.value for path in builder_input.process_audit_readiness.artifact_paths),
    }
    assert required_refs <= set(checked_refs)


def test_closeout_package_id_is_deterministic() -> None:
    builder_input = _closeout_package_builder_input()

    first_package = build_closeout_package(builder_input)
    second_package = build_closeout_package(builder_input)
    changed_package = build_closeout_package(
        builder_input.model_copy(update={"graph_version": builder_input.graph_version + 1})
    )

    assert first_package.closeout_package_id == second_package.closeout_package_id
    assert first_package.closeout_package_id != changed_package.closeout_package_id


def test_closeout_package_dump_is_audit_friendly_json() -> None:
    payload = _build_package().model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert "D:/" not in serialized
    assert "C:/" not in serialized
    assert "D:\\" not in serialized
    assert "C:\\" not in serialized
    assert ".pytest" not in serialized
    assert "backend/app/core" not in serialized


def test_closeout_package_requires_typed_builder_inputs() -> None:
    payload = _closeout_package_builder_input().model_dump(mode="python")

    with pytest.raises(ValidationError, match="closeout_gate_result must be CloseoutGateResult"):
        CloseoutPackageBuilderInput.model_validate(payload)


def test_closeout_package_rejects_scalar_tuple_refs() -> None:
    package = _build_package()
    payload = package.model_dump(mode="python")
    payload["checked_refs"] = "source-inventory.scalar"

    with pytest.raises(ValidationError, match="checked_refs must be a tuple or list"):
        CloseoutPackage.model_validate(payload)


def test_closeout_package_rejects_blocked_gate_result() -> None:
    builder_input = _closeout_package_builder_input()
    blocked_result = builder_input.closeout_gate_result.model_copy(
        update={
            "verdict": CloseoutGateVerdict.BLOCKED,
            "blockers": (
                CloseoutGateBlocker(
                    code=CloseoutGateBlockerCode.REPLAY_NOT_READY,
                    message="Replay is not ready.",
                    related_ref="replay-bundle.test",
                ),
            ),
        }
    )

    with pytest.raises(ValidationError, match="closeout gate result must be passed"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"closeout_gate_result": blocked_result})
        )


def test_closeout_package_rejects_verdict_mismatch() -> None:
    package = _build_package()

    with pytest.raises(ValidationError, match="checked_refs|verdict"):
        CloseoutPackage.model_validate(
            {
                **package.model_dump(mode="python"),
                "verdict": CloseoutPackageVerdict.FAILED,
            }
        )


def test_closeout_package_rejects_non_v1_version() -> None:
    payload = _build_package().model_dump(mode="python")
    payload["version"] = 2

    with pytest.raises(ValidationError, match="version"):
        CloseoutPackage.model_validate(payload)


def test_closeout_package_recomputes_gate_result_id() -> None:
    builder_input = _closeout_package_builder_input()
    mismatched_gate = builder_input.closeout_gate_result.model_copy(
        update={"closeout_gate_result_id": CloseoutGateResultRef(value="closeout-gate-result.other")}
    )

    with pytest.raises(ValidationError, match="closeout gate result id mismatch"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"closeout_gate_result": mismatched_gate})
        )


def test_closeout_package_rejects_source_inventory_git_commit_mismatch() -> None:
    builder_input = _closeout_package_builder_input()
    mismatched_inventory = builder_input.source_inventory.model_copy(
        update={"package_commit_ref": PackageCommitRef(value="package-commit." + "d" * 40)}
    )

    with pytest.raises(ValidationError, match="package_commit_ref mismatch"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"source_inventory": mismatched_inventory})
        )


def test_closeout_package_rejects_git_readiness_bundle_mismatch() -> None:
    builder_input = _closeout_package_builder_input()
    mismatched_readiness = GitAuditReadiness(
        git_clean=False,
        final_commit_sha="d" * 40,
        source_inventory_hash="e" * 64,
        source_inventory_hash_matches=False,
        final_command_evidence_at_final_commit=False,
    )

    with pytest.raises(ValidationError, match="git audit readiness bundle mismatch"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"git_audit_readiness": mismatched_readiness})
        )


def test_closeout_package_rejects_replay_readiness_bundle_mismatch() -> None:
    builder_input = _closeout_package_builder_input()
    mismatched_readiness = builder_input.replay_readiness.model_copy(
        update={"summary_hash": "2" * 64}
    )

    with pytest.raises(ValidationError, match="replay readiness bundle mismatch"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"replay_readiness": mismatched_readiness})
        )


def test_closeout_package_rejects_process_audit_readiness_gap() -> None:
    builder_input = _closeout_package_builder_input()
    mismatched_readiness = builder_input.process_audit_readiness.model_copy(
        update={"artifact_paths": builder_input.process_audit_readiness.artifact_paths[:-1]}
    )

    with pytest.raises(ValidationError, match="process audit readiness bundle mismatch"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"process_audit_readiness": mismatched_readiness})
        )


def test_closeout_package_rejects_gate_checked_refs_gap() -> None:
    builder_input = _closeout_package_builder_input()
    gate_result = builder_input.closeout_gate_result.model_copy(
        update={"checked_refs": (builder_input.source_inventory.source_inventory_id.value,)}
    )

    with pytest.raises(ValidationError, match="closeout gate checked_refs"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"closeout_gate_result": gate_result})
        )


def test_closeout_package_rejects_project_ref_mismatch_across_bundles() -> None:
    builder_input = _closeout_package_builder_input()
    mismatched_bundle = builder_input.git_version_audit_bundle.model_copy(
        update={"project_ref": ProjectRef(value="project.other")}
    )

    with pytest.raises(ValidationError, match="git version audit bundle project_ref mismatch"):
        CloseoutPackageBuilderInput.model_validate(
            builder_input.model_copy(update={"git_version_audit_bundle": mismatched_bundle})
        )


def test_closeout_package_rejects_naive_generated_at() -> None:
    with pytest.raises(ValidationError, match="generated_at must include timezone"):
        _closeout_package_builder_input(generated_at=datetime(2026, 5, 24, 13, 0))


def test_closeout_package_rejects_unsafe_checked_refs_or_paths() -> None:
    package = _build_package()
    payload = package.model_dump(mode="python")
    payload["checked_refs"] = (*payload["checked_refs"], CloseoutPackageCheckedRef(value="C:/tmp/evidence"))

    with pytest.raises(ValidationError, match="audit-friendly"):
        CloseoutPackage.model_validate(payload)
