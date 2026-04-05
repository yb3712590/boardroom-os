from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.contracts.projections import (
    ArtifactCleanupCandidatesProjectionEnvelope,
    CEOShadowProjectionEnvelope,
    DashboardProjectionEnvelope,
    DependencyInspectorProjectionEnvelope,
    IncidentDetailProjectionEnvelope,
    InboxProjectionEnvelope,
    MeetingDetailProjectionEnvelope,
    RuntimeProviderProjectionEnvelope,
    ReviewRoomDeveloperInspectorProjectionEnvelope,
    ReviewRoomProjectionEnvelope,
    TicketArtifactsProjectionEnvelope,
    WorkerRuntimeProjectionEnvelope,
    WorkforceProjectionEnvelope,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.projections import (
    build_artifact_cleanup_candidates_projection,
    build_ceo_shadow_projection,
    build_dashboard_projection,
    build_dependency_inspector_projection,
    build_incident_detail_projection,
    build_inbox_projection,
    build_meeting_projection,
    build_runtime_provider_projection,
    build_review_room_developer_inspector_projection,
    build_review_room_projection,
    build_ticket_artifacts_projection,
    build_worker_runtime_projection,
    build_workforce_projection,
)
from app.db.repository import ControlPlaneRepository
from app.core.runtime_provider_config import RuntimeProviderConfigStore

router = APIRouter(prefix="/api/v1/projections", tags=["projections"])


@router.get("/dashboard", response_model=DashboardProjectionEnvelope)
def get_dashboard(request: Request) -> DashboardProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    runtime_provider_store: RuntimeProviderConfigStore = request.app.state.runtime_provider_store
    return build_dashboard_projection(repository, runtime_provider_store)


@router.get("/runtime-provider", response_model=RuntimeProviderProjectionEnvelope)
def get_runtime_provider(request: Request) -> RuntimeProviderProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    runtime_provider_store: RuntimeProviderConfigStore = request.app.state.runtime_provider_store
    return build_runtime_provider_projection(repository, runtime_provider_store)


@router.get(
    "/workflows/{workflow_id}/dependency-inspector",
    response_model=DependencyInspectorProjectionEnvelope,
)
def get_dependency_inspector(
    request: Request,
    workflow_id: str,
) -> DependencyInspectorProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    projection = build_dependency_inspector_projection(repository, workflow_id)
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_id}' was not found.",
        )
    return projection


@router.get(
    "/workflows/{workflow_id}/ceo-shadow",
    response_model=CEOShadowProjectionEnvelope,
)
def get_ceo_shadow_projection(
    request: Request,
    workflow_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> CEOShadowProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    projection = build_ceo_shadow_projection(repository, workflow_id, limit=limit)
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_id}' was not found.",
        )
    return projection


@router.get(
    "/artifact-cleanup-candidates",
    response_model=ArtifactCleanupCandidatesProjectionEnvelope,
)
def get_artifact_cleanup_candidates(
    request: Request,
    ticket_id: str | None = None,
    retention_class: str | None = None,
    limit: int = Query(default=50, ge=1),
) -> ArtifactCleanupCandidatesProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return build_artifact_cleanup_candidates_projection(
        repository,
        ticket_id=ticket_id,
        retention_class=retention_class,
        limit=limit,
    )


@router.get("/inbox", response_model=InboxProjectionEnvelope)
def get_inbox(request: Request) -> InboxProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return build_inbox_projection(repository)


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailProjectionEnvelope)
def get_meeting_detail_projection(
    request: Request,
    meeting_id: str,
) -> MeetingDetailProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    projection = build_meeting_projection(repository, meeting_id)
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Meeting '{meeting_id}' was not found.",
        )
    return projection


@router.get("/workforce", response_model=WorkforceProjectionEnvelope)
def get_workforce(request: Request) -> WorkforceProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return build_workforce_projection(repository)


@router.get("/worker-runtime", response_model=WorkerRuntimeProjectionEnvelope)
def get_worker_runtime_projection(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
    rejection_limit: int = 20,
    grant_limit: int = 50,
) -> WorkerRuntimeProjectionEnvelope:
    if (tenant_id is None) != (workspace_id is None):
        raise HTTPException(
            status_code=400,
            detail="tenant_id and workspace_id must be provided together.",
        )
    repository: ControlPlaneRepository = request.app.state.repository
    return build_worker_runtime_projection(
        repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=active_only,
        rejection_limit=rejection_limit,
        grant_limit=grant_limit,
    )


@router.get("/tickets/{ticket_id}/artifacts", response_model=TicketArtifactsProjectionEnvelope)
def get_ticket_artifacts(request: Request, ticket_id: str) -> TicketArtifactsProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    projection = build_ticket_artifacts_projection(repository, ticket_id)
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticket '{ticket_id}' was not found.",
        )
    return projection


@router.get("/incidents/{incident_id}", response_model=IncidentDetailProjectionEnvelope)
def get_incident_detail(request: Request, incident_id: str) -> IncidentDetailProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    projection = build_incident_detail_projection(repository, incident_id)
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Incident '{incident_id}' was not found.",
        )
    return projection


@router.get("/review-room/{review_pack_id}", response_model=ReviewRoomProjectionEnvelope)
def get_review_room(request: Request, review_pack_id: str) -> ReviewRoomProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    projection = build_review_room_projection(repository, review_pack_id)
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Review pack '{review_pack_id}' was not found.",
        )
    return projection


@router.get(
    "/review-room/{review_pack_id}/developer-inspector",
    response_model=ReviewRoomDeveloperInspectorProjectionEnvelope,
)
def get_review_room_developer_inspector(
    request: Request,
    review_pack_id: str,
) -> ReviewRoomDeveloperInspectorProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    developer_inspector_store: DeveloperInspectorStore = request.app.state.developer_inspector_store
    projection = build_review_room_developer_inspector_projection(
        repository,
        review_pack_id,
        developer_inspector_store,
    )
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Review pack '{review_pack_id}' was not found.",
        )
    return projection
