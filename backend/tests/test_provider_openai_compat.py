from __future__ import annotations

import json
import time
from types import SimpleNamespace
import threading
from datetime import datetime

import httpx
import pytest

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.provider_openai_compat import (
    OpenAICompatProviderAuthError,
    OpenAICompatProviderBadResponseError,
    OpenAICompatProviderConfig,
    OpenAICompatProviderType,
    OpenAICompatProviderRateLimitedError,
    OpenAICompatProviderUnavailableError,
    invoke_openai_compat_response,
    list_openai_compat_models,
    probe_openai_compat_connectivity,
)


class _FakeResponseStream:
    def __init__(self, *, events: list[object], final_response: object | None = None) -> None:
        self._events = events
        self._final_response = final_response
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    def __iter__(self):
        return iter(self._events)

    def close(self) -> None:
        self.closed = True

    def get_final_response(self):
        return self._final_response


class _FakeResponses:
    def __init__(self, create_factory) -> None:
        self.create_factory = create_factory
        self.create_calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.create_calls.append(dict(kwargs))
        return self.create_factory(**kwargs)


class _FakeOpenAIClient:
    def __init__(self, create_factory) -> None:
        self.responses = _FakeResponses(create_factory)


def _rendered_payload() -> RenderedExecutionPayload:
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id="ctx_001",
            compile_id="cmp_001",
            compile_request_id="creq_001",
            ticket_id="tkt_001",
            workflow_id="wf_001",
            node_id="node_001",
            compiler_version="context-compiler.min.v1",
            model_profile="boardroom_os.runtime.min",
            render_target="json_messages_v1",
            rendered_at=datetime.fromisoformat("2026-04-01T12:00:00+08:00"),
        ),
        messages=[
            RenderedExecutionMessage(
                role="system",
                channel="SYSTEM_CONTROLS",
                content_type="JSON",
                content_payload={"rules": ["stay structured"]},
            ),
            RenderedExecutionMessage(
                role="user",
                channel="TASK_DEFINITION",
                content_type="JSON",
                content_payload={"task": "Return JSON only."},
            ),
        ],
        summary=RenderedExecutionPayloadSummary(
            total_message_count=2,
            control_message_count=2,
            data_message_count=0,
            retrieval_message_count=0,
            degraded_data_message_count=0,
            reference_message_count=0,
        ),
    )


def _config() -> OpenAICompatProviderConfig:
    return OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        schema_name="ui_milestone_review_v1",
        schema_body={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        strict=True,
        provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
    )


def test_invoke_openai_compat_response_uses_official_sdk_create_stream_with_strict_json_schema() -> None:
    client: _FakeOpenAIClient | None = None

    def _create_factory(**kwargs):
        return _FakeResponseStream(
            events=[
                SimpleNamespace(type="response.output_text.delta", delta='{"summary"'),
                SimpleNamespace(type="response.output_text.delta", delta=':"SDK stream ok"}'),
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(id="resp_sdk_stream"),
                ),
            ],
            final_response=SimpleNamespace(id="resp_sdk_stream", output_text='{"summary":"SDK stream ok"}'),
        )

    def _client_factory(config: OpenAICompatProviderConfig):
        nonlocal client
        client = _FakeOpenAIClient(_create_factory)
        return client

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        client_factory=_client_factory,
    )

    assert result.response_id == "resp_sdk_stream"
    assert result.output_text == '{"summary":"SDK stream ok"}'
    assert client is not None
    request = client.responses.create_calls[0]
    assert request["model"] == "gpt-5.3-codex"
    assert request["text"] == {
        "format": {
            "type": "json_schema",
            "name": "ui_milestone_review_v1",
            "schema": {
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
            "strict": True,
        }
    }
    assert request["stream"] is True


def test_invoke_openai_compat_response_uses_official_sdk_create_non_streaming_when_configured() -> None:
    client: _FakeOpenAIClient | None = None

    def _create_factory(**kwargs):
        return SimpleNamespace(
            id="resp_non_stream_sdk",
            output_text='{"summary":"non-stream ok"}',
        )

    def _client_factory(config: OpenAICompatProviderConfig):
        nonlocal client
        client = _FakeOpenAIClient(_create_factory)
        return client

    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
    )

    result = invoke_openai_compat_response(
        config,
        _rendered_payload(),
        client_factory=_client_factory,
    )

    assert result.response_id == "resp_non_stream_sdk"
    assert result.output_payload == {"summary": "non-stream ok"}
    assert client is not None
    request = client.responses.create_calls[0]
    assert request["stream"] is False


