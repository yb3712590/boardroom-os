from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.audit.process_audit import (
    REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS,
    process_audit_readiness,
)
from boardroom_os.audit.replay_bundle import replay_bundle_readiness
from boardroom_os.adapters.git_audit import GitAuditAdapter, GitCommandResult
from boardroom_os.closeout.gate import (
    CloseoutGate,
    CloseoutGateBlockerCode,
    CloseoutGateVerdict,
)
from boardroom_os.closeout.package import CloseoutPackageBuilderInput
from boardroom_os.events.types import EventType
from boardroom_os.reducers.closeout_reducer import (
    CloseoutReducer,
    CloseoutReducerError,
    CloseoutTerminalStatus,
)

_VERIFY_ERRORS = (ValueError, ValidationError)
_BASE_COMMIT_SHA = "abcdef0123456789abcdef0123456789abcdef01"
_FINAL_COMMIT_SHA = "fedcba9876543210fedcba9876543210fedcba98"


class _FakeGitTransport:
    def __init__(self, *, status_output: str = "") -> None:
        self.status_output = status_output
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        self.commands.append(command)
        outputs = {
            ("git", "rev-parse", "HEAD"): _FINAL_COMMIT_SHA,
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): "tiny-package-final",
            ("git", "status", "--porcelain=v1", "-z"): self.status_output,
            ("git", "diff", "--shortstat"): (
                " 1 file changed, 1 insertion(+)\n" if self.status_output else ""
            ),
            ("git", "tag", "--points-at", "HEAD"): "",
        }
        return GitCommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout=outputs[command],
            stderr="",
        )


class _ChangingHeadGitTransport(_FakeGitTransport):
    def __init__(self) -> None:
        super().__init__()
        self._head_calls = 0

    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        if command == ("git", "rev-parse", "HEAD"):
            self.commands.append(command)
            self._head_calls += 1
            stdout = (
                "0123456789abcdef0123456789abcdef01234567"
                if self._head_calls == 1
                else _FINAL_COMMIT_SHA
            )
            return GitCommandResult(
                command=command,
                cwd=cwd,
                exit_code=0,
                stdout=stdout,
                stderr="",
            )
        return super().run(command, cwd=cwd)


def _build_negative_package_fixture(tmp_path: Path):
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_package_assembly_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    fake_provider_fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)
    return build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
        package_contents=TINY_PACKAGE_CONTENTS,
        provider_fixture=fake_provider_fixture,
        allow_fake_provider_for_negative_tests=True,
    )


