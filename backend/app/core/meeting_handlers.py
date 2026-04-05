from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    MeetingRequestCommand,
    ReviewAction,
    ReviewPriority,
    ReviewType,
    TicketBoardReviewRequest,
    TicketCreateCommand,
    TicketEscalationPolicy,
    TicketReviewEvidence,
    TicketReviewOption,
)
from app.core.constants import (
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_STARTED,
    EVENT_TICKET_CREATED,
)
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    meeting_id: str | None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason=None,
        causation_hint=(f"meeting:{meeting_id}" if meeting_id else None),
    )


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    reason: str,
    meeting_id: str | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=(f"meeting:{meeting_id}" if meeting_id else None),
    )


def _normalize_topic(topic: str) -> str:
    return " ".join(topic.strip().lower().split())


def _meeting_responsibility_for_role(role_type: str) -> str:
    normalized = role_type.strip().lower()
    if normalized == "frontend_engineer":
        return "implementation feasibility"
    if normalized == "checker":
        return "validation pressure"
    if normalized == "ui_designer":
        return "surface contract impact"
    return "technical decision input"


def _build_meeting_review_request(
    *,
    topic: str,
    ticket_id: str,
) -> TicketBoardReviewRequest:
    consensus_artifact_ref = f"art://runtime/{ticket_id}/consensus-document.json"
    return TicketBoardReviewRequest(
        review_type=ReviewType.MEETING_ESCALATION,
        priority=ReviewPriority.HIGH,
        title=f"Review technical decision: {topic}",
        subtitle="Technical decision meeting output is ready for board lock-in.",
        blocking_scope="WORKFLOW",
        trigger_reason="Cross-role technical decision needs explicit board confirmation.",
        why_now="Downstream delivery should not continue before this technical decision is locked.",
        recommended_action=ReviewAction.APPROVE,
        recommended_option_id="meeting_consensus_lock",
        recommendation_summary="The meeting converged on one technical direction with concrete follow-up work.",
        options=[
            TicketReviewOption(
                option_id="meeting_consensus_lock",
                label="Lock meeting consensus",
                summary="Proceed with the converged technical decision and continue delivery on the agreed path.",
                artifact_refs=[consensus_artifact_ref],
                pros=["Keeps implementation and validation aligned."],
                cons=["Defers non-critical alternative paths."],
                risks=["A later change will need a fresh governance decision."],
            )
        ],
        evidence_summary=[
            TicketReviewEvidence(
                evidence_id="ev_meeting_consensus",
                source_type="MEETING_CONSENSUS",
                headline="Meeting converged on one technical direction",
                summary="Participants aligned on one technical direction and attached concrete downstream work.",
                source_ref=consensus_artifact_ref,
            )
        ],
        available_actions=[
            ReviewAction.APPROVE,
            ReviewAction.REJECT,
            ReviewAction.MODIFY_CONSTRAINTS,
        ],
        draft_selected_option_id="meeting_consensus_lock",
        inbox_title=f"Review technical decision: {topic}",
        inbox_summary="A technical decision meeting consensus is ready for board review.",
        badges=["meeting", "board_gate", "technical_decision"],
    )


