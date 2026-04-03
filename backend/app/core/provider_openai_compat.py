from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx

from app.contracts.runtime import RenderedExecutionPayload


ReasoningEffort = Literal["low", "medium", "high", "xhigh"]


@dataclass(frozen=True)
class OpenAICompatProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout_sec: float
    reasoning_effort: ReasoningEffort | None = None


@dataclass(frozen=True)
class OpenAICompatProviderResult:
    output_text: str
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


def invoke_openai_compat_response(
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
                json={
                    "model": config.model,
                    "input": _build_responses_input(rendered_payload),
                    **(
                        {"reasoning": {"effort": config.reasoning_effort}}
                        if config.reasoning_effort is not None
                        else {}
                    ),
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

    failure_detail = {
        "provider_status_code": response.status_code,
    }
    if response.status_code == 429:
        retry_after_sec = _parse_retry_after_sec(response.headers.get("Retry-After"))
        if retry_after_sec is not None:
            failure_detail["retry_after_sec"] = retry_after_sec
        raise OpenAICompatProviderRateLimitedError(
            failure_kind="PROVIDER_RATE_LIMITED",
            message="Provider rejected the request with rate limiting.",
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
