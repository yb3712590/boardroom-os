from __future__ import annotations

from app.core.ceo_execution_presets import (
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
)
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
    ProgressionActionType,
    ProgressionPolicy,
    ProgressionSnapshot,
    build_action_metadata,
    build_project_init_kickoff_spec,
    decide_next_actions,
    evaluate_progression_graph,
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
                "reason_code": "progression.wait.open_approval",
                "idempotency_key": first[0]["metadata"]["idempotency_key"],
                "source_graph_version": "gv_42",
                "affected_node_refs": ["graph:node_a", "graph:node_b", "graph:node_c"],
                "expected_state_transition": "WAITING_ON_BLOCKERS",
                "policy_ref": "policy:round8a",
            },
            "payload": {
                "wake_condition": "approval_resolved",
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


def test_policy_effective_graph_uses_replaces_and_ignores_inactive_edges() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_parent",
                "ticket_id": "ticket_parent",
                "ticket_status": "COMPLETED",
                "node_status": "COMPLETED",
            },
            {
                "node_ref": "graph:node_old",
                "ticket_id": "ticket_old",
                "ticket_status": "PENDING",
                "node_status": "SUPERSEDED",
            },
            {
                "node_ref": "graph:node_new",
                "ticket_id": "ticket_new",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
            {
                "node_ref": "graph:node_cancelled",
                "ticket_id": "ticket_cancelled",
                "ticket_status": "CANCELLED",
                "node_status": "CANCELLED",
            },
        ],
        graph_edges=[
            {
                "edge_type": "REPLACES",
                "source_node_ref": "graph:node_new",
                "target_node_ref": "graph:node_old",
                "source_ticket_id": "ticket_new",
                "target_ticket_id": "ticket_old",
            },
            {
                "edge_type": "DEPENDS_ON",
                "source_node_ref": "graph:node_cancelled",
                "target_node_ref": "graph:node_new",
                "source_ticket_id": "ticket_cancelled",
                "target_ticket_id": "ticket_new",
            },
        ],
        replacements=[
            {
                "old_node_ref": "graph:node_old",
                "new_node_ref": "graph:node_new",
                "old_ticket_id": "ticket_old",
                "new_ticket_id": "ticket_new",
            }
        ],
        superseded_refs=["graph:node_old", "ticket_old"],
        cancelled_refs=["graph:node_cancelled", "ticket_cancelled"],
    )

    evaluation = evaluate_progression_graph(snapshot)

    assert evaluation.current_ticket_ids_by_node_ref["graph:node_new"] == "ticket_new"
    assert "graph:node_old" not in evaluation.effective_node_refs
    assert "graph:node_cancelled" not in evaluation.effective_node_refs
    assert evaluation.effective_edges == []
    assert evaluation.ready_ticket_ids == ["ticket_new"]
    assert "ticket_old" not in evaluation.ready_ticket_ids
    assert "ticket_cancelled" not in evaluation.completed_ticket_ids


def test_policy_runtime_pointer_selects_current_and_missing_pointer_blocks_reduction() -> None:
    runtime_pointer_snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_current",
                "ticket_id": "ticket_current",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
            {
                "node_ref": "graph:node_current",
                "ticket_id": "ticket_late_old",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
        ],
        runtime_nodes=[
            {
                "node_ref": "graph:node_current",
                "node_id": "runtime:node_current",
                "latest_ticket_id": "ticket_current",
                "status": "PENDING",
            }
        ],
    )
    missing_pointer_snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_ambiguous",
                "ticket_id": "ticket_old",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
            {
                "node_ref": "graph:node_ambiguous",
                "ticket_id": "ticket_newer_late_output",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
        ]
    )

    runtime_evaluation = evaluate_progression_graph(runtime_pointer_snapshot)
    missing_pointer_evaluation = evaluate_progression_graph(missing_pointer_snapshot)
    missing_pointer_proposal = decide_next_actions(
        missing_pointer_snapshot,
        ProgressionPolicy(policy_ref="policy:round8b"),
    )[0]

    assert runtime_evaluation.current_ticket_ids_by_node_ref == {
        "graph:node_current": "ticket_current"
    }
    assert runtime_evaluation.ready_ticket_ids == ["ticket_current"]
    assert "ticket_late_old" not in runtime_evaluation.ready_ticket_ids
    assert missing_pointer_evaluation.ready_ticket_ids == []
    assert missing_pointer_evaluation.graph_reduction_issues[0]["issue_code"] == (
        "graph.current_pointer.missing_explicit"
    )
    assert missing_pointer_proposal.action_type == ProgressionActionType.INCIDENT
    assert missing_pointer_proposal.metadata.reason_code == "progression.incident.graph_reduction_issue"


