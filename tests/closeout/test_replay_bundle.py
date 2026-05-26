from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib

import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfileId
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    RoleCategory,
    SeatDemand,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.closeout.gate import EventRangeRef, ProjectionVersionRef, ReplayBundleReadiness
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.replay import ProjectionReplay, ProjectionReplayError
from boardroom_os.graph.seat_assignment import SeatAssignmentPayload, SeatAssignmentProjector
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId

from boardroom_os.audit.replay_bundle import (
    ReplayArtifactManifestEntry,
    ReplayAttestationKind,
    ReplayBundleBuilderInput,
    ReplayBundleError,
    ReplayContentHash,
    ReplayHashManifest,
    ReplayManifestEntry,
    ReplayManifestKind,
    build_replay_bundle,
    replay_bundle_readiness,
)

BASE_TIMESTAMP = datetime(2026, 5, 16, 14, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 5, 24, 11, 0, tzinfo=UTC)
PROJECT_REF = ProjectRef(value="project-tiny-fullstack")
PROJECTION_VERSION = ProjectionVersionRef(value="projection.seat_assignment_graph.v1")
REPORT_REF = "report.replay.seat_assignment"
PAYLOAD_MANIFEST_REF = "manifest.payload.seat_assignment"
EVENT_WINDOW_REF = "event-range.project-tiny-fullstack.1-2"
ARTIFACT_MANIFEST_REF = "manifest.artifact.seat_assignment"
HASH_MANIFEST_REF = "manifest.hash.seat_assignment"


class InMemoryReplayPayloadResolver:
    def __init__(
        self,
        *,
        created_payloads: dict[str, TicketCreatedPayload] | None = None,
        assignment_payloads: dict[str, SeatAssignmentPayload] | None = None,
    ) -> None:
        self._created_payloads = created_payloads or {}
        self._assignment_payloads = assignment_payloads or {}

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self._created_payloads[payload_ref.value]

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef):
        raise KeyError(payload_ref.value)

    def resolve_seat_assignment(self, payload_ref: EventPayloadRef) -> SeatAssignmentPayload:
        return self._assignment_payloads[payload_ref.value]



def _ticket_payload(**overrides: object) -> TicketCreatedPayload:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "purpose": "Implement backend API surface",
        "seat_demand": SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
        "depends_on": (),
        "acceptance_refs": ("AC-BOOK-API-STATE-001",),
        "source_surface_refs": ("surface-backend-api",),
        "evidence_obligations": ("obligation-api-test-run",),
        "allowed_read_refs": ("contract:tiny-fullstack",),
        "allowed_write_set": ("10-project/backend/**",),
        "attempt_count": 0,
    }
    values.update(overrides)
    return TicketCreatedPayload(**values)



def _seat_assignment_payload(**overrides: object) -> SeatAssignmentPayload:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "seat_ref": AgentSeatRef(value="seat-worker-backend"),
    }
    values.update(overrides)
    return SeatAssignmentPayload(**values)



def _agent_seat(**overrides: object) -> AgentSeat:
    values = {
        "seat_ref": AgentSeatRef(value="seat-worker-backend"),
        "actor_ref": ActorRef(value="actor.worker.backend"),
        "project_ref": PROJECT_REF,
        "role_profile_ref": RoleProfileId(value="role.implementation.backend"),
        "role_category": RoleCategory.IMPLEMENTATION,
        "capability_tags": (
            CapabilityTag(value="task.implementation"),
            CapabilityTag(value="surface.backend"),
        ),
        "model_execution_profile_ref": ModelExecutionProfileId(
            value="model.implementation.backend"
        ),
        "skill_refs": (SkillRef(value="skill.implementation.backend"),),
        "context_budget_tokens": 8192,
        "lifecycle_status": SeatLifecycleStatus.ACTIVE,
    }
    values.update(overrides)
    return AgentSeat(**values)



def _seat_projection(
    *, active_seats: tuple[AgentSeat, ...] | None = None
) -> SeatLifecycleProjection:
    active = active_seats if active_seats is not None else (_agent_seat(),)
    return SeatLifecycleProjection(
        graph_version=1,
        seats={seat.seat_ref: seat for seat in active},
        active_seats={seat.seat_ref: seat for seat in active},
        replacement_refs={},
    )



def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str = "seat-architect",
    project_ref: ProjectRef = PROJECT_REF,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=project_ref,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )



def _ticket_created_event(
    *,
    graph_version: int = 1,
    payload_ref: str = "payload:ticket-backend-api-created",
    project_ref: ProjectRef = PROJECT_REF,
) -> EventRecord:
    return _event(
        event_id=f"evt-ticket-created-{graph_version}",
        event_type=EventType.TICKET_CREATED,
        payload_ref=payload_ref,
        graph_version=graph_version,
        project_ref=project_ref,
    )



def _seat_assigned_event(*, graph_version: int = 2, project_ref: ProjectRef = PROJECT_REF) -> EventRecord:
    return _event(
        event_id=f"evt-seat-assigned-{graph_version}",
        event_type=EventType.SEAT_ASSIGNED,
        payload_ref="payload:ticket-backend-api-seat-assigned",
        graph_version=graph_version,
        actor_ref="seat-ceo",
        project_ref=project_ref,
    )



