from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    DeliveryStage,
    DeveloperInspectorRefs,
    TicketBoardReviewRequest,
    TicketReviewEvidence,
    TicketResultStatus,
    TicketResultSubmitCommand,
    TicketWrittenArtifact,
    TicketStartCommand,
)
from app.contracts.runtime import CompiledAuditArtifacts, CompiledExecutionPackage
from app.core.context_compiler import (
    MINIMAL_CONTEXT_COMPILER_VERSION,
    compile_and_persist_execution_artifacts,
    export_latest_compile_artifacts_to_developer_inspector,
)
from app.core.constants import (
    EVENT_MEETING_CONCLUDED,
    EVENT_MEETING_ROUND_COMPLETED,
    PROVIDER_PAUSE_FAILURE_KINDS,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    schema_id,
    validate_output_payload,
)
from app.core.provider_openai_compat import (
    OpenAICompatProviderAuthError,
    OpenAICompatProviderBadResponseError,
    OpenAICompatProviderConfig,
    OpenAICompatProviderRateLimitedError,
    OpenAICompatProviderUnavailableError,
    invoke_openai_compat_response,
)
from app.core.provider_claude_code import ClaudeCodeProviderConfig, ClaudeCodeProviderError, invoke_claude_code_response
from app.core.runtime_provider_config import (
    RuntimeProviderAdapterKind,
    RuntimeProviderSelection,
    resolve_provider_failover_selections,
    resolve_provider_selection,
    resolve_runtime_provider_config,
)
from app.core.execution_targets import resolve_execution_target_ref_from_ticket_spec
from app.core.ticket_context_archive import write_ticket_context_markdown
from app.core.ticket_handlers import (
    _open_provider_incident,
    handle_ticket_result_submit,
    handle_ticket_start,
)
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class RuntimeExecutionResult:
    result_status: str
    completion_summary: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    result_payload: dict[str, Any] = field(default_factory=dict)
    written_artifacts: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    confidence: float = 0.0
    failure_kind: str | None = None
    failure_message: str | None = None
    failure_detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeExecutionOutcome:
    ticket_id: str
    lease_owner: str
    start_ack: CommandAckEnvelope
    final_ack: CommandAckEnvelope | None


SUPPORTED_RUNTIME_OUTPUT_SCHEMAS = {
    "ui_milestone_review",
    "maker_checker_verdict",
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    *GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
}
SUPPORTED_RUNTIME_ROLE_PROFILES = {
    "ui_designer_primary",
    "frontend_engineer_primary",
    "checker_primary",
    "backend_engineer_primary",
    "database_engineer_primary",
    "platform_sre_primary",
    "architect_primary",
    "cto_primary",
}
OPENAI_COMPAT_PROVIDER_ID = "prov_openai_compat"
PROVIDER_MAX_ATTEMPTS = 3
PROVIDER_RETRY_BACKOFF_BASE_SEC = 1.0
PROVIDER_RETRY_BACKOFF_MAX_SEC = 8.0
PROVIDER_FAILOVER_FAILURE_KINDS = {"PROVIDER_RATE_LIMITED", "UPSTREAM_UNAVAILABLE"}
_sleep = time.sleep


def _runtime_sort_key(ticket: dict[str, Any]) -> tuple:
    return ticket["updated_at"], ticket["ticket_id"]


def _build_start_idempotency_key(ticket: dict[str, Any]) -> str:
    return f"runtime-start:{ticket['workflow_id']}:{ticket['ticket_id']}:{ticket['lease_owner']}"


def _build_result_submit_idempotency_key(ticket: dict[str, Any], result_status: str) -> str:
    return f"runtime-result-submit:{ticket['workflow_id']}:{ticket['ticket_id']}:{result_status}"


def _build_runtime_developer_inspector_refs(ticket_id: str) -> DeveloperInspectorRefs:
    return DeveloperInspectorRefs(
        compiled_context_bundle_ref=f"ctx://compile/{ticket_id}",
        compile_manifest_ref=f"manifest://compile/{ticket_id}",
        rendered_execution_payload_ref=f"render://compile/{ticket_id}",
    )


def _build_provider_selection_assumptions(
    *,
    execution_package: CompiledExecutionPackage,
    selection: RuntimeProviderSelection,
    provider_response_id: str | None,
    provider_attempt_count: int,
) -> list[str]:
    return [
        f"compiler_version={execution_package.meta.compiler_version}",
        f"compile_request_id={execution_package.meta.compile_request_id}",
        f"preferred_provider_id={selection.preferred_provider_id}",
        f"preferred_model={selection.preferred_model or selection.provider.model or 'unknown'}",
        f"actual_provider_id={selection.provider.provider_id}",
        f"actual_model={selection.actual_model or selection.provider.model or 'unknown'}",
        f"effective_reasoning_effort={selection.effective_reasoning_effort}",
        f"selection_reason={selection.selection_reason or 'provider_selection'}",
        f"policy_reason={selection.policy_reason or 'none'}",
        f"adapter_kind={selection.provider.adapter_kind}",
        f"provider_response_id={provider_response_id or 'unknown'}",
        f"provider_attempt_count={provider_attempt_count}",
    ]


def _resolve_ticket_provider_id(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
) -> str | None:
    lease_owner = ticket.get("lease_owner")
    if lease_owner is None:
        return None
    employee = repository.get_employee_projection(str(lease_owner))
    if employee is None or not employee.get("provider_id"):
        return None
    return str(employee["provider_id"])


def _is_provider_paused_for_ticket(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
) -> bool:
    provider_id = _resolve_ticket_provider_id(repository, ticket)
    if not provider_id:
        return False
    return repository.has_open_circuit_breaker_for_provider(str(provider_id))


def _list_runtime_startable_leased_tickets(
    repository: ControlPlaneRepository,
) -> list[dict[str, Any]]:
    now = now_local()
    leased_tickets = repository.list_ticket_projections_by_statuses_readonly(["LEASED"])
    runnable_tickets = []
    for ticket in leased_tickets:
        lease_owner = ticket.get("lease_owner")
        lease_expires_at = ticket.get("lease_expires_at")
        if lease_owner is None or lease_expires_at is None or lease_expires_at <= now:
            continue
        node_projection = repository.get_current_node_projection(ticket["workflow_id"], ticket["node_id"])
        if node_projection is None:
            continue
        if node_projection["latest_ticket_id"] != ticket["ticket_id"] or node_projection["status"] != "PENDING":
            continue
        runnable_tickets.append(ticket)
    return sorted(runnable_tickets, key=_runtime_sort_key)


def _build_compiled_execution_artifacts(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
) -> CompiledAuditArtifacts:
    return compile_and_persist_execution_artifacts(repository, ticket)


def _resolve_runtime_write_path(allowed_write_pattern: str, filename: str) -> str:
    if "*" in allowed_write_pattern:
        return allowed_write_pattern.replace("*", filename, 1)
    normalized = allowed_write_pattern.rstrip("/")
    if not normalized:
        return filename
    return f"{normalized}/{filename}"


