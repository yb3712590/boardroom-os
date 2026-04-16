from __future__ import annotations

from datetime import datetime

import pytest
import app.core.graph_health as graph_health_module
from pydantic import ValidationError

from app.contracts.advisory import BoardAdvisorySession, GraphPatch, GraphPatchProposal
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from tests.test_api import (
    _create_lease_and_start_ticket,
    _employee_freeze_payload,
    _ensure_scoped_workflow,
    _seed_created_ticket,
    _seed_review_request,
    _ticket_create_payload,
)


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


def _seed_graph_patch_applied_event(
    client,
    *,
    workflow_id: str,
    patch_index: int,
    freeze_node_ids: list[str],
    unfreeze_node_ids: list[str] | None = None,
    focus_node_ids: list[str] | None = None,
    replacements: list[dict[str, str]] | None = None,
    remove_node_ids: list[str] | None = None,
    edge_additions: list[dict[str, str]] | None = None,
    edge_removals: list[dict[str, str]] | None = None,
    payload_override=None,
    occurred_at: str | None = None,
) -> None:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="GRAPH_PATCH_APPLIED",
            actor_type="board",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-graph-patch-applied:{workflow_id}:{patch_index}",
            causation_id=None,
            correlation_id=workflow_id,
            payload=(
                payload_override
                if payload_override is not None
                else {
                    "patch_ref": f"pa://graph-patch/{workflow_id}@{patch_index}",
                    "workflow_id": workflow_id,
                    "session_id": f"adv_graph_patch_{patch_index}",
                    "proposal_ref": f"pa://graph-patch-proposal/{workflow_id}@{patch_index}",
                    "base_graph_version": f"gv_{patch_index}",
                    "freeze_node_ids": list(freeze_node_ids),
                    "unfreeze_node_ids": list(unfreeze_node_ids or []),
                    "focus_node_ids": list(focus_node_ids or freeze_node_ids),
                    "replacements": list(replacements or []),
                    "remove_node_ids": list(remove_node_ids or []),
                    "edge_additions": list(edge_additions or []),
                    "edge_removals": list(edge_removals or []),
                    "reason_summary": "Seed graph patch event for graph health coverage.",
                    "patch_hash": f"hash-{workflow_id}-{patch_index}",
                }
            ),
            occurred_at=datetime.fromisoformat(
                occurred_at or f"2026-04-16T20:0{patch_index}:00+08:00"
            ),
        )
        if payload_override is None or isinstance(payload_override, dict):
            repository.refresh_projections(connection)


def test_graph_patch_contract_accepts_replacements_remove_and_edge_deltas():
    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": "pa://graph-patch-proposal/adv_contracts@1",
            "workflow_id": "wf_graph_patch_contracts",
            "session_id": "adv_contracts",
            "base_graph_version": "gv_1",
            "proposal_summary": "Replace the stale branch with the new branch and rewire the parent edge.",
            "impact_summary": "Supersede node_old, remove node_removed, and connect node_parent to node_new.",
            "freeze_node_ids": ["node_new"],
            "unfreeze_node_ids": [],
            "focus_node_ids": ["node_new"],
            "replacements": [
                {
                    "old_node_id": "node_old",
                    "new_node_id": "node_new",
                }
            ],
            "remove_node_ids": ["node_removed"],
            "edge_additions": [
                {
                    "edge_type": "PARENT_OF",
                    "source_node_id": "node_parent",
                    "target_node_id": "node_new",
                }
            ],
            "edge_removals": [
                {
                    "edge_type": "PARENT_OF",
                    "source_node_id": "node_parent",
                    "target_node_id": "node_old",
                }
            ],
            "source_decision_pack_ref": "pa://decision-summary/adv_contracts@1",
            "proposal_hash": "hash-graph-patch-contracts",
        }
    )

    patch = GraphPatch.model_validate(
        {
            "patch_ref": "pa://graph-patch/adv_contracts@1",
            "workflow_id": proposal.workflow_id,
            "session_id": proposal.session_id,
            "proposal_ref": proposal.proposal_ref,
            "base_graph_version": proposal.base_graph_version,
            "freeze_node_ids": list(proposal.freeze_node_ids),
            "unfreeze_node_ids": list(proposal.unfreeze_node_ids),
            "focus_node_ids": list(proposal.focus_node_ids),
            "replacements": [item.model_dump(mode="json") for item in proposal.replacements],
            "remove_node_ids": list(proposal.remove_node_ids),
            "edge_additions": [item.model_dump(mode="json") for item in proposal.edge_additions],
            "edge_removals": [item.model_dump(mode="json") for item in proposal.edge_removals],
            "reason_summary": proposal.proposal_summary,
            "patch_hash": proposal.proposal_hash,
        }
    )

    assert proposal.replacements[0].old_node_id == "node_old"
    assert proposal.edge_additions[0].edge_type == "PARENT_OF"
    assert patch.remove_node_ids == ["node_removed"]
    assert patch.replacements[0].new_node_id == "node_new"


