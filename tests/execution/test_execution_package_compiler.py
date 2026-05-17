from boardroom_os.execution.compiler import ExecutionPackageCompiler
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from tests.fixtures.execution.compiler import (
    DEFAULT_ACCEPTANCE_REF,
    DEFAULT_SOURCE_SURFACE_REF,
    DEFAULT_TICKET_ID,
    _command,
    _compiler_input,
    _evidence_obligation,
    _model_profile,
)


def test_compiler_builds_backend_worker_execution_package() -> None:
    execution_package = ExecutionPackageCompiler().compile(_compiler_input())

    assert execution_package.execution_package_id == ExecutionPackageId(
        value="exec.ticket.backend.graph-7"
    )
    assert execution_package.ticket_ref == DEFAULT_TICKET_ID
    assert execution_package.graph_version == 7
    assert execution_package.seat_ref.value == "seat.worker.backend"
    assert execution_package.model_execution_profile == _model_profile()
    assert execution_package.objective == "Implement backend fail-closed behavior."
    assert execution_package.context_refs == (
        ContextRef(value="acceptance-contract-001"),
        ContextRef(value="package-contract-001"),
        ContextRef(value="context.workspace.backend"),
        ContextRef(value=DEFAULT_TICKET_ID.value),
        ContextRef(value="context.agent-team-projection.graph-version-7"),
        ContextRef(value="context.workspace.shared"),
    )
    assert execution_package.constraints == (
        "Only write paths listed in allowed_write_set.",
        "Do not modify active contracts or governance state.",
        "Do not create or alter evidence outside declared evidence_obligations.",
        "Do not bypass required tests.",
    )
    assert execution_package.acceptance_refs == (DEFAULT_ACCEPTANCE_REF,)
    assert execution_package.source_surface_refs == (DEFAULT_SOURCE_SURFACE_REF,)
    assert execution_package.allowed_read_refs == (AllowedReadRef(value="README.md"),)
    assert execution_package.allowed_write_set == (
        AllowedWritePath(value="src/backend/app.py"),
    )
    assert execution_package.required_outputs == (
        RequiredOutput(value=f"source:{DEFAULT_SOURCE_SURFACE_REF.value}"),
        RequiredOutput(value="evidence:evidence.backend.patch:source_patch"),
    )
    assert execution_package.commands == (_command(),)
    assert execution_package.evidence_obligations == (_evidence_obligation(),)
    assert execution_package.fallback_policy_ref == FallbackPolicyRef(
        value="fallback.worker.record_failure"
    )
    assert execution_package.audit_requirements == (
        AuditRequirement(value="record.received_execution_package"),
        AuditRequirement(value="preserve.model_execution_profile_snapshot"),
        AuditRequirement(value="preserve.allowed_write_set"),
        AuditRequirement(value="preserve.evidence_obligation_refs"),
        AuditRequirement(value="preserve.agent_team_projection_graph_version"),
    )
