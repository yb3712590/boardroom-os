from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import ModelExecutionProfile, ModelExecutionProfileRegistry, RoleProfile
from boardroom_os.agents.role_prompt_hooks import RolePromptHookRegistry
from boardroom_os.agents.seat import AgentSeat, seat_demand_blockers
from boardroom_os.agents.team import AgentTeamProjection
from boardroom_os.contracts.acceptance import AcceptanceContract, AcceptanceCriterion
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.package import PackageCommand, PackageContract
from boardroom_os.contracts.source_surface import SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.graph.seat_assignment import SeatAssignmentGraph
from boardroom_os.graph.ticket import (
    VERIFY_BLACKBOX_CAPABILITY,
    VERIFY_BLACKBOX_PURPOSE,
    TicketId,
    TicketNode,
    TicketStatus,
)

_DRIVE_LETTER_PATTERN = re.compile(r"^[A-Za-z]:")
_FIXED_AUDIT_REQUIREMENTS = (
    AuditRequirement(value="record.received_execution_package"),
    AuditRequirement(value="preserve.model_execution_profile_snapshot"),
    AuditRequirement(value="preserve.allowed_write_set"),
    AuditRequirement(value="preserve.evidence_obligation_refs"),
    AuditRequirement(value="preserve.agent_team_projection_graph_version"),
)
_FIXED_CONSTRAINTS = (
    "Only write paths listed in allowed_write_set.",
    "Do not modify active contracts or governance state.",
    "Do not create or alter evidence outside declared evidence_obligations.",
)


class ExecutionPackageCompilerError(ValueError):
    pass


class ExecutionWorkspaceContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_ref: ContextRef
    package_root: str
    context_refs: tuple[ContextRef, ...] = ()

    @field_validator("package_root")
    @classmethod
    def _validate_package_root(cls, value: str) -> str:
        return _normalize_relative_path(value, field_name="package_root")


class VerificationExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_manifest_context_ref: ContextRef | None
    skeleton_summary_ref: ContextRef
    package_contract_ref: ContextRef
    acceptance_contract_ref: ContextRef
    project_doc_refs: tuple[ContextRef, ...] = ()
    source_surface_refs: tuple[ContextRef, ...]
    observed_failure_refs: tuple[ContextRef, ...] = ()

    @field_validator("source_surface_refs")
    @classmethod
    def _reject_empty_source_surface_refs(
        cls,
        values: tuple[ContextRef, ...],
    ) -> tuple[ContextRef, ...]:
        if not values:
            raise ValueError("source_surface_refs must not be empty")
        return values


class ExecutionPackageCompilerInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: TicketId
    seat_assignment_graph: SeatAssignmentGraph
    agent_team_projection: AgentTeamProjection
    acceptance_contract: AcceptanceContract
    package_contract: PackageContract
    evidence_obligations: tuple[EvidenceObligation, ...]
    model_execution_profiles: ModelExecutionProfileRegistry
    role_prompt_hook_registry: RolePromptHookRegistry
    workspace_context: ExecutionWorkspaceContext
    verification_context: VerificationExecutionContext | None = None