def _build_runtime_default_artifacts(
    execution_package: CompiledExecutionPackage,
    result_payload: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    ticket_id = execution_package.meta.ticket_id
    output_schema_ref = execution_package.execution.output_schema_ref
    if output_schema_ref in {
        CONSENSUS_DOCUMENT_SCHEMA_REF,
        *GOVERNANCE_DOCUMENT_SCHEMA_REFS,
        IMPLEMENTATION_BUNDLE_SCHEMA_REF,
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    }:
        filename_by_schema = {
            CONSENSUS_DOCUMENT_SCHEMA_REF: "consensus-document.json",
            **{
                schema_ref: f"{schema_ref}.json"
                for schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS
            },
            IMPLEMENTATION_BUNDLE_SCHEMA_REF: "implementation-bundle.json",
            DELIVERY_CHECK_REPORT_SCHEMA_REF: "delivery-check-report.json",
            DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF: "delivery-closeout-package.json",
        }
        artifact_ref = f"art://runtime/{ticket_id}/{filename_by_schema[output_schema_ref]}"
        allowed_write_set = list(execution_package.execution.allowed_write_set)
        if not allowed_write_set:
            return [artifact_ref], []
        write_pattern = allowed_write_set[0]
        return [artifact_ref], [
            {
                "path": _resolve_runtime_write_path(write_pattern, filename_by_schema[output_schema_ref]),
                "artifact_ref": artifact_ref,
                "kind": "JSON",
                "retention_class": "REVIEW_EVIDENCE",
                "content_json": result_payload,
            }
        ]

    artifact_refs = [
        f"art://runtime/{ticket_id}/option-a.json",
        f"art://runtime/{ticket_id}/option-b.json",
    ]
    allowed_write_set = list(execution_package.execution.allowed_write_set)
    if not allowed_write_set:
        return artifact_refs, []
    write_pattern = allowed_write_set[0]
    written_artifacts = [
        {
            "path": _resolve_runtime_write_path(write_pattern, "option-a.json"),
            "artifact_ref": artifact_refs[0],
            "kind": "JSON",
            "retention_class": "REVIEW_EVIDENCE",
            "content_json": {
                "option_id": "option_a",
                "headline": "Primary runtime-generated structured review artifact.",
            },
        },
        {
            "path": _resolve_runtime_write_path(write_pattern, "option-b.json"),
            "artifact_ref": artifact_refs[1],
            "kind": "JSON",
            "retention_class": "REVIEW_EVIDENCE",
            "content_json": {
                "option_id": "option_b",
                "headline": "Fallback runtime-generated structured review artifact.",
            },
        },
    ]
    return artifact_refs, written_artifacts


def _build_meeting_round_notes(round_type: str, topic: str, participant_ids: list[str]) -> list[str]:
    if round_type == "POSITION":
        return [f"{employee_id} stated the main constraint for {topic}." for employee_id in participant_ids]
    if round_type == "CHALLENGE":
        return [f"{employee_id} questioned the hidden risk in the current direction." for employee_id in participant_ids]
    if round_type == "PROPOSAL":
        return [f"{employee_id} proposed one concrete convergence option." for employee_id in participant_ids]
    return [f"{employee_id} confirmed the final technical decision summary." for employee_id in participant_ids]


def _default_build_followup_owner_role(source_owner_role: str) -> str:
    if source_owner_role in {
        "frontend_engineer",
        "backend_engineer",
        "database_engineer",
        "platform_sre",
    }:
        return source_owner_role
    return "frontend_engineer"


def _build_meeting_consensus_payload(
    execution_package: CompiledExecutionPackage,
    meeting_context: dict[str, Any],
    rounds: list[dict[str, Any]],
    archived_context_refs: list[str],
) -> dict[str, Any]:
    participant_ids = list(meeting_context.get("participant_employee_ids") or [])
    ticket_id = execution_package.meta.ticket_id
    topic = str(meeting_context.get("topic") or f"Consensus for ticket {ticket_id}")
    owner_role = execution_package.compiled_role.employee_role_type
    build_owner_role = _default_build_followup_owner_role(owner_role)
    return {
        "topic": topic,
        "participants": participant_ids,
        "input_artifact_refs": [
            block.source_ref
            for block in execution_package.atomic_context_bundle.context_blocks
            if block.source_kind == "ARTIFACT"
        ],
        "consensus_summary": (
            f"Meeting converged on one technical direction after {len(rounds)} structured rounds for {topic}."
        ),
        "decision_record": {
            "format": "ADR_V1",
            "context": f"{topic} required a bounded technical decision before downstream delivery could continue.",
            "decision": "Use the narrowest technical direction that keeps the current MVP delivery moving.",
            "rationale": [
                "The converged path keeps implementation and validation aligned on one contract.",
                "It avoids widening the current MVP boundary with deferred alternatives.",
            ],
            "consequences": [
                "Follow-up implementation must stay inside the converged technical direction.",
                "Deferred alternatives should return through a later governance ticket if needed.",
            ],
            "archived_context_refs": list(archived_context_refs),
        },
        "rejected_options": ["Carry multiple conflicting technical paths into the same delivery round."],
        "open_questions": ["Whether the deferred alternative should return as a later governance ticket."],
        "followup_tickets": [
            {
                "ticket_id": f"{ticket_id}_followup_build",
                "task_title": "Implement the converged build slice",
                "owner_role": build_owner_role,
                "summary": "Implement the converged technical direction without widening the MVP boundary.",
                "delivery_stage": DeliveryStage.BUILD.value,
            },
            {
                "ticket_id": f"{ticket_id}_followup_check",
                "task_title": "Check the converged build slice",
                "owner_role": "checker",
                "summary": "Check the implementation against the converged technical decision before board review.",
                "delivery_stage": DeliveryStage.CHECK.value,
            },
            {
                "ticket_id": f"{ticket_id}_followup_review",
                "task_title": "Prepare the converged review package",
                "owner_role": "frontend_engineer",
                "summary": "Prepare the final board-facing review package from the converged technical decision.",
                "delivery_stage": DeliveryStage.REVIEW.value,
            },
        ],
    }


def _build_meeting_digest_artifact(
    execution_package: CompiledExecutionPackage,
    meeting_context: dict[str, Any],
    rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    meeting_id = str(meeting_context.get("meeting_id") or execution_package.meta.ticket_id)
    path = _resolve_runtime_write_path(
        execution_package.execution.allowed_write_set[0],
        "meeting-digest.json",
    )
    artifact_ref = f"art://runtime/{execution_package.meta.ticket_id}/meeting-digest.json"
    return {
        "path": path,
        "artifact_ref": artifact_ref,
        "kind": "JSON",
        "retention_class": "REVIEW_EVIDENCE",
        "content_json": {
            "meeting_id": meeting_id,
            "topic": meeting_context.get("topic"),
            "rounds": rounds,
            "recorder_employee_id": meeting_context.get("recorder_employee_id"),
        },
    }


def _execute_meeting_runtime(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    execution_package: CompiledExecutionPackage,
    created_spec: dict[str, Any],
) -> RuntimeExecutionResult:
    meeting_context = dict(created_spec.get("meeting_context") or {})
    meeting_id = str(meeting_context.get("meeting_id") or "").strip()
    if not meeting_id:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="RUNTIME_INPUT_ERROR",
            failure_message="Meeting-backed ticket is missing meeting_id in meeting_context.",
        )

    meeting = repository.get_meeting_projection(meeting_id)
    if meeting is None:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="RUNTIME_INPUT_ERROR",
            failure_message=f"Meeting projection {meeting_id} does not exist.",
        )

    topic = str(meeting_context.get("topic") or meeting.get("topic") or execution_package.meta.ticket_id)
    participant_ids = list(meeting_context.get("participant_employee_ids") or [])
    ordered_rounds = ["POSITION", "CHALLENGE", "PROPOSAL", "CONVERGENCE"]
    max_rounds = int(meeting_context.get("max_rounds") or len(ordered_rounds))
    runtime_rounds: list[dict[str, Any]] = []
    round_timestamp = now_local()

    with repository.transaction() as connection:
        repository.update_meeting_projection(
            connection,
            meeting_id,
            status="IN_ROUND",
            current_round=ordered_rounds[0],
            updated_at=round_timestamp,
        )
        for index, round_type in enumerate(ordered_rounds[:max_rounds]):
            completed_at = now_local()
            round_payload = {
                "round_type": round_type,
                "round_index": index + 1,
                "summary": f"{round_type.title()} round closed on {topic}.",
                "notes": _build_meeting_round_notes(round_type, topic, participant_ids),
                "completed_at": completed_at.isoformat(),
            }
            runtime_rounds.append(round_payload)
            repository.insert_event(
                connection,
                event_type=EVENT_MEETING_ROUND_COMPLETED,
                actor_type="runtime",
                actor_id=str(ticket.get("lease_owner") or "runtime"),
                workflow_id=str(ticket["workflow_id"]),
                idempotency_key=f"meeting-round:{meeting_id}:{index + 1}:{ticket['ticket_id']}",
                causation_id=None,
                correlation_id=str(ticket["workflow_id"]),
                payload={
                    "meeting_id": meeting_id,
                    "round_type": round_type,
                    "round_index": index + 1,
                    "summary": round_payload["summary"],
                },
                occurred_at=completed_at,
            )

        if max_rounds < len(ordered_rounds):
            no_consensus_reason = "Round budget exhausted before convergence."
            repository.update_meeting_projection(
                connection,
                meeting_id,
                status="NO_CONSENSUS",
                current_round=runtime_rounds[-1]["round_type"] if runtime_rounds else None,
                rounds=runtime_rounds,
                updated_at=now_local(),
                closed_at=None,
                no_consensus_reason=no_consensus_reason,
                consensus_summary=None,
                review_status=None,
            )
            repository.insert_event(
                connection,
                event_type=EVENT_MEETING_CONCLUDED,
                actor_type="runtime",
                actor_id=str(ticket.get("lease_owner") or "runtime"),
                workflow_id=str(ticket["workflow_id"]),
                idempotency_key=f"meeting-concluded:{meeting_id}:{ticket['ticket_id']}:no-consensus",
                causation_id=None,
                correlation_id=str(ticket["workflow_id"]),
                payload={
                    "meeting_id": meeting_id,
                    "outcome_status": "NO_CONSENSUS",
                    "reason": no_consensus_reason,
                },
                occurred_at=now_local(),
            )
            return RuntimeExecutionResult(
                result_status="failed",
                completion_summary="Meeting exhausted its round budget before convergence.",
                failure_kind="MEETING_NO_CONSENSUS",
                failure_message=no_consensus_reason,
                failure_detail={
                    "meeting_id": meeting_id,
                    "rounds_completed": len(runtime_rounds),
                    "max_rounds": max_rounds,
                },
            )

        meeting_digest_artifact_ref = f"art://runtime/{execution_package.meta.ticket_id}/meeting-digest.json"
        result_payload = _build_meeting_consensus_payload(
            execution_package,
            meeting_context,
            runtime_rounds,
            [meeting_digest_artifact_ref],
        )
        artifact_refs, written_artifacts = _build_runtime_default_artifacts(execution_package, result_payload)
        written_artifacts.append(
            _build_meeting_digest_artifact(execution_package, meeting_context, runtime_rounds)
        )
        artifact_refs.append(str(written_artifacts[-1]["artifact_ref"]))
        consensus_summary = str(result_payload.get("consensus_summary") or "")
        repository.update_meeting_projection(
            connection,
            meeting_id,
            status="CLOSED",
            current_round="CONVERGENCE",
            rounds=runtime_rounds,
            updated_at=now_local(),
            closed_at=now_local(),
            no_consensus_reason=None,
            consensus_summary=consensus_summary,
            review_status="CHECKER_PENDING",
        )
        repository.insert_event(
            connection,
            event_type=EVENT_MEETING_CONCLUDED,
            actor_type="runtime",
            actor_id=str(ticket.get("lease_owner") or "runtime"),
            workflow_id=str(ticket["workflow_id"]),
            idempotency_key=f"meeting-concluded:{meeting_id}:{ticket['ticket_id']}:consensus",
            causation_id=None,
            correlation_id=str(ticket["workflow_id"]),
            payload={
                "meeting_id": meeting_id,
                "outcome_status": "CONSENSUS_SUBMITTED",
                "consensus_summary": consensus_summary,
            },
            occurred_at=now_local(),
        )
        return RuntimeExecutionResult(
            result_status="completed",
            completion_summary=f"Runtime completed meeting {meeting_id} and submitted the consensus document.",
            artifact_refs=artifact_refs,
            result_payload=result_payload,
            written_artifacts=written_artifacts,
            assumptions=[
                f"meeting_id={meeting_id}",
                f"meeting_round_count={len(runtime_rounds)}",
            ],
            issues=[],
            confidence=0.74,
        )


