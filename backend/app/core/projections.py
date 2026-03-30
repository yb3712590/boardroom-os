from __future__ import annotations

from app.contracts.events import EventSeverity
from app.contracts.projections import (
    ActiveWorkflowProjection,
    DashboardProjectionData,
    DashboardProjectionEnvelope,
    EventStreamPreviewItem,
    IncidentDetailProjectionData,
    IncidentDetailProjectionEnvelope,
    IncidentProjectionItem,
    InboxCountsProjection,
    InboxItemProjection,
    InboxProjectionData,
    InboxProjectionEnvelope,
    OpsStripProjection,
    PipelineSummaryProjection,
    ReviewRoomDraftDefaults,
    ReviewRoomDeveloperInspectorProjectionData,
    ReviewRoomDeveloperInspectorProjectionEnvelope,
    ReviewRoomProjectionData,
    ReviewRoomProjectionEnvelope,
    TicketArtifactProjection,
    TicketArtifactsProjectionData,
    TicketArtifactsProjectionEnvelope,
    RouteTarget,
    WorkerAuthRejectionAdminProjection,
    WorkerBindingAdminProjection,
    WorkerDeliveryGrantAdminProjection,
    WorkerRuntimeProjectionData,
    WorkerRuntimeProjectionEnvelope,
    WorkerRuntimeProjectionFilters,
    WorkerRuntimeProjectionSummary,
    WorkerSessionAdminProjection,
    WorkforceSummaryProjection,
    WorkspaceSummary,
)
from app.core.artifacts import build_artifact_metadata
from app.core.constants import (
    APPROVAL_STATUS_OPEN,
    INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
    INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
    SCHEMA_VERSION,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _is_worker_session_active(session: dict[str, object], *, at) -> bool:
    expires_at = session.get("expires_at")
    return bool(session.get("revoked_at") is None and expires_at is not None and expires_at > at)


def _is_worker_delivery_grant_active(grant: dict[str, object], *, at) -> bool:
    expires_at = grant.get("expires_at")
    return bool(grant.get("revoked_at") is None and expires_at is not None and expires_at > at)


def _build_workforce_summary(repository: ControlPlaneRepository) -> WorkforceSummaryProjection:
    employees = repository.list_employee_projections(states=["ACTIVE"], board_approved_only=True)
    busy_tickets = repository.list_ticket_projections_by_statuses_readonly(["LEASED", "EXECUTING"])
    now = now_local()

    busy_workers: set[str] = set()
    for ticket in busy_tickets:
        owner = ticket.get("lease_owner")
        if owner is None:
            continue
        if ticket["status"] == "EXECUTING":
            busy_workers.add(owner)
            continue
        lease_expiry = ticket.get("lease_expires_at")
        if lease_expiry is not None and lease_expiry > now:
            busy_workers.add(owner)

    active_workers = 0
    idle_workers = 0
    active_checkers = 0
    for employee in employees:
        role_type = employee.get("role_type")
        is_busy = employee["employee_id"] in busy_workers
        if role_type == "checker":
            if is_busy:
                active_checkers += 1
            continue
        if is_busy:
            active_workers += 1
        else:
            idle_workers += 1

    return WorkforceSummaryProjection(
        active_workers=active_workers,
        idle_workers=idle_workers,
        overloaded_workers=0,
        active_checkers=active_checkers,
        workers_in_rework_loop=0,
    )


def build_dashboard_projection(repository: ControlPlaneRepository) -> DashboardProjectionEnvelope:
    repository.initialize()
    active_workflow = repository.get_active_workflow()
    cursor, projection_version = repository.get_cursor_and_version()
    pending_approvals = repository.count_open_approvals()
    open_incidents = repository.count_open_incidents()
    open_circuit_breakers = repository.count_open_circuit_breakers()
    open_provider_incidents = repository.count_open_provider_incidents()
    active_tickets = repository.count_active_tickets()
    blocked_nodes = repository.count_blocked_nodes()
    blocked_node_ids = repository.list_blocked_node_ids()

    if active_workflow is None:
        active_workflow_projection = None
        budget_total = 0
        budget_used = 0
    else:
        active_workflow_projection = ActiveWorkflowProjection(
            workflow_id=active_workflow["workflow_id"],
            title=active_workflow["title"],
            north_star_goal=active_workflow["north_star_goal"],
            status=active_workflow["status"],
            current_stage=active_workflow["current_stage"],
            started_at=active_workflow["started_at"],
            deadline_at=active_workflow["deadline_at"],
        )
        budget_total = active_workflow["budget_total"]
        budget_used = active_workflow["budget_used"]

    preview_events = [
        EventStreamPreviewItem(
            event_id=event["event_id"],
            occurred_at=event["occurred_at"],
            category=event["category"],
            severity=EventSeverity(event["severity"]),
            message=event["message"],
            related_ref=event["related_ref"],
        )
        for event in repository.get_recent_event_previews()
    ]

    return DashboardProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=DashboardProjectionData(
            workspace=WorkspaceSummary(
                workspace_id="ws_default",
                workspace_name="Default Workspace",
            ),
            active_workflow=active_workflow_projection,
            ops_strip=OpsStripProjection(
                budget_total=budget_total,
                budget_used=budget_used,
                budget_remaining=max(budget_total - budget_used, 0),
                token_burn_rate_5m=0,
                active_tickets=active_tickets,
                blocked_nodes=blocked_nodes,
                open_incidents=open_incidents,
                open_circuit_breakers=open_circuit_breakers,
                provider_health_summary="DEGRADED" if open_provider_incidents > 0 else "UNKNOWN",
            ),
            pipeline_summary=PipelineSummaryProjection(
                phases=[],
                critical_path_node_ids=[],
                blocked_node_ids=blocked_node_ids,
            ),
            inbox_counts=InboxCountsProjection(
                approvals_pending=pending_approvals,
                incidents_pending=open_incidents,
                budget_alerts=0,
                provider_alerts=open_provider_incidents,
            ),
            workforce_summary=_build_workforce_summary(repository),
            event_stream_preview=preview_events,
        ),
    )