def test_policy_orphan_pending_does_not_block_graph_complete() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_delivery",
                "ticket_id": "ticket_delivery",
                "ticket_status": "COMPLETED",
                "node_status": "COMPLETED",
            },
            {
                "node_ref": "graph:node_stale_orphan",
                "ticket_id": "ticket_stale_orphan",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
        ],
        stale_orphan_pending_refs=["graph:node_stale_orphan", "ticket_stale_orphan"],
    )

    evaluation = evaluate_progression_graph(snapshot)
    proposals = decide_next_actions(snapshot, ProgressionPolicy(policy_ref="policy:round8b"))

    assert evaluation.graph_complete is True
    assert evaluation.completed_ticket_ids == ["ticket_delivery"]
    assert "ticket_stale_orphan" not in evaluation.ready_ticket_ids
    assert proposals[0].action_type == ProgressionActionType.NO_ACTION
    assert proposals[0].metadata.reason_code == "progression.stale_orphan_pending_ignored"


def test_policy_stale_orphan_reason_does_not_hide_effective_blocked_node() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_blocked",
                "ticket_id": "ticket_blocked",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
                "blocking_reason_code": "PACKAGE_STALE",
            },
            {
                "node_ref": "graph:node_stale_orphan",
                "ticket_id": "ticket_stale_orphan",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
            },
        ],
        stale_orphan_pending_refs=["graph:node_stale_orphan", "ticket_stale_orphan"],
    )

    proposal = decide_next_actions(snapshot, ProgressionPolicy(policy_ref="policy:round8b"))[0]

    assert proposal.action_type == ProgressionActionType.NO_ACTION
    assert proposal.metadata.reason_code == "progression.blocked_no_recovery_action"
    assert proposal.metadata.affected_node_refs == ["graph:node_blocked"]


