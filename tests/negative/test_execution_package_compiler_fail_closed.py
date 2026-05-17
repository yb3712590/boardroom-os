import pytest

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.acceptance import (
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
)
from boardroom_os.contracts.source_surface import RequiredTestRef
from boardroom_os.contracts.types import AcceptanceRef, ContractStatus, SourceSurfaceRef
from boardroom_os.execution.compiler import (
    ExecutionPackageCompilerError,
    ExecutionWorkspaceContext,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.graph.ticket import TicketStatus
from tests.fixtures.execution.compiler import (
    DEFAULT_ACCEPTANCE_REF,
    DEFAULT_EVIDENCE_OBLIGATION_REF,
    DEFAULT_SOURCE_SURFACE_REF,
    _acceptance_contract,
    _agent_team_projection,
    _compile,
    _evidence_obligation,
    _package_contract,
    _seat,
    _seat_assignment_graph,
    _source_surface,
    _ticket,
)


def test_compiler_rejects_ticket_not_ready() -> None:
    ticket = _ticket()

    with pytest.raises(ExecutionPackageCompilerError, match="ready_queue"):
        _compile(
            seat_assignment_graph=_seat_assignment_graph(ticket=ticket, ready_queue=()),
        )


def test_compiler_rejects_ticket_status_not_ready_even_when_queued() -> None:
    ticket = _ticket(status=TicketStatus.BLOCKED)

    with pytest.raises(ExecutionPackageCompilerError, match="ticket status"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_missing_assignment() -> None:
    ticket = _ticket()

    with pytest.raises(ExecutionPackageCompilerError, match="missing seat assignment"):
        _compile(
            seat_assignment_graph=_seat_assignment_graph(ticket=ticket, seat_assignments={}),
        )


def test_compiler_rejects_unknown_or_inactive_assigned_seat() -> None:
    ticket = _ticket()

    with pytest.raises(ExecutionPackageCompilerError, match="active seat"):
        _compile(
            seat_assignment_graph=_seat_assignment_graph(
                ticket=ticket,
                seat_assignments={ticket.ticket_id: "seat.worker.ghost"},
            ),
        )


def test_compiler_rejects_capability_mismatch() -> None:
    demand = SeatDemand(
        required_role_category=RoleCategory.IMPLEMENTATION,
        required_capability_tags=(CapabilityTag(value="task.verification"),),
    )
    ticket = _ticket(seat_demand=demand)

    with pytest.raises(ExecutionPackageCompilerError, match="missing capability"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_graph_version_mismatch() -> None:
    with pytest.raises(ExecutionPackageCompilerError, match="graph_version"):
        _compile(agent_team_projection=_agent_team_projection(graph_version=8))


def test_compiler_rejects_acceptance_ref_outside_active_contract() -> None:
    ticket = _ticket(acceptance_refs=("AC-MISSING",))

    with pytest.raises(ExecutionPackageCompilerError, match="acceptance_ref"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_inactive_acceptance_contract() -> None:
    with pytest.raises(ExecutionPackageCompilerError, match="active"):
        _compile(acceptance_contract=_acceptance_contract(status=ContractStatus.retired()))


def test_compiler_rejects_workspace_package_root_mismatch() -> None:
    workspace_context = ExecutionWorkspaceContext(
        workspace_ref=ContextRef(value="context.workspace.backend"),
        package_root="workspace/other-service",
    )

    with pytest.raises(ExecutionPackageCompilerError, match="package_root"):
        _compile(workspace_context=workspace_context)


def test_compiler_rejects_unknown_source_surface() -> None:
    ticket = _ticket(source_surface_refs=("surface.unknown",))

    with pytest.raises(ExecutionPackageCompilerError, match="source_surface_ref"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_source_surface_acceptance_mismatch() -> None:
    criteria = (
        AcceptanceCriterion(
            acceptance_ref=AcceptanceRef(value="AC-BACKEND-001"),
            statement="Primary backend criterion.",
            evidence_required=(EvidenceRequirement(value="source_patch"),),
            blocking=True,
            source_surface_refs=(DEFAULT_SOURCE_SURFACE_REF,),
            verification_strategy=VerificationStrategy(value="checker"),
        ),
        AcceptanceCriterion(
            acceptance_ref=AcceptanceRef(value="AC-BACKEND-002"),
            statement="Secondary backend criterion.",
            evidence_required=(EvidenceRequirement(value="source_patch"),),
            blocking=False,
            source_surface_refs=(DEFAULT_SOURCE_SURFACE_REF,),
            verification_strategy=VerificationStrategy(value="checker"),
        ),
    )
    ticket = _ticket(acceptance_refs=("AC-BACKEND-001", "AC-BACKEND-002"))

    with pytest.raises(ExecutionPackageCompilerError, match="does not cover"):
        _compile(
            seat_assignment_graph=_seat_assignment_graph(ticket=ticket),
            acceptance_contract=_acceptance_contract(criteria=criteria),
        )


def test_compiler_rejects_write_path_outside_source_surface() -> None:
    ticket = _ticket(allowed_write_set=("docs/README.md",))

    with pytest.raises(ExecutionPackageCompilerError, match="allowed_write_set"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


@pytest.mark.parametrize(
    "unsafe_write_path",
    (
        "/tmp/app.py",
        "C:/tmp/app.py",
        "C:tmp/app.py",
        "C:tmp\\app.py",
        "../backend/app.py",
    ),
)
def test_compiler_rejects_unsafe_write_path(unsafe_write_path: str) -> None:
    ticket = _ticket(allowed_write_set=(unsafe_write_path,))

    with pytest.raises(ExecutionPackageCompilerError, match="unsafe write path"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_missing_evidence_obligation() -> None:
    ticket = _ticket(evidence_obligations=("evidence.missing",))

    with pytest.raises(ExecutionPackageCompilerError, match="evidence obligation"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_duplicate_evidence_obligation_ref() -> None:
    ticket = _ticket(
        evidence_obligations=(
            DEFAULT_EVIDENCE_OBLIGATION_REF.value,
            DEFAULT_EVIDENCE_OBLIGATION_REF.value,
        )
    )

    with pytest.raises(ExecutionPackageCompilerError, match="duplicate evidence obligation"):
        _compile(seat_assignment_graph=_seat_assignment_graph(ticket=ticket))


def test_compiler_rejects_evidence_obligation_scope_mismatch() -> None:
    obligation = _evidence_obligation(
        source_surface_refs=(SourceSurfaceRef(value="surface.docs"),),
    )

    with pytest.raises(ExecutionPackageCompilerError, match="source surface"):
        _compile(evidence_obligations=(obligation,))


def test_compiler_rejects_missing_blocking_obligation_coverage() -> None:
    obligation = _evidence_obligation(blocking=False)

    with pytest.raises(ExecutionPackageCompilerError, match="blocking"):
        _compile(evidence_obligations=(obligation,))


def test_compiler_rejects_evidence_required_artifact_type_mismatch() -> None:
    obligation = _evidence_obligation(required_artifact_type="run_log")

    with pytest.raises(ExecutionPackageCompilerError, match="evidence_required"):
        _compile(evidence_obligations=(obligation,))


def test_compiler_rejects_missing_one_of_multiple_evidence_requirements() -> None:
    criteria = (
        AcceptanceCriterion(
            acceptance_ref=DEFAULT_ACCEPTANCE_REF,
            statement="Backend implementation has both source and test evidence.",
            evidence_required=(
                EvidenceRequirement(value="source_patch"),
                EvidenceRequirement(value="test_run"),
            ),
            blocking=True,
            source_surface_refs=(DEFAULT_SOURCE_SURFACE_REF,),
            verification_strategy=VerificationStrategy(value="checker"),
        ),
    )

    with pytest.raises(ExecutionPackageCompilerError, match="evidence_required"):
        _compile(acceptance_contract=_acceptance_contract(criteria=criteria))


def test_compiler_rejects_source_surface_without_required_tests() -> None:
    surface = _source_surface(required_tests=())

    with pytest.raises(ExecutionPackageCompilerError, match="required_tests"):
        _compile(package_contract=_package_contract(source_surfaces=(surface,)))


def test_compiler_rejects_required_test_without_declared_command() -> None:
    surface = _source_surface(required_tests=(RequiredTestRef(value="test.pytest.missing"),))

    with pytest.raises(ExecutionPackageCompilerError, match="declared test command"):
        _compile(package_contract=_package_contract(source_surfaces=(surface,)))


def test_compiler_rejects_unresolvable_model_execution_profile() -> None:
    seat = _seat(model_execution_profile_ref="model.worker.unknown")

    with pytest.raises(ExecutionPackageCompilerError, match="model_execution_profile_ref"):
        _compile(agent_team_projection=_agent_team_projection(seat=seat))


def test_compiler_rejects_unresolvable_role_profile() -> None:
    seat = _seat(role_profile_ref="role.worker.unknown")

    with pytest.raises(ExecutionPackageCompilerError, match="role_profile_ref"):
        _compile(agent_team_projection=_agent_team_projection(seat=seat))
