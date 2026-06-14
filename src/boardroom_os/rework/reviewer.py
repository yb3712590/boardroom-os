from __future__ import annotations

from datetime import datetime
from typing import Mapping

from pydantic import BaseModel, ConfigDict, field_validator

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.rework.model import (
    GraphPatchReview,
    GraphPatchReviewDomain,
    ReworkActorKind,
    TicketGraphPatch,
)


class GraphPatchReviewerError(ValueError):
    pass


class GraphPatchReviewerInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patch: TicketGraphPatch
    review_domain: GraphPatchReviewDomain
    reviewer_role_kind: ReworkActorKind
    expected_provider_attempt_ref: ProviderAttemptRef
    reviewer_execution_package_ref: ExecutionPackageRef
    reviewer_role_prompt_hook_ref: RolePromptHookRef


class GraphPatchReviewParsedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review: GraphPatchReview


class GraphPatchReviewerOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer_input: GraphPatchReviewerInput
    provider_attempt: ProviderAttempt | None
    review: GraphPatchReview
    parsed_payload_ref: ProviderArtifactRef
    validated_at: datetime

    @field_validator("validated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validated_at must be timezone-aware")
        return value


def parse_graph_patch_review_payload(payload: Mapping[str, object]) -> GraphPatchReviewParsedPayload:
    if set(payload) != {"review"}:
        raise GraphPatchReviewerError("graph patch reviewer output must be a single JSON object with review")
    try:
        return GraphPatchReviewParsedPayload(review=GraphPatchReview.model_validate(payload["review"]))
    except Exception as exc:
        raise GraphPatchReviewerError("graph patch reviewer output must be a single JSON object with review") from exc


def validate_graph_patch_review(output: GraphPatchReviewerOutput) -> GraphPatchReviewerOutput:
    attempt = output.provider_attempt
    if attempt is None:
        raise GraphPatchReviewerError("provider_attempt is required")
    if attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise GraphPatchReviewerError("provider_attempt must be succeeded")
    if attempt.outcome is not ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT:
        raise GraphPatchReviewerError("provider_attempt must be primary provider output")
    if attempt.provider_attempt_id != output.reviewer_input.expected_provider_attempt_ref:
        raise GraphPatchReviewerError("provider_attempt_id mismatch")
    if attempt.input_package_ref != output.reviewer_input.reviewer_execution_package_ref:
        raise GraphPatchReviewerError("provider input package mismatch")
    if attempt.role_prompt_hook_ref != output.reviewer_input.reviewer_role_prompt_hook_ref:
        raise GraphPatchReviewerError("provider role prompt hook mismatch")
    if output.review.review_domain != output.reviewer_input.review_domain:
        raise GraphPatchReviewerError("review domain mismatch")
    if output.review.reviewer_role_kind != output.reviewer_input.reviewer_role_kind:
        raise GraphPatchReviewerError("reviewer_role_kind mismatch")
    if output.review.ticket_graph_patch_ref != output.reviewer_input.patch.ticket_graph_patch_id:
        raise GraphPatchReviewerError("review patch ref mismatch")
    return output


def _review_input(
    *,
    patch: TicketGraphPatch,
    expected_provider_attempt_ref: ProviderAttemptRef,
    review_domain: GraphPatchReviewDomain,
    reviewer_role_kind: ReworkActorKind,
    hook_ref: str,
) -> GraphPatchReviewerInput:
    return GraphPatchReviewerInput(
        patch=patch,
        review_domain=review_domain,
        reviewer_role_kind=reviewer_role_kind,
        expected_provider_attempt_ref=expected_provider_attempt_ref,
        reviewer_execution_package_ref=ExecutionPackageRef(value=f"execution-package.{reviewer_role_kind.value}.{review_domain.value}.review"),
        reviewer_role_prompt_hook_ref=RolePromptHookRef(value=hook_ref),
    )


def architect_graph_patch_review_input(
    *,
    patch: TicketGraphPatch,
    expected_provider_attempt_ref: ProviderAttemptRef,
) -> GraphPatchReviewerInput:
    return _review_input(
        patch=patch,
        expected_provider_attempt_ref=expected_provider_attempt_ref,
        review_domain=GraphPatchReviewDomain.STRUCTURAL,
        reviewer_role_kind=ReworkActorKind.ARCHITECT,
        hook_ref="role-prompt-hook.baseline.architect.v1",
    )


def checker_graph_patch_review_input(
    *,
    patch: TicketGraphPatch,
    expected_provider_attempt_ref: ProviderAttemptRef,
) -> GraphPatchReviewerInput:
    return _review_input(
        patch=patch,
        expected_provider_attempt_ref=expected_provider_attempt_ref,
        review_domain=GraphPatchReviewDomain.BLOCKER_COVERAGE,
        reviewer_role_kind=ReworkActorKind.CHECKER,
        hook_ref="role-prompt-hook.baseline.checker.v1",
    )


def tester_graph_patch_review_input(
    *,
    patch: TicketGraphPatch,
    expected_provider_attempt_ref: ProviderAttemptRef,
) -> GraphPatchReviewerInput:
    return _review_input(
        patch=patch,
        expected_provider_attempt_ref=expected_provider_attempt_ref,
        review_domain=GraphPatchReviewDomain.BEHAVIORAL_PROBE,
        reviewer_role_kind=ReworkActorKind.TESTER,
        hook_ref="role-prompt-hook.baseline.tester.v1",
    )


def release_devops_graph_patch_review_input(
    *,
    patch: TicketGraphPatch,
    expected_provider_attempt_ref: ProviderAttemptRef,
) -> GraphPatchReviewerInput:
    return _review_input(
        patch=patch,
        expected_provider_attempt_ref=expected_provider_attempt_ref,
        review_domain=GraphPatchReviewDomain.RUN_ENV_READINESS,
        reviewer_role_kind=ReworkActorKind.RELEASE_DEVOPS,
        hook_ref="role-prompt-hook.baseline.release-devops.v1",
    )


def closeout_graph_patch_review_input(
    *,
    patch: TicketGraphPatch,
    expected_provider_attempt_ref: ProviderAttemptRef,
) -> GraphPatchReviewerInput:
    return _review_input(
        patch=patch,
        expected_provider_attempt_ref=expected_provider_attempt_ref,
        review_domain=GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN,
        reviewer_role_kind=ReworkActorKind.CLOSEOUT,
        hook_ref="role-prompt-hook.baseline.closeout.v1",
    )


__all__ = [
    "GraphPatchReviewParsedPayload",
    "GraphPatchReviewerError",
    "GraphPatchReviewerInput",
    "GraphPatchReviewerOutput",
    "architect_graph_patch_review_input",
    "checker_graph_patch_review_input",
    "closeout_graph_patch_review_input",
    "parse_graph_patch_review_payload",
    "release_devops_graph_patch_review_input",
    "tester_graph_patch_review_input",
    "validate_graph_patch_review",
]
