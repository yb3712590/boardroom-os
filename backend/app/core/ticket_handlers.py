from __future__ import annotations

import fnmatch
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    IncidentFollowupAction,
    IncidentResolveCommand,
    SchedulerWorkerCandidate,
    SchedulerTickCommand,
    TicketCancelCommand,
    TicketCompletedCommand,
    TicketCreateCommand,
    TicketFailCommand,
    TicketHeartbeatCommand,
    TicketLeaseCommand,
    TicketResultStatus,
    TicketResultSubmitCommand,
    TicketStartCommand,
)
from app.core.constants import (
    CIRCUIT_BREAKER_STATE_CLOSED,
    CIRCUIT_BREAKER_STATE_OPEN,
    DEFAULT_LEASE_TIMEOUT_SEC,
    DEFAULT_REPEAT_FAILURE_THRESHOLD,
    DEFAULT_TIMEOUT_BACKOFF_CAP_MULTIPLIER,
    DEFAULT_TIMEOUT_BACKOFF_MULTIPLIER,
    DEFAULT_TIMEOUT_REPEAT_THRESHOLD,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    FAILURE_KIND_PROVIDER_RATE_LIMITED,
    FAILURE_KIND_UPSTREAM_UNAVAILABLE,
    INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
    INCIDENT_STATUS_CLOSED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_STATUS_RECOVERING,
    INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
    INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    PROVIDER_FINGERPRINT_PREFIX,
    PROVIDER_PAUSE_FAILURE_KINDS,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_TIMED_OUT,
    TIMEOUT_FAMILY_RUNTIME,
)
from app.core.context_compiler import export_latest_compile_artifacts_to_developer_inspector
from app.core.developer_inspector import DeveloperInspectorStore, PersistedDeveloperInspectorArtifact
from app.core.ids import new_prefixed_id
from app.core.output_schemas import validate_output_payload
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    ticket_id: str,
    action: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason=f"An identical {action} command was already accepted.",
        causation_hint=f"ticket:{ticket_id}",
    )


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    ticket_id: str,
    reason: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=f"ticket:{ticket_id}",
    )


def _scheduler_duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical scheduler-tick command was already accepted.",
        causation_hint="scheduler:tick",
    )


def _incident_duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    incident_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical incident-resolve command was already accepted.",
        causation_hint=f"incident:{incident_id}",
    )


def _incident_rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    incident_id: str,
    reason: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=f"incident:{incident_id}",
    )


def _cancel_duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    ticket_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical ticket-cancel command was already accepted.",
        causation_hint=f"ticket:{ticket_id}",
    )


def _match_allowed_write_set(path: str, allowed_write_set: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed_write_set)


def _insert_ticket_cancelled_event(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    cancelled_by: str,
    reason: str,
    idempotency_key: str,
) -> None:
    event_row = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CANCELLED,
        actor_type="operator",
        actor_id=cancelled_by,
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "ticket_id": ticket_id,
            "node_id": node_id,
            "cancelled_by": cancelled_by,
            "reason": reason,
        },
        occurred_at=occurred_at,
    )
    if event_row is None:
        raise RuntimeError("Ticket cancellation idempotency conflict.")


def _build_review_pack(
    *,
    payload: TicketCompletedCommand,
    trigger_event_id: str,
    command_target_version: int,
    occurred_at: datetime,
) -> dict:
    review_request = payload.review_request
    if review_request is None:
        raise RuntimeError("review_request is required to build a review pack.")

    return {
        "meta": {
            "review_pack_version": 1,
            "workflow_id": payload.workflow_id,
            "review_type": review_request.review_type.value,
            "created_at": occurred_at.isoformat(),
            "priority": review_request.priority.value,
        },
        "subject": {
            "title": review_request.title,
            "subtitle": review_request.subtitle,
            "source_node_id": payload.node_id,
            "source_ticket_id": payload.ticket_id,
            "blocking_scope": review_request.blocking_scope.value,
        },
        "trigger": {
            "trigger_event_id": trigger_event_id,
            "trigger_reason": review_request.trigger_reason,
            "why_now": review_request.why_now,
        },
        "recommendation": {
            "recommended_action": review_request.recommended_action.value,
            "recommended_option_id": review_request.recommended_option_id,
            "summary": review_request.recommendation_summary,
        },
        "options": [option.model_dump(mode="json") for option in review_request.options],
        "evidence_summary": [
            evidence.model_dump(mode="json") for evidence in review_request.evidence_summary
        ],
        "delta_summary": review_request.delta_summary,
        "maker_checker_summary": review_request.maker_checker_summary,
        "risk_summary": review_request.risk_summary,
        "budget_impact": review_request.budget_impact,
        "decision_form": {
            "allowed_actions": [action.value for action in review_request.available_actions],
            "command_target_version": command_target_version,
            "requires_comment_on_reject": True,
            "requires_constraint_patch_on_modify": True,
        },
        "developer_inspector_refs": (
            review_request.developer_inspector_refs.model_dump(mode="json", exclude_none=True)
            if review_request.developer_inspector_refs is not None
            else None
        ),
    }




def _normalized_failure_detail(failure_detail: dict | None) -> dict:
    if failure_detail is None:
        return {}
    return json.loads(json.dumps(failure_detail, sort_keys=True))


def _build_failure_payload(
    *,
    failure_kind: str,
    failure_message: str,
    failure_detail: dict | None,
) -> dict[str, Any]:
    normalized_detail = _normalized_failure_detail(failure_detail)
    fingerprint_source = {
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": normalized_detail,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_source,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": normalized_detail,
        "failure_fingerprint": fingerprint,
    }


TIMEOUT_FAILURE_KINDS = {"TIMEOUT_SLA_EXCEEDED", "HEARTBEAT_TIMEOUT"}


def _resolve_ticket_lease_timeout_sec(created_spec: dict[str, Any]) -> int:
    return int(created_spec.get("lease_timeout_sec") or DEFAULT_LEASE_TIMEOUT_SEC)


def _resolve_timeout_repeat_threshold(created_spec: dict[str, Any]) -> int:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return int(escalation_policy.get("timeout_repeat_threshold") or DEFAULT_TIMEOUT_REPEAT_THRESHOLD)