def test_graph_patch_contract_rejects_add_node_and_conflicting_replace_remove():
    with pytest.raises(ValidationError, match="add_node_ids"):
        GraphPatchProposal.model_validate(
            {
                "proposal_ref": "pa://graph-patch-proposal/adv_contract_invalid@1",
                "workflow_id": "wf_graph_patch_contract_invalid",
                "session_id": "adv_contract_invalid",
                "base_graph_version": "gv_1",
                "proposal_summary": "This proposal should be rejected because add_node is not part of v2.",
                "impact_summary": "It tries to introduce a brand-new node.",
                "remove_node_ids": ["node_old"],
                "add_node_ids": ["node_new"],
                "source_decision_pack_ref": "pa://decision-summary/adv_contract_invalid@1",
                "proposal_hash": "hash-graph-patch-contract-invalid",
            }
        )

    with pytest.raises(ValidationError, match="cannot both remove and replace"):
        GraphPatch.model_validate(
            {
                "patch_ref": "pa://graph-patch/adv_contract_invalid@1",
                "workflow_id": "wf_graph_patch_contract_invalid",
                "session_id": "adv_contract_invalid",
                "proposal_ref": "pa://graph-patch-proposal/adv_contract_invalid@1",
                "base_graph_version": "gv_1",
                "replacements": [
                    {
                        "old_node_id": "node_old",
                        "new_node_id": "node_new",
                    }
                ],
                "remove_node_ids": ["node_old"],
                "reason_summary": "Conflicting remove and replace for the same node.",
                "patch_hash": "hash-graph-patch-contract-conflict",
            }
        )


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


def test_ticket_graph_snapshot_indexes_in_flight_and_critical_path(client):
    workflow_id = "wf_ticket_graph_in_flight"
    ticket_id = "tkt_in_flight_build"
    node_id = "node_in_flight_build"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph in-flight index",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)

    assert snapshot.index_summary.in_flight_ticket_ids == [ticket_id]
    assert snapshot.index_summary.in_flight_node_ids == [node_id]
    assert snapshot.index_summary.critical_path_node_ids == [node_id]


