from __future__ import annotations

from typing import Any

from app.core.constants import (
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_REJECTED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
)
from app.core.graph_identity import apply_legacy_graph_contract_compat, resolve_ticket_graph_identity
from app.core.output_schemas import GOVERNANCE_DOCUMENT_SCHEMA_REFS
from app.core.review_subjects import resolve_review_subject_identity
from app.core.runtime_node_views import build_runtime_graph_node_views
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.db.repository import ControlPlaneRepository


_ROLE_PROFILE_TO_ROLE_TYPE = {
    "ui_designer_primary": "frontend_engineer",
    "frontend_engineer_primary": "frontend_engineer",
    "checker_primary": "checker",
    "backend_engineer_primary": "backend_engineer",
    "database_engineer_primary": "database_engineer",
    "platform_sre_primary": "platform_sre",
    "architect_primary": "governance_architect",
    "cto_primary": "governance_cto",
}

_ROLE_PROFILE_TO_CAPABILITY = {
    "ui_designer_primary": ("frontend", "delivery_slice"),
    "frontend_engineer_primary": ("frontend", "delivery_slice"),
    "checker_primary": ("quality", "release_guard"),
    "backend_engineer_primary": ("backend", "service_delivery"),
    "database_engineer_primary": ("data", "data_reliability"),
    "platform_sre_primary": ("platform", "runtime_operations"),
    "architect_primary": ("architecture", "architecture"),
    "cto_primary": ("architecture", "architecture"),
}

_MIN_PARTICIPANTS = 2
_MAX_PARTICIPANTS = 4
_FAILED_TICKET_MEETING_OUTPUT_SCHEMAS = {
    "consensus_document",
    "ui_milestone_review",
    *GOVERNANCE_DOCUMENT_SCHEMA_REFS,
}


