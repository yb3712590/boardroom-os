from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.streaming import stream_events
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/stream")
def event_stream(request: Request, after: str | None = None) -> StreamingResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    return StreamingResponse(
        stream_events(repository, after=after),
        media_type="text/event-stream",
    )
