from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Literal

import httpx

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)


ReasoningEffort = Literal["low", "medium", "high", "xhigh"]


class OpenAICompatProviderType(StrEnum):
    RESPONSES_STREAM = "openai_responses_stream"
    RESPONSES_NON_STREAM = "openai_responses_non_stream"


@dataclass(frozen=True)
class OpenAICompatProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout_sec: float
    reasoning_effort: ReasoningEffort | None = None
    provider_type: OpenAICompatProviderType = OpenAICompatProviderType.RESPONSES_STREAM


@dataclass(frozen=True)
class OpenAICompatProviderResult:
    output_text: str
    response_id: str | None = None


@dataclass(frozen=True)
class OpenAICompatConnectivityResult:
    ok: bool
    provider_type: OpenAICompatProviderType
    response_id: str | None = None


class OpenAICompatProviderError(RuntimeError):
    def __init__(self, *, failure_kind: str, message: str, failure_detail: dict[str, object]) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.failure_detail = failure_detail


class OpenAICompatProviderRateLimitedError(OpenAICompatProviderError):
    pass


class OpenAICompatProviderUnavailableError(OpenAICompatProviderError):
    pass


class OpenAICompatProviderAuthError(OpenAICompatProviderError):
    pass


class OpenAICompatProviderBadResponseError(OpenAICompatProviderError):
    pass


def _parse_retry_after_sec(header_value: str | None) -> float | None:
    if header_value is None:
        return None
    stripped = header_value.strip()
    if not stripped:
        return None
    try:
        seconds = float(stripped)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(stripped)
        except (TypeError, ValueError, IndexError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=datetime.now().astimezone().tzinfo)
        delta = (retry_at - datetime.now(retry_at.tzinfo)).total_seconds()
        return max(delta, 0.0)
    return max(seconds, 0.0)


