from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import RoleCategory, SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import AcceptanceRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
from boardroom_os.execution.work_product import (
    WorkProduct,
    WorkProductArtifactRef,
    WorkProductBuildError,
    WorkProductClaimDraft,
    WorkProductClaimDraftRef,
    WorkProductRef,
    WorkProductSubmission,
    build_work_product_from_provider_attempt,
    build_work_product_submitted_event,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId, TicketStatus
from boardroom_os.providers.adapter import (
    FakeProviderTransport,
    ProviderRequest,
    ProviderResponse,
)
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.reducers.errors import TicketReducerError
from boardroom_os.reducers.ticket_reducer import (
    TicketCompletionSnapshot,
    TicketReducer,
    TicketRefPayload,
)
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook,
    baseline_role_prompt_hook_fields,
)


def _work_product_fields() -> dict[str, object]:
    return {
        "work_product_id": {"value": "work-product.backend.1"},
        "execution_package_ref": "exec.ticket.backend.1",
        "ticket_ref": {"value": "ticket.backend"},
        "producer_attempt_ref": "provider-attempt.1",
        "artifact_refs": ("artifact.patch.1",),
        "claim_refs": ({"value": "claim-draft.backend.1"},),
        "summary": "Implemented backend API.",
    }


def _claim_draft_fields() -> dict[str, object]:
    return {
        "claim_draft_ref": "claim-draft.backend.1",
        "producer_attempt_ref": {"value": "provider-attempt.1"},
        "execution_package_ref": "exec.ticket.backend.1",
        "ticket_ref": "ticket.backend",
        "acceptance_refs": ("AC-BACKEND",),
        "source_surface_refs": ({"value": "surface.backend"},),
        "artifact_refs": ("artifact.patch.1",),
        "summary": "Evidence claim draft for backend API.",
    }


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("provider.invoke",),
        fallback_policy_ref="fallback-policy.default",
    )


def _package_command() -> PackageCommand:
    return PackageCommand(
        command_id={"value": "command.test"},
        label="Run tests",
        command=("pytest",),
        cwd=".",
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id={"value": "evidence-obligation.backend-api"},
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND-API"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend-api"),),
        required_artifact_type=RequiredArtifactType(value="source"),
        required_verifier={"value": "source_inventory"},
        blocking=True,
    )


def _execution_package() -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id="execution-package.backend-api",
        ticket_ref="ticket.backend-api",
        graph_version=7,
        seat_ref="seat.worker.backend",
        model_execution_profile=_model_execution_profile(),
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Implement the backend API.",
        context_refs=("context.project-charter",),
        constraints=("Stay inside allowed write set.",),
        acceptance_refs=("AC-BACKEND-API",),
        source_surface_refs=("surface.backend-api",),
        allowed_read_refs=("read.contracts",),
        allowed_write_set=("backend/app.py",),
        required_outputs=("backend source files",),
        commands=(_package_command(),),
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref="fallback-policy.default",
        audit_requirements=("record work product lineage",),
    )


def _fake_provider_attempt() -> ProviderAttempt:
    execution_package = _execution_package()
    transport = FakeProviderTransport(
        response=ProviderResponse(
            raw_output_ref="provider-artifact.raw.backend-api",
            parsed_output_ref="provider-artifact.parsed.backend-api",
            summary="Implemented backend API.",
        ),
        attempt_id="provider-attempt.backend-api",
        started_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 18, 9, 1, tzinfo=UTC),
    )
    return transport.invoke(
        ProviderRequest(
            execution_package_ref=execution_package.execution_package_id.value,
            seat_ref=execution_package.seat_ref,
            model_execution_profile=execution_package.model_execution_profile,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            prompt="Implement the backend API.",
        )
    )



def _provider_attempt(**overrides: object) -> ProviderAttempt:
    fields: dict[str, object] = {
        "provider_attempt_id": "provider-attempt.backend-api",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "reasoning_effort": "medium",
        "input_package_ref": "execution-package.backend-api",
        "seat_ref": "seat.worker.backend",
        **baseline_role_prompt_hook_fields(),
        "status": ProviderAttemptStatus.SUCCEEDED,
        "outcome": ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        "started_at": datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 18, 9, 1, tzinfo=UTC),
        "raw_output_ref": "provider-artifact.raw.backend-api",
        "parsed_output_ref": "provider-artifact.parsed.backend-api",
    }
    fields.update(overrides)
    return ProviderAttempt(**fields)


