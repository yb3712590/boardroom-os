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
    OpenAICompatProviderRateLimitedError,
    OpenAICompatProviderUnavailableError,
    invoke_openai_compat_response,
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
