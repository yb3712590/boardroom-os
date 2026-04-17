from __future__ import annotations

from datetime import datetime

import pytest
import app.core.graph_health as graph_health_module
import app.core.runtime_liveness as runtime_liveness_module
from pydantic import ValidationError

from app.contracts.advisory import BoardAdvisorySession, GraphPatch, GraphPatchProposal
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.graph_identity import GraphIdentityResolutionError, resolve_ticket_graph_identity
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.runtime_node_views import (
    RuntimeNodeViewResolutionError,
    resolve_runtime_node_view,
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
    add_nodes: list[dict[str, object]] | None = None,
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
                    "add_nodes": list(add_nodes or []),
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


def _seed_ticket_precondition_event(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    event_type: str,
    idempotency_key: str,
    occurred_at: str,
    reason_code: str = "PROVIDER_REQUIRED_UNAVAILABLE",
) -> None:
    repository = client.app.state.repository
    payload = {
        "ticket_id": ticket_id,
        "node_id": node_id,
    }
    if event_type == "TICKET_EXECUTION_PRECONDITION_BLOCKED":
        payload["reason_code"] = reason_code
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=event_type,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
            causation_id=None,
            correlation_id=workflow_id,
            payload=payload,
            occurred_at=datetime.fromisoformat(occurred_at),
        )
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


