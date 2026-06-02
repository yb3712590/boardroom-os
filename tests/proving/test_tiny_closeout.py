from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.audit.process_audit import REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
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
_EXISTING_TINY_SAMPLE_ROOT = Path("examples/generated-workspaces/tiny-fullstack")


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


def _closeout_package_payload(fixture, **overrides):
    payload = {
        "closeout_gate_result": fixture.closeout_gate_result,
        "source_inventory": fixture.source_inventory,
        "final_evidence_table": fixture.package_fixture.final_evidence_table,
        "replay_bundle": fixture.replay_bundle,
        "replay_readiness": fixture.replay_readiness,
        "process_audit_bundle": fixture.process_audit_bundle,
        "process_audit_readiness": fixture.process_audit_readiness,
        "git_version_audit_bundle": fixture.git_version_audit_bundle,
        "git_audit_readiness": fixture.git_audit_readiness,
        "graph_version": fixture.replay_bundle.attestations[0].event_window.last_graph_version,
        "generated_at": fixture.replay_bundle.generated_at,
        "run_id": "run-v2-080f",
    }
    payload.update(overrides)
    return payload


class _NoCloseoutPayloadResolver:
    def resolve_closeout_commit(self, payload_ref):
        raise KeyError(payload_ref.value)

    def resolve_closeout_package(self, closeout_package_ref):
        raise KeyError(closeout_package_ref.value)


def _copy_existing_tiny_sample(output_root: Path) -> None:
    if not _EXISTING_TINY_SAMPLE_ROOT.exists():
        raise AssertionError("existing V2-080 tiny sample is required as regression negative material")
    shutil.copytree(_EXISTING_TINY_SAMPLE_ROOT, output_root)


