from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.contracts.artifacts import (
    ArtifactMetadata,
    ArtifactMetadataEnvelope,
    ArtifactPreviewData,
    ArtifactPreviewEnvelope,
)
from app.contracts.commands import (
    CommandAckEnvelope,
    TicketHeartbeatCommand,
    TicketResultSubmitCommand,
    TicketStartCommand,
)
from app.contracts.worker_runtime import (
    WorkerAssignmentItem,
    WorkerAssignmentsData,
    WorkerAssignmentsEnvelope,
    WorkerExecutionPackageData,
    WorkerExecutionPackageEnvelope,
    WorkerTicketHeartbeatCommand,
    WorkerTicketResultSubmitCommand,
    WorkerTicketStartCommand,
)
from app.core.artifact_store import ArtifactStore
from app.core.artifacts import (
    ARTIFACT_LIFECYCLE_ACTIVE,
    ARTIFACT_STATUS_MATERIALIZED,
    build_artifact_metadata,
    classify_artifact_preview_kind,
    resolve_artifact_lifecycle_status,
)
from app.core.ticket_handlers import (
    handle_ticket_heartbeat,
    handle_ticket_result_submit,
    handle_ticket_start,
)
from app.core.time import now_local
from app.core.worker_runtime import (
    authenticate_worker_assignments_request,
    authenticate_worker_request,
    build_output_schema_body_for_execution_package,
    build_worker_artifact_metadata,
    build_worker_command_endpoints,
    build_worker_execution_package_payload,
    build_worker_execution_package_url,
    ensure_worker_execution_handoff,
    list_worker_assignments,
    require_worker_access_to_artifact,
    require_worker_owned_ticket,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/worker-runtime", tags=["worker-runtime"])


@router.get("/assignments", response_model=WorkerAssignmentsEnvelope)
def get_worker_assignments(
    request: Request,
    x_boardroom_worker_bootstrap: str | None = Header(default=None),
    x_boardroom_worker_session: str | None = Header(default=None),
):
    repository: ControlPlaneRepository = request.app.state.repository
    auth_context = authenticate_worker_assignments_request(
        request,
        bootstrap_token=x_boardroom_worker_bootstrap,
        session_token=x_boardroom_worker_session,
    )
    assignments = list_worker_assignments(repository, principal=auth_context.principal)
    issued_at = now_local()
    return WorkerAssignmentsEnvelope(
        data=WorkerAssignmentsData(
            worker_id=auth_context.principal.worker_id,
            tenant_id=auth_context.principal.tenant_id,
            workspace_id=auth_context.principal.workspace_id,
            session_id=auth_context.session_id,
            session_token=auth_context.session_token,
            session_expires_at=auth_context.session_expires_at,
            assignments=[
                WorkerAssignmentItem(
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    status=ticket["status"],
                    lease_expires_at=ticket.get("lease_expires_at"),
                    execution_package_url=execution_package_url,
                    delivery_expires_at=delivery_expires_at,
                )
                for ticket in assignments
                for execution_package_url, delivery_expires_at in [
                    build_worker_execution_package_url(
                        request,
                        worker_id=auth_context.principal.worker_id,
                        session_id=auth_context.session_id,
                        credential_version=int(auth_context.principal.credential_version or 0),
                        tenant_id=auth_context.principal.tenant_id,
                        workspace_id=auth_context.principal.workspace_id,
                        ticket_id=ticket["ticket_id"],
                        issued_at=issued_at,
                    )
                ]
            ],
        )
    )


@router.get(
    "/tickets/{ticket_id}/execution-package",
    response_model=WorkerExecutionPackageEnvelope,
)
def get_worker_execution_package(
    request: Request,
    ticket_id: str,
    access_token: str | None = Query(default=None),
) -> WorkerExecutionPackageEnvelope:
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="execution_package",
        ticket_id=ticket_id,
    )
    repository: ControlPlaneRepository = request.app.state.repository
    ticket = require_worker_owned_ticket(
        repository,
        ticket_id=ticket_id,
        principal=principal,
    )
    latest_bundle, latest_manifest, latest_execution_package = ensure_worker_execution_handoff(
        repository,
        ticket=ticket,
    )
    issued_at = now_local()
    package_payload, payload_delivery_expires_at = build_worker_execution_package_payload(
        request,
        latest_execution_package=latest_execution_package,
        principal=principal,
        ticket_id=ticket["ticket_id"],
        issued_at=issued_at,
    )
    command_endpoints, command_delivery_expires_at = build_worker_command_endpoints(
        request,
        worker_id=principal.worker_id,
        session_id=str(principal.session_id or ""),
        credential_version=int(principal.credential_version or 0),
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
        ticket_id=ticket["ticket_id"],
        issued_at=issued_at,
    )
    return WorkerExecutionPackageEnvelope(
        data=WorkerExecutionPackageData(
            worker_id=principal.worker_id,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            workflow_id=ticket["workflow_id"],
            ticket_id=ticket["ticket_id"],
            node_id=ticket["node_id"],
            status=ticket["status"],
            bundle_id=latest_bundle["bundle_id"],
            compile_id=latest_manifest["compile_id"],
            compile_request_id=latest_execution_package["compile_request_id"],
            output_schema_body=build_output_schema_body_for_execution_package(package_payload),
            compiled_execution_package=package_payload,
            command_endpoints=command_endpoints,
            delivery_expires_at=payload_delivery_expires_at or command_delivery_expires_at,
        )
    )


