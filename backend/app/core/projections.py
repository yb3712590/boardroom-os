from __future__ import annotations

from app.contracts.events import EventSeverity
from app.contracts.projections import (
    ActiveWorkflowProjection,
    DashboardProjectionData,
    DashboardProjectionEnvelope,
    EventStreamPreviewItem,
    InboxCountsProjection,
    InboxItemProjection,
    InboxProjectionData,
    InboxProjectionEnvelope,
    OpsStripProjection,
    PipelineSummaryProjection,
    ReviewRoomDraftDefaults,
    ReviewRoomProjectionData,
    ReviewRoomProjectionEnvelope,
    RouteTarget,
    WorkforceSummaryProjection,
    WorkspaceSummary,
)
from app.core.constants import APPROVAL_STATUS_OPEN, SCHEMA_VERSION
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def build_dashboard_projection(repository: ControlPlaneRepository) -> DashboardProjectionEnvelope:
    repository.initialize()
    active_workflow = repository.get_active_workflow()
    cursor, projection_version = repository.get_cursor_and_version()
    pending_approvals = repository.count_open_approvals()

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
                active_tickets=0,
                blocked_nodes=0,
                open_incidents=0,
                open_circuit_breakers=0,
                provider_health_summary="UNKNOWN",
            ),
            pipeline_summary=PipelineSummaryProjection(
                phases=[],
                critical_path_node_ids=[],
                blocked_node_ids=[],
            ),
            inbox_counts=InboxCountsProjection(
                approvals_pending=pending_approvals,
                incidents_pending=0,
                budget_alerts=0,
                provider_alerts=0,
            ),
            workforce_summary=WorkforceSummaryProjection(
                active_workers=0,
                idle_workers=0,
                overloaded_workers=0,
                active_checkers=0,
                workers_in_rework_loop=0,
            ),
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