def build_inbox_projection(repository: ControlPlaneRepository) -> InboxProjectionEnvelope:
    repository.initialize()
    cursor, projection_version = repository.get_cursor_and_version()
    items = []
    for approval in repository.list_open_approvals():
        payload = approval["payload"]
        items.append(
            InboxItemProjection(
                inbox_item_id=f"inbox_{approval['approval_id']}",
                workflow_id=approval["workflow_id"],
                item_type="BOARD_APPROVAL",
                priority=payload.get("priority", "medium"),
                status=approval["status"],
                created_at=approval["created_at"],
                sla_due_at=None,
                title=payload.get("inbox_title", approval["review_pack_id"]),
                summary=payload.get("inbox_summary", "Board review pending."),
                source_ref=approval["approval_id"],
                route_target=RouteTarget(
                    view="review_room",
                    review_pack_id=approval["review_pack_id"],
                ),
                badges=payload.get("badges", []),
            )
        )
    for incident in repository.list_open_incidents():
        if incident.get("provider_id") is not None:
            provider_id = str(incident["provider_id"])
            pause_reason = str((incident.get("payload") or {}).get("pause_reason") or "PROVIDER_FAILURE")
            items.append(
                InboxItemProjection(
                    inbox_item_id=f"inbox_{incident['incident_id']}",
                    workflow_id=incident["workflow_id"],
                    item_type="PROVIDER_INCIDENT",
                    priority=str(incident.get("severity") or "high"),
                    status=incident["status"],
                    created_at=incident["opened_at"],
                    sla_due_at=None,
                    title=f"Provider pause on {provider_id}",
                    summary=(
                        f"Provider {provider_id} entered paused state because of {pause_reason.lower()}."
                    ),
                    source_ref=incident["incident_id"],
                    route_target=RouteTarget(
                        view="incident_detail",
                        incident_id=incident["incident_id"],
                    ),
                    badges=["provider", "execution_pause"],
                )
            )
            continue
        if incident.get("incident_type") == INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
            node_id = incident.get("node_id") or "unknown-node"
            latest_failure_kind = str(
                (incident.get("payload") or {}).get("latest_failure_kind") or "RUNTIME_ERROR"
            )
            items.append(
                InboxItemProjection(
                    inbox_item_id=f"inbox_{incident['incident_id']}",
                    workflow_id=incident["workflow_id"],
                    item_type="INCIDENT_ESCALATION",
                    priority=str(incident.get("severity") or "high"),
                    status=incident["status"],
                    created_at=incident["opened_at"],
                    sla_due_at=None,
                    title=f"Repeated failure escalation in {node_id}",
                    summary=(
                        f"Node {node_id} repeated the same {latest_failure_kind.lower()} "
                        "fingerprint and opened a circuit breaker."
                    ),
                    source_ref=incident["incident_id"],
                    route_target=RouteTarget(
                        view="incident_detail",
                        incident_id=incident["incident_id"],
                    ),
                    badges=["repeat_failure", "circuit_breaker"],
                )
            )
            continue
        items.append(
            InboxItemProjection(
                inbox_item_id=f"inbox_{incident['incident_id']}",
                workflow_id=incident["workflow_id"],
                item_type="INCIDENT_ESCALATION",
                priority=str(incident.get("severity") or "high"),
                status=incident["status"],
                created_at=incident["opened_at"],
                sla_due_at=None,
                title=f"Repeated timeout escalation in {incident.get('node_id') or 'unknown-node'}",
                summary=(
                    f"Node {incident.get('node_id') or 'unknown-node'} hit repeated runtime timeout "
                    "threshold and opened a circuit breaker."
                ),
                source_ref=incident["incident_id"],
                route_target=RouteTarget(
                    view="incident_detail",
                    incident_id=incident["incident_id"],
                ),
                badges=["runtime_timeout", "circuit_breaker"],
            )
        )
    items.sort(key=lambda item: item.created_at, reverse=True)
    return InboxProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=InboxProjectionData(items=items),
    )


