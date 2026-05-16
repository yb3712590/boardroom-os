from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NonEmptyGraphValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _reject_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class TicketId(NonEmptyGraphValue):
    pass


class TicketStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class _TicketFields(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: TicketId
    purpose: str
    owner_seat_ref: str
    depends_on: tuple[TicketId, ...] = ()
    acceptance_refs: tuple[str, ...]
    source_surface_refs: tuple[str, ...]
    evidence_obligations: tuple[str, ...]
    allowed_read_refs: tuple[str, ...] = ()
    allowed_write_set: tuple[str, ...]
    attempt_count: int = Field(ge=0)

    @field_validator("purpose", "owner_seat_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator(
        "acceptance_refs",
        "source_surface_refs",
        "evidence_obligations",
        "allowed_write_set",
    )
    @classmethod
    def _reject_empty_required_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("required tuple must not be empty")
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("required tuple values must not be empty")
        return normalized_values

    @field_validator("allowed_read_refs")
    @classmethod
    def _normalize_allowed_read_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("allowed read refs must not be empty")
        return normalized_values


class TicketCreatedPayload(_TicketFields):
    pass


class TicketBlockedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: TicketId


class TicketNode(_TicketFields):
    status: TicketStatus

    @classmethod
    def from_created_payload(cls, payload: TicketCreatedPayload) -> "TicketNode":
        return cls(**payload.model_dump(), status=TicketStatus.READY)


class TicketGraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    graph_version: int = Field(gt=0)
    nodes: dict[TicketId, TicketNode]
    blocked_by: dict[TicketId, tuple[TicketId, ...]]
    ready_queue: tuple[TicketId, ...]
    completed_nodes: tuple[TicketId, ...]

    @classmethod
    def from_nodes(
        cls, *, graph_version: int, nodes: tuple[TicketNode, ...]
    ) -> "TicketGraph":
        node_map: dict[TicketId, TicketNode] = {}
        for node in nodes:
            if node.ticket_id in node_map:
                raise ValueError(f"duplicate ticket_id: {node.ticket_id.value}")
            node_map[node.ticket_id] = node

        known_ids = frozenset(node_map)
        for node in nodes:
            unknown_dependencies = tuple(
                dependency for dependency in node.depends_on if dependency not in known_ids
            )
            if unknown_dependencies:
                dependency_list = ", ".join(
                    dependency.value for dependency in unknown_dependencies
                )
                raise ValueError(
                    f"unknown dependency for {node.ticket_id.value}: {dependency_list}"
                )

        cls._reject_dependency_cycles(node_map)

        completed = tuple(
            node.ticket_id for node in nodes if node.status is TicketStatus.COMPLETED
        )
        completed_set = frozenset(completed)
        blocked_by = {
            node.ticket_id: unsatisfied_dependencies
            for node in nodes
            if (
                unsatisfied_dependencies := tuple(
                    dependency
                    for dependency in node.depends_on
                    if dependency not in completed_set
                )
            )
        }
        ready_queue = tuple(
            node.ticket_id
            for node in nodes
            if node.status is TicketStatus.READY and node.ticket_id not in blocked_by
        )
        return cls(
            graph_version=graph_version,
            nodes=node_map,
            blocked_by=blocked_by,
            ready_queue=ready_queue,
            completed_nodes=completed,
        )

    @classmethod
    def _reject_dependency_cycles(cls, nodes_by_id: dict[TicketId, TicketNode]) -> None:
        visited: set[TicketId] = set()
        visiting: set[TicketId] = set()

        def visit(ticket_id: TicketId) -> None:
            if ticket_id in visiting:
                raise ValueError(f"dependency cycle includes: {ticket_id.value}")
            if ticket_id in visited:
                return
            visiting.add(ticket_id)
            for dependency in nodes_by_id[ticket_id].depends_on:
                visit(dependency)
            visiting.remove(ticket_id)
            visited.add(ticket_id)

        for ticket_id in nodes_by_id:
            visit(ticket_id)