def _resolve_repeat_failure_threshold(created_spec: dict[str, Any]) -> int:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return int(
        escalation_policy.get("repeat_failure_threshold") or DEFAULT_REPEAT_FAILURE_THRESHOLD
    )


def _resolve_timeout_backoff_multiplier(created_spec: dict[str, Any]) -> float:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return float(
        escalation_policy.get("timeout_backoff_multiplier") or DEFAULT_TIMEOUT_BACKOFF_MULTIPLIER
    )


def _resolve_timeout_backoff_cap_multiplier(created_spec: dict[str, Any]) -> float:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return float(
        escalation_policy.get("timeout_backoff_cap_multiplier")
        or DEFAULT_TIMEOUT_BACKOFF_CAP_MULTIPLIER
    )


def _resolve_timeout_fingerprint(workflow_id: str, node_id: str) -> str:
    return f"{workflow_id}:{node_id}:{TIMEOUT_FAMILY_RUNTIME}"


def _resolve_provider_fingerprint(provider_id: str) -> str:
    return f"{PROVIDER_FINGERPRINT_PREFIX}:{provider_id}"


def _resolve_repeated_failure_incident_fingerprint(
    workflow_id: str,
    node_id: str,
    failure_fingerprint: str,
) -> str:
    return f"{workflow_id}:{node_id}:repeat-failure:{failure_fingerprint}"


def _resolve_provider_id_for_ticket(
    repository: ControlPlaneRepository,
    connection,
    *,
    ticket: dict[str, Any] | None = None,
    lease_owner: str | None = None,
    failure_detail: dict[str, Any] | None = None,
) -> str | None:
    if failure_detail is not None:
        provider_id = failure_detail.get("provider_id")
        if provider_id:
            return str(provider_id)

    resolved_owner = lease_owner or (str(ticket["lease_owner"]) if ticket and ticket.get("lease_owner") else None)
    if resolved_owner is None:
        return None

    employee = repository.get_employee_projection(resolved_owner, connection=connection)
    if employee is None or not employee.get("provider_id"):
        return None
    return str(employee["provider_id"])


def _is_provider_pause_failure(failure_kind: str) -> bool:
    return failure_kind in PROVIDER_PAUSE_FAILURE_KINDS


def _is_provider_paused(
    repository: ControlPlaneRepository,
    connection,
    provider_id: str | None,
) -> bool:
    if provider_id is None:
        return False
    return repository.has_open_circuit_breaker_for_provider(provider_id, connection=connection)


def _resolve_timeout_root_created_spec(
    repository: ControlPlaneRepository,
    connection,
    created_spec: dict[str, Any],
) -> dict[str, Any]:
    root_spec = created_spec
    parent_ticket_id = created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()
    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        root_spec = parent_spec
        parent_ticket_id = parent_spec.get("parent_ticket_id")
    return root_spec


def _apply_timeout_backoff(current_value: int, root_value: int, multiplier: float, cap_multiplier: float) -> int:
    increased_value = int(current_value * multiplier)
    capped_value = int(root_value * cap_multiplier)
    return max(current_value, min(increased_value, capped_value))


def _calculate_timeout_streak(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    node_id: str,
    created_spec: dict[str, Any],
) -> int:
    streak = 1
    parent_ticket_id = created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()

    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        if parent_spec.get("workflow_id") != workflow_id or parent_spec.get("node_id") != node_id:
            break
        terminal_event = repository.get_latest_ticket_terminal_event(connection, parent_ticket_id)
        if terminal_event is None or terminal_event["event_type"] != EVENT_TICKET_TIMED_OUT:
            break
        if terminal_event["payload"].get("failure_kind") not in TIMEOUT_FAILURE_KINDS:
            break
        streak += 1
        parent_ticket_id = parent_spec.get("parent_ticket_id")

    return streak


def _calculate_failure_streak(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    node_id: str,
    created_spec: dict[str, Any],
    failure_fingerprint: str,
) -> int:
    streak = 1
    parent_ticket_id = created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()

    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        if parent_spec.get("workflow_id") != workflow_id or parent_spec.get("node_id") != node_id:
            break
        terminal_event = repository.get_latest_ticket_terminal_event(connection, parent_ticket_id)
        if terminal_event is None or terminal_event["event_type"] != EVENT_TICKET_FAILED:
            break
        parent_failure_kind = str(terminal_event["payload"].get("failure_kind") or "")
        if _is_provider_pause_failure(parent_failure_kind):
            break
        if terminal_event["payload"].get("failure_fingerprint") != failure_fingerprint:
            break
        streak += 1
        parent_ticket_id = parent_spec.get("parent_ticket_id")

    return streak


def _retry_budget(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(created_spec.get("retry_budget") or current_ticket.get("retry_budget") or 0)


def _retry_count(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(current_ticket.get("retry_count") or created_spec.get("retry_count") or 0)


def _resolve_heartbeat_timeout_sec(current_ticket: dict[str, Any]) -> int:
    return int(current_ticket.get("heartbeat_timeout_sec") or DEFAULT_LEASE_TIMEOUT_SEC)


def _resolve_current_heartbeat_expiry(
    current_ticket: dict[str, Any],
) -> datetime | None:
    heartbeat_expires_at = current_ticket.get("heartbeat_expires_at")
    if heartbeat_expires_at is not None:
        return heartbeat_expires_at

    heartbeat_timeout_sec = current_ticket.get("heartbeat_timeout_sec")
    if heartbeat_timeout_sec is None:
        return None

    last_signal_at = (
        current_ticket.get("last_heartbeat_at")
        or current_ticket.get("started_at")
        or current_ticket.get("updated_at")
    )
    if last_signal_at is None:
        return None

    return last_signal_at + timedelta(seconds=int(heartbeat_timeout_sec))


def _should_retry_failure(
    *,
    current_ticket: dict[str, Any],
    created_spec: dict[str, Any],
    failure_kind: str,
) -> bool:
    retry_budget = _retry_budget(current_ticket, created_spec)
    retry_count = _retry_count(current_ticket, created_spec)
    if retry_count >= retry_budget:
        return False

    escalation_policy = created_spec.get("escalation_policy") or {}
    if failure_kind == "SCHEMA_ERROR":
        return escalation_policy.get("on_schema_error") == "retry"
    return retry_budget > retry_count


def _should_retry_timeout(
    *,
    current_ticket: dict[str, Any],
    created_spec: dict[str, Any],
) -> bool:
    retry_budget = _retry_budget(current_ticket, created_spec)
    retry_count = _retry_count(current_ticket, created_spec)
    if retry_count >= retry_budget:
        return False
    escalation_policy = created_spec.get("escalation_policy") or {}
    return escalation_policy.get("on_timeout") == "retry"


def _should_escalate_repeat_failure(
    *,
    created_spec: dict[str, Any],
    failure_kind: str,
    failure_streak_count: int,
) -> bool:
    if _is_provider_pause_failure(failure_kind):
        return False
    escalation_policy = created_spec.get("escalation_policy") or {}
    return (
        escalation_policy.get("on_repeat_failure") == "escalate_ceo"
        and failure_streak_count >= _resolve_repeat_failure_threshold(created_spec)
    )


def _validate_restore_and_retry_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, incident_ticket_id)
    if latest_terminal_event is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "has no terminal event."
        )
    if latest_terminal_event["event_type"] != EVENT_TICKET_TIMED_OUT:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not a timeout."
        )

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )
    if not _should_retry_timeout(current_ticket=current_ticket, created_spec=created_spec):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the retry budget "
            "is exhausted or timeout retry is disabled."
        )

    return current_ticket, created_spec