def _build_runtime_success_payload(
    execution_package: CompiledExecutionPackage,
    artifact_refs: list[str],
) -> dict[str, Any]:
    if execution_package.execution.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        owner_role = execution_package.compiled_role.employee_role_type
        build_owner_role = _default_build_followup_owner_role(owner_role)
        ticket_id = execution_package.meta.ticket_id
        return {
            "topic": f"Consensus for ticket {ticket_id}",
            "participants": [execution_package.compiled_role.role_profile_ref, "checker_primary"],
            "input_artifact_refs": [
                block.source_ref
                for block in execution_package.atomic_context_bundle.context_blocks
                if block.source_kind == "ARTIFACT"
            ],
            "consensus_summary": "Runtime converged on the narrowest scope that keeps delivery moving.",
            "rejected_options": ["Expand beyond the current MVP boundary in this round."],
            "open_questions": ["Whether non-critical polish should move after board approval."],
            "followup_tickets": [
                {
                    "ticket_id": f"{ticket_id}_followup_build",
                    "task_title": "Build the approved homepage foundation",
                    "owner_role": build_owner_role,
                    "summary": "Build the approved homepage foundation without widening scope.",
                    "delivery_stage": DeliveryStage.BUILD.value,
                },
                {
                    "ticket_id": f"{ticket_id}_followup_check",
                    "task_title": "Check the approved implementation bundle",
                    "owner_role": "checker",
                    "summary": "Check the implementation bundle against the locked scope before board review.",
                    "delivery_stage": DeliveryStage.CHECK.value,
                },
                {
                    "ticket_id": f"{ticket_id}_followup_review",
                    "task_title": "Prepare the approved board review package",
                    "owner_role": "frontend_engineer",
                    "summary": "Prepare the final board-facing homepage review package from the approved implementation.",
                    "delivery_stage": DeliveryStage.REVIEW.value,
                },
            ],
        }
    if execution_package.execution.output_schema_ref == IMPLEMENTATION_BUNDLE_SCHEMA_REF:
        return {
            "summary": f"Implementation bundle prepared for ticket {execution_package.meta.ticket_id}.",
            "deliverable_artifact_refs": list(artifact_refs),
            "implementation_notes": [
                "Homepage foundation stays inside the approved scope lock and is ready for internal checking."
            ],
        }
    if execution_package.execution.output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        ticket_id = execution_package.meta.ticket_id
        output_schema_ref = execution_package.execution.output_schema_ref
        return {
            "document_kind_ref": output_schema_ref,
            "title": f"{output_schema_ref} for ticket {ticket_id}",
            "summary": (
                f"Runtime prepared a structured {output_schema_ref} document before opening the next delivery step."
            ),
            "linked_document_refs": ["doc://governance/upstream/current"],
            "linked_artifact_refs": list(artifact_refs),
            "source_process_asset_refs": [],
            "decisions": [
                "Keep the next delivery step explicit and document-first.",
            ],
            "constraints": [
                "Do not widen the current MVP boundary while preparing governance documents.",
            ],
            "sections": [
                {
                    "section_id": "section_summary",
                    "label": "Summary",
                    "summary": f"Document-first guidance for {ticket_id}.",
                    "content_markdown": (
                        f"Prepared `{output_schema_ref}` so the next ticket can consume structured guidance "
                        "instead of improvising from raw context."
                    ),
                }
            ],
            "followup_recommendations": [
                {
                    "recommendation_id": "rec_document_first_followup",
                    "summary": "Compile this governance document into the next implementation-facing ticket.",
                    "target_role": execution_package.compiled_role.employee_role_type,
                }
            ],
        }
    if execution_package.execution.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return {
            "summary": "Internal delivery check confirmed the implementation bundle stays within the approved scope.",
            "status": "PASS_WITH_NOTES",
            "findings": [
                {
                    "finding_id": "finding_scope_copy",
                    "summary": "Keep the launch copy trimmed to the approved scope lock.",
                    "blocking": False,
                }
            ],
        }
    if execution_package.execution.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return {
            "summary": (
                "Final delivery closeout package captures the approved board choice and the handoff notes "
                "needed to close the workflow."
            ),
            "final_artifact_refs": list(artifact_refs),
            "handoff_notes": [
                "Board-approved final option is captured in the closeout package.",
                "Final evidence remains linked back to the board review pack for audit.",
            ],
            "documentation_updates": [
                {
                    "doc_ref": "doc/TODO.md",
                    "status": "UPDATED",
                    "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
                },
                {
                    "doc_ref": "README.md",
                    "status": "NO_CHANGE_REQUIRED",
                    "summary": "No public capability or runtime flow changed in this round.",
                },
            ],
        }

    return {
        "summary": (
            f"Runtime prepared a minimal {execution_package.execution.output_schema_ref} review package "
            f"for ticket {execution_package.meta.ticket_id}."
        ),
        "recommended_option_id": "option_a",
        "options": [
            {
                "option_id": "option_a",
                "label": "Option A",
                "summary": "Primary minimal runtime-generated review option.",
                "artifact_refs": [artifact_refs[0]],
            },
            {
                "option_id": "option_b",
                "label": "Option B",
                "summary": "Fallback minimal runtime-generated review option.",
                "artifact_refs": [artifact_refs[1]],
            },
        ],
    }


