from __future__ import annotations

from datetime import UTC, datetime
import hashlib

import pytest
from pydantic import ValidationError

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
    ReplayArtifactManifest,
    ReplayArtifactManifestEntry,
    ReplayBundleBuilderInput,
    ReplayBundleError,
    ReplayManifestEntry,
    ReplayManifestKind,
    ReplayPayloadManifest,
    build_replay_bundle,
)
from boardroom_os.closeout.gate import ProjectionVersionRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.replay import ProjectionReplay
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentPayload,
    SeatAssignmentProjector,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId

PROJECT_REF = ProjectRef(value="project-tiny-fullstack")
GENERATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)
PROJECTION_VERSION = ProjectionVersionRef(value="projection.seat_assignment_graph.v1")
EVENT_WINDOW_REF = "event-range.project-tiny-fullstack.1-2"
PAYLOAD_MANIFEST_REF = "artifact.payload-manifest"
ARTIFACT_MANIFEST_REF = "artifact.artifact-manifest"
HASH_MANIFEST_REF = "artifact.hash-manifest"
REPORT_REF = "artifact.replay-report"


def _fixture_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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



def _seat_ref() -> AgentSeatRef:
    return AgentSeatRef(value="seat-worker-backend")



def _ticket_id() -> TicketId:
    return TicketId(value="ticket-backend-api")



def _ticket_payload(*, purpose: str = "Build backend API") -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=_ticket_id(),
        purpose=purpose,
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



def _ticket_created_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="event-ticket-created"),
        event_type=EventType.TICKET_CREATED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="actor-ceo"),
        timestamp=GENERATED_AT,
        graph_version=1,
        payload_refs=(EventPayloadRef(value="payload:ticket-backend-api-created"),),
    )



def _seat_assigned_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="event-seat-assigned"),
        event_type=EventType.SEAT_ASSIGNED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="actor-ceo"),
        timestamp=GENERATED_AT,
        graph_version=2,
        payload_refs=(EventPayloadRef(value="payload:ticket-backend-api-seat-assigned"),),
    )



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



def _projector(*, ticket_purpose: str = "Build backend API") -> SeatAssignmentProjector:
    resolver = InMemoryReplayPayloadResolver(
        created_payloads={
            "payload:ticket-backend-api-created": _ticket_payload(purpose=ticket_purpose)
        },
        assignment_payloads={
            "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload()
        },
    )
    return SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(),
    )



def _events() -> tuple[EventRecord, ...]:
    return (_ticket_created_event(), _seat_assigned_event())



def _projection_summary(
    events: tuple[EventRecord, ...], *, ticket_purpose: str = "Build backend API"
):
    return ProjectionReplay(projection_kind="seat_assignment_graph").replay_events(
        events=events,
        project_ref=PROJECT_REF,
        expected_graph_version=events[-1].graph_version,
        projector=_projector(ticket_purpose=ticket_purpose),
    )



def _payload_manifest_entries(events: tuple[EventRecord, ...]) -> tuple[ReplayManifestEntry, ...]:
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



def _artifact_manifest_entries() -> tuple[ReplayArtifactManifestEntry, ...]:
    return (
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.event_window",
            kind=ReplayManifestKind.EVENT_WINDOW,
            content_ref=EVENT_WINDOW_REF,
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
            manifest_ref="artifact.replay_report",
            kind=ReplayManifestKind.REPLAY_REPORT,
            content_ref=REPORT_REF,
            sha256=_fixture_hash("artifact.replay_report.input"),
        ),
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.hash_manifest",
            kind=ReplayManifestKind.HASH_MANIFEST,
            content_ref=HASH_MANIFEST_REF,
            sha256=_fixture_hash("artifact.hash_manifest.input"),
        ),
    )



def _builder_payload(**overrides: object) -> dict[str, object]:
    events = overrides.pop("events", _events())
    payload: dict[str, object] = {
        "project_ref": PROJECT_REF,
        "events": events,
        "seat_assignment_projector": _projector(),
        "projection_version": PROJECTION_VERSION,
        "payload_manifest_ref": PAYLOAD_MANIFEST_REF,
        "payload_manifest_entries": _payload_manifest_entries(events),
        "event_window_ref": EVENT_WINDOW_REF,
        "artifact_manifest_ref": ARTIFACT_MANIFEST_REF,
        "artifact_manifest_entries": _artifact_manifest_entries(),
        "hash_manifest_ref": HASH_MANIFEST_REF,
        "replay_report_ref": REPORT_REF,
        "generated_at": GENERATED_AT,
    }
    payload.update(overrides)
    return payload