def handle_meeting_request(
    repository: ControlPlaneRepository,
    payload: MeetingRequestCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    meeting_id = new_prefixed_id("mtg")
    meeting_suffix = meeting_id.removeprefix("mtg_")
    ticket_id = f"tkt_meeting_{meeting_suffix}"
    node_id = f"node_meeting_{meeting_suffix}"

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            existing_meeting_id = str((existing_event["payload"] or {}).get("meeting_id") or "").strip() or None
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                meeting_id=existing_meeting_id,
            )

        workflow = repository.get_workflow_projection(payload.workflow_id, connection=connection)
        if workflow is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Workflow {payload.workflow_id} does not exist.",
            )

        normalized_topic = _normalize_topic(payload.topic)
        existing_meeting = repository.find_open_meeting_by_normalized_topic(
            payload.workflow_id,
            normalized_topic,
            connection=connection,
        )
        if existing_meeting is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=(
                    f"Workflow {payload.workflow_id} already has an open meeting for topic "
                    f"'{payload.topic}'."
                ),
                meeting_id=str(existing_meeting["meeting_id"]),
            )

        participants: list[dict[str, Any]] = []
        recorder_projection: dict[str, Any] | None = None
        for employee_id in payload.participant_employee_ids:
            employee = repository.get_employee_projection(employee_id, connection=connection)
            if employee is None:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    reason=f"Participant {employee_id} does not exist.",
                )
            if str(employee.get("state") or "").upper() != "ACTIVE":
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    reason=f"Participant {employee_id} is not active.",
                )
            if not bool(employee.get("board_approved")):
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    reason=f"Participant {employee_id} is not board approved.",
                )
            if employee_id == payload.recorder_employee_id:
                recorder_projection = employee
            participants.append(
                {
                    "employee_id": employee_id,
                    "role_type": str(employee.get("role_type") or ""),
                    "meeting_responsibility": _meeting_responsibility_for_role(
                        str(employee.get("role_type") or "")
                    ),
                    "is_recorder": employee_id == payload.recorder_employee_id,
                }
            )

        if recorder_projection is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason="Recorder must be one of the active participants.",
            )

        role_profile_refs = list(recorder_projection.get("role_profile_refs") or [])
        if not role_profile_refs:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Recorder {payload.recorder_employee_id} has no role profile refs.",
            )

        ticket_payload = TicketCreateCommand(
            ticket_id=ticket_id,
            workflow_id=payload.workflow_id,
            node_id=node_id,
            parent_ticket_id=None,
            attempt_no=1,
            role_profile_ref=str(role_profile_refs[0]),
            constraints_ref="meeting_room_constraints_v1",
            input_artifact_refs=list(payload.input_artifact_refs),
            context_query_plan={
                "keywords": ["meeting", "technical decision", *[item["role_type"] for item in participants]],
                "semantic_queries": [payload.topic],
                "max_context_tokens": 3000,
            },
            acceptance_criteria=[
                "Must complete the technical decision meeting in structured rounds.",
                "Must produce a structured consensus document.",
                "Must keep the final decision inside the current MVP boundary unless evidence justifies widening scope.",
            ],
            output_schema_ref="consensus_document",
            output_schema_version=1,
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[f"reports/meeting/{meeting_id}/*"],
            retry_budget=1,
            priority="high",
            timeout_sla_sec=1800,
            deadline_at=workflow.get("deadline_at"),
            tenant_id=str(workflow.get("tenant_id") or DEFAULT_TENANT_ID),
            workspace_id=str(workflow.get("workspace_id") or DEFAULT_WORKSPACE_ID),
            excluded_employee_ids=[],
            auto_review_request=_build_meeting_review_request(topic=payload.topic, ticket_id=ticket_id),
            meeting_context={
                "meeting_id": meeting_id,
                "meeting_type": payload.meeting_type.value,
                "topic": payload.topic,
                "participant_employee_ids": list(payload.participant_employee_ids),
                "recorder_employee_id": payload.recorder_employee_id,
                "max_rounds": payload.max_rounds,
            },
            escalation_policy=TicketEscalationPolicy(
                on_timeout="retry",
                on_schema_error="retry",
                on_repeat_failure="escalate_ceo",
            ),
            idempotency_key=f"{payload.idempotency_key}:ticket-create",
        )

        requested_event = repository.insert_event(
            connection,
            event_type=EVENT_MEETING_REQUESTED,
            actor_type="operator",
            actor_id="operator",
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "meeting_id": meeting_id,
                "meeting_type": payload.meeting_type.value,
                "topic": payload.topic,
                "participant_employee_ids": list(payload.participant_employee_ids),
                "recorder_employee_id": payload.recorder_employee_id,
                "source_ticket_id": ticket_id,
                "source_node_id": node_id,
            },
            occurred_at=received_at,
        )
        if requested_event is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                meeting_id=meeting_id,
            )

        opened_event = repository.insert_event(
            connection,
            event_type=EVENT_MEETING_STARTED,
            actor_type="system",
            actor_id="meeting-room",
            workflow_id=payload.workflow_id,
            idempotency_key=f"{payload.idempotency_key}:opened",
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "meeting_id": meeting_id,
                "meeting_type": payload.meeting_type.value,
                "topic": payload.topic,
                "source_ticket_id": ticket_id,
                "source_node_id": node_id,
            },
            occurred_at=received_at,
        )
        if opened_event is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                meeting_id=meeting_id,
            )

        ticket_event = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="system",
            workflow_id=payload.workflow_id,
            idempotency_key=ticket_payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload=ticket_payload.model_dump(mode="json"),
            occurred_at=received_at,
        )
        if ticket_event is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=f"Meeting ticket {ticket_id} could not be created.",
                meeting_id=meeting_id,
            )

        repository.create_meeting_projection(
            connection,
            meeting_id=meeting_id,
            workflow_id=payload.workflow_id,
            meeting_type=payload.meeting_type.value,
            topic=payload.topic,
            normalized_topic=normalized_topic,
            status="OPEN",
            source_ticket_id=ticket_id,
            source_node_id=node_id,
            opened_at=received_at,
            updated_at=received_at,
            recorder_employee_id=payload.recorder_employee_id,
            participants=participants,
            rounds=[],
            current_round=None,
            review_status=None,
            review_pack_id=None,
            closed_at=None,
            consensus_summary=None,
            no_consensus_reason=None,
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"meeting:{meeting_id}",
    )
