from __future__ import annotations

import json
import time
from types import SimpleNamespace
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
    load_openai_compat_result_payload,
    probe_openai_compat_connectivity,
    resolve_openai_compat_result_payload,
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


def _sse_response(*events: dict[str, object] | str, status_code: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    lines: list[str] = []
    for event in events:
        if isinstance(event, str):
            lines.append(f"data: {event}\n")
        else:
            lines.append(f"data: {json.dumps(event)}\n")
    return httpx.Response(
        status_code,
        headers={"content-type": "text/event-stream", **(headers or {})},
        content="\n".join(lines).encode("utf-8"),
    )


def _stream_transport(*events: dict[str, object] | str) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL("https://api-vip.codex-for.me/v1/responses")
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["accept"] == "text/event-stream"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "gpt-5.3-codex"
        assert payload["stream"] is True
        return _sse_response(*events)

    return httpx.MockTransport(_handler)


class _FailingSSEStream(httpx.SyncByteStream):
    def __init__(self, *events: dict[str, object], error: Exception) -> None:
        self.events = events
        self.error = error

    def __iter__(self):
        for event in self.events:
            yield f"data: {json.dumps(event)}\n\n".encode("utf-8")
        raise self.error


def test_invoke_openai_compat_response_uses_streaming_text_request_without_provider_json_schema() -> None:
    observed_payloads: list[dict[str, object]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        observed_payloads.append(payload)
        return _sse_response(
            {"type": "response.output_text.delta", "delta": '{"summary"'},
            {"type": "response.output_text.delta", "delta": ':"SSE stream ok"}'},
            {"type": "response.completed", "response": {"id": "resp_sse_stream"}},
        )

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert result.response_id == "resp_sse_stream"
    assert result.output_text == '{"summary":"SSE stream ok"}'
    request = observed_payloads[0]
    assert request["model"] == "gpt-5.3-codex"
    assert "text" not in request
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
    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=_stream_transport(
                {
                    "type": "response.failed",
                    "response": {
                        "id": "resp_failed",
                        "error": {"type": "server_error", "code": "upstream_error", "message": "boom"},
                    },
                }
            ),
        )

    assert exc_info.value.failure_kind == "UPSTREAM_UNAVAILABLE"
    assert exc_info.value.failure_detail["provider_response_id"] == "resp_failed"
    assert exc_info.value.failure_detail["response_error_type"] == "server_error"
    assert exc_info.value.failure_detail["response_error_code"] == "upstream_error"


def test_invoke_openai_compat_response_preserves_multiple_json_objects_from_stream_text() -> None:
    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": '{"summary":"first"}'},
            {"type": "response.output_text.delta", "delta": '{"summary":"second"}'},
            {"type": "response.completed", "response": {"id": "resp_json_sequence"}},
        ),
    )

    assert result.output_payload == {"summary": "first"}
    assert result.selected_payload == {"summary": "first"}
    assert result.output_payloads == (
        {"summary": "first"},
        {"summary": "second"},
    )
    assert result.json_objects == (
        {"summary": "first"},
        {"summary": "second"},
    )
    assert result.raw_output_text == '{"summary":"first"}{"summary":"second"}'
    assert result.finish_state == "COMPLETED"


def test_invoke_openai_compat_response_deduplicates_duplicate_json_objects_from_stream_text() -> None:
    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": '{"summary":"same"}'},
            {"type": "response.output_text.delta", "delta": '{"summary":"same"}'},
            {"type": "response.completed", "response": {"id": "resp_duplicate_json_sequence"}},
        ),
    )

    assert result.json_objects == (
        {"summary": "same"},
    )
    assert result.output_payloads == (
        {"summary": "same"},
    )
    assert result.duplicate_json_object_count == 0
    assert result.selected_payload_index == 0