def _projector(
    *,
    created_payloads: dict[str, TicketCreatedPayload] | None = None,
    assignment_payloads: dict[str, SeatAssignmentPayload] | None = None,
    seat_projection: SeatLifecycleProjection | None = None,
) -> SeatAssignmentProjector:
    if created_payloads is None:
        created_payloads = {"payload:ticket-backend-api-created": _ticket_payload()}
    if assignment_payloads is None:
        assignment_payloads = {
            "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload()
        }
    resolver = InMemoryReplayPayloadResolver(
        created_payloads=created_payloads,
        assignment_payloads=assignment_payloads,
    )
    return SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=seat_projection or _seat_projection(),
    )



def _payload_manifest_entries(
    events: tuple[EventRecord, ...],
    *,
    include_all: bool = True,
) -> tuple[ReplayManifestEntry, ...]:
    refs = []
    for event in events:
        refs.extend(payload_ref.value for payload_ref in event.payload_refs)
    if not include_all:
        refs = refs[:-1]
    return tuple(
        ReplayManifestEntry(
            manifest_ref=f"manifest-entry.payload.{index + 1}",
            kind=ReplayManifestKind.PAYLOAD_MANIFEST,
            content_ref=payload_ref,
            sha256=_fixture_hash(f"payload.{payload_ref}"),
        )
        for index, payload_ref in enumerate(refs)
    )



def _artifact_manifest_entries(*, include_hash_manifest: bool = True) -> tuple[ReplayArtifactManifestEntry, ...]:
    entries = [
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
    ]
    if include_hash_manifest:
        entries.append(
            ReplayArtifactManifestEntry(
                manifest_ref="artifact.hash_manifest",
                kind=ReplayManifestKind.HASH_MANIFEST,
                content_ref=HASH_MANIFEST_REF,
                sha256=_fixture_hash("artifact.hash_manifest.input"),
            )
        )
    return tuple(entries)



def _fixture_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()



def _hash_jsonable(value: object) -> str:
    import json

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()



def _hash_model(model) -> str:
    return _hash_jsonable(model.model_dump(mode="json"))



def _artifact_manifest_structure_hash(artifact_manifest) -> str:
    return _hash_jsonable(
        {
            "artifact_manifest_id": artifact_manifest.artifact_manifest_id.model_dump(mode="json"),
            "project_ref": artifact_manifest.project_ref.model_dump(mode="json"),
            "entries": [
                entry.model_dump(mode="json", exclude={"sha256"})
                for entry in artifact_manifest.entries
            ],
        }
    )




def _event_range_ref_value(project_ref: ProjectRef, event_window) -> str:
    return (
        "event-range."
        f"{project_ref.value}."
        f"{event_window.first_graph_version}-{event_window.last_graph_version}"
    )




def _hash_manifest_logical_input(
    bundle,
    attestation,
    *,
    event_hash_chain=None,
    terminal_event_chain_hash=None,
    event_window_hash=None,
) -> dict[str, object]:
    event_hash_chain = event_hash_chain or bundle.hash_manifest.event_hash_chain
    terminal_event_chain_hash = (
        terminal_event_chain_hash or bundle.hash_manifest.terminal_event_chain_hash
    )
    event_window_hash = event_window_hash or bundle.hash_manifest.event_window_hash
    return {
        "event_hash_chain": [node.model_dump(mode="json") for node in event_hash_chain],
        "terminal_event_chain_hash": terminal_event_chain_hash.model_dump(mode="json"),
        "event_window_hash": event_window_hash.model_dump(mode="json"),
        "payload_manifest_hash": _hash_model(bundle.payload_manifest),
        "replay_report_hash": _hash_model(bundle.replay_report),
        "attestation_hashes": {
            attestation.attestation_id.value: _hash_model(attestation),
        },
    }




def _expected_artifact_entry_hashes(
    *,
    bundle,
    artifact_manifest,
    attestation,
    event_window_hash,
    hash_manifest_input,
) -> dict[ReplayManifestKind, str]:
    return {
        ReplayManifestKind.EVENT_WINDOW: _hash_jsonable(
            {
                "event_window": attestation.event_window.model_dump(mode="json"),
                "event_window_hash": event_window_hash.value,
            }
        ),
        ReplayManifestKind.PAYLOAD_MANIFEST: _hash_model(bundle.payload_manifest),
        ReplayManifestKind.ARTIFACT_MANIFEST: _artifact_manifest_structure_hash(
            artifact_manifest
        ),
        ReplayManifestKind.HASH_MANIFEST: _hash_jsonable(hash_manifest_input),
        ReplayManifestKind.REPLAY_REPORT: _hash_model(bundle.replay_report),
    }




def _artifact_manifest_with_expected_hashes(
    *,
    bundle,
    attestation,
    event_window_hash,
    hash_manifest_input,
    content_ref_overrides: dict[ReplayManifestKind, str] | None = None,
):
    content_ref_overrides = content_ref_overrides or {}
    structural_entries = tuple(
        ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref=content_ref_overrides.get(entry.kind, entry.content_ref),
            sha256=entry.sha256,
        )
        for entry in bundle.artifact_manifest.entries
    )
    structural_manifest = bundle.artifact_manifest.model_copy(
        update={"entries": structural_entries}
    )
    expected_hashes = _expected_artifact_entry_hashes(
        bundle=bundle,
        artifact_manifest=structural_manifest,
        attestation=attestation,
        event_window_hash=event_window_hash,
        hash_manifest_input=hash_manifest_input,
    )
    return bundle.artifact_manifest.model_copy(
        update={
            "entries": tuple(
                ReplayArtifactManifestEntry(
                    manifest_ref=entry.manifest_ref,
                    kind=entry.kind,
                    content_ref=entry.content_ref,
                    sha256=expected_hashes[entry.kind],
                )
                for entry in structural_entries
            )
        }
    )