def test_ticket_graph_snapshot_applies_replacement_and_edge_delta_from_graph_patch_events(client):
    workflow_id = "wf_ticket_graph_patch_replace"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Apply replacement and edge delta overlays from graph patch events.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_patch_parent",
        node_id="node_patch_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_patch_old",
        node_id="node_patch_old",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
        parent_ticket_id="tkt_patch_parent",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_patch_new",
        node_id="node_patch_new",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=["node_patch_new"],
        focus_node_ids=["node_patch_new"],
        replacements=[
            {
                "old_node_id": "node_patch_old",
                "new_node_id": "node_patch_new",
            }
        ],
        edge_additions=[
            {
                "edge_type": "PARENT_OF",
                "source_node_id": "node_patch_parent",
                "target_node_id": "node_patch_new",
            }
        ],
        edge_removals=[
            {
                "edge_type": "PARENT_OF",
                "source_node_id": "node_patch_parent",
                "target_node_id": "node_patch_old",
            }
        ],
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    edge_tuples = {(edge.edge_type, edge.source_node_id, edge.target_node_id) for edge in snapshot.edges}
    node_by_id = {node.node_id: node for node in snapshot.nodes}

    assert node_by_id["node_patch_old"].node_status == "SUPERSEDED"
    assert ("REPLACES", "node_patch_new", "node_patch_old") in edge_tuples
    assert ("PARENT_OF", "node_patch_parent", "node_patch_old") not in edge_tuples
    assert ("PARENT_OF", "node_patch_parent", "node_patch_new") in edge_tuples
    assert "node_patch_new" in snapshot.index_summary.blocked_node_ids
    assert "node_patch_old" not in snapshot.index_summary.blocked_node_ids
    assert "node_patch_new" in snapshot.index_summary.critical_path_node_ids
    assert "node_patch_parent" in snapshot.index_summary.critical_path_node_ids


def test_ticket_graph_snapshot_applies_remove_node_patch_and_excludes_cancelled_node_from_ready_index(client):
    workflow_id = "wf_ticket_graph_patch_remove"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Remove nodes through graph patch overlays without treating them as ready work.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_patch_remove_parent",
        node_id="node_patch_remove_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_patch_remove_target",
        node_id="node_patch_remove_target",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
        parent_ticket_id="tkt_patch_remove_parent",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=[],
        remove_node_ids=["node_patch_remove_target"],
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    edge_tuples = {(edge.edge_type, edge.source_node_id, edge.target_node_id) for edge in snapshot.edges}
    node_by_id = {node.node_id: node for node in snapshot.nodes}

    assert node_by_id["node_patch_remove_target"].node_status == "CANCELLED"
    assert ("PARENT_OF", "node_patch_remove_parent", "node_patch_remove_target") not in edge_tuples
    assert "node_patch_remove_target" not in snapshot.index_summary.ready_node_ids
    assert "node_patch_remove_target" not in snapshot.index_summary.blocked_node_ids


def test_graph_health_report_detects_fanout_too_wide(client):
    workflow_id = "wf_graph_health_fanout"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose wide fanout.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_graph_health",
        node_id="node_backlog_graph_health",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=BACKLOG_RECOMMENDATION_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    for index in range(11):
        _seed_ticket_created_event(
            client,
            workflow_id=workflow_id,
            idempotency_key=(
                f"test-seed-ticket-created:{workflow_id}:tkt_graph_health_child_{index}"
            ),
            ticket_payload={
                **_ticket_create_payload(
                    workflow_id=workflow_id,
                    ticket_id=f"tkt_graph_health_child_{index}",
                    node_id=f"node_graph_health_child_{index}",
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                    delivery_stage="BUILD",
                    parent_ticket_id="tkt_backlog_graph_health",
                ),
            },
        )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-fanout",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding_types = [item["finding_type"] for item in report["findings"]]

    assert "FANOUT_TOO_WIDE" in finding_types
    assert report["overall_health"] in {"WARNING", "CRITICAL"}


def test_graph_health_report_detects_persistent_failure_zone(client):
    workflow_id = "wf_graph_health_failure_zone"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose persistent failure zones.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_failure",
        node_id="node_graph_health_failure",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )

    repository = client.app.state.repository
    with repository.transaction() as connection:
        for index in range(3):
            incident_id = f"inc_graph_health_failure_{index}"
            occurred_at = datetime.fromisoformat(f"2026-04-15T20:4{index}:00+08:00")
            repository.insert_event(
                connection,
                event_type="INCIDENT_OPENED",
                actor_type="system",
                actor_id="test-seed",
                workflow_id=workflow_id,
                idempotency_key=f"incident-opened:{workflow_id}:{incident_id}",
                causation_id=None,
                correlation_id=workflow_id,
                payload={
                    "incident_id": incident_id,
                    "node_id": "node_graph_health_failure",
                    "ticket_id": "tkt_graph_health_failure",
                    "incident_type": "REPEATED_FAILURE_ESCALATION",
                    "status": "OPEN",
                    "severity": "high",
                    "fingerprint": (
                        f"{workflow_id}:node_graph_health_failure:"
                        f"repeat-failure:graph-health-{index}"
                    ),
                    "latest_failure_fingerprint": f"graph-health-{index}",
                },
                occurred_at=occurred_at,
            )
        repository.refresh_projections(connection)

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-failure-zone",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "PERSISTENT_FAILURE_ZONE"
    )

    assert report["overall_health"] == "CRITICAL"
    assert finding["affected_nodes"] == ["node_graph_health_failure"]
    assert finding["metric_value"] == 3


