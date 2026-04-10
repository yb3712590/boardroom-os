from __future__ import annotations

import json
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
        provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
    )


def test_invoke_openai_compat_response_includes_reasoning_effort_when_configured() -> None:
    config = OpenAICompatProviderConfig(
        base_url="https://api-vip.codex-for.me/v1",
        api_key="test-key",
        model="gpt-5.3-codex",
        timeout_sec=30.0,
        reasoning_effort="xhigh",
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["reasoning"] == {"effort": "xhigh"}
        return httpx.Response(
            200,
            json={
                "id": "resp_reasoning",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"summary":"Provider completed.","recommended_option_id":"option_a","options":[]}',
                            }
                        ],
                    }
                ],
            },
        )

    result = invoke_openai_compat_response(
        config,
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert result.response_id == "resp_reasoning"


def test_invoke_openai_compat_response_returns_text_from_responses_message_payload() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api-vip.codex-for.me/v1/responses")
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "gpt-5.3-codex"
        assert isinstance(body["input"], list)
        return httpx.Response(
            200,
            json={
                "id": "resp_001",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"summary":"Provider completed.","recommended_option_id":"option_a","options":[]}',
                            }
                        ],
                    }
                ],
            },
        )

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert result.response_id == "resp_001"
    assert result.output_text.startswith('{"summary":"Provider completed."')


def test_invoke_openai_compat_response_maps_429_to_rate_limited() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "7"},
            json={"error": {"message": "quota exhausted"}},
        )

    with pytest.raises(OpenAICompatProviderRateLimitedError) as exc_info:
        invoke_openai_compat_response(
            _config(),
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
    assert exc_info.value.failure_detail["provider_transport_error"] == "ReadTimeout"


def test_invoke_openai_compat_response_maps_auth_failures() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(OpenAICompatProviderAuthError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "PROVIDER_AUTH_FAILED"
    assert exc_info.value.failure_detail["provider_status_code"] == 401


def test_invoke_openai_compat_response_rejects_bad_json_payloads() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "resp_bad", "output": []})

    with pytest.raises(OpenAICompatProviderBadResponseError) as exc_info:
        invoke_openai_compat_response(
            _config(),
            _rendered_payload(),
            transport=httpx.MockTransport(_handler),
        )

    assert exc_info.value.failure_kind == "PROVIDER_BAD_RESPONSE"
    assert exc_info.value.failure_detail["provider_response_id"] == "resp_bad"


def test_invoke_openai_compat_response_uses_streaming_responses_by_default() -> None:
    request_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        request_urls.append(str(request.url))
        assert request.url.path.endswith("/responses")
        assert request.headers["Accept"] == "text/event-stream"
        body = (
            'event: response.output_text.delta\n'
            'data: {"type":"response.output_text.delta","delta":"{\\"ok\\""}\n\n'
            'event: response.output_text.delta\n'
            'data: {"type":"response.output_text.delta","delta":":true}"}\n\n'
            'event: response.completed\n'
            'data: {"type":"response.completed","response":{"id":"resp_stream_001"}}\n\n'
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert request_urls == [
        "https://api-vip.codex-for.me/v1/responses",
    ]
    assert result.response_id == "resp_stream_001"
    assert result.output_text == '{"ok":true}'


def test_invoke_openai_compat_response_returns_after_response_completed_without_done_sentinel() -> None:
    class _HangingStream(httpx.SyncByteStream):
        def __iter__(self):
            yield (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\":true}"}\n\n'
                b'event: response.completed\n'
                b'data: {"type":"response.completed","response":{"id":"resp_stream_completed_only"}}\n\n'
            )
            raise httpx.ReadTimeout("stream left open after response.completed")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_HangingStream(),
        )

    result = invoke_openai_compat_response(
        _config(),
        _rendered_payload(),
        transport=httpx.MockTransport(_handler),
    )

    assert result.response_id == "resp_stream_completed_only"
    assert result.output_text == '{"ok":true}'


def test_connectivity_test_falls_back_to_non_streaming_responses_when_streaming_is_not_supported() -> None:
    request_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        request_urls.append(str(request.url))
        if request.headers.get("Accept") == "text/event-stream":
            return httpx.Response(
                400,
                json={"error": {"message": "streaming not supported"}},
            )
        return httpx.Response(
            200,
            json={
                "id": "resp_non_stream_connectivity",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"status":"ok"}',
                            }
                        ],
                    }
                ],
            },
        )

    result = probe_openai_compat_connectivity(
        OpenAICompatProviderConfig(
            base_url="https://api-vip.codex-for.me/v1",
            api_key="test-key",
            model="gpt-5.3-codex",
            timeout_sec=30.0,
            provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
        ),
        transport=httpx.MockTransport(_handler),
    )

    assert request_urls == [
        "https://api-vip.codex-for.me/v1/responses",
        "https://api-vip.codex-for.me/v1/responses",
    ]
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
