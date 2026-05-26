from __future__ import annotations

from datetime import UTC, datetime
import hashlib

import pytest

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import ModelExecutionProfileId
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    SeatDemand,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.audit.replay_bundle import (
    ReplayArtifactManifestEntry,
    ReplayBundleBuilderInput,
    ReplayManifestEntry,
    ReplayManifestKind,
    build_replay_bundle,
)
from boardroom_os.closeout.gate import ProjectionVersionRef
from boardroom_os.contracts.refs import namespaced_ref
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.replay import ProjectionReplay, ProjectionReplayError
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentPayload,
    SeatAssignmentProjector,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId

PROJECT_REF = ProjectRef(value="project-tiny-fullstack")
GENERATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)
PROJECTION_VERSION = ProjectionVersionRef(value="projection.seat_assignment_graph.v1")
PAYLOAD_MANIFEST_REF = "artifact.payload-manifest"
ARTIFACT_MANIFEST_REF = "artifact.artifact-manifest"
HASH_MANIFEST_REF = "artifact.hash-manifest"
REPORT_REF = "artifact.replay-report"


class InMemoryReplayPayloadResolver:
    def __init__(
        self,
        *,
        created_payloads: dict[str, TicketCreatedPayload],
        assignment_payloads: dict[str, SeatAssignmentPayload],
    ) -> None:
        self._created_payloads = created_payloads
        self._assignment_payloads = assignment_payloads

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self._created_payloads[payload_ref.value]

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef):
        raise KeyError(payload_ref.value)

    def resolve_seat_assignment(self, payload_ref: EventPayloadRef) -> SeatAssignmentPayload:
        return self._assignment_payloads[payload_ref.value]


def _fixture_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ref_value(ref: object) -> str:
    value = getattr(ref, "value", ref)
    assert isinstance(value, str)
    return value


def _seat_ref() -> AgentSeatRef:
    return AgentSeatRef(value="seat-worker-backend")


def _ticket_id() -> TicketId:
    return TicketId(value="ticket-backend-api")


def _ticket_payload() -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=_ticket_id(),
        purpose="Build backend API",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(CapabilityTag(value="surface.backend"),),
        ),
        depends_on=(),
        acceptance_refs=("AC-BOOK-API",),
        source_surface_refs=("surface.backend",),
        evidence_obligations=("evidence.api",),
        allowed_read_refs=("contract.tiny-fullstack",),
        allowed_write_set=("10-project/backend",),
        attempt_count=0,
    )


def _seat_assignment_payload() -> SeatAssignmentPayload:
    return SeatAssignmentPayload(ticket_id=_ticket_id(), seat_ref=_seat_ref())


def _event(
    *,
    event_id: str,
    event_type: EventType,
    graph_version: int,
    payload_ref: str,
    actor_ref: str = "actor-ceo",
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=GENERATED_AT,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _ticket_created_event(*, graph_version: int = 1) -> EventRecord:
    return _event(
        event_id=f"event-ticket-created-{graph_version}",
        event_type=EventType.TICKET_CREATED,
        graph_version=graph_version,
        payload_ref="payload:ticket-backend-api-created",
    )


def _seat_assigned_event(*, graph_version: int = 2) -> EventRecord:
    return _event(
        event_id=f"event-seat-assigned-{graph_version}",
        event_type=EventType.SEAT_ASSIGNED,
        graph_version=graph_version,
        payload_ref="payload:ticket-backend-api-seat-assigned",
        actor_ref="actor-architect",
    )


def _events() -> tuple[EventRecord, ...]:
    return (_ticket_created_event(), _seat_assigned_event())


def _seat_projection() -> SeatLifecycleProjection:
    seat = AgentSeat(
        seat_ref=_seat_ref(),
        actor_ref=ActorRef(value="actor-worker"),
        project_ref=PROJECT_REF,
        role_profile_ref=RoleProfileId(value="role.worker.backend"),
        role_category=RoleCategory.IMPLEMENTATION,
        capability_tags=(CapabilityTag(value="surface.backend"),),
        model_execution_profile_ref=ModelExecutionProfileId(value="model.worker.backend"),
        skill_refs=(SkillRef(value="skill.python"),),
        context_budget_tokens=4096,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )
    return SeatLifecycleProjection(
        graph_version=1,
        seats={seat.seat_ref: seat},
        active_seats={seat.seat_ref: seat},
        replacement_refs={},
    )


def _projector() -> SeatAssignmentProjector:
    resolver = InMemoryReplayPayloadResolver(
        created_payloads={
            "payload:ticket-backend-api-created": _ticket_payload(),
        },
        assignment_payloads={
            "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload(),
        },
    )
    return SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(),
    )


def _payload_manifest_entries(
    events: tuple[EventRecord, ...],
) -> tuple[ReplayManifestEntry, ...]:
    refs = [payload_ref.value for event in events for payload_ref in event.payload_refs]
    return tuple(
        ReplayManifestEntry(
            manifest_ref=f"manifest-entry.payload.{index + 1}",
            kind=ReplayManifestKind.PAYLOAD_MANIFEST,
            content_ref=payload_ref,
            sha256=_fixture_hash(f"payload.{payload_ref}"),
        )
        for index, payload_ref in enumerate(refs)
    )


def _event_window_ref(events: tuple[EventRecord, ...]) -> str:
    return (
        "event-range."
        f"{PROJECT_REF.value}."
        f"{events[0].graph_version}-{events[-1].graph_version}"
    )


