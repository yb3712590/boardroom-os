from __future__ import annotations

from app.core.ceo_execution_presets import (
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
)
from app.core.output_schemas import ARCHITECTURE_BRIEF_SCHEMA_REF
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
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
