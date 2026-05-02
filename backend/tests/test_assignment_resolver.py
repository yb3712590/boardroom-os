from __future__ import annotations

from app.core.assignment_resolver import NO_ELIGIBLE_ACTOR_SUGGESTED_ACTIONS, resolve_assignment
from app.core.constants import ACTOR_STATUS_ACTIVE, ACTOR_STATUS_SUSPENDED


def _actor(
    actor_id: str,
    capabilities: list[str],
    *,
    status: str = ACTOR_STATUS_ACTIVE,
    provider_id: str | None = None,
) -> dict:
    actor = {
        "actor_id": actor_id,
        "status": status,
        "capability_set": capabilities,
    }
    if provider_id is not None:
        actor["provider_preferences"] = {"provider_id": provider_id}
    return actor


def test_resolver_selects_active_actor_with_required_capabilities() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend", "test.run.backend"],
        actors=[
            _actor("actor_frontend", ["source.modify.application", "test.run.application"]),
            _actor("actor_backend", ["source.modify.backend", "test.run.backend", "evidence.write.test"]),
        ],
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[],
    )

    assert result.selected_actor_id == "actor_backend"
    assert result.diagnostic_payload is None


def test_resolver_rejects_actor_without_required_capabilities_even_when_available() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=[_actor("actor_frontend", ["source.modify.application"])],
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[],
    )

    assert result.selected_actor_id is None
    assert result.diagnostic_payload is not None
    assert result.diagnostic_payload["reason_code"] == "NO_ELIGIBLE_ACTOR"
    assert result.diagnostic_payload["required_capabilities"] == ["source.modify.backend"]

    candidate_details = {
        detail["actor_id"]: detail for detail in result.diagnostic_payload["candidate_details"]
    }
    assert "source.modify.backend" in candidate_details["actor_frontend"]["missing_capabilities"]
    assert "CREATE_ACTOR" in result.diagnostic_payload["suggested_actions"]
    assert "BLOCK_NODE_NO_CAPABLE_ACTOR" in result.diagnostic_payload["suggested_actions"]


def test_resolver_treats_legacy_employee_exclusion_as_actor_employee_exclusion() -> None:
    actors = [
        {**_actor("actor_frontend_primary", ["source.modify.application"]), "employee_id": "emp_frontend_2"},
        {**_actor("actor_frontend_backup", ["source.modify.application"]), "employee_id": "emp_frontend_backup"},
    ]

    result = resolve_assignment(
        ticket_id="tkt_frontend",
        workflow_id="wf_assign",
        node_id="node_frontend",
        required_capabilities=["source.modify.application"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "emp_frontend_2",
                "scope": "ticket",
                "ticket_id": "tkt_frontend",
                "reason": "legacy employee exclusion",
            }
        ],
    )
    assert result.selected_actor_id == "actor_frontend_backup"
    primary_detail = next(
        detail for detail in result.candidate_details if detail["actor_id"] == "actor_frontend_primary"
    )
    assert primary_detail["excluded"] is True


def test_resolver_treats_active_legacy_employee_lease_as_actor_busy() -> None:
    actors = [
        {**_actor("actor_frontend_primary", ["source.modify.application"]), "employee_id": "emp_frontend_2"},
        {**_actor("actor_frontend_backup", ["source.modify.application"]), "employee_id": "emp_frontend_backup"},
    ]

    result = resolve_assignment(
        ticket_id="tkt_frontend",
        workflow_id="wf_assign",
        node_id="node_frontend",
        required_capabilities=["source.modify.application"],
        actors=actors,
        active_lease_actor_ids={"emp_frontend_2"},
        paused_provider_ids=set(),
        scoped_exclusions=[],
    )

    assert result.selected_actor_id == "actor_frontend_backup"
    primary_detail = next(
        detail for detail in result.candidate_details if detail["actor_id"] == "actor_frontend_primary"
    )
    assert primary_detail["busy"] is True


def test_resolver_applies_only_matching_scoped_exclusions() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend"]),
    ]

    result = resolve_assignment(
        ticket_id="tkt_backend_current",
        workflow_id="wf_assign",
        node_id="node_backend_current",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": "ticket",
                "ticket_id": "tkt_unrelated",
                "reason": "unrelated ticket retry",
            },
            {
                "actor_id": "actor_backend_primary",
                "scope": "node",
                "node_id": "node_backend_current",
                "reason": "current node exclusion",
            },
        ],
    )

    assert result.selected_actor_id == "actor_backend_backup"
    primary_detail = next(
        detail for detail in result.candidate_details if detail["actor_id"] == "actor_backend_primary"
    )
    assert primary_detail["excluded"] is True

    exclusion_matches = primary_detail["exclusion_matches"]
    assert any(
        match.get("scope") == "node"
        and match.get("reason") == "current node exclusion"
        and match.get("node_id") == "node_backend_current"
        for match in exclusion_matches
    )
    assert not any(
        match.get("scope") == "ticket" and match.get("ticket_id") == "tkt_unrelated"
        for match in exclusion_matches
    )