def _chain_hash(previous_hash: str, event_hash: str) -> str:
    return hashlib.sha256(f"{previous_hash}{event_hash}".encode("utf-8")).hexdigest()



def _builder_input(
    *,
    events: tuple[EventRecord, ...] | None = None,
    generated_at: datetime = GENERATED_AT,
    projection_version: ProjectionVersionRef = PROJECTION_VERSION,
    payload_manifest_entries: tuple[ReplayManifestEntry, ...] | None = None,
    artifact_manifest_entries: tuple[ReplayArtifactManifestEntry, ...] | None = None,
    event_window_ref: str = EVENT_WINDOW_REF,
    project_ref: ProjectRef = PROJECT_REF,
    seat_assignment_projector: SeatAssignmentProjector | None = None,
):
    events = events or (_ticket_created_event(), _seat_assigned_event())
    return ReplayBundleBuilderInput(
        project_ref=project_ref,
        events=events,
        seat_assignment_projector=seat_assignment_projector or _projector(),
        projection_version=projection_version,
        payload_manifest_ref=PAYLOAD_MANIFEST_REF,
        payload_manifest_entries=payload_manifest_entries or _payload_manifest_entries(events),
        event_window_ref=event_window_ref,
        artifact_manifest_ref=ARTIFACT_MANIFEST_REF,
        artifact_manifest_entries=artifact_manifest_entries or _artifact_manifest_entries(),
        hash_manifest_ref=HASH_MANIFEST_REF,
        replay_report_ref=REPORT_REF,
        generated_at=generated_at,
    )



def test_replay_bundle_rejects_empty_event_window() -> None:
    builder_payload = _builder_input().model_dump(mode="python")
    builder_payload["events"] = ()

    with pytest.raises(ValidationError, match="events"):
        ReplayBundleBuilderInput.model_validate(builder_payload)



def test_replay_bundle_rejects_projection_version_mismatch() -> None:
    builder_input = _builder_input().model_copy(
        update={
            "projection_version": ProjectionVersionRef(
                value="projection.ticket_graph.v1"
            )
        }
    )

    with pytest.raises(ReplayBundleError, match="projection version mismatch"):
        build_replay_bundle(builder_input)



def test_replay_bundle_builder_rejects_non_seat_assignment_projector() -> None:
    builder_input = _builder_input().model_copy(
        update={"seat_assignment_projector": object()}
    )

    with pytest.raises(
        ReplayBundleError,
        match="seat_assignment_projector must be SeatAssignmentProjector",
    ):
        build_replay_bundle(builder_input)



def test_replay_bundle_rejects_missing_artifact_hash() -> None:
    broken_entries = [
        entry.model_dump(mode="python") for entry in _artifact_manifest_entries()
    ]
    broken_entries[3]["sha256"] = ""

    with pytest.raises(ValidationError, match="sha256|value"):
        _builder_input(
            artifact_manifest_entries=tuple(
                ReplayArtifactManifestEntry.model_validate(entry)
                for entry in broken_entries
            )
        )


def test_replay_bundle_rejects_missing_artifact_manifest_kind() -> None:
    with pytest.raises(ReplayBundleError, match="artifact manifest missing"):
        build_replay_bundle(
            _builder_input(artifact_manifest_entries=_artifact_manifest_entries(include_hash_manifest=False))
        )



def test_replay_bundle_rejects_artifact_manifest_content_ref_mismatch() -> None:
    broken_entries = tuple(
        entry
        if entry.kind is not ReplayManifestKind.REPLAY_REPORT
        else ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref="report.replay.other",
            sha256=entry.sha256,
        )
        for entry in _artifact_manifest_entries()
    )

    with pytest.raises(ReplayBundleError, match="artifact manifest content ref mismatch"):
        build_replay_bundle(_builder_input(artifact_manifest_entries=broken_entries))




def test_replay_bundle_rejects_event_window_ref_that_does_not_match_stable_event_range() -> None:
    broken_entries = tuple(
        entry
        if entry.kind is not ReplayManifestKind.EVENT_WINDOW
        else ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref="manifest.event_window.seat_assignment",
            sha256=entry.sha256,
        )
        for entry in _artifact_manifest_entries()
    )

    with pytest.raises(ReplayBundleError, match="event_window.*content ref|content ref mismatch"):
        build_replay_bundle(
            _builder_input(
                artifact_manifest_entries=broken_entries,
                event_window_ref="manifest.event_window.seat_assignment",
            )
        )


@pytest.mark.parametrize("content_ref", ("artifact/.", "artifact/..", "a/b/.", "a/b/.."))
def test_replay_bundle_rejects_artifact_manifest_content_ref_dot_tail(
    content_ref: str,
) -> None:
    with pytest.raises(ValidationError, match="content_ref"):
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.bad-dot-tail",
            kind=ReplayManifestKind.REPLAY_REPORT,
            content_ref=content_ref,
            sha256=_fixture_hash(f"bad-dot-tail.{content_ref}"),
        )




