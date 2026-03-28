from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.contracts.common import StrictModel
from app.contracts.commands import TicketEscalationPolicy


class CompileRequestMeta(StrictModel):
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)


class CompileRequestControlRefs(StrictModel):
    role_profile_ref: str = Field(min_length=1)
    constraints_ref: str = Field(min_length=1)
    output_schema_ref: str = Field(min_length=1)
    output_schema_version: int = Field(ge=1)


class CompileRequestWorkerBinding(StrictModel):
    lease_owner: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    employee_role_type: str = Field(min_length=1)
    skill_profile: dict[str, Any] = Field(default_factory=dict)
    personality_profile: dict[str, Any] = Field(default_factory=dict)
    aesthetic_profile: dict[str, Any] = Field(default_factory=dict)


class CompileRequestBudgetPolicy(StrictModel):
    max_input_tokens: int = Field(ge=1)
    overflow_policy: Literal["FAIL_CLOSED"]


class CompileRequestExplicitSource(StrictModel):
    source_ref: str = Field(min_length=1)
    source_kind: Literal["ARTIFACT"]
    is_mandatory: bool = True


class CompileRequestExecution(StrictModel):
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_write_set: list[str] = Field(default_factory=list)


class CompileRequestGovernance(StrictModel):
    retry_budget: int = Field(ge=0)
    timeout_sla_sec: int = Field(ge=1)
    escalation_policy: TicketEscalationPolicy


class CompileRequest(StrictModel):
    meta: CompileRequestMeta
    control_refs: CompileRequestControlRefs
    worker_binding: CompileRequestWorkerBinding
    budget_policy: CompileRequestBudgetPolicy
    explicit_sources: list[CompileRequestExplicitSource]
    execution: CompileRequestExecution
    governance: CompileRequestGovernance


class CompiledExecutionPackageMeta(StrictModel):
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)
    lease_owner: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)


class CompiledRole(StrictModel):
    role_profile_ref: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    employee_role_type: str = Field(min_length=1)
    skill_profile: dict[str, Any] = Field(default_factory=dict)
    personality_profile: dict[str, Any] = Field(default_factory=dict)
    aesthetic_profile: dict[str, Any] = Field(default_factory=dict)


class CompiledConstraints(StrictModel):
    constraints_ref: str = Field(min_length=1)
    global_rules: list[str] = Field(default_factory=list)
    board_constraints: list[str] = Field(default_factory=list)
    budget_constraints: dict[str, Any] = Field(default_factory=dict)


class AtomicContextBlock(StrictModel):
    block_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_kind: Literal["ARTIFACT"]
    content_type: Literal["SOURCE_DESCRIPTOR"]
    content_payload: dict[str, Any] = Field(default_factory=dict)


class AtomicContextBundle(StrictModel):
    context_blocks: list[AtomicContextBlock] = Field(default_factory=list)
    token_budget: int = Field(ge=1)


class CompiledExecution(StrictModel):
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_write_set: list[str] = Field(default_factory=list)
    output_schema_ref: str = Field(min_length=1)
    output_schema_version: int = Field(ge=1)


class CompiledGovernance(StrictModel):
    retry_budget: int = Field(ge=0)
    timeout_sla_sec: int = Field(ge=1)
    escalation_policy: TicketEscalationPolicy


class CompiledExecutionPackage(StrictModel):
    meta: CompiledExecutionPackageMeta
    compiled_role: CompiledRole
    compiled_constraints: CompiledConstraints
    atomic_context_bundle: AtomicContextBundle
    execution: CompiledExecution
    governance: CompiledGovernance