def test_graph_health_report_detects_dependency_based_critical_path_depth(client):
    workflow_id = "wf_graph_health_dependency_depth"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should read critical path depth from DAG edges, not parent-only trees.",
    )

    previous_ticket_id = None
    deepest_node_id = None
    for index in range(16):
        ticket_id = f"tkt_graph_health_dependency_depth_{index}"
        node_id = f"node_graph_health_dependency_depth_{index}"
        deepest_node_id = node_id
        dispatch_intent = {
            "assignee_employee_id": "emp_frontend_2",
            "selection_reason": "Seed dependency depth coverage",
            "dependency_gate_refs": [previous_ticket_id] if previous_ticket_id else [],
            "selected_by": "test",
            "wakeup_policy": "default",
        }
        _seed_ticket_created_event(
            client,
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-created:{workflow_id}:{ticket_id}",
            ticket_payload={
                **_ticket_create_payload(
                    workflow_id=workflow_id,
                    ticket_id=ticket_id,
                    node_id=node_id,
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                    delivery_stage="BUILD",
                    dispatch_intent=dispatch_intent,
                ),
            },
        )
        previous_ticket_id = ticket_id

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-dependency-depth",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "CRITICAL_PATH_TOO_DEEP"
    )

    assert finding["affected_nodes"] == [deepest_node_id]
    assert finding["metric_value"] == 16


def test_graph_health_report_detects_bottleneck_dependency_node(client):
    workflow_id = "wf_graph_health_bottleneck"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose dependency bottlenecks.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_shared_dependency",
        node_id="node_graph_health_shared_dependency",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    for index in range(4):
        _seed_ticket_created_event(
            client,
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_graph_health_bottleneck_child_{index}",
            ticket_payload={
                **_ticket_create_payload(
                    workflow_id=workflow_id,
                    ticket_id=f"tkt_graph_health_bottleneck_child_{index}",
                    node_id=f"node_graph_health_bottleneck_child_{index}",
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                    delivery_stage="BUILD",
                    dispatch_intent={
                        "assignee_employee_id": "emp_frontend_2",
                        "selection_reason": "Seed bottleneck coverage",
                        "dependency_gate_refs": ["tkt_graph_health_shared_dependency"],
                        "selected_by": "test",
                        "wakeup_policy": "default",
                    },
                ),
            },
        )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-bottleneck",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "BOTTLENECK_DETECTED"
    )

    assert finding["affected_nodes"] == ["node_graph_health_shared_dependency"]
    assert finding["metric_value"] == 4


def test_graph_health_report_detects_orphan_subgraph(client):
    workflow_id = "wf_graph_health_orphan"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose orphan subgraphs once closeout exists.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_main_build",
        node_id="node_graph_health_main_build",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_main_closeout",
        node_id="node_graph_health_main_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        delivery_stage="CLOSEOUT",
        parent_ticket_id="tkt_graph_health_main_build",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_orphan_build",
        node_id="node_graph_health_orphan_build",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-orphan",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "ORPHAN_SUBGRAPH"
    )

    assert finding["affected_nodes"] == ["node_graph_health_orphan_build"]