class ExecutionPackageCompiler:
    def compile(self, input: ExecutionPackageCompilerInput) -> ExecutionPackage:
        ticket = self._resolve_ticket(input)
        _validate_verify_blackbox_ticket(ticket)
        self._validate_graph_version(input)
        assigned_seat = self._resolve_assigned_seat(input, ticket)
        role_profile = self._resolve_role_profile(input, assigned_seat)
        role_prompt_hook = self._resolve_role_prompt_hook(input, role_profile)
        model_execution_profile = self._resolve_model_execution_profile(input, assigned_seat)
        self._validate_active_acceptance_contract(input.acceptance_contract)
        self._validate_package_root(input)

        acceptance_refs, selected_criteria = self._resolve_acceptance_criteria(
            ticket=ticket,
            acceptance_contract=input.acceptance_contract,
        )
        source_surface_refs, selected_surfaces = self._resolve_source_surfaces(
            ticket=ticket,
            package_contract=input.package_contract,
        )
        self._validate_surface_acceptance_coverage(
            acceptance_refs=acceptance_refs,
            source_surfaces=selected_surfaces,
        )
        self._validate_criterion_source_surface_scope(
            criteria=selected_criteria,
            source_surface_refs=source_surface_refs,
        )

        allowed_write_set = self._resolve_allowed_write_set(
            ticket=ticket,
            source_surfaces=selected_surfaces,
        )
        evidence_obligations = self._resolve_evidence_obligations(
            ticket=ticket,
            evidence_obligations=input.evidence_obligations,
            acceptance_refs=acceptance_refs,
            source_surface_refs=source_surface_refs,
            selected_criteria=selected_criteria,
        )
        commands = self._resolve_required_commands(
            package_contract=input.package_contract,
            source_surfaces=selected_surfaces,
        )
        context_refs = self._build_context_refs(input, ticket)
        self._validate_read_only_context_refs(ticket=ticket, context_refs=context_refs)

        return ExecutionPackage(
            execution_package_id=ExecutionPackageId(
                value=f"exec.{ticket.ticket_id.value}.graph-{input.seat_assignment_graph.graph_version}"
            ),
            ticket_ref=ticket.ticket_id,
            graph_version=input.seat_assignment_graph.graph_version,
            seat_ref=assigned_seat.seat_ref,
            model_execution_profile=model_execution_profile,
            role_prompt_hook=role_prompt_hook,
            objective=ticket.purpose,
            context_refs=context_refs,
            constraints=self._build_constraints(role_profile),
            acceptance_refs=acceptance_refs,
            source_surface_refs=source_surface_refs,
            allowed_read_refs=tuple(
                AllowedReadRef(value=allowed_read_ref)
                for allowed_read_ref in ticket.allowed_read_refs
            ),
            allowed_write_set=allowed_write_set,
            required_outputs=self._build_required_outputs(
                source_surface_refs=source_surface_refs,
                evidence_obligations=evidence_obligations,
            ),
            commands=commands,
            evidence_obligations=evidence_obligations,
            fallback_policy_ref=FallbackPolicyRef(
                value=model_execution_profile.fallback_policy_ref.value
            ),
            audit_requirements=_FIXED_AUDIT_REQUIREMENTS,
        )

    def _resolve_ticket(self, input: ExecutionPackageCompilerInput) -> TicketNode:
        ticket = input.seat_assignment_graph.nodes.get(input.ticket_ref)
        if ticket is None:
            raise ExecutionPackageCompilerError(
                f"ticket_ref does not exist in seat_assignment_graph: {input.ticket_ref.value}"
            )
        if ticket.status is not TicketStatus.READY:
            raise ExecutionPackageCompilerError(
                f"ticket status must be ready: {ticket.ticket_id.value}"
            )
        if ticket.ticket_id not in input.seat_assignment_graph.ready_queue:
            raise ExecutionPackageCompilerError(
                f"ticket must be present in ready_queue: {ticket.ticket_id.value}"
            )
        return ticket

    def _validate_graph_version(self, input: ExecutionPackageCompilerInput) -> None:
        if input.seat_assignment_graph.graph_version != input.agent_team_projection.graph_version:
            raise ExecutionPackageCompilerError(
                "SeatAssignmentGraph graph_version must match AgentTeamProjection graph_version"
            )

    def _resolve_assigned_seat(
        self,
        input: ExecutionPackageCompilerInput,
        ticket: TicketNode,
    ) -> AgentSeat:
        seat_ref = input.seat_assignment_graph.seat_assignments.get(ticket.ticket_id)
        if seat_ref is None:
            raise ExecutionPackageCompilerError(
                f"missing seat assignment for ticket: {ticket.ticket_id.value}"
            )

        seat = input.agent_team_projection.seat_lifecycle.active_seats.get(seat_ref)
        if seat is None:
            raise ExecutionPackageCompilerError(
                f"assigned seat must resolve to an active seat: {seat_ref.value}"
            )

        blockers = seat_demand_blockers(seat=seat, demand=ticket.seat_demand)
        if blockers:
            raise ExecutionPackageCompilerError("; ".join(blockers))
        return seat

    def _resolve_role_profile(
        self,
        input: ExecutionPackageCompilerInput,
        seat: AgentSeat,
    ) -> RoleProfile:
        for role_profile in input.agent_team_projection.role_profiles.profiles:
            if role_profile.role_profile_id == seat.role_profile_ref:
                return role_profile
        raise ExecutionPackageCompilerError(
            f"unknown role_profile_ref: {seat.role_profile_ref.value}"
        )

    def _resolve_role_prompt_hook(
        self,
        input: ExecutionPackageCompilerInput,
        role_profile: RoleProfile,
    ):
        try:
            hook = input.role_prompt_hook_registry.require(
                role_profile.role_prompt_hook_ref
            )
        except Exception as error:
            raise ExecutionPackageCompilerError(
                "role prompt hook registry could not resolve profile hook: "
                f"{role_profile.role_prompt_hook_ref.value}"
            ) from error
        if hook.hook_version != role_profile.role_prompt_hook_version:
            raise ExecutionPackageCompilerError("role prompt hook version mismatch")
        if hook.content_sha256 != role_profile.role_prompt_hook_sha256:
            raise ExecutionPackageCompilerError("role prompt hook hash mismatch")
        if hook.role_category is not role_profile.role_category:
            raise ExecutionPackageCompilerError("role prompt hook category mismatch")
        return hook

    def _resolve_model_execution_profile(
        self,
        input: ExecutionPackageCompilerInput,
        seat: AgentSeat,
    ) -> ModelExecutionProfile:
        for model_execution_profile in input.model_execution_profiles.profiles:
            if model_execution_profile.model_execution_profile_id == seat.model_execution_profile_ref:
                return model_execution_profile
        raise ExecutionPackageCompilerError(
            "unknown model_execution_profile_ref: "
            f"{seat.model_execution_profile_ref.value}"
        )

    def _validate_active_acceptance_contract(
        self,
        acceptance_contract: AcceptanceContract,
    ) -> None:
        if acceptance_contract.status.value != "active":
            raise ExecutionPackageCompilerError("active acceptance contract is required")

    def _validate_package_root(self, input: ExecutionPackageCompilerInput) -> None:
        package_contract_root = _normalize_relative_path(
            input.package_contract.package_root,
            field_name="package_contract.package_root",
        )
        if input.workspace_context.package_root != package_contract_root:
            raise ExecutionPackageCompilerError(
                "workspace_context package_root must match package_contract package_root"
            )

    def _resolve_acceptance_criteria(
        self,
        *,
        ticket: TicketNode,
        acceptance_contract: AcceptanceContract,
    ) -> tuple[tuple[AcceptanceRef, ...], tuple[AcceptanceCriterion, ...]]:
        criteria_by_ref = {
            criterion.acceptance_ref.value: criterion
            for criterion in acceptance_contract.criteria
        }
        acceptance_refs = tuple(AcceptanceRef(value=value) for value in ticket.acceptance_refs)
        criteria: list[AcceptanceCriterion] = []
        for acceptance_ref in acceptance_refs:
            criterion = criteria_by_ref.get(acceptance_ref.value)
            if criterion is None:
                raise ExecutionPackageCompilerError(
                    f"acceptance_ref is outside active contract: {acceptance_ref.value}"
                )
            criteria.append(criterion)
        return acceptance_refs, tuple(criteria)

    def _resolve_source_surfaces(
        self,
        *,
        ticket: TicketNode,
        package_contract: PackageContract,
    ) -> tuple[tuple[SourceSurfaceRef, ...], tuple[SourceSurface, ...]]:
        source_surfaces_by_ref = {
            source_surface.source_surface_ref.value: source_surface
            for source_surface in package_contract.source_surfaces
        }
        source_surface_refs = tuple(SourceSurfaceRef(value=value) for value in ticket.source_surface_refs)
        source_surfaces: list[SourceSurface] = []
        for source_surface_ref in source_surface_refs:
            source_surface = source_surfaces_by_ref.get(source_surface_ref.value)
            if source_surface is None:
                raise ExecutionPackageCompilerError(
                    f"unknown source_surface_ref: {source_surface_ref.value}"
                )
            source_surfaces.append(source_surface)
        return source_surface_refs, tuple(source_surfaces)

    def _validate_surface_acceptance_coverage(
        self,
        *,
        acceptance_refs: tuple[AcceptanceRef, ...],
        source_surfaces: tuple[SourceSurface, ...],
    ) -> None:
        covered_acceptance_refs = {
            acceptance_ref.value
            for source_surface in source_surfaces
            for acceptance_ref in source_surface.acceptance_refs
        }
        missing_acceptance_refs = [
            acceptance_ref.value
            for acceptance_ref in acceptance_refs
            if acceptance_ref.value not in covered_acceptance_refs
        ]
        if missing_acceptance_refs:
            raise ExecutionPackageCompilerError(
                "selected source surfaces does not cover ticket acceptance refs: "
                + ", ".join(missing_acceptance_refs)
            )

    def _validate_criterion_source_surface_scope(
        self,
        *,
        criteria: tuple[AcceptanceCriterion, ...],
        source_surface_refs: tuple[SourceSurfaceRef, ...],
    ) -> None:
        declared_refs = {source_surface_ref.value for source_surface_ref in source_surface_refs}
        for criterion in criteria:
            for source_surface_ref in criterion.source_surface_refs:
                if source_surface_ref.value not in declared_refs:
                    raise ExecutionPackageCompilerError(
                        "ticket source_surface_refs must include all acceptance criterion "
                        f"source_surface_refs: {source_surface_ref.value}"
                    )

    def _resolve_allowed_write_set(
        self,
        *,
        ticket: TicketNode,
        source_surfaces: tuple[SourceSurface, ...],
    ) -> tuple[AllowedWritePath, ...]:
        if _is_verify_blackbox_ticket(ticket):
            _validate_verify_blackbox_ticket(ticket)
            if ticket.allowed_write_set:
                raise ExecutionPackageCompilerError(
                    "verify-blackbox ticket allowed_write_set must be empty"
                )
            return ()
        if not ticket.allowed_write_set:
            raise ExecutionPackageCompilerError(
                "allowed_write_set is required for writable tickets"
            )
        declared_surface_paths = tuple(
            _normalize_relative_path(surface_path, field_name="source surface path")
            for source_surface in source_surfaces
            for surface_path in source_surface.paths
        )

        allowed_write_paths: list[AllowedWritePath] = []
        for raw_path in ticket.allowed_write_set:
            normalized_path = _normalize_relative_path(raw_path, field_name="unsafe write path")
            if not any(
                _path_within_surface(normalized_path, surface_path)
                for surface_path in declared_surface_paths
            ):
                raise ExecutionPackageCompilerError(
                    f"allowed_write_set path must stay within referenced source surfaces: {normalized_path}"
                )
            allowed_write_paths.append(AllowedWritePath(value=normalized_path))
        return tuple(allowed_write_paths)

    def _resolve_evidence_obligations(
        self,
        *,
        ticket: TicketNode,
        evidence_obligations: tuple[EvidenceObligation, ...],
        acceptance_refs: tuple[AcceptanceRef, ...],
        source_surface_refs: tuple[SourceSurfaceRef, ...],
        selected_criteria: tuple[AcceptanceCriterion, ...],
    ) -> tuple[EvidenceObligation, ...]:
        obligations_by_ref = {
            evidence_obligation.evidence_obligation_id.value: evidence_obligation
            for evidence_obligation in evidence_obligations
        }
        acceptance_ref_values = {acceptance_ref.value for acceptance_ref in acceptance_refs}
        source_surface_ref_values = {source_surface_ref.value for source_surface_ref in source_surface_refs}

        resolved_obligations: list[EvidenceObligation] = []
        seen_obligation_refs: set[str] = set()
        for evidence_obligation_ref_value in ticket.evidence_obligations:
            evidence_obligation_ref = EvidenceObligationRef(value=evidence_obligation_ref_value)
            if evidence_obligation_ref.value in seen_obligation_refs:
                raise ExecutionPackageCompilerError(
                    f"duplicate evidence obligation ref: {evidence_obligation_ref.value}"
                )
            seen_obligation_refs.add(evidence_obligation_ref.value)
            evidence_obligation = obligations_by_ref.get(evidence_obligation_ref.value)
            if evidence_obligation is None:
                raise ExecutionPackageCompilerError(
                    f"missing evidence obligation: {evidence_obligation_ref.value}"
                )
            if not {
                acceptance_ref.value for acceptance_ref in evidence_obligation.acceptance_refs
            }.issubset(acceptance_ref_values):
                raise ExecutionPackageCompilerError(
                    "evidence obligation acceptance scope must be a subset of ticket acceptance refs"
                )
            if not {
                source_surface_ref.value
                for source_surface_ref in evidence_obligation.source_surface_refs
            }.issubset(source_surface_ref_values):
                raise ExecutionPackageCompilerError(
                    "evidence obligation source surface scope must be a subset of ticket source surface refs"
                )
            resolved_obligations.append(evidence_obligation)

        self._validate_evidence_required_coverage(
            selected_criteria=selected_criteria,
            evidence_obligations=tuple(resolved_obligations),
        )
        return tuple(resolved_obligations)

    def _validate_evidence_required_coverage(
        self,
        *,
        selected_criteria: tuple[AcceptanceCriterion, ...],
        evidence_obligations: tuple[EvidenceObligation, ...],
    ) -> None:
        for criterion in selected_criteria:
            for evidence_requirement in criterion.evidence_required:
                matching_obligations = tuple(
                    evidence_obligation
                    for evidence_obligation in evidence_obligations
                    if evidence_obligation.required_artifact_type.value == evidence_requirement.value
                    and criterion.acceptance_ref
                    in evidence_obligation.acceptance_refs
                )
                if not matching_obligations:
                    raise ExecutionPackageCompilerError(
                        "evidence_required must be covered by evidence obligation "
                        f"required_artifact_type: {criterion.acceptance_ref.value}:"
                        f"{evidence_requirement.value}"
                    )
                if criterion.blocking and not any(
                    evidence_obligation.blocking
                    for evidence_obligation in matching_obligations
                ):
                    raise ExecutionPackageCompilerError(
                        "blocking evidence_required must have blocking evidence obligation coverage: "
                        f"{criterion.acceptance_ref.value}:{evidence_requirement.value}"
                    )

    def _resolve_required_commands(
        self,
        *,
        package_contract: PackageContract,
        source_surfaces: tuple[SourceSurface, ...],
    ) -> tuple[PackageCommand, ...]:
        test_commands_by_id = {
            test_command.command_id.value: test_command
            for test_command in package_contract.test_commands
        }
        commands: list[PackageCommand] = []
        seen_command_ids: set[str] = set()
        for source_surface in source_surfaces:
            if not source_surface.required_tests:
                raise ExecutionPackageCompilerError(
                    f"source surface required_tests must not be empty: {source_surface.source_surface_ref.value}"
                )
            for required_test in source_surface.required_tests:
                test_command = test_commands_by_id.get(required_test.value)
                if test_command is None:
                    raise ExecutionPackageCompilerError(
                        "required test must map to a declared test command: "
                        f"{required_test.value}"
                    )
                if test_command.command_id.value in seen_command_ids:
                    continue
                commands.append(test_command)
                seen_command_ids.add(test_command.command_id.value)
        return tuple(commands)

    def _build_context_refs(
        self,
        input: ExecutionPackageCompilerInput,
        ticket: TicketNode,
    ) -> tuple[ContextRef, ...]:
        base_refs = [
            ContextRef(value=input.acceptance_contract.acceptance_contract_id.value),
            ContextRef(value=input.package_contract.package_contract_id.value),
            input.workspace_context.workspace_ref,
            ContextRef(value=ticket.ticket_id.value),
            ContextRef(
                value=(
                    "context.agent-team-projection.graph-version-"
                    f"{input.agent_team_projection.graph_version}"
                )
            ),
        ]
        seen_values = {context_ref.value for context_ref in base_refs}
        for context_ref in (
            *input.workspace_context.context_refs,
            *self._verification_context_refs(input, ticket),
        ):
            if context_ref.value in seen_values:
                continue
            base_refs.append(context_ref)
            seen_values.add(context_ref.value)
        return tuple(base_refs)

    def _validate_read_only_context_refs(
        self,
        *,
        ticket: TicketNode,
        context_refs: tuple[ContextRef, ...],
    ) -> None:
        if not _is_verify_blackbox_ticket(ticket):
            return
        unauthorized_refs = _context_refs_outside_allowed_reads(
            context_refs,
            ticket,
            allow_internal_refs=True,
        )
        if unauthorized_refs:
            raise ExecutionPackageCompilerError(
                "context_refs outside ticket allowed_read_refs: "
                + ", ".join(unauthorized_refs)
            )

    def _verification_context_refs(
        self,
        input: ExecutionPackageCompilerInput,
        ticket: TicketNode,
    ) -> tuple[ContextRef, ...]:
        if not _is_verify_blackbox_ticket(ticket):
            return ()
        context = input.verification_context
        if context is None:
            raise ExecutionPackageCompilerError(
                "verification context is required for verify-blackbox ticket"
            )
        if context.raw_manifest_context_ref is None:
            raise ExecutionPackageCompilerError(
                "raw manifest context ref is required for verify-blackbox ticket"
            )
        if context.package_contract_ref.value != input.package_contract.package_contract_id.value:
            raise ExecutionPackageCompilerError(
                "verification context package contract ref mismatch"
            )
        if (
            context.acceptance_contract_ref.value
            != input.acceptance_contract.acceptance_contract_id.value
        ):
            raise ExecutionPackageCompilerError(
                "verification context acceptance contract ref mismatch"
            )
        ticket_surface_refs = set(ticket.source_surface_refs)
        missing_surface_refs = tuple(
            ref.value for ref in context.source_surface_refs if ref.value not in ticket_surface_refs
        )
        if missing_surface_refs:
            raise ExecutionPackageCompilerError(
                "verification context source surface ref outside ticket scope: "
                + ", ".join(missing_surface_refs)
            )
        context_refs = (
            context.raw_manifest_context_ref,
            context.skeleton_summary_ref,
            context.package_contract_ref,
            context.acceptance_contract_ref,
            *context.project_doc_refs,
            *context.source_surface_refs,
            *context.observed_failure_refs,
        )
        unauthorized_refs = _context_refs_outside_allowed_reads(context_refs, ticket)
        if unauthorized_refs:
            raise ExecutionPackageCompilerError(
                "verification context refs outside ticket allowed_read_refs: "
                + ", ".join(unauthorized_refs)
            )
        return context_refs

    def _build_constraints(self, role_profile: RoleProfile) -> tuple[str, ...]:
        return (*_FIXED_CONSTRAINTS, *role_profile.forbidden_actions)

    def _build_required_outputs(
        self,
        *,
        source_surface_refs: tuple[SourceSurfaceRef, ...],
        evidence_obligations: tuple[EvidenceObligation, ...],
    ) -> tuple[RequiredOutput, ...]:
        outputs: list[RequiredOutput] = [
            RequiredOutput(value=f"source:{source_surface_ref.value}")
            for source_surface_ref in source_surface_refs
        ]
        outputs.extend(
            RequiredOutput(
                value=(
                    "evidence:"
                    f"{evidence_obligation.evidence_obligation_id.value}:"
                    f"{evidence_obligation.required_artifact_type.value}"
                )
            )
            for evidence_obligation in evidence_obligations
        )
        return tuple(outputs)


