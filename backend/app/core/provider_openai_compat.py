from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Callable, Literal

import httpx

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)


ReasoningEffort = Literal["low", "medium", "high", "xhigh"]
ProviderAuditObserver = Callable[[str, dict[str, object]], None]
OpenAIClientFactory = Callable[["OpenAICompatProviderConfig"], object]


class OpenAICompatProviderType(StrEnum):
    RESPONSES_STREAM = "openai_responses_stream"
    RESPONSES_NON_STREAM = "openai_responses_non_stream"


@dataclass(frozen=True)
class OpenAICompatProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout_sec: float
    connect_timeout_sec: float | None = None
    write_timeout_sec: float | None = None
    first_token_timeout_sec: float | None = None
    stream_idle_timeout_sec: float | None = None
    request_total_timeout_sec: float | None = None
    reasoning_effort: ReasoningEffort | None = None
    provider_type: OpenAICompatProviderType = OpenAICompatProviderType.RESPONSES_STREAM
    schema_name: str | None = None
    schema_body: dict[str, object] | None = None
    strict: bool = True


@dataclass(frozen=True)
class OpenAICompatProviderResult:
    output_text: str
    response_id: str | None = None
    output_payload: dict[str, Any] | None = None
    output_payloads: tuple[dict[str, Any], ...] = ()


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
    normalized_content_type = str(content_type or "TEXT").upper()
    if normalized_content_type == "TEXT":
        text_value = content_payload.get("text")
        if isinstance(text_value, str) and text_value.strip():
            return text_value
    return json.dumps(content_payload, ensure_ascii=False, sort_keys=True, indent=2)


def _render_message_text(message: RenderedExecutionMessage) -> str:
    header = f"[{message.channel}/{message.content_type}]"
    body = _message_payload_to_text(message.content_type, dict(message.content_payload))
    return f"{header}\n{body}"


def _build_responses_instructions(rendered_payload: RenderedExecutionPayload) -> str | None:
    instruction_parts = [
        _render_message_text(message)
        for message in rendered_payload.messages
        if str(message.role or "").lower() == "system"
    ]
    if not instruction_parts:
        return None
    return "\n\n".join(instruction_parts)


def _build_responses_input(rendered_payload: RenderedExecutionPayload) -> list[dict[str, object]]:
    return [
        {
            "role": message.role,
            "content": [
                {
                    "type": "input_text",
                    "text": _render_message_text(message),
                }
            ],
        }
        for message in rendered_payload.messages
        if str(message.role or "").lower() != "system"
    ]


