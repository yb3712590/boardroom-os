from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.core.ceo_executor import execute_ceo_action_batch
from app.core.ceo_proposer import (
    build_deterministic_fallback_batch,
    build_no_action_batch,
    propose_ceo_action_batch,
)
from app.core.graph_identity import GraphIdentityResolutionError
from app.core.graph_health import GraphHealthUnavailableError
from app.core.graph_patch_reducer import GraphPatchReducerUnavailableError
from app.core.ceo_prompts import CEO_SHADOW_PROMPT_VERSION
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.ceo_snapshot_contracts import controller_state_view
from app.core.ceo_hire_loop import detect_consecutive_hire_loop, open_ceo_hire_loop_incident
from app.core.ceo_validator import validate_ceo_action_batch
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED, INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
from app.core.runtime_provider_config import RuntimeProviderConfigStore
from app.core.time import now_local
from app.core.workflow_controller import workflow_controller_effect
from app.db.repository import ControlPlaneRepository

SCHEDULER_IDLE_MAINTENANCE_TRIGGER = "SCHEDULER_IDLE_MAINTENANCE"


@dataclass(frozen=True)
class CeoShadowPipelineError(RuntimeError):
    workflow_id: str
    trigger_type: str
    trigger_ref: str | None
    source_stage: str
    error_class: str
    error_message: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(
            self,
            f"CEO shadow pipeline failed at {self.source_stage}: {self.error_class}: {self.error_message}",
        )


def is_ticket_graph_unavailable_error(error: Exception) -> bool:
    if isinstance(
        error,
        (
            GraphHealthUnavailableError,
            GraphPatchReducerUnavailableError,
            GraphIdentityResolutionError,
        ),
    ):
        return True
    message = str(error).strip().lower()
    return "graph" in message and "unavailable" in message


def _empty_execution_summary() -> dict[str, int]:
    return {
        "attempted_action_count": 0,
        "executed_action_count": 0,
        "duplicate_action_count": 0,
        "passthrough_action_count": 0,
        "deferred_action_count": 0,
        "failed_action_count": 0,
    }


def _build_mainline_effect(snapshot: dict[str, Any]) -> str:
    return workflow_controller_effect(snapshot)


