from __future__ import annotations

from datetime import datetime

import pytest

from app.contracts.governance import GovernanceProfile
from app.core.constants import EVENT_TICKET_COMPLETED, EVENT_TICKET_CREATED
from app.core.versioning import build_graph_version, resolve_workflow_graph_version
from app.db.repository import ControlPlaneRepository


def test_governance_profile_append_only_and_supersede_chain(db_path) -> None:
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    with repository.transaction() as connection:
        first = repository.save_governance_profile(
            connection,
            GovernanceProfile(
                profile_id="gp_1",
                workflow_id="wf_governance_profile",
                approval_mode="AUTO_CEO",
                audit_mode="MINIMAL",
                source_ref="doc://charter/v1",
                supersedes_ref=None,
                effective_from_event="evt_bootstrap",
                version_int=1,
            ),
        )
        second = repository.save_governance_profile(
            connection,
            GovernanceProfile(
                profile_id="gp_2",
                workflow_id="wf_governance_profile",
                approval_mode="EXPERT_GATED",
                audit_mode="TICKET_TRACE",
                source_ref="doc://charter/v2",
                supersedes_ref="gp_1",
                effective_from_event="evt_constraints_update",
                version_int=2,
            ),
        )

    latest = repository.get_latest_governance_profile("wf_governance_profile")
    history = repository.list_governance_profiles("wf_governance_profile")

    assert first.profile_id == "gp_1"
    assert second.profile_id == "gp_2"
    assert latest is not None
    assert latest["profile_id"] == "gp_2"
    assert latest["supersedes_ref"] == "gp_1"
    assert [item["profile_id"] for item in history] == ["gp_2", "gp_1"]


def test_governance_profile_rejects_missing_superseded_target(db_path) -> None:
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    with repository.transaction() as connection:
        with pytest.raises(ValueError, match="supersedes_ref"):
            repository.save_governance_profile(
                connection,
                GovernanceProfile(
                    profile_id="gp_2",
                    workflow_id="wf_governance_profile",
                    approval_mode="AUTO_CEO",
                    audit_mode="MINIMAL",
                    source_ref="doc://charter/v2",
                    supersedes_ref="gp_1",
                    effective_from_event="evt_constraints_update",
                    version_int=2,
                ),
            )


def test_resolve_workflow_graph_version_uses_latest_graph_mutation_event(db_path) -> None:
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test",
            workflow_id="wf_graph_version",
            idempotency_key="ticket-create:wf_graph_version:tkt_001",
            causation_id=None,
            correlation_id="wf_graph_version",
            payload={
                "workflow_id": "wf_graph_version",
                "ticket_id": "tkt_001",
                "node_id": "node_001",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        completed_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_COMPLETED,
            actor_type="system",
            actor_id="test",
            workflow_id="wf_graph_version",
            idempotency_key="ticket-completed:wf_graph_version:tkt_001",
            causation_id=None,
            correlation_id="wf_graph_version",
            payload={
                "workflow_id": "wf_graph_version",
                "ticket_id": "tkt_001",
                "node_id": "node_001",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        )

    graph_version = resolve_workflow_graph_version(repository, "wf_graph_version")

    assert completed_row is not None
    assert graph_version == build_graph_version(int(completed_row["sequence_no"]))


def test_resolve_workflow_graph_version_fail_closed_when_workflow_has_no_graph_events(db_path) -> None:
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    with pytest.raises(ValueError, match="graph version"):
        resolve_workflow_graph_version(repository, "wf_missing_graph_version")
