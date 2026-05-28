from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from boardroom_os.adapters.git_audit import GitAuditAdapter, GitAuditAdapterError, GitCommandResult
from boardroom_os.audit.git_version_audit import (
    GitChangedFile,
    GitChangedFileStatus,
    GitCommandEvidenceBinding,
    GitDiffSummary,
    GitDirtyStatus,
    GitVersionAuditBuilderInput,
    GitVersionAuditBundle,
    GitVersionAuditError,
    GitVersionAuditFactSet,
    _bundle_payload_for_hash,
    _hash_jsonable,
    _hash_model,
    build_git_version_audit_bundle,
    git_version_audit_readiness,
    source_inventory_hash,
)
from boardroom_os.closeout.gate import GitAuditReadiness
from boardroom_os.contracts.types import ContractId
from boardroom_os.execution.verification_run import VerificationRunStatus
from boardroom_os.workspace.source_inventory import PackageCommitRef
from tests.closeout.test_closeout_gate import _FINAL_COMMIT_SHA, _ready_input

_NOW = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
_BASE_COMMIT_SHA = "abcdef0123456789abcdef0123456789abcdef01"
_OTHER_COMMIT_SHA = "fedcba9876543210fedcba9876543210fedcba98"
_TAMPERED_SHA256 = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"


class FakeGitTransport:
    def __init__(self, results: dict[tuple[str, ...], GitCommandResult]) -> None:
        self.results = results
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        self.commands.append(command)
        return self.results[command]


def _git_facts(**overrides: Any) -> GitVersionAuditFactSet:
    ready = _ready_input()
    values = {
        "fact_set_id": "git-version-audit-facts.project-tiny-fullstack",
        "project_ref": "project-tiny-fullstack",
        "package_root": "10-project",
        "branch_ref": "branch.main",
        "worktree_ref": "worktree.final-package",
        "base_commit_sha": _BASE_COMMIT_SHA,
        "final_commit_sha": _FINAL_COMMIT_SHA,
        "optional_tag_ref": None,
        "dirty_status": GitDirtyStatus.CLEAN,
        "git_clean": True,
        "changed_files": (),
        "diff_summary": GitDiffSummary(
            diff_summary_id="git-diff-summary.clean",
            changed_file_count=0,
            insertions=0,
            deletions=0,
            summary_text="clean working tree",
        ),
        "source_inventory_hash": source_inventory_hash(ready.source_inventory),
        "generated_at": _NOW,
    }
    values.update(overrides)
    return GitVersionAuditFactSet(**values)


def _command_binding(**overrides: Any) -> GitCommandEvidenceBinding:
    ready = _ready_input()
    run = ready.verification_runs[0]
    run_manifest_command = next(command for command in ready.run_manifest.commands if command.command_id == run.command_id)
    values = {
        "binding_id": "git-command-evidence-binding.verification-run.app",
        "verification_run_ref": run.verification_run_id,
        "run_manifest_ref": ready.run_manifest.run_manifest_id,
        "package_contract_ref": ready.package_contract.package_contract_id,
        "command_id": run_manifest_command.command_id,
        "command": run.command,
        "cwd": run.cwd,
        "workspace_snapshot_ref": run.workspace_snapshot_ref,
        "commit_sha": _FINAL_COMMIT_SHA,
        "source_inventory_hash": source_inventory_hash(ready.source_inventory),
    }
    values.update(overrides)
    return GitCommandEvidenceBinding(**values)


def _builder_input(**overrides: Any) -> GitVersionAuditBuilderInput:
    ready = _ready_input()
    values = {
        "project_ref": "project-tiny-fullstack",
        "generated_at": _NOW,
        "package_contract": ready.package_contract,
        "source_inventory": ready.source_inventory,
        "run_manifest": ready.run_manifest,
        "verification_runs": ready.verification_runs,
        "command_evidence_bindings": (_command_binding(),),
        "git_facts": _git_facts(),
        "run_id": "run-v2-071e",
    }
    values.update(overrides)
    return GitVersionAuditBuilderInput(**values)


def _build_bundle(**overrides: Any) -> GitVersionAuditBundle:
    return build_git_version_audit_bundle(_builder_input(**overrides))


def test_git_version_audit_rejects_dirty_package() -> None:
    dirty_facts = _git_facts(
        dirty_status=GitDirtyStatus.DIRTY,
        git_clean=False,
        changed_files=(
            GitChangedFile(path="app.py", status=GitChangedFileStatus.MODIFIED),
        ),
        diff_summary=GitDiffSummary(
            diff_summary_id="git-diff-summary.dirty",
            changed_file_count=1,
            insertions=3,
            deletions=1,
            summary_text="app.py | 4 ++--",
        ),
    )

    with pytest.raises(GitVersionAuditError, match="git facts must be clean"):
        build_git_version_audit_bundle(_builder_input(git_facts=dirty_facts))