def test_graph_patch_contract_accepts_added_placeholder_nodes():
    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": "pa://graph-patch-proposal/adv_add_node@1",
            "workflow_id": "wf_graph_patch_add_node",
            "session_id": "adv_add_node",
            "base_graph_version": "gv_1",
            "proposal_summary": "Add a placeholder node for the new implementation slice.",
            "impact_summary": "Create a planned node under the existing parent and keep its dependency explicit.",
            "add_nodes": [
                {
                    "node_id": "node_placeholder_build",
                    "node_kind": "IMPLEMENTATION",
                    "deliverable_kind": "source_code_delivery",
                    "role_hint": "frontend_engineer_primary",
                    "parent_node_id": "node_existing_parent",
                    "dependency_node_ids": ["node_existing_dependency"],
                }
            ],
            "source_decision_pack_ref": "pa://decision-summary/adv_add_node@1",
            "proposal_hash": "hash-graph-patch-add-node",
        }
    )

    patch = GraphPatch.model_validate(
        {
            "patch_ref": "pa://graph-patch/adv_add_node@1",
            "workflow_id": proposal.workflow_id,
            "session_id": proposal.session_id,
            "proposal_ref": proposal.proposal_ref,
            "base_graph_version": proposal.base_graph_version,
            "add_nodes": [item.model_dump(mode="json") for item in proposal.add_nodes],
            "reason_summary": proposal.proposal_summary,
            "patch_hash": proposal.proposal_hash,
        }
    )

    assert proposal.add_nodes[0].node_id == "node_placeholder_build"
    assert proposal.add_nodes[0].parent_node_id == "node_existing_parent"
    assert proposal.add_nodes[0].dependency_node_ids == ["node_existing_dependency"]
    assert patch.add_nodes[0].deliverable_kind == "source_code_delivery"


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

    with pytest.raises(ValidationError, match="parent_node_id"):
        GraphPatchProposal.model_validate(
            {
                "proposal_ref": "pa://graph-patch-proposal/adv_contract_missing_parent@1",
                "workflow_id": "wf_graph_patch_contract_invalid",
                "session_id": "adv_contract_invalid",
                "base_graph_version": "gv_1",
                "proposal_summary": "Missing parent metadata should fail closed.",
                "impact_summary": "Placeholder nodes must declare their parent edge explicitly.",
                "add_nodes": [
                    {
                        "node_id": "node_missing_parent",
                        "node_kind": "IMPLEMENTATION",
                        "deliverable_kind": "source_code_delivery",
                        "role_hint": "frontend_engineer_primary",
                        "dependency_node_ids": [],
                    }
                ],
                "source_decision_pack_ref": "pa://decision-summary/adv_contract_missing_parent@1",
                "proposal_hash": "hash-graph-patch-contract-missing-parent",
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
            "graph_contract": None,
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


def test_ticket_graph_snapshot_assigns_graph_identity_lanes_for_shared_runtime_node(client):
    workflow_id = "wf_ticket_graph_shared_runtime_node"
    shared_node_id = "node_shared_runtime_review"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Shared runtime nodes should split execution and review graph identities.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_shared_runtime_maker",
        node_id=shared_node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_shared_runtime_checker",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_shared_runtime_checker",
                node_id=shared_node_id,
                role_profile_ref="checker_primary",
                output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
                delivery_stage="CHECK",
                parent_ticket_id="tkt_shared_runtime_maker",
                dispatch_intent={
                    "assignee_employee_id": "emp_checker_1",
                    "selection_reason": "Seed shared runtime checker lane",
                    "dependency_gate_refs": ["tkt_shared_runtime_maker"],
                    "selected_by": "test",
                    "wakeup_policy": "default",
                },
            ),
            "graph_contract": None,
            "ticket_kind": "MAKER_CHECKER_REVIEW",
            "maker_checker_context": {
                "maker_ticket_id": "tkt_shared_runtime_maker",
                "maker_completed_by": "emp_frontend_2",
                "maker_artifact_refs": ["art://delivery/shared-runtime-maker.json"],
                "maker_process_asset_refs": [
                    "SOURCE_CODE_DELIVERY:scd_tkt_shared_runtime_maker@1"
                ],
                "maker_ticket_spec": {
                    "ticket_id": "tkt_shared_runtime_maker",
                    "node_id": shared_node_id,
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
    node_by_graph_id = {node.graph_node_id: node for node in snapshot.nodes}
    review_edge = next(edge for edge in snapshot.edges if edge.edge_type == "REVIEWS")

    assert shared_node_id in node_by_graph_id
    assert f"{shared_node_id}::review" in node_by_graph_id
    assert node_by_graph_id[shared_node_id].graph_lane_kind == "execution"
    assert node_by_graph_id[f"{shared_node_id}::review"].graph_lane_kind == "review"
    assert node_by_graph_id[shared_node_id].runtime_node_id == shared_node_id
    assert node_by_graph_id[f"{shared_node_id}::review"].runtime_node_id == shared_node_id
    assert review_edge.source_graph_node_id == f"{shared_node_id}::review"
    assert review_edge.target_graph_node_id == shared_node_id
    assert review_edge.source_runtime_node_id == shared_node_id
    assert review_edge.target_runtime_node_id == shared_node_id


def test_graph_health_ignores_same_lane_retry_parent_self_edge(client):
    workflow_id = "wf_graph_health_retry_self_edge"
    node_id = "node_graph_health_retry_self_edge"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Retry lineage on the same execution lane should not create a graph-health cycle.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_retry_parent",
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_graph_health_retry_child",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_graph_health_retry_child",
                node_id=node_id,
                role_profile_ref="frontend_engineer_primary",
                output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                delivery_stage="BUILD",
                parent_ticket_id="tkt_graph_health_retry_parent",
            ),
            "graph_contract": {
                "lane_kind": "execution",
            },
        },
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    parent_edges = [
        edge
        for edge in snapshot.edges
        if edge.edge_type == "PARENT_OF"
        and edge.source_graph_node_id == node_id
        and edge.target_graph_node_id == node_id
    ]

    assert parent_edges == []
    report = graph_health_module.build_graph_health_report(
        client.app.state.repository,
        workflow_id=workflow_id,
    )
    assert report.overall_health in {"HEALTHY", "WARNING", "CRITICAL"}


def test_ticket_graph_snapshot_uses_graph_contract_review_lane_without_taxonomy_keywords(client):
    workflow_id = "wf_ticket_graph_contract_review_lane"
    node_id = "node_contract_review_lane"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph identity should trust graph_contract lane_kind before old taxonomy keywords.",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_contract_review_lane",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_contract_review_lane",
                node_id=node_id,
                role_profile_ref="frontend_engineer_primary",
                output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                delivery_stage="CHECK",
            ),
            "graph_contract": {
                "lane_kind": "review",
            },
        },
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    node_by_graph_id = {node.graph_node_id: node for node in snapshot.nodes}

    assert f"{node_id}::review" in node_by_graph_id
    assert node_by_graph_id[f"{node_id}::review"].graph_lane_kind == "review"


