from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app.contracts.common import StrictModel
from app.contracts.commands import (
    ArtifactCleanupCommand,
    ArtifactDeleteCommand,
    BoardAdvisoryAppendTurnCommand,
    BoardAdvisoryApplyPatchCommand,
    BoardApproveCommand,
    BoardRejectCommand,
    BoardAdvisoryRequestAnalysisCommand,
    CommandAckEnvelope,
    EmployeeFreezeCommand,
    EmployeeHireRequestCommand,
    EmployeeReplaceRequestCommand,
    EmployeeRestoreCommand,
    IncidentResolveCommand,
    MeetingRequestCommand,
    ModifyConstraintsCommand,
    ProjectInitCommand,
    RuntimeProviderConfigInput,
    RuntimeProviderUpsertCommand,
    SchedulerTickCommand,
    TicketArtifactImportUploadCommand,
    TicketCancelCommand,
    TicketCompletedCommand,
    TicketBoardReviewRequest,
    TicketCreateCommand,
    TicketFailCommand,
    TicketHeartbeatCommand,
    TicketLeaseCommand,
    TicketResultSubmitCommand,
    TicketStartCommand,
)
from app.core.artifact_handlers import (
    handle_artifact_cleanup,
    handle_artifact_delete,
    handle_ticket_artifact_import_upload,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.approval_handlers import (
    handle_board_advisory_append_turn,
    handle_board_advisory_apply_patch,
    handle_board_advisory_request_analysis,
    handle_board_approve,
    handle_board_reject,
    handle_modify_constraints,
)
from app.core.artifact_store import ArtifactStore
from app.core.command_handlers import handle_project_init
from app.core.provider_openai_compat import (
    OpenAICompatProviderConfig,
    OpenAICompatProviderType,
    list_openai_compat_models,
    probe_openai_compat_connectivity,
)
from app.core.runtime_provider_config import (
    RuntimeProviderConfigStore,
    find_provider_entry,
    resolve_runtime_provider_config,
    save_runtime_provider_command,
)
from app.core.employee_handlers import (
    handle_employee_freeze,
    handle_employee_hire_request,
    handle_employee_replace_request,
    handle_employee_restore,
)
from app.core.meeting_handlers import handle_meeting_request
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


class ProjectInitRequest(ProjectInitCommand):
    tenant_id: str | None = Field(default=None, min_length=1)
    workspace_id: str | None = Field(default=None, min_length=1)

    def to_command(self) -> ProjectInitCommand:
        return ProjectInitCommand.model_validate(
            self.model_dump(mode="json", exclude={"tenant_id", "workspace_id"})
        )


class TicketCreateRequest(TicketCreateCommand):
    tenant_id: str | None = Field(default=None, min_length=1)
    workspace_id: str | None = Field(default=None, min_length=1)

    def to_command(self) -> TicketCreateCommand:
        return TicketCreateCommand.model_validate(
            self.model_dump(mode="json", exclude={"tenant_id", "workspace_id"})
        )


ProjectInitRequest.model_rebuild()
TicketCreateRequest.model_rebuild()


class RuntimeProviderModelsRefreshRequest(StrictModel):
    provider_id: str = Field(min_length=1)


@router.post("/project-init", response_model=CommandAckEnvelope)
def project_init(request: Request, payload: ProjectInitRequest) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_project_init(repository, payload.to_command())


@router.post("/runtime-provider-upsert", response_model=CommandAckEnvelope)
def runtime_provider_upsert(
    request: Request,
    payload: RuntimeProviderUpsertCommand,
) -> CommandAckEnvelope:
    runtime_provider_store: RuntimeProviderConfigStore = request.app.state.runtime_provider_store
    return save_runtime_provider_command(runtime_provider_store, payload)


def _build_openai_connectivity_config(payload: RuntimeProviderConfigInput | dict) -> OpenAICompatProviderConfig:
    provider_type = payload.type if isinstance(payload, RuntimeProviderConfigInput) else payload["type"]
    timeout_sec = (
        payload.request_total_timeout_sec
        if isinstance(payload, RuntimeProviderConfigInput)
        else payload.get("request_total_timeout_sec")
    ) or (payload.timeout_sec if isinstance(payload, RuntimeProviderConfigInput) else payload.get("timeout_sec")) or 120.0
    return OpenAICompatProviderConfig(
        base_url=payload.base_url if isinstance(payload, RuntimeProviderConfigInput) else payload["base_url"],
        api_key=payload.api_key if isinstance(payload, RuntimeProviderConfigInput) else payload["api_key"],
        model=(
            payload.preferred_model if isinstance(payload, RuntimeProviderConfigInput) else payload["preferred_model"]
        )
        or "gpt-5.3-codex",
        timeout_sec=float(timeout_sec),
        connect_timeout_sec=float(
            (
                payload.connect_timeout_sec
                if isinstance(payload, RuntimeProviderConfigInput)
                else payload.get("connect_timeout_sec")
            )
            or 10.0
        ),
        write_timeout_sec=float(
            (
                payload.write_timeout_sec
                if isinstance(payload, RuntimeProviderConfigInput)
                else payload.get("write_timeout_sec")
            )
            or 20.0
        ),
        first_token_timeout_sec=float(
            (
                payload.first_token_timeout_sec
                if isinstance(payload, RuntimeProviderConfigInput)
                else payload.get("first_token_timeout_sec")
            )
            or 45.0
        ),
        stream_idle_timeout_sec=float(
            (
                payload.stream_idle_timeout_sec
                if isinstance(payload, RuntimeProviderConfigInput)
                else payload.get("stream_idle_timeout_sec")
            )
            or 20.0
        ),
        request_total_timeout_sec=float(timeout_sec),
        reasoning_effort=(
            payload.reasoning_effort
            if isinstance(payload, RuntimeProviderConfigInput)
            else payload.get("reasoning_effort") or "high"
        ),
        provider_type=OpenAICompatProviderType(provider_type.value if hasattr(provider_type, "value") else provider_type),
    )


@router.post("/runtime-provider-connectivity-test")
def runtime_provider_connectivity_test(
    payload: RuntimeProviderConfigInput,
) -> dict[str, object]:
    result = probe_openai_compat_connectivity(_build_openai_connectivity_config(payload))
    resolved_alias = payload.alias or payload.base_url.split("//")[-1].split(".")[-2]
    return {
        "ok": result.ok,
        "response_id": result.response_id,
        "resolved_provider": {
            "provider_id": payload.provider_id,
            "type": result.provider_type.value,
            "base_url": payload.base_url,
            "alias": resolved_alias,
            "preferred_model": payload.preferred_model,
            "max_context_window": payload.max_context_window or 1000000,
            "reasoning_effort": payload.reasoning_effort or "high",
            "enabled": payload.enabled,
        },
    }


@router.post("/runtime-provider-models-refresh")
def runtime_provider_models_refresh(
    request: Request,
    payload: RuntimeProviderModelsRefreshRequest,
) -> dict[str, object]:
    runtime_provider_store: RuntimeProviderConfigStore = request.app.state.runtime_provider_store
    config = resolve_runtime_provider_config(runtime_provider_store)
    provider = find_provider_entry(config, payload.provider_id)
    if provider is None:
        return {"provider_id": payload.provider_id, "models": []}
    models = list_openai_compat_models(
        OpenAICompatProviderConfig(
            base_url=str(provider.base_url or ""),
            api_key=str(provider.api_key or ""),
            model=str(provider.preferred_model or provider.model or "gpt-5.3-codex"),
            timeout_sec=float(provider.timeout_sec),
            connect_timeout_sec=float(provider.connect_timeout_sec or provider.timeout_sec or 0),
            write_timeout_sec=float(provider.write_timeout_sec or provider.timeout_sec or 0),
            first_token_timeout_sec=float(provider.first_token_timeout_sec or provider.timeout_sec or 0),
            stream_idle_timeout_sec=float(provider.stream_idle_timeout_sec or provider.timeout_sec or 0),
            request_total_timeout_sec=float(provider.request_total_timeout_sec or provider.timeout_sec or 0),
            provider_type=OpenAICompatProviderType(provider.type.value),
        )
    )
    return {"provider_id": payload.provider_id, "models": models}


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


@router.post("/meeting-request", response_model=CommandAckEnvelope)
def meeting_request(request: Request, payload: MeetingRequestCommand) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_meeting_request(repository, payload)


@router.post("/ticket-create", response_model=CommandAckEnvelope)
def ticket_create(request: Request, payload: TicketCreateRequest) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_ticket_create(repository, payload.to_command())


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


@router.post("/ticket-artifact-import-upload", response_model=CommandAckEnvelope)
def ticket_artifact_import_upload(
    request: Request,
    payload: TicketArtifactImportUploadCommand,
) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return handle_ticket_artifact_import_upload(repository, payload, artifact_store)


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


@router.post("/board-advisory-append-turn", response_model=CommandAckEnvelope)
def board_advisory_append_turn(
    request: Request,
    payload: BoardAdvisoryAppendTurnCommand,
) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_board_advisory_append_turn(repository, payload)


@router.post("/board-advisory-request-analysis", response_model=CommandAckEnvelope)
def board_advisory_request_analysis(
    request: Request,
    payload: BoardAdvisoryRequestAnalysisCommand,
) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_board_advisory_request_analysis(repository, payload)


@router.post("/board-advisory-apply-patch", response_model=CommandAckEnvelope)
def board_advisory_apply_patch(
    request: Request,
    payload: BoardAdvisoryApplyPatchCommand,
) -> CommandAckEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return handle_board_advisory_apply_patch(repository, payload)