def _build_runtime_checker_verdict_payload() -> dict[str, Any]:
    return {
        "summary": "Checker approved the submitted deliverable with one non-blocking note.",
        "review_status": "APPROVED_WITH_NOTES",
        "findings": [
            {
                "finding_id": "finding_cta_spacing",
                "severity": "low",
                "category": "VISUAL_POLISH",
                "headline": "One follow-up polish item remains.",
                "summary": "The deliverable is acceptable, but one polish task should be tracked downstream.",
                "required_action": "Carry the noted polish item into downstream implementation.",
                "blocking": False,
            }
        ],
    }


def _build_runtime_review_request(
    *,
    ticket: dict[str, Any],
    execution_result: RuntimeExecutionResult,
    created_spec: dict[str, Any] | None,
) -> TicketBoardReviewRequest | None:
    if execution_result.result_status != "completed" or created_spec is None:
        return None

    template_payload = created_spec.get("auto_review_request")
    if not isinstance(template_payload, dict):
        return None

    review_request = TicketBoardReviewRequest.model_validate(template_payload)
    artifact_refs = list(execution_result.artifact_refs)
    result_payload = execution_result.result_payload if isinstance(execution_result.result_payload, dict) else {}
    documentation_sync_summary = _build_closeout_documentation_sync_summary(
        result_payload.get("documentation_updates")
        if created_spec.get("output_schema_ref") == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF
        else None
    )
    review_summary = str(
        result_payload.get("consensus_summary")
        or result_payload.get("summary")
        or execution_result.completion_summary
        or review_request.recommendation_summary
    )
    if documentation_sync_summary is not None:
        review_summary = f"{review_summary} Documentation sync: {documentation_sync_summary}"

    updated_options = []
    for index, option in enumerate(review_request.options):
        updated_options.append(
            option.model_copy(
                update={
                    "artifact_refs": artifact_refs if index == 0 and artifact_refs else list(option.artifact_refs),
                    "summary": review_summary if index == 0 and review_summary else option.summary,
                }
            )
        )

    updated_evidence = []
    for index, evidence in enumerate(review_request.evidence_summary):
        updated_evidence.append(
            evidence.model_copy(
                update={
                    "source_ref": artifact_refs[0] if index == 0 and artifact_refs else evidence.source_ref,
                    "summary": review_summary if index == 0 and review_summary else evidence.summary,
                }
            )
        )

    fallback_evidence = _build_provider_fallback_evidence(execution_result)
    if fallback_evidence is not None:
        updated_evidence.append(fallback_evidence)
    if documentation_sync_summary is not None:
        updated_evidence.append(
            TicketReviewEvidence(
                evidence_id="ev_closeout_documentation_sync",
                source_type="DOCUMENTATION_SYNC",
                headline="Closeout documentation sync status",
                summary=documentation_sync_summary,
                source_ref=artifact_refs[0] if artifact_refs else None,
            )
        )

    return review_request.model_copy(
        update={
            "options": updated_options,
            "evidence_summary": updated_evidence,
            "recommendation_summary": review_summary,
            "inbox_summary": execution_result.completion_summary or review_request.inbox_summary,
            "developer_inspector_refs": review_request.developer_inspector_refs
            or _build_runtime_developer_inspector_refs(str(ticket["ticket_id"])),
        }
    )


def _build_closeout_documentation_sync_summary(documentation_updates: Any) -> str | None:
    if not isinstance(documentation_updates, list) or not documentation_updates:
        return None

    summary_parts: list[str] = []
    for item in documentation_updates:
        if not isinstance(item, dict):
            continue
        doc_ref = str(item.get("doc_ref") or "").strip()
        status = str(item.get("status") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not doc_ref or not status or not summary:
            continue
        summary_parts.append(f"{doc_ref}={status} ({summary})")

    if not summary_parts:
        return None
    return "; ".join(summary_parts)


def _schema_version_for_execution_package(execution_package: CompiledExecutionPackage) -> str:
    return schema_id(
        execution_package.execution.output_schema_ref,
        execution_package.execution.output_schema_version,
    )


def _strip_markdown_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _strip_bom(value: str) -> str:
    return value.lstrip("\ufeff")


def _strip_json_comments(value: str) -> str:
    result: list[str] = []
    in_string = False
    string_delimiter = ""
    escaping = False
    index = 0

    while index < len(value):
        char = value[index]
        next_char = value[index + 1] if index + 1 < len(value) else ""

        if in_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == string_delimiter:
                in_string = False
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = True
            string_delimiter = char
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
            index = min(index + 2, len(value))
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _strip_trailing_commas(value: str) -> str:
    result: list[str] = []
    in_string = False
    string_delimiter = ""
    escaping = False
    index = 0

    while index < len(value):
        char = value[index]

        if in_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == string_delimiter:
                in_string = False
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = True
            string_delimiter = char
            result.append(char)
            index += 1
            continue

        if char == ",":
            lookahead = index + 1
            while lookahead < len(value) and value[lookahead].isspace():
                lookahead += 1
            if lookahead < len(value) and value[lookahead] in {"]", "}"}:
                index += 1
                continue

        result.append(char)
        index += 1

    return "".join(result)


def _normalize_single_quoted_strings(value: str) -> tuple[str, bool]:
    result: list[str] = []
    in_double_quoted_string = False
    escaping = False
    index = 0
    changed = False

    while index < len(value):
        char = value[index]

        if in_double_quoted_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_double_quoted_string = False
            index += 1
            continue

        if char == '"':
            in_double_quoted_string = True
            result.append(char)
            index += 1
            continue

        if char != "'":
            result.append(char)
            index += 1
            continue

        index += 1
        string_buffer: list[str] = []
        single_quoted_escaping = False
        while index < len(value):
            string_char = value[index]
            if single_quoted_escaping:
                string_buffer.append(string_char)
                single_quoted_escaping = False
                index += 1
                continue
            if string_char == "\\":
                single_quoted_escaping = True
                index += 1
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


def _load_provider_payload(output_text: str) -> dict[str, Any]:
    cleaned_output = _strip_bom(_strip_markdown_code_fence(output_text))
    try:
        payload = json.loads(cleaned_output)
    except ValueError as exc:
        repair_steps = [
            "strip_markdown_code_fence",
            "strip_bom",
            "strip_json_comments",
            "strip_trailing_commas",
        ]
        repaired_output = _strip_trailing_commas(_strip_json_comments(cleaned_output))
        normalized_output, normalized = _normalize_single_quoted_strings(repaired_output)
        if normalized:
            repaired_output = normalized_output
            repair_steps.append("normalize_single_quoted_strings")
        try:
            payload = json.loads(repaired_output)
        except ValueError as repaired_exc:
            raise OpenAICompatProviderBadResponseError(
                failure_kind="PROVIDER_BAD_RESPONSE",
                message=f"Provider output was not valid JSON: {repaired_exc}",
                failure_detail={
                    "parse_stage": "repair_parse",
                    "repair_steps": repair_steps,
                    "parse_error": str(repaired_exc),
                },
            ) from repaired_exc
    if not isinstance(payload, dict):
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider output JSON root must be an object.",
            failure_detail={
                "parse_stage": "root_validation",
            },
        )
    return payload