@router.get("/artifacts/by-ref", response_model=ArtifactMetadataEnvelope)
def get_worker_artifact_by_ref(
    request: Request,
    artifact_ref: str = Query(min_length=1),
    ticket_id: str = Query(min_length=1),
    access_token: str | None = Query(default=None),
) -> ArtifactMetadataEnvelope:
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="artifact_read",
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
    )
    repository: ControlPlaneRepository = request.app.state.repository
    artifact = require_worker_access_to_artifact(
        repository,
        artifact_ref=artifact_ref,
        ticket_id=ticket_id,
        principal=principal,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_ref}' was not found.")
    metadata, _ = build_worker_artifact_metadata(
        request,
        principal=principal,
        ticket_id=str(artifact["ticket_id"]),
        issued_at=now_local(),
        artifact=artifact,
        metadata=build_artifact_metadata(artifact),
    )
    return ArtifactMetadataEnvelope(data=ArtifactMetadata.model_validate(metadata))


@router.get("/artifacts/content")
def get_worker_artifact_content(
    request: Request,
    artifact_ref: str = Query(min_length=1),
    ticket_id: str = Query(min_length=1),
    disposition: Literal["inline", "attachment"] = "inline",
    access_token: str | None = Query(default=None),
) -> Response:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="artifact_read",
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        artifact_action="content_inline" if disposition == "inline" else "content_attachment",
    )
    artifact = require_worker_access_to_artifact(
        repository,
        artifact_ref=artifact_ref,
        ticket_id=ticket_id,
        principal=principal,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_ref}' was not found.")

    lifecycle_status = resolve_artifact_lifecycle_status(artifact)
    if lifecycle_status != ARTIFACT_LIFECYCLE_ACTIVE:
        raise HTTPException(
            status_code=410,
            detail=f"Artifact '{artifact_ref}' is no longer available ({lifecycle_status}).",
        )
    if artifact.get("materialization_status") != ARTIFACT_STATUS_MATERIALIZED or not artifact.get("storage_relpath"):
        raise HTTPException(
            status_code=409,
            detail=f"Artifact '{artifact_ref}' is registered but not materialized.",
        )

    content = artifact_store.read_bytes(str(artifact["storage_relpath"]))
    filename = str(artifact["logical_path"]).rsplit("/", 1)[-1]
    media_type = artifact.get("media_type") or "application/octet-stream"
    headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/artifacts/preview", response_model=ArtifactPreviewEnvelope)