def test_invoke_openai_compat_response_maps_sdk_stream_response_failed_event() -> None:
    def _create_factory(**kwargs):
        return _FakeResponseStream(
            events=[
                SimpleNamespace(
                    type="response.failed",
                    response=SimpleNamespace(
                        id="resp_failed",
                        error=SimpleNamespace(type="server_error", code="upstream_error", message="boom"),
                    ),
                )
            ],
        )

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            client_factory=lambda config: _FakeOpenAIClient(_create_factory),
        )

    assert exc_info.value.failure_kind == "UPSTREAM_UNAVAILABLE"
    assert exc_info.value.failure_detail["provider_response_id"] == "resp_failed"
    assert exc_info.value.failure_detail["response_error_type"] == "server_error"
    assert exc_info.value.failure_detail["response_error_code"] == "upstream_error"


def test_invoke_openai_compat_response_preserves_multiple_json_objects_from_stream_text() -> None:
    def _create_factory(**kwargs):
        return _FakeResponseStream(
            events=[
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(
                        id="resp_json_sequence",
                        output_text='{"summary":"first"}{"summary":"second"}',
                    ),
                ),
            ],
        )

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        client_factory=lambda config: _FakeOpenAIClient(_create_factory),
    )

    assert result.output_payload == {"summary": "first"}
    assert result.output_payloads == (
        {"summary": "first"},
        {"summary": "second"},
    )


def test_invoke_openai_compat_response_includes_reasoning_effort_when_configured() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        reasoning_effort="xhigh",
    )

    def _create_factory(**kwargs):
        assert kwargs["reasoning"] == {"effort": "xhigh"}
        assert kwargs["stream"] is True
        return _FakeResponseStream(
            events=[
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(id="resp_reasoning", output_text='{"summary":"Provider completed."}'),
                )
            ],
        )

    result = invoke_openai_compat_response(
        config,
        _rendered_payload(),
        client_factory=lambda config: _FakeOpenAIClient(_create_factory),
    )

    assert result.response_id == "resp_reasoning"


def test_invoke_openai_compat_response_returns_text_from_responses_message_payload() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
    )

    def _create_factory(**kwargs):
        assert kwargs["stream"] is False
        assert kwargs["model"] == "gpt-5.3-codex"
        assert isinstance(kwargs["input"], list)
        return SimpleNamespace(
            id="resp_001",
            output_text='{"summary":"Provider completed.","recommended_option_id":"option_a","options":[]}',
        )

    result = invoke_openai_compat_response(
        config,
        _rendered_payload(),
        client_factory=lambda config: _FakeOpenAIClient(_create_factory),
    )

    assert result.response_id == "resp_001"
    assert result.output_text.startswith('{"summary":"Provider completed."')