@pytest.mark.parametrize("content_ref", ("C:artifact", "D:"))
def test_replay_bundle_rejects_artifact_manifest_content_ref_drive_relative(
    content_ref: str,
) -> None:
    with pytest.raises(ValidationError, match="content_ref"):
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.bad-drive-relative",
            kind=ReplayManifestKind.REPLAY_REPORT,
            content_ref=content_ref,
            sha256=_fixture_hash(f"bad-drive-relative.{content_ref}"),
        )



def test_replay_bundle_rejects_artifact_manifest_hash_that_does_not_close() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    for entry in broken_bundle["artifact_manifest"]["entries"]:
        if entry["kind"] == ReplayManifestKind.REPLAY_REPORT.value:
            entry["sha256"] = _fixture_hash("wrong.replay.report.hash")
            break

    with pytest.raises(ReplayBundleError, match="artifact manifest hash mismatch|artifact_manifest_hash"):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))



def test_replay_bundle_builder_overwrites_artifact_manifest_placeholder_input_hashes() -> None:
    placeholder_entries = tuple(
        ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref=entry.content_ref,
            sha256=_fixture_hash(f"placeholder.input.{index}"),
        )
        for index, entry in enumerate(_artifact_manifest_entries())
    )

    bundle = build_replay_bundle(_builder_input(artifact_manifest_entries=placeholder_entries))

    assert tuple(entry.sha256 for entry in bundle.artifact_manifest.entries) != tuple(
        entry.sha256 for entry in placeholder_entries
    )



def test_replay_bundle_rejects_missing_event_hash_chain() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_manifest = bundle.hash_manifest.model_copy(update={"event_hash_chain": ()})

    with pytest.raises(ReplayBundleError, match="event hash chain"):
        replay_bundle_readiness(bundle.model_copy(update={"hash_manifest": broken_manifest}))



def test_replay_bundle_rejects_missing_hash_manifest() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["hash_manifest"] = None

    with pytest.raises(ValidationError, match="hash_manifest"):
        type(bundle).model_validate(broken_bundle)



def test_replay_bundle_rejects_missing_replay_report() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["replay_report"] = None

    with pytest.raises(ValidationError, match="replay_report"):
        type(bundle).model_validate(broken_bundle)



def test_replay_bundle_rejects_unknown_attestation_kind() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["attestations"][0]["kind"] = "ticket_graph"

    with pytest.raises(ValidationError, match="kind"):
        type(bundle).model_validate(broken_bundle)



def test_replay_bundle_rejects_multiple_attestations_in_v1() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["attestations"] = broken_bundle["attestations"] * 2

    with pytest.raises(ValidationError, match="exactly one attestation"):
        type(bundle).model_validate(broken_bundle)



def test_replay_bundle_rejects_payload_manifest_missing_event_payload_ref() -> None:
    with pytest.raises(ReplayBundleError, match="payload manifest"):
        build_replay_bundle(
            _builder_input(
                payload_manifest_entries=_payload_manifest_entries(
                    (_ticket_created_event(), _seat_assigned_event()),
                    include_all=False,
                )
            )
        )



def test_replay_bundle_rejects_hash_manifest_mismatch() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["hash_manifest"]["replay_report_hash"] = _fixture_hash("wrong.replay.report.manifest.hash")

    with pytest.raises(ReplayBundleError, match="hash manifest mismatch"):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))



def test_replay_bundle_rejects_event_graph_version_gap() -> None:
    events = (
        _ticket_created_event(graph_version=1),
        _seat_assigned_event(graph_version=3),
    )

    with pytest.raises(ProjectionReplayError, match="graph_version.*contiguous"):
        build_replay_bundle(_builder_input(events=events))



def test_replay_bundle_rejects_unordered_event_input() -> None:
    events = (
        _seat_assigned_event(graph_version=2),
        _ticket_created_event(graph_version=1),
    )

    with pytest.raises(ProjectionReplayError, match="strictly ordered"):
        build_replay_bundle(_builder_input(events=events))



def test_replay_bundle_rejects_event_project_mismatch() -> None:
    other_project = ProjectRef(value="project-other")
    events = (
        _ticket_created_event(graph_version=1),
        _seat_assigned_event(graph_version=2, project_ref=other_project),
    )

    with pytest.raises(ValidationError, match="project_ref"):
        _builder_input(events=events)



class LaggingSeatAssignmentProjector(SeatAssignmentProjector):
    def project(self, events: tuple[EventRecord, ...]):
        projection = super().project(events)
        return projection.model_copy(update={"graph_version": projection.graph_version - 1})




def test_replay_bundle_rejects_projector_graph_version_mismatch() -> None:
    events = (_ticket_created_event(), _seat_assigned_event())
    resolver = InMemoryReplayPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _ticket_payload()},
        assignment_payloads={
            "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload()
        },
    )
    projector = LaggingSeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(),
    )

    with pytest.raises(ProjectionReplayError, match="projection version mismatch"):
        build_replay_bundle(
            _builder_input(
                events=events,
                seat_assignment_projector=projector,
            )
        )



def test_replay_bundle_rejects_naive_generated_at() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _builder_input(generated_at=datetime(2026, 5, 24, 11, 0))