def _validate_restore_and_retry_failure_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, incident_ticket_id)
    if latest_terminal_event is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "has no terminal event."
        )
    if latest_terminal_event["event_type"] != EVENT_TICKET_FAILED:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not an ordinary failure."
        )

    latest_failure_kind = str(latest_terminal_event["payload"].get("failure_kind") or "")
    if _is_provider_pause_failure(latest_failure_kind):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not an ordinary failure."
        )

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )
    if not _should_retry_failure(
        current_ticket=current_ticket,
        created_spec=created_spec,
        failure_kind=latest_failure_kind,
    ):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the retry budget "
            "is exhausted or failure retry is disabled."
        )

    return current_ticket, created_spec


def _validate_restore_and_retry_provider_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, incident_ticket_id)
    if latest_terminal_event is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "has no terminal event."
        )
    if latest_terminal_event["event_type"] != EVENT_TICKET_FAILED:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not a provider failure."
        )
    latest_failure_kind = latest_terminal_event["payload"].get("failure_kind")
    if not _is_provider_pause_failure(str(latest_failure_kind)):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not a provider failure."
        )

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )
    if not _should_retry_failure(
        current_ticket=current_ticket,
        created_spec=created_spec,
        failure_kind=str(latest_failure_kind),
    ):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the retry budget "
            "is exhausted or provider retry is disabled."
        )

    return current_ticket, created_spec


def _schedule_retry(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    failed_ticket_id: str,
    node_id: str,
    created_spec: dict[str, Any],
    failure_payload: dict[str, Any],
    retry_source_event_type: str,
    idempotency_key_base: str,
) -> str:
    next_ticket_id = new_prefixed_id("tkt")
    next_attempt_no = int(created_spec.get("attempt_no") or 1) + 1
    next_retry_count = int(created_spec.get("retry_count") or 0) + 1

    retry_event = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_RETRY_SCHEDULED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:retry-scheduled:{failed_ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "ticket_id": failed_ticket_id,
            "node_id": node_id,
            "next_ticket_id": next_ticket_id,
            "next_attempt_no": next_attempt_no,
            "retry_count": next_retry_count,
            "retry_source_event_type": retry_source_event_type,
            "failure_fingerprint": failure_payload["failure_fingerprint"],
        },
        occurred_at=occurred_at,
    )
    if retry_event is None:
        raise RuntimeError("Retry scheduling idempotency conflict.")

    next_ticket_payload = {
        **created_spec,
        "ticket_id": next_ticket_id,
        "parent_ticket_id": failed_ticket_id,
        "attempt_no": next_attempt_no,
        "retry_count": next_retry_count,
        "idempotency_key": f"system-retry-create:{workflow_id}:{next_ticket_id}",
    }
    if retry_source_event_type == EVENT_TICKET_TIMED_OUT:
        root_spec = _resolve_timeout_root_created_spec(repository, connection, created_spec)
        next_ticket_payload["timeout_sla_sec"] = _apply_timeout_backoff(
            int(created_spec.get("timeout_sla_sec") or 0),
            int(root_spec.get("timeout_sla_sec") or 0),
            _resolve_timeout_backoff_multiplier(created_spec),
            _resolve_timeout_backoff_cap_multiplier(created_spec),
        )
        next_ticket_payload["lease_timeout_sec"] = _apply_timeout_backoff(
            _resolve_ticket_lease_timeout_sec(created_spec),
            _resolve_ticket_lease_timeout_sec(root_spec),
            _resolve_timeout_backoff_multiplier(created_spec),
            _resolve_timeout_backoff_cap_multiplier(created_spec),
        )
    created_event = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:retry-create:{next_ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=next_ticket_payload,
        occurred_at=occurred_at,
    )
    if created_event is None:
        raise RuntimeError("Retry ticket creation idempotency conflict.")
    return next_ticket_id


def _auto_close_recovering_incidents_for_completed_ticket(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    completed_ticket_id: str,
) -> None:
    incidents = repository.list_recovering_incidents_for_followup_ticket(
        connection,
        completed_ticket_id,
    )
    for incident in incidents:
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_CLOSED,
            actor_type="system",
            actor_id="runtime",
            workflow_id=workflow_id,
            idempotency_key=f"auto-close-incident:{incident['incident_id']}:{completed_ticket_id}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident["incident_id"],
                "ticket_id": completed_ticket_id,
                "node_id": incident.get("node_id"),
                "provider_id": incident.get("provider_id"),
                "status": INCIDENT_STATUS_CLOSED,
                "followup_action": (incident.get("payload") or {}).get("followup_action"),
                "followup_ticket_id": completed_ticket_id,
                "auto_closed_by": "runtime",
                "close_reason": "Follow-up ticket completed successfully.",
                "incident_type": incident["incident_type"],
            },
            occurred_at=occurred_at,
        )
        if event_row is None:
            raise RuntimeError("Recovering incident auto-close idempotency conflict.")


