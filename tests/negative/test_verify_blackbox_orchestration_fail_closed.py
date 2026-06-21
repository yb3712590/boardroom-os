from __future__ import annotations

import pytest

from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerError,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
    VerificationExecutionContext,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.graph.ticket import TicketCreatedPayload
from tests.orchestration.test_verify_blackbox_native_ticket import (
    RAW_MANIFEST_CONTEXT_REF,
    SKELETON_SUMMARY_REF,
    TICKET_ID,
    SHARED_WORKSPACE_CONTEXT_REF,
    WORKSPACE_CONTEXT_REF,
    _acceptance_contract,
    _agent_team_projection,
    _evidence_obligation,
    _package_contract,
    _seat_assignment_graph_from_events,
    _verification_request,
)
from boardroom_os.orchestration.verification import VerifyBlackboxTicketIntent
from tests.fixtures.execution.compiler import _model_profile
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook_fields_for_category,
    baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.profiles import ModelExecutionProfileRegistry


def test_verify_blackbox_requires_real_seat_assignment() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events(assign=False)

    assert TICKET_ID not in seat_assignment_graph.ready_queue
    assert "missing seat assignment" in seat_assignment_graph.seat_blockers[TICKET_ID][0]


def test_compiler_rejects_verify_blackbox_ticket_without_verification_context() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events()

    with pytest.raises(ExecutionPackageCompilerError, match="verification context"):
        ExecutionPackageCompiler().compile(
            _compiler_input(seat_assignment_graph=seat_assignment_graph)
        )


def test_compiler_rejects_verify_blackbox_with_missing_raw_manifest_context() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events()

    with pytest.raises(ExecutionPackageCompilerError, match="raw manifest context"):
        ExecutionPackageCompiler().compile(
            _compiler_input(
                seat_assignment_graph=seat_assignment_graph,
                verification_context=VerificationExecutionContext(
                    raw_manifest_context_ref=None,
                    skeleton_summary_ref=SKELETON_SUMMARY_REF,
                    package_contract_ref=ContextRef(value="package-contract-001"),
                    acceptance_contract_ref=ContextRef(value="acceptance-contract-001"),
                    project_doc_refs=(ContextRef(value="docs/README.md"),),
                    source_surface_refs=(ContextRef(value="surface.run-manifest"),),
                    observed_failure_refs=(ContextRef(value="failure.raw-run-error"),),
                ),
            )
        )


def test_compiler_rejects_verify_blackbox_ticket_not_in_ready_queue() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events().model_copy(
        update={"ready_queue": ()}
    )

    with pytest.raises(ExecutionPackageCompilerError, match="ready_queue"):
        ExecutionPackageCompiler().compile(
            _compiler_input(
                seat_assignment_graph=seat_assignment_graph,
                verification_context=_verification_context(),
            )
        )


def test_compiler_rejects_verification_context_ref_outside_ticket_allowed_reads() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events()

    with pytest.raises(ExecutionPackageCompilerError, match="allowed_read_refs"):
        ExecutionPackageCompiler().compile(
            _compiler_input(
                seat_assignment_graph=seat_assignment_graph,
                verification_context=VerificationExecutionContext(
                    raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
                    skeleton_summary_ref=SKELETON_SUMMARY_REF,
                    package_contract_ref=ContextRef(value="package-contract-001"),
                    acceptance_contract_ref=ContextRef(value="acceptance-contract-001"),
                    project_doc_refs=(
                        ContextRef(value="docs/README.md"),
                        ContextRef(value="secrets/provider.env"),
                    ),
                    source_surface_refs=(ContextRef(value="surface.run-manifest"),),
                    observed_failure_refs=(ContextRef(value="failure.raw-run-error"),),
                ),
            )
        )


def test_compiler_rejects_workspace_context_ref_outside_ticket_allowed_reads() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events()

    with pytest.raises(ExecutionPackageCompilerError, match="context_refs outside ticket allowed_read_refs"):
        ExecutionPackageCompiler().compile(
            _compiler_input(
                seat_assignment_graph=seat_assignment_graph,
                verification_context=_verification_context(),
                workspace_context=ExecutionWorkspaceContext(
                    workspace_ref=ContextRef(value="context.workspace.unapproved"),
                    package_root="10-project",
                    context_refs=(ContextRef(value="context.workspace.shared"),),
                ),
            )
        )


def test_verify_blackbox_payload_rejects_non_verification_seat_demand() -> None:
    valid_payload = VerifyBlackboxTicketIntent.from_request(
        _verification_request()
    ).to_ticket_created_payload()
    values = valid_payload.model_dump()
    values["seat_demand"] = SeatDemand(
        required_role_category=RoleCategory.IMPLEMENTATION,
        required_capability_tags=(CapabilityTag(value="task.implementation"),),
    )

    with pytest.raises(ValueError, match="verify-blackbox ticket requires verification seat demand"):
        TicketCreatedPayload(**values)


def test_verify_blackbox_payload_rejects_missing_verify_blackbox_capability() -> None:
    valid_payload = VerifyBlackboxTicketIntent.from_request(
        _verification_request()
    ).to_ticket_created_payload()
    values = valid_payload.model_dump()
    values["seat_demand"] = SeatDemand(
        required_role_category=RoleCategory.VERIFICATION,
        required_capability_tags=(CapabilityTag(value="task.other-verification"),),
    )

    with pytest.raises(ValueError, match="verify-blackbox ticket requires task.verify-blackbox capability"):
        TicketCreatedPayload(**values)


