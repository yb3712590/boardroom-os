import pytest
from pydantic import ValidationError

from boardroom_os.agents.seat import RoleCategory
from boardroom_os.graph.seat_assignment import SeatAssignmentPayload
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId, TicketStatus
from tests.proving.fixtures.tiny_ticket_graph import (
    SEAT_CHECKER_REF,
    SEAT_WORKER_BACKEND_REF,
    TICKET_ARCHITECTURE_ID,
    TICKET_BACKEND_API_ID,
    TICKET_CHECKER_ID,
    TICKET_DOCS_RUN_MANIFEST_ID,
    TICKET_FRONTEND_UI_ID,
    TICKET_GOVERNANCE_ID,
    TICKET_TESTS_ID,
    TinyTicketGraphFixture,
    build_tiny_ticket_graph_fixture,
)


def _project_without_assignment(
    fixture: TinyTicketGraphFixture,
    missing_ticket_id: TicketId,
):
    assignment_payload_ref = fixture.assignment_payload_refs_by_ticket_id[missing_ticket_id]
    events = tuple(
        event
        for event in fixture.events
        if assignment_payload_ref not in event.payload_refs
    )

    return fixture.seat_assignment_projector.project(events)


def test_worker_ticket_without_seat_assignment_is_removed_from_ready_queue() -> None:
    fixture = build_tiny_ticket_graph_fixture()

    graph = _project_without_assignment(fixture, TICKET_BACKEND_API_ID)

    assert TICKET_BACKEND_API_ID not in graph.ready_queue
    assert graph.nodes[TICKET_BACKEND_API_ID].status is TicketStatus.BLOCKED
    assert graph.seat_blockers[TICKET_BACKEND_API_ID] == ("missing seat assignment",)
    assert TICKET_BACKEND_API_ID not in graph.seat_assignments


def test_checker_ticket_assigned_to_worker_seat_fails_closed() -> None:
    fixture = build_tiny_ticket_graph_fixture()
    wrong_assignment = SeatAssignmentPayload(
        ticket_id=TICKET_CHECKER_ID,
        seat_ref=SEAT_WORKER_BACKEND_REF,
    )
    resolver = fixture.payload_resolver.with_assignment_payload(
        fixture.assignment_payload_refs_by_ticket_id[TICKET_CHECKER_ID],
        wrong_assignment,
    )

    graph = fixture.build_seat_assignment_projector(resolver).project(fixture.events)

    assert TICKET_CHECKER_ID not in graph.seat_assignments
    assert graph.seat_blockers[TICKET_CHECKER_ID]
    assert "role category mismatch" in graph.seat_blockers[TICKET_CHECKER_ID][0]


def test_ticket_missing_evidence_obligations_fails_closed() -> None:
    fixture = build_tiny_ticket_graph_fixture()
    backend_payload = fixture.ticket_payloads_by_id[TICKET_BACKEND_API_ID]
    values = backend_payload.model_dump()
    values.pop("evidence_obligations")

    with pytest.raises(ValidationError):
        TicketCreatedPayload(**values)


def test_all_tickets_have_active_seat_assignments() -> None:
    fixture = build_tiny_ticket_graph_fixture()

    assert fixture.seat_assignment_graph.seat_blockers == {}
    assert set(fixture.seat_assignment_graph.seat_assignments) == set(fixture.ticket_ids)
    assert fixture.seat_assignment_graph.seat_assignments[TICKET_CHECKER_ID] == SEAT_CHECKER_REF
    for seat_ref in fixture.seat_assignment_graph.seat_assignments.values():
        assert seat_ref in fixture.seat_projection.active_seats


