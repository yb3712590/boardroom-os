from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request

from app.config import get_settings
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.output_schemas import get_output_schema_body
from app.db.repository import ControlPlaneRepository

ACTIVE_WORKER_TICKET_STATUSES = {"LEASED", "EXECUTING", "CANCEL_REQUESTED"}


@dataclass(frozen=True)
class WorkerPrincipal:
    worker_id: str


def authenticate_worker(
    request: Request,
    *,
    worker_key: str | None,
    worker_id: str | None,
) -> WorkerPrincipal:
    settings = get_settings()
    if not settings.worker_shared_secret:
        raise HTTPException(
            status_code=503,
            detail="Worker runtime shared secret is not configured.",
        )
    if not worker_key or not worker_id:
        raise HTTPException(
            status_code=401,
            detail="Worker runtime authentication headers are required.",
        )
    if worker_key != settings.worker_shared_secret:
        raise HTTPException(
            status_code=401,
            detail="Worker runtime shared secret is invalid.",
        )

    repository: ControlPlaneRepository = request.app.state.repository
    employee = repository.get_employee_projection(worker_id)
    if employee is None:
        raise HTTPException(
            status_code=403,
            detail=f"Worker '{worker_id}' is not registered.",
        )

    return WorkerPrincipal(worker_id=worker_id)


def build_worker_artifact_urls(request: Request, artifact_ref: str) -> dict[str, str]:
    encoded_ref = quote(artifact_ref, safe="")
    base_url = str(request.base_url).rstrip("/")
    return {
        "content_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/content"
            f"?artifact_ref={encoded_ref}&disposition=inline"
        ),
        "download_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/content"
            f"?artifact_ref={encoded_ref}&disposition=attachment"
        ),
        "preview_url": f"{base_url}/api/v1/worker-runtime/artifacts/preview?artifact_ref={encoded_ref}",
    }


def build_worker_execution_package_url(request: Request, ticket_id: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/v1/worker-runtime/tickets/{ticket_id}/execution-package"


def build_worker_command_endpoints(request: Request) -> dict[str, str]:
    base_url = str(request.base_url).rstrip("/")
    return {
        "ticket_start_url": f"{base_url}/api/v1/worker-runtime/commands/ticket-start",
        "ticket_heartbeat_url": f"{base_url}/api/v1/worker-runtime/commands/ticket-heartbeat",
        "ticket_result_submit_url": f"{base_url}/api/v1/worker-runtime/commands/ticket-result-submit",
    }


def list_worker_assignments(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
) -> list[dict[str, Any]]:
    tickets = repository.list_ticket_projections_by_statuses_readonly(
        list(ACTIVE_WORKER_TICKET_STATUSES)
    )
    return [
        ticket
        for ticket in tickets
        if ticket.get("lease_owner") == worker_id and ticket["status"] in ACTIVE_WORKER_TICKET_STATUSES
    ]


def require_worker_owned_ticket(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str,
    worker_id: str,
) -> dict[str, Any]:
    ticket = repository.get_current_ticket_projection(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticket '{ticket_id}' was not found.",
        )
    if ticket.get("lease_owner") != worker_id or ticket["status"] not in ACTIVE_WORKER_TICKET_STATUSES:
        raise HTTPException(
            status_code=403,
            detail=f"Worker '{worker_id}' does not currently own ticket '{ticket_id}'.",
        )
    return ticket


def _worker_ticket_scope(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
) -> tuple[set[str], set[str]]:
    repository.initialize()
    with repository.connection() as connection:
        ticket_rows = repository.list_ticket_projections_by_statuses(
            connection,
            list(ACTIVE_WORKER_TICKET_STATUSES),
        )
        owned_tickets = {
            ticket["ticket_id"]: repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"]) or {}
            for ticket in ticket_rows
            if ticket.get("lease_owner") == worker_id
        }

    owned_ticket_ids = set(owned_tickets.keys())
    allowed_input_refs = {
        str(artifact_ref)
        for created_spec in owned_tickets.values()
        for artifact_ref in list(created_spec.get("input_artifact_refs") or [])
    }
    return owned_ticket_ids, allowed_input_refs


def require_worker_access_to_artifact(
    repository: ControlPlaneRepository,
    *,
    artifact_ref: str,
    worker_id: str,
) -> dict[str, Any] | None:
    owned_ticket_ids, allowed_input_refs = _worker_ticket_scope(repository, worker_id=worker_id)
    artifact = repository.get_artifact_by_ref(artifact_ref)

    if artifact_ref in allowed_input_refs:
        return artifact
    if artifact is not None and artifact.get("ticket_id") in owned_ticket_ids:
        return artifact

    raise HTTPException(
        status_code=403,
        detail=f"Worker '{worker_id}' cannot access artifact '{artifact_ref}'.",
    )


def ensure_worker_execution_handoff(
    repository: ControlPlaneRepository,
    *,
    ticket: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket(ticket["ticket_id"])
    latest_manifest = repository.get_latest_compile_manifest_by_ticket(ticket["ticket_id"])
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(ticket["ticket_id"])

    compile_request_id = latest_execution_package["compile_request_id"] if latest_execution_package else None
    if (
        latest_bundle is None
        or latest_manifest is None
        or latest_execution_package is None
        or latest_bundle["compile_request_id"] != compile_request_id
        or latest_manifest["compile_request_id"] != compile_request_id
    ):
        compile_and_persist_execution_artifacts(repository, ticket)
        latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket(ticket["ticket_id"])
        latest_manifest = repository.get_latest_compile_manifest_by_ticket(ticket["ticket_id"])
        latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(ticket["ticket_id"])

    if latest_bundle is None or latest_manifest is None or latest_execution_package is None:
        raise RuntimeError("Compiled execution handoff could not be materialized for worker delivery.")
    return latest_bundle, latest_manifest, latest_execution_package


def build_worker_execution_package_payload(
    request: Request,
    *,
    latest_execution_package: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(latest_execution_package["payload"])
    for block in payload.get("atomic_context_bundle", {}).get("context_blocks", []):
        content_payload = block.get("content_payload") or {}
        artifact_access = content_payload.get("artifact_access")
        artifact_ref = None
        if isinstance(artifact_access, dict):
            artifact_ref = artifact_access.get("artifact_ref")
        if artifact_ref is None:
            artifact_ref = content_payload.get("artifact_ref") or content_payload.get("source_ref")
        if not isinstance(artifact_ref, str) or not artifact_ref:
            continue
        worker_urls = build_worker_artifact_urls(request, artifact_ref)
        if isinstance(artifact_access, dict):
            artifact_access.update(worker_urls)
        content_payload.update(worker_urls)
    return payload


def build_worker_artifact_metadata(
    request: Request,
    *,
    artifact: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    rewritten = dict(metadata)
    rewritten.update(build_worker_artifact_urls(request, str(artifact["artifact_ref"])))
    return rewritten


def build_output_schema_body_for_execution_package(
    execution_package_payload: dict[str, Any],
) -> dict[str, Any]:
    execution = execution_package_payload.get("execution") or {}
    return get_output_schema_body(
        str(execution.get("output_schema_ref") or ""),
        int(execution.get("output_schema_version") or 0),
    )
