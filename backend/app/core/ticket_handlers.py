from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    SchedulerWorkerCandidate,
    SchedulerTickCommand,
    TicketCompletedCommand,
    TicketCreateCommand,
    TicketFailCommand,
    TicketLeaseCommand,
    TicketStartCommand,
)
from app.core.constants import (
    DEFAULT_LEASE_TIMEOUT_SEC,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
)
from app.core.ids import new_prefixed_id
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
        "developer_inspector_refs": review_request.developer_inspector_refs,
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


def _retry_budget(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(created_spec.get("retry_budget") or current_ticket.get("retry_budget") or 0)


def _retry_count(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(current_ticket.get("retry_count") or created_spec.get("retry_count") or 0)


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
        timeout_candidates = repository.list_timed_out_ticket_candidates(connection, received_at)
        for ticket in timeout_candidates:
            timeout_payload = _build_failure_payload(
                failure_kind="TIMEOUT",
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

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
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

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            target_role_profile = created_spec.get("role_profile_ref")
            if not target_role_profile:
                continue

            selected_worker_id = next(
                (
                    worker_id
                    for worker_id in worker_candidates
                    if worker_id not in busy_workers
                    and target_role_profile in worker_by_id[worker_id]
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
                    "lease_timeout_sec": DEFAULT_LEASE_TIMEOUT_SEC,
                    "lease_expires_at": (
                        received_at + timedelta(seconds=DEFAULT_LEASE_TIMEOUT_SEC)
                    ).isoformat(),
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
        if created_spec is not None and _should_retry_failure(
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


def handle_ticket_completed(
    repository: ControlPlaneRepository,
    payload: TicketCompletedCommand,
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

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        if current_ticket is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection is missing for the currently executing node.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
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

        repository.refresh_projections(connection)

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
