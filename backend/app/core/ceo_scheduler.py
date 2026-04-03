from __future__ import annotations

from typing import Any

from app.core.ceo_executor import execute_ceo_action_batch
from app.core.ceo_proposer import build_no_action_batch, propose_ceo_action_batch
from app.core.ceo_prompts import CEO_SHADOW_PROMPT_VERSION
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.ceo_validator import validate_ceo_action_batch
from app.core.runtime_provider_config import RuntimeProviderConfigStore
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _build_mainline_effect(snapshot: dict[str, Any]) -> str:
    if snapshot["approvals"]:
        return "WAIT_FOR_BOARD"
    if snapshot["incidents"]:
        return "WAIT_FOR_INCIDENT"
    if snapshot["ticket_summary"]["ready_count"] > 0:
        return "RUN_SCHEDULER_TICK"
    if snapshot["ticket_summary"]["active_count"] > 0:
        return "WAIT_FOR_RUNTIME"
    return "NO_IMMEDIATE_FOLLOWUP"


def _build_comparison(
    *,
    snapshot: dict[str, Any],
    accepted_actions: list[dict[str, Any]],
    rejected_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    deterministic_effect = _build_mainline_effect(snapshot)
    accepted_action_types = [item["action_type"] for item in accepted_actions]
    mainline_waiting_states = {"WAIT_FOR_BOARD", "WAIT_FOR_INCIDENT", "WAIT_FOR_RUNTIME", "NO_IMMEDIATE_FOLLOWUP"}
    if deterministic_effect in mainline_waiting_states:
        diverges_from_mainline = any(action_type != "NO_ACTION" for action_type in accepted_action_types)
    else:
        diverges_from_mainline = not bool(accepted_actions)
    return {
        "mainline_controller": "workflow_auto_advance",
        "deterministic_effect": deterministic_effect,
        "accepted_action_types": accepted_action_types,
        "accepted_action_count": len(accepted_actions),
        "rejected_action_count": len(rejected_actions),
        "diverges_from_mainline": diverges_from_mainline,
    }


def run_ceo_shadow_for_trigger(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_type: str,
    trigger_ref: str | None,
    runtime_provider_store: RuntimeProviderConfigStore | None = None,
) -> dict[str, Any]:
    repository.initialize()
    occurred_at = now_local()
    snapshot: dict[str, Any] = {
        "trigger": {"trigger_type": trigger_type, "trigger_ref": trigger_ref},
        "workflow": {"workflow_id": workflow_id},
    }
    proposal = None
    accepted_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []
    executed_actions: list[dict[str, Any]] = []
    execution_summary: dict[str, Any] = {
        "attempted_action_count": 0,
        "executed_action_count": 0,
        "duplicate_action_count": 0,
        "passthrough_action_count": 0,
        "deferred_action_count": 0,
        "failed_action_count": 0,
    }
    deterministic_fallback_used = False
    deterministic_fallback_reason: str | None = None
    comparison: dict[str, Any] = {
        "mainline_controller": "workflow_auto_advance",
        "deterministic_effect": "SHADOW_ERROR",
        "accepted_action_types": [],
        "accepted_action_count": 0,
        "rejected_action_count": 0,
        "diverges_from_mainline": False,
    }

    try:
        snapshot = build_ceo_shadow_snapshot(
            repository,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
        )
        proposal = propose_ceo_action_batch(
            repository,
            snapshot=snapshot,
            runtime_provider_store=runtime_provider_store,
        )
        validation = validate_ceo_action_batch(repository, action_batch=proposal.action_batch)
        accepted_actions = validation["accepted_actions"]
        rejected_actions = validation["rejected_actions"]
        execution_result = execute_ceo_action_batch(
            repository,
            action_batch=proposal.action_batch,
            accepted_actions=accepted_actions,
        )
        executed_actions = execution_result["executed_actions"]
        execution_summary = execution_result["execution_summary"]
        comparison = _build_comparison(
            snapshot=snapshot,
            accepted_actions=accepted_actions,
            rejected_actions=rejected_actions,
        )
        if proposal.fallback_reason is not None:
            deterministic_fallback_used = True
            deterministic_fallback_reason = proposal.fallback_reason
        first_failed_action = next(
            (item for item in executed_actions if item.get("execution_status") == "FAILED"),
            None,
        )
        if first_failed_action is not None:
            deterministic_fallback_used = True
            deterministic_fallback_reason = str(first_failed_action.get("reason") or "Limited CEO execution failed.")
    except Exception as exc:
        fallback_reason = f"CEO shadow snapshot/proposal pipeline failed: {exc}"
        proposal = type("FallbackProposal", (), {})()
        proposal.action_batch = build_no_action_batch(fallback_reason)
        proposal.effective_mode = "SHADOW_ERROR"
        proposal.provider_health_summary = "ERROR"
        proposal.model = None
        proposal.provider_response_id = None
        proposal.fallback_reason = fallback_reason
        deterministic_fallback_used = True
        deterministic_fallback_reason = fallback_reason

    with repository.transaction() as connection:
        return repository.append_ceo_shadow_run(
            connection,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            occurred_at=occurred_at,
            effective_mode=proposal.effective_mode,
            provider_health_summary=proposal.provider_health_summary,
            model=proposal.model,
            prompt_version=CEO_SHADOW_PROMPT_VERSION,
            provider_response_id=proposal.provider_response_id,
            fallback_reason=proposal.fallback_reason,
            snapshot=snapshot,
            proposed_action_batch=proposal.action_batch.model_dump(mode="json"),
            accepted_actions=accepted_actions,
            rejected_actions=rejected_actions,
            executed_actions=executed_actions,
            execution_summary=execution_summary,
            deterministic_fallback_used=deterministic_fallback_used,
            deterministic_fallback_reason=deterministic_fallback_reason,
            comparison=comparison,
        )