def _message_payload_to_text(content_type: str, content_payload: dict[str, object]) -> str:
    return json.dumps(
        {
            "content_type": content_type,
            "content_payload": content_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _build_responses_input(rendered_payload: RenderedExecutionPayload) -> list[dict[str, object]]:
    return [
        {
            "role": message.role,
            "content": [
                {
                    "type": "input_text",
                    "text": _message_payload_to_text(message.content_type, dict(message.content_payload)),
                }
            ],
        }
        for message in rendered_payload.messages
    ]


def _build_chat_completions_messages(rendered_payload: RenderedExecutionPayload) -> list[dict[str, object]]:
    return [
        {
            "role": message.role,
            "content": _message_payload_to_text(message.content_type, dict(message.content_payload)),
        }
        for message in rendered_payload.messages
    ]


def _extract_output_text(response_payload: dict[str, object]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = response_payload.get("output")
    if not isinstance(output, list):
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider response is missing output text content.",
            failure_detail={
                "provider_response_id": response_payload.get("id"),
            },
        )

    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            content_text = content_item.get("text")
            content_type = content_item.get("type")
            if isinstance(content_text, str) and content_text.strip() and content_type in {
                "output_text",
                "text",
            }:
                texts.append(content_text)
    if texts:
        return "\n".join(texts)

    raise OpenAICompatProviderBadResponseError(
        failure_kind="PROVIDER_BAD_RESPONSE",
        message="Provider response did not contain any assistant text output.",
        failure_detail={
            "provider_response_id": response_payload.get("id"),
        },
    )


def _extract_streaming_responses_output(
    response: httpx.Response,
) -> tuple[str, str | None]:
    response_id: str | None = None
    output_parts: list[str] = []
    buffer = ""

    for chunk in response.iter_text():
        if not chunk:
            continue
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            if data == "[DONE]":
                combined = "".join(output_parts).strip()
                if not combined:
                    raise OpenAICompatProviderBadResponseError(
                        failure_kind="PROVIDER_BAD_RESPONSE",
                        message="Streaming chat completion did not return any assistant text output.",
                        failure_detail={
                            "provider_response_id": response_id,
                        },
                    )
                return combined, response_id
            try:
                event_payload = json.loads(data)
            except ValueError as exc:
                raise OpenAICompatProviderBadResponseError(
                    failure_kind="PROVIDER_BAD_RESPONSE",
                    message=f"Streaming responses call returned invalid JSON event: {exc}",
                    failure_detail={
                        "provider_response_id": response_id,
                    },
                ) from exc
            if not isinstance(event_payload, dict):
                continue
            event_type = str(event_payload.get("type") or "")
            if response_id is None and event_payload.get("response", {}).get("id") is not None:
                response_id = str(event_payload["response"]["id"])
            if response_id is None and event_payload.get("id") is not None:
                response_id = str(event_payload.get("id"))
            if event_type == "response.output_text.delta":
                delta = event_payload.get("delta")
                if isinstance(delta, str) and delta:
                    output_parts.append(delta)
                continue
            response_payload = event_payload.get("response")
            if isinstance(response_payload, dict) and response_id is None and response_payload.get("id") is not None:
                response_id = str(response_payload.get("id"))

    combined = "".join(output_parts).strip()
    if combined:
        return combined, response_id
    raise OpenAICompatProviderBadResponseError(
        failure_kind="PROVIDER_BAD_RESPONSE",
        message="Streaming responses call ended without any assistant text output.",
        failure_detail={
            "provider_response_id": response_id,
        },
    )


def _responses_request_payload(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    stream: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": config.model,
        "input": _build_responses_input(rendered_payload),
    }
    if stream:
        payload["stream"] = True
    if config.reasoning_effort is not None:
        payload["reasoning"] = {"effort": config.reasoning_effort}
    return payload


def _map_provider_error_response(response: httpx.Response, *, streaming: bool) -> None:
    failure_detail = {"provider_status_code": response.status_code}
    if response.status_code == 429:
        retry_after_sec = _parse_retry_after_sec(response.headers.get("Retry-After"))
        if retry_after_sec is not None:
            failure_detail["retry_after_sec"] = retry_after_sec
        raise OpenAICompatProviderRateLimitedError(
            failure_kind="PROVIDER_RATE_LIMITED",
            message=(
                "Provider rejected the streaming responses request with rate limiting."
                if streaming
                else "Provider rejected the request with rate limiting."
            ),
            failure_detail=failure_detail,
        )
    if response.status_code in {401, 403}:
        raise OpenAICompatProviderAuthError(
            failure_kind="PROVIDER_AUTH_FAILED",
            message="Provider rejected the configured credentials.",
            failure_detail=failure_detail,
        )
    if response.status_code >= 500:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message="Provider returned an upstream server error.",
            failure_detail=failure_detail,
        )
    if response.status_code >= 400:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider returned an unsupported client error.",
            failure_detail=failure_detail,
        )


def _parse_non_streaming_response(response: httpx.Response) -> OpenAICompatProviderResult:
    try:
        response_payload = response.json()
    except ValueError as exc:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message=f"Provider response was not valid JSON: {exc}",
            failure_detail={},
        ) from exc
    if not isinstance(response_payload, dict):
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider response root must be a JSON object.",
            failure_detail={},
        )

    output_text = _extract_output_text(response_payload)
    return OpenAICompatProviderResult(
        output_text=output_text,
        response_id=str(response_payload.get("id")) if response_payload.get("id") is not None else None,
    )


def _invoke_streaming_responses(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    transport: httpx.BaseTransport | None = None,
) -> OpenAICompatProviderResult:
    try:
        with httpx.Client(
            timeout=config.timeout_sec,
            transport=transport,
        ) as client:
            with client.stream(
                "POST",
                f"{config.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=_responses_request_payload(config, rendered_payload, stream=True),
            ) as response:
                _map_provider_error_response(response, streaming=True)
                content_type = str(response.headers.get("content-type") or "").lower()
                if "text/event-stream" not in content_type:
                    return _parse_non_streaming_response(response)

                output_text, response_id = _extract_streaming_responses_output(response)
                return OpenAICompatProviderResult(
                    output_text=output_text,
                    response_id=response_id,
                )
    except httpx.TimeoutException as exc:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Provider request timed out: {exc}",
            failure_detail={
                "provider_transport_error": type(exc).__name__,
            },
        ) from exc
    except httpx.TransportError as exc:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Provider transport failed: {exc}",
            failure_detail={
                "provider_transport_error": type(exc).__name__,
            },
        ) from exc