def test_work_product_accepts_yaml_shaped_ref_strings() -> None:
    work_product = WorkProduct(**_work_product_fields())

    assert isinstance(work_product.work_product_id, WorkProductRef)
    assert work_product.work_product_id.value == "work-product.backend.1"
    assert isinstance(work_product.execution_package_ref, ExecutionPackageRef)
    assert work_product.execution_package_ref.value == "exec.ticket.backend.1"
    assert isinstance(work_product.ticket_ref, TicketId)
    assert work_product.ticket_ref.value == "ticket.backend"
    assert isinstance(work_product.producer_attempt_ref, ProviderAttemptRef)
    assert work_product.producer_attempt_ref.value == "provider-attempt.1"
    assert isinstance(work_product.artifact_refs[0], WorkProductArtifactRef)
    assert work_product.artifact_refs[0].value == "artifact.patch.1"
    assert isinstance(work_product.claim_refs[0], WorkProductClaimDraftRef)
    assert work_product.claim_refs[0].value == "claim-draft.backend.1"
    assert work_product.summary == "Implemented backend API."


def test_work_product_strips_summary() -> None:
    fields = _work_product_fields()
    fields["summary"] = "  Implemented backend API.  "

    work_product = WorkProduct(**fields)

    assert work_product.summary == "Implemented backend API."


def test_claim_draft_accepts_yaml_shaped_ref_strings() -> None:
    claim_draft = WorkProductClaimDraft(**_claim_draft_fields())

    assert isinstance(claim_draft.claim_draft_ref, WorkProductClaimDraftRef)
    assert claim_draft.claim_draft_ref.value == "claim-draft.backend.1"
    assert isinstance(claim_draft.producer_attempt_ref, ProviderAttemptRef)
    assert claim_draft.producer_attempt_ref.value == "provider-attempt.1"
    assert isinstance(claim_draft.execution_package_ref, ExecutionPackageRef)
    assert claim_draft.execution_package_ref.value == "exec.ticket.backend.1"
    assert isinstance(claim_draft.ticket_ref, TicketId)
    assert claim_draft.ticket_ref.value == "ticket.backend"
    assert isinstance(claim_draft.acceptance_refs[0], AcceptanceRef)
    assert claim_draft.acceptance_refs[0].value == "AC-BACKEND"
    assert isinstance(claim_draft.source_surface_refs[0], SourceSurfaceRef)
    assert claim_draft.source_surface_refs[0].value == "surface.backend"
    assert isinstance(claim_draft.artifact_refs[0], WorkProductArtifactRef)
    assert claim_draft.artifact_refs[0].value == "artifact.patch.1"
    assert claim_draft.summary == "Evidence claim draft for backend API."


def test_claim_draft_strips_summary() -> None:
    fields = _claim_draft_fields()
    fields["summary"] = "  Evidence claim draft for backend API.  "

    claim_draft = WorkProductClaimDraft(**fields)

    assert claim_draft.summary == "Evidence claim draft for backend API."


def test_work_product_requires_producer_attempt_ref() -> None:
    fields = _work_product_fields()
    fields.pop("producer_attempt_ref")

    with pytest.raises(ValidationError):
        WorkProduct(**fields)


def test_work_product_requires_artifact_refs() -> None:
    fields = _work_product_fields()
    fields["artifact_refs"] = ()

    with pytest.raises(ValidationError, match="artifact_refs must not be empty"):
        WorkProduct(**fields)


def test_work_product_requires_claim_refs() -> None:
    fields = _work_product_fields()
    fields["claim_refs"] = ()

    with pytest.raises(ValidationError, match="claim_refs must not be empty"):
        WorkProduct(**fields)


def test_work_product_rejects_blank_summary() -> None:
    fields = _work_product_fields()
    fields["summary"] = "   "

    with pytest.raises(ValidationError, match="summary must not be empty"):
        WorkProduct(**fields)


def test_work_product_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WorkProduct(
            **_work_product_fields(),
            unexpected="not allowed",
        )


def test_claim_draft_requires_acceptance_refs() -> None:
    fields = _claim_draft_fields()
    fields["acceptance_refs"] = ()

    with pytest.raises(ValidationError, match="acceptance_refs must not be empty"):
        WorkProductClaimDraft(**fields)


def test_claim_draft_requires_artifact_refs() -> None:
    fields = _claim_draft_fields()
    fields["artifact_refs"] = ()

    with pytest.raises(ValidationError, match="artifact_refs must not be empty"):
        WorkProductClaimDraft(**fields)