def test_policy_graph_complete_wait_and_blocked_reason_codes_are_stable() -> None:
    graph_complete_snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_done",
                "ticket_id": "ticket_done",
                "ticket_status": "COMPLETED",
                "node_status": "COMPLETED",
            }
        ]
    )
    approval_snapshot = _minimal_progression_snapshot(
        approvals=[{"approval_id": "approval_a", "node_ref": "graph:node_review"}]
    )
    incident_snapshot = _minimal_progression_snapshot(
        incidents=[{"incident_id": "incident_a", "node_ref": "graph:node_incident"}]
    )
    in_flight_snapshot = _minimal_progression_snapshot(
        in_flight_ticket_ids=["ticket_running"],
        in_flight_node_refs=["graph:node_running"],
    )
    graph_issue_snapshot = _minimal_progression_snapshot(
        graph_reduction_issues=[
            {
                "issue_code": "graph.current_pointer.missing_explicit",
                "node_ref": "graph:node_ambiguous",
                "recoverable": False,
            }
        ]
    )
    blocked_snapshot = _minimal_progression_snapshot(
        blocked_ticket_ids=["ticket_blocked"],
        blocked_node_refs=["graph:node_blocked"],
        blocked_reasons=[
            {
                "reason_code": "EXPLICIT_BLOCKING_REASON:PACKAGE_STALE",
                "ticket_ids": ["ticket_blocked"],
                "node_refs": ["graph:node_blocked"],
            }
        ],
    )
    policy = ProgressionPolicy(policy_ref="policy:round8b")

    assert decide_next_actions(graph_complete_snapshot, policy)[0].metadata.reason_code == (
        "progression.graph_complete_no_closeout_in_8b"
    )
    assert decide_next_actions(approval_snapshot, policy)[0].metadata.reason_code == (
        "progression.wait.open_approval"
    )
    assert decide_next_actions(incident_snapshot, policy)[0].metadata.reason_code == (
        "progression.wait.open_incident"
    )
    assert decide_next_actions(in_flight_snapshot, policy)[0].metadata.reason_code == (
        "progression.wait.in_flight_runtime"
    )
    graph_issue_proposal = decide_next_actions(graph_issue_snapshot, policy)[0]
    assert graph_issue_proposal.action_type == ProgressionActionType.INCIDENT
    assert graph_issue_proposal.metadata.reason_code == "progression.incident.graph_reduction_issue"
    assert decide_next_actions(blocked_snapshot, policy)[0].metadata.reason_code == (
        "progression.blocked_no_recovery_action"
    )


def test_decide_next_actions_uses_policy_recomputed_graph_indexes() -> None:
    policy = ProgressionPolicy(policy_ref="policy:round8b")
    in_flight_snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_running",
                "ticket_id": "ticket_running",
                "ticket_status": "EXECUTING",
                "node_status": "EXECUTING",
            }
        ]
    )
    blocked_snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_blocked",
                "ticket_id": "ticket_blocked",
                "ticket_status": "PENDING",
                "node_status": "PENDING",
                "blocking_reason_code": "PACKAGE_STALE",
            }
        ]
    )

    in_flight_proposal = decide_next_actions(in_flight_snapshot, policy)[0]
    blocked_proposal = decide_next_actions(blocked_snapshot, policy)[0]

    assert in_flight_proposal.action_type == ProgressionActionType.WAIT
    assert in_flight_proposal.metadata.reason_code == "progression.wait.in_flight_runtime"
    assert in_flight_proposal.payload["blocked_by"]["in_flight_ticket_ids"] == ["ticket_running"]
    assert blocked_proposal.action_type == ProgressionActionType.NO_ACTION
    assert blocked_proposal.metadata.reason_code == "progression.blocked_no_recovery_action"
    assert blocked_proposal.metadata.affected_node_refs == ["graph:node_blocked"]


