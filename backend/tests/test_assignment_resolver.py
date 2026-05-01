from __future__ import annotations

from app.core.assignment_resolver import (
    EXCLUSION_SCOPE_CAPABILITY,
    EXCLUSION_SCOPE_NODE,
    EXCLUSION_SCOPE_TICKET,
    EXCLUSION_SCOPE_WORKFLOW,
    NO_ELIGIBLE_ACTOR_REASON_CODE,
    resolve_assignment,
)
from app.core.constants import ACTOR_STATUS_ACTIVE, ACTOR_STATUS_SUSPENDED


def _actor(actor_id: str, capabilities: list[str], *, status: str = ACTOR_STATUS_ACTIVE) -> dict:
    return {
        "actor_id": actor_id,
        "status": status,
        "capability_set": capabilities,
        "provider_preferences": {"provider_id": f"prov_{actor_id}"},
    }


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
    assert result.diagnostic_payload["reason_code"] == NO_ELIGIBLE_ACTOR_REASON_CODE
    assert result.diagnostic_payload["required_capabilities"] == ["source.modify.backend"]
    assert result.diagnostic_payload["candidate_details"][0]["missing_capabilities"] == ["source.modify.backend"]
    assert "CREATE_ACTOR" in result.diagnostic_payload["suggested_actions"]
    assert "BLOCK_NODE_NO_CAPABLE_ACTOR" in result.diagnostic_payload["suggested_actions"]


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
                "scope": EXCLUSION_SCOPE_TICKET,
                "ticket_id": "tkt_unrelated",
                "reason": "unrelated ticket retry",
            },
            {
                "actor_id": "actor_backend_primary",
                "scope": EXCLUSION_SCOPE_NODE,
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
    assert primary_detail["exclusion_matches"] == [
        {
            "scope": EXCLUSION_SCOPE_NODE,
            "reason": "current node exclusion",
            "capability": None,
            "ticket_id": None,
            "node_id": "node_backend_current",
            "workflow_id": None,
        }
    ]


def test_resolver_scopes_capability_and_workflow_exclusions() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend", "test.run.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend", "test.run.backend"]),
    ]

    capability_result = resolve_assignment(
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
                "scope": EXCLUSION_SCOPE_CAPABILITY,
                "capability": "test.run.backend",
                "reason": "different capability",
            }
        ],
    )
    assert capability_result.selected_actor_id == "actor_backend_primary"

    workflow_result = resolve_assignment(
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
                "scope": EXCLUSION_SCOPE_WORKFLOW,
                "workflow_id": "wf_assign",
                "reason": "workflow incident",
            }
        ],
    )
    assert workflow_result.selected_actor_id == "actor_backend_backup"


def test_resolver_marks_status_busy_and_provider_paused_reasons() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=[
            _actor("actor_suspended", ["source.modify.backend"], status=ACTOR_STATUS_SUSPENDED),
            _actor("actor_busy", ["source.modify.backend"]),
            _actor("actor_paused", ["source.modify.backend"]),
        ],
        active_lease_actor_ids={"actor_busy"},
        paused_provider_ids={"prov_actor_paused"},
        scoped_exclusions=[],
    )

    assert result.selected_actor_id is None
    details = {detail["actor_id"]: detail for detail in result.diagnostic_payload["candidate_details"]}
    assert details["actor_suspended"]["status_eligible"] is False
    assert details["actor_busy"]["busy"] is True
    assert details["actor_paused"]["provider_paused"] is True
