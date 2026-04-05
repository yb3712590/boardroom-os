from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.contracts.projections import WorkerRuntimeProjectionEnvelope
from app.core.projections import build_worker_runtime_projection
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/projections", tags=["projections"])


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