def test_resolve_ticket_graph_identity_rejects_missing_graph_contract():
    with pytest.raises(GraphIdentityResolutionError, match="graph_contract"):
        resolve_ticket_graph_identity(
            ticket_id="tkt_missing_graph_contract",
            runtime_node_id="node_missing_graph_contract",
            created_spec={
                "ticket_id": "tkt_missing_graph_contract",
                "node_id": "node_missing_graph_contract",
                "role_profile_ref": "frontend_engineer_primary",
                "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                "delivery_stage": "BUILD",
            },
        )


def test_ticket_graph_snapshot_rejects_non_legacy_ticket_without_graph_contract(client):
    workflow_id = "wf_ticket_graph_missing_contract_non_legacy"
    node_id = "node_missing_contract_non_legacy"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph core should fail closed when a non-legacy ticket is missing graph_contract.",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_missing_contract_non_legacy",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_missing_contract_non_legacy",
                node_id=node_id,
                role_profile_ref="frontend_engineer_primary",
                output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                delivery_stage="BUILD",
            ),
            "graph_contract": None,
        },
    )

    with pytest.raises(GraphIdentityResolutionError, match="graph_contract"):
        build_ticket_graph_snapshot(client.app.state.repository, workflow_id)


def test_ticket_graph_snapshot_prefers_graph_contract_execution_lane_over_review_taxonomy(client):
    workflow_id = "wf_ticket_graph_contract_execution_lane"
    node_id = "node_contract_execution_lane"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph identity should keep execution lane when graph_contract says execution.",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_contract_execution_lane",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_contract_execution_lane",
                node_id=node_id,
                role_profile_ref="checker_primary",
                output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
                delivery_stage="CHECK",
            ),
            "ticket_kind": "MAKER_CHECKER_REVIEW",
            "graph_contract": {
                "lane_kind": "execution",
            },
        },
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    node_by_graph_id = {node.graph_node_id: node for node in snapshot.nodes}

    assert node_id in node_by_graph_id
    assert f"{node_id}::review" not in node_by_graph_id
    assert node_by_graph_id[node_id].graph_lane_kind == "execution"


