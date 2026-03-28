from __future__ import annotations

from fastapi import APIRouter, Request

from app.contracts.commands import (
    BoardApproveCommand,
    BoardRejectCommand,
    CommandAckEnvelope,
    ModifyConstraintsCommand,
    ProjectInitCommand,
    SchedulerTickCommand,
    TicketCompletedCommand,
    TicketCreateCommand,
    TicketFailCommand,
    TicketLeaseCommand,
    TicketStartCommand,
)
from app.core.approval_handlers import (
    handle_board_approve,
    handle_board_reject,
    handle_modify_constraints,
)
from app.core.command_handlers import handle_project_init
from app.core.ticket_handlers import (
    handle_scheduler_tick,
    handle_ticket_completed,
    handle_ticket_create,
    handle_ticket_fail,
    handle_ticket_lease,
    handle_ticket_start,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


@router.post("/project-init", response_model=CommandAckEnvelope)
def project_init(request: Request, payload: ProjectInitCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_project_init(repository, payload)


@router.post("/ticket-create", response_model=CommandAckEnvelope)
def ticket_create(request: Request, payload: TicketCreateCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_create(repository, payload)


@router.post("/ticket-lease", response_model=CommandAckEnvelope)
def ticket_lease(request: Request, payload: TicketLeaseCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_lease(repository, payload)


@router.post("/ticket-start", response_model=CommandAckEnvelope)
def ticket_start(request: Request, payload: TicketStartCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_start(repository, payload)


@router.post("/ticket-fail", response_model=CommandAckEnvelope)
def ticket_fail(request: Request, payload: TicketFailCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_fail(repository, payload)


@router.post("/ticket-complete", response_model=CommandAckEnvelope)
def ticket_complete(request: Request, payload: TicketCompletedCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_completed(repository, payload)


@router.post("/scheduler-tick", response_model=CommandAckEnvelope)
def scheduler_tick(request: Request, payload: SchedulerTickCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_scheduler_tick(repository, payload)


@router.post("/board-approve", response_model=CommandAckEnvelope)
def board_approve(request: Request, payload: BoardApproveCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_board_approve(repository, payload)


@router.post("/board-reject", response_model=CommandAckEnvelope)
def board_reject(request: Request, payload: BoardRejectCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_board_reject(repository, payload)


@router.post("/modify-constraints", response_model=CommandAckEnvelope)
def modify_constraints(request: Request, payload: ModifyConstraintsCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_modify_constraints(repository, payload)
