from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.contracts.types import EvidenceObligationRef
from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanAction,
    BlackboxPlanActionKind,
    BlackboxPlanApproval,
    BlackboxPlanApprovalRef,
    BlackboxVerificationPlan,
    BlackboxVerificationPlanRef,
    validate_blackbox_plan_approval,
    validate_blackbox_plan_lineage,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import (
    ContextRef,
    ExecutionPackage,
    ExecutionPackageRef,
    FallbackPolicyRef,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook,
    baseline_role_prompt_hook_fields,
)


VERIFICATION_HOOK_REF = "role-prompt-hook.baseline.tester.v1"


def build_verify_blackbox_execution_package(
    *,
    seat_ref: str = "seat.tester.integration",
    execution_package_id: str = "exec.ticket.verify-blackbox.generated.graph-12",
    hook_ref: str = VERIFICATION_HOOK_REF,
    acceptance_refs: tuple[str, ...] = ("AC-LIVE-BLACKBOX",),
    context_refs: tuple[str, ...] = (
        "context.run-manifest.raw",
        "context.run-manifest.skeleton",
        "contract.package.tiny-fullstack",
        "contract.acceptance.tiny-fullstack",
        "docs.README",
        "surface.backend-api",
        "failure.raw-run-error",
    ),
) -> ExecutionPackage:
    acceptance_ref_values = tuple(AcceptanceRef(value=value) for value in acceptance_refs)
    source_surface_refs = (SourceSurfaceRef(value="surface.backend-api"),)
    return ExecutionPackage(
        execution_package_id=execution_package_id,
        ticket_ref=TicketId(value="ticket.verify-blackbox.generated"),
        graph_version=12,
        seat_ref=AgentSeatRef(value=seat_ref),
        model_execution_profile=ModelExecutionProfile(
            model_execution_profile_id="model.verification.blackbox",
            provider="openai-compatible",
            model="gpt-verifier",
            reasoning_effort="high",
            context_window=200000,
            temperature=0.2,
            tool_permissions=("command.run", "http.request", "filesystem.read"),
            fallback_policy_ref=ContractId(value="fallback.verification.record_failure"),
        ),
        role_prompt_hook=baseline_role_prompt_hook(hook_ref),
        objective="verify-blackbox",
        context_refs=tuple(ContextRef(value=value) for value in context_refs),
        constraints=("RunManifest is context; execute only approved verification plan.",),
        acceptance_refs=acceptance_ref_values,
        source_surface_refs=source_surface_refs,
        allowed_read_refs=tuple(context_refs),
        allowed_write_set=(),
        required_outputs=("blackbox-verification-plan",),
        commands=(
            PackageCommand(
                command_id=ContractId(value="test.backend"),
                label="Run backend tests",
                command=("python", "-m", "pytest"),
                cwd=".",
            ),
        ),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(
                    value="evidence.live-blackbox"
                ),
                acceptance_refs=acceptance_ref_values,
                source_surface_refs=source_surface_refs,
                required_artifact_type=RequiredArtifactType(value="live_blackbox"),
                required_verifier=RequiredVerifier(value="live_blackbox"),
                blocking=True,
            ),
        ),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.verification.record_failure"),
        audit_requirements=("provider_attempt_hook_snapshot_binding",),
    )


def build_provider_attempt(
    *,
    execution_package_ref: str = "exec.ticket.verify-blackbox.generated.graph-12",
    provider_attempt_ref: str = "provider-attempt.verify-blackbox.1",
    seat_ref: str = "seat.tester.integration",
    hook_ref: str = VERIFICATION_HOOK_REF,
    outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
) -> ProviderAttempt:
    fields: dict[str, object] = {
        "provider_attempt_id": ProviderAttemptRef(value=provider_attempt_ref),
        "provider": "openai-compatible",
        "model": "gpt-verifier",
        "reasoning_effort": "high",
        "input_package_ref": ExecutionPackageRef(value=execution_package_ref),
        "seat_ref": AgentSeatRef(value=seat_ref),
        **baseline_role_prompt_hook_fields(hook_ref),
        "status": ProviderAttemptStatus.SUCCEEDED,
        "outcome": outcome,
        "started_at": datetime(2026, 6, 21, 10, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 6, 21, 10, 1, tzinfo=UTC),
        "raw_output_ref": ProviderArtifactRef(value="artifact.provider.raw.blackbox-plan"),
        "parsed_output_ref": ProviderArtifactRef(
            value="artifact.provider.parsed.blackbox-plan"
        ),
    }
    if outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT:
        fields["fallback_kind"] = FallbackKind.PROVIDER_UNAVAILABLE
    return ProviderAttempt(**fields)