def test_replay_bundle_rejects_placeholder_or_empty_hash() -> None:
    with pytest.raises(ValidationError, match="sha256"):
        ReplayArtifactManifestEntry(
            manifest_ref="artifact.bad",
            kind=ReplayManifestKind.REPLAY_REPORT,
            content_ref=REPORT_REF,
            sha256="placeholder",
        )


@pytest.mark.parametrize("placeholder_hash", ("0" * 64, "1" * 64, "f" * 64))
def test_replay_bundle_rejects_placeholder_sha256_digest(placeholder_hash: str) -> None:
    with pytest.raises(ValidationError, match="placeholder|synthetic|sha256"):
        ReplayContentHash(value=placeholder_hash)



def test_replay_bundle_allows_zero_previous_hash_for_first_event_only() -> None:
    bundle = build_replay_bundle(_builder_input())

    assert bundle.hash_manifest.event_hash_chain[0].previous_hash.value == "0" * 64
    assert all(
        node.previous_hash.value != "0" * 64
        for node in bundle.hash_manifest.event_hash_chain[1:]
    )



def test_replay_bundle_readiness_revalidates_hash_manifest() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["attestations"][0]["summary_hash"] = {
        "value": _fixture_hash("wrong.attestation.summary.hash")
    }

    with pytest.raises(ReplayBundleError, match="hash manifest mismatch"):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))




def test_replay_hash_manifest_rejects_duplicate_attestation_keys_after_trim() -> None:
    bundle = build_replay_bundle(_builder_input())
    attestation_hash = bundle.hash_manifest.attestation_hashes[
        bundle.attestations[0].attestation_id.value
    ]

    with pytest.raises(ValidationError, match="attestation_hashes.*unique"):
        ReplayHashManifest(
            hash_manifest_id=bundle.hash_manifest.hash_manifest_id,
            project_ref=bundle.hash_manifest.project_ref,
            event_hash_chain=bundle.hash_manifest.event_hash_chain,
            terminal_event_chain_hash=bundle.hash_manifest.terminal_event_chain_hash,
            event_window_hash=bundle.hash_manifest.event_window_hash,
            payload_manifest_hash=bundle.hash_manifest.payload_manifest_hash,
            artifact_manifest_hash=bundle.hash_manifest.artifact_manifest_hash,
            replay_report_hash=bundle.hash_manifest.replay_report_hash,
            attestation_hashes={
                "attestation.duplicate": attestation_hash,
                " attestation.duplicate ": attestation_hash,
            },
        )




@pytest.mark.parametrize(
    "summary_hash",
    (
        "abc123",
        "A" * 64,
        "g" * 64,
    ),
)
def test_replay_report_rejects_non_sha256_summary_hash(summary_hash: str) -> None:
    bundle = build_replay_bundle(_builder_input())
    report_payload = bundle.replay_report.model_dump(mode="python")
    report_payload["summary_hash"] = {"value": summary_hash}

    with pytest.raises(ValidationError, match="summary_hash|sha256"):
        type(bundle.replay_report).model_validate(report_payload)




@pytest.mark.parametrize(
    "summary_hash",
    (
        "abc123",
        "A" * 64,
        "g" * 64,
    ),
)
def test_replay_attestation_rejects_non_sha256_summary_hash(summary_hash: str) -> None:
    bundle = build_replay_bundle(_builder_input())
    attestation_payload = bundle.attestations[0].model_dump(mode="python")
    attestation_payload["summary_hash"] = {"value": summary_hash}

    with pytest.raises(ValidationError, match="summary_hash|sha256"):
        type(bundle.attestations[0]).model_validate(attestation_payload)



def test_replay_bundle_readiness_revalidates_payload_manifest_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["payload_manifest"]["entries"][0]["content_ref"] = "payload:tampered"

    with pytest.raises(ReplayBundleError, match="payload_manifest_hash"):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))



def test_replay_bundle_readiness_revalidates_artifact_manifest_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["artifact_manifest"]["entries"][0]["manifest_ref"] = "artifact.event_window.tampered"

    with pytest.raises(ReplayBundleError, match="artifact_manifest_hash|artifact manifest hash"):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))



def test_replay_bundle_readiness_revalidates_replay_report_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["replay_report"]["generated_at"] = (
        GENERATED_AT + timedelta(minutes=1)
    )

    with pytest.raises(ReplayBundleError, match="replay_report_hash"):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))



def test_replay_bundle_readiness_revalidates_attestation_event_window_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_bundle["attestations"][0]["event_window"]["last_event_id"] = {
        "value": "evt-seat-assigned-tampered"
    }

    with pytest.raises(
        (ReplayBundleError, ValidationError),
        match="event hash chain.*event_window|event_window_hash|attestation hash|events.*event_window",
    ):
        replay_bundle_readiness(type(bundle).model_validate(broken_bundle))




