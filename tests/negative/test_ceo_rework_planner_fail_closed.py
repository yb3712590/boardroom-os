from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef, RolePromptHookSha256
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.rework.model import ReworkDecisionKind
from boardroom_os.rework.planner import (
    CeoReworkPlannerBoundary,
    CeoReworkPlannerError,
    CeoReworkPlannerInput,
    CeoReworkPlannerOutput,
    parse_ceo_rework_planner_payload,
)
from tests.reducers.test_rework_reducer import _patch, _plan, _request

NOW = datetime(2026, 6, 14, 14, 0, tzinfo=UTC)
CEO_HOOK_REF = RolePromptHookRef(value="role-prompt-hook.baseline.ceo.v1")
CEO_HOOK_SHA = RolePromptHookSha256(value="0" * 64)
PLANNER_PACKAGE = ExecutionPackageRef(value="execution-package.ceo.rework-plan")
CEO_ATTEMPT_REF = ProviderAttemptRef(value="provider-attempt.ceo.rework-plan")


def _provider_attempt(
    *,
    attempt_ref: ProviderAttemptRef = CEO_ATTEMPT_REF,
    hook_ref: RolePromptHookRef = CEO_HOOK_REF,
    status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
    outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
) -> ProviderAttempt:
    return ProviderAttempt(
        provider_attempt_id=attempt_ref,
        provider="fake-provider",
        model="gpt-test",
        reasoning_effort="high",
        input_package_ref=PLANNER_PACKAGE,
        seat_ref=AgentSeatRef(value="seat.ceo.delivery"),
        role_prompt_hook_ref=hook_ref,
        role_prompt_hook_version="v1",
        role_prompt_hook_sha256=CEO_HOOK_SHA,
        status=status,
        outcome=outcome,
        started_at=NOW,
        finished_at=NOW,
        raw_output_ref=ProviderArtifactRef(value="provider-artifact.raw.ceo-rework-plan"),
        parsed_output_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        fallback_kind=(
            FallbackKind.PROVIDER_UNAVAILABLE
            if outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT
            else None
        ),
    )


def _planner_input() -> CeoReworkPlannerInput:
    return CeoReworkPlannerInput(
        rework_request=_request(),
        blocker_reports=(),
        current_graph_version=40,
        active_contract_refs=(ContractId(value="acceptance.v2-090f"), ContractId(value="package.v2-090f")),
        active_acceptance_refs=(AcceptanceRef(value="acceptance.book.add"),),
        active_source_surface_refs=(SourceSurfaceRef(value="surface.backend.api"),),
        active_evidence_obligation_refs=(EvidenceObligationRef(value="evidence.add.api"),),
        package_contract_ref=ContractId(value="package.v2-090f"),
        run_manifest_ref="run-manifest.v2-090f",
        planner_execution_package_ref=PLANNER_PACKAGE,
        planner_role_prompt_hook_ref=CEO_HOOK_REF,
    )


def test_ceo_rework_plan_requires_provider_attempt() -> None:
    with pytest.raises(CeoReworkPlannerError, match="provider_attempt is required"):
        CeoReworkPlannerBoundary.validate(
            CeoReworkPlannerOutput(
                planner_input=_planner_input(),
                provider_attempt=None,
                plan=_plan(),
                patch=_patch(),
                parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
                validated_at=NOW,
            )
        )


def test_ceo_rework_plan_requires_ceo_role_prompt_hook() -> None:
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(
            hook_ref=RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
        ),
        plan=_plan(),
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="CEO role prompt hook"):
        CeoReworkPlannerBoundary.validate(output)


def test_ceo_rework_plan_rejects_fallback_provider_attempt() -> None:
    failed_attempt = _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT)

    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=failed_attempt,
        plan=_plan(),
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="primary provider output"):
        CeoReworkPlannerBoundary.validate(output)


def test_ceo_rework_plan_must_map_every_blocker() -> None:
    plan = _plan().model_copy(
        update={
            "decisions": (
                _plan().decisions[0].model_copy(update={"blocker_refs": ()}),
            )
        }
    )
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(),
        plan=plan,
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises((ValidationError, CeoReworkPlannerError), match="blocker"):
        CeoReworkPlannerBoundary.validate(output)


def test_v2_100c_rejects_narrow_scope_until_acceptance_includes_it() -> None:
    decision = _plan().decisions[0].model_copy(
        update={"decision_kind": ReworkDecisionKind.NARROW_SCOPE}
    )
    plan = _plan().model_copy(update={"decisions": (decision,)})
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(),
        plan=plan,
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="not allowed for V2-100C"):
        CeoReworkPlannerBoundary.validate(output)


def test_ceo_graph_patch_rejects_stale_acceptance_refs() -> None:
    operation = _patch().operations[0].model_copy(
        update={"acceptance_refs": (AcceptanceRef(value="AC-TINY-API-BOOK-CREATE"),)}
    )
    patch = _patch().model_copy(update={"operations": (operation,)})
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(),
        plan=_plan(),
        patch=patch,
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="unknown acceptance_ref"):
        CeoReworkPlannerBoundary.validate(output)


def test_ceo_planner_input_contract_refs_must_match_rework_request() -> None:
    planner_input = _planner_input().model_copy(
        update={"active_contract_refs": (ContractId(value="acceptance.second-source"),)}
    )
    output = CeoReworkPlannerOutput(
        planner_input=planner_input,
        provider_attempt=_provider_attempt(),
        plan=_plan(),
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="active_contract_refs mismatch"):
        CeoReworkPlannerBoundary.validate(output)


def test_ceo_planner_rejects_prose_only_output() -> None:
    with pytest.raises(CeoReworkPlannerError, match="single JSON object"):
        parse_ceo_rework_planner_payload(
            {"message": "I will ask the runtime to fix this automatically."}
        )