def test_graph_health_report_detects_freeze_spread_too_wide(client):
    workflow_id = "wf_graph_health_freeze_spread"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose advisory freeze spread.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_freeze_target",
        node_id="node_graph_health_freeze_target",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=["node_graph_health_freeze_target"],
        focus_node_ids=["node_graph_health_freeze_target"],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-freeze-spread",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "FREEZE_SPREAD_TOO_WIDE"
    )

    assert finding["affected_nodes"] == ["node_graph_health_freeze_target"]
    assert finding["metric_value"] == 1


def test_graph_health_report_detects_graph_thrashing(client):
    workflow_id = "wf_graph_health_thrashing"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose repeated graph patch churn.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_thrashing_parent",
        node_id="node_graph_health_thrashing_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_thrashing_target",
        node_id="node_graph_health_thrashing_target",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    for patch_index, operation in ((1, "add"), (2, "remove"), (3, "add"), (4, "remove")):
        _seed_graph_patch_applied_event(
            client,
            workflow_id=workflow_id,
            patch_index=patch_index,
            freeze_node_ids=[],
            focus_node_ids=[],
            edge_additions=[
                {
                    "edge_type": "PARENT_OF",
                    "source_node_id": "node_graph_health_thrashing_parent",
                    "target_node_id": "node_graph_health_thrashing_target",
                }
            ]
            if operation == "add"
            else [],
            edge_removals=[
                {
                    "edge_type": "PARENT_OF",
                    "source_node_id": "node_graph_health_thrashing_parent",
                    "target_node_id": "node_graph_health_thrashing_target",
                }
            ]
            if operation == "remove"
            else [],
        )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-thrashing",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "GRAPH_THRASHING"
    )

    assert report["overall_health"] == "CRITICAL"
    assert set(finding["affected_nodes"]) == {
        "node_graph_health_thrashing_parent",
        "node_graph_health_thrashing_target",
    }
    assert finding["metric_value"] == 4


def test_graph_health_report_does_not_flag_graph_thrashing_below_threshold(client):
    workflow_id = "wf_graph_health_thrashing_below_threshold"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should ignore low patch churn.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_thrashing_low",
        node_id="node_graph_health_thrashing_low",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    for patch_index in range(1, 4):
        _seed_graph_patch_applied_event(
            client,
            workflow_id=workflow_id,
            patch_index=patch_index,
            freeze_node_ids=["node_graph_health_thrashing_low"],
        )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-thrashing-below-threshold",
    )

    finding_types = [
        item["finding_type"] for item in snapshot["projection_snapshot"]["graph_health_report"]["findings"]
    ]

    assert "GRAPH_THRASHING" not in finding_types


def test_graph_health_report_detects_ready_node_stale(client, monkeypatch):
    workflow_id = "wf_graph_health_ready_node_stale"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose stale ready nodes.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_stale_ready",
        node_id="node_graph_health_stale_ready",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        graph_health_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T12:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", "tkt_graph_health_stale_ready"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-ready-node-stale",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "READY_NODE_STALE"
    )

    assert finding["severity"] == "WARNING"
    assert finding["affected_nodes"] == ["node_graph_health_stale_ready"]
    assert finding["metric_value"] == 10800


def test_graph_health_report_does_not_flag_ready_node_stale_within_sla(client, monkeypatch):
    workflow_id = "wf_graph_health_ready_node_fresh"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should ignore ready nodes within SLA.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_fresh_ready",
        node_id="node_graph_health_fresh_ready",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        graph_health_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T10:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:30:01+08:00", "tkt_graph_health_fresh_ready"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-ready-node-fresh",
    )

    finding_types = [
        item["finding_type"] for item in snapshot["projection_snapshot"]["graph_health_report"]["findings"]
    ]

    assert "READY_NODE_STALE" not in finding_types


def test_graph_health_report_rejects_malformed_graph_patch_timeline(client):
    workflow_id = "wf_graph_health_bad_patch_timeline"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should fail closed on malformed graph patch payloads.",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        payload_override="malformed-graph-patch",
    )

    with pytest.raises(RuntimeError, match="graph unavailable"):
        graph_health_module.build_graph_health_report(
            client.app.state.repository,
            workflow_id,
        )


