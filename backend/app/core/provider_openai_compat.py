from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
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
PayloadResolver = Callable[[dict[str, Any]], dict[str, Any]]


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
    events: tuple[dict[str, object], ...] = ()
    items: tuple[dict[str, object], ...] = ()
    text_deltas: tuple[str, ...] = ()
    final_text: str = ""
    json_objects: tuple[dict[str, Any], ...] = ()
    selected_payload: dict[str, Any] | None = None
    raw_output_text: str = ""
    finish_state: str = "COMPLETED"
    request_id: str | None = None
    duplicate_json_object_count: int = 0
    selected_payload_index: int | None = None
    ambiguous_candidate_count: int = 0
    repair_steps: tuple[str, ...] = ()
    json_parse_error: str | None = None
    raw_text_length: int = 0
    first_token_elapsed_sec: float | None = None
    last_token_elapsed_sec: float | None = None
    max_stream_idle_gap_sec: float | None = None
    events_summary: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenAICompatResolvedPayload:
    payload: dict[str, Any]
    candidate_count: int
    selected_candidate_index: int
    ambiguous_candidate_count: int = 0
    repair_steps: tuple[str, ...] = ()
    schema_validation_error: str | None = None


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


def _strip_json_comments(value: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    escaping = False

    while index < len(value):
        char = value[index]
        next_char = value[index + 1] if index + 1 < len(value) else ""

        if in_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(value) and value[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(value) and not (value[index] == "*" and value[index + 1] == "/"):
                index += 1
            index += 2 if index + 1 < len(value) else 0
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _strip_trailing_commas(value: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    escaping = False

    while index < len(value):
        char = value[index]
        if in_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == ",":
            look_ahead = index + 1
            while look_ahead < len(value) and value[look_ahead].isspace():
                look_ahead += 1
            if look_ahead < len(value) and value[look_ahead] in "]}":
                index += 1
                continue

        result.append(char)
        index += 1

    return "".join(result)


def _normalize_single_quoted_strings(value: str) -> tuple[str, bool]:
    result: list[str] = []
    index = 0
    in_double_string = False
    escaping = False
    changed = False

    while index < len(value):
        char = value[index]
        if in_double_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_double_string = False
            index += 1
            continue

        if char == '"':
            in_double_string = True
            result.append(char)
            index += 1
            continue

        if char != "'":
            result.append(char)
            index += 1
            continue

        string_buffer: list[str] = []
        index += 1
        while index < len(value):
            string_char = value[index]
            if string_char == "\\" and index + 1 < len(value):
                string_buffer.append(string_char)
                string_buffer.append(value[index + 1])
                index += 2
                continue
            if string_char == "'":
                break
            string_buffer.append(string_char)
            index += 1

        if index >= len(value) or value[index] != "'":
            return value, False

        result.append(json.dumps("".join(string_buffer), ensure_ascii=False))
        changed = True
        index += 1

    return "".join(result), changed


def _extract_json_object_fragments(value: str) -> tuple[str, ...]:
    fragments: list[str] = []
    stack: list[str] = []
    start_index: int | None = None
    in_string = False
    escaping = False

    for index, char in enumerate(value):
        if in_string:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if not stack:
                start_index = index
            stack.append(char)
            continue
        if char == "}" and stack:
            stack.pop()
            if not stack and start_index is not None:
                fragment = value[start_index : index + 1].strip()
                if fragment:
                    fragments.append(fragment)
                start_index = None
    return tuple(fragments)


@dataclass(frozen=True)
class _ResolvedJsonCandidate:
    payload: dict[str, Any]
    repair_steps: tuple[str, ...]
    candidate_text: str


class OpenAICompatJsonResolver:
    def __init__(
        self,
        *,
        output_text: str,
        response_id: str | None,
        request_id: str | None,
    ) -> None:
        self.output_text = str(output_text or "")
        self.response_id = response_id
        self.request_id = request_id

    def collect_candidates(self) -> tuple[tuple[_ResolvedJsonCandidate, ...], str | None]:
        raw_output = self.output_text
        stripped_output = raw_output.strip()
        if not stripped_output:
            return (), None

        candidates: list[_ResolvedJsonCandidate] = []
        parse_errors: list[str] = []
        variation_inputs: list[tuple[str, tuple[str, ...]]] = []

        def _push_variation(candidate_text: str, repair_steps: tuple[str, ...]) -> None:
            if not candidate_text.strip():
                return
            entry = (candidate_text, repair_steps)
            if entry not in variation_inputs:
                variation_inputs.append(entry)

        bom_stripped = _strip_bom(stripped_output)
        bom_steps: list[str] = ["strip_bom"] if bom_stripped != stripped_output else []
        _push_variation(stripped_output, ())
        _push_variation(bom_stripped, tuple(bom_steps))

        fence_stripped = _strip_markdown_code_fence(bom_stripped)
        fence_steps = list(bom_steps)
        if fence_stripped != bom_stripped:
            fence_steps.append("strip_markdown_code_fence")
        _push_variation(fence_stripped, tuple(fence_steps))

        comment_stripped = _strip_json_comments(fence_stripped)
        comment_steps = list(fence_steps)
        if comment_stripped != fence_stripped:
            comment_steps.append("strip_json_comments")

        comma_stripped = _strip_trailing_commas(comment_stripped)
        comma_steps = list(comment_steps)
        if comma_stripped != comment_stripped:
            comma_steps.append("strip_trailing_commas")

        normalized_quotes, normalized = _normalize_single_quoted_strings(comma_stripped)
        normalized_steps = list(comma_steps)
        if normalized:
            normalized_steps.append("normalize_single_quoted_strings")
        _push_variation(normalized_quotes, tuple(normalized_steps))

        seen_payloads: set[str] = set()

        def _record_payloads(candidate_text: str, repair_steps: tuple[str, ...]) -> None:
            parsed_payloads, parse_error = _parse_json_object_sequence_with_error(candidate_text)
            if parsed_payloads:
                for payload in parsed_payloads:
                    serialized = _canonical_json_object(payload)
                    if serialized in seen_payloads:
                        continue
                    seen_payloads.add(serialized)
                    candidates.append(
                        _ResolvedJsonCandidate(
                            payload=dict(payload),
                            repair_steps=repair_steps,
                            candidate_text=candidate_text,
                        )
                    )
                return
            if parse_error is not None:
                parse_errors.append(parse_error)

        for candidate_text, repair_steps in variation_inputs:
            _record_payloads(candidate_text, repair_steps)
            for fragment in _extract_json_object_fragments(candidate_text):
                _record_payloads(fragment, repair_steps + ("extract_json_object_fragment",))

        return tuple(candidates), (parse_errors[-1] if parse_errors else None)


def _responses_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/responses"


def _stream_timeout(config: OpenAICompatProviderConfig) -> httpx.Timeout:
    read_timeout_candidates = [
        config.first_token_timeout_sec,
        config.stream_idle_timeout_sec,
        config.request_total_timeout_sec,
        config.timeout_sec,
    ]
    read_timeout_sec = min(
        float(item)
        for item in read_timeout_candidates
        if item is not None and float(item) > 0
    )
    return httpx.Timeout(
        connect=float(config.connect_timeout_sec or config.timeout_sec),
        write=float(config.write_timeout_sec or config.timeout_sec),
        read=read_timeout_sec,
        pool=float(config.connect_timeout_sec or config.timeout_sec),
    )


class _ResponsesHttpClient:
    def __init__(self, config: OpenAICompatProviderConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self.transport = transport

    @contextmanager
    def stream(self, payload: dict[str, object]):
        with httpx.Client(
            transport=self.transport,
            timeout=_stream_timeout(self.config),
        ) as client:
            with client.stream(
                "POST",
                _responses_url(self.config.base_url),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=payload,
            ) as response:
                yield response


@dataclass(frozen=True)
class _SSEEvent:
    event: str | None
    data: str


class _SSEDecoder:
    def __init__(self) -> None:
        self._event: str | None = None
        self._data_lines: list[str] = []

    def feed_line(self, line: str) -> _SSEEvent | None:
        if line == "":
            return self._flush()
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value
        elif field == "data":
            self._data_lines.append(value)
        return None

    def close(self) -> _SSEEvent | None:
        return self._flush()

    def _flush(self) -> _SSEEvent | None:
        if not self._data_lines:
            self._event = None
            return None
        event = _SSEEvent(event=self._event, data="\n".join(self._data_lines))
        self._event = None
        self._data_lines = []
        return event


class _ResponsesStreamAccumulator:
    def __init__(
        self,
        *,
        config: OpenAICompatProviderConfig,
        audit_observer: ProviderAuditObserver | None = None,
    ) -> None:
        self.config = config
        self.audit_observer = audit_observer
        self.response_id: str | None = None
        self.request_id: str | None = None
        self.output_parts: list[str] = []
        self.text_deltas: list[str] = []
        self.events: list[dict[str, object]] = []
        self.stream_started_at = time.monotonic()
        self.last_output_at: float | None = None
        self.first_token_elapsed_sec: float | None = None
        self.max_stream_idle_gap_sec: float | None = None

    def check_timeout(self) -> None:
        now = time.monotonic()
        if self.config.request_total_timeout_sec is not None:
            request_total_budget = float(self.config.request_total_timeout_sec)
            if now - self.stream_started_at > request_total_budget:
                raise OpenAICompatProviderUnavailableError(
                    failure_kind="REQUEST_TOTAL_TIMEOUT",
                    message="Provider stream exceeded the total request timeout.",
                    failure_detail={
                        "provider_response_id": self.response_id,
                        "request_id": self.request_id,
                        "timeout_phase": "request_total",
                        "request_total_timeout_sec": request_total_budget,
                    },
                )
        anchor = self.last_output_at if self.last_output_at is not None else self.stream_started_at
        budget = float(
            (self.config.stream_idle_timeout_sec if self.last_output_at is not None else self.config.first_token_timeout_sec)
            or self.config.timeout_sec
        )
        if now - anchor > budget:
            phase = "stream_idle" if self.last_output_at is not None else "first_token"
            raise OpenAICompatProviderUnavailableError(
                failure_kind="STREAM_IDLE_TIMEOUT" if self.last_output_at is not None else "FIRST_TOKEN_TIMEOUT",
                message=(
                    "Provider stream timed out while waiting for the next output token."
                    if self.last_output_at is not None
                    else "Provider stream timed out while waiting for the first output token."
                ),
                failure_detail={
                    "provider_response_id": self.response_id,
                    "request_id": self.request_id,
                    "timeout_phase": phase,
                },
            )

    def consume_event(self, event: dict[str, object]) -> OpenAICompatProviderResult | None:
        self.check_timeout()
        event_type = str(event.get("type") or "")
        self.response_id = self.response_id or _extract_response_id(event)
        event_request_id = _extract_request_id(event)
        self.request_id = self.request_id or event_request_id
        self.events.append(
            {
                "type": event_type,
                "provider_response_id": _extract_response_id(event),
                "request_id": event_request_id,
            }
        )
        if event_type in {"response.output_text.delta", "response.output_text.done"}:
            delta = _extract_event_delta(event)
            if delta and event_type == "response.output_text.delta":
                self.output_parts.append(delta)
                self.text_deltas.append(delta)
            if delta:
                output_mark = time.monotonic()
                if self.last_output_at is None:
                    self.last_output_at = output_mark
                    self.first_token_elapsed_sec = round(output_mark - self.stream_started_at, 3)
                    if self.audit_observer is not None:
                        self.audit_observer(
                            "first_token_received",
                            {
                                "provider_response_id": self.response_id,
                                "request_id": event_request_id,
                                "streaming": True,
                                "provider_type": self.config.provider_type.value,
                                "first_token_elapsed_sec": self.first_token_elapsed_sec,
                            },
                        )
                else:
                    gap_sec = round(output_mark - self.last_output_at, 3)
                    if self.max_stream_idle_gap_sec is None or gap_sec > self.max_stream_idle_gap_sec:
                        self.max_stream_idle_gap_sec = gap_sec
                    self.last_output_at = output_mark
            return None
        if event_type in {"response.failed", "error"}:
            _raise_from_response_error(event, response_id=self.response_id)
        if event_type == "response.completed":
            if self.audit_observer is not None:
                self.audit_observer(
                    "response_completed",
                    {
                        "provider_response_id": self.response_id,
                        "request_id": event_request_id,
                        "streaming": True,
                        "provider_type": self.config.provider_type.value,
                    },
                )
            return self.build_result(
                _value_from_object(event, "response"),
                finish_state="COMPLETED",
            )
        return None

    def build_result(self, response: object | None = None, *, finish_state: str = "CLOSED") -> OpenAICompatProviderResult:
        result = _build_result_from_response(
            response,
            output_parts=self.output_parts,
            response_id=self.response_id,
            events=tuple(self.events),
            text_deltas=tuple(self.text_deltas),
            finish_state=finish_state,
            request_id=self.request_id,
        )
        events_summary = {
            **dict(result.events_summary),
            "stream_transport": "httpx_sse",
            "first_token_timeout_sec": float(self.config.first_token_timeout_sec or self.config.timeout_sec),
            "stream_idle_timeout_sec": float(self.config.stream_idle_timeout_sec or self.config.timeout_sec),
            "request_total_timeout_sec": self.config.request_total_timeout_sec,
        }
        return OpenAICompatProviderResult(
            **{
                **result.__dict__,
                "first_token_elapsed_sec": self.first_token_elapsed_sec,
                "last_token_elapsed_sec": (
                    round(self.last_output_at - self.stream_started_at, 3) if self.last_output_at is not None else None
                ),
                "max_stream_idle_gap_sec": self.max_stream_idle_gap_sec,
                "events_summary": events_summary,
            }
        )


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


def append_openai_compat_retry_feedback(
    rendered_payload: RenderedExecutionPayload,
    *,
    attempt_no: int,
    failure_kind: str,
    failure_message: str,
) -> RenderedExecutionPayload:
    retry_message = RenderedExecutionMessage(
        role="user",
        channel="OUTPUT_CONTRACT_REMINDER",
        content_type="JSON",
        content_payload={
            "retry_attempt": attempt_no,
            "previous_failure_kind": failure_kind,
            "previous_failure_message": failure_message,
            "rules": [
                "Return exactly one JSON object.",
                "Do not wrap the JSON in markdown code fences.",
                "Do not include any explanatory text before or after the JSON object.",
            ],
        },
    )
    summary = rendered_payload.summary.model_copy(
        update={
            "total_message_count": rendered_payload.summary.total_message_count + 1,
            "control_message_count": rendered_payload.summary.control_message_count + 1,
        }
    )
    return rendered_payload.model_copy(
        update={
            "messages": [*rendered_payload.messages, retry_message],
            "summary": summary,
        }
    )


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
    items, _ = _parse_json_object_sequence_with_error(value)
    return items


def _strip_markdown_code_fence(value: str) -> str:
    stripped = str(value or "").strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _strip_bom(value: str) -> str:
    if value.startswith("\ufeff"):
        return value[1:]
    return value


def _parse_json_object_sequence_with_error(value: str) -> tuple[tuple[dict[str, Any], ...], str | None]:
    decoder = json.JSONDecoder()
    stripped = _strip_bom(_strip_markdown_code_fence(str(value or ""))).strip()
    if not stripped:
        return (), None
    items: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(stripped):
        while cursor < len(stripped) and stripped[cursor].isspace():
            cursor += 1
        if cursor >= len(stripped):
            break
        try:
            parsed, next_cursor = decoder.raw_decode(stripped, cursor)
        except ValueError as exc:
            return (), str(exc)
        if not isinstance(parsed, dict):
            return (), "Provider output JSON root must be an object."
        items.append(dict(parsed))
        cursor = next_cursor
    return tuple(items), None


def _extract_output_items(response_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    output = response_payload.get("output")
    if not isinstance(output, list):
        return ()
    items: list[dict[str, object]] = []
    for item in output:
        if isinstance(item, dict):
            items.append(dict(item))
    return tuple(items)


def _extract_response_parsed_payloads(response_payload: dict[str, object]) -> tuple[dict[str, Any], ...]:
    output_parsed = response_payload.get("output_parsed")
    if isinstance(output_parsed, dict):
        return (dict(output_parsed),)

    output = response_payload.get("output")
    if not isinstance(output, list):
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
    return tuple(payloads)


def _extract_output_payloads(response_payload: dict[str, object]) -> tuple[dict[str, Any], ...]:
    payloads = _extract_response_parsed_payloads(response_payload)
    if payloads:
        return payloads
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
            failure_kind="EMPTY_ASSISTANT_TEXT",
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
        failure_kind="EMPTY_ASSISTANT_TEXT",
        message="Provider response did not contain any assistant text output.",
        failure_detail={
            "provider_response_id": response_payload.get("id"),
        },
    )


def _canonical_json_object(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dedupe_json_objects(payloads: list[dict[str, Any]]) -> tuple[tuple[dict[str, Any], ...], int]:
    unique_payloads: list[dict[str, Any]] = []
    seen_payloads: set[str] = set()
    duplicate_count = 0
    for payload in payloads:
        serialized = _canonical_json_object(payload)
        if serialized in seen_payloads:
            duplicate_count += 1
            continue
        seen_payloads.add(serialized)
        unique_payloads.append(dict(payload))
    return tuple(unique_payloads), duplicate_count


def _build_json_parse_error(
    *,
    output_text: str,
    response_id: str | None,
    request_id: str | None,
    parse_error: str,
) -> OpenAICompatProviderBadResponseError:
    cleaned_output = _strip_bom(_strip_markdown_code_fence(output_text))
    failure_kind = (
        "PROVIDER_MALFORMED_JSON"
        if _looks_like_truncated_json(cleaned_output, parse_error)
        else "PROVIDER_BAD_RESPONSE"
    )
    return OpenAICompatProviderBadResponseError(
        failure_kind=failure_kind,
        message=f"Provider output was not valid JSON: {parse_error}",
        failure_detail={
            "provider_response_id": response_id,
            "request_id": request_id,
            "parse_stage": "json_object_sequence",
            "parse_error": parse_error,
        },
    )


def _looks_like_truncated_json(value: str, parse_error: str) -> bool:
    normalized_error = str(parse_error or "").lower()
    if (
        "unterminated string" in normalized_error
        or "unexpected end" in normalized_error
        or "expecting ',' delimiter" in normalized_error
    ):
        return True

    stack: list[str] = []
    in_string = False
    escaping = False
    for char in value:
        if in_string:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            stack.append(char)
            continue
        if char == "}" and stack and stack[-1] == "{":
            stack.pop()
            continue
        if char == "]" and stack and stack[-1] == "[":
            stack.pop()
            continue

    stripped = value.rstrip()
    return in_string or bool(stack) or stripped.endswith(("{", "[", ",", ":"))


def iter_openai_compat_result_json_objects(
    provider_result: OpenAICompatProviderResult,
) -> tuple[dict[str, Any], ...]:
    candidate_payloads: list[dict[str, Any]] = []

    json_objects = list(getattr(provider_result, "json_objects", ()) or ())
    for item in json_objects:
        if isinstance(item, dict):
            candidate_payloads.append(dict(item))

    selected_payload = getattr(provider_result, "selected_payload", None)
    if isinstance(selected_payload, dict) and not json_objects:
        candidate_payloads.append(dict(selected_payload))

    output_payload = getattr(provider_result, "output_payload", None)
    if isinstance(output_payload, dict):
        candidate_payloads.append(dict(output_payload))

    for item in list(getattr(provider_result, "output_payloads", ()) or ()):
        if isinstance(item, dict):
            candidate_payloads.append(dict(item))

    if candidate_payloads:
        deduped_payloads, _ = _dedupe_json_objects(candidate_payloads)
        return deduped_payloads

    raw_output_text = str(getattr(provider_result, "raw_output_text", "") or getattr(provider_result, "final_text", "") or getattr(provider_result, "output_text", ""))
    parse_error = getattr(provider_result, "json_parse_error", None)
    resolver = OpenAICompatJsonResolver(
        output_text=raw_output_text,
        response_id=getattr(provider_result, "response_id", None),
        request_id=getattr(provider_result, "request_id", None),
    )
    resolved_candidates, fallback_parse_error = resolver.collect_candidates()
    if resolved_candidates:
        return tuple(dict(item.payload) for item in resolved_candidates)
    if parse_error is None:
        parse_error = fallback_parse_error
    if parse_error is not None and raw_output_text.strip():
        raise _build_json_parse_error(
            output_text=raw_output_text,
            response_id=getattr(provider_result, "response_id", None),
            request_id=getattr(provider_result, "request_id", None),
            parse_error=parse_error,
        )
    return ()


def load_openai_compat_result_payload(provider_result: OpenAICompatProviderResult) -> dict[str, Any]:
    return resolve_openai_compat_result_payload(provider_result).payload


def resolve_openai_compat_result_payload(
    provider_result: OpenAICompatProviderResult,
    *,
    payload_resolver: PayloadResolver | None = None,
) -> OpenAICompatResolvedPayload:
    payloads = iter_openai_compat_result_json_objects(provider_result)
    if not payloads:
        raw_output_text = str(
            getattr(provider_result, "raw_output_text", "")
            or getattr(provider_result, "final_text", "")
            or getattr(provider_result, "output_text", "")
        )
        raise OpenAICompatProviderBadResponseError(
            failure_kind="NO_JSON_OBJECT",
            message="Provider result did not include any JSON object payload.",
            failure_detail={
                "provider_response_id": getattr(provider_result, "response_id", None),
                "request_id": getattr(provider_result, "request_id", None),
                "raw_text_length": len(raw_output_text),
                "repair_steps": list(getattr(provider_result, "repair_steps", ()) or ()),
            },
        )

    resolved_candidates: list[tuple[int, dict[str, Any]]] = []
    last_validation_error: str | None = None
    for index, payload in enumerate(payloads):
        candidate = dict(payload)
        try:
            normalized_payload = payload_resolver(candidate) if payload_resolver is not None else candidate
        except ValueError as exc:
            last_validation_error = str(exc)
            continue
        resolved_candidates.append((index, dict(normalized_payload)))

    if payload_resolver is not None and not resolved_candidates:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="SCHEMA_VALIDATION_FAILED",
            message=last_validation_error or "Provider JSON candidates did not satisfy the local schema validator.",
            failure_detail={
                "provider_response_id": getattr(provider_result, "response_id", None),
                "request_id": getattr(provider_result, "request_id", None),
                "json_candidate_count": len(payloads),
                "schema_validation_error": last_validation_error,
                "repair_steps": list(getattr(provider_result, "repair_steps", ()) or ()),
            },
        )

    selected_candidate_index, selected_payload = resolved_candidates[0] if resolved_candidates else (0, dict(payloads[0]))
    return OpenAICompatResolvedPayload(
        payload=selected_payload,
        candidate_count=len(payloads),
        selected_candidate_index=selected_candidate_index,
        ambiguous_candidate_count=max(len(resolved_candidates) - 1, 0),
        repair_steps=tuple(getattr(provider_result, "repair_steps", ()) or ()),
        schema_validation_error=last_validation_error,
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
    return payload


def _sdk_timeout(config: OpenAICompatProviderConfig, *, streaming: bool) -> httpx.Timeout:
    read_timeout_sec: float | None = float(config.request_total_timeout_sec or config.timeout_sec)
    if streaming:
        read_timeout_sec = min(
            float(item)
            for item in (
                config.first_token_timeout_sec,
                config.stream_idle_timeout_sec,
                config.request_total_timeout_sec,
                config.timeout_sec,
            )
            if item is not None and float(item) > 0
        )
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


def _build_result_from_response(
    response: object | None,
    *,
    output_parts: list[str],
    response_id: str | None,
    events: tuple[dict[str, object], ...] = (),
    text_deltas: tuple[str, ...] = (),
    finish_state: str = "COMPLETED",
    request_id: str | None = None,
) -> OpenAICompatProviderResult:
    response_payload = _response_payload(response)
    final_response_id = response_id or (
        str(response_payload.get("id")) if response_payload.get("id") is not None else None
    )
    final_request_id = request_id or _extract_request_id(response)
    output_text = "".join(output_parts).strip()
    if not output_text and response_payload:
        try:
            output_text = _extract_output_text(response_payload)
        except OpenAICompatProviderBadResponseError:
            output_text = ""
    raw_output_text = output_text
    resolver = OpenAICompatJsonResolver(
        output_text=raw_output_text,
        response_id=final_response_id,
        request_id=final_request_id,
    )
    resolved_candidates, parse_error = resolver.collect_candidates()
    json_objects = tuple(dict(item.payload) for item in resolved_candidates)
    duplicate_json_object_count = 0
    selected_payload = dict(json_objects[0]) if json_objects else None
    if not output_text and selected_payload is not None:
        output_text = json.dumps(selected_payload, ensure_ascii=False, sort_keys=True)
        raw_output_text = output_text
    if not output_text:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="EMPTY_ASSISTANT_TEXT",
            message="Provider response did not contain any assistant text output.",
            failure_detail={
                "provider_response_id": final_response_id,
                "request_id": final_request_id,
            },
        )
    items = _extract_output_items(response_payload)
    return OpenAICompatProviderResult(
        output_text=output_text,
        response_id=final_response_id,
        output_payload=selected_payload,
        output_payloads=json_objects,
        events=events,
        items=items,
        text_deltas=text_deltas,
        final_text=output_text,
        json_objects=json_objects,
        selected_payload=selected_payload,
        raw_output_text=raw_output_text,
        finish_state=finish_state,
        request_id=final_request_id,
        duplicate_json_object_count=duplicate_json_object_count,
        selected_payload_index=(0 if selected_payload is not None else None),
        repair_steps=(resolved_candidates[0].repair_steps if resolved_candidates else ()),
        json_parse_error=parse_error,
        raw_text_length=len(raw_output_text),
        events_summary={
            "event_count": len(events),
            "item_count": len(items),
            "text_delta_count": len(text_deltas),
            "json_object_count": len(json_objects),
            "duplicate_json_object_count": duplicate_json_object_count,
            "finish_state": finish_state,
            "raw_text_length": len(raw_output_text),
        },
    )


def _extract_legacy_streaming_responses_output(
    stream: object,
    *,
    config: OpenAICompatProviderConfig,
    audit_observer: ProviderAuditObserver | None = None,
) -> OpenAICompatProviderResult:
    accumulator = _ResponsesStreamAccumulator(config=config, audit_observer=audit_observer)
    try:
        for event in stream:
            event_payload = _response_payload(event)
            if not event_payload:
                event_payload = {
                    key: value
                    for key in ("type", "delta", "text", "response", "error", "request_id", "_request_id")
                    if (value := _value_from_object(event, key)) is not None
                }
            result = accumulator.consume_event(event_payload)
            if result is not None:
                return result
        return accumulator.build_result(finish_state="CLOSED")
    except httpx.TransportError as exc:
        raise _map_stream_transport_error(exc, accumulator=accumulator) from exc


def _parse_sse_event_data(data: str, *, response_id: str | None) -> dict[str, object] | None:
    if data.strip() == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="MALFORMED_STREAM_EVENT",
            message="Provider stream emitted malformed SSE JSON.",
            failure_detail={
                "provider_response_id": response_id,
                "response_error_type": "MalformedSSEJson",
                "response_error_message": str(exc),
                "raw_event_length": len(data),
            },
        ) from exc
    if not isinstance(payload, dict):
        raise OpenAICompatProviderBadResponseError(
            failure_kind="MALFORMED_STREAM_EVENT",
            message="Provider stream emitted a non-object SSE payload.",
            failure_detail={
                "provider_response_id": response_id,
                "response_error_type": "MalformedSSEPayload",
                "raw_event_length": len(data),
            },
        )
    return payload


def _map_stream_transport_error(
    exc: httpx.TransportError,
    *,
    accumulator: _ResponsesStreamAccumulator | None,
) -> OpenAICompatProviderUnavailableError:
    if isinstance(exc, httpx.ConnectTimeout):
        return OpenAICompatProviderUnavailableError(
            failure_kind="CONNECT_TIMEOUT",
            message=str(exc),
            failure_detail={
                "provider_response_id": accumulator.response_id if accumulator is not None else None,
                "request_id": accumulator.request_id if accumulator is not None else None,
                "provider_transport_error": type(exc).__name__,
                "timeout_phase": "connect",
            },
        )
    if isinstance(exc, httpx.TimeoutException):
        phase = "stream_idle" if accumulator is not None and accumulator.last_output_at is not None else "first_token"
        return OpenAICompatProviderUnavailableError(
            failure_kind="STREAM_IDLE_TIMEOUT" if phase == "stream_idle" else "FIRST_TOKEN_TIMEOUT",
            message=str(exc),
            failure_detail={
                "provider_response_id": accumulator.response_id if accumulator is not None else None,
                "request_id": accumulator.request_id if accumulator is not None else None,
                "provider_transport_error": type(exc).__name__,
                "timeout_phase": phase,
            },
        )
    return OpenAICompatProviderUnavailableError(
        failure_kind="UPSTREAM_UNAVAILABLE",
        message=str(exc),
        failure_detail={
            "provider_response_id": accumulator.response_id if accumulator is not None else None,
            "request_id": accumulator.request_id if accumulator is not None else None,
            "provider_transport_error": type(exc).__name__,
        },
    )


def _extract_streaming_responses_output(
    response: httpx.Response,
    *,
    config: OpenAICompatProviderConfig,
    audit_observer: ProviderAuditObserver | None = None,
) -> OpenAICompatProviderResult:
    accumulator = _ResponsesStreamAccumulator(config=config, audit_observer=audit_observer)
    decoder = _SSEDecoder()
    try:
        for line in response.iter_lines():
            accumulator.check_timeout()
            sse_event = decoder.feed_line(line)
            if sse_event is None:
                continue
            payload = _parse_sse_event_data(sse_event.data, response_id=accumulator.response_id)
            if payload is None:
                return accumulator.build_result(finish_state="CLOSED")
            result = accumulator.consume_event(payload)
            if result is not None:
                return result
        sse_event = decoder.close()
        if sse_event is not None:
            payload = _parse_sse_event_data(sse_event.data, response_id=accumulator.response_id)
            if payload is None:
                return accumulator.build_result(finish_state="CLOSED")
            result = accumulator.consume_event(payload)
            if result is not None:
                return result
        return accumulator.build_result(finish_state="CLOSED")
    except httpx.TransportError as exc:
        raise _map_stream_transport_error(exc, accumulator=accumulator) from exc


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
    if class_name == "ConnectTimeout":
        failure_detail["timeout_phase"] = "connect"
        return OpenAICompatProviderUnavailableError(
            failure_kind="CONNECT_TIMEOUT",
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
                "stream_transport": "httpx_sse",
            },
        )
    try:
        if client_factory is not None and transport is None:
            client = _client_for(config, transport=transport, client_factory=client_factory)
            stream = client.responses.create(**_responses_request_payload(config, rendered_payload, stream=True))
            enter = getattr(stream, "__enter__", None)
            exit_ = getattr(stream, "__exit__", None)
            if callable(enter) and callable(exit_):
                with stream:
                    return _extract_legacy_streaming_responses_output(
                        stream,
                        config=config,
                        audit_observer=audit_observer,
                    )
            return _extract_legacy_streaming_responses_output(
                stream,
                config=config,
                audit_observer=audit_observer,
            )

        client = _ResponsesHttpClient(config, transport=transport)
        with client.stream(_responses_request_payload(config, rendered_payload, stream=True)) as response:
            if response.status_code >= 400:
                _map_provider_error_response(response, streaming=True)
            return _extract_streaming_responses_output(
                response,
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
                    "stream_transport": "httpx_sse",
                },
            )
        raise
    except httpx.TransportError as exc:
        mapped = _map_stream_transport_error(exc, accumulator=None)
        if audit_observer is not None:
            audit_observer(
                "request_failed",
                {
                    "failure_kind": mapped.failure_kind,
                    **dict(mapped.failure_detail),
                    "streaming": True,
                    "provider_type": config.provider_type.value,
                    "stream_transport": "httpx_sse",
                },
            )
        raise mapped from exc
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
                    "stream_transport": "httpx_sse",
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
        load_openai_compat_result_payload(result)
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
        load_openai_compat_result_payload(fallback_result)
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
