from __future__ import annotations

from typing import Any

from app.contracts.commands import (
    BoardApproveCommand,
    BoardRejectCommand,
    CommandAckEnvelope,
    CommandAckStatus,
    ModifyConstraintsCommand,
)
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    EMPLOYEE_STATE_ACTIVE,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
)
from app.core.ids import new_prefixed_id
from app.core.staffing_containment import contain_employee_active_tickets
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    reason: str,
    causation_hint: str | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=causation_hint,
    )


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    approval_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical board command was already accepted.",
        causation_hint=f"approval:{approval_id}",
    )


def _validate_open_approval(
    approval: dict[str, Any] | None,
    *,
    approval_id: str,
    review_pack_id: str,
    review_pack_version: int,
    command_target_version: int,
) -> str | None:
    if approval is None:
        return "Approval target not found."
    if approval["approval_id"] != approval_id or approval["review_pack_id"] != review_pack_id:
        return "Approval target does not match review pack."
    if approval["status"] != APPROVAL_STATUS_OPEN:
        return f"Approval is already resolved with status {approval['status']}."
    if approval["review_pack_version"] != review_pack_version:
        return "Review pack outdated. Reload review-room projection."
    if approval["command_target_version"] != command_target_version:
        return "Projection target outdated. Reload review-room projection."
    return None


def _validate_blocked_projection(
    repository: ControlPlaneRepository,
    approval: dict[str, Any],
) -> str | None:
    subject = approval["payload"].get("review_pack", {}).get("subject", {})
    workflow_id = approval["workflow_id"]
    ticket_id = subject.get("source_ticket_id")
    node_id = subject.get("source_node_id")
    if ticket_id is None or node_id is None:
        return None

    ticket_projection = repository.get_current_ticket_projection(ticket_id)
    node_projection = repository.get_current_node_projection(workflow_id, node_id)
    if ticket_projection is None or node_projection is None:
        return "Ticket or node projection for this approval is missing. Reload dashboard state."
    if ticket_projection["status"] != TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Ticket is not currently blocked for board review."
    if node_projection["status"] != NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Node is not currently blocked for board review."
    if ticket_projection["workflow_id"] != workflow_id or ticket_projection["node_id"] != node_id:
        return "Ticket projection does not match the approval target."
    if node_projection["latest_ticket_id"] != ticket_id:
        return "Node projection no longer points at this approval ticket."
    return None


def _apply_employee_change_approval(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> str | None:
    if approval["approval_type"] != "CORE_HIRE_APPROVAL":
        return None

    review_pack = approval["payload"].get("review_pack") or {}
    employee_change = review_pack.get("employee_change") or {}
    change_kind = str(employee_change.get("change_kind") or "")

    if change_kind == "EMPLOYEE_HIRE":
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-hired",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": employee_change["employee_id"],
                "role_type": employee_change["role_type"],
                "skill_profile": dict(employee_change.get("skill_profile") or {}),
                "personality_profile": dict(employee_change.get("personality_profile") or {}),
                "aesthetic_profile": dict(employee_change.get("aesthetic_profile") or {}),
                "state": EMPLOYEE_STATE_ACTIVE,
                "board_approved": True,
                "provider_id": employee_change.get("provider_id"),
                "role_profile_refs": list(employee_change.get("role_profile_refs") or []),
            },
            occurred_at=occurred_at,
        )
        return str(employee_change["employee_id"])

    if change_kind == "EMPLOYEE_REPLACE":
        replaced_employee_id = str(employee_change["employee_id"])
        replacement_employee_id = str(employee_change["replacement_employee_id"])
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-replacement-hired",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": replacement_employee_id,
                "role_type": employee_change["replacement_role_type"],
                "skill_profile": dict(employee_change.get("replacement_skill_profile") or {}),
                "personality_profile": dict(employee_change.get("replacement_personality_profile") or {}),
                "aesthetic_profile": dict(employee_change.get("replacement_aesthetic_profile") or {}),
                "state": EMPLOYEE_STATE_ACTIVE,
                "board_approved": True,
                "provider_id": employee_change.get("replacement_provider_id"),
                "role_profile_refs": list(employee_change.get("replacement_role_profile_refs") or []),
            },
            occurred_at=occurred_at,
        )
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_REPLACED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-replaced",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": replaced_employee_id,
                "replacement_employee_id": replacement_employee_id,
            },
            occurred_at=occurred_at,
        )
        contain_employee_active_tickets(
            repository,
            connection,
            employee_id=replaced_employee_id,
            action_kind=EVENT_EMPLOYEE_REPLACED,
            reason="Board-approved employee replacement removed the original assignee from active duty.",
            occurred_at=occurred_at,
            command_id=command_id,
            idempotency_key_base=idempotency_key,
            replacement_employee_id=replacement_employee_id,
        )
        return replacement_employee_id

    return None


def handle_board_approve(
    repository: ControlPlaneRepository,
    payload: BoardApproveCommand,
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
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_APPROVED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "selected_option_id": payload.selected_option_id,
                "board_comment": payload.board_comment,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        employee_causation_hint = _apply_employee_change_approval(
            repository,
            connection,
            approval=approval,
            command_id=command_id,
            occurred_at=received_at,
            idempotency_key=payload.idempotency_key,
        )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_APPROVED,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "APPROVE",
                "selected_option_id": payload.selected_option_id,
                "board_comment": payload.board_comment,
            },
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=(
            f"employee:{employee_causation_hint}"
            if employee_causation_hint is not None
            else f"approval:{payload.approval_id}"
        ),
    )


def handle_board_reject(
    repository: ControlPlaneRepository,
    payload: BoardRejectCommand,
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
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REJECTED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "board_comment": payload.board_comment,
                "rejection_reasons": payload.rejection_reasons,
                "decision_action": "REJECT",
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_REJECTED,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "REJECT",
                "board_comment": payload.board_comment,
                "rejection_reasons": payload.rejection_reasons,
            },
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{payload.approval_id}",
    )


def handle_modify_constraints(
    repository: ControlPlaneRepository,
    payload: ModifyConstraintsCommand,
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
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REJECTED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
                "decision_action": "MODIFY_CONSTRAINTS",
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "MODIFY_CONSTRAINTS",
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
            },
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{payload.approval_id}",
    )