def build_review_room_projection(
    repository: ControlPlaneRepository,
    review_pack_id: str,
) -> ReviewRoomProjectionEnvelope | None:
    repository.initialize()
    approval = repository.get_approval_by_review_pack_id(review_pack_id)
    if approval is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    payload = approval["payload"]
    available_actions = payload.get("available_actions", [])
    if approval["status"] != APPROVAL_STATUS_OPEN:
        available_actions = []

    return ReviewRoomProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=ReviewRoomProjectionData(
            review_pack=payload.get("review_pack"),
            available_actions=available_actions,
            draft_defaults=ReviewRoomDraftDefaults(**payload.get("draft_defaults", {})),
        ),
    )


def build_review_room_developer_inspector_projection(
    repository: ControlPlaneRepository,
    review_pack_id: str,
    developer_inspector_store: DeveloperInspectorStore,
) -> ReviewRoomDeveloperInspectorProjectionEnvelope | None:
    repository.initialize()
    approval = repository.get_approval_by_review_pack_id(review_pack_id)
    if approval is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    review_pack = approval["payload"].get("review_pack") or {}
    refs = review_pack.get("developer_inspector_refs") or {}
    compiled_context_bundle_ref = refs.get("compiled_context_bundle_ref")
    compile_manifest_ref = refs.get("compile_manifest_ref")
    compiled_context_bundle = (
        developer_inspector_store.read_json(compiled_context_bundle_ref)
        if compiled_context_bundle_ref is not None
        else None
    )
    compile_manifest = (
        developer_inspector_store.read_json(compile_manifest_ref)
        if compile_manifest_ref is not None
        else None
    )

    ref_count = sum(
        ref is not None for ref in (compiled_context_bundle_ref, compile_manifest_ref)
    )
    materialized_count = sum(
        payload is not None for payload in (compiled_context_bundle, compile_manifest)
    )
    availability = "missing"
    if ref_count == 2 and materialized_count == 2:
        availability = "ready"
    elif ref_count > 0 or materialized_count > 0:
        availability = "partial"

    return ReviewRoomDeveloperInspectorProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=ReviewRoomDeveloperInspectorProjectionData(
            review_pack_id=review_pack_id,
            compiled_context_bundle_ref=compiled_context_bundle_ref,
            compile_manifest_ref=compile_manifest_ref,
            compiled_context_bundle=compiled_context_bundle,
            compile_manifest=compile_manifest,
            availability=availability,
        ),
    )