def test_builder_input_rejects_projection_summary_field() -> None:
    events = _events()
    payload = _builder_payload(
        events=events,
        projection_summary=_projection_summary(events),
    )
    payload.pop("seat_assignment_projector")

    with pytest.raises(ValidationError, match="projection_summary"):
        ReplayBundleBuilderInput.model_validate(payload)



def test_builder_input_rejects_extra_summary_hash() -> None:
    payload = _builder_payload(summary_hash=_fixture_hash("caller supplied hash"))

    with pytest.raises(ValidationError, match="summary_hash"):
        ReplayBundleBuilderInput.model_validate(payload)



def test_build_replay_bundle_rejects_model_copy_projection_summary_extra() -> None:
    valid_input = ReplayBundleBuilderInput.model_validate(_builder_payload())
    tampered_input = valid_input.model_copy(
        update={"projection_summary": _projection_summary(_events())}
    )

    with pytest.raises(
        ReplayBundleError,
        match="unexpected builder input fields|projection_summary|extra",
    ):
        build_replay_bundle(tampered_input)



def test_build_replay_bundle_rejects_non_seat_assignment_projector() -> None:
    builder_input = ReplayBundleBuilderInput.model_validate(_builder_payload()).model_copy(
        update={"seat_assignment_projector": object()}
    )

    with pytest.raises(
        ReplayBundleError,
        match="seat_assignment_projector must be SeatAssignmentProjector",
    ):
        build_replay_bundle(builder_input)



def test_build_replay_bundle_rejects_project_ref_that_is_not_namespace_segment() -> None:
    project_ref = ProjectRef(value="project.tiny-fullstack")
    events = tuple(
        event.model_copy(update={"project_ref": project_ref}) for event in _events()
    )
    builder_input = ReplayBundleBuilderInput.model_validate(_builder_payload()).model_copy(
        update={"project_ref": project_ref, "events": events}
    )

    with pytest.raises(
        ReplayBundleError,
        match="project_ref must be a namespace segment",
    ):
        build_replay_bundle(builder_input)



def test_tampered_events_produce_different_summary_hash() -> None:
    original_input = ReplayBundleBuilderInput.model_validate(_builder_payload())
    tampered_input = ReplayBundleBuilderInput.model_validate(
        _builder_payload(
            seat_assignment_projector=_projector(
                ticket_purpose="Tampered backend API purpose"
            )
        )
    )

    original_bundle = build_replay_bundle(original_input)
    tampered_bundle = build_replay_bundle(tampered_input)

    assert (
        original_bundle.replay_report.summary_hash
        != tampered_bundle.replay_report.summary_hash
    )



def test_payload_manifest_rejects_duplicate_content_ref() -> None:
    events = _events()
    entries = _payload_manifest_entries(events)
    duplicate_entry = entries[1].model_copy(
        update={
            "manifest_ref": "manifest-entry.payload.duplicate",
            "content_ref": entries[0].content_ref,
        }
    )

    with pytest.raises(ValidationError, match="duplicate key|content refs must be unique"):
        ReplayPayloadManifest(
            payload_manifest_id=PAYLOAD_MANIFEST_REF,
            project_ref=PROJECT_REF,
            entries=(entries[0], duplicate_entry),
        )



def test_artifact_manifest_rejects_duplicate_kind() -> None:
    entries = _artifact_manifest_entries()
    duplicate_entry = ReplayArtifactManifestEntry(
        manifest_ref="artifact.duplicate-event-window",
        content_ref="artifact.duplicate-event-window",
        kind=entries[0].kind,
        sha256=_fixture_hash("artifact.duplicate-event-window.input"),
    )

    with pytest.raises(
        ValidationError,
        match="kind values must be unique|duplicate kind",
    ):
        ReplayArtifactManifest(
            artifact_manifest_id=ARTIFACT_MANIFEST_REF,
            project_ref=PROJECT_REF,
            entries=(entries[0], duplicate_entry),
        )