def _build_openai_compat_provider_config(selection: RuntimeProviderSelection) -> OpenAICompatProviderConfig:
    provider = selection.provider
    return OpenAICompatProviderConfig(
        base_url=str(provider.base_url or ""),
        api_key=str(provider.api_key or ""),
        model=str(selection.actual_model or provider.model or ""),
        timeout_sec=float(provider.timeout_sec),
        reasoning_effort=selection.effective_reasoning_effort,
    )


def _build_claude_code_provider_config(selection: RuntimeProviderSelection) -> ClaudeCodeProviderConfig:
    provider = selection.provider
    return ClaudeCodeProviderConfig(
        command_path=str(provider.command_path or ""),
        model=str(selection.actual_model or provider.model or ""),
        timeout_sec=float(provider.timeout_sec),
    )


def _provider_failure_is_retryable(failure_kind: str) -> bool:
    return failure_kind in PROVIDER_PAUSE_FAILURE_KINDS


def _provider_retry_delay_sec(failure_kind: str, failure_detail: dict[str, Any], attempt_no: int) -> float:
    if failure_kind == "PROVIDER_RATE_LIMITED":
        retry_after_sec = failure_detail.get("retry_after_sec")
        if isinstance(retry_after_sec, (int, float)) and retry_after_sec >= 0:
            return float(retry_after_sec)
    return min(PROVIDER_RETRY_BACKOFF_BASE_SEC * (2 ** max(attempt_no - 1, 0)), PROVIDER_RETRY_BACKOFF_MAX_SEC)


def _normalize_provider_failure_detail(
    failure_detail: dict[str, Any] | None,
    *,
    selection: RuntimeProviderSelection | None,
    attempt_count: int,
    fallback_applied: bool,
    fallback_mode: str | None = None,
    fallback_reason: str | None = None,
    incident_id: str | None = None,
) -> dict[str, Any]:
    normalized = dict(failure_detail or {})
    if selection is not None:
        normalized.setdefault("provider_id", selection.provider.provider_id)
        normalized.setdefault("preferred_provider_id", selection.preferred_provider_id)
        normalized.setdefault("preferred_model", selection.preferred_model)
        normalized.setdefault("actual_provider_id", selection.provider.provider_id)
        normalized.setdefault("actual_model", selection.actual_model or selection.provider.model)
        normalized.setdefault("adapter_kind", selection.provider.adapter_kind)
        normalized.setdefault("selection_reason", selection.selection_reason)
        normalized.setdefault("policy_reason", selection.policy_reason)
    else:
        normalized.setdefault("provider_id", OPENAI_COMPAT_PROVIDER_ID)
    normalized["attempt_count"] = attempt_count
    normalized["fallback_applied"] = fallback_applied
    if fallback_mode is not None:
        normalized["fallback_mode"] = fallback_mode
    if fallback_reason is not None:
        normalized["fallback_reason"] = fallback_reason
    if incident_id is not None:
        normalized["incident_id"] = incident_id
    return normalized


def _build_provider_fallback_evidence(execution_result: RuntimeExecutionResult) -> TicketReviewEvidence | None:
    failure_detail = execution_result.failure_detail or {}
    if failure_detail.get("fallback_mode") != "LOCAL_DETERMINISTIC":
        return None
    provider_id = str(failure_detail.get("provider_id") or OPENAI_COMPAT_PROVIDER_ID)
    failure_kind = str(failure_detail.get("provider_failure_kind") or "PROVIDER_FAILURE")
    incident_id = failure_detail.get("incident_id")
    adapter_kind = str(failure_detail.get("adapter_kind") or "openai_compat")
    provider_label = "Claude Code CLI" if adapter_kind == "claude_code_cli" else "OpenAI Compat"
    return TicketReviewEvidence(
        evidence_id="provider_fallback",
        source_type="RUNTIME_FALLBACK",
        headline=f"Provider fallback on {provider_id}",
        summary=f"{provider_label} hit {failure_kind} and this result fell back to the local deterministic path.",
        source_ref=(f"incident:{incident_id}" if incident_id is not None else provider_id),
    )


def _execute_openai_compat_provider(
    execution_package: CompiledExecutionPackage,
    selection: RuntimeProviderSelection,
    *,
    sleep_fn=None,
) -> RuntimeExecutionResult:
    if sleep_fn is None:
        sleep_fn = _sleep
    config = _build_openai_compat_provider_config(selection)
    last_failure_kind = "PROVIDER_BAD_RESPONSE"
    last_failure_message = "Provider execution failed."
    last_failure_detail: dict[str, Any] = {
        "provider_id": selection.provider.provider_id,
        "preferred_provider_id": selection.preferred_provider_id,
        "preferred_model": selection.preferred_model,
        "actual_provider_id": selection.provider.provider_id,
        "actual_model": selection.actual_model or selection.provider.model,
        "adapter_kind": selection.provider.adapter_kind,
    }

    for attempt_no in range(1, PROVIDER_MAX_ATTEMPTS + 1):
        try:
            provider_result = invoke_openai_compat_response(
                config,
                execution_package.rendered_execution_payload,
            )
            result_payload = _load_provider_payload(provider_result.output_text)
            validate_output_payload(
                schema_ref=execution_package.execution.output_schema_ref,
                schema_version=execution_package.execution.output_schema_version,
                submitted_schema_version=_schema_version_for_execution_package(execution_package),
                payload=result_payload,
            )
            if execution_package.execution.output_schema_ref == "maker_checker_verdict":
                artifact_refs: list[str] = []
                written_artifacts: list[dict[str, Any]] = []
            else:
                artifact_refs, written_artifacts = _build_runtime_default_artifacts(
                    execution_package,
                    result_payload,
                )
            return RuntimeExecutionResult(
                result_status="completed",
                completion_summary=(
                    f"Provider-backed runtime executed ticket {execution_package.meta.ticket_id} via "
                    f"{execution_package.meta.compiler_version}."
                ),
                artifact_refs=artifact_refs,
                result_payload=result_payload,
                written_artifacts=written_artifacts,
                assumptions=_build_provider_selection_assumptions(
                    execution_package=execution_package,
                    selection=selection,
                    provider_response_id=provider_result.response_id,
                    provider_attempt_count=attempt_no,
                ),
                issues=[],
                confidence=0.82,
            )
        except (
            OpenAICompatProviderRateLimitedError,
            OpenAICompatProviderUnavailableError,
            OpenAICompatProviderAuthError,
            OpenAICompatProviderBadResponseError,
            ValueError,
        ) as exc:
            failure_kind = (
                exc.failure_kind
                if isinstance(
                    exc,
                    (
                        OpenAICompatProviderRateLimitedError,
                        OpenAICompatProviderUnavailableError,
                        OpenAICompatProviderAuthError,
                        OpenAICompatProviderBadResponseError,
                    ),
                )
                else "PROVIDER_BAD_RESPONSE"
            )
            failure_detail = (
                dict(exc.failure_detail)
                if isinstance(
                    exc,
                    (
                        OpenAICompatProviderRateLimitedError,
                        OpenAICompatProviderUnavailableError,
                        OpenAICompatProviderAuthError,
                        OpenAICompatProviderBadResponseError,
                    ),
                )
                else {}
            )
            last_failure_kind = failure_kind
            last_failure_message = str(exc)
            last_failure_detail = _normalize_provider_failure_detail(
                failure_detail,
                selection=selection,
                attempt_count=attempt_no,
                fallback_applied=False,
            )
            if _provider_failure_is_retryable(failure_kind) and attempt_no < PROVIDER_MAX_ATTEMPTS:
                sleep_fn(_provider_retry_delay_sec(failure_kind, last_failure_detail, attempt_no))
                continue
            return RuntimeExecutionResult(
                result_status="failed",
                failure_kind=last_failure_kind,
                failure_message=last_failure_message,
                failure_detail=last_failure_detail,
            )

    return RuntimeExecutionResult(
        result_status="failed",
        failure_kind=last_failure_kind,
        failure_message=last_failure_message,
        failure_detail=last_failure_detail,
    )


