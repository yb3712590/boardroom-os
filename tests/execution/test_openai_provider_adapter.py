from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.openai_adapter import (
    FileProviderOutputStore,
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
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_fields


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


class _EmptyChatCompletionMessage:
    content = None


class _ChatCompletionChoice:
    message = _ChatCompletionMessage()


class _EmptyChatCompletionChoice:
    message = _EmptyChatCompletionMessage()


class _ChatCompletionResponse:
    id = "chatcmpl_unit_456"
    choices = (_ChatCompletionChoice(),)


class _EmptyChatCompletionResponse:
    id = "chatcmpl_empty_789"
    output_text = None
    choices = (_EmptyChatCompletionChoice(),)


class _ChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _ChatCompletionResponse:
        self.calls.append(kwargs)
        return _ChatCompletionResponse()


class _EmptyChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _EmptyChatCompletionResponse:
        self.calls.append(kwargs)
        return _EmptyChatCompletionResponse()


class _Chat:
    def __init__(self) -> None:
        self.completions = _ChatCompletions()


class _EmptyChat:
    def __init__(self) -> None:
        self.completions = _EmptyChatCompletions()


class _ResponsesFailChatSucceedsClient:
    def __init__(self) -> None:
        self.responses = _FailingResponses()
        self.chat = _Chat()


class _ResponsesFailChatEmptyClient:
    def __init__(self) -> None:
        self.responses = _FailingResponses()
        self.chat = _EmptyChat()


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
        **baseline_role_prompt_hook_fields(),
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
                "BOARDROOM_OPENAI_API_PROTOCOL=responses",
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
    assert settings.api_protocol == "responses"
    assert settings.reasoning_effort == "high"
    assert settings.text_verbosity == "low"
    assert settings.max_output_tokens == 256
    assert settings.timeout_seconds == 30
    assert settings.max_retries == 0
    assert settings.system_instructions == "Return a short audit summary."
    assert "sk-test-secret" not in repr(settings)
    assert "sk-test-secret" not in str(settings.model_dump())


def test_openai_provider_settings_fail_closed_without_required_deployment_config(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text("OPENAI_API_KEY=sk-test-secret\n", encoding="utf-8")

    with pytest.raises(
        OpenAIProviderConfigError,
        match="OPENAI_BASE_URL|BOARDROOM_OPENAI_MODEL|BOARDROOM_OPENAI_API_PROTOCOL",
    ):
        OpenAIProviderSettings.from_env_file(env_file)


def test_openai_provider_settings_loads_first_available_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "OPENAI_API_KEY=sk-test-secret",
                "OPENAI_BASE_URL=https://api.example.invalid/v1",
                "BOARDROOM_OPENAI_MODEL=gpt-5.4",
                "BOARDROOM_OPENAI_API_PROTOCOL=chat_completions",
            )
        ),
        encoding="utf-8",
    )

    settings = OpenAIProviderSettings.from_env_files(
        (tmp_path / ".env.test", env_file),
    )

    assert settings.base_url == "https://api.example.invalid/v1"
    assert settings.model == "gpt-5.4"
    assert settings.api_protocol == "chat_completions"


