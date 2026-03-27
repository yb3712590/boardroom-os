from __future__ import annotations

from datetime import datetime

from app.contracts.commands import CommandAckEnvelope, CommandAckStatus, TicketCompletedCommand
from app.core.constants import (
    EVENT_TICKET_COMPLETED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
)
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


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


def handle_ticket_completed(
    repository: ControlPlaneRepository,
    payload: TicketCompletedCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                status=CommandAckStatus.DUPLICATE,
                received_at=received_at,
                reason="An identical ticket-complete command was already accepted.",
                causation_hint=f"ticket:{payload.ticket_id}",
            )

        current_node = repository.get_current_node_projection(payload.workflow_id, payload.node_id)
        if current_node is not None and current_node["status"] in {
            NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
            NODE_STATUS_COMPLETED,
        }:
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                status=CommandAckStatus.REJECTED,
                received_at=received_at,
                reason=(
                    f"Node {payload.node_id} cannot accept a new ticket result while status is "
                    f"{current_node['status']}."
                ),
                causation_hint=f"node:{payload.node_id}",
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
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                status=CommandAckStatus.DUPLICATE,
                received_at=received_at,
                reason="An identical ticket-complete command was already accepted.",
                causation_hint=f"ticket:{payload.ticket_id}",
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