def test_policy_does_not_trigger_architect_or_meeting_gate_from_legacy_hint_text() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8c",
            "governance": {
                "legacy_hints": [
                    "architect_primary must review this.",
                    "A technical decision meeting is required before fanout.",
                ]
            },
            "fanout": {
                "backlog_implementation_handoff": {
                    "source_ticket_id": "tkt_backlog_parent",
                    "ticket_plans": [
                        {
                            "ticket_key": "BR-BE-01",
                            "node_ref": "graph:backlog:br-be-01",
                            "existing_ticket_id": None,
                            "ticket_payload": {
                                "workflow_id": "wf_policy_contract",
                                "node_id": "node_backlog_followup_br_be_01",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                                "summary": "Deliver the backend API follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        }
                    ],
                }
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.CREATE_TICKET
    assert proposal.metadata.reason_code == "progression.fanout.backlog_handoff_ticket"
    assert proposal.metadata.affected_node_refs == ["graph:backlog:br-be-01"]


def test_policy_creates_structured_architect_gate_ticket_when_required_output_is_missing() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8c",
            "governance": {
                "required_gates": [
                    {
                        "gate_ref": "gate:architect:tkt_backlog_parent",
                        "gate_type": "ARCHITECT_GOVERNANCE",
                        "required_output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
                        "source_ticket_id": "tkt_backlog_parent",
                        "node_ref": "graph:architect_gate:backlog_parent",
                        "ticket_payload": {
                            "workflow_id": "wf_policy_contract",
                            "node_id": "node_architect_gate_backlog_parent",
                            "role_profile_ref": "architect_primary",
                            "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
                            "summary": "Prepare the architect governance brief.",
                            "parent_ticket_id": "tkt_backlog_parent",
                        },
                    }
                ],
                "completed_outputs": [],
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.CREATE_TICKET
    assert proposal.metadata.reason_code == "progression.governance.architect_gate_required"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:architect_gate:backlog_parent"]
    assert proposal.metadata.expected_state_transition == "TICKET_CREATED"
    assert proposal.metadata.idempotency_key.startswith(
        "progression:CREATE_TICKET:gv_42:policy:round8c:"
    )
    assert proposal.payload["candidate_ref"] == "gate:architect:tkt_backlog_parent"
    assert proposal.payload["ticket_payload"]["node_id"] == "node_architect_gate_backlog_parent"


def test_policy_waits_for_structured_meeting_requirement_until_evidence_is_approved() -> None:
    waiting_policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8c",
            "governance": {
                "meeting_requirements": [
                    {
                        "requirement_ref": "meeting:req:tkt_backlog_parent",
                        "source_ticket_id": "tkt_backlog_parent",
                        "node_ref": "graph:backlog:parent",
                        "required_meeting_type": "TECHNICAL_DECISION",
                        "meeting_candidate": {
                            "source_ticket_id": "tkt_backlog_parent",
                            "topic": "Lock implementation boundary",
                            "eligible": True,
                        },
                    }
                ],
                "approved_meeting_evidence": [],
            },
            "fanout": {
                "backlog_implementation_handoff": {
                    "source_ticket_id": "tkt_backlog_parent",
                    "ticket_plans": [
                        {
                            "ticket_key": "BR-BE-01",
                            "node_ref": "graph:backlog:br-be-01",
                            "existing_ticket_id": None,
                            "ticket_payload": {
                                "workflow_id": "wf_policy_contract",
                                "node_id": "node_backlog_followup_br_be_01",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                                "summary": "Deliver the backend API follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        }
                    ],
                }
            },
        }
    )
    approved_policy = ProgressionPolicy.model_validate(
        {
            **waiting_policy.model_dump(mode="json"),
            "governance": {
                **waiting_policy.governance,
                "approved_meeting_evidence": [
                    {
                        "requirement_ref": "meeting:req:tkt_backlog_parent",
                        "meeting_id": "mtg_backlog_parent",
                        "review_status": "APPROVED",
                    }
                ],
            },
        }
    )

    waiting_proposal = decide_next_actions(_minimal_progression_snapshot(), waiting_policy)[0]
    approved_proposal = decide_next_actions(_minimal_progression_snapshot(), approved_policy)[0]

    assert waiting_proposal.action_type == ProgressionActionType.WAIT
    assert waiting_proposal.metadata.reason_code == "progression.wait.meeting_requirement"
    assert waiting_proposal.metadata.affected_node_refs == ["graph:backlog:parent"]
    assert waiting_proposal.payload["meeting_requirements"][0]["requirement_ref"] == (
        "meeting:req:tkt_backlog_parent"
    )
    assert approved_proposal.action_type == ProgressionActionType.CREATE_TICKET
    assert approved_proposal.metadata.reason_code == "progression.fanout.backlog_handoff_ticket"


def test_policy_creates_backlog_fanout_from_structured_handoff_with_stable_metadata() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8c",
            "fanout": {
                "backlog_implementation_handoff": {
                    "source_ticket_id": "tkt_backlog_parent",
                    "source_graph_version": "gv_backlog_7",
                    "ticket_plans": [
                        {
                            "ticket_key": "BR-FE-01",
                            "node_ref": "graph:backlog:br-fe-01",
                            "existing_ticket_id": "tkt_existing_fe",
                            "ticket_payload": {
                                "workflow_id": "wf_policy_contract",
                                "node_id": "node_backlog_followup_br_fe_01",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                                "summary": "Existing frontend follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        },
                        {
                            "ticket_key": "BR-BE-01",
                            "node_ref": "graph:backlog:br-be-01",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": "wf_policy_contract",
                                "node_id": "node_backlog_followup_br_be_01",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                                "summary": "Deliver the backend API follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        },
                    ],
                }
            },
        }
    )

    first = decide_next_actions(snapshot, policy)[0]
    second = decide_next_actions(snapshot, policy)[0]

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.action_type == ProgressionActionType.CREATE_TICKET
    assert first.metadata.reason_code == "progression.fanout.backlog_handoff_ticket"
    assert first.metadata.source_graph_version == "gv_42"
    assert first.metadata.affected_node_refs == ["graph:backlog:br-be-01"]
    assert first.metadata.expected_state_transition == "TICKET_CREATED"
    assert first.payload["candidate_ref"] == "backlog:tkt_backlog_parent:BR-BE-01"
    assert first.payload["source_graph_version"] == "gv_backlog_7"
    assert first.payload["ticket_payload"]["node_id"] == "node_backlog_followup_br_be_01"


def test_policy_creates_backlog_fanout_from_structured_graph_patch_plan() -> None:
    snapshot = _minimal_progression_snapshot(graph_version="gv_patch_12")
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8c",
            "fanout": {
                "fanout_graph_patch_plan": {
                    "patch_ref": "graph_patch:fanout:12",
                    "source_ticket_id": "tkt_backlog_parent",
                    "source_graph_version": "gv_patch_11",
                    "ticket_plans": [
                        {
                            "ticket_key": "BR-API-01",
                            "candidate_ref": "graph_patch:fanout:12:BR-API-01",
                            "node_ref": "graph:patch:br-api-01",
                            "ticket_payload": {
                                "workflow_id": "wf_policy_contract",
                                "node_id": "node_graph_patch_br_api_01",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
                                "summary": "Deliver the graph-patch fanout API work.",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        }
                    ],
                }
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.CREATE_TICKET
    assert proposal.metadata.reason_code == "progression.fanout.graph_patch_ticket"
    assert proposal.metadata.source_graph_version == "gv_patch_12"
    assert proposal.metadata.affected_node_refs == ["graph:patch:br-api-01"]
    assert proposal.metadata.expected_state_transition == "TICKET_CREATED"
    assert proposal.payload["candidate_ref"] == "graph_patch:fanout:12:BR-API-01"
    assert proposal.payload["source_graph_version"] == "gv_patch_11"
    assert proposal.payload["fanout_graph_patch_plan"]["patch_ref"] == "graph_patch:fanout:12"


def test_policy_does_not_create_backlog_fanout_from_completed_milestone_without_structured_input() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8c",
            "governance": {
                "completed_outputs": [
                    {
                        "output_schema_ref": "milestone_plan",
                        "ticket_id": "tkt_parent_milestone_plan",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.NO_ACTION
    assert proposal.metadata.reason_code == "progression.no_action"


def test_policy_creates_closeout_with_stable_metadata() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:delivery",
                "ticket_id": "tkt_delivery_done",
                "ticket_status": "COMPLETED",
                "node_status": "COMPLETED",
            }
        ]
    )
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "closeout": {
                "readiness": {
                    "effective_graph_complete": True,
                    "closeout_parent_ticket_id": "tkt_delivery_done",
                    "final_evidence_legality_summary": {
                        "status": "ACCEPTED",
                        "illegal_ref_count": 0,
                    },
                    "ticket_payload": {
                        "workflow_id": "wf_policy_contract",
                        "node_id": "node_ceo_delivery_closeout",
                        "role_profile_ref": "frontend_engineer_primary",
                        "output_schema_ref": DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
                        "summary": "Prepare the final closeout package.",
                        "parent_ticket_id": "tkt_delivery_done",
                    },
                }
            },
        }
    )

    first = decide_next_actions(snapshot, policy)[0]
    second = decide_next_actions(snapshot, policy)[0]

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.action_type == ProgressionActionType.CLOSEOUT
    assert first.metadata.reason_code == "progression.closeout.create_ready"
    assert first.metadata.source_graph_version == "gv_42"
    assert first.metadata.affected_node_refs == ["graph:delivery"]
    assert first.metadata.expected_state_transition == "CLOSEOUT_REQUESTED"
    assert first.metadata.idempotency_key.startswith(
        "progression:CLOSEOUT:gv_42:policy:round8d:"
    )
    assert first.payload["ticket_payload"]["node_id"] == "node_ceo_delivery_closeout"
    assert first.payload["closeout_parent_ticket_id"] == "tkt_delivery_done"


def test_policy_duplicate_closeout_returns_no_action() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:delivery",
                "ticket_id": "tkt_delivery_done",
                "ticket_status": "COMPLETED",
                "node_status": "COMPLETED",
            }
        ]
    )
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "closeout": {
                "readiness": {
                    "effective_graph_complete": True,
                    "existing_closeout_ticket_id": "tkt_existing_closeout",
                    "closeout_parent_ticket_id": "tkt_delivery_done",
                    "final_evidence_legality_summary": {"status": "ACCEPTED"},
                }
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.NO_ACTION
    assert proposal.metadata.reason_code == "progression.closeout.duplicate_existing_closeout"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.metadata.expected_state_transition == "NO_STATE_CHANGE"
    assert proposal.payload["existing_closeout_ticket_id"] == "tkt_existing_closeout"


def test_policy_blocks_closeout_for_open_incident_approval_gate_or_illegal_evidence() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:delivery",
                "ticket_id": "tkt_delivery_done",
                "ticket_status": "COMPLETED",
                "node_status": "COMPLETED",
            }
        ]
    )
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "closeout": {
                "readiness": {
                    "effective_graph_complete": True,
                    "open_blocking_incident_refs": ["inc_blocking"],
                    "open_approval_refs": ["approval_open"],
                    "delivery_checker_gate_issue": {
                        "reason_code": "delivery_check_failed",
                        "ticket_id": "tkt_check",
                    },
                    "closeout_parent_ticket_id": "tkt_delivery_done",
                    "final_evidence_legality_summary": {
                        "status": "REJECTED",
                        "illegal_ref_count": 1,
                        "illegal_refs": ["art://archive/old"],
                    },
                }
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.WAIT
    assert proposal.metadata.reason_code == "progression.wait.closeout_blockers"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.payload["blocked_by"]["incident_refs"] == ["inc_blocking"]
    assert proposal.payload["blocked_by"]["approval_refs"] == ["approval_open"]
    assert proposal.payload["delivery_checker_gate_issue"]["reason_code"] == "delivery_check_failed"
    assert proposal.payload["final_evidence_legality_summary"]["illegal_ref_count"] == 1


def test_policy_creates_rework_for_checker_blocking_finding() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "rework:checker:tkt_check",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_check",
                        "finding_kind": "checker_blocking_finding",
                        "blocking_findings": [
                            {
                                "finding_id": "finding_1",
                                "blocking": True,
                                "target_node_ref": "graph:delivery",
                            }
                        ],
                        "target_ticket_id": "tkt_delivery",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]
    repeated = decide_next_actions(snapshot, policy)[0]

    assert proposal.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert proposal.action_type == ProgressionActionType.REWORK
    assert proposal.metadata.reason_code == "progression.rework.checker_blocking_finding"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.metadata.expected_state_transition == "REWORK_REQUESTED"
    assert proposal.metadata.idempotency_key.startswith(
        "progression:REWORK:gv_42:policy:round8d:"
    )
    assert proposal.payload["target_ticket_id"] == "tkt_delivery"
    assert proposal.payload["blocking_findings"][0]["finding_id"] == "finding_1"