def test_ticket_graph_snapshot_collapses_rework_back_to_execution_lane(client):
    workflow_id = "wf_ticket_graph_shared_runtime_rework"
    shared_node_id = "node_shared_runtime_rework"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Rework fixes should replace the execution lane ticket without creating a third graph lane.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_shared_runtime_rework_maker",
        node_id=shared_node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_shared_runtime_rework_checker",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_shared_runtime_rework_checker",
                node_id=shared_node_id,
                role_profile_ref="checker_primary",
                output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
                delivery_stage="CHECK",
                parent_ticket_id="tkt_shared_runtime_rework_maker",
                dispatch_intent={
                    "assignee_employee_id": "emp_checker_1",
                    "selection_reason": "Seed shared runtime checker lane for rework coverage",
                    "dependency_gate_refs": ["tkt_shared_runtime_rework_maker"],
                    "selected_by": "test",
                    "wakeup_policy": "default",
                },
            ),
            "graph_contract": None,
            "ticket_kind": "MAKER_CHECKER_REVIEW",
            "maker_checker_context": {
                "maker_ticket_id": "tkt_shared_runtime_rework_maker",
                "maker_completed_by": "emp_frontend_2",
                "maker_ticket_spec": {
                    "ticket_id": "tkt_shared_runtime_rework_maker",
                    "node_id": shared_node_id,
                    "role_profile_ref": "frontend_engineer_primary",
                    "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                    "output_schema_version": 1,
                    "delivery_stage": "BUILD",
                },
                "original_review_request": {
                    "review_type": "INTERNAL_DELIVERY_REVIEW",
                },
            },
        },
    )
    _seed_ticket_created_event(
        client,
        workflow_id=workflow_id,
        idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_shared_runtime_rework_fix",
        ticket_payload={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id="tkt_shared_runtime_rework_fix",
                node_id=shared_node_id,
                role_profile_ref="frontend_engineer_primary",
                output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
                delivery_stage="BUILD",
                parent_ticket_id="tkt_shared_runtime_rework_checker",
            ),
            "graph_contract": None,
            "ticket_kind": "MAKER_REWORK_FIX",
            "maker_checker_context": {
                "maker_ticket_id": "tkt_shared_runtime_rework_maker",
                "maker_completed_by": "emp_frontend_2",
                "maker_ticket_spec": {
                    "ticket_id": "tkt_shared_runtime_rework_maker",
                    "node_id": shared_node_id,
                    "role_profile_ref": "frontend_engineer_primary",
                    "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                    "output_schema_version": 1,
                    "delivery_stage": "BUILD",
                },
                "original_review_request": {
                    "review_type": "INTERNAL_DELIVERY_REVIEW",
                },
                "checker_ticket_id": "tkt_shared_runtime_rework_checker",
                "blocking_finding_refs": ["finding_shared_runtime_rework"],
                "required_fixes": [
                    {
                        "finding_id": "finding_shared_runtime_rework",
                        "headline": "Shared runtime node still needs a rework pass.",
                        "required_action": "Apply the blocking fix on the execution lane.",
                        "severity": "high",
                        "category": "delivery",
                    }
                ],
                "rework_fingerprint": "mkrw:shared-runtime-rework",
                "rework_streak_count": 1,
            },
        },
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    lane_nodes = [
        node for node in snapshot.nodes if node.runtime_node_id == shared_node_id
    ]
    node_by_graph_id = {node.graph_node_id: node for node in lane_nodes}

    assert len(lane_nodes) == 2
    assert node_by_graph_id[shared_node_id].graph_lane_kind == "execution"
    assert node_by_graph_id[shared_node_id].ticket_id == "tkt_shared_runtime_rework_fix"
    assert node_by_graph_id[f"{shared_node_id}::review"].graph_lane_kind == "review"
    assert node_by_graph_id[f"{shared_node_id}::review"].ticket_id == "tkt_shared_runtime_rework_checker"
    assert not any(
        edge.source_graph_node_id == edge.target_graph_node_id
        for edge in snapshot.edges
        if edge.edge_type in {"PARENT_OF", "DEPENDS_ON", "REVIEWS"}
    )


def test_ticket_graph_snapshot_materializes_placeholder_nodes_without_marking_them_ready(client):
    workflow_id = "wf_ticket_graph_placeholder_node"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph-only placeholder nodes should be visible without entering the runtime ready queue.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_parent",
        node_id="node_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_dependency",
        node_id="node_placeholder_dependency",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_placeholder_build"],
        add_nodes=[
            {
                "node_id": "node_placeholder_build",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_placeholder_parent",
                "dependency_node_ids": ["node_placeholder_dependency"],
            }
        ],
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    node_by_graph_id = {node.graph_node_id: node for node in snapshot.nodes}
    placeholder = node_by_graph_id["node_placeholder_build"]
    edge_tuples = {
        (
            edge.edge_type,
            edge.source_graph_node_id,
            edge.target_graph_node_id,
            edge.source_ticket_id,
            edge.target_ticket_id,
        )
        for edge in snapshot.edges
    }

    assert placeholder.is_placeholder is True
    assert placeholder.ticket_id is None
    assert placeholder.runtime_node_id is None
    assert placeholder.graph_lane_kind == "execution"
    assert placeholder.node_status == "PLANNED"
    assert placeholder.graph_node_id not in snapshot.index_summary.ready_graph_node_ids
    assert "node_placeholder_build" not in snapshot.index_summary.ready_node_ids
    assert (
        "PARENT_OF",
        "node_placeholder_parent",
        "node_placeholder_build",
        "tkt_placeholder_parent",
        None,
    ) in edge_tuples
    assert (
        "DEPENDS_ON",
        "node_placeholder_dependency",
        "node_placeholder_build",
        "tkt_placeholder_dependency",
        None,
    ) in edge_tuples