def test_tiny_closeout_rejects_missing_replay_bundle(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

    gate_result = CloseoutGate().evaluate(
        fixture.closeout_gate_input.model_copy(update={"replay_readiness": None})
    )

    assert gate_result.verdict is CloseoutGateVerdict.BLOCKED
    assert any(
        blocker.code is CloseoutGateBlockerCode.REPLAY_NOT_READY
        for blocker in gate_result.blockers
    )
    with pytest.raises(_VERIFY_ERRORS, match="replay_bundle must be ReplayBundle"):
        payload = _closeout_package_payload(fixture, replay_bundle=None)
        CloseoutPackageBuilderInput.model_validate(
            payload
        )


def test_tiny_closeout_rejects_missing_process_audit(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

    gate_result = CloseoutGate().evaluate(
        fixture.closeout_gate_input.model_copy(update={"process_audit_readiness": None})
    )

    assert gate_result.verdict is CloseoutGateVerdict.BLOCKED
    assert any(
        blocker.code is CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY
        for blocker in gate_result.blockers
    )
    assert fixture.process_audit_bundle is None
    assert fixture.process_audit_readiness is None
    with pytest.raises(_VERIFY_ERRORS, match="process_audit_bundle must be ProcessAuditBundle"):
        payload = _closeout_package_payload(fixture, process_audit_bundle=None)
        CloseoutPackageBuilderInput.model_validate(
            payload
        )


def test_tiny_closeout_rejects_missing_git_audit(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

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
        payload = _closeout_package_payload(fixture, git_version_audit_bundle=None)
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

    with pytest.raises(
        _VERIFY_ERRORS,
        match="fake provider|passed closeout|real provider|closeout gate result",
    ):
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
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )
    assert all(
        event.event_type is not EventType.CLOSEOUT_COMMITTED
        for event in fixture.events_before_closeout
    )

    projection = CloseoutReducer(_NoCloseoutPayloadResolver()).reduce(
        fixture.events_before_closeout,
    )

    assert projection.terminal_status is CloseoutTerminalStatus.OPEN
    assert projection.closeout_package_ref is None
    assert projection.work_product_history_refs


@pytest.mark.parametrize("missing_path", REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)
def test_tiny_closeout_defers_30_audit_artifacts_until_workspace_evidence_bundle_exists(
    tmp_path: Path,
    missing_path: str,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

    assert missing_path in REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
    assert fixture.package_fixture.workspace_evidence_bundle is None
    assert fixture.process_audit_bundle is None
    assert fixture.process_audit_readiness is None
    assert any(
        blocker.code is CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY
        for blocker in fixture.closeout_gate_result.blockers
    )


def test_tiny_closeout_blocks_v2_080_failure_package_missing_run_command_evidence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

    assert fixture.closeout_gate_result.verdict is CloseoutGateVerdict.BLOCKED
    command_blockers = tuple(
        blocker
        for blocker in fixture.closeout_gate_result.blockers
        if blocker.code is CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL
    )
    assert {blocker.related_ref for blocker in command_blockers} >= {
        "run-backend",
        "run-frontend",
    }
    assert all(
        "RUN_MANIFEST_COMMAND_UNVERIFIED" in blocker.message
        or "RUN_MANIFEST_SERVICE_NOT_READY" in blocker.message
        for blocker in command_blockers
    )
    assert {command.command_id.value for command in fixture.package_fixture.run_manifest.commands} == {
        "run-backend",
        "run-frontend",
        "test-backend",
        "test-integration",
    }
    assert {run.command_id.value for run in fixture.verification_runs} == {
        "test-backend",
        "test-integration",
    }
    assert fixture.package_fixture.workspace_evidence_bundle is None
    assert any(
        blocker.code is CloseoutGateBlockerCode.WORKSPACE_EVIDENCE_BUNDLE_NOT_READY
        and blocker.related_ref == "workspace-evidence-bundle.unavailable"
        for blocker in fixture.closeout_gate_result.blockers
    )
    assert all(
        event.event_type is not EventType.CLOSEOUT_COMMITTED
        for event in fixture.events_before_closeout
    )
    with pytest.raises(
        _VERIFY_ERRORS,
        match="closeout gate result must be passed|process_audit_bundle",
    ):
        CloseoutPackageBuilderInput.model_validate(_closeout_package_payload(fixture))
    assert fixture.git_version_audit_bundle.fact_set.base_commit_sha != (
        fixture.git_version_audit_bundle.fact_set.final_commit_sha
    )
    open_projection = CloseoutReducer(_NoCloseoutPayloadResolver()).reduce(
        fixture.events_before_closeout,
    )
    assert open_projection.terminal_status is CloseoutTerminalStatus.OPEN
    assert open_projection.closeout_package_ref is None

    assert fixture.process_audit_bundle is None
    assert fixture.process_audit_readiness is None
    assert replay_bundle_readiness(
        fixture.replay_bundle,
        payload_resolver=fixture.replay_payload_resolver,
    ) == fixture.replay_readiness

    assert fixture.audit_answers is None


def test_tiny_closeout_does_not_write_repo_root_audit_dirs(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

    assert fixture.package_fixture.package_root_path == tmp_path / "physical-package-root"
    assert not (tmp_path / "10-project").exists()
    assert not (tmp_path / "20-evidence").exists()
    assert not (tmp_path / "30-audit").exists()


def test_tiny_closeout_git_commit_excludes_runtime_cache_artifacts(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture

    package_fixture = _build_negative_package_fixture(tmp_path)
    build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )

    tracked = subprocess.run(
        ("git", "ls-tree", "-r", "--name-only", "HEAD"),
        cwd=package_fixture.package_root_path,
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


def test_tiny_closeout_sample_materialization_rejects_v2_080_failure_package(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"

    with pytest.raises(ValueError, match="RUN_MANIFEST_COMMAND_UNVERIFIED"):
        _copy_existing_tiny_sample(output_root)
        materialize_tiny_closeout_sample(
            output_root,
            allow_absolute_output_root=True,
        )

    assert (output_root / "closeout-package.json").exists()


def test_tiny_closeout_sample_materializer_rejects_tampered_provider_artifact_lock(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    _copy_existing_tiny_sample(output_root)
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

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    output_root.parent.mkdir(parents=True)
    output_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="sample output_root must be a directory"):
        materialize_tiny_closeout_sample(
            output_root,
            allow_absolute_output_root=True,
        )