def _open_timeout_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    timeout_streak_count: int,
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    fingerprint = _resolve_timeout_fingerprint(workflow_id, node_id)
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "incident_type": INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": fingerprint,
        "timeout_streak_count": timeout_streak_count,
        "latest_failure_kind": failure_payload.get("failure_kind"),
        "latest_failure_message": failure_payload.get("failure_message"),
        "latest_failure_fingerprint": failure_payload.get("failure_fingerprint"),
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Circuit breaker opening idempotency conflict.")

    return incident_id


def _open_repeated_failure_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    failure_streak_count: int,
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    failure_fingerprint = str(failure_payload.get("failure_fingerprint") or "unknown-failure")
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "incident_type": INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": _resolve_repeated_failure_incident_fingerprint(
            workflow_id,
            node_id,
            failure_fingerprint,
        ),
        "failure_streak_count": failure_streak_count,
        "latest_failure_kind": failure_payload.get("failure_kind"),
        "latest_failure_message": failure_payload.get("failure_message"),
        "latest_failure_fingerprint": failure_fingerprint,
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Repeated failure incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": incident_payload["fingerprint"],
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Repeated failure circuit breaker opening idempotency conflict.")

    return incident_id


def _open_provider_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    provider_id: str,
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_provider(provider_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    fingerprint = _resolve_provider_fingerprint(provider_id)
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "provider_id": provider_id,
        "incident_type": INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": fingerprint,
        "pause_reason": failure_payload.get("failure_kind"),
        "latest_failure_kind": failure_payload.get("failure_kind"),
        "latest_failure_message": failure_payload.get("failure_message"),
        "latest_failure_fingerprint": failure_payload.get("failure_fingerprint"),
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Provider incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "provider_id": provider_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Provider circuit breaker opening idempotency conflict.")

    return incident_id


def _dispatch_sort_key(ticket: dict[str, Any]) -> tuple[int, datetime, str]:
    priority_rank = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }
    return (
        priority_rank.get(str(ticket.get("priority")).lower(), 4),
        ticket["updated_at"],
        ticket["ticket_id"],
    )


def _add_worker_candidate(
    worker_candidates: list[str],
    worker_by_id: dict[str, set[str]],
    *,
    employee_id: str,
    role_profile_refs: list[str],
) -> None:
    if employee_id in worker_by_id:
        return
    worker_by_id[employee_id] = set(role_profile_refs)
    worker_candidates.append(employee_id)


def _resolve_scheduler_workers(
    repository: ControlPlaneRepository,
    connection,
    workers: list[SchedulerWorkerCandidate] | None,
) -> tuple[list[str], dict[str, set[str]]]:
    worker_candidates: list[str] = []
    worker_by_id: dict[str, set[str]] = {}

    for employee in repository.list_scheduler_worker_candidates(connection):
        _add_worker_candidate(
            worker_candidates,
            worker_by_id,
            employee_id=employee["employee_id"],
            role_profile_refs=list(employee.get("role_profile_refs", [])),
        )

    for worker in workers or []:
        _add_worker_candidate(
            worker_candidates,
            worker_by_id,
            employee_id=worker.employee_id,
            role_profile_refs=list(worker.role_profile_refs),
        )

    return worker_candidates, worker_by_id


