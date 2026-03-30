from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.artifacts import router as artifacts_router
from app.api.commands import router as commands_router
from app.api.events import router as events_router
from app.api.projections import router as projections_router
from app.api.worker_admin import router as worker_admin_router
from app.api.worker_runtime import router as worker_runtime_router
from app.config import get_settings
from app.core.artifact_store import ArtifactStore
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.inprocess_scheduler import build_inprocess_scheduler
from app.db.repository import ControlPlaneRepository


def create_app() -> FastAPI:
    settings = get_settings()
    artifact_store = ArtifactStore(settings.artifact_store_root)
    repository = ControlPlaneRepository(
        db_path=settings.db_path,
        busy_timeout_ms=settings.busy_timeout_ms,
        recent_event_limit=settings.recent_event_limit,
        artifact_store=artifact_store,
    )
    developer_inspector_store = DeveloperInspectorStore(settings.developer_inspector_root)
    inprocess_scheduler = (
        build_inprocess_scheduler(repository, settings)
        if settings.enable_inprocess_scheduler
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        app.state.repository = repository
        app.state.artifact_store = artifact_store
        app.state.developer_inspector_store = developer_inspector_store
        app.state.inprocess_scheduler = inprocess_scheduler
        if inprocess_scheduler is not None:
            inprocess_scheduler.start()
        try:
            yield
        finally:
            if inprocess_scheduler is not None:
                inprocess_scheduler.stop()

    app = FastAPI(
        title="Boardroom OS Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(artifacts_router)
    app.include_router(commands_router)
    app.include_router(projections_router)
    app.include_router(events_router)
    app.include_router(worker_admin_router)
    app.include_router(worker_runtime_router)
    return app


app = create_app()
