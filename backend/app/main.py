from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.commands import router as commands_router
from app.api.events import router as events_router
from app.api.projections import router as projections_router
from app.config import get_settings
from app.core.developer_inspector import DeveloperInspectorStore
from app.db.repository import ControlPlaneRepository


def create_app() -> FastAPI:
    settings = get_settings()
    repository = ControlPlaneRepository(
        db_path=settings.db_path,
        busy_timeout_ms=settings.busy_timeout_ms,
        recent_event_limit=settings.recent_event_limit,
    )
    developer_inspector_store = DeveloperInspectorStore(settings.developer_inspector_root)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        app.state.repository = repository
        app.state.developer_inspector_store = developer_inspector_store
        yield

    app = FastAPI(
        title="Boardroom OS Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(commands_router)
    app.include_router(projections_router)
    app.include_router(events_router)
    return app


app = create_app()