def _object_to_plain(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_object_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_object_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _object_to_plain(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        try:
            return _object_to_plain(value.model_dump(mode="python"))
        except TypeError:
            return _object_to_plain(value.model_dump())
    if hasattr(value, "__dict__"):
        return {
            str(key): _object_to_plain(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _response_payload(value: object | None) -> dict[str, object]:
    plain = _object_to_plain(value)
    return plain if isinstance(plain, dict) else {}


def _value_from_object(value: object | None, key: str) -> object | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _parse_json_object_sequence(value: str) -> tuple[dict[str, Any], ...]:
    decoder = json.JSONDecoder()
    stripped = str(value or "").strip()
    if not stripped:
        return ()
    items: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(stripped):
        while cursor < len(stripped) and stripped[cursor].isspace():
            cursor += 1
        if cursor >= len(stripped):
            break
        try:
            parsed, next_cursor = decoder.raw_decode(stripped, cursor)
        except ValueError:
            return ()
        if not isinstance(parsed, dict):
            return ()
        items.append(dict(parsed))
        cursor = next_cursor
    return tuple(items)


def _extract_output_payloads(response_payload: dict[str, object]) -> tuple[dict[str, Any], ...]:
    output_parsed = response_payload.get("output_parsed")
    if isinstance(output_parsed, dict):
        return (dict(output_parsed),)

    output = response_payload.get("output")
    if not isinstance(output, list):
        output_text = response_payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return _parse_json_object_sequence(output_text)
        return ()
    payloads: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            parsed = content_item.get("parsed")
            if isinstance(parsed, dict):
                payloads.append(dict(parsed))
    if payloads:
        return tuple(payloads)
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return _parse_json_object_sequence(output_text)
    return ()


def _extract_output_payload(response_payload: dict[str, object]) -> dict[str, Any] | None:
    payloads = _extract_output_payloads(response_payload)
    return dict(payloads[0]) if payloads else None


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


def _extract_response_id(value: object | None) -> str | None:
    if value is None:
        return None
    direct_id = _value_from_object(value, "id")
    if direct_id is not None:
        return str(direct_id)
    response = _value_from_object(value, "response")
    response_id = _value_from_object(response, "id")
    if response_id is not None:
        return str(response_id)
    return None


def _extract_request_id(value: object | None) -> str | None:
    for key in ("request_id", "_request_id"):
        request_id = _value_from_object(value, key)
        if request_id is not None:
            return str(request_id)
    response = _value_from_object(value, "response")
    for key in ("request_id", "_request_id"):
        request_id = _value_from_object(response, key)
        if request_id is not None:
            return str(request_id)
    return None


def _extract_event_delta(event: object) -> str | None:
    delta = _value_from_object(event, "delta")
    if isinstance(delta, str) and delta:
        return delta
    text = _value_from_object(event, "text")
    if isinstance(text, str) and text:
        return text
    return None


def _extract_event_error(event: object) -> object | None:
    error = _value_from_object(event, "error")
    if error is not None:
        return error
    response = _value_from_object(event, "response")
    return _value_from_object(response, "error")


def _response_error_detail(*, event: object, response_id: str | None) -> dict[str, object]:
    error = _extract_event_error(event)
    return {
        "provider_response_id": response_id,
        "request_id": _extract_request_id(event),
        "response_error_type": _value_from_object(error, "type"),
        "response_error_code": _value_from_object(error, "code"),
        "response_error_message": _value_from_object(error, "message"),
    }


def _raise_from_response_error(event: object, *, response_id: str | None) -> None:
    detail = _response_error_detail(event=event, response_id=response_id)
    error_type = str(detail.get("response_error_type") or "").lower()
    error_code = str(detail.get("response_error_code") or "").lower()
    message = str(detail.get("response_error_message") or "Provider response stream failed.")
    if "rate" in error_type or "rate" in error_code:
        raise OpenAICompatProviderRateLimitedError(
            failure_kind="PROVIDER_RATE_LIMITED",
            message=message,
            failure_detail=detail,
        )
    if "auth" in error_type or "permission" in error_type or "api_key" in error_code:
        raise OpenAICompatProviderAuthError(
            failure_kind="PROVIDER_AUTH_FAILED",
            message=message,
            failure_detail=detail,
        )
    if "server" in error_type or "upstream" in error_code or "timeout" in error_code:
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=message,
            failure_detail=detail,
        )
    raise OpenAICompatProviderBadResponseError(
        failure_kind="PROVIDER_BAD_RESPONSE",
        message=message,
        failure_detail=detail,
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
        "stream": stream,
    }
    instructions = _build_responses_instructions(rendered_payload)
    if instructions is not None:
        payload["instructions"] = instructions
    if config.reasoning_effort is not None:
        payload["reasoning"] = {"effort": config.reasoning_effort}
    if config.schema_name and isinstance(config.schema_body, dict):
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": config.schema_name,
                "schema": dict(config.schema_body),
                "strict": bool(config.strict),
            }
        }
    return payload


def _sdk_timeout(config: OpenAICompatProviderConfig, *, streaming: bool) -> httpx.Timeout:
    read_timeout_sec: float | None = float(config.request_total_timeout_sec or config.timeout_sec)
    if streaming:
        read_timeout_sec = None
    return httpx.Timeout(
        connect=float(config.connect_timeout_sec or config.timeout_sec),
        write=float(config.write_timeout_sec or config.timeout_sec),
        read=read_timeout_sec,
        pool=float(config.connect_timeout_sec or config.timeout_sec),
    )


def _build_openai_client(
    config: OpenAICompatProviderConfig,
    *,
    transport: httpx.BaseTransport | None = None,
):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - exercised only when runtime dependency is missing
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message="OpenAI Python SDK is not installed.",
            failure_detail={"provider_transport_error": "OpenAISDKMissing"},
        ) from exc

    http_client = None
    if transport is not None:
        http_client = httpx.Client(
            transport=transport,
            timeout=_sdk_timeout(
                config,
                streaming=config.provider_type == OpenAICompatProviderType.RESPONSES_STREAM,
            ),
        )
    return OpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=_sdk_timeout(config, streaming=config.provider_type == OpenAICompatProviderType.RESPONSES_STREAM),
        http_client=http_client,
        max_retries=0,
    )