def test_load_openai_compat_result_payload_marks_malformed_json_sequence_as_retryable() -> None:
    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": '{"summary":"broken"'},
            {"type": "response.completed", "response": {"id": "resp_malformed_json_sequence"}},
        ),
    )

    with pytest.raises(OpenAICompatProviderBadResponseError) as exc_info:
        load_openai_compat_result_payload(result)

    assert exc_info.value.failure_kind == "PROVIDER_MALFORMED_JSON"
    assert exc_info.value.failure_detail["provider_response_id"] == "resp_malformed_json_sequence"


def test_load_openai_compat_result_payload_extracts_json_from_rich_text() -> None:
    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": 'Here is the result:\n```json\n{"summary":"rich text ok"}\n```'},
            {"type": "response.completed", "response": {"id": "resp_rich_text_json"}},
        ),
    )

    assert load_openai_compat_result_payload(result) == {"summary": "rich text ok"}
    assert result.repair_steps == ("extract_json_object_fragment",)


def test_resolve_openai_compat_result_payload_raises_schema_validation_failed_when_candidates_do_not_match() -> None:
    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": '{"summary":"ok"}'},
            {"type": "response.output_text.delta", "delta": '{"wrong":true}'},
            {"type": "response.completed", "response": {"id": "resp_schema_validation_failed"}},
        ),
    )

    with pytest.raises(OpenAICompatProviderBadResponseError) as exc_info:
        resolve_openai_compat_result_payload(
            result,
            payload_resolver=lambda payload: (_ for _ in ()).throw(ValueError(f"bad candidate: {sorted(payload.keys())}")),
        )

    assert exc_info.value.failure_kind == "SCHEMA_VALIDATION_FAILED"
    assert exc_info.value.failure_detail["json_candidate_count"] == 2


def test_invoke_openai_compat_response_includes_reasoning_effort_when_configured() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        reasoning_effort="xhigh",
    )
    observed_payloads: list[dict[str, object]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        observed_payloads.append(payload)
        return _sse_response(
            {"type": "response.output_text.delta", "delta": '{"summary":"Provider completed."}'},
            {"type": "response.completed", "response": {"id": "resp_reasoning"}},
        )

    result = invoke_openai_compat_response(
        config,
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert observed_payloads[0]["reasoning"] == {"effort": "xhigh"}
    assert observed_payloads[0]["stream"] is True
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

    assert exc_info.value.failure_kind == "FIRST_TOKEN_TIMEOUT"
    assert exc_info.value.failure_detail["provider_transport_error"] == "ReadTimeout"


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
    observed_payloads: list[dict[str, object]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        observed_payloads.append(payload)
        assert payload["instructions"].startswith("[SYSTEM_CONTROLS/JSON]\n")
        assert '"rules"' in payload["instructions"]
        assert '"content_type"' not in payload["instructions"]
        assert payload["input"] == [
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
        return _sse_response(
            {"type": "response.output_text.delta", "delta": '{"ok"'},
            {"type": "response.output_text.delta", "delta": ":true}"},
            {"type": "response.completed", "response": {"id": "resp_stream_001"}},
        )

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert len(observed_payloads) == 1
    assert result.response_id == "resp_stream_001"
    assert result.output_text == '{"ok":true}'
    assert result.events_summary["stream_transport"] == "httpx_sse"


def test_invoke_openai_compat_response_emits_streaming_audit_callbacks() -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": '{"ok"'},
            {"type": "response.output_text.delta", "delta": ":true}"},
            {"type": "response.completed", "response": {"id": "resp_stream_observed"}},
        ),
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
    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=_stream_transport(
            {"type": "response.output_text.delta", "delta": '{"ok":true}'},
            {"type": "response.completed", "response": {"id": "resp_stream_completed_only"}},
            {"type": "response.output_text.delta", "delta": "this must not be consumed"},
        ),
    )

    assert result.response_id == "resp_stream_completed_only"
    assert result.output_text == '{"ok":true}'


def test_invoke_openai_compat_response_enforces_request_total_timeout_for_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic_values = iter([0.0, 0.0, 0.5, 2.0])

    def _fake_monotonic() -> float:
        try:
            return next(monotonic_values)
        except StopIteration:
            return 2.0

    monkeypatch.setattr("app.core.provider_openai_compat.time.monotonic", _fake_monotonic)

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
            transport=_stream_transport(
                {"type": "response.output_text.delta", "delta": '{"ok":'},
                {"type": "response.output_text.delta", "delta": "true}"},
                {"type": "response.completed", "response": {"id": "resp_stream_long_running"}},
            ),
        )

    assert exc_info.value.failure_kind == "REQUEST_TOTAL_TIMEOUT"
    assert exc_info.value.failure_detail["timeout_phase"] == "request_total"


def test_invoke_openai_compat_response_raises_first_token_timeout_before_any_stream_output() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("stream never produced a first token", request=request)

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "FIRST_TOKEN_TIMEOUT"


def test_invoke_openai_compat_response_enforces_first_token_timeout_across_non_output_events() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_FailingSSEStream(
                {"type": "response.created", "response": {"id": "resp_created"}},
                {"type": "response.output_item.added", "item": {"id": "item_1"}},
                {"type": "response.content_part.added"},
                error=httpx.ReadTimeout("metadata only stream stalled", request=request),
            ),
        )

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "FIRST_TOKEN_TIMEOUT"