def _invoke_non_streaming_responses(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    transport: httpx.BaseTransport | None = None,
) -> OpenAICompatProviderResult:
    try:
        with httpx.Client(
            timeout=config.timeout_sec,
            transport=transport,
        ) as client:
            response = client.post(
                f"{config.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=_responses_request_payload(config, rendered_payload, stream=False),
            )
    except httpx.TimeoutException as exc:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Provider request timed out: {exc}",
            failure_detail={
                "provider_transport_error": type(exc).__name__,
            },
        ) from exc
    except httpx.TransportError as exc:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Provider transport failed: {exc}",
            failure_detail={
                "provider_transport_error": type(exc).__name__,
            },
        ) from exc

    _map_provider_error_response(response, streaming=False)
    return _parse_non_streaming_response(response)


def invoke_openai_compat_response(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    transport: httpx.BaseTransport | None = None,
) -> OpenAICompatProviderResult:
    if config.provider_type == OpenAICompatProviderType.RESPONSES_NON_STREAM:
        return _invoke_non_streaming_responses(
            config,
            rendered_payload,
            transport=transport,
        )
    return _invoke_streaming_responses(
        config,
        rendered_payload,
        transport=transport,
    )


def probe_openai_compat_connectivity(
    config: OpenAICompatProviderConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> OpenAICompatConnectivityResult:
    rendered_payload = RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id="ctx_provider_connectivity",
            compile_id="cmp_provider_connectivity",
            compile_request_id="creq_provider_connectivity",
            ticket_id="tkt_provider_connectivity",
            workflow_id="wf_provider_connectivity",
            node_id="node_provider_connectivity",
            compiler_version="context-compiler.min.v1",
            model_profile="boardroom_os.runtime.min",
            render_target="json_messages_v1",
            rendered_at=datetime.now().astimezone(),
        ),
        messages=[
            RenderedExecutionMessage(
                role="system",
                channel="SYSTEM_CONTROLS",
                content_type="JSON",
                content_payload={"rules": ["return JSON only"]},
            ),
            RenderedExecutionMessage(
                role="user",
                channel="TASK_DEFINITION",
                content_type="JSON",
                content_payload={"task": "Return a small JSON object confirming connectivity."},
            ),
        ],
        summary=RenderedExecutionPayloadSummary(
            total_message_count=2,
            control_message_count=1,
            data_message_count=1,
            retrieval_message_count=0,
            degraded_data_message_count=0,
            reference_message_count=0,
        ),
    )
    try:
        result = invoke_openai_compat_response(config, rendered_payload, transport=transport)
        return OpenAICompatConnectivityResult(
            ok=True,
            provider_type=config.provider_type,
            response_id=result.response_id,
        )
    except OpenAICompatProviderBadResponseError as exc:
        if config.provider_type != OpenAICompatProviderType.RESPONSES_STREAM:
            raise
        if exc.failure_detail.get("provider_status_code") != 400:
            raise
        fallback_result = invoke_openai_compat_response(
            OpenAICompatProviderConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                timeout_sec=config.timeout_sec,
                reasoning_effort=config.reasoning_effort,
                provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
            ),
            rendered_payload,
            transport=transport,
        )
        return OpenAICompatConnectivityResult(
            ok=True,
            provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
            response_id=fallback_result.response_id,
        )


def list_openai_compat_models(
    config: OpenAICompatProviderConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[str]:
    try:
        with httpx.Client(timeout=config.timeout_sec, transport=transport) as client:
            response = client.get(
                f"{config.base_url}/models",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException as exc:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Provider request timed out: {exc}",
            failure_detail={
                "provider_transport_error": type(exc).__name__,
            },
        ) from exc
    except httpx.TransportError as exc:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Provider transport failed: {exc}",
            failure_detail={
                "provider_transport_error": type(exc).__name__,
            },
        ) from exc

    _map_provider_error_response(response, streaming=False)
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider model list response must contain a data array.",
            failure_detail={},
        )
    return sorted(
        {
            str(item.get("id")).strip()
            for item in payload["data"]
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
    )
