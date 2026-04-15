from __future__ import annotations

import json
from typing import Any

from app.contracts.ticket_graph import TicketGraphSnapshot
from app.core.ceo_snapshot_contracts import controller_state_view
from app.core.ceo_execution_presets import PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED, EVENT_WORKFLOW_CREATED
from app.core.execution_targets import infer_execution_contract_payload, employee_supports_execution_contract
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MILESTONE_PLAN_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
    build_project_init_kickoff_spec,
    build_governance_followup_node_id,
    build_governance_followup_summary,
    governance_dependency_gate_refs,
    governance_parent_ticket_id,
    resolve_next_governance_schema,
    resolve_workflow_progression_adapter,
    select_governance_role_and_assignee,
)
from app.core.workflow_completion import resolve_workflow_closeout_completion
from app.db.repository import ControlPlaneRepository

_APPROVED_REVIEW_STATUSES = {"APPROVED", "APPROVED_WITH_NOTES"}
_APPROVED_ARCHITECT_DOCUMENT_SCHEMA_REFS = {
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
}
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


def _normalize_identifier(value: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "_"
        for character in str(value).strip()
    ).strip("_")


def backlog_followup_key_to_node_id(ticket_key: str) -> str:
    normalized = _normalize_identifier(ticket_key)
    return f"node_backlog_followup_{normalized}" if normalized else "node_backlog_followup"


def _architect_governance_gate_node_id(source_node_id: str | None, source_ticket_id: str | None) -> str:
    normalized = _normalize_identifier(source_node_id or source_ticket_id or "workflow")
    return (
        f"node_architect_governance_gate_{normalized}"
        if normalized
        else "node_architect_governance_gate"
    )


def workflow_controller_effect(snapshot: dict[str, Any]) -> str:
    state = str((controller_state_view(snapshot) or {}).get("state") or "").strip()
    if state == "WAIT_FOR_BOARD":
        return "WAIT_FOR_BOARD"
    if state == "WAIT_FOR_INCIDENT":
        return "WAIT_FOR_INCIDENT"
    if state == "READY_TICKET":
        return "RUN_SCHEDULER_TICK"
    if state == "WAIT_FOR_RUNTIME":
        return "WAIT_FOR_RUNTIME"
    if state in {"GOVERNANCE_REQUIRED", "ARCHITECT_REQUIRED", "MEETING_REQUIRED", "STAFFING_REQUIRED"}:
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


def _latest_completed_governance_ticket_ids_by_schema(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ? AND status = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id, "COMPLETED"),
    ).fetchall()
    completed_ticket_ids_by_schema: dict[str, str] = {}
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
            completed_ticket_ids_by_schema.setdefault(output_schema_ref, ticket_id)
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
        maker_output_schema_ref = str(maker_ticket_spec.get("output_schema_ref") or "").strip()
        if maker_output_schema_ref not in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
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
        completed_ticket_ids_by_schema.setdefault(maker_output_schema_ref, maker_ticket_id or ticket_id)
    return completed_ticket_ids_by_schema


def _build_governance_progression_ticket_plan(
    repository: ControlPlaneRepository,
    *,
    workflow: dict[str, Any],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    connection,
) -> dict[str, Any] | None:
    adapter_id = resolve_workflow_progression_adapter(workflow)
    if adapter_id != AUTOPILOT_GOVERNANCE_CHAIN:
        return None

    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if not workflow_id:
        return None

    completed_ticket_ids_by_schema = _latest_completed_governance_ticket_ids_by_schema(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    has_project_init_governance_node = any(
        str(node.get("node_id") or "").strip() == PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID
        for node in workflow_nodes
    )
    if (
        not completed_ticket_ids_by_schema
        and not has_project_init_governance_node
        and not workflow_uses_ceo_board_delegate(workflow)
    ):
        return None
    next_schema_ref = resolve_next_governance_schema(completed_ticket_ids_by_schema)
    if next_schema_ref is None:
        return None

    role_profile_ref, assignee_employee_id = select_governance_role_and_assignee(
        employees,
        output_schema_ref=next_schema_ref,
    )
    if role_profile_ref is None:
        return None

    node_id = build_governance_followup_node_id(next_schema_ref)
    existing_ticket_ids_by_node_id = {
        str(node.get("node_id") or ""): str(node.get("latest_ticket_id") or "")
        for node in workflow_nodes
        if str(node.get("node_id") or "").strip() and str(node.get("latest_ticket_id") or "").strip()
    }
    dependency_gate_refs = governance_dependency_gate_refs(
        completed_ticket_ids_by_schema,
        next_schema_ref,
    )
    parent_ticket_id = governance_parent_ticket_id(
        completed_ticket_ids_by_schema,
        next_schema_ref,
    )
    execution_contract = infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=next_schema_ref,
    ) or {}
    summary = build_governance_followup_summary(next_schema_ref)
    selection_reason = (
        f"Follow the current governance progression and create the next {next_schema_ref} document."
    )
    if not completed_ticket_ids_by_schema and next_schema_ref == ARCHITECTURE_BRIEF_SCHEMA_REF:
        kickoff_spec = build_project_init_kickoff_spec(workflow)
        summary = str(kickoff_spec["summary"])
        selection_reason = "Keep the first governance document on the current live frontend owner."
    return {
        "node_id": node_id,
        "role_profile_ref": role_profile_ref,
        "output_schema_ref": next_schema_ref,
        "execution_contract": execution_contract,
        "required_capability_tags": list(execution_contract.get("required_capability_tags") or []),
        "assignee_employee_id": assignee_employee_id,
        "parent_ticket_id": parent_ticket_id,
        "dependency_gate_refs": dependency_gate_refs,
        "summary": summary,
        "selection_reason": selection_reason,
        "source_ticket_id": parent_ticket_id,
        "source_node_id": build_governance_followup_node_id(next_schema_ref),
        "existing_ticket_id": existing_ticket_ids_by_node_id.get(node_id),
    }


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
        if (
            str(maker_ticket_spec.get("output_schema_ref") or "").strip()
            not in _APPROVED_ARCHITECT_DOCUMENT_SCHEMA_REFS
        ):
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