def _execute_claude_code_provider(
    execution_package: CompiledExecutionPackage,
    selection: RuntimeProviderSelection,
) -> RuntimeExecutionResult:
    try:
        provider_result = invoke_claude_code_response(
            _build_claude_code_provider_config(selection),
            execution_package.rendered_execution_payload,
        )
        result_payload = _load_provider_payload(provider_result.output_text)
        validate_output_payload(
            schema_ref=execution_package.execution.output_schema_ref,
            schema_version=execution_package.execution.output_schema_version,
            submitted_schema_version=_schema_version_for_execution_package(execution_package),
            payload=result_payload,
        )
        if execution_package.execution.output_schema_ref == "maker_checker_verdict":
            artifact_refs: list[str] = []
            written_artifacts: list[dict[str, Any]] = []
        else:
            artifact_refs, written_artifacts = _build_runtime_default_artifacts(
                execution_package,
                result_payload,
            )
        return RuntimeExecutionResult(
            result_status="completed",
            completion_summary=(
                f"Provider-backed runtime executed ticket {execution_package.meta.ticket_id} via "
                f"{execution_package.meta.compiler_version}."
            ),
            artifact_refs=artifact_refs,
            result_payload=result_payload,
            written_artifacts=written_artifacts,
            assumptions=_build_provider_selection_assumptions(
                execution_package=execution_package,
                selection=selection,
                provider_response_id=None,
                provider_attempt_count=1,
            ),
            issues=[],
            confidence=0.82,
        )
    except (ClaudeCodeProviderError, ValueError) as exc:
        failure_detail = (
            dict(exc.failure_detail)
            if isinstance(exc, ClaudeCodeProviderError)
            else {}
        )
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind=(exc.failure_kind if isinstance(exc, ClaudeCodeProviderError) else "PROVIDER_BAD_RESPONSE"),
            failure_message=str(exc),
            failure_detail=_normalize_provider_failure_detail(
                failure_detail,
                selection=selection,
                attempt_count=1,
                fallback_applied=False,
            ),
        )


def _build_provider_fallback_execution_result(
    execution_package: CompiledExecutionPackage,
    provider_failure: RuntimeExecutionResult,
    *,
    selection: RuntimeProviderSelection | None,
    fallback_reason: str,
    incident_id: str | None = None,
) -> RuntimeExecutionResult:
    deterministic_result = _execute_compiled_execution_package(execution_package)
    if deterministic_result.result_status != "completed":
        return deterministic_result

    failure_detail = _normalize_provider_failure_detail(
        provider_failure.failure_detail,
        selection=selection,
        attempt_count=int((provider_failure.failure_detail or {}).get("attempt_count") or 0),
        fallback_applied=True,
        fallback_mode="LOCAL_DETERMINISTIC",
        fallback_reason=fallback_reason,
        incident_id=incident_id,
    )
    failure_detail["provider_failure_kind"] = provider_failure.failure_kind or "PROVIDER_FAILURE"
    failure_detail["provider_failure_message"] = provider_failure.failure_message or fallback_reason

    provider_id = str(failure_detail.get("provider_id") or OPENAI_COMPAT_PROVIDER_ID)
    failure_kind = str(failure_detail["provider_failure_kind"])
    provider_label = "Claude Code CLI" if str(failure_detail.get("adapter_kind") or "") == "claude_code_cli" else "OpenAI Compat"
    fallback_issue = (
        f"{provider_label} provider {provider_id} hit {failure_kind}; runtime fell back to the local "
        "deterministic path for this result."
    )
    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=(
            f"{deterministic_result.completion_summary} OpenAI Compat fallback was applied because {fallback_reason}."
        ),
        artifact_refs=list(deterministic_result.artifact_refs),
        result_payload=dict(deterministic_result.result_payload),
        written_artifacts=list(deterministic_result.written_artifacts),
        assumptions=[
            *deterministic_result.assumptions,
            "runtime_fallback=LOCAL_DETERMINISTIC",
            f"runtime_fallback_reason={fallback_reason}",
            f"provider_id={provider_id}",
            f"preferred_provider_id={failure_detail.get('preferred_provider_id') or provider_id}",
            f"preferred_model={failure_detail.get('preferred_model') or 'unknown'}",
            f"actual_provider_id={failure_detail.get('actual_provider_id') or provider_id}",
            f"actual_model={failure_detail.get('actual_model') or 'unknown'}",
            f"selection_reason={failure_detail.get('selection_reason') or 'provider_selection'}",
            f"policy_reason={failure_detail.get('policy_reason') or 'none'}",
            f"provider_failure_kind={failure_kind}",
        ],
        issues=[fallback_issue, *deterministic_result.issues],
        confidence=deterministic_result.confidence,
        failure_detail=failure_detail,
    )


def _execute_provider_selection(
    execution_package: CompiledExecutionPackage,
    selection: RuntimeProviderSelection,
) -> RuntimeExecutionResult:
    if selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        return _execute_openai_compat_provider(execution_package, selection)
    return _execute_claude_code_provider(execution_package, selection)


def _annotate_provider_failover_success(
    provider_result: RuntimeExecutionResult,
    *,
    failed_selection: RuntimeProviderSelection,
    failover_selection: RuntimeProviderSelection,
    failure_kind: str,
) -> RuntimeExecutionResult:
    return RuntimeExecutionResult(
        result_status=provider_result.result_status,
        completion_summary=provider_result.completion_summary,
        artifact_refs=list(provider_result.artifact_refs),
        result_payload=dict(provider_result.result_payload),
        written_artifacts=list(provider_result.written_artifacts),
        assumptions=[
            *provider_result.assumptions,
            f"provider_failover_from={failed_selection.provider.provider_id}",
            f"provider_failover_to={failover_selection.provider.provider_id}",
            f"provider_failover_failure_kind={failure_kind}",
        ],
        issues=[
            (
                f"Provider failover switched execution from {failed_selection.provider.provider_id} "
                f"to {failover_selection.provider.provider_id} after {failure_kind}."
            ),
            *provider_result.issues,
        ],
        confidence=provider_result.confidence,
        failure_kind=provider_result.failure_kind,
        failure_message=provider_result.failure_message,
        failure_detail=dict(provider_result.failure_detail or {}),
    )