def run_scheduler_tick(
    repository: ControlPlaneRepository,
    *,
    idempotency_key: str,
    max_dispatches: int,
    workers: list[SchedulerWorkerCandidate] | None = None,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, idempotency_key)
        if existing_event is not None:
            return _scheduler_duplicate_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
            )

        event_index = 0

        def next_idempotency_key(suffix: str) -> str:
            nonlocal event_index
            key = idempotency_key if event_index == 0 else f"{idempotency_key}:{event_index}:{suffix}"
            event_index += 1
            return key

        changed_state = False
        timed_out_ticket_ids: set[str] = set()
        total_timeout_candidates = repository.list_total_timeout_ticket_candidates(connection, received_at)
        for ticket in total_timeout_candidates:
            timeout_payload = _build_failure_payload(
                failure_kind="TIMEOUT_SLA_EXCEEDED",
                failure_message="Ticket exceeded timeout SLA.",
                failure_detail={"timeout_sla_sec": ticket.get("timeout_sla_sec")},
            )
            timeout_event = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_TIMED_OUT,
                actor_type="system",
                actor_id="scheduler",
                workflow_id=ticket["workflow_id"],
                idempotency_key=next_idempotency_key(f"timed-out:{ticket['ticket_id']}"),
                causation_id=command_id,
                correlation_id=ticket["workflow_id"],
                payload={
                    "ticket_id": ticket["ticket_id"],
                    "node_id": ticket["node_id"],
                    **timeout_payload,
                },
                occurred_at=received_at,
            )
            if timeout_event is None:
                return _scheduler_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                )
            changed_state = True
            timed_out_ticket_ids.add(ticket["ticket_id"])

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            timeout_streak_count = _calculate_timeout_streak(
                repository,
                connection,
                workflow_id=ticket["workflow_id"],
                node_id=ticket["node_id"],
                created_spec=created_spec,
            )
            timeout_threshold = _resolve_timeout_repeat_threshold(created_spec)
            if timeout_streak_count >= timeout_threshold:
                _open_timeout_incident(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    timeout_streak_count=timeout_streak_count,
                    failure_payload=timeout_payload,
                    idempotency_key_base=f"{idempotency_key}:timeout:{ticket['ticket_id']}",
                )
                changed_state = True
                continue
            if _should_retry_timeout(current_ticket=ticket, created_spec=created_spec):
                _schedule_retry(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    failed_ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    created_spec=created_spec,
                    failure_payload=timeout_payload,
                    retry_source_event_type=EVENT_TICKET_TIMED_OUT,
                    idempotency_key_base=f"{idempotency_key}:timeout:{ticket['ticket_id']}",
                )
                changed_state = True

        heartbeat_timeout_candidates = repository.list_heartbeat_timeout_ticket_candidates(
            connection,
            received_at,
        )
        for ticket in heartbeat_timeout_candidates:
            if ticket["ticket_id"] in timed_out_ticket_ids:
                continue
            timeout_payload = _build_failure_payload(
                failure_kind="HEARTBEAT_TIMEOUT",
                failure_message="Ticket missed the required heartbeat window.",
                failure_detail={
                    "heartbeat_expires_at": (
                        ticket["heartbeat_expires_at"].isoformat()
                        if ticket.get("heartbeat_expires_at") is not None
                        else None
                    ),
                    "heartbeat_timeout_sec": ticket.get("heartbeat_timeout_sec"),
                },
            )
            timeout_event = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_TIMED_OUT,
                actor_type="system",
                actor_id="scheduler",
                workflow_id=ticket["workflow_id"],
                idempotency_key=next_idempotency_key(f"heartbeat-timed-out:{ticket['ticket_id']}"),
                causation_id=command_id,
                correlation_id=ticket["workflow_id"],
                payload={
                    "ticket_id": ticket["ticket_id"],
                    "node_id": ticket["node_id"],
                    **timeout_payload,
                },
                occurred_at=received_at,
            )
            if timeout_event is None:
                return _scheduler_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                )
            changed_state = True
            timed_out_ticket_ids.add(ticket["ticket_id"])

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            timeout_streak_count = _calculate_timeout_streak(
                repository,
                connection,
                workflow_id=ticket["workflow_id"],
                node_id=ticket["node_id"],
                created_spec=created_spec,
            )
            timeout_threshold = _resolve_timeout_repeat_threshold(created_spec)
            if timeout_streak_count >= timeout_threshold:
                _open_timeout_incident(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    timeout_streak_count=timeout_streak_count,
                    failure_payload=timeout_payload,
                    idempotency_key_base=f"{idempotency_key}:heartbeat-timeout:{ticket['ticket_id']}",
                )
                changed_state = True
                continue
            if _should_retry_timeout(current_ticket=ticket, created_spec=created_spec):
                _schedule_retry(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    failed_ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    created_spec=created_spec,
                    failure_payload=timeout_payload,
                    retry_source_event_type=EVENT_TICKET_TIMED_OUT,
                    idempotency_key_base=f"{idempotency_key}:heartbeat-timeout:{ticket['ticket_id']}",
                )
                changed_state = True

        repository.refresh_projections(connection)

        worker_candidates, worker_by_id = _resolve_scheduler_workers(repository, connection, workers)

        all_busy_tickets = repository.list_ticket_projections_by_statuses(
            connection,
            [TICKET_STATUS_LEASED, TICKET_STATUS_EXECUTING],
        )
        busy_workers: set[str] = set()
        for ticket in all_busy_tickets:
            owner = ticket.get("lease_owner")
            if owner is None:
                continue
            if ticket["status"] == TICKET_STATUS_EXECUTING:
                busy_workers.add(owner)
                continue
            lease_expiry = ticket.get("lease_expires_at")
            if lease_expiry is not None and lease_expiry > received_at:
                busy_workers.add(owner)

        dispatchable_tickets = sorted(
            repository.list_dispatchable_ticket_projections(connection, received_at),
            key=_dispatch_sort_key,
        )
        dispatched = 0

        for ticket in dispatchable_tickets:
            if dispatched >= max_dispatches:
                break

            node_projection = repository.get_current_node_projection(
                ticket["workflow_id"],
                ticket["node_id"],
                connection=connection,
            )
            if node_projection is None:
                continue
            if (
                node_projection["latest_ticket_id"] != ticket["ticket_id"]
                or node_projection["status"] != NODE_STATUS_PENDING
            ):
                continue
            if repository.has_open_circuit_breaker_for_node(
                ticket["workflow_id"],
                ticket["node_id"],
                connection=connection,
            ):
                continue

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            target_role_profile = created_spec.get("role_profile_ref")
            if not target_role_profile:
                continue
            lease_timeout_sec = _resolve_ticket_lease_timeout_sec(created_spec)

            selected_worker_id = next(
                (
                    worker_id
                    for worker_id in worker_candidates
                    if worker_id not in busy_workers
                    and target_role_profile in worker_by_id[worker_id]
                    and not _is_provider_paused(
                        repository,
                        connection,
                        _resolve_provider_id_for_ticket(
                            repository,
                            connection,
                            lease_owner=worker_id,
                        ),
                    )
                ),
                None,
            )
            if selected_worker_id is None:
                continue

            lease_event = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_LEASED,
                actor_type="system",
                actor_id="scheduler",
                workflow_id=ticket["workflow_id"],
                idempotency_key=next_idempotency_key(
                    f"lease:{ticket['ticket_id']}:{selected_worker_id}"
                ),
                causation_id=command_id,
                correlation_id=ticket["workflow_id"],
                payload={
                    "ticket_id": ticket["ticket_id"],
                    "node_id": ticket["node_id"],
                    "leased_by": selected_worker_id,
                    "lease_timeout_sec": lease_timeout_sec,
                    "lease_expires_at": (received_at + timedelta(seconds=lease_timeout_sec)).isoformat(),
                },
                occurred_at=received_at,
            )
            if lease_event is None:
                return _scheduler_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                )

            busy_workers.add(selected_worker_id)
            dispatched += 1
            changed_state = True

        if changed_state or dispatched > 0:
            repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint="scheduler:tick",
    )