def build_blackbox_plan(
    *,
    execution_package_ref: str = "exec.ticket.verify-blackbox.generated.graph-12",
    producer_attempt_ref: str = "provider-attempt.verify-blackbox.1",
    producer_seat_ref: str = "seat.tester.integration",
    acceptance_refs: tuple[str, ...] = ("AC-LIVE-BLACKBOX",),
    input_context_refs: tuple[str, ...] = (
        "context.run-manifest.raw",
        "context.run-manifest.skeleton",
        "contract.package.tiny-fullstack",
        "contract.acceptance.tiny-fullstack",
        "docs.README",
        "surface.backend-api",
        "failure.raw-run-error",
    ),
) -> BlackboxVerificationPlan:
    return BlackboxVerificationPlan(
        plan_id=BlackboxVerificationPlanRef(value="blackbox-plan.verify.generated"),
        execution_package_ref=ExecutionPackageRef(value=execution_package_ref),
        producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
        producer_seat_ref=AgentSeatRef(value=producer_seat_ref),
        role_prompt_hook_ref=baseline_role_prompt_hook(VERIFICATION_HOOK_REF).hook_ref,
        objective="Verify the generated service behavior against active acceptance refs.",
        input_context_refs=tuple(ContextRef(value=value) for value in input_context_refs),
        run_manifest_context_ref=ContextRef(value="context.run-manifest.raw"),
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
        package_contract_ref=ContextRef(value="contract.package.tiny-fullstack"),
        actions=(
            BlackboxPlanAction(
                action_id="action.command.pytest",
                action_kind=BlackboxPlanActionKind.COMMAND,
                description="Run the package test command declared by the package contract.",
                acceptance_refs=tuple(
                    AcceptanceRef(value=value) for value in acceptance_refs
                ),
                input_refs=(ContextRef(value="contract.package.tiny-fullstack"),),
                command=("python", "-m", "pytest"),
                cwd=".",
                required_permissions=("command.run",),
                expected_observations=("Command exit code and captured stdout/stderr.",),
            ),
            BlackboxPlanAction(
                action_id="action.http.books",
                action_kind=BlackboxPlanActionKind.HTTP,
                description="Probe the documented books API without treating manifest prose as evidence.",
                acceptance_refs=tuple(
                    AcceptanceRef(value=value) for value in acceptance_refs
                ),
                input_refs=(ContextRef(value="context.run-manifest.raw"),),
                method="GET",
                url="http://127.0.0.1:8000/api/books",
                required_permissions=("http.request",),
                expected_observations=("HTTP status and response body shape.",),
            ),
        ),
        evidence_obligation_refs=(
            EvidenceObligationRef(value="evidence.live-blackbox"),
        ),
        created_at=datetime(2026, 6, 21, 10, 2, tzinfo=UTC),
    )


def test_provider_backed_plan_matches_assigned_execution_package_lineage() -> None:
    package = build_verify_blackbox_execution_package()
    attempt = build_provider_attempt()
    plan = build_blackbox_plan()

    validated = validate_blackbox_plan_lineage(
        plan,
        execution_package=package,
        provider_attempts=(attempt,),
    )

    assert validated == plan
    assert validated.producer_attempt_ref == attempt.provider_attempt_id
    assert validated.producer_seat_ref == package.seat_ref
    assert validated.role_prompt_hook_ref == package.role_prompt_hook.hook_ref
    assert validated.run_manifest_context_ref in package.context_refs


def test_blackbox_plan_serializes_lineage_without_success_claims() -> None:
    plan = build_blackbox_plan()

    payload = plan.model_dump(mode="json")

    assert payload["execution_package_ref"] == {
        "value": "exec.ticket.verify-blackbox.generated.graph-12"
    }
    assert payload["producer_attempt_ref"] == {
        "value": "provider-attempt.verify-blackbox.1"
    }
    assert payload["producer_seat_ref"] == {"value": "seat.tester.integration"}
    assert "passed" not in payload
    assert "approved" not in payload
    assert "closeout_ready" not in payload


def test_blackbox_plan_approval_only_marks_plan_actions_executable() -> None:
    plan = build_blackbox_plan()
    approval = BlackboxPlanApproval(
        approval_id=BlackboxPlanApprovalRef(value="blackbox-plan-approval.verify.generated"),
        plan_ref=plan.plan_id,
        approved_action_ids=("action.command.pytest", "action.http.books"),
        approval_scope="execute_plan_actions_only",
        approved_at=datetime(2026, 6, 21, 10, 3, tzinfo=UTC),
    )

    validated = validate_blackbox_plan_approval(approval, plan=plan)

    assert validated == approval
    assert validated.plan_ref == plan.plan_id
    assert set(validated.approved_action_ids) == {
        "action.command.pytest",
        "action.http.books",
    }