def build_ticket_artifacts_projection(
    repository: ControlPlaneRepository,
    ticket_id: str,
) -> TicketArtifactsProjectionEnvelope | None:
    repository.initialize()
    ticket = repository.get_current_ticket_projection(ticket_id)
    if ticket is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    artifacts = repository.list_ticket_artifacts(ticket_id)
    return TicketArtifactsProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=TicketArtifactsProjectionData(
            ticket_id=ticket_id,
            artifacts=[
                TicketArtifactProjection(
                    artifact_ref=metadata["artifact_ref"],
                    path=metadata["path"],
                    kind=metadata["kind"],
                    media_type=metadata["media_type"],
                    status=metadata["status"],
                    materialization_status=metadata["materialization_status"],
                    lifecycle_status=metadata["lifecycle_status"],
                    retention_class=metadata["retention_class"],
                    expires_at=metadata["expires_at"],
                    deleted_at=metadata["deleted_at"],
                    size_bytes=metadata["size_bytes"],
                    content_hash=metadata["content_hash"],
                    content_url=metadata["content_url"],
                    download_url=metadata["download_url"],
                    preview_url=metadata["preview_url"],
                    created_at=metadata["created_at"],
                )
                for artifact in artifacts
                for metadata in [build_artifact_metadata(artifact)]
            ],
        ),
    )


def build_incident_detail_projection(
    repository: ControlPlaneRepository,
    incident_id: str,
) -> IncidentDetailProjectionEnvelope | None:
    repository.initialize()
    incident = repository.get_incident_projection(incident_id)
    if incident is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    return IncidentDetailProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=IncidentDetailProjectionData(
            incident=IncidentProjectionItem(
                incident_id=incident["incident_id"],
                workflow_id=incident["workflow_id"],
                node_id=incident.get("node_id"),
                ticket_id=incident.get("ticket_id"),
                provider_id=incident.get("provider_id"),
                incident_type=incident["incident_type"],
                status=incident["status"],
                severity=incident.get("severity"),
                fingerprint=incident["fingerprint"],
                circuit_breaker_state=incident.get("circuit_breaker_state"),
                opened_at=incident["opened_at"],
                closed_at=incident.get("closed_at"),
                payload=incident.get("payload") or {},
            )
        ),
    )