def _client_for(
    config: OpenAICompatProviderConfig,
    *,
    transport: httpx.BaseTransport | None,
    client_factory: OpenAIClientFactory | None,
):
    if client_factory is not None:
        return client_factory(config)
    return _build_openai_client(config, transport=transport)


def _call_stream_close(stream: object) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        close()


def _build_result_from_response(
    response: object | None,
    *,
    output_parts: list[str],
    response_id: str | None,
) -> OpenAICompatProviderResult:
    response_payload = _response_payload(response)
    final_response_id = response_id or (
        str(response_payload.get("id")) if response_payload.get("id") is not None else None
    )
    output_payloads = _extract_output_payloads(response_payload)
    output_payload = dict(output_payloads[0]) if output_payloads else None
    output_text = ""
    if response_payload:
        try:
            output_text = _extract_output_text(response_payload)
        except OpenAICompatProviderBadResponseError:
            output_text = ""
    if not output_text:
        output_text = "".join(output_parts).strip()
    if not output_text and output_payload is not None:
        output_text = json.dumps(output_payload, ensure_ascii=False, sort_keys=True)
    if not output_text:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider response did not contain any assistant text output.",
            failure_detail={"provider_response_id": final_response_id},
        )
    return OpenAICompatProviderResult(
        output_text=output_text,
        response_id=final_response_id,
        output_payload=output_payload,
        output_payloads=output_payloads,
    )


def _extract_streaming_responses_output(
    stream: object,
    *,
    config: OpenAICompatProviderConfig,
    audit_observer: ProviderAuditObserver | None = None,
) -> OpenAICompatProviderResult:
    response_id: str | None = None
    output_parts: list[str] = []
    stream_queue: queue.Queue[tuple[str, object | None]] = queue.Queue()
    first_output_at: float | None = None
    started_at = time.monotonic()

    def _stream_reader() -> None:
        try:
            for event in stream:
                stream_queue.put(("event", event))
        except BaseException as exc:  # pragma: no cover - exercised through queue handoff
            stream_queue.put(("error", exc))
        finally:
            stream_queue.put(("done", None))

    reader = threading.Thread(target=_stream_reader, daemon=True)
    reader.start()

    while True:
        elapsed_sec = time.monotonic() - started_at
        request_total_timeout_sec = float(config.request_total_timeout_sec or config.timeout_sec)
        remaining_total_sec = request_total_timeout_sec - elapsed_sec
        if remaining_total_sec <= 0:
            _call_stream_close(stream)
            raise OpenAICompatProviderUnavailableError(
                failure_kind="REQUEST_TOTAL_TIMEOUT",
                message="Provider stream exceeded the total request timeout.",
                failure_detail={
                    "provider_response_id": response_id,
                    "timeout_phase": "request_total",
                },
            )

        phase_timeout_sec = float(
            (
                config.stream_idle_timeout_sec
                if first_output_at is not None
                else config.first_token_timeout_sec
            )
            or config.timeout_sec
        )
        wait_timeout_sec = min(phase_timeout_sec, remaining_total_sec)
        try:
            event_kind, payload = stream_queue.get(timeout=wait_timeout_sec)
        except queue.Empty as exc:
            _call_stream_close(stream)
            if remaining_total_sec <= phase_timeout_sec:
                raise OpenAICompatProviderUnavailableError(
                    failure_kind="REQUEST_TOTAL_TIMEOUT",
                    message="Provider stream exceeded the total request timeout.",
                    failure_detail={
                        "provider_response_id": response_id,
                        "timeout_phase": "request_total",
                    },
                ) from exc
            raise OpenAICompatProviderUnavailableError(
                failure_kind="STREAM_IDLE_TIMEOUT" if first_output_at is not None else "FIRST_TOKEN_TIMEOUT",
                message="Provider stream timed out while waiting for the next output event.",
                failure_detail={
                    "provider_response_id": response_id,
                    "timeout_phase": ("stream_idle" if first_output_at is not None else "first_token"),
                },
            ) from exc

        if event_kind == "done":
            return _build_result_from_response(None, output_parts=output_parts, response_id=response_id)
        if event_kind == "error":
            error = payload if isinstance(payload, BaseException) else RuntimeError(str(payload))
            if isinstance(error, httpx.TimeoutException):
                raise OpenAICompatProviderUnavailableError(
                    failure_kind="STREAM_IDLE_TIMEOUT" if first_output_at is not None else "FIRST_TOKEN_TIMEOUT",
                    message=str(error),
                    failure_detail={
                        "provider_response_id": response_id,
                        "provider_transport_error": type(error).__name__,
                        "timeout_phase": ("stream_idle" if first_output_at is not None else "first_token"),
                    },
                ) from error
            if isinstance(error, httpx.TransportError):
                raise OpenAICompatProviderUnavailableError(
                    failure_kind="UPSTREAM_UNAVAILABLE",
                    message=str(error),
                    failure_detail={
                        "provider_response_id": response_id,
                        "provider_transport_error": type(error).__name__,
                    },
                ) from error
            raise _map_sdk_exception(error)

        event = payload
        event_type = str(_value_from_object(event, "type") or "")
        response_id = response_id or _extract_response_id(event)
        if event_type in {"response.output_text.delta", "response.output_text.done"}:
            delta = _extract_event_delta(event)
            if delta:
                output_parts.append(delta)
                if first_output_at is None:
                    first_output_at = time.monotonic()
                    if audit_observer is not None:
                        audit_observer(
                            "first_token_received",
                            {
                                "provider_response_id": response_id,
                                "request_id": _extract_request_id(event),
                                "streaming": True,
                                "provider_type": config.provider_type.value,
                            },
                        )
            continue
        if event_type in {"response.failed", "error"}:
            _raise_from_response_error(event, response_id=response_id)
        if event_type == "response.completed":
            if audit_observer is not None:
                audit_observer(
                    "response_completed",
                    {
                        "provider_response_id": response_id,
                        "request_id": _extract_request_id(event),
                        "streaming": True,
                        "provider_type": config.provider_type.value,
                    },
                )
            return _build_result_from_response(
                _value_from_object(event, "response") or _call_get_final_response(stream),
                output_parts=output_parts,
                response_id=response_id,
            )


