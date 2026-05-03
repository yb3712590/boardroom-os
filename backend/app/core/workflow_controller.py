from __future__ import annotations

import json
from typing import Any

from app.contracts.ticket_graph import TicketGraphSnapshot
from app.core.ceo_snapshot_contracts import controller_state_view
from app.core.ceo_hire_loop import ceo_hire_loop_summary_from_incidents
from app.core.ceo_execution_presets import (
    GOVERNANCE_DOCUMENT_CHAIN_ORDER,
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
)
from app.core.constants import (
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
)
from app.core.employee_reuse import (
    ROLE_ALREADY_COVERED_REASON_CODE,
    find_reuse_candidate_employee,
    normalize_role_profile_refs,
)
from app.core.execution_targets import infer_execution_contract_payload, employee_supports_execution_contract
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    OutputSchemaValidationError,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    build_backlog_recommendation_artifact_path,
    build_backlog_recommendation_artifact_ref,
    schema_id,
    validate_output_payload,
)
from app.core.staffing_catalog import (
    STAFFING_CAP_REACHED_REASON_CODE,
    build_staffing_capacity_details,
    count_active_board_approved_staffing_matches,
    resolve_limited_ceo_staffing_combo,
)
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate
from app.core.workflow_progression import (
    AUTOPILOT_GOVERNANCE_CHAIN,
    ProgressionActionType,
    ProgressionPolicy,
    ProgressionSnapshot,
    build_project_init_kickoff_spec,
    build_governance_followup_node_id,
    build_governance_followup_summary,
    decide_next_actions,
    evaluate_progression_graph,
    governance_dependency_gate_refs,
    governance_parent_ticket_id,
    resolve_workflow_progression_adapter,
    select_governance_role_and_assignee,
)
from app.core.workflow_completion import (
    evaluate_workflow_closeout_gate_issue,
)
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
_BACKLOG_FOLLOWUP_DEFAULT_OUTPUT_SCHEMA_BY_ROLE_PROFILE = {
    "frontend_engineer_primary": SOURCE_CODE_DELIVERY_SCHEMA_REF,
    "backend_engineer_primary": SOURCE_CODE_DELIVERY_SCHEMA_REF,
    "database_engineer_primary": SOURCE_CODE_DELIVERY_SCHEMA_REF,
    "platform_sre_primary": SOURCE_CODE_DELIVERY_SCHEMA_REF,
    "architect_primary": ARCHITECTURE_BRIEF_SCHEMA_REF,
    "cto_primary": BACKLOG_RECOMMENDATION_SCHEMA_REF,
    "checker_primary": DELIVERY_CHECK_REPORT_SCHEMA_REF,
}
_BACKLOG_FOLLOWUP_ALLOWED_OUTPUT_SCHEMAS_BY_ROLE_PROFILE = {
    role_profile_ref: {output_schema_ref}
    for role_profile_ref, output_schema_ref in _BACKLOG_FOLLOWUP_DEFAULT_OUTPUT_SCHEMA_BY_ROLE_PROFILE.items()
}
_BACKLOG_FOLLOWUP_ALLOWED_OUTPUT_SCHEMAS_BY_ROLE_PROFILE["checker_primary"] = {
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
}
class BacklogRecommendationContractError(ValueError):
    pass


def _normalize_identifier(value: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "_"
        for character in str(value).strip()
    ).strip("_")


def backlog_followup_key_to_node_id(ticket_key: str) -> str:
    normalized = _normalize_identifier(ticket_key)
    return f"node_backlog_followup_{normalized}" if normalized else "node_backlog_followup"


def _current_ticket_ids_by_node_id(
    *,
    tickets: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
) -> dict[str, str]:
    latest_ticket_ids_by_node_id: dict[str, str] = {}
    latest_sort_keys_by_node_id: dict[str, tuple[str, str]] = {}
    for ticket in tickets:
        node_id = str(ticket.get("node_id") or "").strip()
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        if not node_id or not ticket_id:
            continue
        sort_key = (str(ticket.get("updated_at") or ""), ticket_id)
        if sort_key >= latest_sort_keys_by_node_id.get(node_id, ("", "")):
            latest_sort_keys_by_node_id[node_id] = sort_key
            latest_ticket_ids_by_node_id[node_id] = ticket_id
    for node in workflow_nodes:
        node_id = str(node.get("node_id") or "").strip()
        ticket_id = str(node.get("latest_ticket_id") or "").strip()
        if node_id and ticket_id and node_id not in latest_ticket_ids_by_node_id:
            latest_ticket_ids_by_node_id[node_id] = ticket_id
    return latest_ticket_ids_by_node_id


def _known_node_ids(
    *,
    tickets: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
) -> set[str]:
    node_ids = {
        str(ticket.get("node_id") or "").strip()
        for ticket in tickets
        if str(ticket.get("node_id") or "").strip()
    }
    node_ids.update(
        str(node.get("node_id") or "").strip()
        for node in workflow_nodes
        if str(node.get("node_id") or "").strip()
    )
    return node_ids


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
    if state == "GRAPH_HEALTH_WAIT":
        return "WAIT_FOR_GRAPH_HEALTH"
    if state == "READY_TICKET":
        return "RUN_SCHEDULER_TICK"
    if state == "WAIT_FOR_RUNTIME":
        return "WAIT_FOR_RUNTIME"
    if state in {"GOVERNANCE_REQUIRED", "ARCHITECT_REQUIRED", "MEETING_REQUIRED", "STAFFING_REQUIRED"}:
        return state
    if state == "READY_FOR_FANOUT":
        return "READY_FOR_FANOUT"
    return "NO_IMMEDIATE_FOLLOWUP"


def _graph_health_requires_pause(graph_health_report: dict[str, Any] | None) -> bool:
    if not isinstance(graph_health_report, dict):
        return False
    return str(graph_health_report.get("overall_health") or "").strip() == "CRITICAL"


