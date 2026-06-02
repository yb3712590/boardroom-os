import pytest

from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.types import AcceptanceRef
from tests.fixtures.contracts import tiny_fullstack_contract
from tests.fixtures.contracts.tiny_fullstack_contract import build_tiny_fullstack_contract_fixture
from tests.proving.fixtures import tiny_provider_attempts


def test_uvicorn_backend_command_conflicts_with_standard_library_only_prompt() -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    package_contract = fixture.package_contract.model_copy(
        update={
            "run_commands": tuple(
                command.model_copy(update={"command": ("python", "-m", "uvicorn", "backend.app:app")})
                if command.command_id.value == "run-backend"
                else command
                for command in fixture.package_contract.run_commands
            )
        }
    )

    with pytest.raises(ValueError, match="standard-library HTTP route"):
        tiny_fullstack_contract.validate_tiny_fullstack_contract_recovery(
            acceptance_contract=fixture.acceptance_contract,
            package_contract=package_contract,
            provider_system_instructions=(
                "Use only Python standard library modules. Do not use Flask, FastAPI, "
                "requests, npm, or other third-party packages."
            ),
        )


@pytest.mark.parametrize(
    "provider_system_instructions",
    (
        "standard-library-only",
    ),
)
def test_tiny_contract_always_rejects_uvicorn_backend_command(
    provider_system_instructions: str,
) -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    package_contract = fixture.package_contract.model_copy(
        update={
            "run_commands": tuple(
                command.model_copy(update={"command": ("python", "-m", "uvicorn", "backend.app:app")})
                if command.command_id.value == "run-backend"
                else command
                for command in fixture.package_contract.run_commands
            )
        }
    )

    with pytest.raises(ValueError, match="standard-library HTTP route"):
        tiny_fullstack_contract.validate_tiny_fullstack_contract_recovery(
            acceptance_contract=fixture.acceptance_contract,
            package_contract=package_contract,
            provider_system_instructions=provider_system_instructions,
        )


def test_fetch_backend_api_without_live_http_evidence_is_not_closeout_ready() -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    acceptance_contract = _replace_criterion(
        fixture.acceptance_contract,
        acceptance_ref="AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
        statement="Frontend fetches the backend API instead of serving static placeholder data.",
        evidence_required=("frontend_backend_integration_evidence", "frontend_source_inventory"),
    )

    with pytest.raises(ValueError, match="live HTTP integration evidence"):
        tiny_fullstack_contract.validate_tiny_fullstack_contract_recovery(
            acceptance_contract=acceptance_contract,
            package_contract=fixture.package_contract,
            provider_system_instructions=tiny_provider_attempts.tiny_source_delivery_system_instructions(),
        )


def test_declared_commands_without_final_evidence_obligation_are_not_closeout_ready() -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    acceptance_contract = _replace_criterion(
        fixture.acceptance_contract,
        acceptance_ref="AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
        statement="Package declares local run and test commands.",
        evidence_required=("run_manifest", "command_evidence"),
    )

    with pytest.raises(ValueError, match="final command evidence"):
        tiny_fullstack_contract.validate_tiny_fullstack_contract_recovery(
            acceptance_contract=acceptance_contract,
            package_contract=fixture.package_contract,
            provider_system_instructions=tiny_provider_attempts.tiny_source_delivery_system_instructions(),
        )


@pytest.mark.parametrize(
    ("provider_system_instructions", "match"),
    (
        (
            "",
            "provider prompt",
        ),
        (
            "Use only Python standard library modules. Return JSON.",
            "http.server|BaseHTTPRequestHandler",
        ),
        (
            (
                "Use Python standard library modules including http.server and "
                "BaseHTTPRequestHandler. Implement /health and /books."
            ),
            "SQLite persistence via HTTP",
        ),
        (
            (
                "Use Python standard library modules including http.server and "
                "BaseHTTPRequestHandler. Implement /health and /books with "
                "SQLite persistence via HTTP."
            ),
            "fakeFetch-only",
        ),
    ),
)
def test_tiny_contract_recovery_requires_provider_prompt_http_route_markers(
    provider_system_instructions: str,
    match: str,
) -> None:
    fixture = build_tiny_fullstack_contract_fixture()

    with pytest.raises(ValueError, match=match):
        tiny_fullstack_contract.validate_tiny_fullstack_contract_recovery(
            acceptance_contract=fixture.acceptance_contract,
            package_contract=fixture.package_contract,
            provider_system_instructions=provider_system_instructions,
        )


def _replace_criterion(
    acceptance_contract: AcceptanceContract,
    *,
    acceptance_ref: str,
    statement: str,
    evidence_required: tuple[str, ...],
) -> AcceptanceContract:
    criteria = tuple(
        criterion.model_copy(
            update={
                "statement": statement,
                "evidence_required": tuple(
                    tiny_fullstack_contract.EvidenceRequirement(value=value)
                    for value in evidence_required
                ),
            }
        )
        if criterion.acceptance_ref == AcceptanceRef(value=acceptance_ref)
        else criterion
        for criterion in acceptance_contract.criteria
    )
    return acceptance_contract.model_copy(update={"criteria": criteria})
