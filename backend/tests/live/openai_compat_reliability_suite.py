from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
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
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    ARCHITECTURE_BRIEF_SCHEMA_VERSION,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    DETAILED_DESIGN_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_VERSION,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
    MILESTONE_PLAN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_VERSION,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_VERSION,
    get_output_schema_body,
    validate_output_payload,
)
from app.core.provider_openai_compat import (  # noqa: E402
    OpenAICompatProviderBadResponseError,
    OpenAICompatProviderConfig,
    OpenAICompatProviderUnavailableError,
    OpenAICompatProviderType,
    append_openai_compat_retry_feedback,
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
class ReliabilityScenario:
    scenario_id: str
    description: str
    task_prompt: str
    payload_resolver: PayloadResolver
    schema_ref: str
    schema_version: int


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


def _ui_milestone_review_resolver(payload: dict[str, Any]) -> dict[str, Any]:
    validate_output_payload(
        schema_ref="ui_milestone_review",
        schema_version=1,
        submitted_schema_version="ui_milestone_review_v1",
        payload=payload,
    )
    return payload


def _build_rendered_payload(*, scenario: ReliabilityScenario, ordinal: int) -> RenderedExecutionPayload:
    output_contract = get_output_schema_body(scenario.schema_ref, scenario.schema_version)
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id=f"ctx_openai_compat_reliability_{ordinal:02d}",
            compile_id=f"cmp_openai_compat_reliability_{ordinal:02d}",
            compile_request_id=f"creq_openai_compat_reliability_{ordinal:02d}",
            ticket_id=f"tkt_openai_compat_reliability_{ordinal:02d}",
            workflow_id="wf_openai_compat_reliability",
            node_id=f"node_openai_compat_reliability_{ordinal:02d}",
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
                content_payload={
                    "rules": [
                        "Respond in a way that satisfies the task exactly.",
                        "The response must contain a JSON object, even if the task intentionally asks for noisy wrapping.",
                    ]
                },
            ),
            RenderedExecutionMessage(
                role="user",
                channel="TASK_DEFINITION",
                content_type="JSON",
                content_payload={
                    "scenario_id": scenario.scenario_id,
                    "task": scenario.task_prompt,
                    "submitted_schema_version": f"{scenario.schema_ref}_v{scenario.schema_version}",
                    "output_contract": output_contract,
                    "rules": [
                        "Populate every required field with a concrete, non-empty value.",
                        "Return exactly one JSON object unless the task explicitly asks for a noisy wrapper.",
                        "If the task asks for noisy wrapping, still ensure one valid JSON object is present in the response.",
                    ],
                },
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


def _load_provider_config(provider_id: str) -> OpenAICompatProviderConfig:
    from app.config import get_settings

    store = RuntimeProviderConfigStore(Path(get_settings().runtime_provider_config_path))
    config = resolve_runtime_provider_config(store)
    provider = find_provider_entry(config, provider_id)
    if provider is None:
        raise RuntimeError(f"Provider `{provider_id}` was not found in runtime provider config.")
    if not all((provider.base_url, provider.api_key, provider.preferred_model or provider.model)):
        raise RuntimeError(f"Provider `{provider_id}` is missing base_url/api_key/model.")
    return OpenAICompatProviderConfig(
        base_url=str(provider.base_url or ""),
        api_key=str(provider.api_key or ""),
        model=str(provider.preferred_model or provider.model or ""),
        timeout_sec=float(provider.timeout_sec or 300.0),
        connect_timeout_sec=float(provider.connect_timeout_sec or 10.0),
        write_timeout_sec=float(provider.write_timeout_sec or 20.0),
        first_token_timeout_sec=float(provider.first_token_timeout_sec or 300.0),
        stream_idle_timeout_sec=float(provider.stream_idle_timeout_sec or 300.0),
        request_total_timeout_sec=float(provider.request_total_timeout_sec or provider.timeout_sec or 300.0),
        reasoning_effort=provider.reasoning_effort,
        provider_type=OpenAICompatProviderType.RESPONSES_STREAM,
    )


def _scenarios() -> list[ReliabilityScenario]:
    return [
        ReliabilityScenario(
            "architecture_brief",
            "真实治理 schema：architecture_brief",
            "Return one valid architecture_brief_v1 JSON object for a minimalist library workflow.",
            _schema_payload_resolver(ARCHITECTURE_BRIEF_SCHEMA_REF, ARCHITECTURE_BRIEF_SCHEMA_VERSION),
            ARCHITECTURE_BRIEF_SCHEMA_REF,
            ARCHITECTURE_BRIEF_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "technology_decision",
            "真实治理 schema：technology_decision",
            "Return one valid technology_decision_v1 JSON object for a local-first terminal UI app.",
            _schema_payload_resolver(TECHNOLOGY_DECISION_SCHEMA_REF, TECHNOLOGY_DECISION_SCHEMA_VERSION),
            TECHNOLOGY_DECISION_SCHEMA_REF,
            TECHNOLOGY_DECISION_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "milestone_plan",
            "真实治理 schema：milestone_plan",
            "Return one valid milestone_plan_v1 JSON object for a two-week implementation schedule.",
            _schema_payload_resolver(MILESTONE_PLAN_SCHEMA_REF, MILESTONE_PLAN_SCHEMA_VERSION),
            MILESTONE_PLAN_SCHEMA_REF,
            MILESTONE_PLAN_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "detailed_design",
            "真实治理 schema：detailed_design",
            "Return one valid detailed_design_v1 JSON object for a streaming JSON resolver pipeline.",
            _schema_payload_resolver(DETAILED_DESIGN_SCHEMA_REF, DETAILED_DESIGN_SCHEMA_VERSION),
            DETAILED_DESIGN_SCHEMA_REF,
            DETAILED_DESIGN_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "backlog_recommendation",
            "真实治理 schema：backlog_recommendation",
            "Return one valid backlog_recommendation_v1 JSON object for frontend and backend follow-up work.",
            _schema_payload_resolver(BACKLOG_RECOMMENDATION_SCHEMA_REF, BACKLOG_RECOMMENDATION_SCHEMA_VERSION),
            BACKLOG_RECOMMENDATION_SCHEMA_REF,
            BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "maker_checker_verdict",
            "真实治理 schema：maker_checker_verdict",
            "Return one valid maker_checker_verdict_v1 JSON object approving a low-risk change.",
            _schema_payload_resolver(MAKER_CHECKER_VERDICT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_VERSION),
            MAKER_CHECKER_VERDICT_SCHEMA_REF,
            MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "source_code_delivery",
            "真实交付 schema：source_code_delivery",
            "Return one valid source_code_delivery_v1 JSON object for a single-file Python bugfix delivery.",
            _schema_payload_resolver(SOURCE_CODE_DELIVERY_SCHEMA_REF, SOURCE_CODE_DELIVERY_SCHEMA_VERSION),
            SOURCE_CODE_DELIVERY_SCHEMA_REF,
            SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "delivery_closeout_package",
            "真实交付 schema：delivery_closeout_package",
            "Return one valid delivery_closeout_package_v1 JSON object closing out a completed source delivery.",
            _schema_payload_resolver(DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF, DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION),
            DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
            DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
        ),
        ReliabilityScenario(
            "rich_text_wrapper",
            "脏返回：说明文字 + JSON",
            "Return a valid ui_milestone_review_v1 JSON object, but wrap it with one short intro sentence before the JSON.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
        ReliabilityScenario(
            "markdown_code_fence",
            "脏返回：markdown code fence",
            "Return a valid ui_milestone_review_v1 JSON object inside a ```json fenced block.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
        ReliabilityScenario(
            "double_json_sequence",
            "脏返回：两个连续 JSON object，第二个才有效",
            "Return two consecutive JSON objects with no separator. The first must be {'bad': true}. The second must be a valid ui_milestone_review_v1 JSON object.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
        ReliabilityScenario(
            "trailing_comma_json",
            "脏返回：尾逗号 JSON",
            "Return a valid ui_milestone_review_v1 JSON object, but intentionally include trailing commas where JSON parsers usually reject them.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
        ReliabilityScenario(
            "commented_json",
            "脏返回：带注释 JSON",
            "Return a valid ui_milestone_review_v1 JSON object, but include // comments inside the JSON.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
        ReliabilityScenario(
            "single_quote_json",
            "脏返回：单引号伪 JSON",
            "Return a valid ui_milestone_review_v1 object, but write it using single quotes instead of double quotes.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
        ReliabilityScenario(
            "long_text_embedded_json",
            "脏返回：长文本夹一个目标 JSON object",
            "Write one long paragraph explaining the answer, and inside that paragraph embed one valid ui_milestone_review_v1 JSON object exactly once.",
            _ui_milestone_review_resolver,
            "ui_milestone_review",
            1,
        ),
    ]


def run_suite(provider_id: str) -> dict[str, Any]:
    config = _load_provider_config(provider_id)
    scenarios = _scenarios()
    results: list[dict[str, Any]] = []

    for index, scenario in enumerate(scenarios, start=1):
        result_entry: dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "description": scenario.description,
            "status": "FAILED",
        }
        provider_result = None
        last_exception: Exception | None = None
        last_failure_kind = "PROVIDER_BAD_RESPONSE"
        last_failure_message = "Reliability suite request failed."
        for attempt_no in range(1, 4):
            payload = _build_rendered_payload(scenario=scenario, ordinal=index)
            if attempt_no > 1:
                payload = append_openai_compat_retry_feedback(
                    payload,
                    attempt_no=attempt_no,
                    failure_kind=last_failure_kind,
                    failure_message=last_failure_message,
                )
            try:
                provider_result = invoke_openai_compat_response(config, payload)
                resolved = resolve_openai_compat_result_payload(
                    provider_result,
                    payload_resolver=scenario.payload_resolver,
                )
                result_entry.update(
                    {
                        "status": "PASSED",
                        "attempt_count": attempt_no,
                        "response_id": provider_result.response_id,
                        "raw_text_length": provider_result.raw_text_length,
                        "first_token_elapsed_sec": provider_result.first_token_elapsed_sec,
                        "last_token_elapsed_sec": provider_result.last_token_elapsed_sec,
                        "json_candidate_count": resolved.candidate_count,
                        "selected_candidate_index": resolved.selected_candidate_index,
                        "ambiguous_candidate_count": resolved.ambiguous_candidate_count,
                        "repair_steps": list(resolved.repair_steps),
                    }
                )
                last_exception = None
                break
            except (OpenAICompatProviderBadResponseError, OpenAICompatProviderUnavailableError) as exc:
                last_exception = exc
                last_failure_kind = exc.failure_kind
                last_failure_message = str(exc)
                if attempt_no >= 3:
                    break
        if last_exception is not None:
            exc = last_exception
            detail = dict(getattr(exc, "failure_detail", {}) or {})
            if provider_result is not None:
                detail.setdefault("first_token_elapsed_sec", provider_result.first_token_elapsed_sec)
                detail.setdefault("last_token_elapsed_sec", provider_result.last_token_elapsed_sec)
                detail.setdefault("raw_text_length", provider_result.raw_text_length)
            result_entry.update(
                {
                    "attempt_count": 3,
                    "failure_kind": getattr(exc, "failure_kind", type(exc).__name__),
                    "failure_message": str(exc),
                    "failure_detail": detail,
                }
            )
        results.append(result_entry)

    passed = len([item for item in results if item["status"] == "PASSED"])
    return {
        "provider_id": provider_id,
        "scenario_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "success_threshold_met": passed >= 14,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OpenAI-compat streaming JSON reliability suite.")
    parser.add_argument("--provider-id", default="prov_openai_compat", help="Runtime provider id to use.")
    parser.add_argument("--output", default="", help="Optional JSON report output path.")
    args = parser.parse_args()

    report = run_suite(args.provider_id)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["success_threshold_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