def _normalize_relative_path(path: str, *, field_name: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if not normalized or normalized == ".":
        raise ExecutionPackageCompilerError(f"{field_name} must be a non-empty relative path")
    if normalized.startswith("/") or _DRIVE_LETTER_PATTERN.match(normalized):
        raise ExecutionPackageCompilerError(f"{field_name} must be a non-empty relative path")

    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts:
        raise ExecutionPackageCompilerError(f"{field_name} must be a non-empty relative path")
    if any(part == ".." for part in parts):
        raise ExecutionPackageCompilerError(f"{field_name} contains parent escape")
    return "/".join(parts)


def _path_within_surface(path: str, surface_path: str) -> bool:
    normalized_path = _normalize_relative_path(path, field_name="unsafe write path")
    normalized_surface_path = _normalize_relative_path(surface_path, field_name="source surface path")
    if normalized_path == normalized_surface_path:
        return True
    return normalized_path.startswith(f"{normalized_surface_path}/") or normalized_path.startswith(
        normalized_surface_path.rstrip("/") + "/"
    )


def _is_verify_blackbox_ticket(ticket: TicketNode) -> bool:
    return ticket.purpose == VERIFY_BLACKBOX_PURPOSE


def _validate_verify_blackbox_ticket(ticket: TicketNode) -> None:
    if not _is_verify_blackbox_ticket(ticket):
        return
    if ticket.seat_demand.required_role_category is not RoleCategory.VERIFICATION:
        raise ExecutionPackageCompilerError(
            "verify-blackbox ticket requires verification seat demand"
        )
    if VERIFY_BLACKBOX_CAPABILITY not in ticket.seat_demand.required_capability_tags:
        raise ExecutionPackageCompilerError(
            "verify-blackbox ticket requires task.verify-blackbox capability"
        )


def _context_refs_outside_allowed_reads(
    context_refs: tuple[ContextRef, ...],
    ticket: TicketNode,
    *,
    allow_internal_refs: bool = False,
) -> tuple[str, ...]:
    allowed_read_refs = set(ticket.allowed_read_refs)
    return tuple(
        context_ref.value
        for context_ref in context_refs
        if context_ref.value not in allowed_read_refs
        and not (
            allow_internal_refs
            and _is_execution_package_internal_context_ref(context_ref.value, ticket)
        )
    )


def _is_execution_package_internal_context_ref(value: str, ticket: TicketNode) -> bool:
    if value == ticket.ticket_id.value:
        return True
    return value.startswith("context.agent-team-projection.graph-version-")


__all__ = [
    "ExecutionPackageCompiler",
    "ExecutionPackageCompilerError",
    "ExecutionPackageCompilerInput",
    "ExecutionWorkspaceContext",
    "VerificationExecutionContext",
]