def test_claim_draft_rejects_blank_summary() -> None:
    fields = _claim_draft_fields()
    fields["summary"] = "   "

    with pytest.raises(ValidationError, match="summary must not be empty"):
        WorkProductClaimDraft(**fields)


def test_claim_draft_requires_source_surface_refs() -> None:
    fields = _claim_draft_fields()
    fields["source_surface_refs"] = ()

    with pytest.raises(ValidationError, match="source_surface_refs must not be empty"):
        WorkProductClaimDraft(**fields)


def test_claim_draft_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WorkProductClaimDraft(
            **_claim_draft_fields(),
            unexpected="not allowed",
        )


def test_work_product_submission_requires_claim_drafts() -> None:
    work_product = WorkProduct(**_work_product_fields())

    with pytest.raises(ValidationError, match="claim_drafts"):
        WorkProductSubmission(work_product=work_product, claim_drafts=())


def test_work_product_submission_requires_claim_refs_to_match_claim_drafts() -> None:
    fields = _work_product_fields()
    fields["claim_refs"] = ("claim-draft.backend.2",)
    work_product = WorkProduct(**fields)
    claim_draft = WorkProductClaimDraft(**_claim_draft_fields())

    with pytest.raises(ValidationError, match="claim_refs|claim_drafts"):
        WorkProductSubmission(work_product=work_product, claim_drafts=(claim_draft,))


def test_build_work_product_from_provider_attempt_creates_submission() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_fake_provider_attempt(),
    )

    assert submission.version == 1
    assert submission.work_product.work_product_id.value == "work-product.provider-attempt.backend-api"
    assert submission.work_product.execution_package_ref.value == "execution-package.backend-api"
    assert submission.work_product.ticket_ref.value == "ticket.backend-api"
    assert submission.work_product.producer_attempt_ref.value == "provider-attempt.backend-api"
    assert tuple(ref.value for ref in submission.work_product.artifact_refs) == (
        "provider-artifact.raw.backend-api",
        "provider-artifact.parsed.backend-api",
    )
    assert tuple(ref.value for ref in submission.work_product.claim_refs) == (
        "claim-draft.provider-attempt.backend-api",
    )
    assert submission.work_product.summary == "Provider output submitted as work product."
    assert submission.work_product.fallback_kind is None

    claim_draft = submission.claim_drafts[0]
    assert claim_draft.claim_draft_ref.value == "claim-draft.provider-attempt.backend-api"
    assert claim_draft.execution_package_ref.value == "execution-package.backend-api"
    assert claim_draft.ticket_ref.value == "ticket.backend-api"
    assert tuple(ref.value for ref in claim_draft.acceptance_refs) == ("AC-BACKEND-API",)
    assert tuple(ref.value for ref in claim_draft.source_surface_refs) == (
        "surface.backend-api",
    )
    assert tuple(ref.value for ref in claim_draft.artifact_refs) == (
        "provider-artifact.raw.backend-api",
        "provider-artifact.parsed.backend-api",
    )
    assert claim_draft.summary == "Provider output submitted as work product."


def test_build_work_product_from_fallback_provider_attempt_preserves_fallback_kind() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(
            outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT,
            fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
        ),
        summary="Fallback artifact submitted.",
    )

    assert submission.work_product.fallback_kind is FallbackKind.TOOLING_PREFLIGHT
    assert submission.work_product.summary == "Fallback artifact submitted."
    assert submission.claim_drafts[0].summary == "Fallback artifact submitted."