def get_worker_artifact_preview(
    request: Request,
    artifact_ref: str = Query(min_length=1),
    ticket_id: str = Query(min_length=1),
    access_token: str | None = Query(default=None),
) -> ArtifactPreviewEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="artifact_read",
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        artifact_action="preview",
    )
    artifact = require_worker_access_to_artifact(
        repository,
        artifact_ref=artifact_ref,
        ticket_id=ticket_id,
        principal=principal,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_ref}' was not found.")

    metadata, _ = build_worker_artifact_metadata(
        request,
        principal=principal,
        ticket_id=str(artifact["ticket_id"]),
        issued_at=now_local(),
        artifact=artifact,
        metadata=build_artifact_metadata(artifact),
    )
    lifecycle_status = resolve_artifact_lifecycle_status(artifact)
    if lifecycle_status != ARTIFACT_LIFECYCLE_ACTIVE:
        raise HTTPException(
            status_code=410,
            detail=f"Artifact '{artifact_ref}' is no longer available ({lifecycle_status}).",
        )
    if artifact.get("materialization_status") != ARTIFACT_STATUS_MATERIALIZED or not artifact.get("storage_relpath"):
        raise HTTPException(
            status_code=409,
            detail=f"Artifact '{artifact_ref}' is registered but not materialized.",
        )

    preview_kind = classify_artifact_preview_kind(
        kind=str(artifact["kind"]),
        media_type=artifact.get("media_type"),
    )
    preview_payload = {
        "artifact_ref": artifact_ref,
        "preview_kind": preview_kind,
        "media_type": artifact.get("media_type"),
        "lifecycle_status": metadata["lifecycle_status"],
        "content_url": metadata["content_url"],
        "download_url": metadata["download_url"],
        "json_content": None,
        "text_content": None,
    }
    content = artifact_store.read_bytes(str(artifact["storage_relpath"]))
    if preview_kind == "JSON":
        preview_payload["json_content"] = json.loads(content.decode("utf-8"))
    elif preview_kind == "TEXT":
        preview_payload["text_content"] = content.decode("utf-8")

    return ArtifactPreviewEnvelope(data=ArtifactPreviewData.model_validate(preview_payload))


@router.post("/commands/ticket-start", response_model=CommandAckEnvelope)
def worker_ticket_start(
    request: Request,
    payload: WorkerTicketStartCommand,
    access_token: str | None = Query(default=None),
) -> CommandAckEnvelope:
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="command",
        ticket_id=payload.ticket_id,
        command_name="ticket-start",
    )
    repository: ControlPlaneRepository = request.app.state.repository
    require_worker_owned_ticket(
        repository,
        ticket_id=payload.ticket_id,
        principal=principal,
    )
    return handle_ticket_start(
        repository,
        TicketStartCommand(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            node_id=payload.node_id,
            started_by=principal.worker_id,
            idempotency_key=payload.idempotency_key,
        ),
    )


@router.post("/commands/ticket-heartbeat", response_model=CommandAckEnvelope)
def worker_ticket_heartbeat(
    request: Request,
    payload: WorkerTicketHeartbeatCommand,
    access_token: str | None = Query(default=None),
) -> CommandAckEnvelope:
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="command",
        ticket_id=payload.ticket_id,
        command_name="ticket-heartbeat",
    )
    repository: ControlPlaneRepository = request.app.state.repository
    require_worker_owned_ticket(
        repository,
        ticket_id=payload.ticket_id,
        principal=principal,
    )
    return handle_ticket_heartbeat(
        repository,
        TicketHeartbeatCommand(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            node_id=payload.node_id,
            reported_by=principal.worker_id,
            idempotency_key=payload.idempotency_key,
        ),
    )


@router.post("/commands/ticket-result-submit", response_model=CommandAckEnvelope)
def worker_ticket_result_submit(
    request: Request,
    payload: WorkerTicketResultSubmitCommand,
    access_token: str | None = Query(default=None),
) -> CommandAckEnvelope:
    principal = authenticate_worker_request(
        request,
        access_token=access_token,
        scope="command",
        ticket_id=payload.ticket_id,
        command_name="ticket-result-submit",
    )
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    developer_inspector_store = request.app.state.developer_inspector_store
    require_worker_owned_ticket(
        repository,
        ticket_id=payload.ticket_id,
        principal=principal,
    )
    return handle_ticket_result_submit(
        repository,
        TicketResultSubmitCommand(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            node_id=payload.node_id,
            submitted_by=principal.worker_id,
            result_status=payload.result_status,
            schema_version=payload.schema_version,
            payload=payload.payload,
            artifact_refs=payload.artifact_refs,
            written_artifacts=payload.written_artifacts,
            assumptions=payload.assumptions,
            issues=payload.issues,
            confidence=payload.confidence,
            needs_escalation=payload.needs_escalation,
            summary=payload.summary,
            review_request=payload.review_request,
            failure_kind=payload.failure_kind,
            failure_message=payload.failure_message,
            failure_detail=payload.failure_detail,
            idempotency_key=payload.idempotency_key,
        ),
        developer_inspector_store,
        artifact_store,
    )