def test_replay_bundle_readiness_requires_attestation_event_window_hash_to_match_hash_manifest_even_if_rehashed() -> None:
    bundle = build_replay_bundle(_builder_input())
    attestation = bundle.attestations[0]
    tampered_event_window_hash = type(attestation.event_window_hash)(
        value=_fixture_hash("tampered.attestation.event_window_hash")
    )
    broken_attestation = attestation.model_copy(
        update={"event_window_hash": tampered_event_window_hash}
    )
    attestation_hash_type = type(
        bundle.hash_manifest.attestation_hashes[attestation.attestation_id.value]
    )
    broken_attestation_hash = attestation_hash_type(
        value=_hash_model(broken_attestation)
    )
    hash_manifest_input = _hash_manifest_logical_input(bundle, broken_attestation)
    broken_artifact_entries = tuple(
        ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref=entry.content_ref,
            sha256=_hash_jsonable(hash_manifest_input)
            if entry.kind is ReplayManifestKind.HASH_MANIFEST
            else entry.sha256,
        )
        for entry in bundle.artifact_manifest.entries
    )
    broken_artifact_manifest = bundle.artifact_manifest.model_copy(
        update={"entries": broken_artifact_entries}
    )
    broken_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "attestation_hashes": {
                broken_attestation.attestation_id.value: broken_attestation_hash
            },
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=_hash_model(broken_artifact_manifest)
            ),
        }
    )

    with pytest.raises(ReplayBundleError, match="event_window_hash"):
        replay_bundle_readiness(
            bundle.model_copy(
                update={
                    "attestations": (broken_attestation,),
                    "artifact_manifest": broken_artifact_manifest,
                    "hash_manifest": broken_hash_manifest,
                }
            )
        )



def test_replay_bundle_readiness_revalidates_event_previous_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_node = bundle.hash_manifest.event_hash_chain[1].model_copy(
        update={
            "previous_hash": type(
                bundle.hash_manifest.event_hash_chain[1].previous_hash
            )(value=_fixture_hash("wrong.previous.hash"))
        }
    )
    broken_manifest = bundle.hash_manifest.model_copy(
        update={
            "event_hash_chain": (
                bundle.hash_manifest.event_hash_chain[0],
                broken_node,
            )
        }
    )

    with pytest.raises(ReplayBundleError, match="event hash chain"):
        replay_bundle_readiness(bundle.model_copy(update={"hash_manifest": broken_manifest}))



def test_replay_bundle_readiness_revalidates_event_chain_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_node = bundle.hash_manifest.event_hash_chain[1].model_copy(
        update={
            "chain_hash": type(bundle.hash_manifest.event_hash_chain[1].chain_hash)(
                value=_fixture_hash("wrong.chain.hash")
            )
        }
    )
    broken_manifest = bundle.hash_manifest.model_copy(
        update={
            "event_hash_chain": (
                bundle.hash_manifest.event_hash_chain[0],
                broken_node,
            )
        }
    )

    with pytest.raises(ReplayBundleError, match="event hash chain"):
        replay_bundle_readiness(bundle.model_copy(update={"hash_manifest": broken_manifest}))




def test_replay_bundle_readiness_rejects_event_hash_rewrite_even_if_chain_and_manifests_are_rehashed() -> None:
    bundle = build_replay_bundle(_builder_input())
    first_event_hash = type(bundle.hash_manifest.event_hash_chain[0].event_hash)(
        value=_fixture_hash("tampered.first.event.hash")
    )
    first_chain_hash = type(bundle.hash_manifest.event_hash_chain[0].chain_hash)(
        value=_chain_hash(
            bundle.hash_manifest.event_hash_chain[0].previous_hash.value,
            first_event_hash.value,
        )
    )
    first_node = bundle.hash_manifest.event_hash_chain[0].model_copy(
        update={"event_hash": first_event_hash, "chain_hash": first_chain_hash}
    )
    second_chain_hash = type(bundle.hash_manifest.event_hash_chain[1].chain_hash)(
        value=_chain_hash(
            first_chain_hash.value,
            bundle.hash_manifest.event_hash_chain[1].event_hash.value,
        )
    )
    second_node = bundle.hash_manifest.event_hash_chain[1].model_copy(
        update={
            "previous_hash": type(bundle.hash_manifest.event_hash_chain[1].previous_hash)(
                value=first_chain_hash.value
            ),
            "chain_hash": second_chain_hash,
        }
    )
    broken_chain = (first_node, second_node)
    event_window_entry = bundle.artifact_manifest.entries_by_kind[ReplayManifestKind.EVENT_WINDOW]
    broken_event_window_hash = type(bundle.hash_manifest.event_window_hash)(
        value=_hash_jsonable(
            {
                "event_window": bundle.attestations[0].event_window.model_dump(mode="json"),
                "terminal_event_chain_hash": second_chain_hash.value,
                "event_window_ref": event_window_entry.content_ref.value,
            }
        )
    )
    broken_attestation = bundle.attestations[0].model_copy(
        update={"event_window_hash": broken_event_window_hash}
    )
    hash_manifest_input = _hash_manifest_logical_input(
        bundle,
        broken_attestation,
        event_hash_chain=broken_chain,
        terminal_event_chain_hash=second_chain_hash,
        event_window_hash=broken_event_window_hash,
    )
    broken_artifact_manifest = _artifact_manifest_with_expected_hashes(
        bundle=bundle,
        attestation=broken_attestation,
        event_window_hash=broken_event_window_hash,
        hash_manifest_input=hash_manifest_input,
    )
    broken_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "event_hash_chain": broken_chain,
            "terminal_event_chain_hash": second_chain_hash,
            "event_window_hash": broken_event_window_hash,
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=_hash_model(broken_artifact_manifest)
            ),
            "attestation_hashes": {
                broken_attestation.attestation_id.value: type(
                    bundle.hash_manifest.attestation_hashes[
                        broken_attestation.attestation_id.value
                    ]
                )(value=_hash_model(broken_attestation))
            },
        }
    )

    with pytest.raises(ReplayBundleError, match="event hash.*EventRecord|canonical"):
        replay_bundle_readiness(
            bundle.model_copy(
                update={
                    "attestations": (broken_attestation,),
                    "artifact_manifest": broken_artifact_manifest,
                    "hash_manifest": broken_hash_manifest,
                }
            )
        )



