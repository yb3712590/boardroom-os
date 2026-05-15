from typing import Protocol

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventPayloadRef, EventType
from boardroom_os.graph.ticket import (
    TicketBlockedPayload,
    TicketCreatedPayload,
    TicketGraph,
    TicketId,
    TicketNode,
    TicketStatus,
)


class TicketGraphProjectionError(ValueError):
    pass


class TicketPayloadResolver(Protocol):
    def resolve_ticket_created(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCreatedPayload: ...

    def resolve_ticket_blocked(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketBlockedPayload: ...


class TicketGraphProjector:
    def __init__(self, payload_resolver: TicketPayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def project(self, events: tuple[EventRecord, ...]) -> TicketGraph:
        if not events:
            raise TicketGraphProjectionError("events must not be empty")

        nodes_by_id: dict[TicketId, TicketNode] = {}
        latest_graph_version = 0
        for event in sorted(events, key=lambda item: item.graph_version):
            latest_graph_version = event.graph_version
            payload_ref = event.payload_refs[0]
            if event.event_type is EventType.TICKET_CREATED:
                payload = self._resolve_created_payload(payload_ref)
                if payload.ticket_id in nodes_by_id:
                    raise TicketGraphProjectionError(
                        f"ticket already exists: {payload.ticket_id.value}"
                    )
                nodes_by_id[payload.ticket_id] = TicketNode.from_created_payload(payload)
                continue

            if event.event_type is EventType.TICKET_BLOCKED:
                payload = self._resolve_blocked_payload(payload_ref)
                existing = nodes_by_id.get(payload.ticket_id)
                if existing is None:
                    raise TicketGraphProjectionError(
                        "ticket must exist before blocked event: "
                        f"{payload.ticket_id.value}"
                    )
                nodes_by_id[payload.ticket_id] = existing.model_copy(
                    update={"status": TicketStatus.BLOCKED}
                )
                continue

            if event.event_type.value.startswith("ticket_"):
                raise TicketGraphProjectionError(
                    f"unsupported ticket event: {event.event_type.value}"
                )

        try:
            return TicketGraph.from_nodes(
                graph_version=latest_graph_version,
                nodes=tuple(nodes_by_id.values()),
            )
        except ValueError as error:
            raise TicketGraphProjectionError(str(error)) from error

    def _resolve_created_payload(
        self, payload_ref: EventPayloadRef
    ) -> TicketCreatedPayload:
        try:
            return self._payload_resolver.resolve_ticket_created(payload_ref)
        except Exception as error:
            raise TicketGraphProjectionError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _resolve_blocked_payload(
        self, payload_ref: EventPayloadRef
    ) -> TicketBlockedPayload:
        try:
            return self._payload_resolver.resolve_ticket_blocked(payload_ref)
        except Exception as error:
            raise TicketGraphProjectionError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error