def _artifact_manifest_entries(
    events: tuple[EventRecord, ...],
) -> tuple[ReplayArtifactManifestEntry, ...]:
    return (
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.event_window",
            kind=ReplayManifestKind.EVENT_WINDOW,
            content_ref=_event_window_ref(events),
            sha256=_fixture_hash("artifact.event_window.input"),
        ),
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.payload_manifest",
            kind=ReplayManifestKind.PAYLOAD_MANIFEST,
            content_ref=PAYLOAD_MANIFEST_REF,
            sha256=_fixture_hash("artifact.payload_manifest.input"),
        ),
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.artifact_manifest",
            kind=ReplayManifestKind.ARTIFACT_MANIFEST,
            content_ref=ARTIFACT_MANIFEST_REF,
            sha256=_fixture_hash("artifact.artifact_manifest.input"),
        ),
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.hash_manifest",
            kind=ReplayManifestKind.HASH_MANIFEST,
            content_ref=HASH_MANIFEST_REF,
            sha256=_fixture_hash("artifact.hash_manifest.input"),
        ),
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.replay_report",
            kind=ReplayManifestKind.REPLAY_REPORT,
            content_ref=REPORT_REF,
            sha256=_fixture_hash("artifact.replay_report.input"),
        ),
    )


def _builder_payload(**overrides: object) -> dict[str, object]:
    events = overrides.pop("events", _events())
    assert isinstance(events, tuple)
    payload: dict[str, object] = {
        "project_ref": PROJECT_REF,
        "events": events,
        "seat_assignment_projector": _projector(),
        "projection_version": PROJECTION_VERSION,
        "payload_manifest_ref": PAYLOAD_MANIFEST_REF,
        "payload_manifest_entries": _payload_manifest_entries(events),
        "event_window_ref": _event_window_ref(events),
        "artifact_manifest_ref": ARTIFACT_MANIFEST_REF,
        "artifact_manifest_entries": _artifact_manifest_entries(events),
        "hash_manifest_ref": HASH_MANIFEST_REF,
        "replay_report_ref": REPORT_REF,
        "generated_at": GENERATED_AT,
    }
    payload.update(overrides)
    return payload


def _builder_input(**overrides: object) -> ReplayBundleBuilderInput:
    return ReplayBundleBuilderInput.model_validate(_builder_payload(**overrides))


def _bundle(**overrides: object):
    return build_replay_bundle(_builder_input(**overrides))


def test_re_replay_yields_stable_summary_hash() -> None:
    events = _events()
    projector = _projector()

    first_bundle = _bundle(events=events, seat_assignment_projector=projector)
    second_bundle = _bundle(events=events, seat_assignment_projector=projector)

    assert first_bundle.replay_report.summary_hash == second_bundle.replay_report.summary_hash


def test_re_replay_matches_independent_projection_replay_call() -> None:
    events = _events()
    projector = _projector()
    replay_summary = ProjectionReplay(
        projection_kind="seat_assignment_graph"
    ).replay_events(
        events=events,
        project_ref=PROJECT_REF,
        expected_graph_version=events[-1].graph_version,
        projector=projector,
    )

    bundle = _bundle(events=events, seat_assignment_projector=projector)

    assert _ref_value(bundle.replay_report.summary_hash) == replay_summary.summary_hash


def test_re_replay_fails_when_events_violate_graph_version_contiguity() -> None:
    events = (_ticket_created_event(graph_version=1), _seat_assigned_event(graph_version=3))
    builder_input = _builder_input(events=events)

    with pytest.raises(ProjectionReplayError, match="contiguous"):
        build_replay_bundle(builder_input)


def test_payload_manifest_entries_order_invariance() -> None:
    events = _events()
    entries = _payload_manifest_entries(events)

    ordered_bundle = _bundle(events=events, payload_manifest_entries=entries)
    reversed_bundle = _bundle(
        events=events,
        payload_manifest_entries=tuple(reversed(entries)),
    )

    assert (
        ordered_bundle.payload_manifest.payload_manifest_hash
        == reversed_bundle.payload_manifest.payload_manifest_hash
    )


def test_artifact_manifest_entries_order_invariance() -> None:
    events = _events()
    entries = _artifact_manifest_entries(events)

    ordered_bundle = _bundle(events=events, artifact_manifest_entries=entries)
    reversed_bundle = _bundle(
        events=events,
        artifact_manifest_entries=tuple(reversed(entries)),
    )

    assert (
        ordered_bundle.artifact_manifest.artifact_manifest_hash
        == reversed_bundle.artifact_manifest.artifact_manifest_hash
    )


def test_replay_bundle_id_includes_namespaced_segments() -> None:
    bundle = _bundle()
    summary_hash = _ref_value(bundle.replay_report.summary_hash)
    expected = namespaced_ref(
        kind="replay-bundle",
        project_ref=PROJECT_REF.value,
        content_hash=summary_hash,
        run_id=None,
    )

    assert bundle.replay_bundle_id.value == expected


def test_build_replay_bundle_with_run_id_produces_unique_bundle_id() -> None:
    first_bundle = _bundle(run_id="run-001")
    second_bundle = _bundle(run_id="run-002")
    first_summary_hash = _ref_value(first_bundle.replay_report.summary_hash)
    second_summary_hash = _ref_value(second_bundle.replay_report.summary_hash)
    first_expected = namespaced_ref(
        kind="replay-bundle",
        project_ref=PROJECT_REF.value,
        content_hash=first_summary_hash,
        run_id="run-001",
    )
    second_expected = namespaced_ref(
        kind="replay-bundle",
        project_ref=PROJECT_REF.value,
        content_hash=second_summary_hash,
        run_id="run-002",
    )

    assert first_bundle.replay_bundle_id.value == first_expected
    assert second_bundle.replay_bundle_id.value == second_expected
    assert _ref_value(first_bundle.replay_bundle_id) != _ref_value(
        second_bundle.replay_bundle_id
    )
