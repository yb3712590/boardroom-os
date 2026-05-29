from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.openai_adapter import (
    OpenAIProviderConfigError,
    OpenAIProviderSettings,
    OpenAIProviderTransport,
)
from boardroom_os.providers.adapter import ProviderRequest
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


def test_openai_provider_adapter_imports_in_fresh_interpreter() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from boardroom_os.providers.openai_adapter import OpenAIProviderSettings; "
            "print(OpenAIProviderSettings.__name__)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OpenAIProviderSettings"


class _Response:
    id = "resp_unit_123"
    output_text = "implemented tiny backend"


class _Responses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _Response:
        self.calls.append(kwargs)
        return _Response()


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


class _FailingResponses:
    def create(self, **kwargs: object) -> object:
        raise RuntimeError("secret-like details must not be copied")


class _FailingClient:
    responses = _FailingResponses()


class _ChatCompletionMessage:
    content = "implemented tiny fallback-compatible output"


class _ChatCompletionChoice:
    message = _ChatCompletionMessage()


class _ChatCompletionResponse:
    id = "chatcmpl_unit_456"
    choices = (_ChatCompletionChoice(),)


class _ChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _ChatCompletionResponse:
        self.calls.append(kwargs)
        return _ChatCompletionResponse()


class _Chat:
    def __init__(self) -> None:
        self.completions = _ChatCompletions()


class _ResponsesFailChatSucceedsClient:
    def __init__(self) -> None:
        self.responses = _FailingResponses()
        self.chat = _Chat()


class _CountingFailingResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise RuntimeError("responses endpoint unavailable")


class _CountingResponsesFailChatSucceedsClient:
    def __init__(self) -> None:
        self.responses = _CountingFailingResponses()
        self.chat = _Chat()


def _profile(
    *,
    provider: str = "openai-compatible",
    model: str = "gpt-5.5",
    reasoning_effort: str = "high",
) -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model.real.worker",
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        context_window=200000,
        temperature=0.2,
        tool_permissions=("provider.invoke",),
        fallback_policy_ref="fallback.tiny.record-failure",
    )


def _request(profile: ModelExecutionProfile | None = None) -> ProviderRequest:
    return ProviderRequest(
        execution_package_ref=ExecutionPackageRef(value="exec.ticket.real-provider"),
        seat_ref=AgentSeatRef(value="seat.worker.real-provider"),
        model_execution_profile=profile or _profile(),
        prompt="Implement the tiny provider attempt.",
    )


def test_openai_provider_settings_loads_local_env_without_exposing_key(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "\n".join(
            (
                "OPENAI_API_KEY=sk-test-secret",
                "OPENAI_BASE_URL=https://api.truerealbill.com/v1",
                "BOARDROOM_OPENAI_MODEL=gpt-5.5",
                "BOARDROOM_OPENAI_REASONING_EFFORT=high",
                "BOARDROOM_OPENAI_TEXT_VERBOSITY=low",
                "BOARDROOM_OPENAI_MAX_OUTPUT_TOKENS=256",
                "BOARDROOM_OPENAI_TIMEOUT_SECONDS=30",
                "BOARDROOM_OPENAI_MAX_RETRIES=0",
                "BOARDROOM_OPENAI_SYSTEM_INSTRUCTIONS=Return a short audit summary.",
            )
        ),
        encoding="utf-8",
    )

    settings = OpenAIProviderSettings.from_env_file(env_file)

    assert settings.base_url == "https://api.truerealbill.com/v1"
    assert settings.model == "gpt-5.5"
    assert settings.reasoning_effort == "high"
    assert settings.text_verbosity == "low"
    assert settings.max_output_tokens == 256
    assert settings.timeout_seconds == 30
    assert settings.max_retries == 0
    assert settings.system_instructions == "Return a short audit summary."
    assert "sk-test-secret" not in repr(settings)
    assert "sk-test-secret" not in str(settings.model_dump())


def test_openai_provider_settings_fail_closed_without_api_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "\n".join(
            (
                "OPENAI_BASE_URL=https://api.truerealbill.com/v1",
                "BOARDROOM_OPENAI_MODEL=gpt-5.5",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(OpenAIProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIProviderSettings.from_env_file(env_file)


def test_openai_provider_transport_invokes_responses_api_with_reasoning() -> None:
    client = _Client()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
    )
    request = _request(_profile(reasoning_effort="high"))

    attempt = transport.invoke(request)

    assert client.responses.calls == [
        {
            "model": "gpt-5.5",
            "input": request.prompt,
            "instructions": None,
            "reasoning": {"effort": "high"},
            "text": {"verbosity": "low"},
            "max_output_tokens": 1024,
            "timeout": 60.0,
        }
    ]
    assert attempt.provider_attempt_id.value == "provider-attempt.openai.resp_unit_123"
    assert attempt.provider == "openai-compatible"
    assert attempt.model == "gpt-5.5"
    assert attempt.reasoning_effort == "high"
    assert attempt.input_package_ref == request.execution_package_ref
    assert attempt.seat_ref == request.seat_ref
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
    assert attempt.raw_output_ref == ProviderArtifactRef(value="provider-artifact.openai.raw.resp_unit_123")
    assert attempt.parsed_output_ref == ProviderArtifactRef(value="provider-artifact.openai.text.resp_unit_123")


def test_openai_provider_transport_records_failed_attempt_without_secret_leak() -> None:
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit-secret",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=_FailingClient(),
    )

    attempt = transport.invoke(_request())

    assert attempt.status is ProviderAttemptStatus.FAILED
    assert attempt.raw_output_ref is None
    assert attempt.parsed_output_ref is None
    assert attempt.failure_kind == "provider_error.RuntimeError"
    assert "sk-unit-secret" not in attempt.model_dump_json()
    assert "secret-like details" not in attempt.model_dump_json()


def test_openai_provider_transport_uses_chat_completions_when_responses_api_is_blocked() -> None:
    client = _ResponsesFailChatSucceedsClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
    )
    request = _request(_profile(reasoning_effort="xhigh"))

    attempt = transport.invoke(request)

    assert client.chat.completions.calls == [
        {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": request.prompt}],
            "reasoning_effort": "xhigh",
            "max_completion_tokens": 1024,
            "verbosity": "low",
            "timeout": 60.0,
        }
    ]
    assert attempt.provider_attempt_id.value == "provider-attempt.openai.chatcmpl_unit_456"
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
    assert attempt.reasoning_effort == "xhigh"
    assert attempt.raw_output_ref == ProviderArtifactRef(value="provider-artifact.openai.raw.chatcmpl_unit_456")
    assert attempt.parsed_output_ref == ProviderArtifactRef(value="provider-artifact.openai.text.chatcmpl_unit_456")


def test_openai_provider_transport_reuses_chat_protocol_after_responses_api_is_blocked() -> None:
    client = _CountingResponsesFailChatSucceedsClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
    )

    first_attempt = transport.invoke(_request())
    second_attempt = transport.invoke(_request())

    assert first_attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert second_attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert len(client.responses.calls) == 1
    assert len(client.chat.completions.calls) == 2


def test_openai_provider_transport_passes_system_instructions_to_chat_completions() -> None:
    client = _ResponsesFailChatSucceedsClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            system_instructions="Return a short audit summary.",
        ),
        client=client,
    )

    attempt = transport.invoke(_request())

    assert client.chat.completions.calls[0]["messages"] == [
        {"role": "system", "content": "Return a short audit summary."},
        {"role": "user", "content": "Implement the tiny provider attempt."},
    ]
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED
