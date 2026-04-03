from __future__ import annotations

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.ids import new_prefixed_id
from app.core.time import now_local


CEO_SHADOW_PROMPT_VERSION = "ceo_shadow_v1"


def build_ceo_shadow_system_prompt() -> str:
    return (
        "You are the Boardroom OS CEO in shadow mode.\n"
        "You read the current workflow snapshot and propose controlled actions only.\n"
        "You do not execute actions and you do not rewrite workflow history.\n"
        "Prefer the smallest useful next step.\n"
        "If the workflow is blocked by board review or incident, usually return NO_ACTION.\n"
        "Return strict JSON matching ceo_action_batch_v1 with a short summary and actions array.\n"
        "Supported actions: CREATE_TICKET, RETRY_TICKET, HIRE_EMPLOYEE, ESCALATE_TO_BOARD, NO_ACTION."
    )


def build_ceo_shadow_rendered_payload(snapshot: dict) -> RenderedExecutionPayload:
    rendered_at = now_local()
    workflow = snapshot["workflow"]
    trigger = snapshot["trigger"]
    messages = [
        RenderedExecutionMessage(
            role="system",
            channel="SYSTEM_CONTROLS",
            content_type="TEXT",
            content_payload={"text": build_ceo_shadow_system_prompt()},
        ),
        RenderedExecutionMessage(
            role="user",
            channel="TASK_DEFINITION",
            content_type="JSON",
            content_payload={
                "task": "Review the workflow snapshot and propose the next controlled CEO actions.",
                "shadow_mode": True,
                "prompt_version": CEO_SHADOW_PROMPT_VERSION,
            },
        ),
        RenderedExecutionMessage(
            role="user",
            channel="CONTEXT_BLOCK",
            content_type="JSON",
            content_payload=snapshot,
            block_id=f"ceo_shadow_snapshot:{workflow['workflow_id']}",
            source_ref=trigger.get("trigger_ref") or workflow["workflow_id"],
        ),
        RenderedExecutionMessage(
            role="user",
            channel="OUTPUT_CONTRACT_REMINDER",
            content_type="JSON",
            content_payload={
                "output_schema_ref": "ceo_action_batch",
                "output_schema_version": 1,
                "must_output_json_only": True,
            },
        ),
    ]
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id=new_prefixed_id("ctx"),
            compile_id=new_prefixed_id("manifest"),
            compile_request_id=new_prefixed_id("compile"),
            ticket_id=f"ceo-shadow-{workflow['workflow_id']}",
            workflow_id=workflow["workflow_id"],
            node_id="node_ceo_shadow",
            compiler_version=CEO_SHADOW_PROMPT_VERSION,
            model_profile="ceo_shadow",
            render_target="json_messages_v1",
            rendered_at=rendered_at,
        ),
        messages=messages,
        summary=RenderedExecutionPayloadSummary(
            total_message_count=len(messages),
            control_message_count=1,
            data_message_count=3,
            retrieval_message_count=0,
            degraded_data_message_count=0,
            reference_message_count=0,
        ),
    )

