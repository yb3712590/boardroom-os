from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.contracts.projections import (
    DashboardProjectionEnvelope,
    InboxProjectionEnvelope,
    ReviewRoomDeveloperInspectorProjectionEnvelope,
    ReviewRoomProjectionEnvelope,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.projections import (
    build_dashboard_projection,
    build_inbox_projection,
    build_review_room_developer_inspector_projection,
    build_review_room_projection,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/projections", tags=["projections"])


@router.get("/dashboard", response_model=DashboardProjectionEnvelope)
def get_dashboard(request: Request) -> DashboardProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return build_dashboard_projection(repository)


@router.get("/inbox", response_model=InboxProjectionEnvelope)
def get_inbox(request: Request) -> InboxProjectionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    return build_inbox_projection(repository)


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