def test_policy_creates_rework_for_deliverable_evidence_gap() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "rework:evidence-gap:tkt_delivery",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_checker",
                        "target_ticket_id": "tkt_delivery",
                        "finding_kind": "evidence_gap",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.REWORK
    assert proposal.metadata.reason_code == "progression.rework.evidence_gap"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.metadata.expected_state_transition == "REWORK_REQUESTED"
    assert proposal.payload["target_ticket_id"] == "tkt_delivery"
    assert proposal.payload["finding_kind"] == "evidence_gap"


def test_policy_opens_incident_when_retry_budget_exhausted() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "retry:tkt_failed",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_failed",
                        "terminal_state": "FAILED",
                        "failure_kind": "SCHEMA_ERROR",
                        "retry_count": 2,
                        "retry_budget": 2,
                        "incident_type": "REPEATED_FAILURE_ESCALATION",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]
    repeated = decide_next_actions(snapshot, policy)[0]

    assert proposal.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert proposal.action_type == ProgressionActionType.INCIDENT
    assert proposal.metadata.reason_code == "progression.incident.retry_budget_exhausted"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.metadata.expected_state_transition == "INCIDENT_OPENED"
    assert proposal.metadata.idempotency_key.startswith(
        "progression:INCIDENT:gv_42:policy:round8d:"
    )
    assert proposal.payload["source_ticket_id"] == "tkt_failed"
    assert proposal.payload["failure_kind"] == "SCHEMA_ERROR"


