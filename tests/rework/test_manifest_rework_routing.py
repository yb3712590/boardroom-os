from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.evidence.live_blackbox import build_live_blackbox_evidence_from_blackbox_facts
from boardroom_os.evidence.blackbox_plan import BlackboxPlanActionKind, BlackboxVerificationPlanRef
from boardroom_os.execution.blackbox_plan_runner import (
    BlackboxActionExecutionFact,
    BlackboxActionExecutionFactRef,
    BlackboxActionInputRefHash,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.reducers.rework import (
    ReworkReducer,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
)
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    ManifestReworkRoutingStatus,
    route_manifest_blackbox_facts,
)
from boardroom_os.rework.model import (
    ReworkActorKind,
    ReworkCycleId,
    ReworkIssueCode,
    RunId,
)

NOW = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)
ACCEPTANCE = AcceptanceRef(value="AC-LIVE-BLACKBOX")
SURFACE = SourceSurfaceRef(value="surface.backend-api")
OBLIGATION = EvidenceObligationRef(value="evidence.live-blackbox")


def test_blackbox_facts_build_live_evidence_without_success_from_prose() -> None:
    fact = _failed_http_fact(status_text="readiness path differs from run manifest")

    evidence = build_live_blackbox_evidence_from_blackbox_facts(
        evidence_id="live-blackbox.v2-100f.manifest",
        package_contract_ref=ContractId(value="package-contract.tiny-fullstack"),
        backend_command_id=ContractId(value="run.backend"),
        frontend_command_id=ContractId(value="run.frontend"),
        backend_service_run_ref="service-run.backend",
        frontend_service_run_ref="service-run.frontend",
        facts=(fact,),
        generated_at=NOW,
    )

    assert evidence.probes[0].passed is False
    assert evidence.probes[0].observed_facts["plan_ref"] == "blackbox-plan.verify.generated"
    assert evidence.probes[0].observed_facts["http_status"] == 404
    assert evidence.probes[0].observed_facts["status_text"] == "readiness path differs from run manifest"


def test_manifest_drift_projects_to_run_manifest_error_rework_issue() -> None:
    result = route_manifest_blackbox_facts(
        facts=(_failed_http_fact(),),
        context=_context(),
        advisory_context={
            "labels": ("readiness path differs from run manifest",),
            "raw_manifest_refs": ("context.run-manifest.raw",),
        },
    )

    assert result.status is ManifestReworkRoutingStatus.REWORK_REQUIRED
    assert result.rework_request is not None
    issue = result.rework_request.issues[0]
    assert issue.issue_code is ReworkIssueCode.RUN_MANIFEST_ERROR
    assert issue.issue_code is not ReworkIssueCode.RUN_MANIFEST_MISMATCH
    assert issue.observed_fact_refs[0].value == "blackbox-action-fact.blackbox-plan.verify.generated.action.http.books"
    assert issue.advisory_context["observed"]["http_status"] == 404
    assert issue.advisory_context["labels"] == ("readiness path differs from run manifest",)


def test_run_manifest_error_rework_request_enters_reducer_checked_refs() -> None:
    result = route_manifest_blackbox_facts(
        facts=(_failed_http_fact(),),
        context=_context(),
    )
    assert result.rework_request is not None

    projection = ReworkReducer(_RequestOnlyResolver(result.rework_request)).reduce(
        (
            EventRecord(
                event_id=EventId(value="evt.rework-requested.v2-100f-e"),
                event_type=EventType.REWORK_REQUESTED,
                project_ref=ProjectRef(value="project.v2-100f"),
                actor_ref=ActorRef(value="seat-checker"),
                timestamp=NOW,
                graph_version=13,
                payload_refs=(EventPayloadRef(value="payload:manifest-request"),),
            ),
        )
    )

    assert projection.request_ref == result.rework_request.rework_request_id
    assert result.rework_request.rework_request_id.value in projection.checked_refs
    assert projection.graph_version == 13


class _RequestOnlyResolver(ReworkReducerPayloadResolver):
    def __init__(self, request) -> None:
        self.request = request

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return ReworkRequestPayload(request=self.request)

    def resolve_rework_plan(self, payload_ref: EventPayloadRef):
        raise AssertionError("plan is not used by request-only projection")

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef):
        raise AssertionError("review is not used by request-only projection")

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef):
        raise AssertionError("approval is not used by request-only projection")

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef):
        raise AssertionError("ticket is not used by request-only projection")

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef):
        raise AssertionError("attempt is not used by request-only projection")

    def resolve_rework_review(self, payload_ref: EventPayloadRef):
        raise AssertionError("outcome is not used by request-only projection")

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef):
        raise AssertionError("terminal is not used by request-only projection")


def _failed_http_fact(*, status_text: str = "not found") -> BlackboxActionExecutionFact:
    return BlackboxActionExecutionFact(
        fact_id=BlackboxActionExecutionFactRef(
            value="blackbox-action-fact.blackbox-plan.verify.generated.action.http.books"
        ),
        plan_ref=BlackboxVerificationPlanRef(value="blackbox-plan.verify.generated"),
        action_id="action.http.books",
        action_kind=BlackboxPlanActionKind.HTTP,
        input_ref_hashes=(
                BlackboxActionInputRefHash(
                    input_ref=ContextRef(value="context.run-manifest.raw"),
                    sha256=Sha256Hex(
                        value="d1831127032628f603a3530fb74b54b45986b5287ab8c70046e7c6bcc1a607f4"
                    ),
                ),
        ),
        method="GET",
        url="http://127.0.0.1:8000/api/books",
        body_ref="artifact.http.books.body",
        artifact_refs=("artifact.http.books.observed",),
        http_status=404,
        status_text=status_text,
        started_at=NOW,
        finished_at=NOW,
        acceptance_refs=(ACCEPTANCE,),
        package_contract_ref=ContextRef(value="contract.package.tiny-fullstack"),
    )


def _context() -> BlockerProjectionContext:
    return BlockerProjectionContext(
        cycle_id=ReworkCycleId(value="rework-cycle.v2-100f-e"),
        run_id=RunId(value="run.v2-100f-e"),
        package_contract_ref=ContractId(value="package-contract.tiny-fullstack"),
        run_manifest_ref="run-manifest.v2-100f",
        active_acceptance_refs=(ACCEPTANCE,),
        active_source_surface_refs=(SURFACE,),
        active_evidence_obligation_refs=(OBLIGATION,),
        active_graph_version=12,
        requested_by_actor=ReworkActorKind.EVIDENCE_VERIFIER,
        requested_at=NOW,
    )