def test_replay_bundle_readiness_revalidates_terminal_event_chain_hash() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_manifest = bundle.hash_manifest.model_copy(
        update={
            "terminal_event_chain_hash": type(
                bundle.hash_manifest.terminal_event_chain_hash
            )(value=_fixture_hash("wrong.terminal.hash"))
        }
    )

    with pytest.raises(ReplayBundleError, match="terminal hash"):
        replay_bundle_readiness(bundle.model_copy(update={"hash_manifest": broken_manifest}))



def test_replay_bundle_readiness_rejects_chain_shorter_than_event_window_even_if_rehashed() -> None:
    bundle = build_replay_bundle(_builder_input())
    short_chain = (bundle.hash_manifest.event_hash_chain[0],)
    short_terminal = short_chain[-1].chain_hash
    event_window_entry = bundle.artifact_manifest.entries_by_kind[ReplayManifestKind.EVENT_WINDOW]
    short_event_window_hash = type(bundle.hash_manifest.event_window_hash)(
        value=_hash_jsonable(
            {
                "event_window": bundle.attestations[0].event_window.model_dump(mode="json"),
                "terminal_event_chain_hash": short_terminal.value,
                "event_window_ref": event_window_entry.content_ref.value,
            }
        )
    )
    short_hash_manifest = ReplayHashManifest(
        hash_manifest_id=bundle.hash_manifest.hash_manifest_id,
        project_ref=bundle.hash_manifest.project_ref,
        event_hash_chain=short_chain,
        terminal_event_chain_hash=short_terminal,
        event_window_hash=short_event_window_hash,
        payload_manifest_hash=bundle.hash_manifest.payload_manifest_hash,
        artifact_manifest_hash=bundle.hash_manifest.artifact_manifest_hash,
        replay_report_hash=bundle.hash_manifest.replay_report_hash,
        attestation_hashes=bundle.hash_manifest.attestation_hashes,
    )

    with pytest.raises(ReplayBundleError, match="event hash chain.*event_window"):
        replay_bundle_readiness(bundle.model_copy(update={"hash_manifest": short_hash_manifest}))



def test_replay_bundle_readiness_rejects_missing_artifact_kind_even_if_rehashed() -> None:
    bundle = build_replay_bundle(_builder_input())
    kept_entries = tuple(
        entry
        for entry in bundle.artifact_manifest.entries
        if entry.kind is not ReplayManifestKind.REPLAY_REPORT
    )
    broken_artifact_manifest = bundle.artifact_manifest.model_copy(
        update={"entries": kept_entries}
    )
    broken_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=_hash_model(broken_artifact_manifest)
            )
        }
    )

    with pytest.raises(ReplayBundleError, match="artifact manifest missing"):
        replay_bundle_readiness(
            bundle.model_copy(
                update={
                    "artifact_manifest": broken_artifact_manifest,
                    "hash_manifest": broken_hash_manifest,
                }
            )
        )




def test_replay_bundle_readiness_rejects_artifact_content_ref_mismatch_even_if_rehashed() -> None:
    bundle = build_replay_bundle(_builder_input())
    broken_entries = tuple(
        ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref="report.replay.wrong-ref"
            if entry.kind is ReplayManifestKind.REPLAY_REPORT
            else entry.content_ref,
            sha256=entry.sha256,
        )
        for entry in bundle.artifact_manifest.entries
    )
    structure_only_manifest = bundle.artifact_manifest.model_copy(
        update={"entries": broken_entries}
    )
    closed_entries = tuple(
        ReplayArtifactManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref=entry.content_ref,
            sha256=_artifact_manifest_structure_hash(structure_only_manifest)
            if entry.kind is ReplayManifestKind.ARTIFACT_MANIFEST
            else entry.sha256,
        )
        for entry in broken_entries
    )
    broken_artifact_manifest = bundle.artifact_manifest.model_copy(
        update={"entries": closed_entries}
    )
    broken_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=_hash_model(broken_artifact_manifest)
            )
        }
    )

    with pytest.raises(ReplayBundleError, match="content ref"):
        replay_bundle_readiness(
            bundle.model_copy(
                update={
                    "artifact_manifest": broken_artifact_manifest,
                    "hash_manifest": broken_hash_manifest,
                }
            )
        )