def test_verify_blackbox_payload_rejects_allowed_write_set() -> None:
    valid_payload = VerifyBlackboxTicketIntent.from_request(
        _verification_request()
    ).to_ticket_created_payload()
    values = valid_payload.model_dump()
    values["allowed_write_set"] = ("10-project/backend/app.py",)

    with pytest.raises(ValueError, match="verify-blackbox ticket allowed_write_set must be empty"):
        TicketCreatedPayload(**values)


def test_compiler_rejects_malformed_verify_blackbox_ticket_even_if_model_constructed() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events()
    valid_ticket = seat_assignment_graph.nodes[TICKET_ID]
    malformed_ticket = valid_ticket.model_copy(
        update={
            "seat_demand": SeatDemand(
                required_role_category=RoleCategory.IMPLEMENTATION,
                required_capability_tags=(CapabilityTag(value="task.implementation"),),
            )
        }
    )
    seat_assignment_graph = seat_assignment_graph.model_copy(
        update={
            "nodes": {**seat_assignment_graph.nodes, TICKET_ID: malformed_ticket}
        }
    )

    with pytest.raises(ExecutionPackageCompilerError, match="verify-blackbox ticket requires"):
        ExecutionPackageCompiler().compile(
            _compiler_input(
                seat_assignment_graph=seat_assignment_graph,
                agent_team_projection=_implementation_agent_team_projection(),
                verification_context=_verification_context(),
            )
        )


def test_compiler_rejects_verify_blackbox_ticket_with_wrong_capability_even_if_constructed() -> None:
    seat_assignment_graph = _seat_assignment_graph_from_events()
    valid_ticket = seat_assignment_graph.nodes[TICKET_ID]
    malformed_ticket = valid_ticket.model_copy(
        update={
            "seat_demand": SeatDemand(
                required_role_category=RoleCategory.VERIFICATION,
                required_capability_tags=(CapabilityTag(value="task.other-verification"),),
            )
        }
    )
    seat_assignment_graph = seat_assignment_graph.model_copy(
        update={
            "nodes": {**seat_assignment_graph.nodes, TICKET_ID: malformed_ticket}
        }
    )

    with pytest.raises(ExecutionPackageCompilerError, match="task.verify-blackbox capability"):
        ExecutionPackageCompiler().compile(
            _compiler_input(
                seat_assignment_graph=seat_assignment_graph,
                verification_context=_verification_context(),
            )
        )


def _compiler_input(
    *,
    seat_assignment_graph,
    agent_team_projection=None,
    verification_context: VerificationExecutionContext | None = None,
    workspace_context: ExecutionWorkspaceContext | None = None,
) -> ExecutionPackageCompilerInput:
    return ExecutionPackageCompilerInput.model_construct(
        ticket_ref=TICKET_ID,
        seat_assignment_graph=seat_assignment_graph,
        agent_team_projection=agent_team_projection or _agent_team_projection(),
        acceptance_contract=_acceptance_contract(),
        package_contract=_package_contract(),
        evidence_obligations=(_evidence_obligation(),),
        model_execution_profiles=ModelExecutionProfileRegistry.from_profiles(
            _model_profile(model_execution_profile_id="model.tester.blackbox")
        ),
        role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
        workspace_context=workspace_context
        or ExecutionWorkspaceContext(
            workspace_ref=WORKSPACE_CONTEXT_REF,
            package_root="10-project",
            context_refs=(SHARED_WORKSPACE_CONTEXT_REF,),
        ),
        verification_context=verification_context,
    )


def _implementation_agent_team_projection():
    projection = _agent_team_projection()
    role_profile = projection.role_profiles.profiles[0].model_copy(
        update={
            "role_category": RoleCategory.IMPLEMENTATION,
            "role_name": "Implementation Worker",
            "responsibilities": ("Implement package changes.",),
            "capability_tags": (CapabilityTag(value="task.implementation"),),
            **baseline_role_prompt_hook_fields_for_category(RoleCategory.IMPLEMENTATION),
        }
    )
    seat = tuple(projection.seat_lifecycle.active_seats.values())[0].model_copy(
        update={
            "role_category": RoleCategory.IMPLEMENTATION,
            "capability_tags": (CapabilityTag(value="task.implementation"),),
        }
    )
    return projection.model_copy(
        update={
            "role_profiles": projection.role_profiles.model_copy(
                update={"profiles": (role_profile,)}
            ),
            "seat_lifecycle": projection.seat_lifecycle.model_copy(
                update={
                    "seats": {seat.seat_ref: seat},
                    "active_seats": {seat.seat_ref: seat},
                }
            ),
        }
    )


def _verification_context() -> VerificationExecutionContext:
    return VerificationExecutionContext(
        raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
        skeleton_summary_ref=SKELETON_SUMMARY_REF,
        package_contract_ref=ContextRef(value="package-contract-001"),
        acceptance_contract_ref=ContextRef(value="acceptance-contract-001"),
        project_doc_refs=(ContextRef(value="docs/README.md"),),
        source_surface_refs=(ContextRef(value="surface.run-manifest"),),
        observed_failure_refs=(ContextRef(value="failure.raw-run-error"),),
    )
