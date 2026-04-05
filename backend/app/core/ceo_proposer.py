from __future__ import annotations

import json
from dataclasses import dataclass

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
    CEOCreateTicketAction,
    CEOCreateTicketPayload,
    CEORequestMeetingAction,
    CEORequestMeetingPayload,
    CEONoAction,
    CEONoActionPayload,
)
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_project_init_scope_summary,
)
from app.core.ceo_prompts import build_ceo_shadow_rendered_payload
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED
from app.core.provider_openai_compat import (
    OpenAICompatProviderConfig,
    OpenAICompatProviderError,
    invoke_openai_compat_response,
)
from app.core.runtime_provider_config import (
    RuntimeProviderConfigStore,
    resolve_runtime_provider_config,
    runtime_provider_effective_mode,
    runtime_provider_health_summary,
)
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class CEOProposalResult:
    action_batch: CEOActionBatch
    effective_mode: str
    provider_health_summary: str
    model: str | None
    provider_response_id: str | None = None
    fallback_reason: str | None = None


def build_no_action_batch(reason: str) -> CEOActionBatch:
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEONoAction(
                action_type="NO_ACTION",
                payload=CEONoActionPayload(reason=reason),
            )
        ],
    )


def _should_fallback_to_project_init_scope_kickoff(snapshot: dict) -> bool:
    trigger = snapshot.get("trigger") or {}
    ticket_summary = snapshot.get("ticket_summary") or {}
    return (
        str(trigger.get("trigger_type") or "") == EVENT_BOARD_DIRECTIVE_RECEIVED
        and int(ticket_summary.get("total") or 0) == 0
        and not snapshot.get("approvals")
        and not snapshot.get("incidents")
    )


def _build_project_init_scope_kickoff_batch(snapshot: dict, reason: str) -> CEOActionBatch:
    workflow = snapshot.get("workflow") or {}
    north_star_goal = str(workflow.get("north_star_goal") or workflow.get("title") or "").strip()
    summary = build_project_init_scope_summary(north_star_goal)
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEOCreateTicketAction(
                action_type=CEOActionType.CREATE_TICKET,
                payload=CEOCreateTicketPayload(
                    workflow_id=str(workflow["workflow_id"]),
                    node_id=PROJECT_INIT_SCOPE_NODE_ID,
                    role_profile_ref="ui_designer_primary",
                    output_schema_ref="consensus_document",
                    summary=summary,
                    parent_ticket_id=None,
                ),
            )
        ],
    )


def _eligible_meeting_candidates(snapshot: dict) -> list[dict]:
    return [
        item
        for item in snapshot.get("meeting_candidates") or []
        if bool(item.get("eligible"))
    ]


def _build_request_meeting_batch(candidate: dict, reason: str) -> CEOActionBatch:
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEORequestMeetingAction(
                action_type=CEOActionType.REQUEST_MEETING,
                payload=CEORequestMeetingPayload(
                    workflow_id=str(candidate["workflow_id"]),
                    meeting_type="TECHNICAL_DECISION",
                    source_node_id=str(candidate["source_node_id"]),
                    source_ticket_id=str(candidate["source_ticket_id"]),
                    topic=str(candidate["topic"]),
                    participant_employee_ids=list(candidate.get("participant_employee_ids") or []),
                    recorder_employee_id=str(candidate["recorder_employee_id"]),
                    input_artifact_refs=list(candidate.get("input_artifact_refs") or []),
                    reason=str(candidate["reason"]),
                ),
            )
        ],
    )


def build_deterministic_fallback_batch(snapshot: dict, reason: str) -> CEOActionBatch:
    if _should_fallback_to_project_init_scope_kickoff(snapshot):
        return _build_project_init_scope_kickoff_batch(snapshot, reason)
    eligible_meeting_candidates = _eligible_meeting_candidates(snapshot)
    if len(eligible_meeting_candidates) == 1:
        candidate = {
            **eligible_meeting_candidates[0],
            "workflow_id": str((snapshot.get("workflow") or {}).get("workflow_id") or ""),
        }
        return _build_request_meeting_batch(
            candidate,
            reason=(
                "Open one bounded technical decision meeting because the snapshot exposes a single eligible candidate."
            ),
        )
    return build_no_action_batch(reason)


def propose_ceo_action_batch(
    repository: ControlPlaneRepository,
    *,
    snapshot: dict,
    runtime_provider_store: RuntimeProviderConfigStore | None = None,
) -> CEOProposalResult:
    config = resolve_runtime_provider_config(runtime_provider_store)
    effective_mode, effective_reason = runtime_provider_effective_mode(config, repository)
    provider_health_summary = runtime_provider_health_summary(config, repository)
    if effective_mode != "OPENAI_COMPAT_LIVE":
        return CEOProposalResult(
            action_batch=build_deterministic_fallback_batch(snapshot, effective_reason),
            effective_mode=effective_mode,
            provider_health_summary=provider_health_summary,
            model=config.model,
            fallback_reason=effective_reason,
        )

    if config.base_url is None or config.api_key is None or config.model is None:
        fallback_reason = "OpenAI-compatible provider config is incomplete for CEO shadow mode."
        return CEOProposalResult(
            action_batch=build_deterministic_fallback_batch(snapshot, fallback_reason),
            effective_mode=effective_mode,
            provider_health_summary=provider_health_summary,
            model=config.model,
            fallback_reason=fallback_reason,
        )

    try:
        provider_result = invoke_openai_compat_response(
            OpenAICompatProviderConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                timeout_sec=config.timeout_sec,
                reasoning_effort=config.reasoning_effort,
            ),
            build_ceo_shadow_rendered_payload(snapshot),
        )
        payload = json.loads(provider_result.output_text)
        action_batch = CEOActionBatch.model_validate(payload)
        return CEOProposalResult(
            action_batch=action_batch,
            effective_mode=effective_mode,
            provider_health_summary=provider_health_summary,
            model=config.model,
            provider_response_id=provider_result.response_id,
        )
    except (OpenAICompatProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
        fallback_reason = str(exc)
        return CEOProposalResult(
            action_batch=build_deterministic_fallback_batch(snapshot, fallback_reason),
            effective_mode=effective_mode,
            provider_health_summary=provider_health_summary,
            model=config.model,
            fallback_reason=fallback_reason,
        )
