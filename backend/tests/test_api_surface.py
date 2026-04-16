from __future__ import annotations

from app.api.router_registry import (
    ALL_ROUTE_GROUPS,
    FROZEN_ROUTE_GROUPS,
    MAINLINE_ROUTE_GROUPS,
)
from app.main import create_app
from app.core.api_surface import collect_api_surface_groups


def test_collect_api_surface_groups_matches_current_route_families():
    app = create_app()

    groups = collect_api_surface_groups(app)

    assert set(groups) == {
        "commands",
        "projections",
        "artifacts",
        "artifact-uploads",
        "events",
        "worker-runtime",
        "worker-admin",
        "worker-admin-projections",
        "worker-runtime-projections",
    }
    assert set(groups["commands"]) == {
        "POST /api/v1/commands/artifact-cleanup",
        "POST /api/v1/commands/artifact-delete",
        "POST /api/v1/commands/board-advisory-append-turn",
        "POST /api/v1/commands/board-advisory-apply-patch",
        "POST /api/v1/commands/board-advisory-request-analysis",
        "POST /api/v1/commands/board-approve",
        "POST /api/v1/commands/board-reject",
        "POST /api/v1/commands/employee-freeze",
        "POST /api/v1/commands/employee-hire-request",
        "POST /api/v1/commands/employee-replace-request",
        "POST /api/v1/commands/employee-restore",
        "POST /api/v1/commands/incident-resolve",
        "POST /api/v1/commands/meeting-request",
        "POST /api/v1/commands/modify-constraints",
        "POST /api/v1/commands/project-init",
        "POST /api/v1/commands/runtime-provider-connectivity-test",
        "POST /api/v1/commands/runtime-provider-models-refresh",
        "POST /api/v1/commands/runtime-provider-upsert",
        "POST /api/v1/commands/scheduler-tick",
        "POST /api/v1/commands/ticket-artifact-import-upload",
        "POST /api/v1/commands/ticket-cancel",
        "POST /api/v1/commands/ticket-complete",
        "POST /api/v1/commands/ticket-create",
        "POST /api/v1/commands/ticket-fail",
        "POST /api/v1/commands/ticket-heartbeat",
        "POST /api/v1/commands/ticket-lease",
        "POST /api/v1/commands/ticket-result-submit",
        "POST /api/v1/commands/ticket-start",
    }
    assert set(groups["projections"]) == {
        "GET /api/v1/projections/artifact-cleanup-candidates",
        "GET /api/v1/projections/dashboard",
        "GET /api/v1/projections/inbox",
        "GET /api/v1/projections/incidents/{incident_id}",
        "GET /api/v1/projections/meetings/{meeting_id}",
        "GET /api/v1/projections/review-room/{review_pack_id}",
        "GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector",
        "GET /api/v1/projections/runtime-provider",
        "GET /api/v1/projections/tickets/{ticket_id}/artifacts",
        "GET /api/v1/projections/workflows/{workflow_id}/ceo-shadow",
        "GET /api/v1/projections/workflows/{workflow_id}/dependency-inspector",
        "GET /api/v1/projections/workforce",
    }
    assert set(groups["artifacts"]) == {
        "GET /api/v1/artifacts/by-ref",
        "GET /api/v1/artifacts/content",
        "GET /api/v1/artifacts/preview",
    }
    assert set(groups["artifact-uploads"]) == {
        "POST /api/v1/artifact-uploads/sessions",
        "POST /api/v1/artifact-uploads/sessions/{session_id}/abort",
        "POST /api/v1/artifact-uploads/sessions/{session_id}/complete",
        "PUT /api/v1/artifact-uploads/sessions/{session_id}/parts/{part_number}",
    }
    assert set(groups["events"]) == {
        "GET /api/v1/events/stream",
    }
    assert set(groups["worker-runtime"]) == {
        "GET /api/v1/worker-runtime/assignments",
        "GET /api/v1/worker-runtime/artifacts/by-ref",
        "GET /api/v1/worker-runtime/artifacts/content",
        "GET /api/v1/worker-runtime/artifacts/preview",
        "GET /api/v1/worker-runtime/tickets/{ticket_id}/execution-package",
        "POST /api/v1/worker-runtime/commands/ticket-artifact-import-upload",
        "POST /api/v1/worker-runtime/commands/ticket-heartbeat",
        "POST /api/v1/worker-runtime/commands/ticket-result-submit",
        "POST /api/v1/worker-runtime/commands/ticket-start",
    }
    assert set(groups["worker-admin"]) == {
        "GET /api/v1/worker-admin/auth-rejections",
        "GET /api/v1/worker-admin/bindings",
        "GET /api/v1/worker-admin/bootstrap-issues",
        "GET /api/v1/worker-admin/delivery-grants",
        "GET /api/v1/worker-admin/operator-tokens",
        "GET /api/v1/worker-admin/scope-summary",
        "GET /api/v1/worker-admin/sessions",
        "POST /api/v1/worker-admin/cleanup-bindings",
        "POST /api/v1/worker-admin/contain-scope",
        "POST /api/v1/worker-admin/create-binding",
        "POST /api/v1/worker-admin/issue-bootstrap",
        "POST /api/v1/worker-admin/revoke-bootstrap",
        "POST /api/v1/worker-admin/revoke-delivery-grant",
        "POST /api/v1/worker-admin/revoke-operator-token",
        "POST /api/v1/worker-admin/revoke-session",
    }
    assert set(groups["worker-admin-projections"]) == {
        "GET /api/v1/projections/worker-admin-audit",
        "GET /api/v1/projections/worker-admin-auth-rejections",
    }
    assert set(groups["worker-runtime-projections"]) == {
        "GET /api/v1/projections/worker-runtime",
    }


def test_router_registry_declares_stable_mainline_and_frozen_group_order():
    assert ALL_ROUTE_GROUPS == (
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
    assert FROZEN_ROUTE_GROUPS == (
        "artifact-uploads",
        "worker-runtime",
        "worker-admin",
        "worker-admin-projections",
        "worker-runtime-projections",
    )
    assert MAINLINE_ROUTE_GROUPS == (
        "commands",
        "projections",
        "artifacts",
        "events",
    )