def _normalize_topic(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _read_backlog_recommendation_payload(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str,
    connection,
) -> dict[str, Any]:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise BacklogRecommendationContractError(
            "Canonical backlog_recommendation artifact is unavailable because no artifact store is configured."
        )
    expected_artifact_ref = build_backlog_recommendation_artifact_ref(ticket_id)
    expected_logical_path = build_backlog_recommendation_artifact_path(ticket_id)
    artifact = next(
        (
            item
            for item in repository.list_ticket_artifacts(ticket_id, connection=connection)
            if str(item.get("artifact_ref") or "").strip() == expected_artifact_ref
        ),
        None,
    )
    if artifact is None:
        raise BacklogRecommendationContractError(
            f"Canonical backlog_recommendation artifact is missing for ticket {ticket_id}."
        )
    if str(artifact.get("logical_path") or "").strip() != expected_logical_path:
        raise BacklogRecommendationContractError(
            f"Canonical backlog_recommendation artifact path mismatch for ticket {ticket_id}."
        )
    try:
        payload = json.loads(
            artifact_store.read_bytes(
                str(artifact.get("storage_relpath") or "").strip() or None,
                storage_object_key=str(artifact.get("storage_object_key") or "").strip() or None,
            ).decode("utf-8")
        )
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise BacklogRecommendationContractError(
            f"Canonical backlog_recommendation artifact for ticket {ticket_id} is unreadable."
        ) from exc
    if not isinstance(payload, dict):
        raise BacklogRecommendationContractError(
            f"Canonical backlog_recommendation artifact for ticket {ticket_id} must decode to a JSON object."
        )
    try:
        validate_output_payload(
            schema_ref=BACKLOG_RECOMMENDATION_SCHEMA_REF,
            schema_version=BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
            submitted_schema_version=schema_id(
                BACKLOG_RECOMMENDATION_SCHEMA_REF,
                BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
            ),
            payload=payload,
        )
    except (OutputSchemaValidationError, ValueError) as exc:
        raise BacklogRecommendationContractError(
            f"Canonical backlog_recommendation artifact for ticket {ticket_id} violates the implementation_handoff contract: {exc}"
        ) from exc
    return payload


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


def _load_workflow_governance_requirements(connection, workflow_id: str) -> dict[str, Any]:
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
        requirements = payload.get("governance_requirements")
        if isinstance(requirements, dict):
            return dict(requirements)
    return {}


def _load_workflow_progression_policy_input(connection, workflow_id: str) -> dict[str, Any]:
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
        policy_input = payload.get("progression_policy_input")
        if isinstance(policy_input, dict):
            return dict(policy_input)
    return {}


def _select_default_assignee(
    employees: list[dict[str, Any]],
    *,
    role_profile_ref: str,
    output_schema_ref: str,
    require_role_profile: bool = False,
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
        if require_role_profile and role_profile_ref not in set(employee.get("role_profile_refs") or []):
            continue
        if not employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            continue
        return str(employee["employee_id"])
    return None


def _resolve_target_role_profile(raw_ticket: dict[str, Any]) -> str:
    explicit_role = str(raw_ticket.get("target_role") or "").strip().lower()
    mapped = _ROLE_PROFILE_BY_TARGET_ROLE.get(explicit_role)
    if mapped is None:
        raise BacklogRecommendationContractError(
            "Backlog implementation_handoff tickets must declare a supported target_role."
        )
    return mapped


def _resolve_followup_output_schema_ref(role_profile_ref: str) -> str:
    return _BACKLOG_FOLLOWUP_DEFAULT_OUTPUT_SCHEMA_BY_ROLE_PROFILE.get(
        role_profile_ref,
        SOURCE_CODE_DELIVERY_SCHEMA_REF,
    )


def _resolve_backlog_followup_execution_plan(raw_ticket: dict[str, Any]) -> dict[str, Any]:
    target_role = str(raw_ticket.get("target_role") or "").strip().lower()
    role_profile_ref = _ROLE_PROFILE_BY_TARGET_ROLE.get(target_role)
    if role_profile_ref is None:
        return {
            "ok": False,
            "reason_code": "unsupported_target_role",
            "target_role": target_role,
            "role_profile_ref": "",
            "output_schema_ref": "",
        }

    default_output_schema_ref = _resolve_followup_output_schema_ref(role_profile_ref)
    output_schema_ref = str(raw_ticket.get("output_schema_ref") or default_output_schema_ref).strip()
    allowed_output_schema_refs = _BACKLOG_FOLLOWUP_ALLOWED_OUTPUT_SCHEMAS_BY_ROLE_PROFILE.get(
        role_profile_ref,
        {default_output_schema_ref},
    )
    if output_schema_ref not in allowed_output_schema_refs:
        return {
            "ok": False,
            "reason_code": "unsupported_role_schema_combo",
            "target_role": target_role,
            "role_profile_ref": role_profile_ref,
            "output_schema_ref": output_schema_ref,
        }

    execution_contract = infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if execution_contract is None:
        return {
            "ok": False,
            "reason_code": "execution_contract_missing",
            "target_role": target_role,
            "role_profile_ref": role_profile_ref,
            "output_schema_ref": output_schema_ref,
        }

    return {
        "ok": True,
        "target_role": target_role,
        "role_profile_ref": role_profile_ref,
        "output_schema_ref": output_schema_ref,
        "execution_contract": execution_contract,
        "execution_target_ref": str(execution_contract["execution_target_ref"]),
        "deliverable_kind": output_schema_ref,
    }


def _build_ceo_create_ticket_payload(
    *,
    workflow_id: str,
    node_id: str,
    role_profile_ref: str,
    output_schema_ref: str,
    assignee_employee_id: str | None,
    selection_reason: str,
    dependency_gate_refs: list[str] | None,
    summary: str,
    parent_ticket_id: str | None,
    execution_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_execution_contract = execution_contract or infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    ) or {}
    return {
        "workflow_id": workflow_id,
        "node_id": node_id,
        "role_profile_ref": role_profile_ref,
        "output_schema_ref": output_schema_ref,
        "execution_contract": resolved_execution_contract,
        "dispatch_intent": {
            "assignee_employee_id": assignee_employee_id or "",
            "selection_reason": selection_reason,
            "dependency_gate_refs": list(dependency_gate_refs or []),
            "selected_by": "ceo",
            "wakeup_policy": "default",
        },
        "summary": summary,
        "parent_ticket_id": parent_ticket_id,
    }


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
            payload = _read_backlog_recommendation_payload(
                repository,
                ticket_id=trigger_ticket_id,
                connection=connection,
            )
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
            payload = _read_backlog_recommendation_payload(
                repository,
                ticket_id=ticket_id,
                connection=connection,
            )
            return ticket_id, created_spec, payload
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
        payload = _read_backlog_recommendation_payload(
            repository,
            ticket_id=maker_ticket_id,
            connection=connection,
        )
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


def _build_governance_progression_ticket_plans(
    repository: ControlPlaneRepository,
    *,
    workflow: dict[str, Any],
    tickets: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    connection,
) -> list[dict[str, Any]]:
    adapter_id = resolve_workflow_progression_adapter(workflow)
    if adapter_id != AUTOPILOT_GOVERNANCE_CHAIN:
        return []

    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if not workflow_id:
        return []

    known_node_ids = _known_node_ids(tickets=tickets, workflow_nodes=workflow_nodes)
    existing_ticket_ids_by_node_id = _current_ticket_ids_by_node_id(
        tickets=tickets,
        workflow_nodes=workflow_nodes,
    )
    completed_ticket_ids_by_schema = _latest_completed_governance_ticket_ids_by_schema(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    ticket_plans: list[dict[str, Any]] = []
    for output_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        if output_schema_ref in completed_ticket_ids_by_schema:
            continue
        role_profile_ref, assignee_employee_id = select_governance_role_and_assignee(
            employees,
            output_schema_ref=output_schema_ref,
        )
        if role_profile_ref is None:
            continue

        node_id = build_governance_followup_node_id(output_schema_ref)
        dependency_gate_refs = governance_dependency_gate_refs(
            completed_ticket_ids_by_schema,
            output_schema_ref,
        )
        parent_ticket_id = governance_parent_ticket_id(
            completed_ticket_ids_by_schema,
            output_schema_ref,
        )
        summary = build_governance_followup_summary(output_schema_ref)
        selection_reason = (
            f"Follow the current governance progression and create the next {output_schema_ref} document."
        )
        if not completed_ticket_ids_by_schema and output_schema_ref == ARCHITECTURE_BRIEF_SCHEMA_REF:
            kickoff_spec = build_project_init_kickoff_spec(workflow)
            summary = str(kickoff_spec["summary"])
            selection_reason = "Assign the first governance document to the active architect owner."
        ticket_plans.append(
            {
                "existing_ticket_id": existing_ticket_ids_by_node_id.get(node_id),
                "ticket_payload": _build_ceo_create_ticket_payload(
                    workflow_id=str(workflow.get("workflow_id") or "").strip(),
                    node_id=node_id,
                    role_profile_ref=role_profile_ref,
                    output_schema_ref=output_schema_ref,
                    assignee_employee_id=assignee_employee_id,
                    selection_reason=selection_reason,
                    dependency_gate_refs=dependency_gate_refs,
                    summary=summary,
                    parent_ticket_id=parent_ticket_id,
                ),
            }
        )
    return ticket_plans


def _required_governance_ticket_missing_assignee(ticket_plan: dict[str, Any] | None) -> bool:
    ticket_payload = (ticket_plan or {}).get("ticket_payload") or {}
    dispatch_intent = ticket_payload.get("dispatch_intent") or {}
    return (
        isinstance(ticket_payload, dict)
        and not str(dispatch_intent.get("assignee_employee_id") or "").strip()
    )


def _recommended_hire_for_role_profile(role_profile_ref: str) -> dict[str, Any] | None:
    normalized_role_profile_ref = str(role_profile_ref or "").strip()
    role_type = _ROLE_TYPE_BY_ROLE_PROFILE.get(normalized_role_profile_ref)
    if role_type is None:
        return None
    request_summary = (
        "Hire an architect before governance kickoff continues."
        if normalized_role_profile_ref == "architect_primary"
        else f"Hire {normalized_role_profile_ref} before governance kickoff continues."
    )
    return {
        "role_type": role_type,
        "role_profile_refs": [normalized_role_profile_ref],
        "request_summary": request_summary,
    }


def _recent_role_already_covered_hire_rejection(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    recommended_hire: dict[str, Any],
    employees: list[dict[str, Any]],
    connection,
) -> dict[str, Any] | None:
    role_type = str(recommended_hire.get("role_type") or "").strip()
    role_profile_refs = normalize_role_profile_refs(recommended_hire.get("role_profile_refs") or [])
    if not role_type or not role_profile_refs:
        return None

    reuse_candidate = find_reuse_candidate_employee(
        role_type=role_type,
        role_profile_refs=role_profile_refs,
        employees=employees,
    )
    if reuse_candidate is None:
        return None

    for run in repository.list_ceo_shadow_runs(workflow_id, limit=5, connection=connection):
        for rejected_action in list(run.get("rejected_actions") or []):
            if str(rejected_action.get("action_type") or "").strip() != "HIRE_EMPLOYEE":
                continue
            payload = rejected_action.get("payload") or {}
            details = rejected_action.get("details") or {}
            if not isinstance(payload, dict) or not isinstance(details, dict):
                continue
            if str(details.get("reason_code") or "").strip() != ROLE_ALREADY_COVERED_REASON_CODE:
                continue
            rejected_role_type = str(details.get("role_type") or payload.get("role_type") or "").strip()
            rejected_role_profile_refs = normalize_role_profile_refs(
                details.get("role_profile_refs") or payload.get("role_profile_refs") or []
            )
            if rejected_role_type != role_type or rejected_role_profile_refs != role_profile_refs:
                continue
            return {
                "reason_code": ROLE_ALREADY_COVERED_REASON_CODE,
                "reuse_candidate_employee_id": str(reuse_candidate["employee_id"]),
                "role_type": role_type,
                "role_profile_refs": role_profile_refs,
                "source_ceo_shadow_run_id": str(run.get("run_id") or ""),
            }
    return None


def _build_followup_ticket_plans(
    *,
    workflow_id: str,
    backlog_ticket_id: str,
    backlog_created_spec: dict[str, Any],
    backlog_payload: dict[str, Any],
    tickets: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    implementation_handoff = backlog_payload.get("implementation_handoff")
    if not isinstance(implementation_handoff, dict):
        raise BacklogRecommendationContractError(
            f"Backlog ticket {backlog_ticket_id} is missing a valid implementation_handoff object."
        )

    raw_tickets = implementation_handoff.get("tickets")
    raw_dependency_graph = implementation_handoff.get("dependency_graph")
    raw_sequence = implementation_handoff.get("recommended_sequence")
    if not isinstance(raw_tickets, list) or not isinstance(raw_dependency_graph, list) or not isinstance(raw_sequence, list):
        raise BacklogRecommendationContractError(
            f"Backlog ticket {backlog_ticket_id} has an incomplete implementation_handoff payload."
        )

    recommended_tickets = {
        str(raw_ticket.get("ticket_id") or "").strip(): raw_ticket
        for raw_ticket in raw_tickets
        if isinstance(raw_ticket, dict) and str(raw_ticket.get("ticket_id") or "").strip()
    }
    dependency_map = {
        str(raw_dependency.get("ticket_id") or "").strip(): [
            str(item).strip()
            for item in list(raw_dependency.get("depends_on") or [])
            if str(item).strip()
        ]
        for raw_dependency in raw_dependency_graph
        if isinstance(raw_dependency, dict) and str(raw_dependency.get("ticket_id") or "").strip()
    }
    ordered_ticket_keys = [
        str(item).strip()
        for item in raw_sequence
        if isinstance(item, str) and item.strip()
    ]

    existing_ticket_ids_by_node_id = _current_ticket_ids_by_node_id(
        tickets=tickets,
        workflow_nodes=workflow_nodes,
    )

    followup_ticket_plans: list[dict[str, Any]] = []
    for ticket_key in ordered_ticket_keys:
        raw_ticket = recommended_tickets.get(ticket_key)
        if not isinstance(raw_ticket, dict):
            continue
        node_id = backlog_followup_key_to_node_id(ticket_key)
        execution_plan = _resolve_backlog_followup_execution_plan(raw_ticket)
        if not execution_plan.get("ok"):
            raise BacklogRecommendationContractError(
                "Backlog follow-up ticket has no valid execution contract: "
                f"{execution_plan.get('reason_code')}"
            )
        role_profile_ref = str(execution_plan["role_profile_ref"])
        output_schema_ref = str(execution_plan["output_schema_ref"])
        execution_contract = dict(execution_plan["execution_contract"])
        task_scope = [
            str(item).strip()
            for item in list(raw_ticket.get("scope") or [])
            if str(item).strip()
        ]
        assignee_employee_id = _select_default_assignee(
            employees,
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
            require_role_profile=True,
        )
        dependency_ticket_keys = list(dependency_map.get(ticket_key) or [])
        dependency_gate_refs = [
            existing_ticket_ids_by_node_id.get(backlog_followup_key_to_node_id(dependency_key))
            for dependency_key in dependency_ticket_keys
            if existing_ticket_ids_by_node_id.get(backlog_followup_key_to_node_id(dependency_key))
        ]
        scope_suffix = f"；范围：{'、'.join(task_scope)}" if task_scope else ""
        followup_ticket_plans.append(
            {
                "ticket_key": ticket_key,
                "existing_ticket_id": existing_ticket_ids_by_node_id.get(node_id),
                "blocked_by_plan_keys": dependency_ticket_keys,
                "ticket_payload": _build_ceo_create_ticket_payload(
                    workflow_id=workflow_id,
                    node_id=node_id,
                    role_profile_ref=role_profile_ref,
                    output_schema_ref=output_schema_ref,
                    execution_contract=execution_contract,
                    assignee_employee_id=assignee_employee_id,
                    selection_reason=(
                        "Follow the current capability plan and translate the approved backlog recommendation into an auditable implementation ticket."
                    ),
                    dependency_gate_refs=dependency_gate_refs,
                    summary=(
                        f"{ticket_key} "
                        f"{str(raw_ticket.get('name') or raw_ticket.get('summary') or ticket_key).strip() or ticket_key}"
                        f"{scope_suffix}"
                    ),
                    parent_ticket_id=backlog_ticket_id,
                ),
                "execution_plan": execution_plan,
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


def _busy_worker_ids(connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT actor_id
        FROM ticket_projection
        WHERE status IN ('LEASED', 'EXECUTING')
          AND actor_id IS NOT NULL
          AND TRIM(actor_id) != ''
        """
    ).fetchall()
    return {str(row["actor_id"]) for row in rows}


def _provider_paused_for_employee(
    repository: ControlPlaneRepository,
    connection,
    employee: dict[str, Any],
) -> bool:
    provider_id = str(employee.get("provider_id") or "").strip()
    if not provider_id:
        return False
    return repository.has_open_circuit_breaker_for_provider(provider_id, connection=connection)


def _build_ready_ticket_issue_payload(
    *,
    ticket_id: str,
    ticket: dict[str, Any],
    created_spec: dict[str, Any],
    reason_code: str,
    role_profile_ref: str,
    role_type: str,
    excluded_employee_ids: set[str],
    candidate_details: list[dict[str, Any]],
    matching_role_count: int,
    excluded_count: int,
    busy_count: int,
    provider_paused_count: int,
    eligible_count: int,
    capacity_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ticket_id": str(ticket_id),
        "node_id": str(ticket.get("node_id") or created_spec.get("node_id") or ""),
        "reason_code": reason_code,
        "required_role_profile_ref": role_profile_ref,
        "role_type": role_type,
        "excluded_employee_ids": sorted(excluded_employee_ids),
        "candidate_summary": {
            "total_candidate_count": len(candidate_details),
            "matching_role_count": matching_role_count,
            "excluded_count": excluded_count,
            "busy_count": busy_count,
            "provider_paused_count": provider_paused_count,
            "eligible_count": eligible_count,
        },
        "candidate_details": candidate_details,
    }
    if capacity_details is not None:
        payload.update(capacity_details)
    return payload


def _build_ready_ticket_staffing_assessment(
    repository: ControlPlaneRepository,
    *,
    ready_ticket_ids: list[str],
    tickets: list[dict[str, Any]],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    employees: list[dict[str, Any]],
    connection,
) -> dict[str, Any]:
    if not ready_ticket_ids:
        return {
            "ready_ticket_staffing_gaps": [],
            "contract_issues": [],
            "reuse_candidate_employee_ids": [],
            "staffing_wait_reasons": [],
        }
    ticket_by_id = {str(ticket.get("ticket_id") or ""): ticket for ticket in tickets}
    busy_workers = _busy_worker_ids(connection)
    gaps: list[dict[str, Any]] = []
    contract_issues: list[dict[str, Any]] = []
    reuse_candidate_employee_ids: set[str] = set()
    staffing_wait_reasons: list[dict[str, Any]] = []
    for ticket_id in ready_ticket_ids:
        ticket = ticket_by_id.get(str(ticket_id))
        created_spec = created_specs_by_ticket.get(str(ticket_id)) or {}
        if ticket is None or not created_spec:
            continue
        role_profile_ref = str(created_spec.get("role_profile_ref") or "").strip()
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        role_type = _ROLE_TYPE_BY_ROLE_PROFILE.get(role_profile_ref)
        if not role_profile_ref or role_type is None:
            continue
        inferred_execution_contract = infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        if inferred_execution_contract is None:
            contract_issues.append(
                {
                    "ticket_id": str(ticket_id),
                    "node_id": str(ticket.get("node_id") or created_spec.get("node_id") or ""),
                    "reason_code": "ROLE_SCHEMA_UNSUPPORTED",
                    "required_role_profile_ref": role_profile_ref,
                    "role_type": role_type,
                    "output_schema_ref": output_schema_ref,
                }
            )
            continue
        execution_contract = created_spec.get("execution_contract")
        if not isinstance(execution_contract, dict):
            contract_issues.append(
                {
                    "ticket_id": str(ticket_id),
                    "node_id": str(ticket.get("node_id") or created_spec.get("node_id") or ""),
                    "reason_code": "INVALID_EXECUTION_CONTRACT",
                    "required_role_profile_ref": role_profile_ref,
                    "role_type": role_type,
                    "output_schema_ref": output_schema_ref,
                    "expected_execution_contract": inferred_execution_contract,
                }
            )
            continue
        expected_target_ref = str(inferred_execution_contract.get("execution_target_ref") or "").strip()
        actual_target_ref = str(execution_contract.get("execution_target_ref") or "").strip()
        expected_required_tags = {
            str(tag)
            for tag in list(inferred_execution_contract.get("required_capability_tags") or [])
            if str(tag).strip()
        }
        actual_required_tags = {
            str(tag)
            for tag in list(execution_contract.get("required_capability_tags") or [])
            if str(tag).strip()
        }
        if (
            actual_target_ref != expected_target_ref
            or not actual_required_tags
            or actual_required_tags != expected_required_tags
            or str(execution_contract.get("runtime_contract_version") or "").strip()
            != str(inferred_execution_contract.get("runtime_contract_version") or "").strip()
        ):
            contract_issues.append(
                {
                    "ticket_id": str(ticket_id),
                    "node_id": str(ticket.get("node_id") or created_spec.get("node_id") or ""),
                    "reason_code": "INVALID_EXECUTION_CONTRACT",
                    "required_role_profile_ref": role_profile_ref,
                    "role_type": role_type,
                    "output_schema_ref": output_schema_ref,
                    "expected_execution_contract": inferred_execution_contract,
                    "actual_execution_contract": execution_contract,
                }
            )
            continue
        excluded_employee_ids = {
            str(employee_id)
            for employee_id in list(created_spec.get("excluded_employee_ids") or [])
            if str(employee_id).strip()
        }
        candidate_details: list[dict[str, Any]] = []
        matching_role_count = 0
        excluded_count = 0
        busy_count = 0
        provider_paused_count = 0
        eligible_count = 0
        for employee in sorted(employees, key=lambda item: str(item.get("employee_id") or "")):
            employee_id = str(employee.get("employee_id") or "").strip()
            role_profile_refs = set(employee.get("role_profile_refs") or [])
            has_required_role = role_profile_ref in role_profile_refs
            is_active_board_approved = str(employee.get("state") or "") == "ACTIVE" and bool(
                employee.get("board_approved")
            )
            supports_contract = employee_supports_execution_contract(
                employee=employee,
                execution_contract=execution_contract,
            )
            is_excluded = employee_id in excluded_employee_ids
            is_busy = employee_id in busy_workers
            provider_paused = _provider_paused_for_employee(repository, connection, employee)
            if has_required_role and supports_contract and is_active_board_approved:
                matching_role_count += 1
                reuse_candidate_employee_ids.add(employee_id)
            if is_excluded:
                excluded_count += 1
            if is_busy:
                busy_count += 1
            if provider_paused:
                provider_paused_count += 1
            eligible = (
                has_required_role
                and supports_contract
                and not is_excluded
                and not is_busy
                and not provider_paused
                and is_active_board_approved
            )
            if eligible:
                eligible_count += 1
            candidate_details.append(
                {
                    "employee_id": employee_id,
                    "role_profile_refs": sorted(role_profile_refs),
                    "has_required_role": has_required_role,
                    "supports_execution_contract": supports_contract,
                    "excluded": is_excluded,
                    "busy": is_busy,
                    "provider_id": employee.get("provider_id"),
                    "provider_paused": provider_paused,
                    "eligible": eligible,
                }
            )
        template, _staffing_reason = resolve_limited_ceo_staffing_combo(role_type, [role_profile_ref])
        active_matching_count = count_active_board_approved_staffing_matches(
            role_type=role_type,
            role_profile_refs=[role_profile_ref],
            employees=employees,
        )
        max_active_count = int(template["max_active_count"]) if template is not None else active_matching_count + 1
        cap_reached = active_matching_count >= max_active_count
        cap_reached_details = build_staffing_capacity_details(
            reason_code=STAFFING_CAP_REACHED_REASON_CODE,
            role_type=role_type,
            role_profile_refs=[role_profile_ref],
            active_matching_count=active_matching_count,
            max_active_count=max_active_count,
            template_id=str(template["template_id"]) if template is not None else None,
        )
        if eligible_count > 0:
            continue
        if matching_role_count == 0:
            gaps.append(
                _build_ready_ticket_issue_payload(
                    ticket_id=str(ticket_id),
                    ticket=ticket,
                    created_spec=created_spec,
                    reason_code="NO_ACTIVE_ROLE_WORKER",
                    role_profile_ref=role_profile_ref,
                    role_type=role_type,
                    excluded_employee_ids=excluded_employee_ids,
                    candidate_details=candidate_details,
                    matching_role_count=matching_role_count,
                    excluded_count=excluded_count,
                    busy_count=busy_count,
                    provider_paused_count=provider_paused_count,
                    eligible_count=eligible_count,
                )
            )
            continue
        if excluded_count > 0:
            staffing_wait_reasons.append(
                _build_ready_ticket_issue_payload(
                    ticket_id=str(ticket_id),
                    ticket=ticket,
                    created_spec=created_spec,
                    reason_code="WORKER_EXCLUDED",
                    role_profile_ref=role_profile_ref,
                    role_type=role_type,
                    excluded_employee_ids=excluded_employee_ids,
                    candidate_details=candidate_details,
                    matching_role_count=matching_role_count,
                    excluded_count=excluded_count,
                    busy_count=busy_count,
                    provider_paused_count=provider_paused_count,
                    eligible_count=eligible_count,
                )
            )
            continue
        if provider_paused_count > 0:
            staffing_wait_reasons.append(
                _build_ready_ticket_issue_payload(
                    ticket_id=str(ticket_id),
                    ticket=ticket,
                    created_spec=created_spec,
                    reason_code="PROVIDER_PAUSED",
                    role_profile_ref=role_profile_ref,
                    role_type=role_type,
                    excluded_employee_ids=excluded_employee_ids,
                    candidate_details=candidate_details,
                    matching_role_count=matching_role_count,
                    excluded_count=excluded_count,
                    busy_count=busy_count,
                    provider_paused_count=provider_paused_count,
                    eligible_count=eligible_count,
                )
            )
            continue
        if busy_count > 0:
            target_collection = staffing_wait_reasons if cap_reached else gaps
            target_collection.append(
                _build_ready_ticket_issue_payload(
                    ticket_id=str(ticket_id),
                    ticket=ticket,
                    created_spec=created_spec,
                    reason_code=STAFFING_CAP_REACHED_REASON_CODE if cap_reached else "WORKER_BUSY",
                    role_profile_ref=role_profile_ref,
                    role_type=role_type,
                    excluded_employee_ids=excluded_employee_ids,
                    candidate_details=candidate_details,
                    matching_role_count=matching_role_count,
                    excluded_count=excluded_count,
                    busy_count=busy_count,
                    provider_paused_count=provider_paused_count,
                    eligible_count=eligible_count,
                    capacity_details=cap_reached_details if cap_reached else None,
                )
            )
            continue
    return {
        "ready_ticket_staffing_gaps": gaps,
        "contract_issues": contract_issues,
        "reuse_candidate_employee_ids": sorted(reuse_candidate_employee_ids),
        "staffing_wait_reasons": staffing_wait_reasons,
    }


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
    workflow_id: str,
    backlog_ticket_id: str,
    backlog_created_spec: dict[str, Any],
    tickets: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
) -> dict[str, Any]:
    source_node_id = str(backlog_created_spec.get("node_id") or "").strip() or None
    node_id = _architect_governance_gate_node_id(source_node_id, backlog_ticket_id)
    existing_ticket_ids_by_node_id = _current_ticket_ids_by_node_id(
        tickets=tickets,
        workflow_nodes=workflow_nodes,
    )
    return {
        "existing_ticket_id": existing_ticket_ids_by_node_id.get(node_id),
        "ticket_payload": _build_ceo_create_ticket_payload(
            workflow_id=workflow_id,
            node_id=node_id,
            role_profile_ref="architect_primary",
            output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
            assignee_employee_id=_select_default_assignee(
                employees,
                role_profile_ref="architect_primary",
                output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
            ),
            selection_reason="Satisfy the current architect governance gate before implementation fanout continues.",
            dependency_gate_refs=[],
            summary="Prepare the architect governance brief before implementation fanout continues.",
            parent_ticket_id=backlog_ticket_id,
        ),
    }


def _approved_meeting_evidence_records(*, workflow_id: str, connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT meeting_id, meeting_type, source_ticket_id, source_graph_node_id, source_node_id, review_status
        FROM meeting_projection
        WHERE workflow_id = ? AND closed_at IS NOT NULL AND review_status IN (?, ?)
        ORDER BY closed_at DESC, meeting_id DESC
        """,
        (workflow_id, "APPROVED", "APPROVED_WITH_NOTES"),
    ).fetchall()
    return [
        {
            "meeting_id": str(row["meeting_id"]),
            "required_meeting_type": str(row["meeting_type"]),
            "source_ticket_id": str(row["source_ticket_id"]),
            "node_ref": str(row["source_graph_node_id"] or row["source_node_id"] or ""),
            "review_status": str(row["review_status"] or ""),
        }
        for row in rows
    ]


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
        "source_graph_node_id": source_node_id,
        "source_node_id": source_node_id,
        "source_ticket_id": source_ticket_id,
        "topic": topic,
        "reason": "Implementation boundary still needs one explicit structured meeting approval before execution starts.",
        "participant_employee_ids": [
            str(architect_employees[0]["employee_id"]),
            str(checker_employees[0]["employee_id"]),
        ],
        "recorder_employee_id": str(architect_employees[0]["employee_id"]),
        "input_artifact_refs": list(source_created_spec.get("input_artifact_refs") or []),
        "eligible": eligible,
        "eligibility_reason": eligibility_reason,
    }


def _progression_snapshot_from_controller_inputs(
    *,
    workflow_id: str,
    graph_version: str,
    tickets: list[dict[str, Any]],
    ticket_graph_snapshot: TicketGraphSnapshot | None,
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> ProgressionSnapshot:
    if ticket_graph_snapshot is None:
        return ProgressionSnapshot(
            workflow_id=workflow_id,
            graph_version=graph_version,
            node_refs=[
                str(ticket.get("node_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("node_id") or "").strip()
            ],
            ticket_refs=[
                str(ticket.get("ticket_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("ticket_id") or "").strip()
            ],
            ready_ticket_ids=[
                str(ticket.get("ticket_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("status") or "").strip() == "PENDING"
            ],
            in_flight_ticket_ids=[
                str(ticket.get("ticket_id") or "").strip()
                for ticket in tickets
                if str(ticket.get("status") or "").strip() in {"LEASED", "EXECUTING"}
            ],
            approvals=[
                {
                    "approval_id": str(item.get("approval_id") or ""),
                    "node_ref": str(item.get("source_graph_node_id") or item.get("source_node_id") or ""),
                }
                for item in approvals
            ],
            incidents=[
                {
                    "incident_id": str(item.get("incident_id") or ""),
                    "node_ref": str(item.get("node_id") or ""),
                }
                for item in incidents
            ],
        )
    return ProgressionSnapshot(
        workflow_id=workflow_id,
        graph_version=str(ticket_graph_snapshot.graph_version),
        node_refs=[str(node.graph_node_id or "").strip() for node in ticket_graph_snapshot.nodes],
        ticket_refs=[
            str(node.ticket_id or "").strip()
            for node in ticket_graph_snapshot.nodes
            if str(node.ticket_id or "").strip()
        ],
        graph_nodes=[
            {
                "node_ref": str(node.graph_node_id or "").strip(),
                "node_id": str(node.node_id or "").strip(),
                "ticket_id": str(node.ticket_id or "").strip(),
                "ticket_status": str(node.ticket_status or "").strip(),
                "node_status": str(node.node_status or "").strip(),
                "blocking_reason_code": str(node.blocking_reason_code or "").strip(),
            }
            for node in ticket_graph_snapshot.nodes
            if str(node.graph_node_id or "").strip()
        ],
        graph_edges=[
            {
                "edge_type": str(edge.edge_type or "").strip(),
                "source_node_ref": str(edge.source_graph_node_id or "").strip(),
                "target_node_ref": str(edge.target_graph_node_id or "").strip(),
                "source_ticket_id": str(edge.source_ticket_id or "").strip(),
                "target_ticket_id": str(edge.target_ticket_id or "").strip(),
            }
            for edge in ticket_graph_snapshot.edges
        ],
        graph_reduction_issues=[
            {
                "issue_code": str(issue.issue_code or ""),
                "detail": str(issue.detail or ""),
                "node_ref": str(issue.node_id or ""),
                "related_ticket_id": str(issue.related_ticket_id or issue.ticket_id or ""),
                "recoverable": False,
            }
            for issue in ticket_graph_snapshot.reduction_issues
        ],
        approvals=[
            {
                "approval_id": str(item.get("approval_id") or ""),
                "node_ref": str(item.get("source_graph_node_id") or item.get("source_node_id") or ""),
            }
            for item in approvals
        ],
        incidents=[
            {
                "incident_id": str(item.get("incident_id") or ""),
                "node_ref": str(item.get("node_id") or ""),
            }
            for item in incidents
        ],
    )


def _policy_node_ref_from_ticket_payload(ticket_payload: dict[str, Any]) -> str:
    node_id = str(ticket_payload.get("node_id") or "").strip()
    return f"graph:{node_id}" if node_id else ""


def _build_governance_policy_input(
    *,
    repository: ControlPlaneRepository,
    governance_requirements: dict[str, Any],
    structured_governance_policy_input: dict[str, Any] | None = None,
    governance_ticket_plans: list[dict[str, Any]],
    completed_governance_ticket_ids_by_schema: dict[str, str],
    workflow_id: str,
    backlog_ticket_id: str | None,
    backlog_created_spec: dict[str, Any],
    tickets: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    connection,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    governance_policy = dict(structured_governance_policy_input or {})
    governance_policy.update(
        {
        "chain_order": list(GOVERNANCE_DOCUMENT_CHAIN_ORDER),
        "completed_outputs": [
            {
                "output_schema_ref": output_schema_ref,
                "ticket_id": ticket_id,
                "approved": True,
            }
            for output_schema_ref, ticket_id in sorted(completed_governance_ticket_ids_by_schema.items())
        ],
        "chain_ticket_plans": [],
        "required_gates": [],
        "meeting_requirements": [],
        "approved_meeting_evidence": _approved_meeting_evidence_records(
            workflow_id=workflow_id,
            connection=connection,
        ),
        }
    )
    structured_completed_outputs = (
        (structured_governance_policy_input or {}).get("completed_outputs")
        if isinstance((structured_governance_policy_input or {}).get("completed_outputs"), list)
        else []
    )
    governance_policy["completed_outputs"].extend(
        dict(item)
        for item in structured_completed_outputs
        if isinstance(item, dict)
    )
    for governance_ticket_plan in governance_ticket_plans:
        if not isinstance(governance_ticket_plan, dict):
            continue
        ticket_payload = dict(governance_ticket_plan.get("ticket_payload") or {})
        output_schema_ref = str(ticket_payload.get("output_schema_ref") or "").strip()
        if output_schema_ref:
            governance_policy["chain_ticket_plans"].append(
                {
                    "candidate_ref": f"governance:{output_schema_ref}",
                    "output_schema_ref": output_schema_ref,
                    "node_ref": _policy_node_ref_from_ticket_payload(ticket_payload),
                    "existing_ticket_id": governance_ticket_plan.get("existing_ticket_id"),
                    "ticket_payload": ticket_payload,
                }
            )

    required_governance_ticket_plan: dict[str, Any] | None = None
    controller_meeting_candidates: list[dict[str, Any]] = []
    structured_required_gates = [
        dict(item)
        for item in list(governance_requirements.get("required_gates") or [])
        if isinstance(item, dict)
    ]
    for gate in structured_required_gates:
        gate_type = str(gate.get("gate_type") or "").strip().upper()
        if gate_type != "ARCHITECT_GOVERNANCE":
            governance_policy["required_gates"].append(gate)
            continue
        if not backlog_ticket_id:
            continue
        gate_satisfied = _has_approved_architect_document(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
        if gate_satisfied:
            required_governance_ticket_plan = None
            governance_policy["required_gates"].append(
                {
                    **gate,
                    "gate_ref": str(gate.get("gate_ref") or f"gate:architect:{backlog_ticket_id}"),
                    "gate_type": "ARCHITECT_GOVERNANCE",
                    "required_output_schema_ref": str(
                        gate.get("required_output_schema_ref") or ARCHITECTURE_BRIEF_SCHEMA_REF
                    ),
                    "source_ticket_id": backlog_ticket_id,
                    "satisfied": True,
                }
            )
            continue
        required_governance_ticket_plan = _build_required_governance_ticket_plan(
            workflow_id=workflow_id,
            backlog_ticket_id=backlog_ticket_id,
            backlog_created_spec=backlog_created_spec,
            tickets=tickets,
            workflow_nodes=workflow_nodes,
            employees=employees,
        )
        ticket_payload = dict(required_governance_ticket_plan.get("ticket_payload") or {})
        governance_policy["required_gates"].append(
            {
                **gate,
                "gate_ref": str(gate.get("gate_ref") or f"gate:architect:{backlog_ticket_id}"),
                "gate_type": "ARCHITECT_GOVERNANCE",
                "required_output_schema_ref": str(
                    gate.get("required_output_schema_ref") or ARCHITECTURE_BRIEF_SCHEMA_REF
                ),
                "source_ticket_id": backlog_ticket_id,
                "node_ref": _policy_node_ref_from_ticket_payload(ticket_payload),
                "satisfied": gate_satisfied,
                "existing_ticket_id": required_governance_ticket_plan.get("existing_ticket_id"),
                "ticket_payload": ticket_payload,
            }
        )

    for requirement in [
        dict(item)
        for item in list(governance_requirements.get("meeting_requirements") or [])
        if isinstance(item, dict)
    ]:
        if not backlog_ticket_id:
            governance_policy["meeting_requirements"].append(requirement)
            continue
        source_node_id = str(backlog_created_spec.get("node_id") or "").strip() or None
        meeting_candidate = _build_controller_meeting_candidate(
            repository,
            workflow_id=workflow_id,
            source_ticket_id=backlog_ticket_id,
            source_node_id=source_node_id,
            employees=employees,
            approvals=[],
            incidents=[],
            connection=connection,
        )
        if meeting_candidate is not None:
            controller_meeting_candidates.append(meeting_candidate)
        governance_policy["meeting_requirements"].append(
            {
                **requirement,
                "requirement_ref": str(requirement.get("requirement_ref") or f"meeting:{backlog_ticket_id}"),
                "source_ticket_id": backlog_ticket_id,
                "node_ref": str(source_node_id or backlog_ticket_id),
                "required_meeting_type": str(requirement.get("required_meeting_type") or "TECHNICAL_DECISION"),
                "meeting_candidate": meeting_candidate or {},
            }
        )
    return governance_policy, required_governance_ticket_plan, controller_meeting_candidates


def _build_fanout_policy_input(
    *,
    source_ticket_id: str | None,
    graph_version: str,
    followup_ticket_plans: list[dict[str, Any]],
    structured_fanout_policy_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fanout_policy = dict(structured_fanout_policy_input or {})
    if not source_ticket_id or not followup_ticket_plans:
        return fanout_policy
    fanout_policy["backlog_implementation_handoff"] = {
            "source_ticket_id": source_ticket_id,
            "source_graph_version": graph_version,
            "ticket_plans": [
                {
                    "ticket_key": str(plan.get("ticket_key") or "").strip(),
                    "node_ref": _policy_node_ref_from_ticket_payload(
                        dict(plan.get("ticket_payload") or {})
                    ),
                    "existing_ticket_id": plan.get("existing_ticket_id"),
                    "blocked_by_plan_keys": list(plan.get("blocked_by_plan_keys") or []),
                    "ticket_payload": dict(plan.get("ticket_payload") or {}),
                    "execution_plan": dict(plan.get("execution_plan") or {}),
                    "sequence_index": index,
                }
                for index, plan in enumerate(followup_ticket_plans)
                if isinstance(plan, dict)
            ],
    }
    return fanout_policy


def _latest_closeout_ticket_id(
    *,
    created_specs_by_ticket: dict[str, dict[str, Any]],
    effective_ticket_ids: list[str] | None = None,
) -> str | None:
    effective_ticket_id_set = {
        str(ticket_id).strip()
        for ticket_id in list(effective_ticket_ids or [])
        if str(ticket_id).strip()
    }
    for ticket_id, created_spec in sorted(created_specs_by_ticket.items()):
        if effective_ticket_id_set and ticket_id not in effective_ticket_id_set:
            continue
        if str(created_spec.get("output_schema_ref") or "").strip() == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
            return ticket_id
    return None


def _closeout_parent_ticket_id(
    *,
    tickets: list[dict[str, Any]],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    completed_ticket_ids: list[str] | None = None,
) -> str | None:
    effective_completed_ticket_ids = {
        str(ticket_id).strip()
        for ticket_id in list(completed_ticket_ids or [])
        if str(ticket_id).strip()
    }
    completed_tickets = [
        ticket
        for ticket in tickets
        if str(ticket.get("status") or "").strip() == "COMPLETED"
        and (
            not effective_completed_ticket_ids
            or str(ticket.get("ticket_id") or "").strip() in effective_completed_ticket_ids
        )
    ]
    for ticket in sorted(
        completed_tickets,
        key=lambda item: (str(item.get("updated_at") or ""), str(item.get("ticket_id") or "")),
        reverse=True,
    ):
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        created_spec = created_specs_by_ticket.get(ticket_id) or {}
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF:
            maker_ticket_id = str(
                (created_spec.get("maker_checker_context") or {}).get("maker_ticket_id") or ""
            ).strip()
            if maker_ticket_id:
                return maker_ticket_id
    for ticket in sorted(
        completed_tickets,
        key=lambda item: (str(item.get("updated_at") or ""), str(item.get("ticket_id") or "")),
        reverse=True,
    ):
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        created_spec = created_specs_by_ticket.get(ticket_id) or {}
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref in {
            SOURCE_CODE_DELIVERY_SCHEMA_REF,
            DELIVERY_CHECK_REPORT_SCHEMA_REF,
        }:
            return ticket_id
    return None


def _closeout_final_evidence_summary(closeout_gate_issue: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(closeout_gate_issue, dict) and closeout_gate_issue:
        reason_code = str(closeout_gate_issue.get("reason_code") or "").strip()
        details = closeout_gate_issue.get("details")
        details = dict(details) if isinstance(details, dict) else {}
        return {
            "status": "REJECTED",
            "reason_code": reason_code,
            "illegal_ref_count": (
                1
                if reason_code == "closeout_illegal_final_artifact_ref"
                else 0
            ),
            "details": details,
        }
    return {
        "status": "ACCEPTED",
        "illegal_ref_count": 0,
    }


def _build_closeout_policy_input(
    *,
    workflow: dict[str, Any],
    tickets: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    closeout_gate_issue: dict[str, Any] | None,
    created_specs_by_ticket: dict[str, dict[str, Any]],
    graph_complete: bool,
    completed_ticket_ids: list[str] | None = None,
) -> dict[str, Any]:
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    parent_ticket_id = _closeout_parent_ticket_id(
        tickets=tickets,
        created_specs_by_ticket=created_specs_by_ticket,
        completed_ticket_ids=completed_ticket_ids,
    )
    closeout_role_profile_ref = "frontend_engineer_primary"
    assignee_employee_id = _select_default_assignee(
        employees,
        role_profile_ref=closeout_role_profile_ref,
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    )
    ticket_payload = None
    if workflow_id and parent_ticket_id and assignee_employee_id:
        goal = str(
            workflow.get("north_star_goal")
            or workflow.get("title")
            or "the current workflow"
        ).strip()
        ticket_payload = _build_ceo_create_ticket_payload(
            workflow_id=workflow_id,
            node_id="node_ceo_delivery_closeout",
            role_profile_ref=closeout_role_profile_ref,
            output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
            assignee_employee_id=assignee_employee_id,
            selection_reason="Collect final delivery evidence and handoff notes into one auditable closeout package.",
            dependency_gate_refs=[parent_ticket_id],
            summary=f"Prepare the final delivery closeout package for {goal}.",
            parent_ticket_id=parent_ticket_id,
        )
    return {
        "readiness": {
            "effective_graph_complete": graph_complete,
            "open_blocking_incident_refs": [
                str(item.get("incident_id") or "").strip()
                for item in incidents
                if str(item.get("incident_id") or "").strip()
            ],
            "open_approval_refs": [
                str(item.get("approval_id") or "").strip()
                for item in approvals
                if str(item.get("approval_id") or "").strip()
            ],
            "delivery_checker_gate_issue": closeout_gate_issue or None,
            "existing_closeout_ticket_id": _latest_closeout_ticket_id(
                created_specs_by_ticket=created_specs_by_ticket,
                effective_ticket_ids=completed_ticket_ids,
            ),
            "closeout_parent_ticket_id": parent_ticket_id,
            "final_evidence_legality_summary": _closeout_final_evidence_summary(
                closeout_gate_issue
            ),
            "ticket_payload": ticket_payload,
        }
    }


def _ticket_graph_node_refs_by_ticket_id(
    ticket_graph_snapshot: TicketGraphSnapshot | None,
) -> dict[str, str]:
    if ticket_graph_snapshot is None:
        return {}
    return {
        str(node.ticket_id or "").strip(): str(node.graph_node_id or "").strip()
        for node in ticket_graph_snapshot.nodes
        if str(node.ticket_id or "").strip() and str(node.graph_node_id or "").strip()
    }


def _node_ref_for_ticket(
    ticket: dict[str, Any],
    node_refs_by_ticket_id: dict[str, str],
) -> str:
    ticket_id = str(ticket.get("ticket_id") or "").strip()
    return node_refs_by_ticket_id.get(ticket_id) or str(ticket.get("node_id") or "").strip()


def _recommended_terminal_followup_action(
    *,
    ticket_status: str,
    terminal_event_type: str,
) -> str | None:
    if terminal_event_type == EVENT_TICKET_TIMED_OUT or ticket_status == "TIMED_OUT":
        return "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    if terminal_event_type == EVENT_TICKET_FAILED or ticket_status == "FAILED":
        return "RESTORE_AND_RETRY_LATEST_FAILURE"
    return None


def _policy_reuse_gate_from_rejection(rejection: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(rejection, dict) or not rejection:
        return None
    return {
        "satisfies": False,
        "reason_code": str(rejection.get("reason_code") or "").strip(),
        "completed_ticket_id": str(rejection.get("completed_ticket_id") or "").strip(),
        "terminal_failed_ticket_id": str(
            rejection.get("terminal_failed_ticket_id") or ""
        ).strip(),
        "details": dict(rejection),
    }


def _build_recovery_policy_input(
    *,
    tickets: list[dict[str, Any]],
    created_specs_by_ticket: dict[str, dict[str, Any]],
    ticket_terminal_events_by_ticket: dict[str, dict[str, Any] | None],
    followup_ticket_plans: list[dict[str, Any]],
    ticket_graph_snapshot: TicketGraphSnapshot | None,
    structured_recovery_policy_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recovery_policy = dict(structured_recovery_policy_input or {})
    actions: list[dict[str, Any]] = [
        dict(item)
        for item in list(recovery_policy.get("actions") or [])
        if isinstance(item, dict)
    ]
    seen_action_refs = {
        str(action.get("action_ref") or "").strip()
        for action in actions
        if str(action.get("action_ref") or "").strip()
    }
    node_refs_by_ticket_id = _ticket_graph_node_refs_by_ticket_id(ticket_graph_snapshot)
    effective_current_ticket_ids = (
        set(node_refs_by_ticket_id)
        if ticket_graph_snapshot is not None
        else {
            str(ticket.get("ticket_id") or "").strip()
            for ticket in tickets
            if str(ticket.get("ticket_id") or "").strip()
        }
    )
    for ticket in sorted(
        tickets,
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("ticket_id") or ""),
        ),
    ):
        ticket_status = str(ticket.get("status") or "").strip().upper()
        if ticket_status not in {"FAILED", "TIMED_OUT"}:
            continue
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        if ticket_id not in effective_current_ticket_ids:
            continue
        action_ref = f"terminal:{ticket_id}"
        if action_ref in seen_action_refs:
            continue
        created_spec = created_specs_by_ticket.get(ticket_id) or {}
        terminal_event = ticket_terminal_events_by_ticket.get(ticket_id) or {}
        terminal_payload = terminal_event.get("payload") if isinstance(terminal_event, dict) else {}
        terminal_payload = terminal_payload if isinstance(terminal_payload, dict) else {}
        terminal_event_type = (
            str(terminal_event.get("event_type") or "").strip()
            if isinstance(terminal_event, dict)
            else ""
        )
        retry_budget = int(created_spec.get("retry_budget") or ticket.get("retry_budget") or 0)
        retry_count = int(ticket.get("retry_count") or created_spec.get("retry_count") or 0)
        failure_kind = str(
            terminal_payload.get("failure_kind")
            or ticket.get("last_failure_kind")
            or ticket_status
        ).strip()
        actions.append(
            {
                "action_ref": action_ref,
                "node_ref": _node_ref_for_ticket(ticket, node_refs_by_ticket_id),
                "ticket_id": ticket_id,
                "terminal_state": ticket_status,
                "retry_count": retry_count,
                "retry_budget": retry_budget,
                "failure_kind": failure_kind,
                "recommended_followup_action": _recommended_terminal_followup_action(
                    ticket_status=ticket_status,
                    terminal_event_type=terminal_event_type,
                ),
                "failure_lineage": {
                    "parent_ticket_id": str(created_spec.get("parent_ticket_id") or "").strip(),
                    "attempt_no": int(created_spec.get("attempt_no") or 1),
                    "terminal_event_type": terminal_event_type,
                },
            }
        )
        seen_action_refs.add(action_ref)

    current_tickets_by_id = {
        str(ticket.get("ticket_id") or "").strip(): ticket
        for ticket in tickets
        if str(ticket.get("ticket_id") or "").strip()
    }
    for followup_plan in followup_ticket_plans:
        if not isinstance(followup_plan, dict):
            continue
        existing_ticket_id = str(followup_plan.get("existing_ticket_id") or "").strip()
        if not existing_ticket_id:
            continue
        ticket = current_tickets_by_id.get(existing_ticket_id)
        if ticket is None:
            action_ref = f"restore-needed:{existing_ticket_id or 'missing-ticket'}"
            if action_ref not in seen_action_refs:
                actions.append(
                    {
                        "action_ref": action_ref,
                        "node_ref": _policy_node_ref_from_ticket_payload(
                            dict(followup_plan.get("ticket_payload") or {})
                        ),
                        "ticket_id": existing_ticket_id,
                        "restore_needed": True,
                    }
                )
                seen_action_refs.add(action_ref)
            continue
        rejection = followup_plan.get("completed_ticket_gate_rejection")
        reuse_gate = _policy_reuse_gate_from_rejection(
            rejection if isinstance(rejection, dict) else None
        )
        if reuse_gate is None:
            continue
        action_ref = f"reuse-gate:{existing_ticket_id}"
        if action_ref in seen_action_refs:
            continue
        actions.append(
            {
                "action_ref": action_ref,
                "node_ref": _node_ref_for_ticket(ticket, node_refs_by_ticket_id),
                "ticket_id": existing_ticket_id,
                "completed_ticket_reuse_gate": reuse_gate,
                "superseded_lineage_refs": (
                    [reuse_gate["completed_ticket_id"]]
                    if reuse_gate["reason_code"] == "completed_ticket_superseded"
                    and reuse_gate["completed_ticket_id"]
                    else []
                ),
                "invalidated_lineage_refs": (
                    [reuse_gate["completed_ticket_id"]]
                    if reuse_gate["reason_code"] == "completed_ticket_lineage_invalidated"
                    and reuse_gate["completed_ticket_id"]
                    else []
                ),
            }
        )
        seen_action_refs.add(action_ref)

    recovery_policy["actions"] = actions
    loop_signals = [
        dict(item)
        for item in list(recovery_policy.get("loop_signals") or [])
        if isinstance(item, dict)
    ]
    recovery_policy["loop_signals"] = loop_signals
    return recovery_policy


def _policy_create_ticket_payload(proposal: dict[str, Any]) -> dict[str, Any]:
    payload = proposal.get("payload") or {}
    ticket_payload = payload.get("ticket_payload") if isinstance(payload, dict) else {}
    return dict(ticket_payload) if isinstance(ticket_payload, dict) else {}


def _ticket_plan_matches_payload(ticket_plan: dict[str, Any], ticket_payload: dict[str, Any]) -> bool:
    plan_payload = ticket_plan.get("ticket_payload")
    if not isinstance(plan_payload, dict):
        return False
    return (
        str(plan_payload.get("node_id") or "").strip() == str(ticket_payload.get("node_id") or "").strip()
        and str(plan_payload.get("role_profile_ref") or "").strip()
        == str(ticket_payload.get("role_profile_ref") or "").strip()
        and str(plan_payload.get("output_schema_ref") or "").strip()
        == str(ticket_payload.get("output_schema_ref") or "").strip()
    )


def _selected_governance_ticket_plan_from_policy_proposal(
    proposal: dict[str, Any] | None,
    *,
    governance_ticket_plans: list[dict[str, Any]],
    required_governance_ticket_plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(proposal, dict):
        return required_governance_ticket_plan
    action_type = str(proposal.get("action_type") or "").strip()
    metadata = proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {}
    reason_code = str((metadata or {}).get("reason_code") or "").strip()
    if action_type not in {ProgressionActionType.CREATE_TICKET.value, ProgressionActionType.WAIT.value}:
        return required_governance_ticket_plan
    if not (
        reason_code.startswith("progression.governance.")
        or reason_code.startswith("progression.wait.governance")
    ):
        return required_governance_ticket_plan
    ticket_payload = _policy_create_ticket_payload(proposal)
    if not ticket_payload:
        payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
        for key in ("governance_gate", "governance_followup"):
            policy_plan = payload.get(key) if isinstance(payload, dict) else {}
            if isinstance(policy_plan, dict):
                nested_payload = policy_plan.get("ticket_payload")
                if isinstance(nested_payload, dict):
                    ticket_payload = dict(nested_payload)
                    break
    if not ticket_payload:
        return required_governance_ticket_plan
    if (
        required_governance_ticket_plan is not None
        and _ticket_plan_matches_payload(required_governance_ticket_plan, ticket_payload)
    ):
        return required_governance_ticket_plan
    return next(
        (
            plan
            for plan in governance_ticket_plans
            if isinstance(plan, dict) and _ticket_plan_matches_payload(plan, ticket_payload)
        ),
        required_governance_ticket_plan,
    )


def _controller_state_from_policy_proposal(
    proposal: dict[str, Any] | None,
    *,
    required_governance_ticket_plan: dict[str, Any] | None,
    followup_ticket_plans: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(proposal, dict):
        return None
    action_type = str(proposal.get("action_type") or "").strip()
    metadata = proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {}
    reason_code = str((metadata or {}).get("reason_code") or "").strip()
    if action_type == ProgressionActionType.CREATE_TICKET.value:
        if reason_code.startswith("progression.governance."):
            if (
                reason_code
                in {
                    "progression.governance.architect_gate_required",
                    "progression.governance.followup_required",
                    "progression.governance.gate_required",
                }
                and required_governance_ticket_plan is not None
                and _required_governance_ticket_missing_assignee(required_governance_ticket_plan)
            ):
                required_role_profile_ref = str(
                    ((required_governance_ticket_plan.get("ticket_payload") or {}).get("role_profile_ref") or "")
                ).strip()
                return {
                    "state": (
                        "ARCHITECT_REQUIRED"
                        if required_role_profile_ref == "architect_primary"
                        else "STAFFING_REQUIRED"
                    ),
                    "recommended_action": "HIRE_EMPLOYEE",
                    "blocking_reason": (
                        "Structured governance policy requires an eligible assignee before "
                        "the governance ticket can be assigned."
                    ),
                }
            return {
                "state": (
                    "ARCHITECT_REQUIRED"
                    if reason_code == "progression.governance.architect_gate_required"
                    else "GOVERNANCE_REQUIRED"
                ),
                "recommended_action": "CREATE_TICKET",
                "blocking_reason": "Structured governance policy requires a governance ticket before fanout.",
            }
        if reason_code.startswith("progression.fanout.") and followup_ticket_plans:
            return {
                "state": "READY_FOR_FANOUT",
                "recommended_action": "CREATE_TICKET",
                "blocking_reason": None,
            }
    if action_type == ProgressionActionType.CLOSEOUT.value:
        return {
            "state": "CLOSEOUT_REQUIRED",
            "recommended_action": "CREATE_TICKET",
            "blocking_reason": "Structured closeout policy requires a final closeout ticket.",
        }
    if action_type == ProgressionActionType.REWORK.value:
        return {
            "state": "REWORK_REQUIRED",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Structured recovery policy requires rework before progression continues.",
        }
    if action_type == ProgressionActionType.INCIDENT.value:
        return {
            "state": "INCIDENT_REQUIRED",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Structured recovery policy requires opening an incident before progression continues.",
        }
    if action_type == ProgressionActionType.WAIT.value:
        if reason_code == "progression.wait.meeting_requirement":
            return {
                "state": "MEETING_REQUIRED",
                "recommended_action": "REQUEST_MEETING",
                "blocking_reason": "A structured meeting requirement must be approved before fanout.",
            }
        if reason_code == "progression.wait.closeout_blockers":
            return {
                "state": "CLOSEOUT_GATE_BLOCKED",
                "recommended_action": "NO_ACTION",
                "blocking_reason": "Structured closeout policy is waiting on closeout blockers.",
            }
        if reason_code.startswith("progression.wait.governance") and required_governance_ticket_plan is not None:
            return {
                "state": "GOVERNANCE_REQUIRED",
                "recommended_action": "NO_ACTION",
                "blocking_reason": "The required governance ticket already exists and must finish first.",
            }
    return None


def _is_closeout_or_recovery_policy_proposal(proposal: dict[str, Any] | None) -> bool:
    if not isinstance(proposal, dict):
        return False
    action_type = str(proposal.get("action_type") or "").strip()
    metadata = proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {}
    reason_code = str((metadata or {}).get("reason_code") or "").strip()
    if action_type in {
        ProgressionActionType.CLOSEOUT.value,
        ProgressionActionType.REWORK.value,
        ProgressionActionType.INCIDENT.value,
    }:
        return True
    return reason_code.startswith("progression.closeout.") or reason_code.startswith(
        "progression.wait.closeout"
    )


def _apply_policy_controller_side_effects(
    *,
    controller_state: dict[str, Any],
    employees: list[dict[str, Any]],
    policy_meeting_candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    controller_meeting_candidate = None
    if (
        controller_state["state"] == "ARCHITECT_REQUIRED"
        and controller_state["recommended_action"] == "CREATE_TICKET"
        and not _active_board_approved_employees(employees, role_profile_ref="architect_primary")
    ):
        controller_state = {
            "state": "ARCHITECT_REQUIRED",
            "recommended_action": "HIRE_EMPLOYEE",
            "blocking_reason": (
                "Structured architect governance policy requires a board-approved architect before "
                "the governance ticket can be assigned."
            ),
        }
    if controller_state["state"] == "MEETING_REQUIRED":
        controller_meeting_candidate = next(
            (
                item
                for item in policy_meeting_candidates
                if bool(item.get("eligible"))
            ),
            policy_meeting_candidates[0] if policy_meeting_candidates else None,
        )
    return controller_state, controller_meeting_candidate


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
    graph_health_report: dict[str, Any] | None = None,
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
    # Graph ready/blocked/in-flight indexes are compiled by progression policy
    # through ticket_graph. Controller-specific branches below are limited to
    # input compilation, dispatch guards, and API display state.
    hard_constraints = _load_workflow_hard_constraints(connection, workflow_id)
    governance_requirements = _load_workflow_governance_requirements(connection, workflow_id)
    structured_progression_policy_input = _load_workflow_progression_policy_input(connection, workflow_id)
    created_specs_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
        for ticket in tickets
    }
    ticket_terminal_events_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_terminal_event(connection, str(ticket["ticket_id"]))
        for ticket in tickets
    }
    ready_ticket_staffing_assessment = _build_ready_ticket_staffing_assessment(
        repository,
        ready_ticket_ids=graph_ready_ticket_ids,
        tickets=tickets,
        created_specs_by_ticket=created_specs_by_ticket,
        employees=employees,
        connection=connection,
    )
    ready_ticket_staffing_gaps = list(ready_ticket_staffing_assessment["ready_ticket_staffing_gaps"])
    contract_issues = list(ready_ticket_staffing_assessment["contract_issues"])
    reuse_candidate_employee_ids = list(ready_ticket_staffing_assessment["reuse_candidate_employee_ids"])
    staffing_wait_reasons = list(ready_ticket_staffing_assessment["staffing_wait_reasons"])
    closeout_gate_issue = evaluate_workflow_closeout_gate_issue(
        tickets=tickets,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )
    backlog_ticket_id, backlog_created_spec, backlog_payload = _latest_completed_backlog_ticket(
        repository,
        workflow_id=workflow_id,
        trigger_ref=trigger_ref,
        connection=connection,
    )
    completed_governance_ticket_ids_by_schema = _latest_completed_governance_ticket_ids_by_schema(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    governance_ticket_plans = _build_governance_progression_ticket_plans(
        repository,
        workflow=workflow,
        tickets=tickets,
        workflow_nodes=nodes,
        employees=employees,
        connection=connection,
    )
    selected_governance_chain_ticket_plan = next(
        (
            plan
            for plan in governance_ticket_plans
            if isinstance(plan, dict)
            and str(((plan.get("ticket_payload") or {}).get("output_schema_ref") or "")).strip()
            == next(
                (
                    schema_ref
                    for schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER
                    if schema_ref not in completed_governance_ticket_ids_by_schema
                ),
                "",
            )
        ),
        None,
    )
    followup_ticket_plans: list[dict[str, Any]] = []
    task_type = "steady_state"
    deliverable_kind = None
    coordination_mode = "wait"
    if selected_governance_chain_ticket_plan is not None:
        task_type = "governance_followup"
        deliverable_kind = "structured_document_delivery"
        coordination_mode = "document_chain"
    if backlog_ticket_id and isinstance(backlog_payload, dict):
        followup_ticket_plans = _build_followup_ticket_plans(
            workflow_id=workflow_id,
            backlog_ticket_id=backlog_ticket_id,
            backlog_created_spec=backlog_created_spec,
            backlog_payload=backlog_payload,
            tickets=tickets,
            workflow_nodes=nodes,
            employees=employees,
        )
        if followup_ticket_plans and selected_governance_chain_ticket_plan is None:
            task_type = "implementation_fanout"
            deliverable_kind = SOURCE_CODE_DELIVERY_SCHEMA_REF
            coordination_mode = "fanout"

    requires_architect = any(
        str(item.get("gate_type") or "").strip().upper() == "ARCHITECT_GOVERNANCE"
        for item in list(governance_requirements.get("required_gates") or [])
        if isinstance(item, dict)
    )
    requires_meeting = any(
        isinstance(item, dict)
        for item in list(governance_requirements.get("meeting_requirements") or [])
    )
    staffing_gaps = sorted(
        {
            str((plan.get("ticket_payload") or {}).get("role_profile_ref") or "").strip()
            for plan in followup_ticket_plans
            if plan.get("existing_ticket_id") is None
            and str((plan.get("ticket_payload") or {}).get("role_profile_ref") or "").strip()
            and not str(
                (((plan.get("ticket_payload") or {}).get("dispatch_intent") or {}).get("assignee_employee_id") or "")
            ).strip()
        }
    )
    staffing_gaps = sorted(
        set(staffing_gaps)
        | {
            str(gap.get("required_role_profile_ref") or "").strip()
            for gap in ready_ticket_staffing_gaps
            if str(gap.get("required_role_profile_ref") or "").strip()
        }
    )

    controller_state = {
        "state": "NO_IMMEDIATE_FOLLOWUP",
        "recommended_action": "NO_ACTION",
        "blocking_reason": None,
    }
    controller_meeting_candidate = None
    graph_version = (
        str(ticket_graph_snapshot.graph_version)
        if ticket_graph_snapshot is not None
        else f"workflow:{workflow_id}:legacy"
    )
    governance_policy_input, required_governance_ticket_plan, policy_meeting_candidates = (
        _build_governance_policy_input(
            repository=repository,
            governance_requirements=governance_requirements,
            structured_governance_policy_input=(
                structured_progression_policy_input.get("governance")
                if isinstance(structured_progression_policy_input.get("governance"), dict)
                else {}
            ),
            governance_ticket_plans=governance_ticket_plans,
            completed_governance_ticket_ids_by_schema=completed_governance_ticket_ids_by_schema,
            workflow_id=workflow_id,
            backlog_ticket_id=backlog_ticket_id,
            backlog_created_spec=backlog_created_spec,
            tickets=tickets,
            workflow_nodes=nodes,
            employees=employees,
            connection=connection,
        )
    )
    fanout_policy_input = _build_fanout_policy_input(
        source_ticket_id=backlog_ticket_id,
        graph_version=graph_version,
        followup_ticket_plans=followup_ticket_plans,
        structured_fanout_policy_input=(
            structured_progression_policy_input.get("fanout")
            if isinstance(structured_progression_policy_input.get("fanout"), dict)
            else {}
        ),
    )
    progression_snapshot = _progression_snapshot_from_controller_inputs(
        workflow_id=workflow_id,
        graph_version=graph_version,
        tickets=tickets,
        ticket_graph_snapshot=ticket_graph_snapshot,
        approvals=approvals,
        incidents=incidents,
    )
    progression_graph_evaluation = evaluate_progression_graph(progression_snapshot)
    closeout_policy_input = _build_closeout_policy_input(
        workflow=workflow,
        tickets=tickets,
        employees=employees,
        approvals=approvals,
        incidents=incidents,
        closeout_gate_issue=closeout_gate_issue,
        created_specs_by_ticket=created_specs_by_ticket,
        graph_complete=progression_graph_evaluation.graph_complete,
        completed_ticket_ids=progression_graph_evaluation.completed_ticket_ids,
    )
    recovery_policy_input = _build_recovery_policy_input(
        tickets=tickets,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
        followup_ticket_plans=followup_ticket_plans,
        ticket_graph_snapshot=ticket_graph_snapshot,
        structured_recovery_policy_input=(
            structured_progression_policy_input.get("recovery")
            if isinstance(structured_progression_policy_input.get("recovery"), dict)
            else {}
        ),
    )
    progression_policy = ProgressionPolicy(
        policy_ref=f"progression-policy:{workflow_id}:{graph_version}:8d",
        governance=governance_policy_input,
        fanout=fanout_policy_input,
        closeout=closeout_policy_input,
        recovery=recovery_policy_input,
    )
    progression_policy_proposals = [
        proposal.model_dump(mode="json")
        for proposal in decide_next_actions(progression_snapshot, progression_policy)
    ]
    primary_policy_proposal = progression_policy_proposals[0] if progression_policy_proposals else None
    required_governance_ticket_plan = _selected_governance_ticket_plan_from_policy_proposal(
        primary_policy_proposal,
        governance_ticket_plans=governance_ticket_plans,
        required_governance_ticket_plan=required_governance_ticket_plan,
    )

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
    elif _graph_health_requires_pause(graph_health_report):
        controller_state = {
            "state": "GRAPH_HEALTH_WAIT",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Critical graph health recommends pausing new fanout until recovery is confirmed.",
        }
    elif _is_closeout_or_recovery_policy_proposal(primary_policy_proposal) and (
        policy_controller_state := _controller_state_from_policy_proposal(
        primary_policy_proposal,
        required_governance_ticket_plan=required_governance_ticket_plan,
        followup_ticket_plans=followup_ticket_plans,
        )
    ) is not None:
        controller_state, controller_meeting_candidate = _apply_policy_controller_side_effects(
            controller_state=policy_controller_state,
            employees=employees,
            policy_meeting_candidates=policy_meeting_candidates,
        )
    elif contract_issues:
        first_issue = contract_issues[0]
        controller_state = {
            "state": "CONTRACT_REPLAN_REQUIRED",
            "recommended_action": "NO_ACTION",
            "blocking_reason": (
                "A ready ticket has an invalid execution contract for "
                f"{first_issue['required_role_profile_ref']} and must be replanned."
            ),
        }
    elif ready_ticket_staffing_gaps:
        first_gap = ready_ticket_staffing_gaps[0]
        controller_state = {
            "state": "STAFFING_REQUIRED",
            "recommended_action": "HIRE_EMPLOYEE",
            "blocking_reason": (
                "A ready ticket cannot be leased because no eligible worker matches "
                f"{first_gap['required_role_profile_ref']}."
            ),
        }
    elif staffing_wait_reasons:
        first_wait_reason = staffing_wait_reasons[0]
        controller_state = {
            "state": "STAFFING_WAIT",
            "recommended_action": "NO_ACTION",
            "blocking_reason": (
                "A ready ticket has matching workers, but dispatch must wait because "
                f"{first_wait_reason['reason_code']} blocks the current roster."
            ),
        }
    elif graph_ready_ticket_ids:
        controller_state = {
            "state": "READY_TICKET",
            "recommended_action": "NO_ACTION",
            "blocking_reason": "Ready tickets already exist on the current mainline.",
        }
    elif (
        not _is_closeout_or_recovery_policy_proposal(primary_policy_proposal)
        and (
            policy_controller_state := _controller_state_from_policy_proposal(
                primary_policy_proposal,
                required_governance_ticket_plan=required_governance_ticket_plan,
                followup_ticket_plans=followup_ticket_plans,
            )
        )
        is not None
    ):
        controller_state, controller_meeting_candidate = _apply_policy_controller_side_effects(
            controller_state=policy_controller_state,
            employees=employees,
            policy_meeting_candidates=policy_meeting_candidates,
        )
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
            else str(
                (((required_governance_ticket_plan or {}).get("ticket_payload") or {}).get("parent_ticket_id") or "")
            ).strip()
            or None
        ),
        "source_node_id": (
            str(backlog_created_spec.get("node_id") or "").strip() or None
            if task_type == "implementation_fanout"
            else None
        ),
        "hard_constraints": hard_constraints,
        "governance_requirements": governance_requirements,
        "progression_adapter_id": progression_adapter_id,
    }
    ceo_hire_loop_summary = ceo_hire_loop_summary_from_incidents(incidents)
    capability_plan = {
        "required_capabilities": sorted(
            {
                capability
                for plan in followup_ticket_plans
                for capability in list(
                    ((plan.get("ticket_payload") or {}).get("execution_contract") or {}).get(
                        "required_capability_tags"
                    )
                    or []
                )
            }
        ),
        "optional_capabilities": [],
        "staffing_gaps": staffing_gaps,
        "requires_architect": requires_architect,
        "requires_meeting": requires_meeting,
        "required_governance_ticket_plan": required_governance_ticket_plan,
        "followup_ticket_plans": followup_ticket_plans,
        "ready_ticket_staffing_gaps": ready_ticket_staffing_gaps,
        "contract_issues": contract_issues,
        "reuse_candidate_employee_ids": reuse_candidate_employee_ids,
        "staffing_wait_reasons": staffing_wait_reasons,
        "progression_adapter_id": progression_adapter_id,
        "progression_policy": progression_policy.model_dump(mode="json"),
        "progression_policy_proposals": progression_policy_proposals,
    }
    if closeout_gate_issue is not None:
        capability_plan["closeout_gate_issue"] = closeout_gate_issue
    if ceo_hire_loop_summary is not None:
        capability_plan["ceo_hire_loop_summary"] = ceo_hire_loop_summary
    if required_governance_ticket_plan is not None:
        capability_plan["required_capabilities"] = sorted(
            set(capability_plan["required_capabilities"])
            | set(
                (
                    ((required_governance_ticket_plan.get("ticket_payload") or {}).get("execution_contract") or {})
                    .get("required_capability_tags")
                    or []
                )
            )
        )
    if controller_state["recommended_action"] == "HIRE_EMPLOYEE":
        if ready_ticket_staffing_gaps:
            first_gap = ready_ticket_staffing_gaps[0]
            request_summary = (
                "Hire additional "
                f"{first_gap['required_role_profile_ref']} capacity so ready ticket "
                f"{first_gap['ticket_id']} can be leased while existing workers are busy."
                if str(first_gap.get("reason_code") or "") == "WORKER_BUSY"
                else (
                    "Hire "
                    f"{first_gap['required_role_profile_ref']} so ready ticket "
                    f"{first_gap['ticket_id']} can be leased."
                )
            )
            capability_plan["recommended_hire"] = {
                "role_type": str(first_gap["role_type"]),
                "role_profile_refs": [str(first_gap["required_role_profile_ref"])],
                "request_summary": request_summary,
            }
        elif (
            required_governance_ticket_plan is not None
            and _required_governance_ticket_missing_assignee(required_governance_ticket_plan)
        ):
            recommended_hire = _recommended_hire_for_role_profile(
                str(
                    ((required_governance_ticket_plan.get("ticket_payload") or {}).get("role_profile_ref") or "")
                )
            )
            if recommended_hire is not None:
                capability_plan["recommended_hire"] = recommended_hire
        elif controller_state["state"] == "ARCHITECT_REQUIRED":
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
        if isinstance(capability_plan.get("recommended_hire"), dict):
            repeated_rejection = _recent_role_already_covered_hire_rejection(
                repository,
                workflow_id=workflow_id,
                recommended_hire=dict(capability_plan["recommended_hire"]),
                employees=employees,
                connection=connection,
            )
            if repeated_rejection is not None:
                capability_plan.pop("recommended_hire", None)
                reuse_candidate_employee_ids = sorted(
                    set(capability_plan.get("reuse_candidate_employee_ids") or [])
                    | {str(repeated_rejection["reuse_candidate_employee_id"])}
                )
                capability_plan["reuse_candidate_employee_ids"] = reuse_candidate_employee_ids
                capability_plan.setdefault("staffing_wait_reasons", []).append(repeated_rejection)
                controller_state = {
                    "state": "STAFFING_WAIT",
                    "recommended_action": "NO_ACTION",
                    "blocking_reason": (
                        "A recent CEO hire proposal was rejected because the requested role profile is already "
                        f"covered by {repeated_rejection['reuse_candidate_employee_id']}."
                    ),
                }

    return {
        "task_sensemaking": task_sensemaking,
        "capability_plan": capability_plan,
        "controller_state": controller_state,
        "meeting_candidates": combined_meeting_candidates,
        "ticket_graph_summary": graph_index_summary,
        "progression_policy": progression_policy.model_dump(mode="json"),
        "progression_policy_proposals": progression_policy_proposals,
    }
