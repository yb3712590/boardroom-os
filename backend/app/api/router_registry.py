from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.routing import APIRouter

from app.api.artifacts import router as artifacts_router
from app.api.artifact_uploads import router as artifact_uploads_router
from app.api.commands import router as commands_router
from app.api.events import router as events_router
from app.api.projections import router as projections_router


@dataclass(frozen=True)
class RegisteredRouter:
    group_name: str
    is_frozen: bool
    router: APIRouter


ROUTER_REGISTRY: tuple[RegisteredRouter, ...] = (
    RegisteredRouter(group_name="commands", is_frozen=False, router=commands_router),
    RegisteredRouter(group_name="projections", is_frozen=False, router=projections_router),
    RegisteredRouter(group_name="artifacts", is_frozen=False, router=artifacts_router),
    RegisteredRouter(group_name="artifact-uploads", is_frozen=True, router=artifact_uploads_router),
    RegisteredRouter(group_name="events", is_frozen=False, router=events_router),
)

MAINLINE_ROUTER_REGISTRY: tuple[RegisteredRouter, ...] = tuple(
    entry for entry in ROUTER_REGISTRY if not entry.is_frozen
)
FROZEN_ROUTER_REGISTRY: tuple[RegisteredRouter, ...] = tuple(
    entry for entry in ROUTER_REGISTRY if entry.is_frozen
)

ALL_ROUTE_GROUPS: tuple[str, ...] = tuple(entry.group_name for entry in ROUTER_REGISTRY)
MAINLINE_ROUTE_GROUPS: tuple[str, ...] = tuple(entry.group_name for entry in MAINLINE_ROUTER_REGISTRY)
FROZEN_ROUTE_GROUPS: tuple[str, ...] = tuple(entry.group_name for entry in FROZEN_ROUTER_REGISTRY)


def include_registered_routers(app: FastAPI) -> None:
    for entry in ROUTER_REGISTRY:
        app.include_router(entry.router)


__all__ = [
    "ALL_ROUTE_GROUPS",
    "FROZEN_ROUTE_GROUPS",
    "FROZEN_ROUTER_REGISTRY",
    "MAINLINE_ROUTE_GROUPS",
    "MAINLINE_ROUTER_REGISTRY",
    "ROUTER_REGISTRY",
    "RegisteredRouter",
    "include_registered_routers",
]