def test_git_version_audit_rejects_source_inventory_hash_mismatch() -> None:
    mismatched_facts = _git_facts(source_inventory_hash=_TAMPERED_SHA256)

    with pytest.raises(GitVersionAuditError, match="source inventory hash mismatch"):
        build_git_version_audit_bundle(_builder_input(git_facts=mismatched_facts))


def test_git_version_audit_rejects_final_command_not_at_final_commit() -> None:
    binding = _command_binding(commit_sha=_OTHER_COMMIT_SHA)

    with pytest.raises(GitVersionAuditError, match="final commit"):
        build_git_version_audit_bundle(_builder_input(command_evidence_bindings=(binding,)))


def test_git_version_audit_rejects_source_inventory_package_commit_mismatch() -> None:
    ready = _ready_input()
    mismatched_inventory = ready.source_inventory.model_copy(
        update={"package_commit_ref": PackageCommitRef(value=f"package-commit.{_OTHER_COMMIT_SHA}")}
    )
    facts = _git_facts(source_inventory_hash=source_inventory_hash(mismatched_inventory))
    binding = _command_binding(source_inventory_hash=source_inventory_hash(mismatched_inventory))

    with pytest.raises(GitVersionAuditError, match="package_commit_ref"):
        build_git_version_audit_bundle(
            _builder_input(
                source_inventory=mismatched_inventory,
                git_facts=facts,
                command_evidence_bindings=(binding,),
            )
        )


def test_git_version_audit_rejects_missing_command_evidence_binding() -> None:
    with pytest.raises(GitVersionAuditError, match="command evidence bindings"):
        build_git_version_audit_bundle(_builder_input(command_evidence_bindings=()))


def test_git_version_audit_rejects_orphan_command_evidence_binding() -> None:
    binding = _command_binding(verification_run_ref="verification-run.orphan")

    with pytest.raises(GitVersionAuditError, match="verification runs"):
        build_git_version_audit_bundle(_builder_input(command_evidence_bindings=(_command_binding(), binding)))


def test_git_version_audit_rejects_command_binding_not_declared_in_run_manifest() -> None:
    binding = _command_binding(command_id=ContractId(value="undeclared-command"))

    with pytest.raises(GitVersionAuditError, match="declared command"):
        build_git_version_audit_bundle(_builder_input(command_evidence_bindings=(binding,)))


def test_git_version_audit_rejects_failed_verification_run() -> None:
    ready = _ready_input()
    failed_run = ready.verification_runs[0].model_copy(
        update={"status": VerificationRunStatus.FAILED, "exit_code": 1}
    )

    with pytest.raises(GitVersionAuditError, match="verification runs must pass"):
        build_git_version_audit_bundle(_builder_input(verification_runs=(failed_run,)))


def test_git_version_audit_rejects_hash_manifest_mismatch() -> None:
    bundle = _build_bundle()
    tampered_manifest = bundle.hash_manifest.model_copy(update={"report_hash": _TAMPERED_SHA256})
    tampered_bundle = bundle.model_copy(update={"hash_manifest": tampered_manifest})

    with pytest.raises(GitVersionAuditError, match="hash manifest"):
        git_version_audit_readiness(tampered_bundle)