def build_worker_runtime_projection(
    repository: ControlPlaneRepository,
    *,
    worker_id: str | None,
    tenant_id: str | None,
    workspace_id: str | None,
    active_only: bool,
    rejection_limit: int,
    grant_limit: int,
) -> WorkerRuntimeProjectionEnvelope:
    repository.initialize()
    generated_at = now_local()
    cursor, projection_version = repository.get_cursor_and_version()
    bindings = repository.list_worker_binding_admin_views(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        at=generated_at,
    )
    sessions = repository.list_worker_sessions(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    session_items = [
        WorkerSessionAdminProjection(
            session_id=str(session["session_id"]),
            worker_id=str(session["worker_id"]),
            tenant_id=str(session["tenant_id"]),
            workspace_id=str(session["workspace_id"]),
            issued_at=session["issued_at"],
            expires_at=session["expires_at"],
            last_seen_at=session["last_seen_at"],
            revoked_at=session.get("revoked_at"),
            credential_version=int(session["credential_version"]),
            revoke_reason=session.get("revoke_reason"),
            revoked_via=session.get("revoked_via"),
            revoked_by=session.get("revoked_by"),
            is_active=_is_worker_session_active(session, at=generated_at),
        )
        for session in sorted(
            sessions,
            key=lambda item: (item["issued_at"], str(item["session_id"])),
            reverse=True,
        )
    ]
    if active_only:
        session_items = [item for item in session_items if item.is_active]

    grants = repository.list_worker_delivery_grants(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    grant_items = [
        WorkerDeliveryGrantAdminProjection(
            grant_id=str(grant["grant_id"]),
            scope=str(grant["scope"]),
            worker_id=str(grant["worker_id"]),
            session_id=str(grant["session_id"]),
            credential_version=int(grant["credential_version"]),
            tenant_id=str(grant["tenant_id"]),
            workspace_id=str(grant["workspace_id"]),
            ticket_id=str(grant["ticket_id"]),
            artifact_ref=grant.get("artifact_ref"),
            artifact_action=grant.get("artifact_action"),
            command_name=grant.get("command_name"),
            issued_at=grant["issued_at"],
            expires_at=grant["expires_at"],
            revoked_at=grant.get("revoked_at"),
            revoke_reason=grant.get("revoke_reason"),
            revoked_via=grant.get("revoked_via"),
            revoked_by=grant.get("revoked_by"),
            is_active=_is_worker_delivery_grant_active(grant, at=generated_at),
        )
        for grant in sorted(
            grants,
            key=lambda item: (item["issued_at"], str(item["grant_id"])),
            reverse=True,
        )
    ]
    if active_only:
        grant_items = [item for item in grant_items if item.is_active]
    grant_items = grant_items[:grant_limit]

    rejections = repository.list_worker_auth_rejection_logs(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    rejection_items = [
        WorkerAuthRejectionAdminProjection(
            occurred_at=rejection["occurred_at"],
            route_family=str(rejection["route_family"]),
            reason_code=str(rejection["reason_code"]),
            worker_id=rejection.get("worker_id"),
            session_id=rejection.get("session_id"),
            grant_id=rejection.get("grant_id"),
            ticket_id=rejection.get("ticket_id"),
            tenant_id=rejection.get("tenant_id"),
            workspace_id=rejection.get("workspace_id"),
        )
        for rejection in sorted(
            rejections,
            key=lambda item: (item["occurred_at"], str(item.get("rejection_id") or "")),
            reverse=True,
        )[:rejection_limit]
    ]

    return WorkerRuntimeProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=WorkerRuntimeProjectionData(
            summary=WorkerRuntimeProjectionSummary(
                binding_count=len(bindings),
                cleanup_eligible_binding_count=sum(
                    1 for binding in bindings if bool(binding.get("cleanup_eligible"))
                ),
                active_session_count=sum(1 for item in session_items if item.is_active),
                active_delivery_grant_count=sum(1 for item in grant_items if item.is_active),
                recent_rejection_count=len(rejection_items),
            ),
            filters=WorkerRuntimeProjectionFilters(
                worker_id=worker_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                active_only=active_only,
                rejection_limit=rejection_limit,
                grant_limit=grant_limit,
            ),
            bindings=[
                WorkerBindingAdminProjection(
                    worker_id=str(binding["worker_id"]),
                    credential_version=int(binding["credential_version"]),
                    tenant_id=str(binding["tenant_id"]),
                    workspace_id=str(binding["workspace_id"]),
                    revoked_before=binding.get("revoked_before"),
                    rotated_at=binding.get("rotated_at"),
                    updated_at=binding["updated_at"],
                    active_session_count=int(binding["active_session_count"]),
                    active_delivery_grant_count=int(binding["active_delivery_grant_count"]),
                    active_ticket_count=int(binding["active_ticket_count"]),
                    latest_bootstrap_issue_at=binding.get("latest_bootstrap_issue_at"),
                    latest_bootstrap_issue_source=binding.get("latest_bootstrap_issue_source"),
                    cleanup_eligible=bool(binding["cleanup_eligible"]),
                )
                for binding in bindings
            ],
            sessions=session_items,
            delivery_grants=grant_items,
            auth_rejections=rejection_items,
        ),
    )