def test_policy_creates_rework_for_retryable_failed_terminal_target() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "retry:tkt_failed",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_failed",
                        "terminal_state": "FAILED",
                        "failure_kind": "TEST_FAILURE",
                        "retry_count": 0,
                        "retry_budget": 1,
                        "recommended_followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.REWORK
    assert proposal.metadata.reason_code == "progression.rework.failed_terminal_recovery_target"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.metadata.expected_state_transition == "REWORK_REQUESTED"
    assert proposal.payload["source_ticket_id"] == "tkt_failed"
    assert proposal.payload["retry_count"] == 0
    assert proposal.payload["retry_budget"] == 1


def test_policy_opens_incident_for_unrecoverable_failure_kind() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "retry:tkt_failed",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_failed",
                        "terminal_state": "FAILED",
                        "failure_kind": "CONTRACT_CORRUPTION",
                        "retry_count": 0,
                        "retry_budget": 3,
                        "unrecoverable_failure_kinds": ["CONTRACT_CORRUPTION"],
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.INCIDENT
    assert proposal.metadata.reason_code == "progression.incident.unrecoverable_failure_kind"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.payload["failure_kind"] == "CONTRACT_CORRUPTION"


def test_policy_restore_needed_missing_ticket_id_opens_incident() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "restore-needed:missing-ticket",
                        "node_ref": "graph:delivery",
                        "restore_needed": True,
                        "recommended_followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.INCIDENT
    assert proposal.metadata.reason_code == "progression.incident.restore_needed_missing_ticket_id"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.payload["recommended_followup_action"] == "RESTORE_AND_RETRY_LATEST_FAILURE"