def test_invoke_openai_compat_response_emits_failure_audit_callback_for_first_token_timeout() -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("stream never produced a first token", request=request)

    with pytest.raises(OpenAICompatProviderUnavailableError):
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
            audit_observer=lambda event_type, payload: observed.append((event_type, dict(payload))),
        )

    assert [item[0] for item in observed] == [
        "request_started",
        "request_failed",
    ]
    assert observed[-1][1]["failure_kind"] == "FIRST_TOKEN_TIMEOUT"
    assert observed[-1][1]["timeout_phase"] == "first_token"


def test_invoke_openai_compat_response_raises_stream_idle_timeout_after_first_token() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_FailingSSEStream(
                {"type": "response.output_text.delta", "delta": '{"ok":true'},
                error=httpx.ReadTimeout("stream stalled after the first token", request=request),
            ),
        )

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "STREAM_IDLE_TIMEOUT"


def test_invoke_openai_compat_response_enforces_stream_idle_timeout_across_non_output_events() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_FailingSSEStream(
                {"type": "response.output_text.delta", "delta": '{"ok":'},
                {"type": "response.output_item.added", "item": {"id": "item_1"}},
                {"type": "response.content_part.added"},
                error=httpx.ReadTimeout("metadata only stream stalled after first token", request=request),
            ),
        )

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "STREAM_IDLE_TIMEOUT"


def test_invoke_openai_compat_response_maps_stream_http_429_to_rate_limited() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {"message": "quota exhausted"}})

    with pytest.raises(OpenAICompatProviderRateLimitedError) as exc_info:
        invoke_openai_compat_response(_config(), _rendered_payload(), transport=httpx.MockTransport(_handler))

    assert exc_info.value.failure_detail["provider_status_code"] == 429
    assert exc_info.value.failure_detail["retry_after_sec"] == 7.0


def test_invoke_openai_compat_response_maps_stream_http_auth_failure() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(OpenAICompatProviderAuthError) as exc_info:
        invoke_openai_compat_response(_config(), _rendered_payload(), transport=httpx.MockTransport(_handler))

    assert exc_info.value.failure_detail["provider_status_code"] == 401


def test_invoke_openai_compat_response_maps_stream_http_5xx_to_unavailable() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    with pytest.raises(OpenAICompatProviderUnavailableError) as exc_info:
        invoke_openai_compat_response(_config(), _rendered_payload(), transport=httpx.MockTransport(_handler))

    assert exc_info.value.failure_detail["provider_status_code"] == 503


def test_invoke_openai_compat_response_rejects_malformed_sse_json() -> None:
    with pytest.raises(OpenAICompatProviderBadResponseError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=_stream_transport('{"type":"response.output_text.delta",'),
        )

    assert exc_info.value.failure_kind == "PROVIDER_BAD_RESPONSE"
    assert exc_info.value.failure_detail["response_error_type"] == "MalformedSSEJson"


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