def test_implementation_ticket_contract_fields_come_from_active_contracts() -> None:
    fixture = build_tiny_ticket_graph_fixture()
    expected_acceptance_refs_by_ticket = {
        TICKET_BACKEND_API_ID: {
            "AC-TINY-API-BOOK-CREATE",
            "AC-TINY-API-BOOK-LIST",
            "AC-TINY-API-CHECKOUT-RETURN",
            "AC-TINY-API-BOOK-DELETE",
            "AC-TINY-PERSISTENCE-SQLITE",
        },
        TICKET_FRONTEND_UI_ID: {"AC-TINY-UI-FETCH-BACKEND"},
        TICKET_TESTS_ID: {
            "AC-TINY-API-BOOK-CREATE",
            "AC-TINY-API-BOOK-LIST",
            "AC-TINY-API-CHECKOUT-RETURN",
            "AC-TINY-API-BOOK-DELETE",
            "AC-TINY-PERSISTENCE-SQLITE",
            "AC-TINY-UI-FETCH-BACKEND",
            "AC-TINY-RUN-TEST-COMMANDS",
        },
        TICKET_DOCS_RUN_MANIFEST_ID: {"AC-TINY-RUN-TEST-COMMANDS"},
    }
    expected_source_surface_refs_by_ticket = {
        TICKET_BACKEND_API_ID: {"backend-api", "persistence", "tests"},
        TICKET_FRONTEND_UI_ID: {"frontend-ui", "tests"},
        TICKET_TESTS_ID: {"backend-api", "persistence", "frontend-ui", "tests", "run-manifest"},
        TICKET_DOCS_RUN_MANIFEST_ID: {"docs", "run-manifest", "tests"},
    }
    expected_obligation_refs_by_ticket = {
        ticket_id: {
            obligation.evidence_obligation_id.value
            for obligation in fixture.contracts.contract_gate.evidence_obligations
            if any(
                acceptance_ref.value in expected_acceptance_refs
                for acceptance_ref in obligation.acceptance_refs
            )
        }
        for ticket_id, expected_acceptance_refs in expected_acceptance_refs_by_ticket.items()
    }

    for ticket_id, expected_acceptance_refs in expected_acceptance_refs_by_ticket.items():
        ticket = fixture.seat_assignment_graph.nodes[ticket_id]
        assert set(ticket.acceptance_refs) == expected_acceptance_refs
        assert set(ticket.source_surface_refs) == expected_source_surface_refs_by_ticket[ticket_id]
        assert set(ticket.evidence_obligations) == expected_obligation_refs_by_ticket[ticket_id]


def test_initial_ready_queue_contains_assigned_dependency_free_work() -> None:
    fixture = build_tiny_ticket_graph_fixture()

    assert fixture.seat_assignment_graph.ready_queue == (
        TICKET_GOVERNANCE_ID,
        TICKET_ARCHITECTURE_ID,
        TICKET_BACKEND_API_ID,
        TICKET_FRONTEND_UI_ID,
        TICKET_TESTS_ID,
        TICKET_DOCS_RUN_MANIFEST_ID,
    )
    assert TICKET_CHECKER_ID not in fixture.seat_assignment_graph.ready_queue
    assert fixture.seat_assignment_graph.blocked_by[TICKET_CHECKER_ID] == (
        TICKET_BACKEND_API_ID,
        TICKET_FRONTEND_UI_ID,
        TICKET_TESTS_ID,
        TICKET_DOCS_RUN_MANIFEST_ID,
    )


def test_checker_ticket_uses_verification_seat_and_waits_for_implementation() -> None:
    fixture = build_tiny_ticket_graph_fixture()
    checker_ticket = fixture.seat_assignment_graph.nodes[TICKET_CHECKER_ID]

    assert checker_ticket.seat_demand.required_role_category is RoleCategory.VERIFICATION
    assert fixture.seat_assignment_graph.seat_assignments[TICKET_CHECKER_ID] == SEAT_CHECKER_REF
    assert TICKET_CHECKER_ID in fixture.seat_assignment_graph.blocked_by
    assert TICKET_CHECKER_ID not in fixture.seat_assignment_graph.ready_queue


def test_checker_ticket_becomes_ready_when_dependency_projection_marks_implementation_complete() -> None:
    fixture = build_tiny_ticket_graph_fixture()

    advanced_graph = fixture.project_with_completed_dependency_nodes(
        fixture.implementation_ticket_ids,
    )

    assert TICKET_CHECKER_ID in advanced_graph.ready_queue
    assert TICKET_CHECKER_ID not in advanced_graph.blocked_by
    for ticket_id in fixture.implementation_ticket_ids:
        assert advanced_graph.nodes[ticket_id].status is TicketStatus.COMPLETED