def test_git_version_audit_readiness_recomputes_report_booleans() -> None:
    bundle = _build_bundle()
    tampered_report = bundle.report.model_copy(
        update={"final_command_evidence_at_final_commit": False}
    )
    tampered_bundle = bundle.model_copy(update={"report": tampered_report})
    tampered_manifest = tampered_bundle.hash_manifest.model_copy(
        update={
            "report_hash": type(tampered_bundle.hash_manifest.report_hash)(
                value=_hash_model(tampered_report)
            ),
        }
    )
    tampered_bundle = tampered_bundle.model_copy(update={"hash_manifest": tampered_manifest})
    tampered_manifest = tampered_bundle.hash_manifest.model_copy(
        update={
            "bundle_payload_hash": type(tampered_bundle.hash_manifest.bundle_payload_hash)(
                value=_hash_jsonable(
                    _bundle_payload_for_hash(
                        bundle_id=tampered_bundle.git_version_audit_bundle_id,
                        project_ref=tampered_bundle.project_ref,
                        generated_at=tampered_bundle.generated_at,
                        fact_set=tampered_bundle.fact_set,
                        command_evidence_bindings=tampered_bundle.command_evidence_bindings,
                        report=tampered_bundle.report,
                        checked_refs=tampered_bundle.checked_refs,
                        hash_manifest_without_bundle_hash={
                            "hash_manifest_id": tampered_bundle.hash_manifest.hash_manifest_id.value,
                            "project_ref": tampered_bundle.hash_manifest.project_ref.value,
                            "fact_set_hash": tampered_bundle.hash_manifest.fact_set_hash.value,
                            "report_hash": tampered_bundle.hash_manifest.report_hash.value,
                            "command_binding_hashes": {
                                key: value.value
                                for key, value in tampered_bundle.hash_manifest.command_binding_hashes.items()
                            },
                        },
                    )
                )
            ),
        }
    )
    tampered_bundle = tampered_bundle.model_copy(update={"hash_manifest": tampered_manifest})

    with pytest.raises(GitVersionAuditError, match="report final command evidence readiness mismatch"):
        git_version_audit_readiness(tampered_bundle)


def test_git_version_audit_rejects_raw_dict_inputs() -> None:
    payload = _builder_input().model_dump(mode="python")

    with pytest.raises(ValidationError, match="package_contract must be PackageContract"):
        GitVersionAuditBuilderInput.model_validate(payload)


def test_git_version_audit_rejects_scalar_tuple_inputs() -> None:
    payload = _builder_input().model_dump(mode="python")
    payload["verification_runs"] = "verification-run.app"

    with pytest.raises(ValidationError, match="verification_runs must be a tuple or list"):
        GitVersionAuditBuilderInput.model_validate(payload)


def test_git_version_audit_rejects_naive_generated_at() -> None:
    with pytest.raises(ValidationError, match="generated_at must include timezone"):
        _git_facts(generated_at=datetime(2026, 5, 24, 12, 0))


def test_git_version_audit_rejects_placeholder_source_inventory_hash() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        _git_facts(source_inventory_hash="a" * 64)


def test_git_audit_adapter_rejects_git_command_failure() -> None:
    transport = FakeGitTransport(
        {
            ("git", "rev-parse", "HEAD"): GitCommandResult(
                command=("git", "rev-parse", "HEAD"),
                cwd="D:/tmp/repo",
                exit_code=128,
                stdout="",
                stderr="not a git repository",
            )
        }
    )
    adapter = GitAuditAdapter(transport=transport)

    with pytest.raises(GitAuditAdapterError, match="git command failed"):
        adapter.collect(
            package_root="10-project",
            project_ref="project-tiny-fullstack",
            cwd="D:/tmp/repo",
            source_inventory_hash=source_inventory_hash(_ready_input().source_inventory),
            base_commit_sha=_BASE_COMMIT_SHA,
            worktree_ref="worktree.final-package",
        )


def test_git_audit_adapter_does_not_expose_arbitrary_git_runner() -> None:
    adapter = GitAuditAdapter(transport=FakeGitTransport({}))

    assert not hasattr(adapter, "run_git")


def test_git_version_audit_bundle_records_clean_final_version() -> None:
    bundle = _build_bundle()

    assert bundle.version == 1
    assert bundle.fact_set.final_commit_sha.value == _FINAL_COMMIT_SHA
    assert bundle.report.package_commit_ref.value == f"package-commit.{_FINAL_COMMIT_SHA}"
    assert bundle.report.source_inventory_hash == source_inventory_hash(_ready_input().source_inventory)
    assert bundle.report.command_evidence_refs == ("verification-run.app",)


def test_git_version_audit_readiness_matches_closeout_gate_contract() -> None:
    readiness = git_version_audit_readiness(_build_bundle())

    assert isinstance(readiness, GitAuditReadiness)
    assert readiness.git_clean is True
    assert readiness.final_commit_sha.value == _FINAL_COMMIT_SHA
    assert readiness.source_inventory_hash_matches is True
    assert readiness.final_command_evidence_at_final_commit is True


def test_git_version_audit_recomputes_source_inventory_hash_deterministically() -> None:
    ready = _ready_input()
    first_hash = source_inventory_hash(ready.source_inventory)
    second_hash = source_inventory_hash(ready.source_inventory)
    changed_inventory = ready.source_inventory.model_copy(
        update={"package_commit_ref": PackageCommitRef(value=f"package-commit.{_OTHER_COMMIT_SHA}")}
    )

    assert first_hash == second_hash
    assert first_hash != source_inventory_hash(changed_inventory)


