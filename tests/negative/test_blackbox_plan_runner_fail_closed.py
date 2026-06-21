from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanApproval,
    BlackboxPlanApprovalRef,
)
from boardroom_os.execution.blackbox_plan_runner import (
    BlackboxActionInputRefHash,
    BlackboxPlanRunner,
    BlackboxPlanRunnerInput,
    BlackboxPlanRunnerStatus,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from tests.evidence.test_blackbox_verification_plan import (
    build_blackbox_plan,
    build_verify_blackbox_execution_package,
)
from tests.execution.test_blackbox_plan_runner import _package_contract


def test_runner_rejects_missing_approved_plan() -> None:
    with pytest.raises(ValueError, match="approved BlackboxVerificationPlan is required"):
        BlackboxPlanRunner().run(build_runner_input(plan=None))


def test_runner_rejects_action_not_in_plan() -> None:
    plan = build_blackbox_plan()

    with pytest.raises(ValueError, match="action is not approved by plan"):
        BlackboxPlanRunner().run_action(
            build_runner_input(plan=plan),
            action_id="action.extra",
        )


def test_http_action_without_executor_routes_blocked_or_escalated() -> None:
    result = BlackboxPlanRunner(http_executor=None).run(
        build_runner_input(
            plan=build_blackbox_plan(),
            approved_action_ids=("action.http.books",),
        )
    )

    assert result.status is BlackboxPlanRunnerStatus.BLOCKED_OR_ESCALATED
    assert result.blocked_reason_code == "executor_missing"
    assert result.facts == ()


def test_runner_rejects_unapproved_plan_action() -> None:
    plan = build_blackbox_plan()

    with pytest.raises(ValueError, match="action is not approved by plan"):
        BlackboxPlanRunner().run_action(
            build_runner_input(
                plan=plan,
                approved_action_ids=("action.command.pytest",),
            ),
            action_id="action.http.books",
        )


def test_runner_rejects_action_missing_input_hash() -> None:
    plan = build_blackbox_plan()

    with pytest.raises(ValueError, match="input ref hashes must cover action input_refs"):
        BlackboxPlanRunner().run_action(
            build_runner_input(plan=plan, input_ref_hashes=()),
            action_id="action.command.pytest",
        )


def test_command_action_must_match_single_declared_execution_command() -> None:
    plan = build_blackbox_plan()
    execution_package = build_verify_blackbox_execution_package().model_copy(
        update={"commands": ()}
    )

    with pytest.raises(ValueError, match="approved command action must match exactly one"):
        BlackboxPlanRunner().run_action(
            build_runner_input(
                plan=plan,
                execution_package=execution_package,
            ),
            action_id="action.command.pytest",
        )


def test_runner_result_cannot_mix_facts_with_blocked_reason() -> None:
    plan = build_blackbox_plan()
    result = BlackboxPlanRunner(http_executor=None).run(
        build_runner_input(
            plan=plan,
            approved_action_ids=("action.command.pytest", "action.http.books"),
        )
    )

    assert result.status is BlackboxPlanRunnerStatus.BLOCKED_OR_ESCALATED
    assert result.blocked_reason_code == "executor_missing"
    assert result.facts == ()


def build_runner_input(
    *,
    plan,
    approved_action_ids: tuple[str, ...] | None = None,
    execution_package=None,
    input_ref_hashes: tuple[BlackboxActionInputRefHash, ...] | None = None,
) -> BlackboxPlanRunnerInput:
    if plan is None:
        return BlackboxPlanRunnerInput.model_construct(plan=None)
    return BlackboxPlanRunnerInput(
        plan=plan,
        approval=BlackboxPlanApproval(
            approval_id=BlackboxPlanApprovalRef(
                value="blackbox-plan-approval.verify.generated"
            ),
            plan_ref=plan.plan_id,
            approved_action_ids=approved_action_ids
            or ("action.command.pytest", "action.http.books"),
            approval_scope="execute_plan_actions_only",
            approved_at=datetime(2026, 6, 21, 10, 3, tzinfo=UTC),
        ),
        execution_package=execution_package or build_verify_blackbox_execution_package(),
        package_contract=_package_contract(),
        package_root=Path("."),
        input_ref_hashes=(
            input_ref_hashes
            if input_ref_hashes is not None
            else (
                BlackboxActionInputRefHash(
                    input_ref=ContextRef(value="contract.package.tiny-fullstack"),
                    sha256=Sha256Hex(value=f"{1:064x}"),
                ),
                BlackboxActionInputRefHash(
                    input_ref=ContextRef(value="context.run-manifest.raw"),
                    sha256=Sha256Hex(value=f"{2:064x}"),
                ),
            )
        ),
        runner_ref=RunnerRef(value="runner.blackbox-plan"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local-python"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.blackbox"),
    )
