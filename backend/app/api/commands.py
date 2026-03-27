from __future__ import annotations

from fastapi import APIRouter, Request

from app.contracts.commands import (
    BoardApproveCommand,
    BoardRejectCommand,
    CommandAckEnvelope,
    ModifyConstraintsCommand,
    ProjectInitCommand,
)
from app.core.approval_handlers import (
    handle_board_approve,
    handle_board_reject,
    handle_modify_constraints,
)
from app.core.command_handlers import handle_project_init
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


@router.post("/project-init", response_model=CommandAckEnvelope)
def project_init(request: Request, payload: ProjectInitCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_project_init(repository, payload)


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