def test_replay_bundle_readiness_rejects_event_window_content_ref_mismatch_even_if_rehashed() -> None:
    bundle = build_replay_bundle(_builder_input())
    wrong_event_window_ref = "event-range.project-tiny-fullstack.999-1000"
    broken_event_window_hash = type(bundle.hash_manifest.event_window_hash)(
        value=_hash_jsonable(
            {
                "event_window": bundle.attestations[0].event_window.model_dump(mode="json"),
                "terminal_event_chain_hash": bundle.hash_manifest.terminal_event_chain_hash.value,
                "event_window_ref": wrong_event_window_ref,
            }
        )
    )
    broken_attestation = bundle.attestations[0].model_copy(
        update={"event_window_hash": broken_event_window_hash}
    )
    hash_manifest_input = _hash_manifest_logical_input(
        bundle,
        broken_attestation,
        event_window_hash=broken_event_window_hash,
    )
    broken_artifact_manifest = _artifact_manifest_with_expected_hashes(
        bundle=bundle,
        attestation=broken_attestation,
        event_window_hash=broken_event_window_hash,
        hash_manifest_input=hash_manifest_input,
        content_ref_overrides={ReplayManifestKind.EVENT_WINDOW: wrong_event_window_ref},
    )
    broken_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "event_window_hash": broken_event_window_hash,
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=_hash_model(broken_artifact_manifest)
            ),
            "attestation_hashes": {
                broken_attestation.attestation_id.value: type(
                    bundle.hash_manifest.attestation_hashes[
                        broken_attestation.attestation_id.value
                    ]
                )(value=_hash_model(broken_attestation))
            },
        }
    )

    with pytest.raises(ReplayBundleError, match="content ref.*event_window"):
        replay_bundle_readiness(
            bundle.model_copy(
                update={
                    "attestations": (broken_attestation,),
                    "artifact_manifest": broken_artifact_manifest,
                    "hash_manifest": broken_hash_manifest,
                }
            )
        )



def test_replay_report_requires_passed_true_and_empty_blockers() -> None:
    bundle = build_replay_bundle(_builder_input())
    report_payload = bundle.replay_report.model_dump(mode="python")
    report_payload["replay_passed"] = False

    with pytest.raises(ValidationError, match="replay_passed"):
        type(bundle.replay_report).model_validate(report_payload)

    report_payload = bundle.replay_report.model_dump(mode="python")
    report_payload["blockers"] = ("projection failed",)

    with pytest.raises(ValidationError, match="blockers"):
        type(bundle.replay_report).model_validate(report_payload)



def test_replay_bundle_builds_seat_assignment_attestation_from_rereplay() -> None:
    events = (_ticket_created_event(), _seat_assigned_event())
    summary = ProjectionReplay(projection_kind="seat_assignment_graph").replay_events(
        events=events,
        project_ref=PROJECT_REF,
        expected_graph_version=events[-1].graph_version,
        projector=_projector(),
    )

    bundle = build_replay_bundle(_builder_input(events=events))

    assert bundle.version == 1
    assert len(bundle.attestations) == 1
    assert bundle.attestations[0].kind is ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH
    assert bundle.attestations[0].summary_hash.value == summary.summary_hash
    assert bundle.attestations[0].event_window.first_graph_version == summary.event_range.first_graph_version
    assert bundle.attestations[0].event_window.last_graph_version == summary.event_range.last_graph_version
    assert bundle.attestations[0].projection_kind == ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value



def test_replay_bundle_hash_chain_proves_event_window_integrity() -> None:
    bundle = build_replay_bundle(_builder_input())

    assert len(bundle.hash_manifest.event_hash_chain) == 2
    assert bundle.hash_manifest.event_hash_chain[0].previous_hash.value == "0" * 64
    assert (
        bundle.hash_manifest.event_hash_chain[-1].chain_hash
        == bundle.hash_manifest.terminal_event_chain_hash
    )

    tampered_node = bundle.hash_manifest.event_hash_chain[0].model_dump(mode="python")
    tampered_node["event_hash"] = _fixture_hash("wrong.event.hash")
    broken_bundle = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_chain = list(broken_bundle["hash_manifest"]["event_hash_chain"])
    broken_chain[0] = tampered_node
    broken_bundle["hash_manifest"]["event_hash_chain"] = tuple(broken_chain)

    with pytest.raises(ValidationError, match="event hash chain"):
        type(bundle).model_validate(broken_bundle)



def test_replay_bundle_readiness_matches_closeout_gate_contract() -> None:
    readiness = replay_bundle_readiness(build_replay_bundle(_builder_input()))

    assert isinstance(readiness, ReplayBundleReadiness)
    assert readiness.replay_passed is True
    assert readiness.hash_chain_verified is True
    assert readiness.projection_versions == (PROJECTION_VERSION,)
    assert readiness.event_range == EventRangeRef(
        value="event-range.project-tiny-fullstack.1-2"
    )



def test_replay_bundle_is_audit_friendly_json() -> None:
    first_bundle = build_replay_bundle(_builder_input())
    second_bundle = build_replay_bundle(_builder_input())

    payload = first_bundle.model_dump(mode="json")
    serialized = str(payload)

    assert "D:/" not in serialized
    assert "\\" not in serialized
    assert first_bundle.replay_bundle_id == second_bundle.replay_bundle_id
    assert first_bundle.bundle_hash == second_bundle.bundle_hash



def test_replay_bundle_does_not_define_unimplemented_projection_names() -> None:
    assert tuple(kind.value for kind in ReplayAttestationKind) == ("seat_assignment_graph",)
    assert "ticket_graph" not in {kind.value for kind in ReplayAttestationKind}
    assert "evidence_map" not in {kind.value for kind in ReplayAttestationKind}
    assert "closeout_reducer" not in {kind.value for kind in ReplayAttestationKind}
