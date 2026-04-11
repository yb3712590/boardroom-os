from __future__ import annotations

from app.core.ceo_execution_presets import (
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
    PROJECT_INIT_SCOPE_NODE_ID,
)
from app.core.output_schemas import ARCHITECTURE_BRIEF_SCHEMA_REF, CONSENSUS_DOCUMENT_SCHEMA_REF
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
    STANDARD_LEGACY_SCOPE_CHAIN,
    build_project_init_kickoff_spec,
    resolve_workflow_progression_adapter,
)


def test_resolve_workflow_progression_adapter_uses_profile_specific_adapter() -> None:
    assert (
        resolve_workflow_progression_adapter({"workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"})
        == AUTOPILOT_GOVERNANCE_CHAIN
    )
    assert resolve_workflow_progression_adapter({"workflow_profile": "STANDARD"}) == STANDARD_LEGACY_SCOPE_CHAIN


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
    assert kickoff["role_profile_ref"] == "frontend_engineer_primary"
    assert kickoff["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF


def test_build_project_init_kickoff_spec_uses_legacy_scope_kickoff_for_standard() -> None:
    kickoff = build_project_init_kickoff_spec(
        {
            "workflow_id": "wf_standard_progression",
            "workflow_profile": "STANDARD",
            "north_star_goal": "Build a library management system",
            "title": "Build a library management system",
        }
    )

    assert kickoff["adapter_id"] == STANDARD_LEGACY_SCOPE_CHAIN
    assert kickoff["node_id"] == PROJECT_INIT_SCOPE_NODE_ID
    assert kickoff["role_profile_ref"] == "ui_designer_primary"
    assert kickoff["output_schema_ref"] == CONSENSUS_DOCUMENT_SCHEMA_REF
