from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    TicketCompletedCommand,
    TicketFailCommand,
    TicketStartCommand,
)
from app.core.ticket_handlers import (
    handle_ticket_completed,
    handle_ticket_fail,
    handle_ticket_start,
)
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class RuntimeBridgeExecutionPackage:
    workflow_id: str
    ticket_id: str
    node_id: str
    lease_owner: str
    employee_role_type: str
    role_profile_ref: str
    constraints_ref: str
    input_artifact_refs: list[str]
    acceptance_criteria: list[str]
    allowed_tools: list[str]
    allowed_write_set: list[str]
    output_schema_ref: str
    output_schema_version: int
    retry_budget: int
    timeout_sla_sec: int
    escalation_policy: dict[str, Any]
    bridge_contract_version: str = "runtime-bridge.v1"


@dataclass(frozen=True)
class RuntimeExecutionResult:
    result_status: str
    completion_summary: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    result_payload: dict[str, Any] = field(default_factory=dict)
    failure_kind: str | None = None
    failure_message: str | None = None
    failure_detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeExecutionOutcome:
    ticket_id: str
    lease_owner: str
    start_ack: CommandAckEnvelope
    final_ack: CommandAckEnvelope | None


SUPPORTED_RUNTIME_OUTPUT_SCHEMA = "ui_milestone_review"
SUPPORTED_RUNTIME_ROLE_PROFILES = {"ui_designer_primary", "checker_primary"}


def _runtime_sort_key(ticket: dict[str, Any]) -> tuple:
    return ticket["updated_at"], ticket["ticket_id"]


def _build_start_idempotency_key(ticket: dict[str, Any]) -> str:
    return f"runtime-start:{ticket['workflow_id']}:{ticket['ticket_id']}:{ticket['lease_owner']}"


def _build_complete_idempotency_key(ticket: dict[str, Any]) -> str:
    return f"runtime-complete:{ticket['workflow_id']}:{ticket['ticket_id']}"


def _build_fail_idempotency_key(ticket: dict[str, Any], failure_kind: str) -> str:
    return f"runtime-fail:{ticket['workflow_id']}:{ticket['ticket_id']}:{failure_kind}"


def _list_runtime_startable_leased_tickets(
    repository: ControlPlaneRepository,
) -> list[dict[str, Any]]:
    now = now_local()
    leased_tickets = repository.list_ticket_projections_by_statuses_readonly(["LEASED"])
    runnable_tickets = []
    for ticket in leased_tickets:
        lease_owner = ticket.get("lease_owner")
        lease_expires_at = ticket.get("lease_expires_at")
        if lease_owner is None or lease_expires_at is None or lease_expires_at <= now:
            continue
        node_projection = repository.get_current_node_projection(ticket["workflow_id"], ticket["node_id"])
        if node_projection is None:
            continue
        if node_projection["latest_ticket_id"] != ticket["ticket_id"] or node_projection["status"] != "PENDING":
            continue
        runnable_tickets.append(ticket)
    return sorted(runnable_tickets, key=_runtime_sort_key)


def _build_runtime_bridge_execution_package(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
) -> RuntimeBridgeExecutionPackage:
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
        if created_spec is None:
            raise ValueError("Ticket create spec is missing for runtime execution.")

    lease_owner = ticket.get("lease_owner")
    if lease_owner is None:
        raise ValueError("Ticket lease owner is missing for runtime execution.")
    employee = repository.get_employee_projection(lease_owner)
    if employee is None:
        raise ValueError(f"Employee {lease_owner} is missing from employee_projection.")

    return RuntimeBridgeExecutionPackage(
        workflow_id=ticket["workflow_id"],
        ticket_id=ticket["ticket_id"],
        node_id=ticket["node_id"],
        lease_owner=lease_owner,
        employee_role_type=str(employee.get("role_type") or "unknown"),
        role_profile_ref=str(created_spec.get("role_profile_ref") or ""),
        constraints_ref=str(created_spec.get("constraints_ref") or ""),
        input_artifact_refs=list(created_spec.get("input_artifact_refs") or []),
        acceptance_criteria=list(created_spec.get("acceptance_criteria") or []),
        allowed_tools=list(created_spec.get("allowed_tools") or []),
        allowed_write_set=list(created_spec.get("allowed_write_set") or []),
        output_schema_ref=str(created_spec.get("output_schema_ref") or ""),
        output_schema_version=int(created_spec.get("output_schema_version") or 0),
        retry_budget=int(created_spec.get("retry_budget") or 0),
        timeout_sla_sec=int(created_spec.get("timeout_sla_sec") or 0),
        escalation_policy=dict(created_spec.get("escalation_policy") or {}),
    )


