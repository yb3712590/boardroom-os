from __future__ import annotations

from typing import Any

from app.contracts.ceo_actions import CEOCreateTicketPayload
from app.contracts.commands import CommandAckEnvelope, TicketCreateCommand
from app.core.ceo_execution_presets import build_ceo_create_ticket_command
from app.core.constants import EMPLOYEE_STATE_ACTIVE
from app.core.execution_targets import employee_supports_execution_contract, infer_execution_contract_payload
from app.core.ticket_handlers import handle_ticket_create
from app.core.workflow_progression import build_project_init_kickoff_spec
from app.db.repository import ControlPlaneRepository


def _select_kickoff_assignee(
    repository: ControlPlaneRepository,
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
    employees = sorted(
        repository.list_employee_projections(
            states=[EMPLOYEE_STATE_ACTIVE],
            board_approved_only=True,
        ),
        key=lambda item: str(item.get("employee_id") or ""),
    )
    for employee in employees:
        if employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            return str(employee["employee_id"])
    return None


def create_project_init_governance_kickoff_ticket(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    workflow: dict[str, Any] | None = None,
    extra_input_artifact_refs: list[str] | None = None,
) -> CommandAckEnvelope:
    workflow_projection = workflow or repository.get_workflow_projection(workflow_id)
    if workflow_projection is None:
        raise ValueError("Workflow projection missing during project-init governance kickoff.")

    kickoff_spec = build_project_init_kickoff_spec(workflow_projection)
    role_profile_ref = str(kickoff_spec["role_profile_ref"])
    output_schema_ref = str(kickoff_spec["output_schema_ref"])
    assignee_employee_id = _select_kickoff_assignee(
        repository,
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    dispatch_intent = (
        {
            "assignee_employee_id": assignee_employee_id,
            "selection_reason": "Assign the initial governance kickoff to an active worker that satisfies the execution contract.",
            "dependency_gate_refs": [],
            "selected_by": "system",
            "wakeup_policy": "default",
        }
        if assignee_employee_id is not None
        else None
    )
    payload = CEOCreateTicketPayload(
        workflow_id=workflow_id,
        node_id=str(kickoff_spec["node_id"]),
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
        dispatch_intent=dispatch_intent,
        summary=str(kickoff_spec["summary"]),
        parent_ticket_id=None,
    )
    command = build_ceo_create_ticket_command(
        workflow=workflow_projection,
        payload=payload,
        repository=repository,
    )
    input_artifact_refs = list(command.input_artifact_refs)
    for artifact_ref in extra_input_artifact_refs or []:
        normalized_ref = str(artifact_ref).strip()
        if normalized_ref and normalized_ref not in input_artifact_refs:
            input_artifact_refs.append(normalized_ref)
    if input_artifact_refs != list(command.input_artifact_refs):
        command = TicketCreateCommand.model_validate(
            {
                **command.model_dump(mode="json"),
                "input_artifact_refs": input_artifact_refs,
            }
        )
    return handle_ticket_create(repository, command)