def test_openai_provider_settings_fail_closed_without_api_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "\n".join(
            (
                "OPENAI_BASE_URL=https://api.truerealbill.com/v1",
                "BOARDROOM_OPENAI_MODEL=gpt-5.5",
                "BOARDROOM_OPENAI_API_PROTOCOL=responses",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(OpenAIProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIProviderSettings.from_env_file(env_file)


def test_openai_provider_transport_invokes_responses_api_and_materializes_artifacts(
    tmp_path: Path,
) -> None:
    client = _Client()
    artifact_store = FileProviderOutputStore(root=tmp_path / "provider-artifacts")
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="responses",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
        artifact_store=artifact_store,
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
    assert attempt.raw_output_ref is not None
    assert attempt.parsed_output_ref is not None
    assert attempt.raw_output_ref.value.startswith("provider-artifact.openai.raw.resp_unit_123.")
    assert attempt.parsed_output_ref.value.startswith(
        "provider-artifact.openai.parsed.resp_unit_123."
    )
    assert "implemented tiny backend" in artifact_store.read_text(attempt.raw_output_ref)
    assert artifact_store.read_text(attempt.parsed_output_ref) == "implemented tiny backend"
    assert (
        artifact_store.get(attempt.raw_output_ref).content_hash.value
        == attempt.raw_output_ref.value.rsplit(".", 1)[-1]
    )
    assert (
        artifact_store.get(attempt.parsed_output_ref).content_hash.value
        == attempt.parsed_output_ref.value.rsplit(".", 1)[-1]
    )


def test_provider_output_store_requires_exact_hash_suffix(tmp_path: Path) -> None:
    artifact_store = FileProviderOutputStore(root=tmp_path / "provider-artifacts")
    artifact = artifact_store.write_text(
        response_id="resp_unit_exact_hash",
        artifact_kind="raw",
        text="provider output content",
    )
    tampered_ref = ProviderArtifactRef(
        value=(
            "provider-artifact.openai.raw."
            f"resp_{artifact.content_hash.value}."
            f"{'0' * 64}"
        )
    )
    artifact.path.replace(artifact_store._path_for_ref(tampered_ref))

    with pytest.raises(OpenAIProviderConfigError, match="hash does not match ref"):
        artifact_store.get(tampered_ref)


def test_openai_provider_transport_records_failed_attempt_without_secret_leak() -> None:
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit-secret",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="responses",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=_FailingClient(),
        artifact_store=FileProviderOutputStore(root=Path(".pytest-tmp-openai-failed-artifacts")),
    )

    attempt = transport.invoke(_request())

    assert attempt.status is ProviderAttemptStatus.FAILED
    assert attempt.raw_output_ref is None
    assert attempt.parsed_output_ref is None
    assert attempt.failure_kind == "provider_error.RuntimeError"
    assert "sk-unit-secret" not in attempt.model_dump_json()
    assert "secret-like details" not in attempt.model_dump_json()


def test_openai_provider_transport_fails_closed_when_explicit_responses_api_is_blocked(
    tmp_path: Path,
) -> None:
    client = _ResponsesFailChatSucceedsClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="responses",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
        artifact_store=FileProviderOutputStore(root=tmp_path / "provider-artifacts"),
    )

    attempt = transport.invoke(_request(_profile(reasoning_effort="xhigh")))

    assert attempt.status is ProviderAttemptStatus.FAILED
    assert client.chat.completions.calls == []


def test_openai_provider_transport_uses_explicit_chat_completions_protocol(
    tmp_path: Path,
) -> None:
    client = _ResponsesFailChatSucceedsClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
        artifact_store=FileProviderOutputStore(root=tmp_path / "provider-artifacts"),
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
    assert attempt.provider_attempt_id.value.startswith("provider-attempt.openai.chatcmpl_unit_456")
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
    assert attempt.reasoning_effort == "xhigh"
    assert attempt.raw_output_ref is not None
    assert attempt.parsed_output_ref is not None


def test_openai_provider_transport_passes_json_object_response_format(
    tmp_path: Path,
) -> None:
    client = _ResponsesFailChatSucceedsClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            response_format="json_object",
        ),
        client=client,
        artifact_store=FileProviderOutputStore(root=tmp_path / "provider-artifacts"),
    )

    attempt = transport.invoke(_request())

    assert client.chat.completions.calls[0]["response_format"] == {
        "type": "json_object",
    }
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED


def test_openai_provider_transport_passes_system_instructions_to_chat_completions(
    tmp_path: Path,
) -> None:
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
        artifact_store=FileProviderOutputStore(root=tmp_path / "provider-artifacts"),
    )

    attempt = transport.invoke(_request())

    assert client.chat.completions.calls[0]["messages"] == [
        {"role": "system", "content": "Return a short audit summary."},
        {"role": "user", "content": "Implement the tiny provider attempt."},
    ]
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED


def test_openai_provider_transport_rejects_empty_chat_completion_content(
    tmp_path: Path,
) -> None:
    client = _ResponsesFailChatEmptyClient()
    transport = OpenAIProviderTransport(
        settings=OpenAIProviderSettings(
            api_key="sk-unit",
            base_url="https://api.truerealbill.com/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
        ),
        client=client,
        artifact_store=FileProviderOutputStore(root=tmp_path / "provider-artifacts"),
    )

    attempt = transport.invoke(_request())

    assert attempt.status is ProviderAttemptStatus.FAILED
    assert attempt.raw_output_ref is None
    assert attempt.parsed_output_ref is None
    assert attempt.failure_kind == "provider_error.OpenAIProviderConfigError"
    assert not list((tmp_path / "provider-artifacts").glob("*"))