def _map_sdk_exception(exc: BaseException) -> OpenAICompatProviderError:
    class_name = exc.__class__.__name__
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    failure_detail: dict[str, object] = {
        "provider_transport_error": class_name,
        "provider_status_code": status_code,
        "request_id": getattr(exc, "request_id", None) or getattr(exc, "_request_id", None),
    }
    if hasattr(exc, "code"):
        failure_detail["response_error_code"] = getattr(exc, "code")
    if hasattr(exc, "type"):
        failure_detail["response_error_type"] = getattr(exc, "type")
    retry_after_sec = _parse_retry_after_sec(headers.get("Retry-After") if hasattr(headers, "get") else None)
    if retry_after_sec is not None:
        failure_detail["retry_after_sec"] = retry_after_sec

    if status_code == 429 or class_name == "RateLimitError":
        return OpenAICompatProviderRateLimitedError(
            failure_kind="PROVIDER_RATE_LIMITED",
            message=str(exc),
            failure_detail=failure_detail,
        )
    if status_code in {401, 403} or class_name in {"AuthenticationError", "PermissionDeniedError"}:
        return OpenAICompatProviderAuthError(
            failure_kind="PROVIDER_AUTH_FAILED",
            message=str(exc),
            failure_detail=failure_detail,
        )
    if (
        class_name in {"APITimeoutError", "APIConnectionError", "Timeout"}
        or (isinstance(status_code, int) and status_code >= 500)
    ):
        return OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=str(exc),
            failure_detail=failure_detail,
        )
    if isinstance(exc, OpenAICompatProviderError):
        return exc
    return OpenAICompatProviderBadResponseError(
        failure_kind="PROVIDER_BAD_RESPONSE",
        message=str(exc),
        failure_detail=failure_detail,
    )


