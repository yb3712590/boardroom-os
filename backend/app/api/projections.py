from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.contracts.projections import DashboardProjectionEnvelope, InboxProjectionEnvelope
from app.core.projections import build_dashboard_projection, build_inbox_projection
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


@router.get("/review-room/{review_pack_id}")
def get_review_room(request: Request, review_pack_id: str):
    repository: ControlPlaneRepository = request.app.state.repository
    repository.initialize()
    raise HTTPException(
        status_code=404,
        detail=(
            "Review room projection route is reserved, but no review packs are "
            f"materialized yet for '{review_pack_id}'."
        ),
    )
