from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from boardroom_os.events.log import InMemoryEventLog
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventId, ProjectRef
from boardroom_os.graph.projection import TicketGraphProjectionError
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentGraph,
    SeatAssignmentProjectionError,
    SeatAssignmentProjector,
)

ProjectionKind = Literal["seat_assignment_graph"]


class ProjectionReplayError(ValueError):
    pass


class ProjectionReplayEventRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    first_graph_version: int = Field(gt=0)
    last_graph_version: int = Field(gt=0)
    first_event_id: EventId
    last_event_id: EventId


class ProjectionReplaySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    projection_kind: ProjectionKind
    project_ref: ProjectRef
    event_range: ProjectionReplayEventRange
    event_count: int = Field(gt=0)
    graph_version: int = Field(gt=0)
    nodes: dict[str, dict[str, object]]
    blocked_by: dict[str, tuple[str, ...]]
    ready_queue: tuple[str, ...]
    completed_nodes: tuple[str, ...]
    seat_assignments: dict[str, str]
    seat_blockers: dict[str, tuple[str, ...]]

    @computed_field
    @property
    def summary_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"summary_hash"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()


class ProjectionReplay:
    def __init__(self, *, projection_kind: ProjectionKind) -> None:
        self._projection_kind = projection_kind

    def replay(
        self,
        *,
        event_log: InMemoryEventLog,
        project_ref: ProjectRef,
        expected_graph_version: int,
        projector: SeatAssignmentProjector,
        from_graph_version: int | None = None,
        to_graph_version: int | None = None,
    ) -> ProjectionReplaySummary:
        self._validate_replay_range(from_graph_version)
        events = event_log.read(
            project_ref,
            from_graph_version=from_graph_version,
            to_graph_version=to_graph_version,
        )
        return self.replay_events(
            events=events,
            project_ref=project_ref,
            expected_graph_version=expected_graph_version,
            projector=projector,
        )

    def replay_events(
        self,
        *,
        events: tuple[EventRecord, ...],
        project_ref: ProjectRef,
        expected_graph_version: int,
        projector: SeatAssignmentProjector,
    ) -> ProjectionReplaySummary:
        self._validate_expected_graph_version(expected_graph_version)
        self._validate_events(events=events, project_ref=project_ref)
        try:
            projection = projector.project(events)
        except (SeatAssignmentProjectionError, TicketGraphProjectionError) as error:
            raise ProjectionReplayError(f"projection failed: {error}") from error

        if projection.graph_version != expected_graph_version:
            raise ProjectionReplayError(
                "projection version mismatch: "
                f"expected {expected_graph_version}, got {projection.graph_version}"
            )

        return self._summary(
            project_ref=project_ref,
            events=events,
            projection=projection,
        )

    def _validate_expected_graph_version(self, expected_graph_version: int) -> None:
        if expected_graph_version <= 0:
            raise ProjectionReplayError("expected_graph_version must be positive")

    def _validate_replay_range(self, from_graph_version: int | None) -> None:
        if from_graph_version is not None and from_graph_version != 1:
            raise ProjectionReplayError(
                "from_graph_version requires snapshot or base projection contract"
            )

    def _validate_events(
        self,
        *,
        events: tuple[EventRecord, ...],
        project_ref: ProjectRef,
    ) -> None:
        if not events:
            raise ProjectionReplayError("event range must not be empty")

        previous_graph_version: int | None = None
        for event in events:
            if event.project_ref != project_ref:
                raise ProjectionReplayError(
                    "event project_ref mismatch: "
                    f"expected {project_ref.value}, got {event.project_ref.value}"
                )
            if previous_graph_version is not None:
                if event.graph_version <= previous_graph_version:
                    raise ProjectionReplayError(
                        "graph_version must be strictly ordered in replay input"
                    )
                if event.graph_version != previous_graph_version + 1:
                    raise ProjectionReplayError(
                        "graph_version must be contiguous in replay input"
                    )
            previous_graph_version = event.graph_version

    def _summary(
        self,
        *,
        project_ref: ProjectRef,
        events: tuple[EventRecord, ...],
        projection: SeatAssignmentGraph,
    ) -> ProjectionReplaySummary:
        return ProjectionReplaySummary(
            projection_kind=self._projection_kind,
            project_ref=project_ref,
            event_range=ProjectionReplayEventRange(
                first_graph_version=events[0].graph_version,
                last_graph_version=events[-1].graph_version,
                first_event_id=events[0].event_id,
                last_event_id=events[-1].event_id,
            ),
            event_count=len(events),
            graph_version=projection.graph_version,
            nodes={
                ticket_id.value: ticket.model_dump(mode="json")
                for ticket_id, ticket in projection.nodes.items()
            },
            blocked_by={
                ticket_id.value: tuple(dependency.value for dependency in dependencies)
                for ticket_id, dependencies in projection.blocked_by.items()
            },
            ready_queue=tuple(ticket_id.value for ticket_id in projection.ready_queue),
            completed_nodes=tuple(
                ticket_id.value for ticket_id in projection.completed_nodes
            ),
            seat_assignments={
                ticket_id.value: seat_ref.value
                for ticket_id, seat_ref in projection.seat_assignments.items()
            },
            seat_blockers={
                ticket_id.value: blockers
                for ticket_id, blockers in projection.seat_blockers.items()
            },
        )
