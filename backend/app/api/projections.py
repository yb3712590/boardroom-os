from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.worker_admin_auth import (
    WorkerAdminOperatorContext,
    get_worker_admin_operator_context,
    require_worker_admin_read_scope,
)
from app.contracts.projections import (
    ArtifactCleanupCandidatesProjectionEnvelope,
    DashboardProjectionEnvelope,
    IncidentDetailProjectionEnvelope,
    InboxProjectionEnvelope,
    ReviewRoomDeveloperInspectorProjectionEnvelope,
    ReviewRoomProjectionEnvelope,
    WorkerAdminAuthRejectionProjectionEnvelope,
    TicketArtifactsProjectionEnvelope,
    WorkerAdminAuditProjectionEnvelope,
    WorkerRuntimeProjectionEnvelope,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.projections import (
    build_artifact_cleanup_candidates_projection,
    build_dashboard_projection,
    build_incident_detail_projection,
    build_inbox_projection,
    build_worker_admin_auth_rejection_projection,
    build_worker_admin_audit_projection,
    build_review_room_developer_inspector_projection,
    build_review_room_projection,
    build_ticket_artifacts_projection,
    build_worker_runtime_projection,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/projections", tags=["projections"])


@router.get("/dashboard", response_model=DashboardProjectionEnvelope)
def get_dashboard(request: Request) -> DashboardProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return build_dashboard_projection(repository)


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


@router.get("/worker-admin-audit", response_model=WorkerAdminAuditProjectionEnvelope)
def get_worker_admin_audit_projection(
    request: Request,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    worker_id: str | None = None,
    operator_id: str | None = None,
    action_type: str | None = None,
    dry_run: bool | None = None,
    limit: int = Query(default=50, ge=1),
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminAuditProjectionEnvelope:
    if (tenant_id is None) != (workspace_id is None):
        raise HTTPException(
            status_code=400,
            detail="tenant_id and workspace_id must be provided together.",
        )
    require_worker_admin_read_scope(
        operator,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    repository: ControlPlaneRepository = request.app.state.repository
    return build_worker_admin_audit_projection(
        repository,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        worker_id=worker_id,
        operator_id=operator_id,
        action_type=action_type,
        dry_run=dry_run,
        limit=limit,
    )


@router.get(
    "/worker-admin-auth-rejections",
    response_model=WorkerAdminAuthRejectionProjectionEnvelope,
)
def get_worker_admin_auth_rejection_projection(
    request: Request,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    operator_id: str | None = None,
    operator_role: str | None = None,
    token_id: str | None = None,
    route_path: str | None = None,
    limit: int = Query(default=50, ge=1),
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminAuthRejectionProjectionEnvelope:
    if (tenant_id is None) != (workspace_id is None):
        raise HTTPException(
            status_code=400,
            detail="tenant_id and workspace_id must be provided together.",
        )
    require_worker_admin_read_scope(
        operator,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    repository: ControlPlaneRepository = request.app.state.repository
    return build_worker_admin_auth_rejection_projection(
        repository,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        operator_id=operator_id,
        operator_role=operator_role,
        token_id=token_id,
        route_path=route_path,
        limit=limit,
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