def _execute_runtime_bridge_package(
    execution_package: RuntimeBridgeExecutionPackage,
) -> RuntimeExecutionResult:
    if execution_package.role_profile_ref not in SUPPORTED_RUNTIME_ROLE_PROFILES:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="UNSUPPORTED_RUNTIME_EXECUTION",
            failure_message=(
                f"Runtime bridge executor does not support role profile "
                f"{execution_package.role_profile_ref}."
            ),
            failure_detail={
                "bridge_contract_version": execution_package.bridge_contract_version,
                "role_profile_ref": execution_package.role_profile_ref,
                "output_schema_ref": execution_package.output_schema_ref,
            },
        )

    if execution_package.output_schema_ref != SUPPORTED_RUNTIME_OUTPUT_SCHEMA:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="UNSUPPORTED_RUNTIME_EXECUTION",
            failure_message=(
                f"Runtime bridge executor does not support output schema "
                f"{execution_package.output_schema_ref}."
            ),
            failure_detail={
                "bridge_contract_version": execution_package.bridge_contract_version,
                "role_profile_ref": execution_package.role_profile_ref,
                "output_schema_ref": execution_package.output_schema_ref,
                "output_schema_version": execution_package.output_schema_version,
            },
        )

    if not execution_package.input_artifact_refs:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="RUNTIME_INPUT_ERROR",
            failure_message="Runtime bridge executor requires at least one input artifact reference.",
            failure_detail={
                "bridge_contract_version": execution_package.bridge_contract_version,
                "ticket_id": execution_package.ticket_id,
            },
        )

    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=(
            f"Runtime bridge executed ticket {execution_package.ticket_id} for "
            f"{execution_package.role_profile_ref}."
        ),
        artifact_refs=[],
        result_payload={
            "bridge_contract_version": execution_package.bridge_contract_version,
            "role_profile_ref": execution_package.role_profile_ref,
            "output_schema_ref": execution_package.output_schema_ref,
            "input_artifact_count": len(execution_package.input_artifact_refs),
        },
    )


def _build_runtime_failure(
    *,
    ticket: dict[str, Any],
    failed_by: str,
    failure_kind: str,
    failure_message: str,
    failure_detail: dict[str, Any] | None,
) -> TicketFailCommand:
    return TicketFailCommand(
        workflow_id=ticket["workflow_id"],
        ticket_id=ticket["ticket_id"],
        node_id=ticket["node_id"],
        failed_by=failed_by,
        failure_kind=failure_kind,
        failure_message=failure_message,
        failure_detail=failure_detail,
        idempotency_key=_build_fail_idempotency_key(ticket, failure_kind),
    )


def run_leased_ticket_runtime(
    repository: ControlPlaneRepository,
) -> list[RuntimeExecutionOutcome]:
    outcomes: list[RuntimeExecutionOutcome] = []

    for ticket in _list_runtime_startable_leased_tickets(repository):
        lease_owner = str(ticket["lease_owner"])
        start_ack = handle_ticket_start(
            repository,
            TicketStartCommand(
                workflow_id=ticket["workflow_id"],
                ticket_id=ticket["ticket_id"],
                node_id=ticket["node_id"],
                started_by=lease_owner,
                idempotency_key=_build_start_idempotency_key(ticket),
            ),
        )

        if start_ack.status != CommandAckStatus.ACCEPTED:
            outcomes.append(
                RuntimeExecutionOutcome(
                    ticket_id=ticket["ticket_id"],
                    lease_owner=lease_owner,
                    start_ack=start_ack,
                    final_ack=None,
                )
            )
            continue

        try:
            execution_package = _build_runtime_bridge_execution_package(repository, ticket)
            execution_result = _execute_runtime_bridge_package(execution_package)
        except ValueError as exc:
            final_ack = handle_ticket_fail(
                repository,
                _build_runtime_failure(
                    ticket=ticket,
                    failed_by=lease_owner,
                    failure_kind="RUNTIME_INPUT_ERROR",
                    failure_message=str(exc),
                    failure_detail={
                        "bridge_contract_version": "runtime-bridge.v1",
                    },
                ),
            )
            outcomes.append(
                RuntimeExecutionOutcome(
                    ticket_id=ticket["ticket_id"],
                    lease_owner=lease_owner,
                    start_ack=start_ack,
                    final_ack=final_ack,
                )
            )
            continue

        if execution_result.result_status == "completed":
            final_ack = handle_ticket_completed(
                repository,
                TicketCompletedCommand(
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    completed_by=lease_owner,
                    completion_summary=execution_result.completion_summary or "Runtime completed ticket.",
                    artifact_refs=execution_result.artifact_refs,
                    review_request=None,
                    idempotency_key=_build_complete_idempotency_key(ticket),
                ),
            )
        else:
            final_ack = handle_ticket_fail(
                repository,
                _build_runtime_failure(
                    ticket=ticket,
                    failed_by=lease_owner,
                    failure_kind=execution_result.failure_kind or "RUNTIME_ERROR",
                    failure_message=execution_result.failure_message or "Runtime bridge executor failed.",
                    failure_detail=execution_result.failure_detail,
                ),
            )

        outcomes.append(
            RuntimeExecutionOutcome(
                ticket_id=ticket["ticket_id"],
                lease_owner=lease_owner,
                start_ack=start_ack,
                final_ack=final_ack,
            )
        )

    return outcomes
