import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.execution.package import (
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.graph.ticket import TicketId


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker.default",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.write",),
        fallback_policy_ref="fallback.default",
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.source.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )


def _command() -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value="cmd.test"),
        label="Run tests",
        command=("pytest", "tests"),
        cwd="10-project",
    )


def _package_fields() -> dict[str, object]:
    return {
        "execution_package_id": ExecutionPackageId(value="exec.ticket.backend.1"),
        "ticket_ref": TicketId(value="ticket.backend"),
        "graph_version": 7,
        "seat_ref": AgentSeatRef(value="seat.worker.backend"),
        "model_execution_profile": _model_execution_profile(),
        "objective": "Implement backend API",
        "context_refs": (ContextRef(value="context.contracts.active"),),
        "constraints": ("Only write backend files",),
        "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
        "source_surface_refs": (SourceSurfaceRef(value="surface.backend"),),
        "allowed_read_refs": ("README.md",),
        "allowed_write_set": (AllowedWritePath(value="backend/app.py"),),
        "required_outputs": (RequiredOutput(value="backend source patch"),),
        "commands": (_command(),),
        "evidence_obligations": (_evidence_obligation(),),
        "fallback_policy_ref": FallbackPolicyRef(value="fallback.default"),
        "audit_requirements": (AuditRequirement(value="record received context"),),
    }


@pytest.mark.parametrize(
    "field_name",
    (
        "ticket_ref",
        "graph_version",
        "seat_ref",
        "model_execution_profile",
        "acceptance_refs",
        "allowed_write_set",
        "evidence_obligations",
        "fallback_policy_ref",
    ),
)
def test_execution_package_rejects_missing_required_fields(field_name: str) -> None:
    fields = _package_fields()
    fields.pop(field_name)

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


@pytest.mark.parametrize("graph_version", (0, -1))
def test_execution_package_rejects_non_positive_graph_version(graph_version: int) -> None:
    fields = _package_fields()
    fields["graph_version"] = graph_version

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


@pytest.mark.parametrize(
    "field_name",
    (
        "context_refs",
        "acceptance_refs",
        "source_surface_refs",
        "allowed_write_set",
        "required_outputs",
        "commands",
        "evidence_obligations",
        "audit_requirements",
    ),
)
def test_execution_package_rejects_empty_required_tuples(field_name: str) -> None:
    fields = _package_fields()
    fields[field_name] = ()

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


def test_execution_package_allows_empty_allowed_read_refs() -> None:
    fields = _package_fields()
    fields["allowed_read_refs"] = ()

    package = ExecutionPackage(**fields)

    assert package.allowed_read_refs == ()


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("context_refs", (ContextRef(value="context.valid"), " ")),
        ("allowed_read_refs", (" ",)),
        ("allowed_write_set", (" ",)),
        ("required_outputs", (" ",)),
        ("audit_requirements", (" ",)),
    ),
)
def test_execution_package_rejects_empty_ref_items(
    field_name: str,
    bad_value: tuple[object, ...],
) -> None:
    fields = _package_fields()
    fields[field_name] = bad_value

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


def test_execution_package_rejects_empty_command_items() -> None:
    fields = _package_fields()
    fields["commands"] = (
        {
            "command_id": {"value": "cmd.bad"},
            "label": "Bad command",
            "command": ("pytest", " "),
            "cwd": "10-project",
        },
    )

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


def test_execution_package_rejects_unknown_fields() -> None:
    fields = _package_fields()
    fields["provider_attempt_ref"] = "attempt.future"

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


def test_execution_package_rejects_ticket_id_alias() -> None:
    fields = _package_fields()
    fields.pop("ticket_ref")
    fields["ticket_id"] = TicketId(value="ticket.backend")

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)


def test_execution_package_requires_model_execution_profile_snapshot() -> None:
    fields = _package_fields()
    fields.pop("model_execution_profile")
    fields["model_execution_profile_ref"] = ContractId(value="model-profile.worker.default")

    with pytest.raises(ValidationError):
        ExecutionPackage(**fields)