def handle_incident_resolve(
    repository: ControlPlaneRepository,
    payload: IncidentResolveCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _incident_duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
            )

        incident = repository.get_incident_projection(payload.incident_id, connection=connection)
        if incident is None:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=f"Incident {payload.incident_id} does not exist.",
            )
        if incident["status"] != INCIDENT_STATUS_OPEN:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=f"Incident {payload.incident_id} is not open for recovery.",
            )
        if incident.get("circuit_breaker_state") != CIRCUIT_BREAKER_STATE_OPEN:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=(
                    f"Incident {payload.incident_id} cannot be resolved because its circuit breaker "
                    "is not OPEN."
                ),
            )

        workflow_id = incident["workflow_id"]
        followup_ticket_id: str | None = None
        followup_action = payload.followup_action.value
        retry_ticket: dict[str, Any] | None = None
        retry_created_spec: dict[str, Any] | None = None
        if payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT:
            if incident["incident_type"] != INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support timeout retry recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE:
            if incident["incident_type"] != INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support ordinary failure retry recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_failure_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE:
            if incident["incident_type"] != INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support provider retry recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_provider_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )

        resolution_payload = {
            "incident_id": payload.incident_id,
            "node_id": incident.get("node_id"),
            "ticket_id": incident.get("ticket_id"),
            "provider_id": incident.get("provider_id"),
            "resolved_by": payload.resolved_by,
            "resolution_summary": payload.resolution_summary,
            "followup_action": followup_action,
            "followup_ticket_id": None,
            "incident_type": incident["incident_type"],
        }

        breaker_closed_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_CLOSED,
            actor_type="operator",
            actor_id=payload.resolved_by,
            workflow_id=workflow_id,
            idempotency_key=f"{payload.idempotency_key}:breaker-closed",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                **resolution_payload,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_CLOSED,
            },
            occurred_at=received_at,
        )
        if breaker_closed_event is None:
            return _incident_duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
            )

        if payload.followup_action in {
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE,
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT,
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE,
        }:
            assert retry_ticket is not None
            assert retry_created_spec is not None
            retry_source_event_type = (
                EVENT_TICKET_TIMED_OUT
                if payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT
                else EVENT_TICKET_FAILED
            )
            followup_ticket_id = _schedule_retry(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=workflow_id,
                failed_ticket_id=str(incident["ticket_id"]),
                node_id=str(incident["node_id"]),
                created_spec=retry_created_spec,
                failure_payload={
                    "failure_fingerprint": (
                        (incident.get("payload") or {}).get("latest_failure_fingerprint")
                        or incident.get("fingerprint")
                    ),
                },
                retry_source_event_type=retry_source_event_type,
                idempotency_key_base=f"{payload.idempotency_key}:followup-timeout",
            )
            resolution_payload["followup_ticket_id"] = followup_ticket_id

        incident_recovery_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_RECOVERY_STARTED,
            actor_type="operator",
            actor_id=payload.resolved_by,
            workflow_id=workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                **resolution_payload,
                "status": INCIDENT_STATUS_RECOVERING,
            },
            occurred_at=received_at,
        )
        if incident_recovery_event is None:
            return _incident_duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"incident:{payload.incident_id}",
    )


