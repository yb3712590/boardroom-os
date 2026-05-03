from __future__ import annotations

import tests.test_api as api_test_helpers


def test_it006_ceo_shadow_failure_incident_recommends_restore_action(client):
    api_test_helpers.test_p2_ceo_shadow_incident_detail_exposes_restore_failure_action_for_source_ticket(
        client
    )


def test_it006_ceo_shadow_timeout_incident_recommends_restore_action(client, set_ticket_time):
    api_test_helpers.test_p2_ceo_shadow_incident_detail_exposes_restore_timeout_action_for_source_ticket(
        client,
        set_ticket_time,
    )


def test_it006_incident_restore_retry_accepts_exhausted_budget(client, set_ticket_time):
    api_test_helpers.test_incident_resolve_restore_and_retry_can_override_exhausted_retry_budget(
        client,
        set_ticket_time,
    )


def test_it006_dependency_gate_waits_for_restore_chain(client, set_ticket_time, monkeypatch):
    api_test_helpers.test_scheduler_tick_keeps_ticket_pending_when_dependency_gate_has_open_restore_incident(
        client,
        set_ticket_time,
        monkeypatch,
    )


def test_it006_backlog_followup_retries_existing_ticket(client):
    from tests.test_workflow_progression import (
        test_policy_creates_rework_for_retryable_failed_terminal_target,
    )

    test_policy_creates_rework_for_retryable_failed_terminal_target()


def test_it006_backlog_followup_raises_restore_needed_instead_of_no_actions_built(client):
    from tests.test_workflow_progression import (
        test_policy_restore_needed_missing_ticket_id_opens_incident,
    )

    test_policy_restore_needed_missing_ticket_id_opens_incident()
