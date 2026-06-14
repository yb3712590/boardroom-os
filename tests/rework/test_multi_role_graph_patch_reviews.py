from datetime import UTC, datetime

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import ProviderArtifactRef
from boardroom_os.rework.model import (
    GraphPatchApprovalStatus,
    GraphPatchReviewDomain,
    ReworkActorKind,
    ReworkIssue,
    ReworkIssueCode,
)
from boardroom_os.rework.reviewer import (
    GraphPatchReviewerOutput,
    architect_graph_patch_review_input,
    validate_graph_patch_review,
)
from boardroom_os.rework.ticket_graph_patch import (
    RequiredReviewDomainInput,
    build_graph_patch_approval_set,
    derive_ticket_graph_patch_hash,
    infer_required_review_domains,
)
from tests.negative.test_ceo_rework_planner_fail_closed import _provider_attempt
from tests.reducers.test_rework_reducer import _issue, _patch, _review

NOW = datetime(2026, 6, 14, 14, 0, tzinfo=UTC)


def _issue_with_code(code: ReworkIssueCode) -> ReworkIssue:
    return _issue().model_copy(update={"issue_code": code})


def test_probe_response_shape_patch_requires_tester_review() -> None:
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(_issue_with_code(ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH),), operations=(_patch().operations[0],))
    )

    assert domains == (
        GraphPatchReviewDomain.PLANNING,
        GraphPatchReviewDomain.STRUCTURAL,
        GraphPatchReviewDomain.BLOCKER_COVERAGE,
        GraphPatchReviewDomain.BEHAVIORAL_PROBE,
    )


def test_env_binding_patch_requires_release_devops_review() -> None:
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(_issue_with_code(ReworkIssueCode.ENV_BINDING_NOT_CONVERGED),), operations=(_patch().operations[0],))
    )

    assert GraphPatchReviewDomain.RUN_ENV_READINESS in domains


def test_closeout_old_run_patch_requires_fact_chain_review() -> None:
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(_issue_with_code(ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS),), operations=(_patch().operations[0],))
    )

    assert GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN in domains


def test_patch_hash_is_stable_and_changes_with_operations() -> None:
    first = derive_ticket_graph_patch_hash(_patch())
    second = derive_ticket_graph_patch_hash(_patch())
    changed_operation = _patch().operations[0].model_copy(update={"rationale": "Different rationale."})
    changed = derive_ticket_graph_patch_hash(_patch().model_copy(update={"operations": (changed_operation,)}))

    assert first == second
    assert first.startswith("sha256:")
    assert first != changed


def test_approval_set_is_ready_only_after_all_required_reviews() -> None:
    patch = _patch()
    reviews = tuple(
        _review(domain, role)
        for domain, role in (
            (GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            (GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            (GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
            (GraphPatchReviewDomain.BEHAVIORAL_PROBE, ReworkActorKind.TESTER),
        )
    )

    approval_set = build_graph_patch_approval_set(patch, reviews, computed_at=NOW)

    assert approval_set.status is GraphPatchApprovalStatus.READY_TO_COMMIT


def test_architect_review_output_validates_provider_lineage() -> None:
    reviewer_input = architect_graph_patch_review_input(
        patch=_patch(),
        expected_provider_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
    )
    attempt = _provider_attempt(
        hook_ref=RolePromptHookRef(value="role-prompt-hook.baseline.architect.v1"),
    ).model_copy(
        update={
            "input_package_ref": ExecutionPackageRef(value="execution-package.architect.structural.review"),
        }
    )
    output = GraphPatchReviewerOutput(
        reviewer_input=reviewer_input,
        provider_attempt=attempt,
        review=_review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT).model_copy(
            update={"reviewer_attempt_ref": ProviderAttemptRef(value="provider-attempt.ceo.rework-plan")}
        ),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.architect-review"),
        validated_at=NOW,
    )

    assert validate_graph_patch_review(output) == output
