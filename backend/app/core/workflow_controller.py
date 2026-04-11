from __future__ import annotations

import json
from typing import Any

from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED, EVENT_WORKFLOW_CREATED
from app.core.execution_targets import infer_execution_contract_payload, employee_supports_execution_contract
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.db.repository import ControlPlaneRepository

_APPROVED_REVIEW_STATUSES = {"APPROVED", "APPROVED_WITH_NOTES"}
_ROLE_PROFILE_BY_TARGET_ROLE = {
    "frontend_engineer": "frontend_engineer_primary",
    "frontend_engineer_primary": "frontend_engineer_primary",
    "backend_engineer": "backend_engineer_primary",
    "backend_engineer_primary": "backend_engineer_primary",
    "database_engineer": "database_engineer_primary",
    "database_engineer_primary": "database_engineer_primary",
    "platform_sre": "platform_sre_primary",
    "platform_sre_primary": "platform_sre_primary",
    "checker": "checker_primary",
    "checker_primary": "checker_primary",
    "architect": "architect_primary",
    "architect_primary": "architect_primary",
    "governance_architect": "architect_primary",
    "cto": "cto_primary",
    "cto_primary": "cto_primary",
    "governance_cto": "cto_primary",
}
_ROLE_TYPE_BY_ROLE_PROFILE = {
    "frontend_engineer_primary": "frontend_engineer",
    "backend_engineer_primary": "backend_engineer",
    "database_engineer_primary": "database_engineer",
    "platform_sre_primary": "platform_sre",
    "checker_primary": "checker",
    "architect_primary": "governance_architect",
    "cto_primary": "governance_cto",
}
_MEETING_REQUIRED_HINTS = (
    "技术决策会议",
    "technical decision meeting",
    "meeting escalation",
    "meeting gate",
)


def backlog_followup_key_to_node_id(ticket_key: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "_"
        for character in str(ticket_key).strip()
    ).strip("_")
    return f"node_backlog_followup_{normalized}" if normalized else "node_backlog_followup"


def workflow_controller_effect(snapshot: dict[str, Any]) -> str:
    state = str((snapshot.get("controller_state") or {}).get("state") or "").strip()
    if state == "WAIT_FOR_BOARD":
        return "WAIT_FOR_BOARD"
    if state == "WAIT_FOR_INCIDENT":
        return "WAIT_FOR_INCIDENT"
    if state == "READY_TICKET":
        return "RUN_SCHEDULER_TICK"
    if state == "WAIT_FOR_RUNTIME":
        return "WAIT_FOR_RUNTIME"
    if state in {"ARCHITECT_REQUIRED", "MEETING_REQUIRED", "STAFFING_REQUIRED"}:
        return state
    if state == "READY_FOR_FANOUT":
        return "READY_FOR_FANOUT"
    return "NO_IMMEDIATE_FOLLOWUP"