def _attempt_provider_failover(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    execution_package: CompiledExecutionPackage,
    created_spec: dict[str, Any] | None,
    *,
    primary_selection: RuntimeProviderSelection,
    primary_failure: RuntimeExecutionResult,
) -> RuntimeExecutionResult | None:
    target_ref = _resolve_ticket_target_ref(created_spec)
    if target_ref is None:
        return None
    config = resolve_runtime_provider_config()
    for failover_selection in resolve_provider_failover_selections(
        config,
        repository,
        target_ref=target_ref,
        primary_selection=primary_selection,
    ):
        failover_result = _execute_provider_selection(execution_package, failover_selection)
        if failover_result.result_status == "completed":
            return _annotate_provider_failover_success(
                failover_result,
                failed_selection=primary_selection,
                failover_selection=failover_selection,
                failure_kind=primary_failure.failure_kind or "PROVIDER_FAILURE",
            )
        if failover_result.failure_kind in PROVIDER_PAUSE_FAILURE_KINDS:
            _open_runtime_provider_incident(repository, ticket, failover_result)
            continue
        return None
    return None


def _open_runtime_provider_incident(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    provider_failure: RuntimeExecutionResult,
) -> str | None:
    provider_id = str(
        (provider_failure.failure_detail or {}).get("provider_id")
        or _resolve_ticket_provider_id(repository, ticket)
        or ""
    )
    if not provider_id:
        return None
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    with repository.transaction() as connection:
        incident_id = _open_provider_incident(
            repository=repository,
            connection=connection,
            command_id=command_id,
            occurred_at=occurred_at,
            workflow_id=str(ticket["workflow_id"]),
            ticket_id=str(ticket["ticket_id"]),
            node_id=str(ticket["node_id"]),
            provider_id=provider_id,
            failure_payload={
                "failure_kind": provider_failure.failure_kind,
                "failure_message": provider_failure.failure_message,
                "failure_fingerprint": provider_failure.failure_kind,
            },
            idempotency_key_base=(
                f"runtime-provider-fallback:{ticket['workflow_id']}:{ticket['ticket_id']}:"
                f"{provider_failure.failure_kind or 'provider_failure'}"
            ),
        )
        repository.refresh_projections(connection)
    return incident_id


def _build_preemptive_provider_fallback_result(
    execution_package: CompiledExecutionPackage,
    *,
    selection: RuntimeProviderSelection | None,
    failure_kind: str,
    failure_message: str,
    fallback_reason: str,
) -> RuntimeExecutionResult:
    return _build_provider_fallback_execution_result(
        execution_package,
        RuntimeExecutionResult(
            result_status="failed",
            failure_kind=failure_kind,
            failure_message=failure_message,
            failure_detail={
                "provider_id": selection.provider.provider_id if selection is not None else OPENAI_COMPAT_PROVIDER_ID,
                "attempt_count": 0,
            },
        ),
        selection=selection,
        fallback_reason=fallback_reason,
    )


def _resolve_ticket_target_ref(created_spec: dict[str, Any] | None) -> str | None:
    return resolve_execution_target_ref_from_ticket_spec(created_spec)


def _resolve_provider_selection_for_ticket(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    created_spec: dict[str, Any] | None,
) -> RuntimeProviderSelection | None:
    config = resolve_runtime_provider_config()
    target_ref = _resolve_ticket_target_ref(created_spec)
    if target_ref is None:
        return None
    return resolve_provider_selection(
        config,
        target_ref=target_ref,
        employee_provider_id=_resolve_ticket_provider_id(repository, ticket),
        runtime_preference=(created_spec or {}).get("runtime_preference"),
    )


def _execute_runtime_with_provider_if_configured(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    execution_package: CompiledExecutionPackage,
    created_spec: dict[str, Any] | None,
) -> RuntimeExecutionResult:
    if (
        created_spec is not None
        and isinstance(created_spec.get("meeting_context"), dict)
        and execution_package.execution.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF
    ):
        return _execute_meeting_runtime(repository, ticket, execution_package, created_spec)

    selection = _resolve_provider_selection_for_ticket(repository, ticket, created_spec)
    if selection is not None:
        if repository.has_open_circuit_breaker_for_provider(selection.provider.provider_id):
            return _build_preemptive_provider_fallback_result(
                execution_package,
                selection=selection,
                failure_kind="UPSTREAM_UNAVAILABLE",
                failure_message="Provider execution is currently paused by an open incident.",
                fallback_reason="provider execution is paused",
            )
        if selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT and not all(
            (selection.provider.base_url, selection.provider.api_key, selection.actual_model or selection.provider.model)
        ):
            return _build_preemptive_provider_fallback_result(
                execution_package,
                selection=selection,
                failure_kind="PROVIDER_CONFIG_INCOMPLETE",
                failure_message="Provider config is incomplete for OpenAI Compat execution.",
                fallback_reason="provider configuration is incomplete",
            )
        if selection.provider.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI and not all(
            (selection.provider.command_path, selection.actual_model or selection.provider.model)
        ):
            return _build_preemptive_provider_fallback_result(
                execution_package,
                selection=selection,
                failure_kind="PROVIDER_CONFIG_INCOMPLETE",
                failure_message="Provider config is incomplete for Claude Code execution.",
                fallback_reason="provider configuration is incomplete",
            )
        provider_result = _execute_provider_selection(execution_package, selection)
        if provider_result.result_status == "completed":
            return provider_result
        if provider_result.failure_kind in PROVIDER_PAUSE_FAILURE_KINDS:
            incident_id = _open_runtime_provider_incident(repository, ticket, provider_result)
            if provider_result.failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
                failover_result = _attempt_provider_failover(
                    repository,
                    ticket,
                    execution_package,
                    created_spec,
                    primary_selection=selection,
                    primary_failure=provider_result,
                )
                if failover_result is not None:
                    return failover_result
            return _build_provider_fallback_execution_result(
                execution_package,
                provider_result,
                selection=selection,
                fallback_reason="provider execution is paused after retry exhaustion",
                incident_id=incident_id,
            )
        if provider_result.failure_kind in {"PROVIDER_AUTH_FAILED", "PROVIDER_BAD_RESPONSE", "UPSTREAM_UNAVAILABLE"}:
            return _build_provider_fallback_execution_result(
                execution_package,
                provider_result,
                selection=selection,
                fallback_reason="provider returned a non-retryable error",
            )
        return provider_result
    return _execute_compiled_execution_package(execution_package)


