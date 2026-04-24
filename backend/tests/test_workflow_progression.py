from __future__ import annotations

from app.core.ceo_execution_presets import (
    PROJECT_INIT_ARCHITECTURE_SEGMENT_IDS,
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
    build_project_init_architecture_segment_artifact_ref,
    build_project_init_architecture_segment_ticket_id,
)
from app.core.output_schemas import ARCHITECTURE_BRIEF_SCHEMA_REF, ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_REF
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
    build_project_init_architecture_brief_ticket_specs,
    build_project_init_kickoff_spec,
    resolve_workflow_progression_adapter,
    select_governance_role_and_assignee,
)


def test_resolve_workflow_progression_adapter_uses_profile_specific_adapter() -> None:
    assert (
        resolve_workflow_progression_adapter({"workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"})
        == AUTOPILOT_GOVERNANCE_CHAIN
    )
    assert resolve_workflow_progression_adapter({"workflow_profile": "STANDARD"}) == AUTOPILOT_GOVERNANCE_CHAIN


def test_build_project_init_kickoff_spec_uses_governance_kickoff_for_autopilot() -> None:
    kickoff = build_project_init_kickoff_spec(
        {
            "workflow_id": "wf_autopilot_progression",
            "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
            "north_star_goal": "Build a library management system",
            "title": "Build a library management system",
        }
    )

    assert kickoff["adapter_id"] == AUTOPILOT_GOVERNANCE_CHAIN
    assert kickoff["node_id"] == PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID
    assert kickoff["role_profile_ref"] == "architect_primary"
    assert kickoff["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert "catalog-visibility contract" in kickoff["summary"]
    assert "availability lookup contract" in kickoff["summary"]
    assert "Remove action rules" in kickoff["summary"]


def test_build_project_init_kickoff_spec_uses_governance_kickoff_for_standard() -> None:
    kickoff = build_project_init_kickoff_spec(
        {
            "workflow_id": "wf_standard_progression",
            "workflow_profile": "STANDARD",
            "north_star_goal": "Build a library management system",
            "title": "Build a library management system",
        }
    )

    assert kickoff["adapter_id"] == AUTOPILOT_GOVERNANCE_CHAIN
    assert kickoff["node_id"] == PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID
    assert kickoff["role_profile_ref"] == "architect_primary"
    assert kickoff["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert "catalog-visibility contract" in kickoff["summary"]
    assert "availability lookup contract" in kickoff["summary"]
    assert "Remove action rules" in kickoff["summary"]


def test_build_project_init_architecture_brief_ticket_specs_splits_kickoff_into_segments() -> None:
    workflow_id = "wf_architecture_segments"
    board_brief_ref = f"art://project-init/{workflow_id}/board-brief.md"

    specs = build_project_init_architecture_brief_ticket_specs(
        {
            "workflow_id": workflow_id,
            "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
            "north_star_goal": "Build a library management system",
            "title": "Build a library management system",
        },
        board_brief_artifact_ref=board_brief_ref,
    )

    segment_specs = [spec for spec in specs if spec["output_schema_ref"] == ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_REF]
    aggregator_spec = specs[-1]
    segment_ticket_ids = [
        build_project_init_architecture_segment_ticket_id(workflow_id, segment_id)
        for segment_id in PROJECT_INIT_ARCHITECTURE_SEGMENT_IDS
    ]
    segment_artifact_refs = [
        build_project_init_architecture_segment_artifact_ref(ticket_id)
        for ticket_id in segment_ticket_ids
    ]

    assert len(specs) == 5
    assert [spec["ticket_id"] for spec in segment_specs] == segment_ticket_ids
    assert all(spec["role_profile_ref"] == "architect_primary" for spec in segment_specs)
    assert all(spec["output_schema_version"] == 1 for spec in segment_specs)
    assert aggregator_spec["node_id"] == PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID
    assert aggregator_spec["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert aggregator_spec["dispatch_intent"]["dependency_gate_refs"] == segment_ticket_ids
    assert aggregator_spec["input_artifact_refs"] == [board_brief_ref, *segment_artifact_refs]
    assert "synthesize the final architecture_brief" in aggregator_spec["acceptance_criteria"][0]


def test_select_governance_role_and_assignee_requires_architect_for_architecture_brief() -> None:
    role_profile_ref, assignee_employee_id = select_governance_role_and_assignee(
        [
            {
                "employee_id": "emp_frontend_2",
                "state": "ACTIVE",
                "role_type": "frontend_engineer",
                "role_profile_refs": ["frontend_engineer_primary"],
            }
        ],
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
    )

    assert role_profile_ref == "architect_primary"
    assert assignee_employee_id is None