def test_tiny_closeout_rejects_missing_replay_bundle(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")

    gate_result = CloseoutGate().evaluate(
        fixture.closeout_gate_input.model_copy(update={"replay_readiness": None})
    )

    assert gate_result.verdict is CloseoutGateVerdict.BLOCKED
    assert any(
        blocker.code is CloseoutGateBlockerCode.REPLAY_NOT_READY
        for blocker in gate_result.blockers
    )
    with pytest.raises(_VERIFY_ERRORS, match="replay_bundle must be ReplayBundle"):
        payload = fixture.closeout_package_input.model_dump(mode="python")
        payload["replay_bundle"] = None
        CloseoutPackageBuilderInput.model_validate(
            payload
        )


def test_tiny_closeout_rejects_missing_process_audit(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")

    gate_result = CloseoutGate().evaluate(
        fixture.closeout_gate_input.model_copy(update={"process_audit_readiness": None})
    )

    assert gate_result.verdict is CloseoutGateVerdict.BLOCKED
    assert any(
        blocker.code is CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY
        for blocker in gate_result.blockers
    )
    with pytest.raises(_VERIFY_ERRORS, match="process_audit_bundle must be ProcessAuditBundle"):
        payload = fixture.closeout_package_input.model_dump(mode="python")
        payload["process_audit_bundle"] = None
        CloseoutPackageBuilderInput.model_validate(
            payload
        )


def test_tiny_closeout_rejects_missing_git_audit(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")

    gate_result = CloseoutGate().evaluate(
        fixture.closeout_gate_input.model_copy(update={"git_audit_readiness": None})
    )

    assert gate_result.verdict is CloseoutGateVerdict.BLOCKED
    assert any(
        blocker.code is CloseoutGateBlockerCode.GIT_AUDIT_NOT_READY
        for blocker in gate_result.blockers
    )
    with pytest.raises(
        _VERIFY_ERRORS,
        match="git_version_audit_bundle must be GitVersionAuditBundle",
    ):
        payload = fixture.closeout_package_input.model_dump(mode="python")
        payload["git_version_audit_bundle"] = None
        CloseoutPackageBuilderInput.model_validate(
            payload
        )


def test_tiny_closeout_rejects_dirty_git_adapter_facts_before_closeout(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    transport = _FakeGitTransport(status_output=" M 10-project/backend/app.py\0")
    package_fixture = _build_negative_package_fixture(tmp_path)

    with pytest.raises(_VERIFY_ERRORS, match="git facts must be clean|git audit"):
        build_tiny_closeout_fixture(
            package_root=package_fixture.package_root_path,
            package_fixture=package_fixture,
            git_transport=transport,
            base_commit_sha=_BASE_COMMIT_SHA,
            allow_fake_provider_for_negative_tests=True,
        )

    assert ("git", "status", "--porcelain=v1", "-z") in transport.commands


def test_tiny_git_audit_adapter_uses_transport_for_final_commit_without_closeout(
    tmp_path: Path,
) -> None:
    transport = _FakeGitTransport()

    facts = GitAuditAdapter(transport=transport).collect(
        package_root="10-project",
        project_ref="project-tiny-book-tracker",
        cwd=str(tmp_path),
        source_inventory_hash=hashlib.sha256(b"tiny-source-inventory").hexdigest(),
        base_commit_sha=_BASE_COMMIT_SHA,
        worktree_ref="worktree.test",
    )

    assert ("git", "rev-parse", "HEAD") in transport.commands
    assert ("git", "status", "--porcelain=v1", "-z") in transport.commands
    assert facts.final_commit_sha.value == _FINAL_COMMIT_SHA
    assert facts.base_commit_sha.value == _BASE_COMMIT_SHA
    assert facts.git_clean is True


def test_tiny_closeout_rejects_fake_provider_even_with_clean_injected_git_facts(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)

    with pytest.raises(_VERIFY_ERRORS, match="fake provider|passed closeout|real provider"):
        build_tiny_closeout_fixture(
            package_root=package_fixture.package_root_path,
            package_fixture=package_fixture,
            git_transport=_FakeGitTransport(),
            base_commit_sha=_BASE_COMMIT_SHA,
            allow_fake_provider_for_negative_tests=True,
        )


def test_tiny_closeout_rejects_missing_base_commit_for_injected_git_audit(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)

    with pytest.raises(_VERIFY_ERRORS, match="base_commit_sha|base commit"):
        build_tiny_closeout_fixture(
            package_root=package_fixture.package_root_path,
            package_fixture=package_fixture,
            git_transport=_FakeGitTransport(),
            allow_fake_provider_for_negative_tests=True,
        )


def test_tiny_closeout_rejects_final_commit_changed_between_inventory_and_git_audit(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    transport = _ChangingHeadGitTransport()
    package_fixture = _build_negative_package_fixture(tmp_path)

    with pytest.raises(_VERIFY_ERRORS, match="package_commit_ref|final commit"):
        build_tiny_closeout_fixture(
            package_root=package_fixture.package_root_path,
            package_fixture=package_fixture,
            git_transport=transport,
            base_commit_sha=_BASE_COMMIT_SHA,
            allow_fake_provider_for_negative_tests=True,
        )


def test_tiny_closeout_rejects_fake_provider_attempt_refs(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture
    package_fixture = _build_negative_package_fixture(tmp_path)

    with pytest.raises(_VERIFY_ERRORS, match="fake provider|ProviderAttempt|real provider"):
        build_tiny_closeout_fixture(
            package_root=package_fixture.package_root_path,
            package_fixture=package_fixture,
            git_transport=_FakeGitTransport(),
            base_commit_sha=_BASE_COMMIT_SHA,
        )


def test_tiny_work_product_submitted_does_not_replace_closeout(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")
    assert all(
        event.event_type is not EventType.CLOSEOUT_COMMITTED
        for event in fixture.events_before_closeout
    )

    projection = CloseoutReducer(fixture.closeout_payload_resolver).reduce(
        fixture.events_before_closeout,
    )

    assert projection.terminal_status is CloseoutTerminalStatus.OPEN
    assert projection.closeout_package_ref is None
    assert projection.work_product_history_refs


@pytest.mark.parametrize("missing_path", REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)
def test_tiny_closeout_rejects_missing_required_30_audit_artifact(
    tmp_path: Path,
    missing_path: str,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")
    broken_bundle = fixture.process_audit_bundle.model_copy(
        update={
            "artifacts": tuple(
                artifact
                for artifact in fixture.process_audit_bundle.artifacts
                if artifact.path.value != missing_path
            )
        }
    )

    with pytest.raises(_VERIFY_ERRORS, match="artifact|required|process audit"):
        process_audit_readiness(broken_bundle)


def test_tiny_closeout_passes_with_replay_process_git_and_reducer_projection(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")

    assert fixture.closeout_gate_result.verdict is CloseoutGateVerdict.PASSED
    assert fixture.closeout_gate_result.blockers == ()
    assert fixture.closeout_package.verdict.value == "passed"
    assert fixture.git_version_audit_bundle.fact_set.base_commit_sha != (
        fixture.git_version_audit_bundle.fact_set.final_commit_sha
    )
    assert fixture.closeout_projection.terminal_status is CloseoutTerminalStatus.SUCCEEDED
    assert (
        fixture.closeout_projection.closeout_package_ref
        == fixture.closeout_package.closeout_package_id
    )

    assert {artifact.path.value for artifact in fixture.process_audit_bundle.artifacts} == set(
        REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
    )
    assert replay_bundle_readiness(
        fixture.replay_bundle,
        payload_resolver=fixture.replay_payload_resolver,
    ) == fixture.replay_readiness

    audit_answers = fixture.audit_answers
    assert audit_answers.timeline_event_count >= len(fixture.events_before_closeout)
    assert audit_answers.agent_decision_count >= 1
    assert audit_answers.agent_context_entry_count == len(
        fixture.package_fixture.provider_attempts_by_ticket_id
    )
    assert {entry.path.value for entry in fixture.source_inventory.entries}.issubset(
        set(audit_answers.artifact_paths)
    )
    assert audit_answers.git_final_commit_sha == fixture.git_audit_readiness.final_commit_sha.value
    assert set(audit_answers.evidence_map_acceptance_refs) == {
        row.acceptance_ref.value for row in fixture.package_fixture.final_evidence_table.rows
    }


def test_tiny_closeout_does_not_write_repo_root_audit_dirs(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")

    assert fixture.package_fixture.package_root_path == tmp_path / "physical-package-root"
    assert not (tmp_path / "10-project").exists()
    assert not (tmp_path / "20-evidence").exists()
    assert not (tmp_path / "30-audit").exists()


def test_tiny_closeout_git_commit_excludes_runtime_cache_artifacts(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    fixture = build_tiny_closeout_fixture(package_root=tmp_path / "physical-package-root")

    tracked = subprocess.run(
        ("git", "ls-tree", "-r", "--name-only", "HEAD"),
        cwd=fixture.package_fixture.package_root_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, tracked.stderr
    tracked_paths = set(tracked.stdout.splitlines())

    assert not any(path.startswith(".pytest") for path in tracked_paths)
    assert not any("__pycache__" in path for path in tracked_paths)
    assert "backend/app.py" in tracked_paths
    assert "tests/integration/test_frontend_backend.py" in tracked_paths


def test_tiny_closeout_sample_materialization_is_stable_and_bounded(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    first = materialize_tiny_closeout_sample(
        output_root,
        allow_absolute_output_root=True,
    )
    first_files = {
        path.relative_to(output_root).as_posix(): path.read_bytes()
        for path in output_root.rglob("*")
        if path.is_file()
    }
    second = materialize_tiny_closeout_sample(
        output_root,
        allow_absolute_output_root=True,
    )
    second_files = {
        path.relative_to(output_root).as_posix(): path.read_bytes()
        for path in output_root.rglob("*")
        if path.is_file()
    }

    assert first == second
    assert first.file_count == 39
    assert first.total_bytes < 400_000
    assert first_files == second_files
    assert len(second_files) == 40
    assert len(
        [
            path
            for path in second_files
            if path.startswith("20-evidence/provider-artifacts/")
        ]
    ) == 8
    assert not (output_root / "00-boardroom").exists()
    assert {path.as_posix() for path in (output_root / "30-audit").iterdir()} == {
        (output_root / required_path).as_posix()
        for required_path in REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
    }

    manifest = json.loads((output_root / "sample-manifest.json").read_text(encoding="utf-8"))
    assert first.sha256 == manifest["sha256"]
    assert manifest["files"] == list(first.files)
    assert manifest["sample_root"] == "examples/generated-workspaces/tiny-fullstack"


def test_tiny_closeout_sample_materializer_rejects_tampered_provider_artifact_lock(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    materialize_tiny_closeout_sample(
        output_root,
        allow_absolute_output_root=True,
    )
    artifact_path = next((output_root / "20-evidence/provider-artifacts").glob("*.txt"))
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8") + "\n# tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provider artifact lock hash mismatch"):
        materialize_tiny_closeout_sample(
            output_root,
            allow_absolute_output_root=True,
        )


def test_tiny_closeout_sample_materializer_rejects_tampered_provider_hook_lineage(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import (
        _PROVIDER_ATTEMPTS_SAMPLE_PATH,
        _PROVIDER_ARTIFACTS_SAMPLE_DIR,
        _locked_provider_fixture_from_sample,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    output_root.mkdir(parents=True)
    fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)
    attempts = [
        attempt.model_dump(mode="json")
        for _ticket_id, attempt in sorted(
            fixture.provider_attempts_by_ticket_id.items(),
            key=lambda item: item[0].value,
        )
    ]
    attempts[0]["role_prompt_hook_sha256"]["value"] = "0" * 64
    attempts_path = output_root / _PROVIDER_ATTEMPTS_SAMPLE_PATH
    attempts_path.parent.mkdir(parents=True)
    attempts_path.write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / _PROVIDER_ARTIFACTS_SAMPLE_DIR).mkdir(parents=True)

    with pytest.raises(ValueError, match="role prompt hook lineage"):
        _locked_provider_fixture_from_sample(output_root)


@pytest.mark.parametrize(
    "unsafe_output",
    [
        Path("10-project"),
        Path("20-evidence/tiny"),
        Path("30-audit"),
        Path("examples/generated-workspaces/other"),
        Path("../outside"),
    ],
)
def test_tiny_closeout_sample_materializer_rejects_unsafe_output_roots(
    unsafe_output: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    with pytest.raises(ValueError, match="sample output_root|runtime directory|tiny-fullstack"):
        materialize_tiny_closeout_sample(unsafe_output)


def test_tiny_closeout_sample_materializer_rejects_file_output_root(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "tiny-fullstack"
    output_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="sample output_root must be a directory"):
        materialize_tiny_closeout_sample(
            output_root,
            allow_absolute_output_root=True,
        )