def _build_comparison(
    *,
    snapshot: dict[str, Any],
    accepted_actions: list[dict[str, Any]],
    rejected_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        deterministic_effect = _build_mainline_effect(snapshot)
        expected_action = str((controller_state_view(snapshot) or {}).get("recommended_action") or "").strip()
    except ValueError:
        deterministic_effect = "PIPELINE_FAILED_BEFORE_SNAPSHOT"
        expected_action = ""
    accepted_action_types = [item["action_type"] for item in accepted_actions]
    mainline_waiting_states = {
        "WAIT_FOR_BOARD",
        "WAIT_FOR_INCIDENT",
        "WAIT_FOR_RUNTIME",
        "WAIT_FOR_GRAPH_HEALTH",
        "NO_IMMEDIATE_FOLLOWUP",
    }
    if deterministic_effect in mainline_waiting_states:
        diverges_from_mainline = any(action_type != "NO_ACTION" for action_type in accepted_action_types)
    elif expected_action in {"CREATE_TICKET", "HIRE_EMPLOYEE", "REQUEST_MEETING"}:
        diverges_from_mainline = expected_action not in accepted_action_types
    else:
        diverges_from_mainline = not bool(accepted_actions)
    return {
        "mainline_controller": "workflow_auto_advance",
        "deterministic_effect": deterministic_effect,
        "expected_action": expected_action,
        "accepted_action_types": accepted_action_types,
        "accepted_action_count": len(accepted_actions),
        "rejected_action_count": len(rejected_actions),
        "diverges_from_mainline": diverges_from_mainline,
    }


def _snapshot_graph_health_requires_pause(snapshot: dict[str, Any]) -> bool:
    try:
        controller_state = controller_state_view(snapshot)
    except ValueError:
        controller_state = {}
    if str(controller_state.get("state") or "").strip() == "GRAPH_HEALTH_WAIT":
        return True

    graph_health_report = (snapshot.get("projection_snapshot") or {}).get("graph_health_report") or {}
    if str(graph_health_report.get("overall_health") or "").strip() != "CRITICAL":
        return False
    phrases: list[str] = []
    phrases.extend(str(item or "") for item in list(graph_health_report.get("recommended_actions") or []))
    for finding in list(graph_health_report.get("findings") or []):
        if not isinstance(finding, dict):
            continue
        if str(finding.get("severity") or "").strip() != "CRITICAL":
            continue
        phrases.append(str(finding.get("suggested_action") or ""))
        phrases.append(str(finding.get("description") or ""))
    haystack = " ".join(phrases).lower()
    return "pause" in haystack and ("fanout" in haystack or "graph health" in haystack)


def _needs_deterministic_fallback_after_validation(
    *,
    snapshot: dict[str, Any],
    accepted_actions: list[dict[str, Any]],
    rejected_actions: list[dict[str, Any]],
) -> bool:
    if accepted_actions or not rejected_actions:
        return False
    if _snapshot_graph_health_requires_pause(snapshot):
        return False
    expected_action = str((controller_state_view(snapshot) or {}).get("recommended_action") or "").strip()
    if expected_action not in {"CREATE_TICKET", "HIRE_EMPLOYEE", "REQUEST_MEETING"}:
        return False
    return all(str(item.get("action_type") or "").strip() == "NO_ACTION" for item in rejected_actions)


def _snapshot_has_idle_maintenance_signal(snapshot: dict[str, Any]) -> bool:
    idle_maintenance = snapshot.get("idle_maintenance") or {}
    return bool(idle_maintenance.get("signal_types"))


def _snapshot_has_controller_action_signal(snapshot: dict[str, Any]) -> bool:
    controller_state = controller_state_view(snapshot)
    return str(controller_state.get("recommended_action") or "").strip() in {
        "CREATE_TICKET",
        "HIRE_EMPLOYEE",
        "REQUEST_MEETING",
    }


def _has_blocking_idle_maintenance_incident(snapshot: dict[str, Any]) -> bool:
    for incident in snapshot.get("incidents") or []:
        if (
            str(incident.get("incident_type") or "").strip() == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
            and str(incident.get("trigger_type") or "").strip() == EVENT_BOARD_DIRECTIVE_RECEIVED
        ):
            continue
        return True
    return False


def _parse_snapshot_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        return datetime.fromisoformat(value)
    return None


def _snapshot_latest_state_change_at(snapshot: dict[str, Any]) -> datetime | None:
    idle_maintenance = snapshot.get("idle_maintenance") or {}
    latest_change = _parse_snapshot_timestamp(idle_maintenance.get("latest_state_change_at"))
    return latest_change


def list_due_ceo_maintenance_workflows(
    repository: ControlPlaneRepository,
    *,
    current_time: datetime,
    interval_sec: int | None = None,
) -> list[dict[str, Any]]:
    resolved_interval_sec = (
        get_settings().ceo_maintenance_interval_sec if interval_sec is None else interval_sec
    )
    if resolved_interval_sec <= 0:
        return []

    due_workflows: list[dict[str, Any]] = []
    for workflow in repository.list_workflow_projections():
        if str(workflow.get("status") or "") != "EXECUTING":
            continue
        snapshot = build_ceo_shadow_snapshot(
            repository,
            workflow_id=str(workflow["workflow_id"]),
            trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            trigger_ref=None,
        )
        if snapshot.get("approvals") or _has_blocking_idle_maintenance_incident(snapshot):
            continue
        if int((snapshot.get("ticket_summary") or {}).get("working_count") or 0) > 0:
            continue
        if not _snapshot_has_idle_maintenance_signal(snapshot) and not _snapshot_has_controller_action_signal(snapshot):
            continue
        latest_state_change_at = _snapshot_latest_state_change_at(snapshot)
        if latest_state_change_at is not None:
            elapsed_since_change = (current_time - latest_state_change_at).total_seconds()
            if elapsed_since_change < resolved_interval_sec:
                continue
        latest_run = repository.get_latest_ceo_shadow_run_for_trigger(
            str(workflow["workflow_id"]),
            SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        )
        if latest_run is not None:
            elapsed_sec = (current_time - latest_run["occurred_at"]).total_seconds()
            if elapsed_sec < resolved_interval_sec:
                continue
        due_workflows.append(
            {
                **workflow,
                "idle_maintenance_signal_types": list(
                    (snapshot.get("idle_maintenance") or {}).get("signal_types") or []
                ),
                "idle_maintenance_latest_state_change_at": (
                    latest_state_change_at.isoformat() if latest_state_change_at is not None else None
                ),
            }
        )

    return due_workflows


def run_due_ceo_maintenance(
    repository: ControlPlaneRepository,
    *,
    current_time: datetime,
    trigger_ref: str,
    interval_sec: int | None = None,
    runtime_provider_store: RuntimeProviderConfigStore | None = None,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for workflow in list_due_ceo_maintenance_workflows(
        repository,
        current_time=current_time,
        interval_sec=interval_sec,
    ):
        run = trigger_ceo_shadow_with_recovery(
            repository,
            workflow_id=str(workflow["workflow_id"]),
            trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            trigger_ref=trigger_ref,
            runtime_provider_store=runtime_provider_store,
            idempotency_key_base=f"idle-maintenance:{workflow['workflow_id']}:{trigger_ref}",
        )
        if run is not None:
            runs.append(run)
    return runs


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
    execution_summary: dict[str, Any] = _empty_execution_summary()
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
    proposed_action_batch = build_no_action_batch("CEO shadow run did not complete.").model_dump(mode="json")

    def _append_run(
        *,
        effective_mode: str,
        provider_health_summary: str,
        model: str | None,
        preferred_provider_id: str | None,
        preferred_model: str | None,
        actual_provider_id: str | None,
        actual_model: str | None,
        selection_reason: str | None,
        policy_reason: str | None,
        provider_response_id: str | None,
        fallback_reason: str | None,
        deterministic_used: bool,
        deterministic_reason: str | None,
    ) -> dict[str, Any]:
        nonlocal comparison
        comparison = _build_comparison(
            snapshot=snapshot,
            accepted_actions=accepted_actions,
            rejected_actions=rejected_actions,
        )
        with repository.transaction() as connection:
            previous_runs = repository.list_ceo_shadow_runs(
                workflow_id,
                limit=1,
                connection=connection,
            )
            run = repository.append_ceo_shadow_run(
                connection,
                workflow_id=workflow_id,
                trigger_type=trigger_type,
                trigger_ref=trigger_ref,
                occurred_at=occurred_at,
                effective_mode=effective_mode,
                provider_health_summary=provider_health_summary,
                model=model,
                preferred_provider_id=preferred_provider_id,
                preferred_model=preferred_model,
                actual_provider_id=actual_provider_id,
                actual_model=actual_model,
                selection_reason=selection_reason,
                policy_reason=policy_reason,
                prompt_version=CEO_SHADOW_PROMPT_VERSION,
                provider_response_id=provider_response_id,
                fallback_reason=fallback_reason,
                snapshot=snapshot,
                proposed_action_batch=proposed_action_batch,
                accepted_actions=accepted_actions,
                rejected_actions=rejected_actions,
                executed_actions=executed_actions,
                execution_summary=execution_summary,
                deterministic_fallback_used=deterministic_used,
                deterministic_fallback_reason=deterministic_reason,
                comparison=comparison,
            )
            loop_detection = detect_consecutive_hire_loop(
                workflow_id=workflow_id,
                snapshot=snapshot,
                rejected_actions=rejected_actions,
                previous_run=previous_runs[0] if previous_runs else None,
            )
            if loop_detection is not None:
                open_ceo_hire_loop_incident(
                    repository,
                    connection=connection,
                    workflow_id=workflow_id,
                    detection=loop_detection,
                    occurred_at=occurred_at,
                    idempotency_key_base=f"ceo-shadow-run:{run['run_id']}:hire-loop",
                    causation_id=str(run["run_id"]),
                )
            return run

    def _raise_pipeline_error(source_stage: str, exc: Exception) -> None:
        is_existing_error = isinstance(exc, CeoShadowPipelineError)
        exception_details = getattr(exc, "details", None)
        provider_response_id = (
            str(exception_details.get("provider_response_id") or "").strip()
            if isinstance(exception_details, dict)
            else ""
        ) or None
        error = (
            exc
            if is_existing_error
            else CeoShadowPipelineError(
                workflow_id=workflow_id,
                trigger_type=trigger_type,
                trigger_ref=trigger_ref,
                source_stage=source_stage,
                error_class=type(exc).__name__,
                error_message=str(exc),
            )
        )
        _append_run(
            effective_mode="SHADOW_ERROR",
            provider_health_summary="ERROR",
            model=None,
            preferred_provider_id=None,
            preferred_model=None,
            actual_provider_id=None,
            actual_model=None,
            selection_reason=None,
            policy_reason=None,
            provider_response_id=provider_response_id,
            fallback_reason=error.error_message,
            deterministic_used=False,
            deterministic_reason=None,
        )
        if is_existing_error:
            raise error
        raise error from exc

    try:
        snapshot = build_ceo_shadow_snapshot(
            repository,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
        )
    except Exception as exc:
        if is_ticket_graph_unavailable_error(exc):
            raise
        _raise_pipeline_error("snapshot", exc)

    try:
        proposal = propose_ceo_action_batch(
            repository,
            snapshot=snapshot,
            runtime_provider_store=runtime_provider_store,
        )
        proposed_action_batch = proposal.action_batch.model_dump(mode="json")
    except Exception as exc:
        _raise_pipeline_error("proposal", exc)

    try:
        validation = validate_ceo_action_batch(repository, action_batch=proposal.action_batch, snapshot=snapshot)
        accepted_actions = validation["accepted_actions"]
        rejected_actions = validation["rejected_actions"]
        action_batch_for_execution = proposal.action_batch
        validation_fallback_reason = None
        if _needs_deterministic_fallback_after_validation(
            snapshot=snapshot,
            accepted_actions=accepted_actions,
            rejected_actions=rejected_actions,
        ):
            expected_action = str(controller_state_view(snapshot).get("recommended_action") or "").strip()
            validation_fallback_reason = (
                "Deterministic fallback used because the live CEO proposal had no accepted actions "
                f"while controller_state.recommended_action is {expected_action}."
            )
            action_batch_for_execution = build_deterministic_fallback_batch(
                repository,
                snapshot,
                validation_fallback_reason,
            )
            fallback_validation = validate_ceo_action_batch(
                repository,
                action_batch=action_batch_for_execution,
                snapshot=snapshot,
            )
            accepted_actions = fallback_validation["accepted_actions"]
            rejected_actions = rejected_actions + fallback_validation["rejected_actions"]
            proposed_action_batch = action_batch_for_execution.model_dump(mode="json")
    except Exception as exc:
        _raise_pipeline_error("validation", exc)

    try:
        execution_result = execute_ceo_action_batch(
            repository,
            action_batch=action_batch_for_execution,
            accepted_actions=accepted_actions,
        )
        executed_actions = execution_result["executed_actions"]
        execution_summary = execution_result["execution_summary"]
    except Exception as exc:
        _raise_pipeline_error("execution", exc)

    first_failed_action = next(
        (item for item in executed_actions if item.get("execution_status") == "FAILED"),
        None,
    )
    if first_failed_action is not None:
        _raise_pipeline_error(
            "execution",
            CeoShadowPipelineError(
                workflow_id=workflow_id,
                trigger_type=trigger_type,
                trigger_ref=trigger_ref,
                source_stage="execution",
                error_class="ExecutionFailed",
                error_message=str(first_failed_action.get("reason") or "Limited CEO execution failed."),
            ),
        )

    if validation_fallback_reason is not None:
        deterministic_fallback_used = True
        deterministic_fallback_reason = validation_fallback_reason
    elif proposal.fallback_reason is not None:
        deterministic_fallback_used = True
        deterministic_fallback_reason = proposal.fallback_reason

    fallback_reason = validation_fallback_reason or proposal.fallback_reason
    return _append_run(
        effective_mode=proposal.effective_mode,
        provider_health_summary=proposal.provider_health_summary,
        model=proposal.model,
        preferred_provider_id=proposal.preferred_provider_id,
        preferred_model=proposal.preferred_model,
        actual_provider_id=proposal.actual_provider_id,
        actual_model=proposal.actual_model,
        selection_reason=proposal.selection_reason,
        policy_reason=proposal.policy_reason,
        provider_response_id=proposal.provider_response_id,
        fallback_reason=fallback_reason,
        deterministic_used=deterministic_fallback_used,
        deterministic_reason=deterministic_fallback_reason,
    )


def trigger_ceo_shadow_with_recovery(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_type: str,
    trigger_ref: str | None,
    runtime_provider_store: RuntimeProviderConfigStore | None = None,
    idempotency_key_base: str | None = None,
) -> dict[str, Any] | None:
    resolved_key_base = (
        idempotency_key_base
        or f"ceo-shadow-trigger:{workflow_id}:{trigger_type}:{trigger_ref or 'none'}"
    )
    try:
        return run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            runtime_provider_store=runtime_provider_store,
        )
    except Exception as exc:
        if is_ticket_graph_unavailable_error(exc):
            from app.core.ticket_handlers import open_ticket_graph_unavailable_incident

            open_ticket_graph_unavailable_incident(
                repository,
                workflow_id=workflow_id,
                source_component="ceo_shadow_snapshot",
                error=exc,
                idempotency_key_base=f"{resolved_key_base}:graph-unavailable",
                actor_id="ceo-shadow-trigger",
            )
            return None
        if isinstance(exc, CeoShadowPipelineError):
            from app.core.ticket_handlers import open_ceo_shadow_pipeline_failed_incident

            open_ceo_shadow_pipeline_failed_incident(
                repository,
                workflow_id=workflow_id,
                error=exc,
                idempotency_key_base=f"{resolved_key_base}:pipeline-failed",
                actor_id="ceo-shadow-trigger",
            )
            return None
        raise