def _normalize_topic(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _role_type_for_profile(role_profile_ref: str | None) -> str | None:
    return _ROLE_PROFILE_TO_ROLE_TYPE.get(str(role_profile_ref or "").strip())


def _capability_for_profile(role_profile_ref: str | None) -> tuple[str | None, str | None]:
    return _ROLE_PROFILE_TO_CAPABILITY.get(str(role_profile_ref or "").strip(), (None, None))


def _approved_active_employees(
    repository: ControlPlaneRepository,
) -> list[dict[str, Any]]:
    return repository.list_employee_projections(states=["ACTIVE"], board_approved_only=True)


def _find_employee_by_id(
    employees: list[dict[str, Any]],
    employee_id: str | None,
) -> dict[str, Any] | None:
    normalized = str(employee_id or "").strip()
    if not normalized:
        return None
    for employee in employees:
        if str(employee.get("employee_id") or "").strip() == normalized:
            return employee
    return None


def _find_owner_employee(
    employees: list[dict[str, Any]],
    *,
    current_ticket: dict[str, Any] | None,
    role_profile_ref: str | None,
) -> dict[str, Any] | None:
    lease_owner = str((current_ticket or {}).get("lease_owner") or "").strip()
    if lease_owner:
        matched = _find_employee_by_id(employees, lease_owner)
        if matched is not None:
            return matched

    normalized_profile = str(role_profile_ref or "").strip()
    normalized_role_type = _role_type_for_profile(normalized_profile)
    for employee in employees:
        employee_profiles = set(employee.get("role_profile_refs") or [])
        if normalized_profile == "ui_designer_primary" and "frontend_engineer_primary" in employee_profiles:
            return employee
        if normalized_profile in employee_profiles:
            return employee
    if normalized_role_type is None:
        return None
    for employee in employees:
        if str(employee.get("role_type") or "").strip() == normalized_role_type:
            return employee
    return None


def _select_best_capability_match(
    employees: list[dict[str, Any]],
    *,
    excluded_employee_ids: set[str],
    target_role_type: str | None,
    target_role_profile_ref: str | None,
    target_domain: str | None,
    target_scope: str | None,
) -> dict[str, Any] | None:
    best: tuple[int, str, dict[str, Any]] | None = None
    for employee in employees:
        employee_id = str(employee.get("employee_id") or "").strip()
        if not employee_id or employee_id in excluded_employee_ids:
            continue
        score = 0
        if target_role_type and str(employee.get("role_type") or "").strip() == target_role_type:
            score += 100
        if target_role_profile_ref and target_role_profile_ref in set(employee.get("role_profile_refs") or []):
            score += 80
        if (
            target_role_profile_ref == "ui_designer_primary"
            and "frontend_engineer_primary" in set(employee.get("role_profile_refs") or [])
        ):
            score += 70
        skill_profile = employee.get("skill_profile_json") or employee.get("skill_profile") or {}
        if target_domain and str(skill_profile.get("primary_domain") or "").strip() == target_domain:
            score += 20
        if target_scope and str(skill_profile.get("system_scope") or "").strip() == target_scope:
            score += 10
        if score <= 0:
            continue
        candidate = (score, employee_id, employee)
        if best is None or candidate > best:
            best = candidate
    return None if best is None else best[2]


def _select_participants(
    repository: ControlPlaneRepository,
    *,
    current_ticket: dict[str, Any] | None,
    role_profile_ref: str | None,
) -> tuple[list[str], str | None, str]:
    employees = _approved_active_employees(repository)
    owner_employee = _find_owner_employee(
        employees,
        current_ticket=current_ticket,
        role_profile_ref=role_profile_ref,
    )
    if owner_employee is None:
        return [], None, "No active board-approved owner candidate matches the source node."

    participants: list[str] = [str(owner_employee["employee_id"])]
    excluded = {str(owner_employee["employee_id"])}
    owner_role_type = str(owner_employee.get("role_type") or "").strip()
    target_roles: list[tuple[str | None, str | None, str | None, str | None]] = []

    if owner_role_type != "checker":
        target_roles.append(("checker", "checker_primary", "quality", "release_guard"))
    else:
        target_roles.append(("frontend_engineer", "frontend_engineer_primary", "frontend", "delivery_slice"))

    for target_role_type, target_profile, target_domain, target_scope in target_roles:
        match = _select_best_capability_match(
            employees,
            excluded_employee_ids=excluded,
            target_role_type=target_role_type,
            target_role_profile_ref=target_profile,
            target_domain=target_domain,
            target_scope=target_scope,
        )
        if match is None:
            continue
        match_id = str(match["employee_id"])
        participants.append(match_id)
        excluded.add(match_id)

    if len(participants) < _MIN_PARTICIPANTS:
        fallback_domain, fallback_scope = _capability_for_profile(role_profile_ref)
        match = _select_best_capability_match(
            employees,
            excluded_employee_ids=excluded,
            target_role_type=None,
            target_role_profile_ref=role_profile_ref,
            target_domain=fallback_domain,
            target_scope=fallback_scope,
        )
        if match is not None:
            participants.append(str(match["employee_id"]))
            excluded.add(str(match["employee_id"]))

    participants = _dedupe(participants)[:_MAX_PARTICIPANTS]
    if len(participants) < _MIN_PARTICIPANTS:
        return participants, str(owner_employee["employee_id"]), "Meeting requires at least two active board-approved participants."
    return participants, str(owner_employee["employee_id"]), "Eligible meeting participants resolved from the current roster."


def _workflow_graph_context(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph_snapshot = build_ticket_graph_snapshot(
        repository,
        workflow_id,
        connection=connection,
    )
    runtime_views = build_runtime_graph_node_views(
        repository,
        workflow_id,
        graph_snapshot=graph_snapshot,
        connection=connection,
    )
    graph_node_by_ticket_id = {
        str(node.ticket_id): node
        for node in graph_snapshot.nodes
        if str(node.ticket_id or "").strip()
    }
    return graph_node_by_ticket_id, runtime_views


def _build_ticket_failed_candidate(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_ref: str | None,
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_ticket_id = str(trigger_ref or "").strip()
    if not source_ticket_id:
        return []

    with repository.connection() as connection:
        current_ticket = repository.get_current_ticket_projection(source_ticket_id, connection=connection)
        terminal_event = repository.get_latest_ticket_terminal_event(connection, source_ticket_id)
        created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id)
        if created_spec is None:
            return [
                {
                    "source_graph_node_id": None,
                    "source_node_id": None,
                    "source_ticket_id": source_ticket_id,
                    "topic": f"Resolve blocker for {source_ticket_id}",
                    "reason": "Source ticket create spec is missing.",
                    "participant_employee_ids": [],
                    "recorder_employee_id": None,
                    "input_artifact_refs": [],
                    "eligible": False,
                    "eligibility_reason": "Source ticket create spec is missing.",
                }
            ]
        created_spec = apply_legacy_graph_contract_compat(created_spec)
        source_identity = resolve_ticket_graph_identity(
            ticket_id=source_ticket_id,
            created_spec=created_spec,
            runtime_node_id=str(created_spec.get("node_id") or "").strip() or None,
        )
        graph_node_by_ticket_id, runtime_views = _workflow_graph_context(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
        source_graph_node_id = source_identity.graph_node_id
        source_node_id = source_identity.runtime_node_id
        current_graph_node = graph_node_by_ticket_id.get(source_ticket_id)
        current_view = runtime_views.get(source_graph_node_id)
        if current_graph_node is None or current_view is None:
            raise ValueError(
                f"Meeting candidate source ticket {source_ticket_id} is missing graph/runtime truth for {source_graph_node_id}."
            )

    topic = f"Resolve cross-role blocker on {source_node_id or source_ticket_id}"
    normalized_topic = _normalize_topic(topic)
    existing_meeting = repository.find_open_meeting_by_normalized_topic(workflow_id, normalized_topic)
    participants, recorder_employee_id, participant_reason = _select_participants(
        repository,
        current_ticket=current_ticket,
        role_profile_ref=str(created_spec.get("role_profile_ref") or ""),
    )

    eligibility_reason = "Eligible failed-ticket meeting candidate."
    eligible = True

    if approvals:
        eligible = False
        eligibility_reason = "Workflow is already waiting for board review."
    elif terminal_event is None or terminal_event["event_type"] not in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
        eligible = False
        eligibility_reason = "Source ticket is not on a failed terminal event."
    elif str(created_spec.get("output_schema_ref") or "").strip() not in _FAILED_TICKET_MEETING_OUTPUT_SCHEMAS:
        eligible = False
        eligibility_reason = "Only decision-oriented tickets are eligible for automatic meeting recovery."
    elif str(current_view.ticket_id or "").strip() != source_ticket_id:
        eligible = False
        eligibility_reason = "Source graph lane already moved to a newer ticket."
    else:
        retry_budget = int((current_ticket or {}).get("retry_budget") or 0)
        retry_count = int((current_ticket or {}).get("retry_count") or 0)
        incident_for_ticket = any(str(item.get("ticket_id") or "").strip() == source_ticket_id for item in incidents)
        ticket_status = str((current_ticket or {}).get("status") or "").strip()
        if (
            ticket_status not in {TICKET_STATUS_FAILED, TICKET_STATUS_TIMED_OUT, TICKET_STATUS_REWORK_REQUIRED}
            and terminal_event["event_type"] == EVENT_TICKET_FAILED
        ):
            eligible = False
            eligibility_reason = f"Source ticket status {ticket_status or 'UNKNOWN'} is not eligible for a meeting."
        elif retry_count < retry_budget and not incident_for_ticket:
            eligible = False
            eligibility_reason = "Serial retries are still available on this ticket."
        elif existing_meeting is not None:
            eligible = False
            eligibility_reason = "Workflow already has an open meeting for this topic."
        elif len(participants) < _MIN_PARTICIPANTS:
            eligible = False
            eligibility_reason = participant_reason

    return [
        {
            "source_graph_node_id": source_graph_node_id,
            "source_node_id": source_node_id or None,
            "source_ticket_id": source_ticket_id,
            "topic": topic,
            "reason": (
                f"Ticket {source_ticket_id} failed and serial retries are no longer the cheapest path."
            ),
            "participant_employee_ids": participants,
            "recorder_employee_id": recorder_employee_id,
            "input_artifact_refs": list(created_spec.get("input_artifact_refs") or []),
            "eligible": eligible,
            "eligibility_reason": eligibility_reason,
        }
    ]


def _build_approval_candidate(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_ref: str | None,
) -> list[dict[str, Any]]:
    approval_id = str(trigger_ref or "").strip()
    if not approval_id:
        return []

    with repository.connection() as connection:
        approval = repository.get_approval_by_id(connection, approval_id)
        if approval is None:
            return []
        review_pack = (approval.get("payload") or {}).get("review_pack") or {}
        subject = review_pack.get("subject") or {}
        source_ticket_id, source_graph_node_id, source_node_id = resolve_review_subject_identity(
            repository,
            workflow_id=workflow_id,
            subject=subject,
            connection=connection,
        )
        current_ticket = repository.get_current_ticket_projection(source_ticket_id, connection=connection)
        graph_node_by_ticket_id, runtime_views = _workflow_graph_context(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
        current_graph_node = graph_node_by_ticket_id.get(source_ticket_id) if source_ticket_id else None
        current_view = runtime_views.get(str(source_graph_node_id or "").strip()) if source_graph_node_id else None
        created_spec = (
            repository.get_latest_ticket_created_payload(connection, source_ticket_id)
            if source_ticket_id
            else None
        )
        source_node_id = source_node_id or (str(current_view.node_id) if current_view is not None else None)

    topic = f"Re-align {source_node_id or approval_id} after board feedback"
    normalized_topic = _normalize_topic(topic)
    existing_meeting = repository.find_open_meeting_by_normalized_topic(workflow_id, normalized_topic)
    role_profile_ref = str((created_spec or {}).get("role_profile_ref") or "")
    participants, recorder_employee_id, participant_reason = _select_participants(
        repository,
        current_ticket=current_ticket,
        role_profile_ref=role_profile_ref,
    )

    eligible = True
    eligibility_reason = "Eligible approval-resolution meeting candidate."
    approval_status = str(approval.get("status") or "").strip()
    approval_type = str(approval.get("approval_type") or "").strip()

    if approval_status not in {APPROVAL_STATUS_REJECTED, APPROVAL_STATUS_MODIFIED_CONSTRAINTS}:
        eligible = False
        eligibility_reason = f"Approval status {approval_status or 'UNKNOWN'} does not require a meeting."
    elif approval_type == "MEETING_ESCALATION":
        eligible = False
        eligibility_reason = "Meeting escalation reviews cannot recursively trigger another meeting."
    elif not source_ticket_id or current_ticket is None or current_graph_node is None or current_view is None:
        raise ValueError(
            f"Approval meeting candidate {approval_id} is missing graph/runtime truth for {source_graph_node_id or '<missing>'}."
        )
    elif str(current_view.ticket_id or "").strip() != source_ticket_id:
        eligible = False
        eligibility_reason = "Approval source graph lane already moved to a new ticket."
    elif existing_meeting is not None:
        eligible = False
        eligibility_reason = "Workflow already has an open meeting for this topic."
    elif len(participants) < _MIN_PARTICIPANTS:
        eligible = False
        eligibility_reason = participant_reason

    return [
        {
            "source_graph_node_id": source_graph_node_id,
            "source_node_id": source_node_id or None,
            "source_ticket_id": source_ticket_id or None,
            "topic": topic,
            "reason": "Board feedback requires a bounded cross-role technical decision before continuing.",
            "participant_employee_ids": participants,
            "recorder_employee_id": recorder_employee_id,
            "input_artifact_refs": list((created_spec or {}).get("input_artifact_refs") or []),
            "eligible": eligible,
            "eligibility_reason": eligibility_reason,
        }
    ]


def build_ceo_meeting_candidates(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_type: str,
    trigger_ref: str | None,
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_trigger = str(trigger_type or "").strip()
    if normalized_trigger == EVENT_TICKET_FAILED:
        return _build_ticket_failed_candidate(
            repository,
            workflow_id=workflow_id,
            trigger_ref=trigger_ref,
            approvals=approvals,
            incidents=incidents,
        )
    if normalized_trigger == "APPROVAL_RESOLVED":
        return _build_approval_candidate(
            repository,
            workflow_id=workflow_id,
            trigger_ref=trigger_ref,
        )
    return []


__all__ = ["build_ceo_meeting_candidates"]