class _WorkProductAwareTicketResolver:
    def __init__(self, submission: WorkProductSubmission) -> None:
        self._submission = submission

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        if payload_ref.value != "payload.ticket.created.backend-api":
            raise KeyError(payload_ref.value)
        package = _execution_package()
        return TicketCreatedPayload(
            ticket_id=package.ticket_ref,
            purpose=package.objective,
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.IMPLEMENTATION,
                required_capability_tags=(
                    CapabilityTag(value="task.implementation"),
                    CapabilityTag(value="surface.backend"),
                ),
            ),
            acceptance_refs=tuple(ref.value for ref in package.acceptance_refs),
            source_surface_refs=tuple(ref.value for ref in package.source_surface_refs),
            evidence_obligations=(package.evidence_obligations[0].evidence_obligation_id.value,),
            allowed_read_refs=tuple(ref.value for ref in package.allowed_read_refs),
            allowed_write_set=tuple(ref.value for ref in package.allowed_write_set),
            attempt_count=0,
        )

    def resolve_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        return TicketRefPayload(ticket_id=TicketId(value=payload_ref.value))

    def resolve_work_product_ticket_ref(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketRefPayload:
        if payload_ref.value != self._submission.work_product.work_product_id.value:
            raise KeyError(payload_ref.value)
        return TicketRefPayload(ticket_id=self._submission.work_product.ticket_ref)

    def resolve_ticket_check(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError("resolve_ticket_check should not be called")

    def resolve_ticket_completion(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCompletionSnapshot:
        if payload_ref.value != "payload.ticket.completed.backend-api":
            raise KeyError(payload_ref.value)
        return TicketCompletionSnapshot(
            ticket_id=self._submission.work_product.ticket_ref,
            provider_attempt_count=1,
            evidence_complete=True,
            checker_approved=True,
            blocking_issue_refs=(),
        )



def _created_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="event.ticket-created.backend-api"),
        event_type=EventType.TICKET_CREATED,
        project_ref=ProjectRef(value="project.tiny-fullstack"),
        actor_ref=ActorRef(value="seat-architect"),
        timestamp=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        graph_version=1,
        payload_refs=(EventPayloadRef(value="payload.ticket.created.backend-api"),),
    )



def _completed_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="event.ticket-completed.backend-api"),
        event_type=EventType.TICKET_COMPLETED,
        project_ref=ProjectRef(value="project.tiny-fullstack"),
        actor_ref=ActorRef(value="seat-checker"),
        timestamp=datetime(2026, 5, 18, 10, 3, tzinfo=UTC),
        graph_version=3,
        payload_refs=(EventPayloadRef(value="payload.ticket.completed.backend-api"),),
    )



def test_work_product_event_factory_emits_work_product_ref_payload_for_work_product_submitted() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )

    event = build_work_product_submitted_event(
        work_product=submission.work_product,
        project_ref=ProjectRef(value="project.tiny-fullstack"),
        actor_ref=ActorRef(value="runtime:provider-executor"),
        graph_version=8,
        timestamp=datetime(2026, 5, 18, 10, 2, tzinfo=UTC),
    )

    assert event.event_type is EventType.WORK_PRODUCT_SUBMITTED
    assert tuple(ref.value for ref in event.payload_refs) == (
        submission.work_product.work_product_id.value,
    )



def test_work_product_submitted_event_payload_can_be_resolved_to_ticket_ref() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )
    event = build_work_product_submitted_event(
        work_product=submission.work_product,
        project_ref=ProjectRef(value="project.tiny-fullstack"),
        actor_ref=ActorRef(value="runtime:provider-executor"),
        graph_version=8,
        timestamp=datetime(2026, 5, 18, 10, 2, tzinfo=UTC),
    )

    resolved_payload = _WorkProductAwareTicketResolver(
        submission
    ).resolve_work_product_ticket_ref(event.payload_refs[0])

    assert resolved_payload.ticket_id == submission.work_product.ticket_ref


def test_work_product_claim_draft_is_not_verified_evidence() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )

    claim_draft = submission.claim_drafts[0]

    assert not hasattr(claim_draft, "verified_evidence_refs")
    assert not hasattr(claim_draft, "verdict")
    assert not hasattr(claim_draft, "status")



def test_work_product_event_registers_with_ticket_reducer_without_completing_ticket() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )
    event = build_work_product_submitted_event(
        work_product=submission.work_product,
        project_ref=ProjectRef(value="project.tiny-fullstack"),
        actor_ref=ActorRef(value="runtime:provider-executor"),
        graph_version=2,
        timestamp=datetime(2026, 5, 18, 10, 2, tzinfo=UTC),
    )

    graph = TicketReducer(_WorkProductAwareTicketResolver(submission)).reduce(
        (_created_event(), event)
    )

    assert graph.graph_version == 2
    assert graph.nodes[submission.work_product.ticket_ref].status is TicketStatus.READY
    assert graph.completed_nodes == ()



def test_work_product_event_allows_later_ticket_completion_gate_to_pass() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )
    event = build_work_product_submitted_event(
        work_product=submission.work_product,
        project_ref=ProjectRef(value="project.tiny-fullstack"),
        actor_ref=ActorRef(value="runtime:provider-executor"),
        graph_version=2,
        timestamp=datetime(2026, 5, 18, 10, 2, tzinfo=UTC),
    )

    graph = TicketReducer(_WorkProductAwareTicketResolver(submission)).reduce(
        (_created_event(), event, _completed_event())
    )

    assert graph.graph_version == 3
    assert graph.nodes[submission.work_product.ticket_ref].status is TicketStatus.COMPLETED
    assert graph.completed_nodes == (submission.work_product.ticket_ref,)



