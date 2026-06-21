"""verify-blackbox 原生编排安全边界负例。"""

from __future__ import annotations

import pytest

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerError,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
    VerificationExecutionContext,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from tests.orchestration.test_verify_blackbox_native_ticket import (
    RAW_MANIFEST_CONTEXT_REF,
    SKELETON_SUMMARY_REF,
    ACCEPTANCE_REF,
    SOURCE_SURFACE_REF,
    EVIDENCE_OBLIGATION_REF,
    _acceptance_contract,
    _agent_team_projection,
    _evidence_obligation,
    _package_contract,
    _seat_projection,
    InMemoryResolver,
    _ticket_created_event,
    _seat_assigned_event,
)
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.seat_assignment import SeatAssignmentProjector
from tests.fixtures.execution.compiler import _model_profile
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_registry
from boardroom_os.agents.profiles import ModelExecutionProfileRegistry


def test_verification_context_cannot_inject_refs_outside_ticket_allowed_read_refs() -> None:
    """拒绝 verification_context 注入未授权的 read refs。"""
    allowed_read_refs = (
        RAW_MANIFEST_CONTEXT_REF.value,
        SKELETON_SUMMARY_REF.value,
        "acceptance-contract-001",
        "package-contract-001",
        SOURCE_SURFACE_REF.value,
    )

    payload = TicketCreatedPayload(
        ticket_id=TicketId(value="ticket.verify-blackbox.generated"),
        purpose="verify-blackbox",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.VERIFICATION,
            required_capability_tags=(CapabilityTag(value="task.verify-blackbox"),),
        ),
        depends_on=(),
        acceptance_refs=(ACCEPTANCE_REF.value,),
        source_surface_refs=(SOURCE_SURFACE_REF.value,),
        evidence_obligations=(EVIDENCE_OBLIGATION_REF.value,),
        allowed_read_refs=allowed_read_refs,
        allowed_write_set=(),
        attempt_count=0,
    )

    resolver = InMemoryResolver(created_payload=payload)
    events = (_ticket_created_event(), _seat_assigned_event())
    seat_assignment_graph = SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(),
    ).project(events)

    verification_context = VerificationExecutionContext(
        raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
        skeleton_summary_ref=SKELETON_SUMMARY_REF,
        package_contract_ref=ContextRef(value="package-contract-001"),
        acceptance_contract_ref=ContextRef(value="acceptance-contract-001"),
        project_doc_refs=(
            ContextRef(value="secrets/provider.env"),
        ),
        source_surface_refs=(ContextRef(value=SOURCE_SURFACE_REF.value),),
        observed_failure_refs=(
            ContextRef(value="secrets/api-keys.json"),
        ),
    )

    with pytest.raises(
        ExecutionPackageCompilerError,
        match="verification context refs outside ticket allowed_read_refs",
    ):
        ExecutionPackageCompiler().compile(
            ExecutionPackageCompilerInput.model_construct(
                ticket_ref=TicketId(value="ticket.verify-blackbox.generated"),
                seat_assignment_graph=seat_assignment_graph,
                agent_team_projection=_agent_team_projection(),
                acceptance_contract=_acceptance_contract(),
                package_contract=_package_contract(),
                evidence_obligations=(_evidence_obligation(),),
                model_execution_profiles=ModelExecutionProfileRegistry.from_profiles(
                    _model_profile(model_execution_profile_id="model.tester.blackbox")
                ),
                role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
                workspace_context=ExecutionWorkspaceContext(
                    workspace_ref=ContextRef(value="context.workspace.tiny-fullstack"),
                    package_root="10-project",
                    context_refs=(ContextRef(value="context.workspace.shared"),),
                ),
                verification_context=verification_context,
            )
        )


def test_verify_blackbox_purpose_without_verification_seat_demand_is_rejected() -> None:
    """拒绝只靠 purpose 伪装的非验证席位需求。"""
    with pytest.raises(
        ValueError,
        match="verify-blackbox ticket requires verification seat demand",
    ):
        TicketCreatedPayload(
            ticket_id=TicketId(value="ticket.verify-blackbox.malformed"),
            purpose="verify-blackbox",
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.IMPLEMENTATION,
                required_capability_tags=(CapabilityTag(value="task.implement-package"),),
            ),
            depends_on=(),
            acceptance_refs=(ACCEPTANCE_REF.value,),
            source_surface_refs=(SOURCE_SURFACE_REF.value,),
            evidence_obligations=(EVIDENCE_OBLIGATION_REF.value,),
            allowed_read_refs=(
                RAW_MANIFEST_CONTEXT_REF.value,
                SKELETON_SUMMARY_REF.value,
                "acceptance-contract-001",
                "package-contract-001",
            ),
            allowed_write_set=(),
            attempt_count=0,
        )
