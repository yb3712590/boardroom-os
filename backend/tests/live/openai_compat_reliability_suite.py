from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.runtime import (  # noqa: E402
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.output_schemas import (  # noqa: E402
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
    get_output_schema_body,
    validate_output_payload,
)
from app.core.provider_openai_compat import (  # noqa: E402
    OpenAICompatProviderConfig,
    OpenAICompatProviderType,
    ProviderEvent,
    ProviderEventType,
    invoke_openai_compat_response,
    resolve_openai_compat_result_payload,
)
from app.core.runtime_provider_config import (  # noqa: E402
    RuntimeProviderConfigStore,
    find_provider_entry,
    resolve_runtime_provider_config,
)


PayloadResolver = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SmokePrompt:
    prompt_id: str
    description: str
    task_prompt: str
    schema_ref: str | None = None
    schema_version: int | None = None
    payload_resolver: PayloadResolver | None = None


@dataclass(frozen=True)
class ProviderIdentity:
    preferred_provider_id: str
    preferred_model: str
    actual_provider_id: str
    actual_model: str


def _schema_payload_resolver(schema_ref: str, schema_version: int) -> PayloadResolver:
    expected_schema_id = f"{schema_ref}_v{schema_version}"

    def _resolver(payload: dict[str, Any]) -> dict[str, Any]:
        validate_output_payload(
            schema_ref=schema_ref,
            schema_version=schema_version,
            submitted_schema_version=expected_schema_id,
            payload=payload,
        )
        return payload

    return _resolver


def _load_provider_identity_and_config(provider_id: str) -> tuple[ProviderIdentity, OpenAICompatProviderConfig]:
    from app.config import get_settings

    store = RuntimeProviderConfigStore(Path(get_settings().runtime_provider_config_path))
    config = resolve_runtime_provider_config(store)
    provider = find_provider_entry(config, provider_id)
    if provider is None:
        raise RuntimeError(f"Provider `{provider_id}` was not found in runtime provider config.")
    preferred_model = str(provider.preferred_model or provider.model or "").strip()
    if not all((provider.base_url, provider.api_key, preferred_model)):
        raise RuntimeError(f"Provider `{provider_id}` is missing base_url/api_key/model.")
    identity = ProviderIdentity(
        preferred_provider_id=provider.provider_id,
        preferred_model=preferred_model,
        actual_provider_id=provider.provider_id,
        actual_model=preferred_model,
    )
    provider_config = OpenAICompatProviderConfig(
        base_url=str(provider.base_url or ""),
        api_key=str(provider.api_key or ""),
        model=preferred_model,
        timeout_sec=float(provider.timeout_sec or 300.0),
        connect_timeout_sec=float(provider.connect_timeout_sec or 10.0),
        write_timeout_sec=float(provider.write_timeout_sec or 20.0),
        first_token_timeout_sec=float(provider.first_token_timeout_sec or 300.0),
        stream_idle_timeout_sec=float(provider.stream_idle_timeout_sec or 300.0),
        request_total_timeout_sec=(
            float(provider.request_total_timeout_sec)
            if provider.request_total_timeout_sec is not None
            else None
        ),
        reasoning_effort=provider.reasoning_effort,
        provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
    )
    return identity, provider_config


def _smoke_prompts() -> tuple[SmokePrompt, ...]:
    return (
        SmokePrompt(
            prompt_id="small",
            description="small streaming prompt",
            task_prompt="Return one compact JSON object with keys status and summary confirming provider streaming works.",
        ),
        SmokePrompt(
            prompt_id="medium",
            description="medium streaming prompt",
            task_prompt=(
                "Return one JSON object with keys status, summary, observations, and next_steps. "
                "Use five observations and five next_steps about validating an AI provider adapter."
            ),
        ),
        SmokePrompt(
            prompt_id="schema",
            description="schema validation prompt",
            task_prompt="Return one valid maker_checker_verdict_v1 JSON object approving a low-risk provider smoke result.",
            schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
            schema_version=MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
            payload_resolver=_schema_payload_resolver(
                MAKER_CHECKER_VERDICT_SCHEMA_REF,
                MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
            ),
        ),
    )


def _prompt_for_attempt(attempt_no: int) -> SmokePrompt:
    prompts = _smoke_prompts()
    return prompts[(attempt_no - 1) % len(prompts)]


def _build_rendered_payload(*, prompt: SmokePrompt, ordinal: int, long_request: bool = False) -> RenderedExecutionPayload:
    output_contract = (
        get_output_schema_body(prompt.schema_ref, prompt.schema_version)
        if prompt.schema_ref is not None and prompt.schema_version is not None
        else None
    )
    task_prompt = prompt.task_prompt
    if long_request:
        task_prompt = (
            "Return one JSON object with keys status, summary, sections, and closing_note. "
            "The sections array must contain 80 objects. Each object must have keys index, title, and details. "
            "Each details value must be a detailed paragraph about provider streaming stability, timeout attribution, "
            "schema validation, and parser observability."
        )
    content_payload: dict[str, Any] = {
        "prompt_id": prompt.prompt_id,
        "task": task_prompt,
        "rules": [
            "Return exactly one JSON object.",
            "Do not wrap the JSON in markdown code fences.",
            "Do not include explanatory text before or after the JSON object.",
        ],
    }
    if output_contract is not None:
        content_payload["submitted_schema_version"] = f"{prompt.schema_ref}_v{prompt.schema_version}"
        content_payload["output_contract"] = output_contract
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id=f"ctx_provider_streaming_smoke_{ordinal:02d}",
            compile_id=f"cmp_provider_streaming_smoke_{ordinal:02d}",
            compile_request_id=f"creq_provider_streaming_smoke_{ordinal:02d}",
            ticket_id=f"provider_smoke_{ordinal:02d}",
            workflow_id="provider_streaming_smoke_no_workflow",
            node_id=f"provider_smoke_node_{ordinal:02d}",
            compiler_version="provider-smoke.v1",
            model_profile="boardroom_os.provider_smoke",
            render_target="json_messages_v1",
            rendered_at=datetime.now().astimezone(),
        ),
        messages=[
            RenderedExecutionMessage(
                role="system",
                channel="SYSTEM_CONTROLS",
                content_type="JSON",
                content_payload={"rules": ["return JSON only", "stream the response normally"]},
            ),
            RenderedExecutionMessage(
                role="user",
                channel="TASK_DEFINITION",
                content_type="JSON",
                content_payload=content_payload,
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



def _provider_event_report(events: tuple[ProviderEvent, ...]) -> list[dict[str, Any]]:
    return [
        {
            "type": event.type.value,
            "provider_name": event.provider_name,
            "model": event.model,
            "request_id": event.request_id,
            "attempt_id": event.attempt_id,
            "monotonic_ts": event.monotonic_ts,
            "raw_byte_count": event.raw_byte_count,
            "text_char_count": event.text_char_count,
            "error_category": event.error_category,
            "response_id": event.response_id,
            "metadata": dict(event.metadata),
        }
        for event in events
    ]


def _provider_event_metrics(events: tuple[ProviderEvent, ...]) -> dict[str, Any]:
    request_started = next((event for event in events if event.type == ProviderEventType.REQUEST_STARTED), None)
    first_token = next((event for event in events if event.type == ProviderEventType.FIRST_TOKEN), None)
    content_events = [event for event in events if event.type == ProviderEventType.CONTENT_DELTA]
    failed_event = next(
        (
            event
            for event in reversed(events)
            if event.type in {ProviderEventType.FAILED_RETRYABLE, ProviderEventType.FAILED_TERMINAL}
        ),
        None,
    )
    idle_gap_sec = None
    if len(content_events) >= 2:
        idle_gap_sec = round(
            max(
                content_events[index].monotonic_ts - content_events[index - 1].monotonic_ts
                for index in range(1, len(content_events))
            ),
            3,
        )
    return {
        "first_token_elapsed_sec": (
            round(first_token.monotonic_ts - request_started.monotonic_ts, 3)
            if first_token is not None and request_started is not None
            else None
        ),
        "max_stream_idle_gap_sec": idle_gap_sec,
        "stream_text_char_count": sum(event.text_char_count for event in content_events),
        "stream_byte_count": sum(event.raw_byte_count for event in content_events),
        "failure_category": failed_event.error_category if failed_event is not None else None,
        "provider_events": _provider_event_report(events),
    }



def _classify_exception(exc: Exception) -> tuple[str, dict[str, Any]]:
    failure_kind = str(getattr(exc, "failure_kind", type(exc).__name__))
    detail = dict(getattr(exc, "failure_detail", {}) or {})
    return failure_kind, detail


def _run_smoke_attempt(
    *,
    identity: ProviderIdentity,
    config: OpenAICompatProviderConfig,
    prompt: SmokePrompt,
    ordinal: int,
    long_request: bool = False,
) -> dict[str, Any]:
    started_at = time.monotonic()
    audit_events: list[dict[str, Any]] = []

    def observe(event_type: str, payload: dict[str, object]) -> None:
        audit_events.append({"event_type": event_type, "payload": dict(payload)})

    result_entry: dict[str, Any] = {
        "attempt_no": ordinal,
        "prompt_id": prompt.prompt_id,
        "description": prompt.description,
        "status": "FAILED",
        "preferred_provider_id": identity.preferred_provider_id,
        "preferred_model": identity.preferred_model,
        "actual_provider_id": identity.actual_provider_id,
        "actual_model": identity.actual_model,
        "timeout_contract": {
            "connect_timeout_sec": config.connect_timeout_sec,
            "first_token_timeout_sec": config.first_token_timeout_sec,
            "stream_idle_timeout_sec": config.stream_idle_timeout_sec,
            "request_total_timeout_sec": config.request_total_timeout_sec,
            "ticket_lease_timeout": "not_applicable_provider_smoke",
        },
    }
    try:
        provider_result = invoke_openai_compat_response(
            config,
            _build_rendered_payload(prompt=prompt, ordinal=ordinal, long_request=long_request),
            audit_observer=observe,
        )
        resolved = resolve_openai_compat_result_payload(
            provider_result,
            payload_resolver=prompt.payload_resolver,
        )
        duration_sec = round(time.monotonic() - started_at, 3)
        event_metrics = _provider_event_metrics(tuple(provider_result.provider_events))
        result_entry.update(
            {
                "status": "PASSED",
                "response_id": provider_result.response_id,
                "request_id": provider_result.request_id,
                "first_token_elapsed_sec": event_metrics["first_token_elapsed_sec"],
                "max_stream_idle_gap_sec": event_metrics["max_stream_idle_gap_sec"],
                "total_duration_sec": duration_sec,
                "raw_text_length": provider_result.raw_text_length,
                "text_delta_count": len(provider_result.text_deltas),
                "stream_text_char_count": event_metrics["stream_text_char_count"],
                "stream_byte_count": event_metrics["stream_byte_count"],
                "failure_category": event_metrics["failure_category"],
                "json_candidate_count": resolved.candidate_count,
                "selected_candidate_index": resolved.selected_candidate_index,
                "ambiguous_candidate_count": resolved.ambiguous_candidate_count,
                "repair_steps": list(resolved.repair_steps),
                "schema_validation_error": resolved.schema_validation_error,
                "provider_events": event_metrics["provider_events"],
                "provider_attempt_count": provider_result.provider_attempt_count,
                "audit_events": audit_events,
            }
        )
    except Exception as exc:
        duration_sec = round(time.monotonic() - started_at, 3)
        failure_kind, detail = _classify_exception(exc)
        failure_events = tuple(getattr(exc, "provider_events", ()) or ())
        event_metrics = _provider_event_metrics(failure_events)
        result_entry.update(
            {
                "status": "FAILED",
                "failure_kind": failure_kind,
                "failure_category": event_metrics["failure_category"] or failure_kind,
                "failure_message": str(exc),
                "failure_detail": detail,
                "total_duration_sec": duration_sec,
                "provider_events": event_metrics["provider_events"],
                "provider_attempt_count": getattr(exc, "provider_attempt_count", None),
                "audit_events": audit_events,
            }
        )
    return result_entry


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return ordered[index]


def run_suite(
    provider_id: str,
    *,
    include_long_request: bool = False,
    long_request_total_timeout_sec: float = 900.0,
) -> dict[str, Any]:
    identity, config = _load_provider_identity_and_config(provider_id)
    results: list[dict[str, Any]] = []
    for attempt_no in range(1, 21):
        results.append(
            _run_smoke_attempt(
                identity=identity,
                config=config,
                prompt=_prompt_for_attempt(attempt_no),
                ordinal=attempt_no,
            )
        )

    if include_long_request:
        long_config = replace(
            config,
            request_total_timeout_sec=float(long_request_total_timeout_sec),
        )
        results.append(
            _run_smoke_attempt(
                identity=identity,
                config=long_config,
                prompt=SmokePrompt(
                    prompt_id="long_request",
                    description="optional long streaming request",
                    task_prompt="long request placeholder replaced by builder",
                ),
                ordinal=21,
                long_request=True,
            )
        )

    passed = len([item for item in results if item["status"] == "PASSED"])
    short_results = results[:20]
    short_passed = len([item for item in short_results if item["status"] == "PASSED"])
    first_token_latencies = [
        float(item["first_token_elapsed_sec"])
        for item in short_results
        if item.get("first_token_elapsed_sec") is not None
    ]
    idle_gaps = [
        float(item["max_stream_idle_gap_sec"])
        for item in short_results
        if item.get("max_stream_idle_gap_sec") is not None
    ]
    failure_counts: dict[str, int] = {}
    for item in results:
        if item["status"] == "PASSED":
            continue
        failure_kind = str(item.get("failure_kind") or "UNKNOWN_FAILURE")
        failure_counts[failure_kind] = failure_counts.get(failure_kind, 0) + 1

    return {
        "suite_id": "openai_compat_provider_streaming_contract_smoke",
        "provider_id": provider_id,
        "preferred_provider_id": identity.preferred_provider_id,
        "preferred_model": identity.preferred_model,
        "actual_provider_id": identity.actual_provider_id,
        "actual_model": identity.actual_model,
        "short_attempt_count": 20,
        "scenario_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "short_passed_count": short_passed,
        "short_success_rate": short_passed / 20,
        "success_threshold_met": short_passed >= 19,
        "first_token_p95_sec": _p95(first_token_latencies),
        "stream_idle_gap_p95_sec": _p95(idle_gaps),
        "failure_counts": failure_counts,
        "ticket_lease_timeout": "not_applicable_provider_smoke",
        "long_request_included": include_long_request,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OpenAI-compat provider-only streaming contract smoke.")
    parser.add_argument("--provider-id", default="prov_openai_compat", help="Runtime provider id to use.")
    parser.add_argument("--output", default="", help="Optional JSON report output path.")
    parser.add_argument(
        "--include-long-request",
        action="store_true",
        help="Run one optional long streaming request after the 20 short attempts.",
    )
    parser.add_argument(
        "--long-request-total-timeout-sec",
        type=float,
        default=900.0,
        help="request_total_timeout_sec used only for --include-long-request.",
    )
    args = parser.parse_args()

    report = run_suite(
        args.provider_id,
        include_long_request=args.include_long_request,
        long_request_total_timeout_sec=args.long_request_total_timeout_sec,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["success_threshold_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
