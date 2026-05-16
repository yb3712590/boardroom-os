from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from boardroom_os.agents.seat import AgentSeat, AgentSeatRef, SeatLifecycleProjection
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventPayloadRef, EventType
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.ticket import (
    TicketCreatedPayload,
    TicketGraph,
    TicketId,
    TicketNode,
    TicketStatus,
)


class SeatAssignmentProjectionError(ValueError):
    pass


class SeatAssignmentPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: TicketId
    seat_ref: AgentSeatRef


class SeatAssignmentGraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    graph_version: int = Field(gt=0)
    nodes: dict[TicketId, TicketNode]
    blocked_by: dict[TicketId, tuple[TicketId, ...]]
    ready_queue: tuple[TicketId, ...]
    completed_nodes: tuple[TicketId, ...]
    seat_assignments: dict[TicketId, AgentSeatRef]
    seat_blockers: dict[TicketId, tuple[str, ...]]

    @classmethod
    def from_ticket_graph(
        cls,
        ticket_graph: TicketGraph,
        *,
        seat_assignments: dict[TicketId, AgentSeatRef],
        seat_blockers: dict[TicketId, tuple[str, ...]],
    ) -> "SeatAssignmentGraph":
        nodes = dict(ticket_graph.nodes)
        for ticket_id in seat_blockers:
            existing = nodes[ticket_id]
            nodes[ticket_id] = existing.model_copy(update={"status": TicketStatus.BLOCKED})

        blocked_ticket_ids = frozenset(seat_blockers)
        ready_queue = tuple(
            ticket_id
            for ticket_id in ticket_graph.ready_queue
            if ticket_id not in blocked_ticket_ids
        )
        return cls(
            graph_version=ticket_graph.graph_version,
            nodes=nodes,
            blocked_by=ticket_graph.blocked_by,
            ready_queue=ready_queue,
            completed_nodes=ticket_graph.completed_nodes,
            seat_assignments=seat_assignments,
            seat_blockers=seat_blockers,
        )


class SeatAssignmentPayloadResolver(Protocol):
    def resolve_ticket_created(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCreatedPayload: ...

    def resolve_seat_assignment(
        self,
        payload_ref: EventPayloadRef,
    ) -> SeatAssignmentPayload: ...


class SeatAssignmentProjector:
    def __init__(
        self,
        *,
        ticket_projector: TicketGraphProjector,
        payload_resolver: SeatAssignmentPayloadResolver,
        seat_projection: SeatLifecycleProjection,
    ) -> None:
        self._ticket_projector = ticket_projector
        self._payload_resolver = payload_resolver
        self._seat_projection = seat_projection

    def project(self, events: tuple[EventRecord, ...]) -> SeatAssignmentGraph:
        ticket_graph = self._ticket_projector.project(events)
        seat_assignments: dict[TicketId, AgentSeatRef] = {}
        seat_blockers: dict[TicketId, tuple[str, ...]] = {}
        created_versions_by_ticket_id: dict[TicketId, int] = {}

        for event in sorted(events, key=lambda item: item.graph_version):
            if event.event_type is EventType.TICKET_CREATED:
                ticket = self._ticket_from_created_event(ticket_graph, event)
                created_versions_by_ticket_id[ticket.ticket_id] = event.graph_version
                continue

            if event.event_type is not EventType.SEAT_ASSIGNED:
                continue

            if len(event.payload_refs) != 1:
                raise SeatAssignmentProjectionError(
                    "seat assignment event must have exactly one payload_ref"
                )

            payload = self._resolve_seat_assignment(event.payload_refs[0])
            ticket = ticket_graph.nodes.get(payload.ticket_id)
            if ticket is None:
                raise SeatAssignmentProjectionError(
                    f"ticket does not exist: {payload.ticket_id.value}"
                )

            created_version = created_versions_by_ticket_id.get(payload.ticket_id)
            if created_version is None:
                raise SeatAssignmentProjectionError(
                    f"seat assignment before ticket created: {payload.ticket_id.value}"
                )

            blockers = self._assignment_blockers(ticket=ticket, payload=payload)
            if blockers:
                seat_blockers[payload.ticket_id] = blockers
                seat_assignments.pop(payload.ticket_id, None)
                continue

            seat_assignments[payload.ticket_id] = payload.seat_ref
            seat_blockers.pop(payload.ticket_id, None)

        for ticket_id in ticket_graph.nodes:
            if ticket_id not in seat_assignments and ticket_id not in seat_blockers:
                seat_blockers[ticket_id] = ("missing seat assignment",)

        return SeatAssignmentGraph.from_ticket_graph(
            ticket_graph,
            seat_assignments=seat_assignments,
            seat_blockers=seat_blockers,
        )

    def _ticket_from_created_event(
        self,
        ticket_graph: TicketGraph,
        event: EventRecord,
    ) -> TicketNode:
        if len(event.payload_refs) != 1:
            raise SeatAssignmentProjectionError(
                "ticket created event must have exactly one payload_ref"
            )
        payload = self._resolve_ticket_created(event.payload_refs[0])
        ticket = ticket_graph.nodes.get(payload.ticket_id)
        if ticket is None:
            raise SeatAssignmentProjectionError(
                f"ticket does not exist: {payload.ticket_id.value}"
            )
        return ticket

    def _resolve_ticket_created(
        self, payload_ref: EventPayloadRef
    ) -> TicketCreatedPayload:
        try:
            return self._payload_resolver.resolve_ticket_created(payload_ref)
        except Exception as error:
            raise SeatAssignmentProjectionError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _resolve_seat_assignment(
        self, payload_ref: EventPayloadRef
    ) -> SeatAssignmentPayload:
        try:
            return self._payload_resolver.resolve_seat_assignment(payload_ref)
        except Exception as error:
            raise SeatAssignmentProjectionError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _assignment_blockers(
        self,
        *,
        ticket: TicketNode,
        payload: SeatAssignmentPayload,
    ) -> tuple[str, ...]:
        seat: AgentSeat | None = self._seat_projection.active_seats.get(payload.seat_ref)
        if seat is None:
            return (
                f"team composition gap: inactive or unknown seat: {payload.seat_ref.value}",
            )

        demand = ticket.seat_demand
        if seat.role_category is not demand.required_role_category:
            return (
                "team composition gap: role category mismatch: "
                f"{seat.role_category.value} != {demand.required_role_category.value}",
            )

        missing_capability_tags = tuple(
            capability_tag.value
            for capability_tag in demand.required_capability_tags
            if capability_tag not in seat.capability_tags
        )
        if missing_capability_tags:
            return (
                "team composition gap: missing capability tags: "
                + ", ".join(missing_capability_tags),
            )

        return ()
