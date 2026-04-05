from __future__ import annotations

from typing import Any

from app.core.constants import DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID


def default_workflow_scope() -> tuple[str, str]:
    return DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID


def resolve_workflow_scope(workflow: dict[str, Any] | None) -> tuple[str, str]:
    if workflow is None:
        return default_workflow_scope()
    return (
        str(workflow.get("tenant_id") or DEFAULT_TENANT_ID),
        str(workflow.get("workspace_id") or DEFAULT_WORKSPACE_ID),
    )


def with_workflow_scope(payload: dict[str, Any], workflow: dict[str, Any] | None) -> dict[str, Any]:
    tenant_id, workspace_id = resolve_workflow_scope(workflow)
    return {
        **payload,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
    }
