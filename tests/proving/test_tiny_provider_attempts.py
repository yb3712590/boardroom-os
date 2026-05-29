from __future__ import annotations

from pathlib import Path

import pytest

from boardroom_os.events.types import EventType
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.providers.attempt import (
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from tests.proving.fixtures.tiny_provider_attempts import (
    TinyProviderAttemptValidationError,
    build_tiny_real_provider_attempt_fixture,
    compile_tiny_implementation_execution_packages,
    openai_settings_from_test_env,
    validate_tiny_provider_attempt_results,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    TICKET_ARCHITECTURE_ID,
    build_tiny_ticket_graph_fixture,
)


def test_tiny_openai_settings_fail_closed_without_test_env(tmp_path: Path) -> None:
    missing_env = tmp_path / ".env.test"

    with pytest.raises(TinyProviderAttemptValidationError, match="OPENAI_API_KEY|env"):
        openai_settings_from_test_env(missing_env)


def test_tiny_execution_packages_compile_from_ticket_graph_contracts() -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )

    assert set(compiled.execution_packages) == set(compiled.ticket_graph_fixture.implementation_ticket_ids)
    for ticket_id, execution_package in compiled.execution_packages.items():
        assert execution_package.ticket_ref == ticket_id
        assert execution_package.model_execution_profile.reasoning_effort == "high"
        assert execution_package.model_execution_profile.model == "gpt-5.5"
        assert execution_package.allowed_write_set
        assert all(not path.value.startswith("10-project/") for path in execution_package.allowed_write_set)

    architecture_profile = compiled.model_execution_profiles_by_ticket_id[TICKET_ARCHITECTURE_ID]
    assert architecture_profile.reasoning_effort == "xhigh"


def test_provider_zero_attempt_rejected() -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )

    with pytest.raises(TinyProviderAttemptValidationError, match="provider attempt"):
        validate_tiny_provider_attempt_results(
            execution_packages=compiled.execution_packages,
            runtime_results=(),
        )


def test_fallback_source_delivery_rejected() -> None:
    fixture = build_tiny_real_provider_attempt_fixture(use_fake_results=True)
    first_result = fixture.runtime_results[0]
    fallback_attempt = first_result.provider_attempt.model_copy(
        update={
            "outcome": ProviderAttemptOutcome.FALLBACK_ARTIFACT,
            "fallback_kind": FallbackKind.TOOLING_PREFLIGHT,
        }
    )
    fallback_result = first_result.model_copy(update={"provider_attempt": fallback_attempt})

    with pytest.raises(TinyProviderAttemptValidationError, match="fallback"):
        validate_tiny_provider_attempt_results(
            execution_packages=fixture.execution_packages,
            runtime_results=(fallback_result, *fixture.runtime_results[1:]),
        )


def test_placeholder_artifact_refs_rejected() -> None:
    fixture = build_tiny_real_provider_attempt_fixture(use_fake_results=True)
    first_result = fixture.runtime_results[0]
    placeholder_attempt = first_result.provider_attempt.model_copy(
        update={
            "raw_output_ref": "provider-artifact.openai.raw.placeholder",
            "parsed_output_ref": "provider-artifact.openai.text.placeholder",
        }
    )
    placeholder_result = first_result.model_copy(update={"provider_attempt": placeholder_attempt})

    with pytest.raises(TinyProviderAttemptValidationError, match="placeholder"):
        validate_tiny_provider_attempt_results(
            execution_packages=fixture.execution_packages,
            runtime_results=(placeholder_result, *fixture.runtime_results[1:]),
        )


def test_fake_fixture_still_proves_runtime_never_emits_ticket_completed() -> None:
    fixture = build_tiny_real_provider_attempt_fixture(use_fake_results=True)

    for result in fixture.runtime_results:
        assert EventType.PROVIDER_ATTEMPT_RECORDED in tuple(event.event_type for event in result.events)
        assert EventType.WORK_PRODUCT_SUBMITTED in tuple(event.event_type for event in result.events)
        assert EventType.TICKET_COMPLETED not in tuple(event.event_type for event in result.events)


def test_real_provider_records_attempts_for_every_tiny_implementation_ticket() -> None:
    settings = openai_settings_from_test_env(Path(".env.test"))

    fixture = build_tiny_real_provider_attempt_fixture(
        settings=settings,
        use_fake_results=False,
    )

    assert set(fixture.provider_attempts_by_ticket_id) == set(fixture.execution_packages)
    assert len(fixture.runtime_results) == 4
    for ticket_id, attempt in fixture.provider_attempts_by_ticket_id.items():
        execution_package = fixture.execution_packages[ticket_id]
        assert attempt.status is ProviderAttemptStatus.SUCCEEDED
        assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
        assert attempt.provider == execution_package.model_execution_profile.provider
        assert attempt.model == settings.model
        assert attempt.reasoning_effort == "high"
        assert attempt.input_package_ref.value == execution_package.execution_package_id.value
        assert attempt.seat_ref == execution_package.seat_ref
        assert attempt.raw_output_ref is not None
        assert attempt.parsed_output_ref is not None