def test_graph_health_report_rejects_ready_node_missing_updated_at(client, monkeypatch):
    workflow_id = "wf_graph_health_missing_updated_at"
    ticket_id = "tkt_graph_health_missing_updated_at"
    node_id = "node_graph_health_missing_updated_at"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should fail closed when ready-node timeline fields are missing.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        graph_health_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T12:00:00+08:00"),
    )
    repository = client.app.state.repository
    original_convert = repository._convert_ticket_projection_row

    def _convert_ticket_projection_row_without_updated_at(row):
        converted = original_convert(row)
        if converted["ticket_id"] == ticket_id:
            converted["updated_at"] = None
        return converted

    monkeypatch.setattr(
        repository,
        "_convert_ticket_projection_row",
        _convert_ticket_projection_row_without_updated_at,
    )

    with pytest.raises(RuntimeError, match="graph unavailable"):
        graph_health_module.build_graph_health_report(repository, workflow_id)


def test_graph_health_report_rejects_ready_node_missing_timeout_sla_sec(client, monkeypatch):
    workflow_id = "wf_graph_health_missing_timeout_sla_sec"
    ticket_id = "tkt_graph_health_missing_timeout_sla_sec"
    node_id = "node_graph_health_missing_timeout_sla_sec"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should fail closed when ready-node timeout_sla_sec is missing.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        graph_health_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T12:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET timeout_sla_sec = ?
            WHERE ticket_id = ?
            """,
            (None, ticket_id),
        )

    with pytest.raises(RuntimeError, match="graph unavailable"):
        graph_health_module.build_graph_health_report(repository, workflow_id)


def test_ticket_graph_snapshot_summarizes_board_review_and_incident_blockers(client):
    board_workflow_id = "wf_ticket_graph_board_block"
    _ensure_scoped_workflow(
        client,
        workflow_id=board_workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph board blocker",
    )
    _seed_review_request(client, workflow_id=board_workflow_id)

    board_snapshot = build_ticket_graph_snapshot(client.app.state.repository, board_workflow_id)

    assert board_snapshot.index_summary.blocked_node_ids == ["node_homepage_visual"]
    assert any(
        item.reason_code == "BOARD_REVIEW_OPEN" and item.node_ids == ["node_homepage_visual"]
        for item in board_snapshot.index_summary.blocked_reasons
    )

    incident_workflow_id = "wf_ticket_graph_incident_block"
    incident_ticket_id = "tkt_incident_build"
    incident_node_id = "node_incident_build"
    _ensure_scoped_workflow(
        client,
        workflow_id=incident_workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph incident blocker",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=incident_workflow_id,
        ticket_id=incident_ticket_id,
        node_id=incident_node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(incident_workflow_id, employee_id="emp_frontend_2"),
    )
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"

    incident_snapshot = build_ticket_graph_snapshot(client.app.state.repository, incident_workflow_id)

    assert incident_node_id in incident_snapshot.index_summary.blocked_node_ids
    assert any(
        item.reason_code == "INCIDENT_OPEN" and incident_node_id in item.node_ids
        for item in incident_snapshot.index_summary.blocked_reasons
    )


def test_ceo_shadow_snapshot_uses_ticket_graph_in_flight_index_for_ready_count_and_runtime_gate(client):
    workflow_id = "wf_ticket_graph_snapshot_in_flight"
    ticket_id = "tkt_snapshot_in_flight"
    node_id = "node_snapshot_in_flight"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket graph snapshot in flight",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="SCHEDULER_IDLE_MAINTENANCE",
        trigger_ref="test-ticket-graph-in-flight",
    )

    assert snapshot["controller_state"]["state"] == "WAIT_FOR_RUNTIME"
    assert snapshot["ticket_summary"]["ready_count"] == 0
    assert snapshot["ticket_graph"]["index_summary"]["in_flight_ticket_ids"] == [ticket_id]
