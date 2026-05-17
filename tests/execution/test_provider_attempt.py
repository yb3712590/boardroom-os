from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.providers.adapter import (
    FakeProviderTransport,
    ProviderRequest,
    ProviderResponse,
)
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


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


def _started_at() -> datetime:
    return datetime(2026, 5, 18, 9, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 5, 18, 9, 1, tzinfo=UTC)


def _attempt_fields() -> dict[str, object]:
    return {
        "provider_attempt_id": "provider-attempt.1",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "reasoning_effort": "medium",
        "input_package_ref": "exec.ticket.backend.1",
        "seat_ref": "seat.worker.backend",
        "status": ProviderAttemptStatus.SUCCEEDED,
        "outcome": ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        "started_at": _started_at(),
        "finished_at": _finished_at(),
        "raw_output_ref": "artifact.raw.1",
        "parsed_output_ref": "artifact.parsed.1",
    }


@pytest.mark.parametrize(
    "field_name",
    (
        "provider",
        "model",
        "reasoning_effort",
        "input_package_ref",
        "seat_ref",
        "status",
        "outcome",
    ),
)
def test_provider_attempt_rejects_missing_required_fields(field_name: str) -> None:
    fields = _attempt_fields()
    fields.pop(field_name)

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


def test_provider_attempt_accepts_yaml_shaped_ref_strings() -> None:
    attempt = ProviderAttempt(**_attempt_fields())

    assert attempt.provider_attempt_id.value == "provider-attempt.1"
    assert attempt.input_package_ref.value == "exec.ticket.backend.1"
    assert attempt.seat_ref.value == "seat.worker.backend"
    assert attempt.raw_output_ref == ProviderArtifactRef(value="artifact.raw.1")
    assert attempt.parsed_output_ref == ProviderArtifactRef(value="artifact.parsed.1")


def test_primary_provider_output_is_explicitly_non_fallback() -> None:
    attempt = ProviderAttempt(**_attempt_fields())

    assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
    assert attempt.fallback_kind is None


def test_fallback_outcome_requires_typed_fallback_kind() -> None:
    fields = _attempt_fields()
    fields["outcome"] = ProviderAttemptOutcome.FALLBACK_ARTIFACT

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


def test_fallback_outcome_accepts_typed_fallback_kind() -> None:
    fields = _attempt_fields()
    fields["outcome"] = ProviderAttemptOutcome.FALLBACK_ARTIFACT
    fields["fallback_kind"] = FallbackKind.TOOLING_PREFLIGHT

    attempt = ProviderAttempt(**fields)

    assert attempt.outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT
    assert attempt.fallback_kind is FallbackKind.TOOLING_PREFLIGHT


def test_primary_outcome_rejects_fallback_kind() -> None:
    fields = _attempt_fields()
    fields["fallback_kind"] = FallbackKind.TOOLING_PREFLIGHT

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


@pytest.mark.parametrize("field_name", ("started_at", "finished_at"))
def test_provider_attempt_rejects_naive_timestamps(field_name: str) -> None:
    fields = _attempt_fields()
    fields[field_name] = fields[field_name].replace(tzinfo=None)

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


def test_provider_attempt_rejects_finished_at_before_started_at() -> None:
    fields = _attempt_fields()
    fields["finished_at"] = datetime(2026, 5, 18, 8, 59, tzinfo=UTC)

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


@pytest.mark.parametrize("missing_field", ("raw_output_ref", "parsed_output_ref"))
def test_succeeded_attempt_requires_output_refs(missing_field: str) -> None:
    fields = _attempt_fields()
    fields.pop(missing_field)

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


def test_succeeded_attempt_rejects_failure_kind() -> None:
    fields = _attempt_fields()
    fields["failure_kind"] = "transport_error"

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


@pytest.mark.parametrize("failure_kind", (None, "", "   "))
def test_failed_attempt_requires_non_empty_failure_kind(
    failure_kind: str | None,
) -> None:
    fields = _attempt_fields()
    fields["status"] = ProviderAttemptStatus.FAILED
    fields.pop("raw_output_ref")
    fields.pop("parsed_output_ref")
    fields["failure_kind"] = failure_kind

    with pytest.raises(ValidationError):
        ProviderAttempt(**fields)


def test_provider_attempt_rejects_unknown_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderAttempt(
            **_attempt_fields(),
            unexpected="not allowed",
        )


def test_provider_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        ProviderRequest(
            execution_package_ref="exec.ticket.backend.1",
            seat_ref="seat.worker.backend",
            model_execution_profile=_model_execution_profile(),
            prompt="   ",
        )


def test_fake_provider_transport_builds_succeeded_attempt_from_request() -> None:
    request = ProviderRequest(
        execution_package_ref="exec.ticket.backend.1",
        seat_ref="seat.worker.backend",
        model_execution_profile=_model_execution_profile(),
        prompt="Implement backend API",
    )
    transport = FakeProviderTransport(
        response=ProviderResponse(
            raw_output_ref="artifact.raw.1",
            parsed_output_ref="artifact.parsed.1",
            summary="Backend API implementation plan",
        ),
        attempt_id="provider-attempt.42",
        started_at=_started_at(),
        finished_at=_finished_at(),
    )

    attempt = transport.invoke(request)

    assert attempt.provider_attempt_id.value == "provider-attempt.42"
    assert attempt.provider == "anthropic"
    assert attempt.model == "claude-opus-4-7"
    assert attempt.reasoning_effort == "medium"
    assert attempt.input_package_ref.value == "exec.ticket.backend.1"
    assert attempt.seat_ref.value == "seat.worker.backend"
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
    assert attempt.fallback_kind is None
    assert attempt.started_at == _started_at()
    assert attempt.finished_at == _finished_at()
    assert attempt.raw_output_ref == ProviderArtifactRef(value="artifact.raw.1")
    assert attempt.parsed_output_ref == ProviderArtifactRef(value="artifact.parsed.1")
    assert attempt.failure_kind is None