def test_invoke_openai_compat_response_maps_429_to_rate_limited() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "7"},
            json={"error": {"message": "quota exhausted"}},
        )

    with pytest.raises(OpenAICompatProviderRateLimitedError) as exc_info:
        invoke_openai_compat_response(
            config,
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "PROVIDER_RATE_LIMITED"
    assert exc_info.value.failure_detail["provider_status_code"] == 429
    assert exc_info.value.failure_detail["retry_after_sec"] == 7.0


def test_invoke_openai_compat_response_maps_timeout_to_unavailable() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "UPSTREAM_UNAVAILABLE"
    assert exc_info.value.failure_detail["provider_transport_error"] == "APITimeoutError"


def test_invoke_openai_compat_response_maps_auth_failures() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(OpenAICompatProviderAuthError) as exc_info:
        invoke_openai_compat_response(
            config,
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "PROVIDER_AUTH_FAILED"
    assert exc_info.value.failure_detail["provider_status_code"] == 401


def test_invoke_openai_compat_response_rejects_bad_json_payloads() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
    )

    def _create_factory(**kwargs):
        return SimpleNamespace(id="resp_bad", output=[])

    with pytest.raises(OpenAICompatProviderBadResponseError) as exc_info:
        invoke_openai_compat_response(
            config,
            _rendered_payload(),
            client_factory=lambda config: _FakeOpenAIClient(_create_factory),
        )

    assert exc_info.value.failure_kind == "PROVIDER_BAD_RESPONSE"
    assert exc_info.value.failure_detail["provider_response_id"] == "resp_bad"


def test_invoke_openai_compat_response_uses_streaming_responses_by_default() -> None:
    client: _FakeOpenAIClient | None = None

    def _create_factory(**kwargs):
        assert kwargs["stream"] is True
        assert kwargs["instructions"].startswith("[SYSTEM_CONTROLS/JSON]\n")
        assert '"rules"' in kwargs["instructions"]
        assert '"content_type"' not in kwargs["instructions"]
        assert kwargs["input"] == [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": '[TASK_DEFINITION/JSON]\n{\n  "task": "Return JSON only."\n}',
                    }
                ],
            }
        ]
        return _FakeResponseStream(
            events=[
                SimpleNamespace(type="response.output_text.delta", delta='{"ok"'),
                SimpleNamespace(type="response.output_text.delta", delta=':true}'),
                SimpleNamespace(type="response.completed", response=SimpleNamespace(id="resp_stream_001")),
            ]
        )

    def _client_factory(config):
        nonlocal client
        client = _FakeOpenAIClient(_create_factory)
        return client

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        client_factory=_client_factory,
    )

    assert client is not None
    assert len(client.responses.create_calls) == 1
    assert result.response_id == "resp_stream_001"
    assert result.output_text == '{"ok":true}'


def test_invoke_openai_compat_response_emits_streaming_audit_callbacks() -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    def _create_factory(**kwargs):
        return _FakeResponseStream(
            events=[
                SimpleNamespace(type="response.output_text.delta", delta='{"ok"'),
                SimpleNamespace(type="response.output_text.delta", delta=':true}'),
                SimpleNamespace(type="response.completed", response=SimpleNamespace(id="resp_stream_observed")),
            ]
        )

    invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        client_factory=lambda config: _FakeOpenAIClient(_create_factory),
        audit_observer=lambda event_type, payload: observed.append((event_type, dict(payload))),
    )

    assert [item[0] for item in observed] == [
        "request_started",
        "first_token_received",
        "response_completed",
    ]
    assert observed[0][1]["streaming"] is True
    assert observed[0][1]["provider_type"] == OpenAICompatProviderType.RESPONSES_STREAM.value
    assert observed[1][1]["provider_response_id"] is None
    assert observed[2][1]["provider_response_id"] == "resp_stream_observed"


def test_invoke_openai_compat_response_returns_after_response_completed_without_done_sentinel() -> None:
    def _create_factory(**kwargs):
        class _HangingStream(_FakeResponseStream):
            def __iter__(self):
                yield SimpleNamespace(type="response.output_text.delta", delta='{"ok":true}')
                yield SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(id="resp_stream_completed_only"),
                )
                raise httpx.ReadTimeout("stream left open after response.completed")

        return _HangingStream(events=[])

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        client_factory=lambda config: _FakeOpenAIClient(_create_factory),
    )

    assert result.response_id == "resp_stream_completed_only"
    assert result.output_text == '{"ok":true}'


def test_invoke_openai_compat_response_enforces_total_timeout_after_first_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NeverCompletesStream(_FakeResponseStream):
        def __iter__(self):
            yield SimpleNamespace(type="response.output_text.delta", delta='{"ok":')
            while True:
                time.sleep(0.01)

    monotonic_values = iter([0.0, 0.0, 0.5, 2.0])

    def _fake_monotonic() -> float:
        value = next(monotonic_values)
        return value

    monkeypatch.setattr("app.core.provider_openai_compat.time.monotonic", _fake_monotonic)

    def _create_factory(**kwargs):
        return _NeverCompletesStream(events=[])

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            OpenAICompatProviderConfig(
                base_url="https://api-vip.codex-for.me/v1",
                api_key="test-key",
                model="gpt-5.3-codex",
                timeout_sec=30.0,
                first_token_timeout_sec=300.0,
                stream_idle_timeout_sec=300.0,
                request_total_timeout_sec=1.0,
                provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
            ),
            _rendered_payload(),
            client_factory=lambda config: _FakeOpenAIClient(_create_factory),
        )

    assert exc_info.value.failure_kind == "REQUEST_TOTAL_TIMEOUT"
    assert exc_info.value.failure_detail["timeout_phase"] == "request_total"