def _build_required_governance_ticket_plan(
    *,
    backlog_ticket_id: str,
    backlog_created_spec: dict[str, Any],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
) -> dict[str, Any]:
    source_node_id = str(backlog_created_spec.get("node_id") or "").strip() or None
    node_id = _architect_governance_gate_node_id(source_node_id, backlog_ticket_id)
    execution_contract = infer_execution_contract_payload(
        role_profile_ref="architect_primary",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
    ) or {}
    existing_ticket_ids_by_node_id = {
        str(node.get("node_id") or ""): str(node.get("latest_ticket_id") or "")
        for node in workflow_nodes
        if str(node.get("node_id") or "").strip() and str(node.get("latest_ticket_id") or "").strip()
    }
    return {
        "node_id": node_id,
        "role_profile_ref": "architect_primary",
        "role_type": _ROLE_TYPE_BY_ROLE_PROFILE["architect_primary"],
        "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
        "execution_contract": execution_contract,
        "required_capability_tags": list(execution_contract.get("required_capability_tags") or []),
        "assignee_employee_id": _select_default_assignee(
            employees,
            role_profile_ref="architect_primary",
            output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        ),
        "parent_ticket_id": backlog_ticket_id,
        "dependency_gate_refs": [],
        "summary": "Prepare the architect governance brief before implementation fanout continues.",
        "selection_reason": "Satisfy the current architect governance gate before implementation fanout continues.",
        "source_ticket_id": backlog_ticket_id,
        "source_node_id": source_node_id,
        "existing_ticket_id": existing_ticket_ids_by_node_id.get(node_id),
    }


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
    ticket_graph_snapshot: TicketGraphSnapshot | None = None,
    connection,
) -> dict[str, Any]:
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    progression_adapter_id = resolve_workflow_progression_adapter(workflow)
    graph_index_summary = (
        ticket_graph_snapshot.index_summary.model_dump(mode="json")
        if ticket_graph_snapshot is not None
        else {
            "ready_ticket_ids": [
                str(ticket.get("ticket_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("status") or "").strip() == "PENDING"
            ],
            "ready_node_ids": [
                str(ticket.get("node_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("status") or "").strip() == "PENDING"
            ],
            "blocked_ticket_ids": [],
            "blocked_node_ids": [],
            "in_flight_ticket_ids": [
                str(ticket.get("ticket_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("status") or "").strip() in {"LEASED", "EXECUTING"}
            ],
            "in_flight_node_ids": [
                str(ticket.get("node_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("status") or "").strip() in {"LEASED", "EXECUTING"}
            ],
            "critical_path_node_ids": [],
            "blocked_reasons": [],
            "reduction_issue_count": 0,
        }
    )
    graph_ready_ticket_ids = list(graph_index_summary.get("ready_ticket_ids") or [])
    graph_ready_node_ids = list(graph_index_summary.get("ready_node_ids") or [])
    graph_blocked_node_ids = list(graph_index_summary.get("blocked_node_ids") or [])
    graph_in_flight_ticket_ids = list(graph_index_summary.get("in_flight_ticket_ids") or [])
    graph_has_reduction_issues = int(graph_index_summary.get("reduction_issue_count") or 0) > 0
    hard_constraints = _load_workflow_hard_constraints(connection, workflow_id)
    created_specs_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
        for ticket in tickets
    }
    ticket_terminal_events_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_terminal_event(connection, str(ticket["ticket_id"]))
        for ticket in tickets
    }
    closeout_completion = resolve_workflow_closeout_completion(
        tickets=tickets,
        nodes=nodes,
        has_open_approval=bool(approvals),
        has_open_incident=bool(incidents),
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )
    backlog_ticket_id, backlog_created_spec, backlog_payload = _latest_completed_backlog_ticket(
        repository,
        workflow_id=workflow_id,
        trigger_ref=trigger_ref,
        connection=connection,
    )
    governance_ticket_plan = (
        None
        if closeout_completion is not None
        else _build_governance_progression_ticket_plan(
            repository,
            workflow=workflow,
            workflow_nodes=nodes,
            employees=employees,
            connection=connection,
        )
    )
    followup_ticket_plans: list[dict[str, Any]] = []
    task_type = "steady_state"
    deliverable_kind = None
    coordination_mode = "wait"
    if governance_ticket_plan is not None:
        task_type = "governance_followup"
        deliverable_kind = "structured_document_delivery"
        coordination_mode = "document_chain"
    elif backlog_ticket_id and isinstance(backlog_payload, dict):
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
    required_governance_ticket_plan = governance_ticket_plan

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
    elif graph_in_flight_ticket_ids:
        controller_state = {
            "state": "WAIT_FOR_RUNTIME",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "A leased ticket is still executing.",
        }
    elif graph_has_reduction_issues and graph_blocked_node_ids and not graph_ready_node_ids:
        controller_state = {
            "state": "NO_IMMEDIATE_FOLLOWUP",
            "recommended_action": "NO_ACTION",
            "blocking_reason": (
                "Ticket graph reports blocked pending nodes and no ready node. "
                "Resolve the legacy graph issue before dispatching more work."
            ),
        }
    elif graph_ready_ticket_ids:
        controller_state = {
            "state": "READY_TICKET",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Ready tickets already exist on the current mainline.",
        }
    elif required_governance_ticket_plan is not None:
        controller_state = {
            "state": "GOVERNANCE_REQUIRED",
            "recommended_action": (
                "CREATE_TICKET"
                if required_governance_ticket_plan.get("existing_ticket_id") is None
                else "NO_ACTION"
            ),
            "blocking_reason": (
                f"The governance-first progression requires {required_governance_ticket_plan['output_schema_ref']} before implementation fanout."
                if required_governance_ticket_plan.get("existing_ticket_id") is None
                else (
                    "The next governance ticket already exists and must finish or be recovered before the progression continues."
                )
            ),
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
            required_governance_ticket_plan = _build_required_governance_ticket_plan(
                backlog_ticket_id=backlog_ticket_id,
                backlog_created_spec=backlog_created_spec,
                workflow_nodes=nodes,
                employees=employees,
            )
            controller_state = {
                "state": "ARCHITECT_REQUIRED",
                "recommended_action": (
                    "CREATE_TICKET"
                    if required_governance_ticket_plan.get("existing_ticket_id") is None
                    else "NO_ACTION"
                ),
                "blocking_reason": (
                    "At least one approved architect_primary governance document is required before implementation fanout."
                    if required_governance_ticket_plan.get("existing_ticket_id") is None
                    else (
                        "A required architect governance ticket already exists and must finish or be recovered before "
                        "implementation fanout."
                    )
                ),
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
        "source_ticket_id": (
            backlog_ticket_id
            if task_type == "implementation_fanout"
            else str((required_governance_ticket_plan or {}).get("source_ticket_id") or "").strip() or None
        ),
        "source_node_id": (
            str(backlog_created_spec.get("node_id") or "").strip() or None
            if task_type == "implementation_fanout"
            else str((required_governance_ticket_plan or {}).get("source_node_id") or "").strip() or None
        ),
        "hard_constraints": hard_constraints,
        "progression_adapter_id": progression_adapter_id,
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
        "required_governance_ticket_plan": required_governance_ticket_plan,
        "followup_ticket_plans": followup_ticket_plans,
        "progression_adapter_id": progression_adapter_id,
    }
    if required_governance_ticket_plan is not None:
        capability_plan["required_capabilities"] = sorted(
            set(capability_plan["required_capabilities"])
            | set(required_governance_ticket_plan.get("required_capability_tags") or [])
        )
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
        "ticket_graph_summary": graph_index_summary,
    }