def handle_ticket_cancel(
    repository: ControlPlaneRepository,
    payload: TicketCancelCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _cancel_duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must exist before it can be cancelled.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] == TICKET_STATUS_CANCELLED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} is already cancelled.",
            )
        if current_ticket["status"] == TICKET_STATUS_COMPLETED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} is already completed.",
            )
        if current_ticket["status"] in {TICKET_STATUS_FAILED, TICKET_STATUS_TIMED_OUT}:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} is already terminal.",
            )

        if current_ticket["status"] == TICKET_STATUS_EXECUTING:
            event_row = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_CANCEL_REQUESTED,
                actor_type="operator",
                actor_id=payload.cancelled_by,
                workflow_id=payload.workflow_id,
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=payload.workflow_id,
                payload={
                    "ticket_id": payload.ticket_id,
                    "node_id": payload.node_id,
                    "cancelled_by": payload.cancelled_by,
                    "reason": payload.reason,
                },
                occurred_at=received_at,
            )
            if event_row is None:
                return _cancel_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                )
        else:
            _insert_ticket_cancelled_event(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                cancelled_by=payload.cancelled_by,
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_create(
    repository: ControlPlaneRepository,
    payload: TicketCreateCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-create",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        if current_ticket is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} already exists in projection state.",
            )

        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_node is not None and current_node["status"] != NODE_STATUS_REWORK_REQUIRED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Node {payload.node_id} cannot accept a new ticket while status is "
                    f"{current_node['status']}."
                ),
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="system",
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload=payload.model_dump(mode="json"),
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-create",
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_lease(
    repository: ControlPlaneRepository,
    payload: TicketLeaseCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    lease_expires_at = received_at + timedelta(seconds=payload.lease_timeout_sec)

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-lease",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created before it can be leased.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] not in {TICKET_STATUS_PENDING, TICKET_STATUS_LEASED}:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only be leased from PENDING or LEASED; "
                    f"current status is {current_ticket['status']}."
                ),
            )

        current_owner = current_ticket.get("lease_owner")
        current_expiry = current_ticket.get("lease_expires_at")
        lease_is_active = current_expiry is not None and current_expiry > received_at
        if current_ticket["status"] == TICKET_STATUS_LEASED and lease_is_active:
            if current_owner != payload.leased_by:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=(
                        f"Ticket {payload.ticket_id} is currently leased by {current_owner} until "
                        f"{current_expiry.isoformat()}."
                    ),
                )

        provider_id = _resolve_provider_id_for_ticket(
            repository,
            connection,
            lease_owner=payload.leased_by,
        )
        if _is_provider_paused(repository, connection, provider_id):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} cannot be leased because worker provider "
                    f"{provider_id} is currently paused."
                ),
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_LEASED,
            actor_type="worker",
            actor_id=payload.leased_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "leased_by": payload.leased_by,
                "lease_timeout_sec": payload.lease_timeout_sec,
                "lease_expires_at": lease_expires_at.isoformat(),
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-lease",
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_start(
    repository: ControlPlaneRepository,
    payload: TicketStartCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-start",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created before it can be started.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_node["status"] != NODE_STATUS_PENDING:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only start while node {payload.node_id} is "
                    f"PENDING; current node status is {current_node['status']}."
                ),
            )
        if current_ticket["status"] != TICKET_STATUS_LEASED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only start from LEASED; current ticket status "
                    f"is {current_ticket['status']}."
                ),
            )

        lease_owner = current_ticket.get("lease_owner")
        lease_expires_at = current_ticket.get("lease_expires_at")
        if lease_owner != payload.started_by:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} is leased by {lease_owner}; "
                    f"{payload.started_by} cannot start it."
                ),
            )
        if lease_expires_at is None or lease_expires_at <= received_at:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} lease is missing or expired.",
            )

        provider_id = _resolve_provider_id_for_ticket(
            repository,
            connection,
            ticket=current_ticket,
            lease_owner=lease_owner,
        )
        if _is_provider_paused(repository, connection, provider_id):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} cannot start because worker provider {provider_id} "
                    "is currently paused."
                ),
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_STARTED,
            actor_type="worker",
            actor_id=payload.started_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "started_by": payload.started_by,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-start",
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_heartbeat(
    repository: ControlPlaneRepository,
    payload: TicketHeartbeatCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-heartbeat",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created and started before it can report heartbeat.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] != TICKET_STATUS_EXECUTING or current_node["status"] != NODE_STATUS_EXECUTING:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only report heartbeat while ticket/node status is "
                    f"EXECUTING/EXECUTING; current status is "
                    f"{current_ticket['status']}/{current_node['status']}."
                ),
            )

        lease_owner = current_ticket.get("lease_owner")
        if lease_owner != payload.reported_by:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} is leased by {lease_owner}; "
                    f"{payload.reported_by} cannot report heartbeat."
                ),
            )

        current_heartbeat_expiry = _resolve_current_heartbeat_expiry(current_ticket)
        if current_heartbeat_expiry is None or current_heartbeat_expiry <= received_at:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} heartbeat window is missing or expired.",
            )

        heartbeat_timeout_sec = _resolve_heartbeat_timeout_sec(current_ticket)
        heartbeat_expires_at = received_at + timedelta(seconds=heartbeat_timeout_sec)
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_HEARTBEAT_RECORDED,
            actor_type="worker",
            actor_id=payload.reported_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "reported_by": payload.reported_by,
                "heartbeat_expires_at": heartbeat_expires_at.isoformat(),
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-heartbeat",
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_fail(
    repository: ControlPlaneRepository,
    payload: TicketFailCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-fail",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created and started before it can fail.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] != TICKET_STATUS_EXECUTING or current_node["status"] != NODE_STATUS_EXECUTING:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only fail while ticket/node status is "
                    f"EXECUTING/EXECUTING; current status is "
                    f"{current_ticket['status']}/{current_node['status']}."
                ),
            )

        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)

        failure_payload = _build_failure_payload(
            failure_kind=payload.failure_kind,
            failure_message=payload.failure_message,
            failure_detail=payload.failure_detail,
        )
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_FAILED,
            actor_type="worker",
            actor_id=payload.failed_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "failed_by": payload.failed_by,
                **failure_payload,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-fail",
            )

        next_ticket_id: str | None = None
        provider_id = _resolve_provider_id_for_ticket(
            repository,
            connection,
            ticket=current_ticket,
            failure_detail=failure_payload.get("failure_detail"),
        )
        if _is_provider_pause_failure(payload.failure_kind) and provider_id is not None:
            _open_provider_incident(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                provider_id=provider_id,
                failure_payload=failure_payload,
                idempotency_key_base=payload.idempotency_key,
            )
        elif created_spec is not None:
            failure_streak_count = _calculate_failure_streak(
                repository,
                connection,
                workflow_id=payload.workflow_id,
                node_id=payload.node_id,
                created_spec=created_spec,
                failure_fingerprint=str(failure_payload["failure_fingerprint"]),
            )
            if _should_escalate_repeat_failure(
                created_spec=created_spec,
                failure_kind=payload.failure_kind,
                failure_streak_count=failure_streak_count,
            ):
                _open_repeated_failure_incident(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=payload.workflow_id,
                    ticket_id=payload.ticket_id,
                    node_id=payload.node_id,
                    failure_streak_count=failure_streak_count,
                    failure_payload=failure_payload,
                    idempotency_key_base=payload.idempotency_key,
                )
            elif _should_retry_failure(
                current_ticket=current_ticket,
                created_spec=created_spec,
                failure_kind=payload.failure_kind,
            ):
                next_ticket_id = _schedule_retry(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=payload.workflow_id,
                    failed_ticket_id=payload.ticket_id,
                    node_id=payload.node_id,
                    created_spec=created_spec,
                    failure_payload=failure_payload,
                    retry_source_event_type=EVENT_TICKET_FAILED,
                    idempotency_key_base=payload.idempotency_key,
                )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{next_ticket_id or payload.ticket_id}",
    )


def handle_ticket_result_submit(
    repository: ControlPlaneRepository,
    payload: TicketResultSubmitCommand,
    developer_inspector_store: DeveloperInspectorStore | None = None,
) -> CommandAckEnvelope:
    current_ticket = repository.get_current_ticket_projection(payload.ticket_id)
    current_node = repository.get_current_node_projection(payload.workflow_id, payload.node_id)
    if current_ticket is None or current_node is None:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason="Ticket must be created and started before it can submit a structured result.",
        )

    if current_ticket["status"] == TICKET_STATUS_CANCELLED:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=f"Ticket {payload.ticket_id} is already cancelled.",
        )

    if current_ticket["status"] == TICKET_STATUS_CANCEL_REQUESTED or current_node["status"] == NODE_STATUS_CANCEL_REQUESTED:
        command_id = new_prefixed_id("cmd")
        received_at = now_local()
        with repository.transaction() as connection:
            existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
            if existing_event is not None:
                return _duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    action="ticket-result-submit",
                )
            _insert_ticket_cancelled_event(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                cancelled_by=payload.submitted_by,
                reason="Late result arrived after cancellation was requested.",
                idempotency_key=payload.idempotency_key,
            )
            repository.refresh_projections(connection)
        return CommandAckEnvelope(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            status=CommandAckStatus.ACCEPTED,
            received_at=received_at,
            reason=None,
            causation_hint=f"ticket:{payload.ticket_id}",
        )

    if current_ticket["status"] != TICKET_STATUS_EXECUTING or current_node["status"] != NODE_STATUS_EXECUTING:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=(
                f"Ticket {payload.ticket_id} can only submit a structured result while ticket/node "
                f"status is EXECUTING/EXECUTING; current status is "
                f"{current_ticket['status']}/{current_node['status']}."
            ),
        )

    if payload.result_status == TicketResultStatus.FAILED:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind=payload.failure_kind or "RUNTIME_ERROR",
                failure_message=payload.failure_message or payload.summary,
                failure_detail=payload.failure_detail,
                idempotency_key=payload.idempotency_key,
            ),
        )

    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)

    if created_spec is None:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="SCHEMA_ERROR",
                failure_message="Ticket result validation could not load the created ticket spec.",
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )

    try:
        validate_output_payload(
            schema_ref=str(created_spec.get("output_schema_ref") or ""),
            schema_version=int(created_spec.get("output_schema_version") or 0),
            submitted_schema_version=payload.schema_version,
            payload=payload.payload,
        )
    except ValueError as exc:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="SCHEMA_ERROR",
                failure_message=str(exc),
                failure_detail={
                    "schema_ref": created_spec.get("output_schema_ref"),
                    "schema_version": created_spec.get("output_schema_version"),
                },
                idempotency_key=payload.idempotency_key,
            ),
        )

    allowed_write_set = list(created_spec.get("allowed_write_set") or [])
    violating_paths = [
        item.path for item in payload.written_artifacts if not _match_allowed_write_set(item.path, allowed_write_set)
    ]
    if violating_paths:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="WRITE_SET_VIOLATION",
                failure_message="Structured result attempted to write outside the allowed write set.",
                failure_detail={
                    "violating_paths": violating_paths,
                    "allowed_write_set": allowed_write_set,
                },
                idempotency_key=payload.idempotency_key,
            ),
        )

    return handle_ticket_completed(
        repository,
        TicketCompletedCommand(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            node_id=payload.node_id,
            completed_by=payload.submitted_by,
            completion_summary=payload.summary,
            artifact_refs=payload.artifact_refs,
            review_request=payload.review_request,
            idempotency_key=payload.idempotency_key,
        ),
        developer_inspector_store,
    )