def test_ticket_reducer_rejects_completion_without_work_product_event() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )

    with pytest.raises(TicketReducerError, match="work product"):
        TicketReducer(_WorkProductAwareTicketResolver(submission)).reduce(
            (_created_event(), _completed_event())
        )



def test_work_product_event_factory_rejects_non_positive_graph_version() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )

    with pytest.raises(ValidationError, match="greater than 0"):
        build_work_product_submitted_event(
            work_product=submission.work_product,
            project_ref=ProjectRef(value="project.tiny-fullstack"),
            actor_ref=ActorRef(value="runtime:provider-executor"),
            graph_version=0,
            timestamp=datetime(2026, 5, 18, 10, 2, tzinfo=UTC),
        )


def test_work_product_event_factory_rejects_naive_timestamp() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )

    with pytest.raises(ValidationError, match="timezone"):
        build_work_product_submitted_event(
            work_product=submission.work_product,
            project_ref=ProjectRef(value="project.tiny-fullstack"),
            actor_ref=ActorRef(value="runtime:provider-executor"),
            graph_version=8,
            timestamp=datetime(2026, 5, 18, 10, 2),
        )


def test_work_product_event_factory_cannot_emit_completion_event() -> None:
    submission = build_work_product_from_provider_attempt(
        execution_package=_execution_package(),
        provider_attempt=_provider_attempt(),
    )

    with pytest.raises(TypeError):
        build_work_product_submitted_event(
            work_product=submission.work_product,
            project_ref=ProjectRef(value="project.tiny-fullstack"),
            actor_ref=ActorRef(value="runtime:provider-executor"),
            graph_version=8,
            timestamp=datetime(2026, 5, 18, 10, 2, tzinfo=UTC),
            event_type=EventType.TICKET_COMPLETED,
        )


def test_build_work_product_from_provider_attempt_rejects_blank_summary() -> None:
    with pytest.raises(WorkProductBuildError, match="summary"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=_provider_attempt(),
            summary="   ",
        )


def test_primary_provider_attempt_with_fallback_kind_is_rejected_by_builder() -> None:
    provider_attempt = _provider_attempt().model_copy(
        update={"fallback_kind": FallbackKind.TOOLING_PREFLIGHT}
    )

    with pytest.raises(WorkProductBuildError, match="fallback_kind"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=provider_attempt,
        )


def test_fallback_provider_attempt_without_fallback_kind_is_rejected_by_builder() -> None:
    provider_attempt = _provider_attempt(
        outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT,
        fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
    ).model_copy(update={"fallback_kind": None})

    with pytest.raises(WorkProductBuildError, match="fallback_kind"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=provider_attempt,
        )


def test_failed_provider_attempt_cannot_build_work_product() -> None:
    provider_attempt = _provider_attempt(
        status=ProviderAttemptStatus.FAILED,
        raw_output_ref=None,
        parsed_output_ref=None,
        failure_kind="provider_unavailable",
    )

    with pytest.raises(WorkProductBuildError, match="succeeded"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=provider_attempt,
        )


def test_provider_attempt_package_mismatch_is_rejected() -> None:
    with pytest.raises(WorkProductBuildError, match="input_package_ref"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=_provider_attempt(input_package_ref="execution-package.frontend-ui"),
        )


def test_provider_attempt_seat_mismatch_is_rejected() -> None:
    with pytest.raises(WorkProductBuildError, match="seat_ref"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=_provider_attempt(seat_ref="seat.worker.frontend"),
        )


def test_provider_attempt_missing_raw_output_is_rejected() -> None:
    provider_attempt = _provider_attempt().model_copy(update={"raw_output_ref": None})

    with pytest.raises(WorkProductBuildError, match="raw_output_ref"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=provider_attempt,
        )


def test_provider_attempt_missing_parsed_output_is_rejected() -> None:
    provider_attempt = _provider_attempt().model_copy(update={"parsed_output_ref": None})

    with pytest.raises(WorkProductBuildError, match="parsed_output_ref"):
        build_work_product_from_provider_attempt(
            execution_package=_execution_package(),
            provider_attempt=provider_attempt,
        )


@pytest.mark.parametrize(
    "ref_type",
    (
        WorkProductRef,
        WorkProductArtifactRef,
        WorkProductClaimDraftRef,
    ),
)
def test_ref_value_objects_reject_empty_values(ref_type: type[object]) -> None:
    with pytest.raises(ValidationError, match="value must not be empty"):
        ref_type(value="   ")
