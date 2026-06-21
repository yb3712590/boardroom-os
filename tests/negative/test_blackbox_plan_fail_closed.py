from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanAction,
    BlackboxPlanActionKind,
    BlackboxPlanApproval,
    BlackboxPlanApprovalRef,
    BlackboxVerificationPlan,
    validate_blackbox_plan_approval,
    validate_blackbox_plan_lineage,
)
from boardroom_os.execution.package import ContextRef, ExecutionPackageRef
from boardroom_os.providers.attempt import ProviderAttemptOutcome
from tests.evidence.test_blackbox_verification_plan import (
    build_blackbox_plan,
    build_provider_attempt,
    build_verify_blackbox_execution_package,
)


def test_blackbox_plan_requires_provider_attempt_for_assigned_execution_package() -> None:
    package = build_verify_blackbox_execution_package(seat_ref="seat.tester.integration")
    plan = build_blackbox_plan(
        execution_package_ref=package.execution_package_id.value,
        producer_attempt_ref="provider-attempt.missing",
        producer_seat_ref=package.seat_ref.value,
    )

    with pytest.raises(ValueError, match="provider attempt could not be resolved"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(),
        )


def test_blackbox_plan_wrong_seat_fails() -> None:
    package = build_verify_blackbox_execution_package(seat_ref="seat.tester.integration")
    attempt = build_provider_attempt(
        execution_package_ref=package.execution_package_id.value,
        seat_ref=package.seat_ref.value,
    )
    plan = build_blackbox_plan(
        execution_package_ref=package.execution_package_id.value,
        producer_attempt_ref=attempt.provider_attempt_id.value,
        producer_seat_ref="seat.worker.implementation",
    )

    with pytest.raises(ValueError, match="producer seat must match execution package"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_rejects_fallback_provider_attempt() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT)
    plan = build_blackbox_plan(producer_attempt_ref=attempt.provider_attempt_id.value)

    with pytest.raises(ValueError, match="provider attempt must be primary provider output"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_rejects_stale_execution_package_ref() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt()
    plan = build_blackbox_plan(execution_package_ref="exec.stale.verify-blackbox")

    with pytest.raises(ValueError, match="plan execution_package_ref must match"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_rejects_provider_attempt_bound_to_stale_package() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt(execution_package_ref="exec.stale.verify-blackbox")
    plan = build_blackbox_plan(producer_attempt_ref=attempt.provider_attempt_id.value)

    with pytest.raises(ValueError, match="provider attempt input_package_ref must match"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_rejects_stale_role_prompt_hook() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt(hook_ref="role-prompt-hook.baseline.worker.v1")
    plan = build_blackbox_plan(producer_attempt_ref=attempt.provider_attempt_id.value)

    with pytest.raises(ValueError, match="provider attempt role prompt hook must match"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_rejects_acceptance_ref_outside_execution_package() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt()
    plan = build_blackbox_plan(
        acceptance_refs=("AC-LIVE-BLACKBOX", "AC-OUTSIDE-CONTRACT")
    )

    with pytest.raises(ValueError, match="plan acceptance refs must be active"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_rejects_context_ref_outside_execution_package() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt()
    plan = build_blackbox_plan(
        input_context_refs=(
            "context.run-manifest.raw",
            "contract.package.tiny-fullstack",
            "context.unassigned",
        ),
    )

    with pytest.raises(ValueError, match="input_context_refs must come from execution package"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_action_requires_acceptance_refs() -> None:
    with pytest.raises(ValidationError, match="acceptance_refs must not be empty"):
        BlackboxPlanAction(
            action_id="action.command.pytest",
            action_kind=BlackboxPlanActionKind.COMMAND,
            description="Run package tests.",
            acceptance_refs=(),
            command=("python", "-m", "pytest"),
            cwd=".",
            required_permissions=("command.run",),
            expected_observations=("Exit code and logs.",),
        )


def test_blackbox_plan_action_requires_expected_observations() -> None:
    with pytest.raises(ValidationError, match="expected_observations must not be empty"):
        BlackboxPlanAction(
            action_id="action.http.books",
            action_kind=BlackboxPlanActionKind.HTTP,
            description="Probe documented endpoint.",
            acceptance_refs=(AcceptanceRef(value="AC-LIVE-BLACKBOX"),),
            method="GET",
            url="http://127.0.0.1:8000/api/books",
            required_permissions=("http.request",),
            expected_observations=(),
        )


def test_blackbox_plan_action_refs_must_be_in_plan_context() -> None:
    base = build_blackbox_plan().model_dump()
    first_action = dict(base["actions"][0])
    first_action["input_refs"] = [{"value": "context.not-in-plan"}]
    base["actions"] = (first_action, *base["actions"][1:])

    with pytest.raises(
        ValidationError,
        match="action input_refs must be a subset of plan input_context_refs",
    ):
        BlackboxVerificationPlan(**base)


def test_blackbox_plan_approval_rejects_action_not_in_plan() -> None:
    plan = build_blackbox_plan()
    approval = BlackboxPlanApproval(
        approval_id=BlackboxPlanApprovalRef(value="blackbox-plan-approval.verify.generated"),
        plan_ref=plan.plan_id,
        approved_action_ids=("action.command.pytest", "action.extra"),
        approval_scope="execute_plan_actions_only",
        approved_at=datetime(2026, 6, 21, 10, 3, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="approved action ids must exist in plan"):
        validate_blackbox_plan_approval(approval, plan=plan)


def test_blackbox_plan_approval_rejects_success_claim_fields() -> None:
    plan = build_blackbox_plan()
    payload = {
        "approval_id": {"value": "blackbox-plan-approval.verify.generated"},
        "plan_ref": plan.plan_id,
        "approved_action_ids": ("action.command.pytest",),
        "approval_scope": "execute_plan_actions_only",
        "approved_at": datetime(2026, 6, 21, 10, 3, tzinfo=UTC),
        "closeout_ready": True,
    }

    with pytest.raises(
        ValidationError,
        match="blackbox plan approval must not contain success claims",
    ):
        BlackboxPlanApproval(**payload)


def test_blackbox_plan_approval_requires_unique_action_ids() -> None:
    plan = build_blackbox_plan()

    with pytest.raises(ValidationError, match="approved_action_ids must be unique"):
        BlackboxPlanApproval(
            approval_id=BlackboxPlanApprovalRef(
                value="blackbox-plan-approval.verify.generated"
            ),
            plan_ref=plan.plan_id,
            approved_action_ids=("action.command.pytest", "action.command.pytest"),
            approval_scope="execute_plan_actions_only",
            approved_at=datetime(2026, 6, 21, 10, 3, tzinfo=UTC),
        )


def test_blackbox_plan_rejects_success_claim_fields() -> None:
    base = build_blackbox_plan().model_dump()
    base["passed"] = True

    with pytest.raises(ValidationError, match="blackbox plan must not contain success claims"):
        BlackboxVerificationPlan(**base)


def test_blackbox_plan_rejects_package_contract_ref_outside_context() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt()
    plan = build_blackbox_plan().model_copy(
        update={
            "package_contract_ref": ContextRef(value="contract.package.other"),
            "execution_package_ref": ExecutionPackageRef(
                value=package.execution_package_id.value
            ),
            "producer_attempt_ref": attempt.provider_attempt_id,
        }
    )

    with pytest.raises(ValueError, match="package_contract_ref must be present"):
        validate_blackbox_plan_lineage(
            plan,
            execution_package=package,
            provider_attempts=(attempt,),
        )


def test_blackbox_plan_requires_timezone_aware_created_at() -> None:
    base = build_blackbox_plan().model_dump()
    base["created_at"] = datetime(2026, 6, 21, 10, 2)

    with pytest.raises(ValidationError, match="created_at must be timezone-aware"):
        BlackboxVerificationPlan(**base)
