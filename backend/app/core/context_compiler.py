from __future__ import annotations

from typing import Any

from app.contracts.commands import TicketEscalationPolicy
from app.contracts.runtime import (
    AtomicContextBlock,
    AtomicContextBundle,
    CompileRequest,
    CompileRequestBudgetPolicy,
    CompileRequestControlRefs,
    CompileRequestExecution,
    CompileRequestExplicitSource,
    CompileRequestGovernance,
    CompileRequestMeta,
    CompileRequestWorkerBinding,
    CompiledConstraints,
    CompiledExecution,
    CompiledExecutionPackage,
    CompiledExecutionPackageMeta,
    CompiledGovernance,
    CompiledRole,
)
from app.core.ids import new_prefixed_id
from app.db.repository import ControlPlaneRepository

MINIMAL_CONTEXT_COMPILER_VERSION = "context-compiler.min.v1"


def _require_ticket_create_spec(
    repository: ControlPlaneRepository,
    ticket_id: str,
) -> dict[str, Any]:
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
    if created_spec is None:
        raise ValueError("Ticket create spec is missing for runtime compilation.")
    return created_spec


def _require_worker_binding(
    repository: ControlPlaneRepository,
    lease_owner: str | None,
) -> tuple[str, dict[str, Any]]:
    if lease_owner is None:
        raise ValueError("Ticket lease owner is missing for runtime compilation.")

    employee = repository.get_employee_projection(lease_owner)
    if employee is None:
        raise ValueError(f"Employee {lease_owner} is missing from employee_projection.")

    return lease_owner, employee


def build_compile_request(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
) -> CompileRequest:
    created_spec = _require_ticket_create_spec(repository, ticket["ticket_id"])
    lease_owner, employee = _require_worker_binding(repository, ticket.get("lease_owner"))

    context_query_plan = dict(created_spec.get("context_query_plan") or {})
    max_input_tokens = int(context_query_plan.get("max_context_tokens") or 0)
    if max_input_tokens <= 0:
        raise ValueError("Ticket context_query_plan.max_context_tokens is missing for runtime compilation.")

    attempt_no = int(created_spec.get("attempt_no") or 0)
    if attempt_no <= 0:
        raise ValueError("Ticket attempt_no is missing for runtime compilation.")

    return CompileRequest(
        meta=CompileRequestMeta(
            compile_request_id=new_prefixed_id("creq"),
            ticket_id=ticket["ticket_id"],
            workflow_id=ticket["workflow_id"],
            node_id=ticket["node_id"],
            attempt_no=attempt_no,
        ),
        control_refs=CompileRequestControlRefs(
            role_profile_ref=str(created_spec.get("role_profile_ref") or ""),
            constraints_ref=str(created_spec.get("constraints_ref") or ""),
            output_schema_ref=str(created_spec.get("output_schema_ref") or ""),
            output_schema_version=int(created_spec.get("output_schema_version") or 0),
        ),
        worker_binding=CompileRequestWorkerBinding(
            lease_owner=lease_owner,
            employee_id=lease_owner,
            employee_role_type=str(employee.get("role_type") or "unknown"),
            skill_profile=dict(employee.get("skill_profile_json") or {}),
            personality_profile=dict(employee.get("personality_profile_json") or {}),
            aesthetic_profile=dict(employee.get("aesthetic_profile_json") or {}),
        ),
        budget_policy=CompileRequestBudgetPolicy(
            max_input_tokens=max_input_tokens,
            overflow_policy="FAIL_CLOSED",
        ),
        explicit_sources=[
            CompileRequestExplicitSource(
                source_ref=str(source_ref),
                source_kind="ARTIFACT",
                is_mandatory=True,
            )
            for source_ref in list(created_spec.get("input_artifact_refs") or [])
        ],
        execution=CompileRequestExecution(
            acceptance_criteria=list(created_spec.get("acceptance_criteria") or []),
            allowed_tools=list(created_spec.get("allowed_tools") or []),
            allowed_write_set=list(created_spec.get("allowed_write_set") or []),
        ),
        governance=CompileRequestGovernance(
            retry_budget=int(created_spec.get("retry_budget") or 0),
            timeout_sla_sec=int(created_spec.get("timeout_sla_sec") or 0),
            escalation_policy=TicketEscalationPolicy.model_validate(
                created_spec.get("escalation_policy") or {}
            ),
        ),
    )


def compile_execution_package(
    compile_request: CompileRequest,
) -> CompiledExecutionPackage:
    context_blocks = [
        AtomicContextBlock(
            block_id=new_prefixed_id("ctxblk"),
            source_ref=source.source_ref,
            source_kind=source.source_kind,
            content_type="SOURCE_DESCRIPTOR",
            content_payload={
                "source_ref": source.source_ref,
                "source_kind": source.source_kind,
                "is_mandatory": source.is_mandatory,
            },
        )
        for source in compile_request.explicit_sources
    ]

    return CompiledExecutionPackage(
        meta=CompiledExecutionPackageMeta(
            compile_request_id=compile_request.meta.compile_request_id,
            ticket_id=compile_request.meta.ticket_id,
            workflow_id=compile_request.meta.workflow_id,
            node_id=compile_request.meta.node_id,
            attempt_no=compile_request.meta.attempt_no,
            lease_owner=compile_request.worker_binding.lease_owner,
            compiler_version=MINIMAL_CONTEXT_COMPILER_VERSION,
        ),
        compiled_role=CompiledRole(
            role_profile_ref=compile_request.control_refs.role_profile_ref,
            employee_id=compile_request.worker_binding.employee_id,
            employee_role_type=compile_request.worker_binding.employee_role_type,
            skill_profile=compile_request.worker_binding.skill_profile,
            personality_profile=compile_request.worker_binding.personality_profile,
            aesthetic_profile=compile_request.worker_binding.aesthetic_profile,
        ),
        compiled_constraints=CompiledConstraints(
            constraints_ref=compile_request.control_refs.constraints_ref,
            global_rules=[],
            board_constraints=[],
            budget_constraints={},
        ),
        atomic_context_bundle=AtomicContextBundle(
            context_blocks=context_blocks,
            token_budget=compile_request.budget_policy.max_input_tokens,
        ),
        execution=CompiledExecution(
            acceptance_criteria=compile_request.execution.acceptance_criteria,
            allowed_tools=compile_request.execution.allowed_tools,
            allowed_write_set=compile_request.execution.allowed_write_set,
            output_schema_ref=compile_request.control_refs.output_schema_ref,
            output_schema_version=compile_request.control_refs.output_schema_version,
        ),
        governance=CompiledGovernance(
            retry_budget=compile_request.governance.retry_budget,
            timeout_sla_sec=compile_request.governance.timeout_sla_sec,
            escalation_policy=compile_request.governance.escalation_policy,
        ),
    )
