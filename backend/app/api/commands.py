from __future__ import annotations

from fastapi import APIRouter, Request

from app.contracts.commands import CommandAckEnvelope, ProjectInitCommand
from app.core.command_handlers import handle_project_init
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


@router.post("/project-init", response_model=CommandAckEnvelope)
def project_init(request: Request, payload: ProjectInitCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_project_init(repository, payload)
