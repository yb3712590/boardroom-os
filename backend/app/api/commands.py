from __future__ import annotations

from fastapi import APIRouter, Request

from app.contracts.commands import (
    ArtifactCleanupCommand,
    ArtifactDeleteCommand,
    BoardApproveCommand,
    BoardRejectCommand,
    CommandAckEnvelope,
    EmployeeFreezeCommand,
    EmployeeHireRequestCommand,
    EmployeeReplaceRequestCommand,
    EmployeeRestoreCommand,
    IncidentResolveCommand,
    ModifyConstraintsCommand,
    ProjectInitCommand,
    RuntimeProviderUpsertCommand,
    SchedulerTickCommand,
    TicketCancelCommand,
    TicketCompletedCommand,
    TicketCreateCommand,
    TicketFailCommand,
    TicketHeartbeatCommand,
    TicketLeaseCommand,
    TicketResultSubmitCommand,
    TicketStartCommand,
)
from app.core.artifact_handlers import handle_artifact_cleanup, handle_artifact_delete
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.approval_handlers import (
    handle_board_approve,
    handle_board_reject,
    handle_modify_constraints,
)
from app.core.artifact_store import ArtifactStore
from app.core.command_handlers import handle_project_init
from app.core.runtime_provider_config import RuntimeProviderConfigStore, save_runtime_provider_command
from app.core.employee_handlers import (
    handle_employee_freeze,
    handle_employee_hire_request,
    handle_employee_replace_request,
    handle_employee_restore,
)
from app.core.ticket_handlers import (
    handle_incident_resolve,
    handle_ticket_cancel,
    handle_scheduler_tick,
    handle_ticket_completed,
    handle_ticket_create,
    handle_ticket_fail,
    handle_ticket_heartbeat,
    handle_ticket_lease,
    handle_ticket_result_submit,
    handle_ticket_start,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


@router.post("/project-init", response_model=CommandAckEnvelope)
def project_init(request: Request, payload: ProjectInitCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_project_init(repository, payload)


@router.post("/runtime-provider-upsert", response_model=CommandAckEnvelope)
def runtime_provider_upsert(
    request: Request,
    payload: RuntimeProviderUpsertCommand,
) -> CommandAckEnvelope:
    runtime_provider_store: RuntimeProviderConfigStore = request.app.state.runtime_provider_store
    return save_runtime_provider_command(runtime_provider_store, payload)


@router.post("/employee-hire-request", response_model=CommandAckEnvelope)
def employee_hire_request(request: Request, payload: EmployeeHireRequestCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_employee_hire_request(repository, payload)


@router.post("/employee-replace-request", response_model=CommandAckEnvelope)
def employee_replace_request(
    request: Request,
    payload: EmployeeReplaceRequestCommand,
) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_employee_replace_request(repository, payload)


@router.post("/employee-freeze", response_model=CommandAckEnvelope)
def employee_freeze(request: Request, payload: EmployeeFreezeCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_employee_freeze(repository, payload)


@router.post("/employee-restore", response_model=CommandAckEnvelope)
def employee_restore(request: Request, payload: EmployeeRestoreCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_employee_restore(repository, payload)


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


@router.post("/ticket-heartbeat", response_model=CommandAckEnvelope)
def ticket_heartbeat(request: Request, payload: TicketHeartbeatCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_heartbeat(repository, payload)


@router.post("/ticket-fail", response_model=CommandAckEnvelope)
def ticket_fail(request: Request, payload: TicketFailCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_fail(repository, payload)


@router.post("/ticket-complete", response_model=CommandAckEnvelope)
def ticket_complete(request: Request, payload: TicketCompletedCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    developer_inspector_store: DeveloperInspectorStore = request.app.state.developer_inspector_store
    return handle_ticket_completed(repository, payload, developer_inspector_store)


@router.post("/ticket-result-submit", response_model=CommandAckEnvelope)
def ticket_result_submit(request: Request, payload: TicketResultSubmitCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    developer_inspector_store: DeveloperInspectorStore = request.app.state.developer_inspector_store
    return handle_ticket_result_submit(repository, payload, developer_inspector_store, artifact_store)


@router.post("/scheduler-tick", response_model=CommandAckEnvelope)
def scheduler_tick(request: Request, payload: SchedulerTickCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_scheduler_tick(repository, payload)


@router.post("/incident-resolve", response_model=CommandAckEnvelope)
def incident_resolve(request: Request, payload: IncidentResolveCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_incident_resolve(repository, payload)


@router.post("/artifact-delete", response_model=CommandAckEnvelope)
def artifact_delete(request: Request, payload: ArtifactDeleteCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return handle_artifact_delete(repository, payload, artifact_store)


@router.post("/artifact-cleanup", response_model=CommandAckEnvelope)
def artifact_cleanup(request: Request, payload: ArtifactCleanupCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return handle_artifact_cleanup(repository, payload, artifact_store)


@router.post("/ticket-cancel", response_model=CommandAckEnvelope)
def ticket_cancel(request: Request, payload: TicketCancelCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_cancel(repository, payload)


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