def _normalize_topic(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _read_ticket_json_artifact(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str,
    connection,
) -> dict[str, Any] | None:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        return None
    artifact = next(
        (
            item
            for item in repository.list_ticket_artifacts(ticket_id, connection=connection)
            if str(item.get("storage_relpath") or "").strip()
            and str(item.get("artifact_ref") or "").strip().endswith(".json")
        ),
        None,
    )
    if artifact is None:
        return None
    try:
        return json.loads(
            artifact_store.read_bytes(str(artifact["storage_relpath"])).decode("utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _load_workflow_hard_constraints(connection, workflow_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM events
        WHERE workflow_id = ? AND event_type IN (?, ?)
        ORDER BY sequence_no DESC
        """,
        (workflow_id, EVENT_BOARD_DIRECTIVE_RECEIVED, EVENT_WORKFLOW_CREATED),
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        constraints = [
            str(item).strip()
            for item in list(payload.get("hard_constraints") or [])
            if str(item).strip()
        ]
        if constraints:
            return constraints
    return []


def _select_default_assignee(
    employees: list[dict[str, Any]],
    *,
    role_profile_ref: str,
    output_schema_ref: str,
) -> str | None:
    execution_contract = infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if execution_contract is None:
        return None
    for employee in sorted(employees, key=lambda item: str(item.get("employee_id") or "")):
        if str(employee.get("state") or "") != "ACTIVE":
            continue
        if not employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            continue
        return str(employee["employee_id"])
    return None


def _resolve_target_role_profile(raw_ticket: dict[str, Any]) -> str:
    explicit_role = str(
        raw_ticket.get("target_role")
        or raw_ticket.get("owner_role")
        or raw_ticket.get("role_profile_ref")
        or ""
    ).strip().lower()
    if explicit_role:
        mapped = _ROLE_PROFILE_BY_TARGET_ROLE.get(explicit_role)
        if mapped is not None:
            return mapped

    haystack = " ".join(
        [
            str(raw_ticket.get("name") or ""),
            *(str(item) for item in list(raw_ticket.get("scope") or [])),
        ]
    ).lower()
    if any(token in haystack for token in ("deploy", "monitor", "ops", "platform", "发布", "监控", "运维")):
        return "platform_sre_primary"
    if any(token in haystack for token in ("database", "schema", "migration", "sql", "数据库", "索引")):
        return "database_engineer_primary"
    if any(token in haystack for token in ("backend", "api", "service", "后端", "认证", "rbac")):
        return "backend_engineer_primary"
    return "frontend_engineer_primary"


def _latest_completed_backlog_ticket(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_ref: str | None,
    connection,
) -> tuple[str | None, dict[str, Any], dict[str, Any] | None]:
    trigger_ticket_id = str(trigger_ref or "").strip()
    if trigger_ticket_id:
        created_spec = repository.get_latest_ticket_created_payload(connection, trigger_ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "").strip() == BACKLOG_RECOMMENDATION_SCHEMA_REF:
            payload = _read_ticket_json_artifact(repository, ticket_id=trigger_ticket_id, connection=connection)
            return trigger_ticket_id, created_spec, payload

    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ? AND status = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id, "COMPLETED"),
    ).fetchall()
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref == BACKLOG_RECOMMENDATION_SCHEMA_REF:
            payload = _read_ticket_json_artifact(repository, ticket_id=ticket_id, connection=connection)
            if isinstance(payload, dict):
                return ticket_id, created_spec, payload
            continue
        if output_schema_ref != MAKER_CHECKER_VERDICT_SCHEMA_REF:
            continue
        maker_checker_context = created_spec.get("maker_checker_context") or {}
        maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
        maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
        if not isinstance(maker_ticket_spec, dict) or not maker_ticket_spec:
            maker_ticket_spec = (
                repository.get_latest_ticket_created_payload(connection, maker_ticket_id)
                if maker_ticket_id
                else {}
            ) or {}
        if str(maker_ticket_spec.get("output_schema_ref") or "").strip() != BACKLOG_RECOMMENDATION_SCHEMA_REF:
            continue
        terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
        completion_payload = terminal_event.get("payload") if terminal_event is not None else {}
        review_status = str(
            (completion_payload or {}).get("maker_checker_summary", {}).get("review_status")
            or (completion_payload or {}).get("review_status")
            or ""
        ).strip()
        if review_status not in _APPROVED_REVIEW_STATUSES:
            continue
        payload = _read_ticket_json_artifact(repository, ticket_id=maker_ticket_id, connection=connection)
        if isinstance(payload, dict):
            return maker_ticket_id, maker_ticket_spec, payload
    return None, {}, None


def _build_followup_ticket_plans(
    *,
    backlog_ticket_id: str,
    backlog_created_spec: dict[str, Any],
    backlog_payload: dict[str, Any],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommended_tickets: dict[str, dict[str, Any]] = {}
    dependency_map: dict[str, list[str]] = {}
    ordered_ticket_keys: list[str] = []

    for section in list(backlog_payload.get("sections") or []):
        if not isinstance(section, dict):
            continue
        content_json = section.get("content_json")
        if not isinstance(content_json, dict):
            continue
        raw_tickets = content_json.get("tickets")
        if isinstance(raw_tickets, list):
            for raw_ticket in raw_tickets:
                if not isinstance(raw_ticket, dict):
                    continue
                ticket_key = str(raw_ticket.get("ticket_id") or "").strip()
                if not ticket_key:
                    continue
                recommended_tickets[ticket_key] = raw_ticket
                if ticket_key not in ordered_ticket_keys:
                    ordered_ticket_keys.append(ticket_key)
        raw_dependency_graph = content_json.get("dependency_graph")
        if isinstance(raw_dependency_graph, list):
            for raw_dependency in raw_dependency_graph:
                if not isinstance(raw_dependency, dict):
                    continue
                ticket_key = str(raw_dependency.get("ticket_id") or "").strip()
                if not ticket_key:
                    continue
                dependency_map[ticket_key] = [
                    str(item).strip()
                    for item in list(raw_dependency.get("depends_on") or [])
                    if str(item).strip()
                ]
        raw_sequence = content_json.get("recommended_sequence")
        if isinstance(raw_sequence, list):
            sequence_ticket_keys: list[str] = []
            for item in raw_sequence:
                prefix = str(item or "").strip().split(" ", 1)[0]
                if prefix:
                    sequence_ticket_keys.append(prefix)
            if sequence_ticket_keys:
                ordered_ticket_keys = list(dict.fromkeys(sequence_ticket_keys + ordered_ticket_keys))

    existing_ticket_ids_by_node_id = {
        str(node.get("node_id") or ""): str(node.get("latest_ticket_id") or "")
        for node in workflow_nodes
        if str(node.get("node_id") or "").strip() and str(node.get("latest_ticket_id") or "").strip()
    }

    followup_ticket_plans: list[dict[str, Any]] = []
    for ticket_key in ordered_ticket_keys:
        raw_ticket = recommended_tickets.get(ticket_key)
        if not isinstance(raw_ticket, dict):
            continue
        node_id = backlog_followup_key_to_node_id(ticket_key)
        role_profile_ref = _resolve_target_role_profile(raw_ticket)
        task_scope = [
            str(item).strip()
            for item in list(raw_ticket.get("scope") or [])
            if str(item).strip()
        ]
        output_schema_ref = SOURCE_CODE_DELIVERY_SCHEMA_REF
        execution_contract = infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        ) or {}
        followup_ticket_plans.append(
            {
                "ticket_key": ticket_key,
                "node_id": node_id,
                "task_name": str(raw_ticket.get("name") or ticket_key).strip() or ticket_key,
                "summary": (
                    str(raw_ticket.get("summary") or raw_ticket.get("name") or ticket_key).strip()
                    or ticket_key
                ),
                "scope": task_scope,
                "role_profile_ref": role_profile_ref,
                "role_type": _ROLE_TYPE_BY_ROLE_PROFILE[role_profile_ref],
                "output_schema_ref": output_schema_ref,
                "required_capability_tags": list(execution_contract.get("required_capability_tags") or []),
                "assignee_employee_id": _select_default_assignee(
                    employees,
                    role_profile_ref=role_profile_ref,
                    output_schema_ref=output_schema_ref,
                ),
                "dependency_ticket_keys": list(dependency_map.get(ticket_key) or []),
                "dependency_gate_refs": [
                    existing_ticket_ids_by_node_id.get(backlog_followup_key_to_node_id(dependency_key))
                    for dependency_key in list(dependency_map.get(ticket_key) or [])
                    if existing_ticket_ids_by_node_id.get(backlog_followup_key_to_node_id(dependency_key))
                ],
                "existing_ticket_id": existing_ticket_ids_by_node_id.get(node_id),
                "source_ticket_id": backlog_ticket_id,
                "source_node_id": str(backlog_created_spec.get("node_id") or "").strip() or None,
            }
        )
    return followup_ticket_plans


def _active_board_approved_employees(
    employees: list[dict[str, Any]],
    *,
    role_profile_ref: str,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for employee in employees:
        if str(employee.get("state") or "") != "ACTIVE":
            continue
        if not bool(employee.get("board_approved")):
            continue
        if role_profile_ref in set(employee.get("role_profile_refs") or []):
            matched.append(employee)
    return sorted(matched, key=lambda item: str(item.get("employee_id") or ""))


def _has_approved_architect_document(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> bool:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ? AND status = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id, "COMPLETED"),
    ).fetchall()
    for row in rows:
        created_spec = repository.get_latest_ticket_created_payload(connection, str(row["ticket_id"])) or {}
        if str(created_spec.get("output_schema_ref") or "").strip() != MAKER_CHECKER_VERDICT_SCHEMA_REF:
            continue
        maker_checker_context = created_spec.get("maker_checker_context") or {}
        maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
        if not isinstance(maker_ticket_spec, dict) or not maker_ticket_spec:
            maker_ticket_spec = (
                repository.get_latest_ticket_created_payload(
                    connection,
                    str(maker_checker_context.get("maker_ticket_id") or ""),
                )
                or {}
            )
        if str(maker_ticket_spec.get("role_profile_ref") or "").strip() != "architect_primary":
            continue
        if str(maker_ticket_spec.get("output_schema_ref") or "").strip() != ARCHITECTURE_BRIEF_SCHEMA_REF:
            continue
        terminal_event = repository.get_latest_ticket_terminal_event(connection, str(row["ticket_id"]))
        completion_payload = terminal_event.get("payload") if terminal_event is not None else {}
        review_status = str(
            (completion_payload or {}).get("maker_checker_summary", {}).get("review_status")
            or (completion_payload or {}).get("review_status")
            or ""
        ).strip()
        if review_status in _APPROVED_REVIEW_STATUSES:
            return True
    return False


def _has_approved_meeting_evidence(*, workflow_id: str, connection) -> bool:
    row = connection.execute(
        """
        SELECT meeting_id
        FROM meeting_projection
        WHERE workflow_id = ? AND closed_at IS NOT NULL AND review_status IN (?, ?)
        ORDER BY closed_at DESC, meeting_id DESC
        LIMIT 1
        """,
        (workflow_id, "APPROVED", "APPROVED_WITH_NOTES"),
    ).fetchone()
    return row is not None


def _build_controller_meeting_candidate(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    source_ticket_id: str,
    source_node_id: str | None,
    employees: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    connection,
) -> dict[str, Any] | None:
    architect_employees = _active_board_approved_employees(
        employees,
        role_profile_ref="architect_primary",
    )
    checker_employees = _active_board_approved_employees(
        employees,
        role_profile_ref="checker_primary",
    )
    if not architect_employees or not checker_employees:
        return None

    topic = f"Lock implementation boundary for {source_node_id or source_ticket_id}"
    normalized_topic = _normalize_topic(topic)
    existing_meeting = repository.find_open_meeting_by_normalized_topic(
        workflow_id,
        normalized_topic,
        connection=connection,
    )
    source_created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id) or {}
    eligible = not approvals and not incidents and existing_meeting is None
    eligibility_reason = "Eligible controller meeting candidate."
    if approvals:
        eligibility_reason = "Workflow is already waiting for board review."
    elif incidents:
        eligibility_reason = "Workflow incident must be resolved before requesting another meeting."
    elif existing_meeting is not None:
        eligibility_reason = "Workflow already has an open meeting for this topic."

    return {
        "source_node_id": source_node_id,
        "source_ticket_id": source_ticket_id,
        "topic": topic,
        "reason": "Implementation boundary still needs one explicit technical decision meeting before execution starts.",
        "participant_employee_ids": [
            str(architect_employees[0]["employee_id"]),
            str(checker_employees[0]["employee_id"]),
        ],
        "recorder_employee_id": str(architect_employees[0]["employee_id"]),
        "input_artifact_refs": list(source_created_spec.get("input_artifact_refs") or []),
        "eligible": eligible,
        "eligibility_reason": eligibility_reason,
    }


def build_workflow_controller_view(
    repository: ControlPlaneRepository,
    *,
    workflow: dict[str, Any],
    tickets: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    trigger_ref: str | None,
    meeting_candidates: list[dict[str, Any]],
    connection,
) -> dict[str, Any]:
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    hard_constraints = _load_workflow_hard_constraints(connection, workflow_id)
    backlog_ticket_id, backlog_created_spec, backlog_payload = _latest_completed_backlog_ticket(
        repository,
        workflow_id=workflow_id,
        trigger_ref=trigger_ref,
        connection=connection,
    )
    followup_ticket_plans: list[dict[str, Any]] = []
    task_type = "steady_state"
    deliverable_kind = None
    coordination_mode = "wait"
    if backlog_ticket_id and isinstance(backlog_payload, dict):
        followup_ticket_plans = _build_followup_ticket_plans(
            backlog_ticket_id=backlog_ticket_id,
            backlog_created_spec=backlog_created_spec,
            backlog_payload=backlog_payload,
            workflow_nodes=nodes,
            employees=employees,
        )
        if followup_ticket_plans:
            task_type = "implementation_fanout"
            deliverable_kind = SOURCE_CODE_DELIVERY_SCHEMA_REF
            coordination_mode = "fanout"

    requires_architect = any("architect_primary" in item.lower() for item in hard_constraints)
    requires_meeting = any(any(token in item.lower() for token in _MEETING_REQUIRED_HINTS) for item in hard_constraints)
    staffing_gaps = sorted(
        {
            plan["role_profile_ref"]
            for plan in followup_ticket_plans
            if plan.get("existing_ticket_id") is None and not plan.get("assignee_employee_id")
        }
    )

    controller_state = {
        "state": "NO_IMMEDIATE_FOLLOWUP",
        "recommended_action": "NO_ACTION",
        "blocking_reason": None,
    }
    controller_meeting_candidate = None

    if approvals:
        controller_state = {
            "state": "WAIT_FOR_BOARD",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Workflow is waiting for board review.",
        }
    elif incidents:
        controller_state = {
            "state": "WAIT_FOR_INCIDENT",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Workflow has an open incident.",
        }
    elif any(ticket["status"] in {"LEASED", "EXECUTING"} for ticket in tickets):
        controller_state = {
            "state": "WAIT_FOR_RUNTIME",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "A leased ticket is still executing.",
        }
    elif any(ticket["status"] == "PENDING" for ticket in tickets):
        controller_state = {
            "state": "READY_TICKET",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Pending tickets already exist on the current mainline.",
        }
    elif followup_ticket_plans:
        active_architects = _active_board_approved_employees(employees, role_profile_ref="architect_primary")
        if requires_architect and not active_architects:
            controller_state = {
                "state": "ARCHITECT_REQUIRED",
                "recommended_action": "HIRE_EMPLOYEE",
                "blocking_reason": "Architect hard constraint is active but no board-approved architect is on the roster.",
            }
        elif requires_architect and not _has_approved_architect_document(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        ):
            controller_state = {
                "state": "ARCHITECT_REQUIRED",
                "recommended_action": "NO_ACTION",
                "blocking_reason": "At least one approved architect_primary governance document is required before implementation fanout.",
            }
        elif requires_meeting and not _has_approved_meeting_evidence(workflow_id=workflow_id, connection=connection):
            controller_meeting_candidate = _build_controller_meeting_candidate(
                repository,
                workflow_id=workflow_id,
                source_ticket_id=backlog_ticket_id,
                source_node_id=str(backlog_created_spec.get("node_id") or "").strip() or None,
                employees=employees,
                approvals=approvals,
                incidents=incidents,
                connection=connection,
            )
            controller_state = {
                "state": "MEETING_REQUIRED",
                "recommended_action": "REQUEST_MEETING" if controller_meeting_candidate is not None else "NO_ACTION",
                "blocking_reason": "A technical decision meeting must approve the implementation boundary before fanout.",
            }
        elif staffing_gaps:
            controller_state = {
                "state": "STAFFING_REQUIRED",
                "recommended_action": "HIRE_EMPLOYEE",
                "blocking_reason": "At least one required implementation capability is missing from the active roster.",
            }
        else:
            controller_state = {
                "state": "READY_FOR_FANOUT",
                "recommended_action": "CREATE_TICKET",
                "blocking_reason": None,
            }

    combined_meeting_candidates = list(meeting_candidates)
    if controller_meeting_candidate is not None:
        combined_meeting_candidates.append(controller_meeting_candidate)

    task_sensemaking = {
        "task_type": task_type,
        "deliverable_kind": deliverable_kind,
        "coordination_mode": coordination_mode,
        "source_ticket_id": backlog_ticket_id,
        "source_node_id": str(backlog_created_spec.get("node_id") or "").strip() or None,
        "hard_constraints": hard_constraints,
    }
    capability_plan = {
        "required_capabilities": sorted(
            {
                capability
                for plan in followup_ticket_plans
                for capability in list(plan.get("required_capability_tags") or [])
            }
        ),
        "optional_capabilities": [],
        "staffing_gaps": staffing_gaps,
        "requires_architect": requires_architect,
        "requires_meeting": requires_meeting,
        "followup_ticket_plans": followup_ticket_plans,
    }
    if controller_state["recommended_action"] == "HIRE_EMPLOYEE":
        if controller_state["state"] == "ARCHITECT_REQUIRED":
            capability_plan["recommended_hire"] = {
                "role_type": "governance_architect",
                "role_profile_refs": ["architect_primary"],
                "request_summary": "Hire an architect before implementation fanout continues.",
            }
        elif staffing_gaps:
            first_gap = staffing_gaps[0]
            capability_plan["recommended_hire"] = {
                "role_type": _ROLE_TYPE_BY_ROLE_PROFILE[first_gap],
                "role_profile_refs": [first_gap],
                "request_summary": f"Hire {first_gap} so implementation fanout can continue.",
            }

    return {
        "task_sensemaking": task_sensemaking,
        "capability_plan": capability_plan,
        "controller_state": controller_state,
        "meeting_candidates": combined_meeting_candidates,
    }