def test_resolver_ignores_capability_exclusion_for_unrequired_capability() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend", "test.run.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend", "test.run.backend"]),
    ]

    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": "capability",
                "capability": "test.run.backend",
                "reason": "different capability",
            }
        ],
    )

    assert result.selected_actor_id == "actor_backend_primary"


def test_resolver_applies_matching_workflow_exclusion() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend", "test.run.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend", "test.run.backend"]),
    ]

    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": "workflow",
                "workflow_id": "wf_assign",
                "reason": "workflow incident",
            }
        ],
    )

    assert result.selected_actor_id == "actor_backend_backup"


def test_resolver_marks_status_busy_and_provider_paused_reasons() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=[
            _actor("actor_suspended", ["source.modify.backend"], status=ACTOR_STATUS_SUSPENDED),
            _actor("actor_busy", ["source.modify.backend"]),
            _actor("actor_paused", ["source.modify.backend"], provider_id="prov_actor_paused"),
        ],
        active_lease_actor_ids={"actor_busy"},
        paused_provider_ids={"prov_actor_paused"},
        scoped_exclusions=[],
    )

    assert result.selected_actor_id is None
    assert result.diagnostic_payload is not None
    details = {detail["actor_id"]: detail for detail in result.diagnostic_payload["candidate_details"]}
    assert details["actor_suspended"]["status_eligible"] is False
    assert details["actor_busy"]["busy"] is True
    assert details["actor_paused"]["provider_paused"] is True


def test_resolver_returns_complete_suggested_actions_in_required_order() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=[_actor("actor_frontend", ["source.modify.application"])],
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[],
    )

    assert result.diagnostic_payload is not None
    assert result.diagnostic_payload["suggested_actions"] == NO_ELIGIBLE_ACTOR_SUGGESTED_ACTIONS



def test_resolver_applies_attempt_exclusion_only_when_ticket_and_attempt_match() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend"]),
    ]

    result = resolve_assignment(
        ticket_id="tkt_backend_current",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": "attempt",
                "ticket_id": "tkt_backend_current",
                "attempt_no": 3,
                "reason": "current attempt exclusion",
            },
            {
                "actor_id": "actor_backend_primary",
                "scope": "attempt",
                "ticket_id": "tkt_backend_other",
                "attempt_no": 2,
                "reason": "different ticket attempt exclusion",
            },
        ],
        attempt_no=3,
    )

    assert result.selected_actor_id == "actor_backend_backup"
    primary_detail = next(
        detail for detail in result.candidate_details if detail["actor_id"] == "actor_backend_primary"
    )
    assert primary_detail["excluded"] is True
    assert primary_detail["exclusion_matches"] == [
        {
            "actor_id": "actor_backend_primary",
            "scope": "attempt",
            "ticket_id": "tkt_backend_current",
            "attempt_no": 3,
            "reason": "current attempt exclusion",
        }
    ]



def test_resolver_does_not_treat_missing_scope_fields_as_wildcards() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend", "test.run.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend", "test.run.backend"]),
    ]

    result = resolve_assignment(
        ticket_id="tkt_backend_current",
        workflow_id="wf_assign_current",
        node_id="node_backend_current",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {"actor_id": "actor_backend_primary", "scope": "ticket", "reason": "missing ticket"},
            {"actor_id": "actor_backend_primary", "scope": "node", "reason": "missing node"},
            {"actor_id": "actor_backend_primary", "scope": "workflow", "reason": "missing workflow"},
            {"actor_id": "actor_backend_primary", "scope": "capability", "reason": "missing capability"},
            {
                "actor_id": "actor_backend_primary",
                "scope": "attempt",
                "ticket_id": "tkt_backend_current",
                "reason": "missing attempt number",
            },
            {"actor_id": "actor_backend_primary", "reason": "missing scope"},
            {"actor_id": "actor_backend_primary", "scope": "unknown", "reason": "unknown scope"},
        ],
        attempt_no=1,
    )

    assert result.selected_actor_id == "actor_backend_primary"
    primary_detail = next(
        detail for detail in result.candidate_details if detail["actor_id"] == "actor_backend_primary"
    )
    assert primary_detail["excluded"] is False
    assert primary_detail["exclusion_matches"] == []
