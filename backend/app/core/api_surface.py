from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict

from fastapi import FastAPI
from fastapi.routing import APIRoute

API_SURFACE_GROUP_ORDER = (
    "commands",
    "projections",
    "artifacts",
    "artifact-uploads",
    "events",
    "worker-runtime",
    "worker-admin",
    "worker-admin-projections",
    "worker-runtime-projections",
)

_METHOD_ORDER = {
    "GET": 0,
    "POST": 1,
    "PUT": 2,
    "DELETE": 3,
    "PATCH": 4,
    "OPTIONS": 5,
    "HEAD": 6,
}


def collect_api_surface_groups(app: FastAPI) -> dict[str, list[str]]:
    grouped_routes: DefaultDict[str, list[str]] = defaultdict(list)
    sortable_routes: list[tuple[str, str, str]] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        group_name = classify_api_surface(route.path)
        method = _primary_method(route)
        sortable_routes.append((group_name, method, route.path))

    for group_name, method, path in sorted(
        sortable_routes,
        key=lambda item: (
            API_SURFACE_GROUP_ORDER.index(item[0]),
            _METHOD_ORDER.get(item[1], 99),
            item[2],
        ),
    ):
        grouped_routes[group_name].append(f"{method} {path}")

    return {group_name: grouped_routes[group_name] for group_name in API_SURFACE_GROUP_ORDER}


def classify_api_surface(path: str) -> str:
    if path.startswith("/api/v1/projections/worker-admin-"):
        return "worker-admin-projections"
    if path == "/api/v1/projections/worker-runtime":
        return "worker-runtime-projections"
    if path.startswith("/api/v1/commands/"):
        return "commands"
    if path.startswith("/api/v1/projections/"):
        return "projections"
    if path.startswith("/api/v1/artifacts/"):
        return "artifacts"
    if path.startswith("/api/v1/artifact-uploads/"):
        return "artifact-uploads"
    if path.startswith("/api/v1/events/"):
        return "events"
    if path.startswith("/api/v1/worker-runtime/"):
        return "worker-runtime"
    if path.startswith("/api/v1/worker-admin/"):
        return "worker-admin"
    raise ValueError(f"Unsupported API surface path: {path}")


def _primary_method(route: APIRoute) -> str:
    methods = sorted(route.methods or [], key=lambda method: _METHOD_ORDER.get(method, 99))
    for method in methods:
        if method not in {"HEAD", "OPTIONS"}:
            return method
    if methods:
        return methods[0]
    raise ValueError(f"Route '{route.path}' has no methods.")
