from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, Request

from app.config import get_settings
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.output_schemas import get_output_schema_body
from app.core.time import now_local
from app.core.worker_delivery_tokens import (
    WorkerCommandName,
    WorkerDeliveryScope,
    issue_worker_delivery_token,
    validate_worker_delivery_token,
)
from app.db.repository import ControlPlaneRepository

ACTIVE_WORKER_TICKET_STATUSES = {"LEASED", "EXECUTING", "CANCEL_REQUESTED"}


@dataclass(frozen=True)
class WorkerPrincipal:
    worker_id: str


def _resolve_worker_delivery_signing_secret() -> str:
    settings = get_settings()
    signing_secret = settings.worker_delivery_signing_secret or settings.worker_shared_secret
    if not signing_secret:
        raise HTTPException(
            status_code=503,
            detail="Worker delivery signing secret is not configured.",
        )
    return signing_secret


def _resolve_worker_public_base_url(request: Request) -> str:
    settings = get_settings()
    return settings.public_base_url or str(request.base_url).rstrip("/")


def _issue_worker_delivery_token(
    *,
    scope: WorkerDeliveryScope,
    worker_id: str,
    ticket_id: str,
    issued_at: datetime,
    artifact_ref: str | None = None,
    command_name: WorkerCommandName | None = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    return issue_worker_delivery_token(
        signing_secret=_resolve_worker_delivery_signing_secret(),
        scope=scope,
        worker_id=worker_id,
        ticket_id=ticket_id,
        issued_at=issued_at,
        ttl_sec=settings.worker_delivery_token_ttl_sec,
        artifact_ref=artifact_ref,
        command_name=command_name,
    )


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


def authenticate_worker_request(
    request: Request,
    *,
    access_token: str | None,
    worker_key: str | None,
    worker_id: str | None,
    scope: WorkerDeliveryScope,
    ticket_id: str,
    artifact_ref: str | None = None,
    command_name: WorkerCommandName | None = None,
) -> WorkerPrincipal:
    if access_token:
        claims = validate_worker_delivery_token(
            access_token,
            signing_secret=_resolve_worker_delivery_signing_secret(),
            expected_scope=scope,
            expected_ticket_id=ticket_id,
            expected_artifact_ref=artifact_ref,
            expected_command_name=command_name,
            at=now_local(),
        )
        repository: ControlPlaneRepository = request.app.state.repository
        employee = repository.get_employee_projection(claims.worker_id)
        if employee is None:
            raise HTTPException(
                status_code=403,
                detail=f"Worker '{claims.worker_id}' is not registered.",
            )
        return WorkerPrincipal(worker_id=claims.worker_id)

    return authenticate_worker(
        request,
        worker_key=worker_key,
        worker_id=worker_id,
    )


def build_worker_artifact_urls(
    request: Request,
    *,
    worker_id: str,
    ticket_id: str,
    artifact_ref: str,
    issued_at: datetime,
) -> tuple[dict[str, str], datetime]:
    base_url = _resolve_worker_public_base_url(request)
    token, expires_at = _issue_worker_delivery_token(
        scope="artifact_read",
        worker_id=worker_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        issued_at=issued_at,
    )
    return {
        "content_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/content?"
            f"{urlencode({'artifact_ref': artifact_ref, 'ticket_id': ticket_id, 'disposition': 'inline', 'access_token': token})}"
        ),
        "download_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/content?"
            f"{urlencode({'artifact_ref': artifact_ref, 'ticket_id': ticket_id, 'disposition': 'attachment', 'access_token': token})}"
        ),
        "preview_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/preview?"
            f"{urlencode({'artifact_ref': artifact_ref, 'ticket_id': ticket_id, 'access_token': token})}"
        ),
    }, expires_at


def build_worker_execution_package_url(
    request: Request,
    *,
    worker_id: str,
    ticket_id: str,
    issued_at: datetime,
) -> tuple[str, datetime]:
    base_url = _resolve_worker_public_base_url(request)
    token, expires_at = _issue_worker_delivery_token(
        scope="execution_package",
        worker_id=worker_id,
        ticket_id=ticket_id,
        issued_at=issued_at,
    )
    return (
        f"{base_url}/api/v1/worker-runtime/tickets/{ticket_id}/execution-package?"
        f"{urlencode({'access_token': token})}",
        expires_at,
    )


def _build_worker_command_url(
    request: Request,
    *,
    worker_id: str,
    ticket_id: str,
    command_name: WorkerCommandName,
    issued_at: datetime,
) -> tuple[str, datetime]:
    base_url = _resolve_worker_public_base_url(request)
    token, expires_at = _issue_worker_delivery_token(
        scope="command",
        worker_id=worker_id,
        ticket_id=ticket_id,
        command_name=command_name,
        issued_at=issued_at,
    )
    return (
        f"{base_url}/api/v1/worker-runtime/commands/{command_name}?"
        f"{urlencode({'access_token': token})}",
        expires_at,
    )


def build_worker_command_endpoints(
    request: Request,
    *,
    worker_id: str,
    ticket_id: str,
    issued_at: datetime,
) -> tuple[dict[str, str], datetime]:
    ticket_start_url, expires_at = _build_worker_command_url(
        request,
        worker_id=worker_id,
        ticket_id=ticket_id,
        command_name="ticket-start",
        issued_at=issued_at,
    )
    ticket_heartbeat_url, _ = _build_worker_command_url(
        request,
        worker_id=worker_id,
        ticket_id=ticket_id,
        command_name="ticket-heartbeat",
        issued_at=issued_at,
    )
    ticket_result_submit_url, _ = _build_worker_command_url(
        request,
        worker_id=worker_id,
        ticket_id=ticket_id,
        command_name="ticket-result-submit",
        issued_at=issued_at,
    )
    return {
        "ticket_start_url": ticket_start_url,
        "ticket_heartbeat_url": ticket_heartbeat_url,
        "ticket_result_submit_url": ticket_result_submit_url,
    }, expires_at


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
    worker_id: str,
    ticket_id: str,
    issued_at: datetime,
) -> tuple[dict[str, Any], datetime | None]:
    payload = deepcopy(latest_execution_package["payload"])
    delivery_expires_at: datetime | None = None
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
        worker_urls, expires_at = build_worker_artifact_urls(
            request,
            worker_id=worker_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            issued_at=issued_at,
        )
        if delivery_expires_at is None:
            delivery_expires_at = expires_at
        if isinstance(artifact_access, dict):
            artifact_access.update(worker_urls)
        content_payload.update(worker_urls)
    return payload, delivery_expires_at


def build_worker_artifact_metadata(
    request: Request,
    *,
    worker_id: str,
    ticket_id: str,
    issued_at: datetime,
    artifact: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], datetime]:
    rewritten = dict(metadata)
    worker_urls, expires_at = build_worker_artifact_urls(
        request,
        worker_id=worker_id,
        ticket_id=ticket_id,
        artifact_ref=str(artifact["artifact_ref"]),
        issued_at=issued_at,
    )
    rewritten.update(worker_urls)
    return rewritten, expires_at


def build_output_schema_body_for_execution_package(
    execution_package_payload: dict[str, Any],
) -> dict[str, Any]:
    execution = execution_package_payload.get("execution") or {}
    return get_output_schema_body(
        str(execution.get("output_schema_ref") or ""),
        int(execution.get("output_schema_version") or 0),
    )
