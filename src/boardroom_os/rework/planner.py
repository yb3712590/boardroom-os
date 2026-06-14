from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.rework.model import (
    BlockerReport,
    BlockerRef,
    ReworkActorKind,
    ReworkDecisionKind,
    ReworkPlan,
    ReworkRequest,
    TicketGraphPatch,
)
from boardroom_os.rework.ticket_graph_patch import (
    TicketGraphPatchBoundaryError,
    validate_ticket_graph_patch_scope,
)

CEO_BASELINE_HOOK_REF = RolePromptHookRef(value="role-prompt-hook.baseline.ceo.v1")
_ALLOWED_DECISIONS = {
    ReworkDecisionKind.FIX_IMPLEMENTATION,
    ReworkDecisionKind.FIX_CONTRACT_OR_PROBE,
    ReworkDecisionKind.SPLIT_TICKET,
    ReworkDecisionKind.REORDER_DEPENDENCIES,
    ReworkDecisionKind.ESCALATE_HUMAN_REVIEW,
}


class CeoReworkPlannerError(ValueError):
    pass


class CeoReworkPlannerInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rework_request: ReworkRequest
    blocker_reports: tuple[BlockerReport, ...] = ()
    current_graph_version: int = Field(gt=0)
    active_contract_refs: tuple[ContractId, ...]
    active_acceptance_refs: tuple[AcceptanceRef, ...]
    active_source_surface_refs: tuple[SourceSurfaceRef, ...]
    active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    package_contract_ref: ContractId
    run_manifest_ref: str
    planner_execution_package_ref: ExecutionPackageRef
    planner_role_prompt_hook_ref: RolePromptHookRef

    @field_validator(
        "active_contract_refs",
        "active_acceptance_refs",
        "active_source_surface_refs",
        "active_evidence_obligation_refs",
    )
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        raw = [getattr(value, "value", str(value)) for value in values]
        if len(raw) != len(set(raw)):
            raise ValueError(f"{info.field_name} must be unique")
        return values

    @field_validator("run_manifest_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("run_manifest_ref must not be empty")
        return normalized


class CeoPlannerParsedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: ReworkPlan
    patch: TicketGraphPatch


class CeoReworkPlannerOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    planner_input: CeoReworkPlannerInput
    provider_attempt: ProviderAttempt | None
    plan: ReworkPlan
    patch: TicketGraphPatch
    parsed_payload_ref: ProviderArtifactRef
    validated_at: datetime

    @field_validator("validated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validated_at must be timezone-aware")
        return value


def parse_ceo_rework_planner_payload(payload: Mapping[str, object]) -> CeoPlannerParsedPayload:
    if set(payload) != {"plan", "patch"}:
        raise CeoReworkPlannerError("CEO planner output must be a single JSON object with plan and patch")
    try:
        return CeoPlannerParsedPayload(
            plan=ReworkPlan.model_validate(payload["plan"]),
            patch=TicketGraphPatch.model_validate(payload["patch"]),
        )
    except Exception as exc:
        raise CeoReworkPlannerError("CEO planner output must be a single JSON object with plan and patch") from exc


def _request_blocker_refs(request: ReworkRequest) -> set[BlockerRef]:
    return {blocker_ref for issue in request.issues for blocker_ref in issue.blocker_refs}


def _unsafe_runtime_instruction(text: str) -> bool:
    normalized = text.lower()
    return "runtime" in normalized and ("auto" in normalized or "automatically" in normalized or "just fix" in normalized)


class CeoReworkPlannerBoundary:
    @staticmethod
    def validate(output: CeoReworkPlannerOutput) -> CeoReworkPlannerOutput:
        _validate_provider_attempt(output)
        _validate_request_plan_patch_binding(output)
        _validate_decisions(output)
        try:
            validate_ticket_graph_patch_scope(
                output.patch,
                active_acceptance_refs=output.planner_input.active_acceptance_refs,
                active_source_surface_refs=output.planner_input.active_source_surface_refs,
                active_evidence_obligation_refs=output.planner_input.active_evidence_obligation_refs,
                active_contract_refs=output.planner_input.active_contract_refs,
            )
        except TicketGraphPatchBoundaryError as exc:
            raise CeoReworkPlannerError(str(exc)) from exc
        return output


def validate_ceo_rework_plan(output: CeoReworkPlannerOutput) -> CeoReworkPlannerOutput:
    return CeoReworkPlannerBoundary.validate(output)


def _validate_provider_attempt(output: CeoReworkPlannerOutput) -> None:
    attempt = output.provider_attempt
    if attempt is None:
        raise CeoReworkPlannerError("provider_attempt is required")
    if attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise CeoReworkPlannerError("provider_attempt must be succeeded")
    if attempt.outcome is not ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT:
        raise CeoReworkPlannerError("provider_attempt must be primary provider output")
    if attempt.provider_attempt_id != output.plan.planner_attempt_ref:
        raise CeoReworkPlannerError("provider_attempt_id must match planner_attempt_ref")
    if attempt.input_package_ref != output.planner_input.planner_execution_package_ref:
        raise CeoReworkPlannerError("provider input package must match planner execution package")
    if attempt.role_prompt_hook_ref != output.planner_input.planner_role_prompt_hook_ref:
        raise CeoReworkPlannerError("provider attempt must use CEO role prompt hook")
    if output.planner_input.planner_role_prompt_hook_ref != CEO_BASELINE_HOOK_REF:
        raise CeoReworkPlannerError("planner input must use active CEO role prompt hook")
    if attempt.role_prompt_hook_ref != CEO_BASELINE_HOOK_REF:
        raise CeoReworkPlannerError("provider attempt must use CEO role prompt hook")
    if output.plan.planner_actor is not ReworkActorKind.CEO:
        raise CeoReworkPlannerError("planner_actor must be CEO")


def _validate_request_plan_patch_binding(output: CeoReworkPlannerOutput) -> None:
    planner_input = output.planner_input
    request = planner_input.rework_request
    plan = output.plan
    patch = output.patch
    if plan.rework_request_id != request.rework_request_id:
        raise CeoReworkPlannerError("plan rework_request_id mismatch")
    if plan.cycle_id != request.cycle_id:
        raise CeoReworkPlannerError("plan cycle_id mismatch")
    if patch.proposed_by_plan_ref != plan.rework_plan_id:
        raise CeoReworkPlannerError("patch proposed_by_plan_ref mismatch")
    if patch.ticket_graph_patch_id != plan.ticket_graph_patch_ref:
        raise CeoReworkPlannerError("patch ticket_graph_patch_id mismatch")
    if patch.base_graph_version != request.active_graph_version:
        raise CeoReworkPlannerError("patch base_graph_version mismatch")
    if planner_input.current_graph_version != request.active_graph_version:
        raise CeoReworkPlannerError("current_graph_version mismatch")
    if planner_input.active_contract_refs != request.active_contract_refs:
        raise CeoReworkPlannerError("active_contract_refs mismatch")


def _validate_decisions(output: CeoReworkPlannerOutput) -> None:
    request_blockers = _request_blocker_refs(output.planner_input.rework_request)
    planned_blockers: set[BlockerRef] = set()
    operation_refs = {operation.operation_id for operation in output.patch.operations}
    for decision in output.plan.decisions:
        if decision.decision_kind is ReworkDecisionKind.NARROW_SCOPE:
            raise CeoReworkPlannerError("decision kind is not allowed for V2-100C")
        if decision.decision_kind not in _ALLOWED_DECISIONS:
            raise CeoReworkPlannerError("decision kind is not allowed for V2-100C")
        if decision.decision_kind is not ReworkDecisionKind.ESCALATE_HUMAN_REVIEW:
            if not decision.target_ticket_refs and not decision.target_graph_operation_refs:
                raise CeoReworkPlannerError("non-escalation decision requires target refs")
            if not any(ref in operation_refs for ref in decision.target_graph_operation_refs):
                raise CeoReworkPlannerError("non-escalation decision must map to a graph patch operation")
        planned_blockers.update(decision.blocker_refs)
        if _unsafe_runtime_instruction(decision.rationale):
            raise CeoReworkPlannerError("runtime auto-repair instructions are not allowed")
    missing = request_blockers - planned_blockers
    if missing:
        names = ", ".join(sorted(blocker.value for blocker in missing))
        raise CeoReworkPlannerError(f"missing blocker mapping: {names}")


__all__ = [
    "CeoPlannerParsedPayload",
    "CeoReworkPlannerBoundary",
    "CeoReworkPlannerError",
    "CeoReworkPlannerInput",
    "CeoReworkPlannerOutput",
    "parse_ceo_rework_planner_payload",
    "validate_ceo_rework_plan",
]
