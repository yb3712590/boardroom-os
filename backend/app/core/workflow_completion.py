from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)

ACTIVE_TICKET_STATUSES = {
    "PENDING",
    "LEASED",
    "EXECUTING",
    "BLOCKED_FOR_BOARD_REVIEW",
    "REWORK_REQUIRED",
    "CANCEL_REQUESTED",
}
DELIVERY_MAINLINE_STAGES = {"BUILD", "CHECK", "REVIEW"}
DELIVERY_MAINLINE_OUTPUT_SCHEMA_STAGE = {
    SOURCE_CODE_DELIVERY_SCHEMA_REF: "BUILD",
    UI_MILESTONE_REVIEW_SCHEMA_REF: "REVIEW",
}


@dataclass(frozen=True)
class WorkflowCloseoutCompletion:
    closeout_ticket: dict[str, Any]
    closeout_terminal_event: dict[str, Any]


def _is_redundant_active_closeout_ticket(
    ticket: dict[str, Any],
    *,
    closeout_ticket: dict[str, Any],
    closeout_completed_at: datetime,
    created_spec: dict[str, Any] | None,
) -> bool:
    ticket_id = str(ticket.get("ticket_id") or "")
    if ticket_id == str(closeout_ticket.get("ticket_id") or ""):
        return False
    if str(ticket.get("status") or "") not in ACTIVE_TICKET_STATUSES:
        return False
    if str(ticket.get("node_id") or "") != str(closeout_ticket.get("node_id") or ""):
        return False
    if str((created_spec or {}).get("output_schema_ref") or "") != DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return False
    updated_at = ticket.get("updated_at")
    if not isinstance(updated_at, datetime):
        return False
    return updated_at <= closeout_completed_at


def _normalized_delivery_stage(created_spec: dict[str, Any] | None) -> str:
    if not isinstance(created_spec, dict):
        return ""
    return str(created_spec.get("delivery_stage") or "").strip().upper()


def _resolved_maker_ticket_spec(
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(created_spec, dict):
        return None
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
    if isinstance(maker_ticket_spec, dict) and maker_ticket_spec:
        return maker_ticket_spec
    maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
    if not maker_ticket_id:
        return None
    return created_specs_by_ticket.get(maker_ticket_id)


def delivery_mainline_stage_for_ticket(
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> str | None:
    delivery_stage = _normalized_delivery_stage(created_spec)
    if delivery_stage in DELIVERY_MAINLINE_STAGES:
        return delivery_stage
    output_schema_ref = str((created_spec or {}).get("output_schema_ref") or "")
    inferred_stage = DELIVERY_MAINLINE_OUTPUT_SCHEMA_STAGE.get(output_schema_ref)
    if inferred_stage is not None:
        return inferred_stage
    if (
        isinstance(created_spec, dict)
        and output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF
    ):
        maker_ticket_spec = _resolved_maker_ticket_spec(created_spec, created_specs_by_ticket)
        maker_delivery_stage = delivery_mainline_stage_for_ticket(maker_ticket_spec, created_specs_by_ticket)
        if maker_delivery_stage in DELIVERY_MAINLINE_STAGES:
            return maker_delivery_stage
    return None


def ticket_has_delivery_mainline_evidence(
    created_spec: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> bool:
    return delivery_mainline_stage_for_ticket(created_spec, created_specs_by_ticket) is not None


def workflow_has_delivery_mainline_evidence(
    created_specs_by_ticket: dict[str, dict[str, Any]],
) -> bool:
    return any(
        ticket_has_delivery_mainline_evidence(created_spec, created_specs_by_ticket)
        for created_spec in created_specs_by_ticket.values()
    )


def infer_workflow_current_stage(
    *,
    nodes: list[dict[str, Any]],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    closeout_completion: WorkflowCloseoutCompletion | None = None,
) -> str:
    if closeout_completion is not None:
        return "closeout"
    if not nodes:
        return "project_init"

    latest_node = max(
        nodes,
        key=lambda item: (
            item.get("updated_at") or datetime.min,
            str(item.get("node_id") or ""),
        ),
    )
    created_spec = created_specs_by_ticket.get(str(latest_node.get("latest_ticket_id") or ""))
    if created_spec is None:
        return "project_init"

    delivery_stage = delivery_mainline_stage_for_ticket(created_spec, created_specs_by_ticket)
    if delivery_stage:
        return delivery_stage.lower()

    output_schema_ref = str(created_spec.get("output_schema_ref") or "")
    if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF or output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return "plan"
    return "project_init"


def resolve_workflow_closeout_completion(
    *,
    tickets: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    has_open_approval: bool,
    has_open_incident: bool,
    created_specs_by_ticket: dict[str, dict[str, Any]],
    ticket_terminal_events_by_ticket: dict[str, dict[str, Any] | None],
) -> WorkflowCloseoutCompletion | None:
    if not nodes or any(str(node.get("status") or "") != "COMPLETED" for node in nodes):
        return None
    if has_open_approval or has_open_incident:
        return None
    if not workflow_has_delivery_mainline_evidence(created_specs_by_ticket):
        return None

    closeout_candidates: list[tuple[datetime, str, dict[str, Any], dict[str, Any]]] = []
    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id") or "")
        created_spec = created_specs_by_ticket.get(ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "") != DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
            continue
        terminal_event = ticket_terminal_events_by_ticket.get(ticket_id)
        if not isinstance(terminal_event, dict):
            continue
        if str(terminal_event.get("event_type") or "") != "TICKET_COMPLETED":
            continue
        occurred_at = terminal_event.get("occurred_at")
        if not isinstance(occurred_at, datetime):
            continue
        closeout_candidates.append((occurred_at, ticket_id, ticket, terminal_event))

    if not closeout_candidates:
        return None

    closeout_completed_at, _, closeout_ticket, closeout_terminal_event = max(
        closeout_candidates,
        key=lambda item: (item[0], item[1]),
    )
    if any(
        not _is_redundant_active_closeout_ticket(
            ticket,
            closeout_ticket=closeout_ticket,
            closeout_completed_at=closeout_completed_at,
            created_spec=created_specs_by_ticket.get(str(ticket.get("ticket_id") or "")),
        )
        for ticket in tickets
        if str(ticket.get("status") or "") in ACTIVE_TICKET_STATUSES
    ):
        return None
    return WorkflowCloseoutCompletion(
        closeout_ticket=closeout_ticket,
        closeout_terminal_event=closeout_terminal_event,
    )
