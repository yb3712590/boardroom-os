from __future__ import annotations

from app.core.ceo_execution_presets import (
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
)
from app.core.output_schemas import ARCHITECTURE_BRIEF_SCHEMA_REF
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
    ProgressionActionType,
    ProgressionPolicy,
    ProgressionSnapshot,
    build_action_metadata,
    build_project_init_kickoff_spec,
    decide_next_actions,
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


def _minimal_progression_snapshot(**overrides) -> ProgressionSnapshot:
    base = {
        "workflow_id": "wf_policy_contract",
        "graph_version": "gv_42",
        "node_refs": ["graph:node_b", "graph:node_a"],
        "ticket_refs": ["ticket_b", "ticket_a"],
        "ready_ticket_ids": [],
        "ready_node_refs": [],
        "blocked_ticket_ids": [],
        "blocked_node_refs": [],
        "in_flight_ticket_ids": [],
        "in_flight_node_refs": [],
        "incidents": [],
        "approvals": [],
        "actor_availability": {"available_actor_refs": ["actor_b", "actor_a"]},
        "provider_availability": {"healthy_provider_refs": ["provider_b", "provider_a"]},
    }
    base.update(overrides)
    return ProgressionSnapshot.model_validate(base)


def test_decide_next_actions_returns_stable_wait_for_open_blockers() -> None:
    snapshot = _minimal_progression_snapshot(
        incidents=[{"incident_id": "inc_b", "node_ref": "graph:node_b"}],
        approvals=[{"approval_id": "appr_a", "node_ref": "graph:node_a"}],
        in_flight_ticket_ids=["ticket_c"],
        in_flight_node_refs=["graph:node_c"],
    )
    policy = ProgressionPolicy(policy_ref="policy:round8a")

    first = [item.model_dump(mode="json") for item in decide_next_actions(snapshot, policy)]
    second = [item.model_dump(mode="json") for item in decide_next_actions(snapshot, policy)]

    assert first == second
    assert first == [
        {
            "action_type": "WAIT",
            "metadata": {
                "reason_code": "progression.wait_for_blockers",
                "idempotency_key": first[0]["metadata"]["idempotency_key"],
                "source_graph_version": "gv_42",
                "affected_node_refs": ["graph:node_a", "graph:node_b", "graph:node_c"],
                "expected_state_transition": "WAITING_ON_BLOCKERS",
                "policy_ref": "policy:round8a",
            },
            "payload": {
                "wake_condition": "approval_or_incident_or_in_flight_resolved",
                "blocked_by": {
                    "approval_refs": ["appr_a"],
                    "incident_refs": ["inc_b"],
                    "in_flight_ticket_ids": ["ticket_c"],
                },
            },
        }
    ]
    assert first[0]["metadata"]["idempotency_key"].startswith(
        "progression:WAIT:gv_42:policy:round8a:"
    )


def test_decide_next_actions_returns_minimal_create_ticket_candidate() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8a",
            "create_ticket_candidates": [
                {
                    "candidate_ref": "candidate:governance:a",
                    "node_ref": "graph:governance_a",
                    "ticket_payload": {
                        "workflow_id": "wf_policy_contract",
                        "node_id": "node_governance_a",
                        "summary": "Prepare the next governance document.",
                    },
                }
            ],
        }
    )

    proposals = [item.model_dump(mode="json") for item in decide_next_actions(snapshot, policy)]

    assert proposals == [
        {
            "action_type": "CREATE_TICKET",
            "metadata": {
                "reason_code": "progression.create_ticket_candidate",
                "idempotency_key": proposals[0]["metadata"]["idempotency_key"],
                "source_graph_version": "gv_42",
                "affected_node_refs": ["graph:governance_a"],
                "expected_state_transition": "TICKET_CREATED",
                "policy_ref": "policy:round8a",
            },
            "payload": {
                "candidate_ref": "candidate:governance:a",
                "ticket_payload": {
                    "workflow_id": "wf_policy_contract",
                    "node_id": "node_governance_a",
                    "summary": "Prepare the next governance document.",
                },
            },
        }
    ]


def test_decide_next_actions_returns_stable_no_action_without_candidates() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy(
        policy_ref="policy:round8a",
        no_action_reason_code="progression.no_structured_candidate",
    )

    first = [item.model_dump(mode="json") for item in decide_next_actions(snapshot, policy)]
    second = [item.model_dump(mode="json") for item in decide_next_actions(snapshot, policy)]

    assert first == second
    assert first[0]["action_type"] == "NO_ACTION"
    assert first[0]["metadata"] == {
        "reason_code": "progression.no_structured_candidate",
        "idempotency_key": first[0]["metadata"]["idempotency_key"],
        "source_graph_version": "gv_42",
        "affected_node_refs": [],
        "expected_state_transition": "NO_STATE_CHANGE",
        "policy_ref": "policy:round8a",
    }
    assert first[0]["payload"] == {"reason": "No structured policy action is currently eligible."}


def test_action_metadata_is_stable_for_all_round8a_action_types() -> None:
    expected_transitions = {
        ProgressionActionType.CREATE_TICKET: "TICKET_CREATED",
        ProgressionActionType.WAIT: "WAITING_ON_BLOCKERS",
        ProgressionActionType.REWORK: "REWORK_REQUESTED",
        ProgressionActionType.CLOSEOUT: "CLOSEOUT_REQUESTED",
        ProgressionActionType.INCIDENT: "INCIDENT_OPENED",
        ProgressionActionType.NO_ACTION: "NO_STATE_CHANGE",
    }

    for action_type, expected_transition in expected_transitions.items():
        first = build_action_metadata(
            action_type=action_type,
            reason_code=f"reason.{action_type.value.lower()}",
            source_graph_version="gv_42",
            affected_node_refs=["graph:node_b", "graph:node_a", "graph:node_b"],
            expected_state_transition=expected_transition,
            policy_ref="policy:round8a",
            idempotency_components={
                "zeta": ["ticket_b", "ticket_a"],
                "alpha": {"node_refs": ["graph:node_b", "graph:node_a"]},
            },
        )
        second = build_action_metadata(
            action_type=action_type,
            reason_code=f"reason.{action_type.value.lower()}",
            source_graph_version="gv_42",
            affected_node_refs=["graph:node_a", "graph:node_b"],
            expected_state_transition=expected_transition,
            policy_ref="policy:round8a",
            idempotency_components={
                "alpha": {"node_refs": ["graph:node_a", "graph:node_b"]},
                "zeta": ["ticket_a", "ticket_b"],
            },
        )

        assert first == second
        assert first.reason_code == f"reason.{action_type.value.lower()}"
        assert first.source_graph_version == "gv_42"
        assert first.affected_node_refs == ["graph:node_a", "graph:node_b"]
        assert first.expected_state_transition == expected_transition
        assert first.policy_ref == "policy:round8a"
        assert first.idempotency_key.startswith(
            f"progression:{action_type.value}:gv_42:policy:round8a:"
        )
