from __future__ import annotations

from datetime import datetime

from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from tests.test_api import _ensure_scoped_workflow, _seed_created_ticket, _ticket_create_payload


def _seed_ticket_created_event(
    client,
    *,
    workflow_id: str,
    ticket_payload: dict,
    idempotency_key: str,
    occurred_at: str = "2026-03-28T10:30:00+08:00",
) -> None:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="TICKET_CREATED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
            causation_id=None,
            correlation_id=workflow_id,
            payload=ticket_payload,
            occurred_at=datetime.fromisoformat(occurred_at),
        )
        repository.refresh_projections(connection)


def test_ticket_graph_snapshot_builds_parent_dependency_and_review_edges(client):
    workflow_id = "wf_ticket_graph_edges"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph edge coverage",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_architecture_brief",
        node_id="node_architecture_brief",
        role_profile_ref="architect_primary",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_technology_decision",
        node_id="node_technology_decision",
        role_profile_ref="cto_primary",
        output_schema_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
        delivery_stage="BUILD",
        parent_ticket_id="tkt_architecture_brief",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_recommendation",
        node_id="node_backlog_recommendation",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=BACKLOG_RECOMMENDATION_SCHEMA_REF,
        delivery_stage="BUILD",
        parent_ticket_id="tkt_technology_decision",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_build_frontend",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_build_frontend",
                node_id="node_build_frontend",
                role_profile_ref="frontend_engineer_primary",
                output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                delivery_stage="BUILD",
                parent_ticket_id="tkt_backlog_recommendation",
                dispatch_intent={
                    "assignee_employee_id": "emp_frontend_2",
                    "selection_reason": "Seed frontend build",
                    "dependency_gate_refs": [],
                    "selected_by": "test",
                    "wakeup_policy": "default",
                },
            ),
        },
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_check_frontend",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_check_frontend",
                node_id="node_check_frontend",
                role_profile_ref="checker_primary",
                output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
                delivery_stage="CHECK",
                parent_ticket_id="tkt_build_frontend",
                dispatch_intent={
                    "assignee_employee_id": "emp_checker_1",
                    "selection_reason": "Seed checker ticket",
                    "dependency_gate_refs": ["tkt_build_frontend"],
                    "selected_by": "test",
                    "wakeup_policy": "default",
                },
            ),
            "ticket_kind": "MAKER_CHECKER_REVIEW",
            "maker_checker_context": {
                "maker_ticket_id": "tkt_build_frontend",
                "maker_completed_by": "emp_frontend_2",
                "maker_artifact_refs": ["art://delivery/source.json"],
                "maker_process_asset_refs": ["SOURCE_CODE_DELIVERY:scd_tkt_build_frontend@1"],
                "maker_ticket_spec": {
                    "ticket_id": "tkt_build_frontend",
                    "node_id": "node_build_frontend",
                    "role_profile_ref": "frontend_engineer_primary",
                    "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                    "delivery_stage": "BUILD",
                },
                "original_review_request": {
                    "review_type": "INTERNAL_DELIVERY_REVIEW",
                },
            },
        },
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    edge_tuples = {
        (edge.edge_type, edge.source_ticket_id, edge.target_ticket_id)
        for edge in snapshot.edges
    }

    assert snapshot.graph_version.startswith("gv_")
    assert ("PARENT_OF", "tkt_architecture_brief", "tkt_technology_decision") in edge_tuples
    assert ("PARENT_OF", "tkt_technology_decision", "tkt_backlog_recommendation") in edge_tuples
    assert ("DEPENDS_ON", "tkt_build_frontend", "tkt_check_frontend") in edge_tuples
    assert ("REVIEWS", "tkt_check_frontend", "tkt_build_frontend") in edge_tuples


def test_ticket_graph_snapshot_fail_closes_invalid_legacy_dependency(client):
    workflow_id = "wf_ticket_graph_invalid_dependency"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph invalid dependency",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_invalid_dependency",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_invalid_dependency",
                node_id="node_invalid_dependency",
                role_profile_ref="frontend_engineer_primary",
                output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                delivery_stage="BUILD",
                dispatch_intent={
                    "assignee_employee_id": "emp_frontend_2",
                    "selection_reason": "Seed invalid dependency",
                    "dependency_gate_refs": ["tkt_missing_dependency"],
                    "selected_by": "test",
                    "wakeup_policy": "default",
                },
            ),
        },
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)

    assert snapshot.index_summary.blocked_node_ids == ["node_invalid_dependency"]
    assert snapshot.reduction_issues
    assert snapshot.reduction_issues[0].issue_code == "graph.dependency.missing_ticket"


def test_ceo_shadow_snapshot_exposes_ticket_graph_summary_without_changing_controller_state(client):
    workflow_id = "wf_ticket_graph_snapshot"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph snapshot",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ready_build",
        node_id="node_ready_build",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="SCHEDULER_IDLE_MAINTENANCE",
        trigger_ref="test-ticket-graph-snapshot",
    )

    assert snapshot["controller_state"]["state"] == "READY_TICKET"
    assert snapshot["ticket_graph"]["index_summary"]["ready_node_ids"] == ["node_ready_build"]
    assert snapshot["ticket_graph"]["index_summary"]["blocked_node_ids"] == []
