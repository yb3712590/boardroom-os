from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from boardroom_os.adapters.process_runner import ProcessResult
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import ContractId, SourceSurfaceRef
from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanApproval,
    BlackboxPlanApprovalRef,
)
from boardroom_os.execution.blackbox_plan_runner import (
    BlackboxActionExecutionFactRef,
    BlackboxActionExecutorResult,
    BlackboxActionInputRefHash,
    BlackboxPlanRunner,
    BlackboxPlanRunnerInput,
    BlackboxPlanRunnerStatus,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRunRef,
    VerificationRunStatus,
    WorkspaceSnapshotRef,
)
from tests.evidence.test_blackbox_verification_plan import (
    build_blackbox_plan,
    build_verify_blackbox_execution_package,
)
from tests.execution.test_command_runner import CapturingProcessExecutor, SequenceClock


def test_runner_executes_approved_command_action_through_command_runner(
    tmp_path: Path,
) -> None:
    plan = build_blackbox_plan()
    execution_package = build_verify_blackbox_execution_package()
    process_executor = CapturingProcessExecutor(
        ProcessResult(exit_code=0, stdout="ok\n", stderr="")
    )
    runner = BlackboxPlanRunner(
        process_executor=process_executor,
        clock=SequenceClock(_started_at(), _finished_at()),
    )

    result = runner.run(
        _runner_input(
            plan=plan,
            execution_package=execution_package,
            package_contract=_package_contract(),
            package_root=tmp_path,
            approved_action_ids=("action.command.pytest",),
        )
    )

    assert result.status is BlackboxPlanRunnerStatus.FACTS_RECORDED
    assert result.blocked_reason_code is None
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.fact_id == BlackboxActionExecutionFactRef(
        value=(
            "blackbox-action-fact."
            "blackbox-plan.verify.generated."
            "action.command.pytest"
        )
    )
    assert fact.plan_ref == plan.plan_id
    assert fact.action_id == "action.command.pytest"
    assert fact.action_kind.value == "command"
    assert fact.command == ("python", "-m", "pytest")
    assert fact.cwd == "."
    assert fact.verification_run_ref == VerificationRunRef(
        value=(
            "verification-run."
            "exec.ticket.verify-blackbox.generated.graph-12."
            "test.backend"
        )
    )
    assert fact.exit_code == 0
    assert fact.status_text == "passed"
    assert fact.stdout_ref is not None
    assert fact.stderr_ref is not None
    assert fact.acceptance_refs == plan.acceptance_refs
    assert fact.package_contract_ref == plan.package_contract_ref
    assert fact.input_ref_hashes == _input_hashes("contract.package.tiny-fullstack")
    assert fact.started_at == _started_at()
    assert fact.finished_at == _finished_at()
    assert process_executor.commands == [("python", "-m", "pytest")]
    assert process_executor.cwd_values == [tmp_path.resolve()]


def test_runner_executes_configured_http_action_as_authoritative_fact() -> None:
    plan = build_blackbox_plan()
    execution_package = build_verify_blackbox_execution_package()
    http_executor = RecordingHttpExecutor(
        BlackboxActionExecutorResult(
            status_code=404,
            body_ref="artifact.http.books.body",
            observed_ref="artifact.http.books.observed",
        )
    )
    runner = BlackboxPlanRunner(http_executor=http_executor)

    result = runner.run(
        _runner_input(
            plan=plan,
            execution_package=execution_package,
            package_contract=_package_contract(),
            approved_action_ids=("action.http.books",),
        )
    )

    assert result.status is BlackboxPlanRunnerStatus.FACTS_RECORDED
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.action_id == "action.http.books"
    assert fact.action_kind.value == "http"
    assert fact.method == "GET"
    assert fact.url == "http://127.0.0.1:8000/api/books"
    assert fact.http_status == 404
    assert fact.body_ref == "artifact.http.books.body"
    assert fact.artifact_refs == ("artifact.http.books.observed",)
    assert http_executor.calls == [("GET", "http://127.0.0.1:8000/api/books")]


class RecordingHttpExecutor:
    def __init__(self, result: BlackboxActionExecutorResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    def execute_http(self, *, method: str, url: str) -> BlackboxActionExecutorResult:
        self.calls.append((method, url))
        return self._result


def _runner_input(
    *,
    plan,
    execution_package=None,
    package_contract=None,
    approved_action_ids: tuple[str, ...],
    package_root: Path | None = None,
) -> BlackboxPlanRunnerInput:
    return BlackboxPlanRunnerInput(
        plan=plan,
        approval=BlackboxPlanApproval(
            approval_id=BlackboxPlanApprovalRef(
                value="blackbox-plan-approval.verify.generated"
            ),
            plan_ref=plan.plan_id,
            approved_action_ids=approved_action_ids,
            approval_scope="execute_plan_actions_only",
            approved_at=datetime(2026, 6, 21, 10, 3, tzinfo=UTC),
        ),
        execution_package=execution_package or build_verify_blackbox_execution_package(),
        package_contract=package_contract or _package_contract(),
        package_root=package_root or Path("."),
        input_ref_hashes=_input_hashes(
            "contract.package.tiny-fullstack",
            "context.run-manifest.raw",
        ),
        runner_ref=RunnerRef(value="runner.blackbox-plan"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local-python"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.blackbox"),
    )


def _input_hashes(*refs: str) -> tuple[BlackboxActionInputRefHash, ...]:
    return tuple(
        BlackboxActionInputRefHash(
            input_ref=ContextRef(value=ref),
            sha256=Sha256Hex(
                value=f"{index + 1:064x}",
            ),
        )
        for index, ref in enumerate(refs)
    )


def _package_contract() -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract.tiny-fullstack"),
        project_charter_ref=ContractId(value="charter.tiny-fullstack"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="surface.backend-api"),
                name="Backend API",
                paths=("backend",),
                owned_by=OwnerSeatRef(value="owner.backend"),
                acceptance_refs=build_blackbox_plan().acceptance_refs,
                required_tests=(RequiredTestRef(value="test.backend"),),
            ),
        ),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run.backend"),
                label="Run backend",
                command=("python", "-m", "app"),
                cwd=".",
            ),
        ),
        test_commands=(
            PackageCommand(
                command_id=ContractId(value="test.backend"),
                label="Run backend tests",
                command=("python", "-m", "pytest"),
                cwd=".",
            ),
        ),
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=False,
        closeout_required=True,
    )


def _started_at() -> datetime:
    return datetime(2026, 6, 21, 10, 4, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 6, 21, 10, 4, 1, tzinfo=UTC)