def test_ticket_graph_snapshot_absorbs_placeholder_node_when_real_ticket_is_created(client):
    workflow_id = "wf_ticket_graph_placeholder_absorbed"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="A graph-only placeholder should disappear once a real ticket is created for the same node.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_absorb_parent",
        node_id="node_placeholder_absorb_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_placeholder_absorb"],
        add_nodes=[
            {
                "node_id": "node_placeholder_absorb",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_placeholder_absorb_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    placeholder_snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    assert next(
        node for node in placeholder_snapshot.nodes if node.graph_node_id == "node_placeholder_absorb"
    ).is_placeholder is True

    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_absorb_real",
        node_id="node_placeholder_absorb",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
        parent_ticket_id="tkt_placeholder_absorb_parent",
    )

    snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    materialized_nodes = [
        node for node in snapshot.nodes if node.graph_node_id == "node_placeholder_absorb"
    ]

    assert len(materialized_nodes) == 1
    assert materialized_nodes[0].is_placeholder is False
    assert materialized_nodes[0].ticket_id == "tkt_placeholder_absorb_real"
    assert materialized_nodes[0].runtime_node_id == "node_placeholder_absorb"
    assert (
        client.app.state.repository.get_planned_placeholder_projection(
            workflow_id,
            "node_placeholder_absorb",
        )
        is None
    )


def test_ticket_graph_snapshot_persists_placeholder_projection_until_real_ticket_exists(client):
    workflow_id = "wf_ticket_graph_placeholder_projection"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Placeholder projection should persist graph-only execution placeholders.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_projection_parent",
        node_id="node_placeholder_projection_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_placeholder_projection_target"],
        add_nodes=[
            {
                "node_id": "node_placeholder_projection_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_placeholder_projection_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    placeholder_projection = client.app.state.repository.get_planned_placeholder_projection(
        workflow_id,
        "node_placeholder_projection_target",
    )

    assert placeholder_projection is not None
    assert placeholder_projection["graph_node_id"] == "node_placeholder_projection_target"
    assert placeholder_projection["status"] == "PLANNED"
    assert placeholder_projection["reason_code"] == "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
    assert placeholder_projection["open_incident_id"] is None
    assert placeholder_projection["materialization_hint"] == "create_ticket"


def test_runtime_node_view_fail_closes_when_placeholder_projection_is_missing(client):
    workflow_id = "wf_runtime_node_view_missing_placeholder_projection"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Runtime node views should fail closed when placeholder projection is missing.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runtime_node_view_missing_placeholder_parent",
        node_id="node_runtime_node_view_missing_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_runtime_node_view_missing_placeholder_target"],
        add_nodes=[
            {
                "node_id": "node_runtime_node_view_missing_placeholder_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_runtime_node_view_missing_placeholder_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM planned_placeholder_projection
            WHERE workflow_id = ? AND node_id = ?
            """,
            (workflow_id, "node_runtime_node_view_missing_placeholder_target"),
        )

    with pytest.raises(RuntimeNodeViewResolutionError, match="planned_placeholder_projection"):
        resolve_runtime_node_view(
            repository,
            workflow_id,
            "node_runtime_node_view_missing_placeholder_target",
        )


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


def test_graph_health_report_exposes_affected_graph_node_ids(client, monkeypatch):
    workflow_id = "wf_graph_health_graph_identity_field"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose graph node ids alongside runtime node ids.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_graph_identity_field",
        node_id="node_graph_health_graph_identity_field",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        runtime_liveness_module,
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
            ("2026-04-16T09:00:00+08:00", "tkt_graph_health_graph_identity_field"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-graph-identity-field",
    )

    finding = next(
        item
        for item in snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
        if item["finding_type"] == "READY_NODE_STALE"
    )

    assert finding["affected_nodes"] == ["node_graph_health_graph_identity_field"]
    assert finding["affected_graph_node_ids"] == ["node_graph_health_graph_identity_field"]


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


def test_graph_health_report_detects_orphan_placeholder_node_without_runtime_node_ids(client):
    workflow_id = "wf_graph_health_orphan_placeholder"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Placeholder nodes should still participate in structural graph health checks.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_placeholder_root",
        node_id="node_graph_health_placeholder_root",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_placeholder_closeout",
        node_id="node_graph_health_placeholder_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        delivery_stage="CLOSEOUT",
        parent_ticket_id="tkt_graph_health_placeholder_root",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_graph_health_placeholder_orphan"],
        add_nodes=[
            {
                "node_id": "node_graph_health_placeholder_orphan",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_graph_health_placeholder_root",
                "dependency_node_ids": [],
            }
        ],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-orphan-placeholder",
    )

    report = snapshot["projection_snapshot"]["graph_health_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "ORPHAN_SUBGRAPH"
    )

    assert finding["affected_nodes"] == []
    assert finding["affected_graph_node_ids"] == ["node_graph_health_placeholder_orphan"]


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


def test_runtime_liveness_report_detects_ready_node_stale(client, monkeypatch):
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
        runtime_liveness_module,
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

    report = snapshot["projection_snapshot"]["runtime_liveness_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "READY_NODE_STALE"
    )

    assert finding["severity"] == "WARNING"
    assert finding["affected_nodes"] == ["node_graph_health_stale_ready"]
    assert finding["metric_value"] == 10800


def test_runtime_liveness_report_detects_queue_starvation(client, monkeypatch):
    workflow_id = "wf_graph_health_queue_starvation"
    ticket_id = "tkt_graph_health_queue_starvation"
    node_id = "node_graph_health_queue_starvation"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose starving ready queues.",
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
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T13:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", ticket_id),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-queue-starvation",
    )

    report = snapshot["projection_snapshot"]["runtime_liveness_report"]
    finding = next(
        item for item in report["findings"] if item["finding_type"] == "QUEUE_STARVATION"
    )

    assert finding["severity"] == "CRITICAL"
    assert finding["affected_nodes"] == [node_id]
    assert finding["metric_value"] == 14400


def test_runtime_liveness_report_ignores_queue_starvation_when_work_is_in_flight(client, monkeypatch):
    workflow_id = "wf_graph_health_queue_starvation_in_flight"
    ready_ticket_id = "tkt_graph_health_queue_starvation_ready"
    ready_node_id = "node_graph_health_queue_starvation_ready"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should ignore ready queue starvation while runtime is still active.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ready_ticket_id,
        node_id=ready_node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_queue_starvation_executing",
        node_id="node_graph_health_queue_starvation_executing",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T13:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", ready_ticket_id),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-queue-starvation-in-flight",
    )
    finding_types = [
        item["finding_type"]
        for item in snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
    ]

    assert "QUEUE_STARVATION" not in finding_types


def test_runtime_liveness_report_detects_ready_blocked_thrashing(client, monkeypatch):
    workflow_id = "wf_graph_health_ready_blocked_thrashing"
    ticket_id = "tkt_graph_health_ready_blocked_thrashing"
    node_id = "node_graph_health_ready_blocked_thrashing"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose ready blocked thrashing from explicit event truth.",
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
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T10:06:00+08:00"),
    )
    for index, event_type in enumerate(
        (
            "TICKET_EXECUTION_PRECONDITION_BLOCKED",
            "TICKET_EXECUTION_PRECONDITION_CLEARED",
            "TICKET_EXECUTION_PRECONDITION_BLOCKED",
            "TICKET_EXECUTION_PRECONDITION_CLEARED",
            "TICKET_EXECUTION_PRECONDITION_BLOCKED",
            "TICKET_EXECUTION_PRECONDITION_CLEARED",
        ),
        start=1,
    ):
        _seed_ticket_precondition_event(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            event_type=event_type,
            idempotency_key=f"test-ready-blocked-thrashing:{workflow_id}:{index}",
            occurred_at=f"2026-04-16T10:0{index}:00+08:00",
        )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-ready-blocked-thrashing",
    )

    report = snapshot["projection_snapshot"]["runtime_liveness_report"]
    finding = next(
        item
        for item in report["findings"]
        if item["finding_type"] == "READY_BLOCKED_THRASHING"
    )

    assert finding["severity"] == "WARNING"
    assert finding["affected_nodes"] == [node_id]
    assert finding["metric_value"] == 3


def test_runtime_liveness_report_ignores_ready_blocked_thrashing_below_threshold(client, monkeypatch):
    workflow_id = "wf_graph_health_ready_blocked_thrashing_low"
    ticket_id = "tkt_graph_health_ready_blocked_thrashing_low"
    node_id = "node_graph_health_ready_blocked_thrashing_low"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should ignore low ready blocked oscillation.",
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
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T10:05:00+08:00"),
    )
    for index, event_type in enumerate(
        (
            "TICKET_EXECUTION_PRECONDITION_BLOCKED",
            "TICKET_EXECUTION_PRECONDITION_CLEARED",
            "TICKET_EXECUTION_PRECONDITION_BLOCKED",
            "TICKET_EXECUTION_PRECONDITION_CLEARED",
        ),
        start=1,
    ):
        _seed_ticket_precondition_event(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            event_type=event_type,
            idempotency_key=f"test-ready-blocked-thrashing-low:{workflow_id}:{index}",
            occurred_at=f"2026-04-16T10:0{index}:00+08:00",
        )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-ready-blocked-thrashing-low",
    )
    finding_types = [
        item["finding_type"]
        for item in snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
    ]

    assert "READY_BLOCKED_THRASHING" not in finding_types


def test_runtime_liveness_report_detects_cross_version_sla_breach(client, monkeypatch):
    workflow_id = "wf_graph_health_cross_version_sla"
    ticket_id = "tkt_graph_health_cross_version_sla"
    node_id = "node_graph_health_cross_version_sla"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should expose blocked nodes that breach SLA across graph versions.",
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
    _seed_ticket_precondition_event(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        event_type="TICKET_EXECUTION_PRECONDITION_BLOCKED",
        idempotency_key=f"test-cross-version-sla-blocked:{workflow_id}",
        occurred_at="2026-04-16T09:00:00+08:00",
    )
    monkeypatch.setattr(
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T12:30:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", ticket_id),
        )
    for patch_index in range(1, 4):
        _seed_graph_patch_applied_event(
            client,
            workflow_id=workflow_id,
            patch_index=patch_index,
            freeze_node_ids=[node_id],
            focus_node_ids=[node_id],
            occurred_at=f"2026-04-16T09:1{patch_index}:00+08:00",
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-cross-version-sla",
    )

    report = snapshot["projection_snapshot"]["runtime_liveness_report"]
    finding = next(
        item
        for item in report["findings"]
        if item["finding_type"] == "CROSS_VERSION_SLA_BREACH"
    )

    assert finding["severity"] == "CRITICAL"
    assert finding["affected_nodes"] == [node_id]
    assert finding["metric_value"] == 3


def test_runtime_liveness_report_ignores_cross_version_sla_breach_below_version_threshold(client, monkeypatch):
    workflow_id = "wf_graph_health_cross_version_sla_low"
    ticket_id = "tkt_graph_health_cross_version_sla_low"
    node_id = "node_graph_health_cross_version_sla_low"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should ignore blocked nodes below the cross version threshold.",
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
    _seed_ticket_precondition_event(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        event_type="TICKET_EXECUTION_PRECONDITION_BLOCKED",
        idempotency_key=f"test-cross-version-sla-low-blocked:{workflow_id}",
        occurred_at="2026-04-16T09:00:00+08:00",
    )
    monkeypatch.setattr(
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T12:30:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", ticket_id),
        )
    for patch_index in range(1, 3):
        _seed_graph_patch_applied_event(
            client,
            workflow_id=workflow_id,
            patch_index=patch_index,
            freeze_node_ids=[node_id],
            focus_node_ids=[node_id],
            occurred_at=f"2026-04-16T09:1{patch_index}:00+08:00",
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-cross-version-sla-low",
    )
    finding_types = [
        item["finding_type"]
        for item in snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
    ]

    assert "CROSS_VERSION_SLA_BREACH" not in finding_types


def test_runtime_liveness_report_does_not_flag_ready_node_stale_within_sla(client, monkeypatch):
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
        runtime_liveness_module,
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
        item["finding_type"]
        for item in snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
    ]

    assert "READY_NODE_STALE" not in finding_types


def test_runtime_liveness_report_uses_policy_override_for_ready_node_stale_threshold(client, monkeypatch):
    workflow_id = "wf_graph_health_policy_override_ready_node_stale"
    ticket_id = "tkt_graph_health_policy_override_ready_node_stale"
    node_id = "node_graph_health_policy_override_ready_node_stale"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health policy override should drive ready-node stale behavior.",
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
        runtime_liveness_module,
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
            ("2026-04-16T09:00:00+08:00", ticket_id),
        )

    import importlib

    graph_health_policy_module = importlib.import_module("app.core.graph_health_policy")
    policy = graph_health_policy_module.DEFAULT_GRAPH_HEALTH_POLICY.model_copy(
        update={
            "ready_node_stale_multiplier": 7,
        }
    )

    report = runtime_liveness_module.build_runtime_liveness_report(
        repository,
        workflow_id,
        policy=policy,
    )
    finding_types = [item.finding_type for item in report.findings]

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


def test_runtime_liveness_report_rejects_ready_node_missing_updated_at(client, monkeypatch):
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
        runtime_liveness_module,
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

    with pytest.raises(RuntimeError, match="runtime liveness unavailable"):
        runtime_liveness_module.build_runtime_liveness_report(repository, workflow_id)


def test_runtime_liveness_report_rejects_ready_node_missing_timeout_sla_sec(client, monkeypatch):
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
        runtime_liveness_module,
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

    with pytest.raises(RuntimeError, match="runtime liveness unavailable"):
        runtime_liveness_module.build_runtime_liveness_report(repository, workflow_id)


def test_runtime_liveness_report_rejects_ready_node_missing_version_for_queue_starvation(client, monkeypatch):
    workflow_id = "wf_graph_health_missing_version"
    ticket_id = "tkt_graph_health_missing_version"
    node_id = "node_graph_health_missing_version"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health should fail closed when queue starvation lacks projection version truth.",
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
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T13:00:00+08:00"),
    )
    repository = client.app.state.repository
    original_convert = repository._convert_ticket_projection_row

    def _convert_ticket_projection_row_without_version(row):
        converted = original_convert(row)
        if converted["ticket_id"] == ticket_id:
            converted["version"] = None
        return converted

    monkeypatch.setattr(
        repository,
        "_convert_ticket_projection_row",
        _convert_ticket_projection_row_without_version,
    )

    with pytest.raises(RuntimeError, match="runtime liveness unavailable"):
        runtime_liveness_module.build_runtime_liveness_report(repository, workflow_id)


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