def test_invoke_openai_compat_response_raises_first_token_timeout_before_any_stream_output() -> None:
    def _create_factory(**kwargs):
        class _SilentStream(_FakeResponseStream):
            def __iter__(self):
                raise httpx.ReadTimeout("stream never produced a first token")

        return _SilentStream(events=[])

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            client_factory=lambda config: _FakeOpenAIClient(_create_factory),
        )

    assert exc_info.value.failure_kind == "FIRST_TOKEN_TIMEOUT"


def test_invoke_openai_compat_response_emits_failure_audit_callback_for_first_token_timeout() -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    def _create_factory(**kwargs):
        class _SilentStream(_FakeResponseStream):
            def __iter__(self):
                raise httpx.ReadTimeout("stream never produced a first token")

        return _SilentStream(events=[])

    with pytest.raises(OpenAICompatProviderUnavailableError):
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            client_factory=lambda config: _FakeOpenAIClient(_create_factory),
            audit_observer=lambda event_type, payload: observed.append((event_type, dict(payload))),
        )

    assert [item[0] for item in observed] == [
        "request_started",
        "request_failed",
    ]
    assert observed[-1][1]["failure_kind"] == "FIRST_TOKEN_TIMEOUT"
    assert observed[-1][1]["timeout_phase"] == "first_token"


def test_invoke_openai_compat_response_raises_stream_idle_timeout_after_first_token() -> None:
    def _create_factory(**kwargs):
        class _IdleAfterFirstTokenStream(_FakeResponseStream):
            def __iter__(self):
                yield SimpleNamespace(type="response.output_text.delta", delta='{"ok":true')
                raise httpx.ReadTimeout("stream stalled after the first token")

        return _IdleAfterFirstTokenStream(events=[])

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            client_factory=lambda config: _FakeOpenAIClient(_create_factory),
        )

    assert exc_info.value.failure_kind == "STREAM_IDLE_TIMEOUT"


def test_connectivity_test_falls_back_to_non_streaming_responses_when_streaming_is_not_supported() -> None:
    call_stream_flags: list[bool] = []

    def _create_factory(**kwargs):
        call_stream_flags.append(bool(kwargs["stream"]))
        if kwargs["stream"] is True:
            error = OpenAICompatProviderBadResponseError(
                failure_kind="PROVIDER_BAD_RESPONSE",
                message="streaming not supported",
                failure_detail={"provider_status_code": 400},
            )
            raise error
        return SimpleNamespace(
            id="resp_non_stream_connectivity",
            output_text='{"status":"ok"}',
        )

    result = probe_openai_compat_connectivity(
        OpenAICompatProviderConfig(
            base_url="https://api-vip.codex-for.me/v1",
            api_key="test-key",
            model="gpt-5.3-codex",
            timeout_sec=30.0,
            provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
        ),
        client_factory=lambda config: _FakeOpenAIClient(_create_factory),
    )

    assert call_stream_flags == [True, False]
    assert result.ok is True
    assert result.provider_type == OpenAICompatProviderType.RESPONSES_NON_STREAM
    assert result.response_id == "resp_non_stream_connectivity"


def test_list_openai_compat_models_returns_sorted_model_ids() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api-vip.codex-for.me/v1/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "gpt-4.1"},
                    {"id": "gpt-5.3-codex"},
                    {"id": "gpt-4.1"},
                ]
            },
        )

    result = list_openai_compat_models(
        OpenAICompatProviderConfig(
            base_url="https://api-vip.codex-for.me/v1",
            api_key="test-key",
            model="gpt-5.3-codex",
            timeout_sec=30.0,
            provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
        ),
        transport=httpx.MockTransport(_handler),
    )

    assert result == ["gpt-4.1", "gpt-5.3-codex"]