def _execute_compiled_execution_package(
    execution_package: CompiledExecutionPackage,
) -> RuntimeExecutionResult:
    if execution_package.compiled_role.role_profile_ref not in SUPPORTED_RUNTIME_ROLE_PROFILES:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="UNSUPPORTED_RUNTIME_EXECUTION",
            failure_message=(
                "Runtime executor does not support role profile "
                f"{execution_package.compiled_role.role_profile_ref}."
            ),
            failure_detail={
                "compiler_version": execution_package.meta.compiler_version,
                "compile_request_id": execution_package.meta.compile_request_id,
                "role_profile_ref": execution_package.compiled_role.role_profile_ref,
                "output_schema_ref": execution_package.execution.output_schema_ref,
            },
        )

    if execution_package.execution.output_schema_ref not in SUPPORTED_RUNTIME_OUTPUT_SCHEMAS:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="UNSUPPORTED_RUNTIME_EXECUTION",
            failure_message=(
                "Runtime executor does not support output schema "
                f"{execution_package.execution.output_schema_ref}."
            ),
            failure_detail={
                "compiler_version": execution_package.meta.compiler_version,
                "compile_request_id": execution_package.meta.compile_request_id,
                "role_profile_ref": execution_package.compiled_role.role_profile_ref,
                "output_schema_ref": execution_package.execution.output_schema_ref,
                "output_schema_version": execution_package.execution.output_schema_version,
            },
        )

    if not execution_package.atomic_context_bundle.context_blocks:
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="RUNTIME_INPUT_ERROR",
            failure_message="Runtime executor requires at least one compiled context block.",
            failure_detail={
                "compiler_version": execution_package.meta.compiler_version,
                "compile_request_id": execution_package.meta.compile_request_id,
                "ticket_id": execution_package.meta.ticket_id,
            },
        )

    if execution_package.execution.output_schema_ref == "maker_checker_verdict":
        return RuntimeExecutionResult(
            result_status="completed",
            completion_summary=(
                f"Runtime executed checker ticket {execution_package.meta.ticket_id} via "
                f"{execution_package.meta.compiler_version}."
            ),
            artifact_refs=[],
            result_payload=_build_runtime_checker_verdict_payload(),
            written_artifacts=[],
            assumptions=[
                f"compiler_version={execution_package.meta.compiler_version}",
                f"compile_request_id={execution_package.meta.compile_request_id}",
            ],
            issues=[],
            confidence=0.7,
        )

    if execution_package.execution.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        result_payload = _build_runtime_success_payload(execution_package, [])
        artifact_refs, written_artifacts = _build_runtime_default_artifacts(
            execution_package,
            result_payload,
        )
    else:
        artifact_refs, _ = _build_runtime_default_artifacts(execution_package, {})
        result_payload = _build_runtime_success_payload(execution_package, artifact_refs)
        artifact_refs, written_artifacts = _build_runtime_default_artifacts(
            execution_package,
            result_payload,
        )
    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=(
            f"Runtime executed ticket {execution_package.meta.ticket_id} via "
            f"{execution_package.meta.compiler_version}."
        ),
        artifact_refs=artifact_refs,
        result_payload=result_payload,
        written_artifacts=written_artifacts,
        assumptions=[
            f"compiler_version={execution_package.meta.compiler_version}",
            f"compile_request_id={execution_package.meta.compile_request_id}",
        ],
        issues=[],
        confidence=0.7,
    )


def _build_runtime_result_submit_command(
    *,
    ticket: dict[str, Any],
    submitted_by: str,
    execution_package: CompiledExecutionPackage | None,
    execution_result: RuntimeExecutionResult,
    created_spec: dict[str, Any] | None,
) -> TicketResultSubmitCommand:
    schema_version = (
        _schema_version_for_execution_package(execution_package)
        if execution_package is not None
        else "ui_milestone_review_v1"
    )
    written_artifacts = [
        TicketWrittenArtifact(
            path=str(item["path"]),
            artifact_ref=str(item["artifact_ref"]),
            kind=str(item["kind"]),
            media_type=item.get("media_type"),
            content_json=item.get("content_json"),
            content_text=item.get("content_text"),
            content_base64=item.get("content_base64"),
            retention_class=str(item.get("retention_class") or "PERSISTENT"),
            retention_ttl_sec=item.get("retention_ttl_sec"),
        )
        for item in execution_result.written_artifacts
    ]
    return TicketResultSubmitCommand(
        workflow_id=ticket["workflow_id"],
        ticket_id=ticket["ticket_id"],
        node_id=ticket["node_id"],
        submitted_by=submitted_by,
        result_status=(
            TicketResultStatus.COMPLETED
            if execution_result.result_status == "completed"
            else TicketResultStatus.FAILED
        ),
        schema_version=schema_version,
        payload=execution_result.result_payload,
        artifact_refs=execution_result.artifact_refs,
        written_artifacts=written_artifacts,
        assumptions=execution_result.assumptions,
        issues=execution_result.issues,
        confidence=execution_result.confidence,
        needs_escalation=False,
        summary=execution_result.completion_summary
        or execution_result.failure_message
        or "Runtime submitted a structured result.",
        review_request=_build_runtime_review_request(
            ticket=ticket,
            execution_result=execution_result,
            created_spec=created_spec,
        ),
        failure_kind=execution_result.failure_kind,
        failure_message=execution_result.failure_message,
        failure_detail=execution_result.failure_detail,
        idempotency_key=_build_result_submit_idempotency_key(ticket, execution_result.result_status),
    )


def run_leased_ticket_runtime(
    repository: ControlPlaneRepository,
) -> list[RuntimeExecutionOutcome]:
    outcomes: list[RuntimeExecutionOutcome] = []
    settings = get_settings()
    developer_inspector_store = DeveloperInspectorStore(settings.developer_inspector_root)

    for ticket in _list_runtime_startable_leased_tickets(repository):
        lease_owner = str(ticket["lease_owner"])
        developer_inspector_refs = _build_runtime_developer_inspector_refs(str(ticket["ticket_id"]))
        start_ack = handle_ticket_start(
            repository,
            TicketStartCommand(
                workflow_id=ticket["workflow_id"],
                ticket_id=ticket["ticket_id"],
                node_id=ticket["node_id"],
                started_by=lease_owner,
                idempotency_key=_build_start_idempotency_key(ticket),
            ),
        )

        if start_ack.status != CommandAckStatus.ACCEPTED:
            outcomes.append(
                RuntimeExecutionOutcome(
                    ticket_id=ticket["ticket_id"],
                    lease_owner=lease_owner,
                    start_ack=start_ack,
                    final_ack=None,
                )
            )
            continue

        try:
            compiled_artifacts = _build_compiled_execution_artifacts(repository, ticket)
            execution_package = compiled_artifacts.compiled_execution_package
            export_latest_compile_artifacts_to_developer_inspector(
                repository,
                developer_inspector_store,
                str(ticket["ticket_id"]),
                developer_inspector_refs,
            )
            if settings.ticket_context_archive_root is not None:
                write_ticket_context_markdown(
                    settings.ticket_context_archive_root,
                    execution_package.model_dump(mode="json"),
                    developer_inspector_refs=developer_inspector_refs,
                )
            with repository.connection() as connection:
                created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            execution_result = _execute_runtime_with_provider_if_configured(
                repository,
                ticket,
                execution_package,
                created_spec,
            )
        except (ValidationError, ValueError) as exc:
            final_ack = handle_ticket_result_submit(
                repository,
                _build_runtime_result_submit_command(
                    ticket=ticket,
                    submitted_by=lease_owner,
                    execution_package=None,
                    execution_result=RuntimeExecutionResult(
                        result_status="failed",
                        completion_summary="Runtime compilation failed before structured submission.",
                        failure_kind="RUNTIME_INPUT_ERROR",
                        failure_message=str(exc),
                        failure_detail={
                            "compiler_version": MINIMAL_CONTEXT_COMPILER_VERSION,
                        },
                    ),
                    created_spec=None,
                ),
                developer_inspector_store,
            )
            outcomes.append(
                RuntimeExecutionOutcome(
                    ticket_id=ticket["ticket_id"],
                    lease_owner=lease_owner,
                    start_ack=start_ack,
                    final_ack=final_ack,
                )
            )
            continue

        final_ack = handle_ticket_result_submit(
            repository,
            _build_runtime_result_submit_command(
                ticket=ticket,
                submitted_by=lease_owner,
                execution_package=execution_package,
                execution_result=execution_result,
                created_spec=created_spec,
            ),
            developer_inspector_store,
        )

        outcomes.append(
            RuntimeExecutionOutcome(
                ticket_id=ticket["ticket_id"],
                lease_owner=lease_owner,
                start_ack=start_ack,
                final_ack=final_ack,
            )
        )

    return outcomes
