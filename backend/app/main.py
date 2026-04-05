from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router_registry import include_registered_routers
from app.config import get_settings
from app.core.artifact_store import build_artifact_store
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.inprocess_scheduler import build_inprocess_scheduler
from app.core.runtime_provider_config import build_runtime_provider_store
from app.db.repository import ControlPlaneRepository


def create_app() -> FastAPI:
    settings = get_settings()
    artifact_store = build_artifact_store(settings)
    runtime_provider_store = build_runtime_provider_store()
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
        app.state.runtime_provider_store = runtime_provider_store
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
    include_registered_routers(app)
    return app


app = create_app()
