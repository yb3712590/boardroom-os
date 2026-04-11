from __future__ import annotations

from typing import Any

from app.core.ceo_execution_presets import (
    GOVERNANCE_DOCUMENT_CHAIN_ORDER,
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
    PROJECT_INIT_SCOPE_NODE_ID,
    build_autopilot_architecture_brief_summary,
    build_project_init_scope_summary,
    supports_ceo_create_ticket_preset,
)
from app.core.execution_targets import (
    employee_supports_execution_contract,
    infer_execution_contract_payload,
)
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate

AUTOPILOT_GOVERNANCE_CHAIN = "AUTOPILOT_GOVERNANCE_CHAIN"
STANDARD_LEGACY_SCOPE_CHAIN = "STANDARD_LEGACY_SCOPE_CHAIN"

_GOVERNANCE_ROLE_PRIORITY_BY_SCHEMA: dict[str, tuple[str, ...]] = {
    ARCHITECTURE_BRIEF_SCHEMA_REF: (
        "frontend_engineer_primary",
        "architect_primary",
        "cto_primary",
        "ui_designer_primary",
    ),
    TECHNOLOGY_DECISION_SCHEMA_REF: (
        "frontend_engineer_primary",
        "architect_primary",
        "cto_primary",
        "ui_designer_primary",
    ),
    MILESTONE_PLAN_SCHEMA_REF: (
        "frontend_engineer_primary",
        "cto_primary",
        "ui_designer_primary",
    ),
    DETAILED_DESIGN_SCHEMA_REF: (
        "frontend_engineer_primary",
        "architect_primary",
        "ui_designer_primary",
    ),
    BACKLOG_RECOMMENDATION_SCHEMA_REF: (
        "frontend_engineer_primary",
        "cto_primary",
        "ui_designer_primary",
    ),
}


def resolve_workflow_progression_adapter(workflow: dict[str, Any] | None) -> str:
    if workflow_uses_ceo_board_delegate(workflow):
        return AUTOPILOT_GOVERNANCE_CHAIN
    return STANDARD_LEGACY_SCOPE_CHAIN


def build_project_init_kickoff_spec(workflow: dict[str, Any] | None) -> dict[str, Any]:
    workflow = workflow or {}
    adapter_id = resolve_workflow_progression_adapter(workflow)
    north_star_goal = str(workflow.get("north_star_goal") or workflow.get("title") or "").strip()
    if adapter_id == AUTOPILOT_GOVERNANCE_CHAIN:
        return {
            "adapter_id": adapter_id,
            "node_id": PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
            "role_profile_ref": "frontend_engineer_primary",
            "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
            "summary": build_autopilot_architecture_brief_summary(north_star_goal),
        }
    return {
        "adapter_id": adapter_id,
        "node_id": PROJECT_INIT_SCOPE_NODE_ID,
        "role_profile_ref": "ui_designer_primary",
        "output_schema_ref": "consensus_document",
        "summary": build_project_init_scope_summary(north_star_goal),
    }


def workflow_progression_supports_legacy_scope_followups(workflow: dict[str, Any] | None) -> bool:
    return resolve_workflow_progression_adapter(workflow) == STANDARD_LEGACY_SCOPE_CHAIN


def resolve_next_governance_schema(completed_ticket_ids_by_schema: dict[str, str]) -> str | None:
    for output_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        if not completed_ticket_ids_by_schema.get(output_schema_ref):
            return output_schema_ref
    return None


def governance_dependency_gate_refs(
    completed_ticket_ids_by_schema: dict[str, str],
    output_schema_ref: str,
) -> list[str]:
    if output_schema_ref not in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        return []
    dependency_gate_refs: list[str] = []
    for prerequisite_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER[
        : GOVERNANCE_DOCUMENT_CHAIN_ORDER.index(output_schema_ref)
    ]:
        ticket_id = str(completed_ticket_ids_by_schema.get(prerequisite_schema_ref) or "").strip()
        if ticket_id:
            dependency_gate_refs.append(ticket_id)
    return dependency_gate_refs


def governance_parent_ticket_id(
    completed_ticket_ids_by_schema: dict[str, str],
    output_schema_ref: str,
) -> str | None:
    dependency_gate_refs = governance_dependency_gate_refs(completed_ticket_ids_by_schema, output_schema_ref)
    return dependency_gate_refs[-1] if dependency_gate_refs else None


def build_governance_followup_node_id(output_schema_ref: str) -> str:
    return f"node_ceo_{output_schema_ref}"


def build_governance_followup_summary(output_schema_ref: str) -> str:
    label = output_schema_ref.replace("_", " ")
    return f"Prepare the {label} before implementation fanout continues."


def select_governance_role_and_assignee(
    employees: list[dict[str, Any]],
    *,
    output_schema_ref: str,
) -> tuple[str | None, str | None]:
    for role_profile_ref in _GOVERNANCE_ROLE_PRIORITY_BY_SCHEMA.get(output_schema_ref, ()):
        if not supports_ceo_create_ticket_preset(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        ):
            continue
        execution_contract = infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        if execution_contract is None:
            continue
        for employee in sorted(employees, key=lambda item: str(item.get("employee_id") or "")):
            if str(employee.get("state") or "") != "ACTIVE":
                continue
            if not employee_supports_execution_contract(
                employee=employee,
                execution_contract=execution_contract,
            ):
                continue
            return role_profile_ref, str(employee["employee_id"])
    return None, None