def _invoke_streaming_responses(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    transport: httpx.BaseTransport | None = None,
    client_factory: OpenAIClientFactory | None = None,
    audit_observer: ProviderAuditObserver | None = None,
) -> OpenAICompatProviderResult:
    if audit_observer is not None:
        audit_observer(
            "request_started",
            {
                "provider_type": config.provider_type.value,
                "streaming": True,
                "model": config.model,
            },
        )
    try:
        client = _client_for(config, transport=transport, client_factory=client_factory)
        stream = client.responses.create(**_responses_request_payload(config, rendered_payload, stream=True))
        enter = getattr(stream, "__enter__", None)
        exit_ = getattr(stream, "__exit__", None)
        if callable(enter) and callable(exit_):
            with stream:
                return _extract_streaming_responses_output(
                    stream,
                    config=config,
                    audit_observer=audit_observer,
                )
        return _extract_streaming_responses_output(
            stream,
            config=config,
            audit_observer=audit_observer,
        )
    except OpenAICompatProviderError as exc:
        if audit_observer is not None:
            audit_observer(
                "request_failed",
                {
                    "failure_kind": exc.failure_kind,
                    **dict(exc.failure_detail),
                    "streaming": True,
                    "provider_type": config.provider_type.value,
                },
            )
        raise
    except BaseException as exc:
        mapped = _map_sdk_exception(exc)
        if audit_observer is not None:
            audit_observer(
                "request_failed",
                {
                    "failure_kind": mapped.failure_kind,
                    **dict(mapped.failure_detail),
                    "streaming": True,
                    "provider_type": config.provider_type.value,
                },
            )
        raise mapped from exc


def _invoke_non_streaming_responses(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    transport: httpx.BaseTransport | None = None,
    client_factory: OpenAIClientFactory | None = None,
    audit_observer: ProviderAuditObserver | None = None,
) -> OpenAICompatProviderResult:
    if audit_observer is not None:
        audit_observer(
            "request_started",
            {
                "provider_type": config.provider_type.value,
                "streaming": False,
                "model": config.model,
            },
        )
    try:
        client = _client_for(config, transport=transport, client_factory=client_factory)
        response = client.responses.create(**_responses_request_payload(config, rendered_payload, stream=False))
        result = _build_result_from_response(
            response,
            output_parts=[],
            response_id=_extract_response_id(response),
        )
    except OpenAICompatProviderError as exc:
        if audit_observer is not None:
            audit_observer(
                "request_failed",
                {
                    "failure_kind": exc.failure_kind,
                    **dict(exc.failure_detail),
                    "streaming": False,
                    "provider_type": config.provider_type.value,
                },
            )
        raise
    except BaseException as exc:
        mapped = _map_sdk_exception(exc)
        if audit_observer is not None:
            audit_observer(
                "request_failed",
                {
                    "failure_kind": mapped.failure_kind,
                    **dict(mapped.failure_detail),
                    "streaming": False,
                    "provider_type": config.provider_type.value,
                },
            )
        raise mapped from exc
    if audit_observer is not None:
        audit_observer(
            "response_completed",
            {
                "provider_response_id": result.response_id,
                "streaming": False,
                "provider_type": config.provider_type.value,
            },
        )
    return result


def invoke_openai_compat_response(
    config: OpenAICompatProviderConfig,
    rendered_payload: RenderedExecutionPayload,
    *,
    transport: httpx.BaseTransport | None = None,
    client_factory: OpenAIClientFactory | None = None,
    audit_observer: ProviderAuditObserver | None = None,
) -> OpenAICompatProviderResult:
    if config.provider_type == OpenAICompatProviderType.RESPONSES_NON_STREAM:
        return _invoke_non_streaming_responses(
            config,
            rendered_payload,
            transport=transport,
            client_factory=client_factory,
            audit_observer=audit_observer,
        )
    return _invoke_streaming_responses(
        config,
        rendered_payload,
        transport=transport,
        client_factory=client_factory,
        audit_observer=audit_observer,
    )


def probe_openai_compat_connectivity(
    config: OpenAICompatProviderConfig,
    *,
    transport: httpx.BaseTransport | None = None,
    client_factory: OpenAIClientFactory | None = None,
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
        result = invoke_openai_compat_response(
            config,
            rendered_payload,
            transport=transport,
            client_factory=client_factory,
        )
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
                connect_timeout_sec=config.connect_timeout_sec,
                write_timeout_sec=config.write_timeout_sec,
                first_token_timeout_sec=config.first_token_timeout_sec,
                stream_idle_timeout_sec=config.stream_idle_timeout_sec,
                request_total_timeout_sec=config.request_total_timeout_sec,
                reasoning_effort=config.reasoning_effort,
                provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
                schema_name=config.schema_name,
                schema_body=config.schema_body,
                strict=config.strict,
            ),
            rendered_payload,
            transport=transport,
            client_factory=client_factory,
        )
        return OpenAICompatConnectivityResult(
            ok=True,
            provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
            response_id=fallback_result.response_id,
        )


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


def list_openai_compat_models(
    config: OpenAICompatProviderConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[str]:
    try:
        with httpx.Client(timeout=_sdk_timeout(config, streaming=False), transport=transport) as client:
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