def test_git_version_audit_hash_manifest_closes_bundle_payload() -> None:
    bundle = _build_bundle()

    assert bundle.hash_manifest.fact_set_hash.value
    assert bundle.hash_manifest.report_hash.value
    assert set(bundle.hash_manifest.command_binding_hashes) == {"git-command-evidence-binding.verification-run.app"}
    assert bundle.bundle_hash == bundle.hash_manifest.bundle_payload_hash.value


def test_git_version_audit_bundle_is_audit_friendly_json() -> None:
    first_bundle = _build_bundle()
    second_bundle = _build_bundle()
    serialized = str(first_bundle.model_dump(mode="json"))

    assert "C:/" not in serialized
    assert "D:/" not in serialized
    assert "\\" not in serialized
    assert ".pytest_tmp" not in serialized
    assert "backend/app/core" not in serialized
    assert first_bundle.git_version_audit_bundle_id == second_bundle.git_version_audit_bundle_id
    assert first_bundle.bundle_hash == second_bundle.bundle_hash


def test_git_version_audit_refs_are_namespaced_by_project_hash_and_run() -> None:
    bundle = _build_bundle()

    assert bundle.git_version_audit_bundle_id.value.startswith(
        f"git-version-audit-bundle.{bundle.project_ref.value}."
    )
    assert bundle.git_version_audit_bundle_id.value.endswith(".run-v2-071e")
    assert bundle.report.git_version_audit_report_id.value.startswith(
        f"git-version-audit-report.{bundle.project_ref.value}."
    )
    assert bundle.report.git_version_audit_report_id.value.endswith(".run-v2-071e")
    assert bundle.hash_manifest.hash_manifest_id.value.startswith(
        f"git-version-audit-hash-manifest.{bundle.project_ref.value}."
    )
    assert bundle.hash_manifest.hash_manifest_id.value.endswith(".run-v2-071e")


def test_git_version_audit_bundle_id_changes_when_run_id_changes() -> None:
    first_bundle = _build_bundle(run_id="run-v2-071e-a")
    second_bundle = _build_bundle(run_id="run-v2-071e-b")

    assert first_bundle.git_version_audit_bundle_id != second_bundle.git_version_audit_bundle_id


    transport = FakeGitTransport(
        {
            ("git", "rev-parse", "HEAD"): GitCommandResult(
                command=("git", "rev-parse", "HEAD"),
                cwd="D:/tmp/repo",
                exit_code=0,
                stdout=f"{_FINAL_COMMIT_SHA}\n",
                stderr="",
            ),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): GitCommandResult(
                command=("git", "rev-parse", "--abbrev-ref", "HEAD"),
                cwd="D:/tmp/repo",
                exit_code=0,
                stdout="main\n",
                stderr="",
            ),
            ("git", "status", "--porcelain=v1", "-z"): GitCommandResult(
                command=("git", "status", "--porcelain=v1", "-z"),
                cwd="D:/tmp/repo",
                exit_code=0,
                stdout="",
                stderr="",
            ),
            ("git", "diff", "--shortstat"): GitCommandResult(
                command=("git", "diff", "--shortstat"),
                cwd="D:/tmp/repo",
                exit_code=0,
                stdout="",
                stderr="",
            ),
            ("git", "tag", "--points-at", "HEAD"): GitCommandResult(
                command=("git", "tag", "--points-at", "HEAD"),
                cwd="D:/tmp/repo",
                exit_code=0,
                stdout="v1.0.0\n",
                stderr="",
            ),
        }
    )
    adapter = GitAuditAdapter(transport=transport)

    facts = adapter.collect(
        package_root="10-project",
        project_ref="project-tiny-fullstack",
        cwd="D:/tmp/repo",
        source_inventory_hash=source_inventory_hash(_ready_input().source_inventory),
        base_commit_sha=_BASE_COMMIT_SHA,
        worktree_ref="worktree.final-package",
        generated_at=_NOW,
    )

    assert facts.final_commit_sha.value == _FINAL_COMMIT_SHA
    assert facts.branch_ref.value == "branch.main"
    assert facts.package_root == "10-project"
    assert facts.worktree_ref.value == "worktree.final-package"
    assert facts.optional_tag_ref.value == "tag.v1.0.0"
    assert transport.commands == [
        ("git", "rev-parse", "HEAD"),
        ("git", "rev-parse", "--abbrev-ref", "HEAD"),
        ("git", "status", "--porcelain=v1", "-z"),
        ("git", "diff", "--shortstat"),
        ("git", "tag", "--points-at", "HEAD"),
    ]
