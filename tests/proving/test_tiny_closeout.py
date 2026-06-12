from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
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
_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP = pytest.mark.skip(
    reason=(
        "V2-090F public wrapper no longer supports provider artifact lock/materialize "
        "success paths; PRD agent-team runner owns build/check semantics"
    )
)


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
    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
        package_contents=TINY_PACKAGE_CONTENTS,
        provider_fixture=fake_provider_fixture,
        allow_test_provider_transport=True,
    )
    return replace(fixture, workspace_evidence_bundle=None)


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


def _write_valid_provider_lock(output_root: Path) -> None:
    from tests.proving.fixtures.tiny_closeout import (
        _PROVIDER_ARTIFACTS_SAMPLE_DIR,
        _PROVIDER_ATTEMPTS_SAMPLE_PATH,
        _provider_artifact_sample_path,
    )
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)
    attempts_path = output_root / _PROVIDER_ATTEMPTS_SAMPLE_PATH
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_root = output_root / _PROVIDER_ARTIFACTS_SAMPLE_DIR
    artifact_root.mkdir(parents=True, exist_ok=True)
    attempts = []
    for ticket_id, attempt in fixture.provider_attempts_by_ticket_id.items():
        suffix = ticket_id.value.replace("ticket-tiny-", "")
        raw_payload = f"locked provider output for {ticket_id.value}"
        parsed_payload = _locked_parsed_payload(fixture.execution_packages[ticket_id])
        raw_ref = _locked_artifact_ref(kind="raw", suffix=suffix, payload=raw_payload)
        parsed_ref = _locked_artifact_ref(
            kind="parsed",
            suffix=suffix,
            payload=parsed_payload,
        )
        for artifact_ref, payload in (
            (raw_ref, raw_payload),
            (parsed_ref, parsed_payload),
        ):
            artifact_path = output_root / _provider_artifact_sample_path(artifact_ref)
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(payload, encoding="utf-8")
        attempt_payload = attempt.model_dump(mode="json")
        attempt_payload["provider_attempt_id"]["value"] = (
            f"provider-attempt.openai.locked.{suffix}"
        )
        attempt_payload["raw_output_ref"]["value"] = raw_ref
        attempt_payload["parsed_output_ref"]["value"] = parsed_ref
        attempts.append((ticket_id.value, attempt_payload))
    attempts_path.write_text(
        json.dumps(
            [payload for _ticket_id, payload in sorted(attempts)],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _locked_parsed_payload(execution_package) -> str:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    files = {
        path.value: TINY_PACKAGE_CONTENTS[path.value]
        for path in execution_package.allowed_write_set
        if path.value
        not in {
            "package-contract.json",
            "run-manifest.json",
        }
    }
    return json.dumps({"files": files}, ensure_ascii=False, sort_keys=True)


def _locked_artifact_ref(
    *,
    kind: str,
    suffix: str,
    payload: str,
) -> str:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"provider-artifact.openai.{kind}.locked-{suffix}.{digest}"


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


def test_tiny_closeout_fixture_passes_with_live_blackbox_command_evidence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_fixture

    provider_lock_root = tmp_path / "provider-lock"
    provider_lock_root.mkdir()
    _write_valid_provider_lock(provider_lock_root)

    fixture = build_tiny_closeout_fixture(
        package_root=tmp_path / "physical-package-root",
        provider_lock_root=provider_lock_root,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
    )

    assert fixture.closeout_gate_result.verdict is CloseoutGateVerdict.PASSED
    assert fixture.closeout_package.verdict.value == "passed"
    assert {
        binding.command_id.value
        for binding in fixture.closeout_gate_input.final_command_bindings
    } == {
        "run-backend",
        "run-frontend",
        "test-backend",
        "test-integration",
    }
    assert {
        service.command_id.value
        for service in fixture.closeout_gate_input.service_run_evidence
    } == {"run-backend", "run-frontend"}
    assert fixture.package_fixture.workspace_evidence_bundle is not None
    assert fixture.package_fixture.workspace_evidence_bundle.service_run_refs
    assert fixture.package_fixture.workspace_evidence_bundle.live_blackbox_evidence_refs
    assert fixture.process_audit_bundle is not None
    assert fixture.audit_answers is not None


def test_tiny_closeout_gate_blocks_when_live_service_evidence_removed(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import build_tiny_closeout_gate_fixture
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    package_fixture = build_tiny_live_blackbox_fixture(
        package_root=tmp_path / "physical-package-root",
        package_contents=TINY_PACKAGE_CONTENTS,
        provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
        allow_test_provider_transport=True,
    )
    fixture = build_tiny_closeout_gate_fixture(
        package_root=package_fixture.package_root_path,
        package_fixture=package_fixture,
        git_transport=_FakeGitTransport(),
        base_commit_sha=_BASE_COMMIT_SHA,
        allow_fake_provider_for_negative_tests=True,
    )
    remaining_services = tuple(
        service
        for service in fixture.closeout_gate_input.service_run_evidence
        if service.command_id.value != "run-backend"
    )
    tampered_input = fixture.closeout_gate_input.model_copy(
        update={
            "service_run_evidence": remaining_services,
            "final_command_bindings": tuple(
                binding
                for binding in fixture.closeout_gate_input.final_command_bindings
                if binding.command_id.value != "run-backend"
            ),
        }
    )

    result = CloseoutGate().evaluate(tampered_input)

    assert result.verdict is CloseoutGateVerdict.BLOCKED
    assert any(
        blocker.code is CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL
        and blocker.related_ref == "run-backend"
        for blocker in result.blockers
    )


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


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_build_copy_fails_closed_on_invalid_legacy_provider_lock(
    tmp_path: Path,
) -> None:
    from scripts.build_tiny_closeout_sample import _copy_valid_provider_lock_if_available

    source_root = tmp_path / "source" / "tiny-fullstack"
    target_root = tmp_path / "target" / "tiny-fullstack"
    source_root.mkdir(parents=True)
    attempts_path = source_root / "20-evidence/provider-attempts/provider-attempts.json"
    attempts_path.parent.mkdir(parents=True)
    attempts_path.write_text(
        json.dumps(
            [
                {
                    "provider_attempt_id": {"value": "provider-attempt.openai.legacy"},
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "input_package_ref": {"value": "execution-package.legacy"},
                    "seat_ref": {"value": "seat.worker.legacy"},
                    "status": "succeeded",
                    "outcome": "primary_provider_output",
                    "started_at": "2026-06-03T00:00:00Z",
                    "finished_at": "2026-06-03T00:00:01Z",
                    "raw_output_ref": {"value": "provider-artifact.openai.raw.legacy"},
                    "parsed_output_ref": {
                        "value": "provider-artifact.openai.parsed.legacy"
                    },
                    "version": 1,
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    artifact_root = source_root / "20-evidence/provider-artifacts"
    artifact_root.mkdir(parents=True)
    (artifact_root / "provider-artifact.openai.raw.legacy.txt").write_text(
        "raw",
        encoding="utf-8",
    )
    (artifact_root / "provider-artifact.openai.parsed.legacy.txt").write_text(
        '{"files":{}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provider lock is invalid|role prompt hook"):
        _copy_valid_provider_lock_if_available(source_root, target_root)
    assert not (target_root / "20-evidence/provider-attempts").exists()
    assert not (target_root / "20-evidence/provider-artifacts").exists()


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_build_uses_v2_080_failure_package_as_regression_negative(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from scripts import build_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    _copy_existing_tiny_sample(output_root)
    observed: list[tuple[Path, float]] = []

    def fake_provider_build(generated_root: Path, *, timeout_seconds: float):
        observed.append((generated_root, timeout_seconds))
        generated_root.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(
            sample_root=generated_root.as_posix(),
            generated_at="2026-06-03T00:00:00Z",
            run_id="run-test",
            file_count=1,
            total_bytes=1,
            sha256="0" * 64,
            files=("sample-manifest.json",),
        )

    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "_materialize_provider_backed_sample_with_deadline",
        fake_provider_build,
    )
    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "_replace_output_root",
        lambda *, source_root, output_root: None,
    )

    build_tiny_closeout_sample._build_sample(
        output_root,
        provider_deadline_seconds=600,
    )

    assert len(observed) == 1
    assert observed[0][1] == 600


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_build_keeps_valid_v2_090_service_lock(
    tmp_path: Path,
) -> None:
    from scripts.build_tiny_closeout_sample import (
        _build_sample,
        _copy_valid_provider_lock_if_available,
    )

    source_root = tmp_path / "source" / "tiny-fullstack"
    target_root = tmp_path / "target" / "tiny-fullstack"
    source_root.mkdir(parents=True)
    _write_valid_provider_lock(source_root)
    _build_sample(source_root)

    assert _copy_valid_provider_lock_if_available(source_root, target_root) is True
    assert (target_root / "20-evidence/provider-attempts").exists()
    assert (target_root / "20-evidence/provider-artifacts").exists()


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_check_copy_requires_valid_provider_lock(
    tmp_path: Path,
) -> None:
    from scripts.build_tiny_closeout_sample import _copy_required_provider_lock

    source_root = tmp_path / "source" / "tiny-fullstack"
    target_root = tmp_path / "target" / "tiny-fullstack"
    _copy_existing_tiny_sample(source_root)

    with pytest.raises(ValueError, match="provider lock|role prompt hook"):
        _copy_required_provider_lock(source_root, target_root)


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_copy_provider_lock_preserves_context_index(
    tmp_path: Path,
) -> None:
    from scripts.build_tiny_closeout_sample import _copy_provider_lock
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    source_root = tmp_path / "source" / "tiny-fullstack"
    target_root = tmp_path / "target" / "tiny-fullstack"
    _write_valid_provider_lock(source_root)
    materialize_tiny_closeout_sample(
        source_root,
        clean=True,
        allow_absolute_output_root=True,
    )
    context_index_path = source_root / "30-audit/agent-context-index.json"
    context_index = json.loads(context_index_path.read_text(encoding="utf-8"))
    for entry in context_index["entries"]:
        entry["model_execution_profile"]["context_window"] = 300000
    context_index_path.write_text(
        json.dumps(context_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _copy_provider_lock(source_root, target_root)

    copied_context_index = json.loads(
        (target_root / "30-audit/agent-context-index.json").read_text(
            encoding="utf-8"
        )
    )
    assert {
        entry["model_execution_profile"]["context_window"]
        for entry in copied_context_index["entries"]
    } == {300000}


def test_tiny_closeout_sample_provider_settings_disable_transport_retries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from boardroom_os.providers.openai_adapter import OpenAIProviderSettings
    from tests.proving.fixtures import tiny_closeout

    monkeypatch.setattr(
        tiny_closeout,
        "openai_settings_from_test_env",
        lambda: OpenAIProviderSettings(
            api_key="sk-test-secret",
            base_url="https://api.example.invalid/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            timeout_seconds=120,
            max_retries=7,
        ),
    )

    settings = tiny_closeout._sample_provider_settings(tmp_path)

    assert settings.max_retries == 0
    assert settings.timeout_seconds == 120
    assert (
        settings.artifact_store_root
        == tmp_path / "20-evidence/provider-artifacts"
    )


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_build_deadline_uses_provider_env_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from boardroom_os.providers.openai_adapter import OpenAIProviderSettings
    from scripts import build_tiny_closeout_sample

    observed_timeouts: list[float] = []

    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "_copy_valid_provider_lock_if_available",
        lambda _source_root, _target_root: False,
    )
    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "openai_settings_from_test_env",
        lambda: OpenAIProviderSettings(
            api_key="sk-test-secret",
            base_url="https://api.example.invalid/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            timeout_seconds=600,
            max_retries=0,
        ),
        raising=False,
    )

    def fake_provider_build(generated_root: Path, *, timeout_seconds: float):
        observed_timeouts.append(timeout_seconds)
        generated_root.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(
            sample_root=generated_root.as_posix(),
            generated_at="2026-06-03T00:00:00Z",
            run_id="run-test",
            file_count=1,
            total_bytes=1,
            sha256="0" * 64,
            files=("sample-manifest.json",),
        )

    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "_materialize_provider_backed_sample_with_deadline",
        fake_provider_build,
    )
    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "_replace_output_root",
        lambda *, source_root, output_root: None,
    )

    build_tiny_closeout_sample._build_sample(
        tmp_path / "generated-workspaces" / "tiny-fullstack"
    )

    assert observed_timeouts == [600]


def test_tiny_closeout_sample_materializer_rejects_unregistered_runtime_files(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    output_root.mkdir(parents=True)
    _write_valid_provider_lock(output_root)
    cache_dir = output_root / "10-project/backend/__pycache__"
    cache_dir.mkdir(parents=True)
    (cache_dir / "app.cpython-312.pyc").write_bytes(b"cache")

    with pytest.raises(ValueError, match="unregistered runtime file|__pycache__"):
        materialize_tiny_closeout_sample(
            output_root,
            allow_absolute_output_root=True,
        )


def test_tiny_closeout_sample_materializes_live_blackbox_evidence_bundle(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import materialize_tiny_closeout_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    output_root.mkdir(parents=True)
    _write_valid_provider_lock(output_root)

    manifest = materialize_tiny_closeout_sample(
        output_root,
        allow_absolute_output_root=True,
    )

    files = set(manifest.files)
    assert "20-evidence/tests/service-runs.json" in files
    assert "20-evidence/tests/live-blackbox.json" in files
    assert "20-evidence/closeout/final-evidence-table.json" in files
    assert "closeout-package.json" in files
    assert "replay-bundle.json" in files
    assert "git-version-audit-bundle.json" in files
    assert "30-audit/process-audit.md" in files
    assert not any("__pycache__" in path for path in files)
    assert not any(path.endswith(".sqlite3") for path in files)

    closeout = json.loads((output_root / "closeout-package.json").read_text())
    evidence_bundle = json.loads(
        (
            output_root
            / "20-evidence/closeout/evidence-bundle-manifest.json"
        ).read_text()
    )
    assert closeout["verdict"] == "passed"
    assert evidence_bundle["service_run_refs"]
    assert evidence_bundle["live_blackbox_evidence_refs"]


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_script_rebuild_is_stable(
    tmp_path: Path,
) -> None:
    from scripts.build_tiny_closeout_sample import _build_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    output_root.mkdir(parents=True)
    _write_valid_provider_lock(output_root)

    first = _build_sample(output_root)
    first_files = _read_file_tree(output_root)
    second = _build_sample(output_root)
    second_files = _read_file_tree(output_root)

    assert second.sha256 == first.sha256
    assert second.file_count == first.file_count
    assert second.total_bytes == first.total_bytes
    assert second.file_count == len(second.files)
    assert second.file_count < 80
    assert second.total_bytes < 500_000
    assert second_files == first_files


def test_locked_provider_replay_uses_sample_context_window(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import (
        _locked_provider_fixture_from_sample,
        materialize_tiny_closeout_sample,
    )

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    _write_valid_provider_lock(output_root)
    materialize_tiny_closeout_sample(
        output_root,
        clean=True,
        allow_absolute_output_root=True,
    )
    context_index_path = output_root / "30-audit/agent-context-index.json"
    context_index = json.loads(context_index_path.read_text(encoding="utf-8"))
    for entry in context_index["entries"]:
        entry["model_execution_profile"]["context_window"] = 300000
    context_index_path.write_text(
        json.dumps(context_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fixture = _locked_provider_fixture_from_sample(output_root)

    assert fixture is not None
    assert {
        package.model_execution_profile.context_window
        for package in fixture.execution_packages.values()
    } == {300000}


def test_locked_provider_replay_rejects_inconsistent_context_window(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_closeout import (
        _locked_provider_fixture_from_sample,
        materialize_tiny_closeout_sample,
    )

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    _write_valid_provider_lock(output_root)
    materialize_tiny_closeout_sample(
        output_root,
        clean=True,
        allow_absolute_output_root=True,
    )
    context_index_path = output_root / "30-audit/agent-context-index.json"
    context_index = json.loads(context_index_path.read_text(encoding="utf-8"))
    context_index["entries"][0]["model_execution_profile"]["context_window"] = 300000
    context_index["entries"][1]["model_execution_profile"]["context_window"] = 400000
    context_index_path.write_text(
        json.dumps(context_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="context_window.*consistent"):
        _locked_provider_fixture_from_sample(output_root)


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_check_does_not_write_output_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.build_tiny_closeout_sample import _build_sample, _check_sample

    output_root = tmp_path / "generated-workspaces" / "tiny-fullstack"
    output_root.mkdir(parents=True)
    _write_valid_provider_lock(output_root)
    _build_sample(output_root)
    before = _read_file_tree(output_root)

    result = _check_sample(output_root)
    after = _read_file_tree(output_root)
    captured = capsys.readouterr()

    assert result == 0
    assert before == after
    assert "check passed" in captured.out


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_provider_subprocess_deadline_terminates_hangs() -> None:
    import sys

    from scripts.build_tiny_closeout_sample import _run_subprocess_with_deadline

    with pytest.raises(TimeoutError, match="provider-backed sample generation.*deadline"):
        _run_subprocess_with_deadline(
            (
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ),
            timeout_seconds=0.2,
            error_context="provider-backed sample generation",
        )


@_LEGACY_PROVIDER_LOCK_WRAPPER_SKIP
def test_tiny_closeout_sample_deadline_cleanup_targets_process_tree(monkeypatch) -> None:
    import subprocess

    from scripts import build_tiny_closeout_sample

    cleaned: list[int] = []

    class FakePopen:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pid = 4242

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd=("python", "-c", "sleep"), timeout=timeout)

    monkeypatch.setattr(build_tiny_closeout_sample.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        build_tiny_closeout_sample,
        "_terminate_process_tree",
        lambda process: cleaned.append(process.pid),
    )

    with pytest.raises(TimeoutError, match="deadline"):
        build_tiny_closeout_sample._run_subprocess_with_deadline(
            ("python", "-c", "sleep"),
            timeout_seconds=1,
            error_context="provider-backed sample generation",
        )

    assert cleaned == [4242]


def _read_file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