def test_policy_completed_ticket_reuse_gate_blocks_parallel_retry() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "reuse:tkt_completed",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_failed_retry",
                        "completed_ticket_reuse_gate": {
                            "satisfies": True,
                            "completed_ticket_id": "tkt_completed",
                        },
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.NO_ACTION
    assert proposal.metadata.reason_code == "progression.recovery.completed_ticket_reuse_gate_satisfied"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.payload["completed_ticket_reuse_gate"]["completed_ticket_id"] == "tkt_completed"


def test_policy_superseded_or_invalidated_lineage_blocks_reuse() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "actions": [
                    {
                        "action_ref": "reuse:tkt_completed_invalid",
                        "node_ref": "graph:delivery",
                        "ticket_id": "tkt_failed_retry",
                        "completed_ticket_reuse_gate": {
                            "satisfies": False,
                            "reason_code": "completed_ticket_superseded",
                            "completed_ticket_id": "tkt_completed",
                            "terminal_failed_ticket_id": "tkt_failed_retry",
                        },
                        "superseded_lineage_refs": ["tkt_completed"],
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.REWORK
    assert proposal.metadata.reason_code == "progression.rework.completed_ticket_reuse_blocked_by_lineage"
    assert proposal.metadata.affected_node_refs == ["graph:delivery"]
    assert proposal.payload["completed_ticket_reuse_gate"]["reason_code"] == "completed_ticket_superseded"
    assert proposal.payload["superseded_lineage_refs"] == ["tkt_completed"]


def test_policy_br100_loop_threshold_opens_incident() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "loop_signals": [
                    {
                        "loop_ref": "BR-100",
                        "node_ref": "graph:br-100",
                        "loop_kind": "maker_checker_rework",
                        "current_count": 3,
                        "threshold": 3,
                        "incident_type": "MAKER_CHECKER_REWORK_ESCALATION",
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.INCIDENT
    assert proposal.metadata.reason_code == "progression.incident.loop_threshold_reached"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:br-100"]
    assert proposal.metadata.expected_state_transition == "INCIDENT_OPENED"
    assert proposal.metadata.idempotency_key.startswith(
        "progression:INCIDENT:gv_42:policy:round8d:"
    )
    assert proposal.payload["loop_ref"] == "BR-100"
    assert proposal.payload["loop_kind"] == "maker_checker_rework"


def test_policy_br100_loop_below_threshold_requests_rework() -> None:
    snapshot = _minimal_progression_snapshot()
    policy = ProgressionPolicy.model_validate(
        {
            "policy_ref": "policy:round8d",
            "recovery": {
                "loop_signals": [
                    {
                        "loop_ref": "BR-100",
                        "node_ref": "graph:br-100",
                        "target_ticket_id": "tkt_br100_maker",
                        "loop_kind": "maker_checker_rework",
                        "current_count": 2,
                        "threshold": 3,
                    }
                ]
            },
        }
    )

    proposal = decide_next_actions(snapshot, policy)[0]

    assert proposal.action_type == ProgressionActionType.REWORK
    assert proposal.metadata.reason_code == "progression.rework.loop_threshold_not_reached"
    assert proposal.metadata.source_graph_version == "gv_42"
    assert proposal.metadata.affected_node_refs == ["graph:br-100"]
    assert proposal.metadata.expected_state_transition == "REWORK_REQUESTED"
    assert proposal.payload["loop_ref"] == "BR-100"
    assert proposal.payload["target_ticket_id"] == "tkt_br100_maker"
    assert proposal.payload["current_count"] == 2
    assert proposal.payload["threshold"] == 3


def test_policy_keeps_blocked_index_for_in_flight_blocked_nodes() -> None:
    snapshot = _minimal_progression_snapshot(
        graph_nodes=[
            {
                "node_ref": "graph:node_running_blocked",
                "ticket_id": "ticket_running_blocked",
                "ticket_status": "EXECUTING",
                "node_status": "EXECUTING",
                "blocking_reason_code": "INCIDENT_OPEN",
            }
        ]
    )

    evaluation = evaluate_progression_graph(snapshot)

    assert evaluation.in_flight_ticket_ids == ["ticket_running_blocked"]
    assert evaluation.in_flight_node_refs == ["graph:node_running_blocked"]
    assert evaluation.blocked_ticket_ids == ["ticket_running_blocked"]
    assert evaluation.blocked_node_refs == ["graph:node_running_blocked"]


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
