from __future__ import annotations

import json
from unittest.mock import patch

from app.core.provider_openai_compat import OpenAICompatProviderResult
from app.core.ticket_graph import build_ticket_graph_snapshot
from tests.test_api import (
    _assert_command_accepted,
    _ensure_scoped_workflow,
    _runtime_provider_upsert_payload,
    _seed_review_request,
    _seed_worker,
    _suppress_ceo_shadow_side_effects,
)


def test_board_advisory_analysis_prefers_graph_subject_over_stale_source_node_id(client):
    workflow_id = "wf_advisory_graph_subject_preferred"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Board advisory analysis should derive execution targets from graph-first review subjects.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_advisory_graph_subject",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:graph-subject",
            ),
        )
    )

    payload = dict(approval["payload"] or {})
    review_pack = dict(payload.get("review_pack") or {})
    subject = dict(review_pack.get("subject") or {})
    assert str(subject.get("source_graph_node_id") or "").strip() == "node_homepage_visual::review"
    subject["source_node_id"] = "node_stale_legacy_review_subject"
    review_pack["subject"] = subject
    payload["review_pack"] = review_pack
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE approval_projection
            SET payload_json = ?, updated_at = updated_at
            WHERE approval_id = ?
            """,
            (json.dumps(payload), approval["approval_id"]),
        )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Freeze the execution lane selected by graph truth."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "approval_mode": "EXPERT_GATED",
                    "audit_mode": "TICKET_TRACE",
                },
                "board_comment": "Graph truth wins over stale compat node ids.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:graph-subject-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    assert advisory_session["affected_nodes"] == ["node_homepage_visual"]

    proposal_payload = {
        "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
        "workflow_id": workflow_id,
        "session_id": advisory_session["session_id"],
        "base_graph_version": build_ticket_graph_snapshot(repository, workflow_id).graph_version,
        "proposal_summary": "Freeze the execution lane derived from graph-first subject.",
        "impact_summary": "The proposal should ignore stale legacy source_node_id values.",
        "freeze_node_ids": ["node_homepage_visual"],
        "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
        "proposal_hash": "hash-advisory-graph-subject",
    }
    with patch(
        "app.core.board_advisory_analysis.invoke_openai_compat_response",
        return_value=OpenAICompatProviderResult(
            output_text='{"bad":"shape"}' + json.dumps(proposal_payload),
            response_id="resp_advisory_graph_subject",
            selected_payload=proposal_payload,
        ),
    ):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:graph-subject",
            },
        )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION", advisory_session["latest_analysis_error"]
    assert advisory_session["latest_patch_proposal_ref"] == proposal_payload["proposal_ref"]