def handle_ticket_completed(
    repository: ControlPlaneRepository,
    payload: TicketCompletedCommand,
    developer_inspector_store: DeveloperInspectorStore | None = None,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    persisted_artifacts: list[PersistedDeveloperInspectorArtifact] = []

    try:
        with repository.transaction() as connection:
            existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
            if existing_event is not None:
                return _duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    action="ticket-complete",
                )

            current_node = repository.get_current_node_projection(
                payload.workflow_id,
                payload.node_id,
                connection=connection,
            )
            if current_node is None:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason="Ticket must be created and started before it can be completed.",
                )
            if current_node["status"] != NODE_STATUS_EXECUTING:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=(
                        f"Node {payload.node_id} cannot accept a ticket result while status is "
                        f"{current_node['status']}."
                    ),
                )
            if current_node["latest_ticket_id"] != payload.ticket_id:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason="Node projection no longer points at this ticket.",
                )

            current_ticket = repository.get_current_ticket_projection(
                payload.ticket_id,
                connection=connection,
            )
            if current_ticket is None:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason="Ticket projection is missing for the currently executing node.",
                )
            if (
                current_ticket["workflow_id"] != payload.workflow_id
                or current_ticket["node_id"] != payload.node_id
            ):
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason="Ticket projection does not match the requested workflow or node.",
                )
            if current_ticket["status"] != TICKET_STATUS_EXECUTING:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=(
                        f"Ticket {payload.ticket_id} cannot be completed while status is "
                        f"{current_ticket['status']}."
                    ),
                )

            event_row = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_COMPLETED,
                actor_type="worker",
                actor_id=payload.completed_by,
                workflow_id=payload.workflow_id,
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=payload.workflow_id,
                payload={
                    "ticket_id": payload.ticket_id,
                    "node_id": payload.node_id,
                    "completion_summary": payload.completion_summary,
                    "artifact_refs": payload.artifact_refs,
                    "board_review_requested": payload.review_request is not None,
                },
                occurred_at=received_at,
            )
            if event_row is None:
                return _duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    action="ticket-complete",
                )

            causation_hint = f"ticket:{payload.ticket_id}"
            if payload.review_request is not None:
                if (
                    payload.review_request.developer_inspector_refs is not None
                    and developer_inspector_store is None
                ):
                    raise RuntimeError("Developer inspector store is required to export inspector artifacts.")
                if (
                    developer_inspector_store is not None
                    and payload.review_request.developer_inspector_refs is not None
                ):
                    persisted_artifacts = export_latest_compile_artifacts_to_developer_inspector(
                        repository,
                        developer_inspector_store,
                        payload.ticket_id,
                        payload.review_request.developer_inspector_refs,
                        connection=connection,
                    )
                approval = repository.create_approval_request(
                    connection,
                    workflow_id=payload.workflow_id,
                    approval_type=payload.review_request.review_type.value,
                    requested_by=payload.completed_by,
                    review_pack=_build_review_pack(
                        payload=payload,
                        trigger_event_id=event_row["event_id"],
                        command_target_version=int(event_row["sequence_no"]),
                        occurred_at=received_at,
                    ),
                    available_actions=[action.value for action in payload.review_request.available_actions],
                    draft_defaults={
                        "selected_option_id": payload.review_request.draft_selected_option_id,
                        "comment_template": payload.review_request.comment_template,
                    },
                    inbox_title=payload.review_request.inbox_title or payload.review_request.title,
                    inbox_summary=payload.review_request.inbox_summary or payload.completion_summary,
                    badges=payload.review_request.badges,
                    priority=payload.review_request.priority.value,
                    occurred_at=received_at,
                    idempotency_key=f"{payload.idempotency_key}:approval-request",
                )
                causation_hint = f"approval:{approval['approval_id']}"

            _auto_close_recovering_incidents_for_completed_ticket(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                completed_ticket_id=payload.ticket_id,
            )
            repository.refresh_projections(connection)
    except Exception:
        if developer_inspector_store is not None:
            for artifact in persisted_artifacts:
                developer_inspector_store.delete_ref(artifact.ref)
        raise

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=causation_hint,
    )


def handle_scheduler_tick(
    repository: ControlPlaneRepository,
    payload: SchedulerTickCommand,
) -> CommandAckEnvelope:
    return run_scheduler_tick(
        repository,
        idempotency_key=payload.idempotency_key,
        max_dispatches=payload.max_dispatches,
        workers=payload.workers,
    )
