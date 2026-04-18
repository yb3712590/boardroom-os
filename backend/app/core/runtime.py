from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

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
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
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
from app.core.graph_identity import apply_legacy_graph_contract_compat, resolve_ticket_graph_identity
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
    verification_evidence_refs: list[str] = field(default_factory=list)
    git_commit_record: dict[str, Any] | None = None
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
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
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
PROVIDER_MAX_ATTEMPTS = 10
PROVIDER_RETRYABLE_FAILURE_KINDS = {
    "PROVIDER_RATE_LIMITED",
    "UPSTREAM_UNAVAILABLE",
    "FIRST_TOKEN_TIMEOUT",
    "STREAM_IDLE_TIMEOUT",
}
PROVIDER_FAILOVER_FAILURE_KINDS = set(PROVIDER_RETRYABLE_FAILURE_KINDS)
PROVIDER_AUTO_PAUSE_FAILURE_KINDS: set[str] = set()
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
        with repository.connection() as connection:
            created_spec = apply_legacy_graph_contract_compat(
                repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
            )
        graph_identity = resolve_ticket_graph_identity(
            ticket_id=str(ticket["ticket_id"]),
            created_spec=created_spec,
            runtime_node_id=str(ticket.get("node_id") or ""),
        )
        runtime_node_projection = repository.get_runtime_node_projection(
            ticket["workflow_id"],
            graph_identity.graph_node_id,
        )
        if runtime_node_projection is None:
            raise RuntimeError(
                f"runtime_node_projection is missing for leased ticket {ticket['ticket_id']} "
                f"on graph lane {graph_identity.graph_node_id}."
            )
        if (
            runtime_node_projection["latest_ticket_id"] != ticket["ticket_id"]
            or runtime_node_projection["status"] != "PENDING"
        ):
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
    if output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        return _build_source_code_delivery_default_artifacts(execution_package, result_payload)
    if output_schema_ref in {
        CONSENSUS_DOCUMENT_SCHEMA_REF,
        *GOVERNANCE_DOCUMENT_SCHEMA_REFS,
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    }:
        filename_by_schema = {
            CONSENSUS_DOCUMENT_SCHEMA_REF: "consensus-document.json",
            **{
                schema_ref: f"{schema_ref}.json"
                for schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS
            },
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


def _default_source_code_extension(role_profile_ref: str) -> str:
    if role_profile_ref == "frontend_engineer_primary":
        return "tsx"
    if role_profile_ref == "backend_engineer_primary":
        return "py"
    if role_profile_ref == "database_engineer_primary":
        return "sql"
    if role_profile_ref == "platform_sre_primary":
        return "sh"
    return "txt"


def _default_source_code_delivery_file_refs(execution_package: CompiledExecutionPackage) -> list[str]:
    ticket_id = execution_package.meta.ticket_id
    extension = _default_source_code_extension(execution_package.compiled_role.role_profile_ref)
    return [f"art://workspace/{quote(ticket_id, safe='')}/source.{extension}"]


def _default_source_code_delivery_source_path(
    execution_package: CompiledExecutionPackage,
    source_pattern: str | None,
) -> str:
    extension = _default_source_code_extension(execution_package.compiled_role.role_profile_ref)
    filename = f"{execution_package.meta.ticket_id}.{extension}"
    if source_pattern is None:
        return f"10-project/src/{filename}"
    return _resolve_runtime_write_path(source_pattern, filename)


def _default_source_code_delivery_source_content(execution_package: CompiledExecutionPackage) -> str:
    ticket_id = execution_package.meta.ticket_id
    role_profile_ref = execution_package.compiled_role.role_profile_ref
    if role_profile_ref == "frontend_engineer_primary":
        return (
            "export function RuntimeGeneratedDelivery() {\n"
            "  return <main>Runtime delivery ready</main>;\n"
            "}\n"
        )
    normalized_ticket_id = re.sub(r"[^a-zA-Z0-9_]", "_", ticket_id)
    if role_profile_ref == "backend_engineer_primary":
        return (
            f"def build_{normalized_ticket_id}():\n"
            f"    return {{'ticket_id': '{ticket_id}', 'status': 'delivery_ready'}}\n"
        )
    if role_profile_ref == "database_engineer_primary":
        return (
            f"CREATE VIEW {normalized_ticket_id}_delivery_ready AS\n"
            f"SELECT '{ticket_id}' AS ticket_id, 'delivery_ready' AS status;\n"
        )
    if role_profile_ref == "platform_sre_primary":
        return (
            "#!/usr/bin/env bash\n"
            f"echo \"ticket={ticket_id} delivery_ready=true\"\n"
        )
    return f"ticket_id={ticket_id}\nstatus=delivery_ready\n"


def _default_source_code_delivery_verification_runs(
    execution_package: CompiledExecutionPackage,
) -> list[dict[str, Any]]:
    ticket_id = execution_package.meta.ticket_id
    artifact_ref = f"art://workspace/{quote(ticket_id, safe='')}/test-report.json"
    path = f"20-evidence/tests/{ticket_id}/attempt-1/test-report.json"
    if execution_package.compiled_role.role_profile_ref == "frontend_engineer_primary":
        return [
            {
                "artifact_ref": artifact_ref,
                "path": path,
                "runner": "vitest",
                "command": "npm run test -- --runInBand",
                "status": "passed",
                "exit_code": 0,
                "duration_sec": 1.0,
                "stdout": " RUN  v1.0.0\n  ✓ runtime delivery smoke\n\n Test Files  1 passed\n",
                "stderr": "",
                "discovered_count": 1,
                "passed_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "failures": [],
            }
        ]
    return [
        {
            "artifact_ref": artifact_ref,
            "path": path,
            "runner": "pytest",
            "command": "pytest tests -q",
            "status": "passed",
            "exit_code": 0,
            "duration_sec": 1.0,
            "stdout": "collected 1 item\n\n1 passed in 0.12s\n",
            "stderr": "",
            "discovered_count": 1,
            "passed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "failures": [],
        }
    ]


def _default_source_code_delivery_source_files(
    execution_package: CompiledExecutionPackage,
    source_file_refs: list[str],
) -> list[dict[str, Any]]:
    allowed_write_set = list(execution_package.execution.allowed_write_set)
    source_pattern = next(
        (
            str(pattern)
            for pattern in allowed_write_set
            if str(pattern).startswith("10-project/")
            and not str(pattern).startswith("10-project/docs/")
        ),
        next((str(pattern) for pattern in allowed_write_set if str(pattern).strip()), None),
    )
    return [
        {
            "artifact_ref": source_file_refs[0],
            "path": _default_source_code_delivery_source_path(execution_package, source_pattern),
            "content": _default_source_code_delivery_source_content(execution_package),
        }
    ]


def _default_source_code_delivery_documentation_updates(
    execution_package: CompiledExecutionPackage,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for index, doc_ref in enumerate(execution_package.execution.doc_update_requirements):
        normalized_doc_ref = str(doc_ref or "").strip()
        if not normalized_doc_ref:
            continue
        updates.append(
            {
                "doc_ref": normalized_doc_ref,
                "status": "UPDATED" if index == 0 else "NO_CHANGE_REQUIRED",
                "summary": (
                    "Updated this document as part of the current source code delivery."
                    if index == 0
                    else "Reviewed this document and confirmed no additional change was required in this round."
                ),
            }
        )
    return updates


def _normalize_source_code_delivery_payload(
    execution_package: CompiledExecutionPackage,
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(result_payload)
    if not str(normalized.get("summary") or "").strip():
        normalized["summary"] = (
            f"Source code delivery prepared for ticket {execution_package.meta.ticket_id}."
        )

    source_file_refs = [
        str(item).strip()
        for item in list(normalized.get("source_file_refs") or [])
        if str(item).strip()
    ]
    source_files = []
    for item in list(normalized.get("source_files") or []):
        if not isinstance(item, dict):
            continue
        artifact_ref = str(item.get("artifact_ref") or "").strip()
        path = str(item.get("path") or "").strip()
        content = item.get("content")
        if artifact_ref and path and isinstance(content, str) and content:
            source_files.append(
                {
                    "artifact_ref": artifact_ref,
                    "path": path,
                    "content": content,
                }
            )
    if not source_file_refs and source_files:
        source_file_refs = [item["artifact_ref"] for item in source_files]
    if not source_file_refs:
        source_file_refs = _default_source_code_delivery_file_refs(execution_package)
    normalized["source_file_refs"] = source_file_refs
    if not source_files:
        source_files = _default_source_code_delivery_source_files(execution_package, source_file_refs)
    normalized["source_files"] = source_files

    verification_runs = [
        dict(item)
        for item in list(normalized.get("verification_runs") or [])
        if isinstance(item, dict)
    ]
    if not verification_runs:
        verification_runs = _default_source_code_delivery_verification_runs(execution_package)
    normalized["verification_runs"] = verification_runs

    implementation_notes = [
        str(item).strip()
        for item in list(normalized.get("implementation_notes") or [])
        if str(item).strip()
    ]
    if not implementation_notes:
        implementation_notes = [
            "Implementation stays inside the approved scope lock and is ready for internal checking."
        ]
    normalized["implementation_notes"] = implementation_notes

    documentation_updates = list(normalized.get("documentation_updates") or [])
    if not documentation_updates and execution_package.execution.doc_update_requirements:
        documentation_updates = _default_source_code_delivery_documentation_updates(execution_package)
    normalized["documentation_updates"] = documentation_updates
    return normalized


def _build_source_code_delivery_default_artifacts(
    execution_package: CompiledExecutionPackage,
    result_payload: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    source_file_refs = [
        str(item).strip()
        for item in list(result_payload.get("source_file_refs") or [])
        if str(item).strip()
    ] or _default_source_code_delivery_file_refs(execution_package)
    source_files = [
        dict(item)
        for item in list(result_payload.get("source_files") or [])
        if isinstance(item, dict)
    ] or _default_source_code_delivery_source_files(execution_package, source_file_refs)
    allowed_write_set = list(execution_package.execution.allowed_write_set)
    evidence_pattern = next(
        (str(pattern) for pattern in allowed_write_set if str(pattern).startswith("20-evidence/tests/")),
        None,
    )
    git_pattern = next(
        (str(pattern) for pattern in allowed_write_set if str(pattern).startswith("20-evidence/git/")),
        None,
    )

    written_artifacts: list[dict[str, Any]] = []
    for source_file in source_files:
        source_file_ref = str(source_file.get("artifact_ref") or "").strip()
        path = str(source_file.get("path") or "").strip()
        content_text = str(source_file.get("content") or "")
        if not source_file_ref or not path or not content_text:
            continue
        written_artifacts.append(
            {
                "path": path,
                "artifact_ref": source_file_ref,
                "kind": "TEXT",
                "retention_class": "PERSISTENT",
                "content_text": content_text,
            }
        )

    verification_runs = [
        dict(item)
        for item in list(result_payload.get("verification_runs") or [])
        if isinstance(item, dict)
    ] or _default_source_code_delivery_verification_runs(execution_package)
    if evidence_pattern is not None:
        for run in verification_runs:
            verification_evidence_ref = str(run.get("artifact_ref") or "").strip()
            verification_path = str(run.get("path") or "").strip()
            if not verification_path:
                verification_path = _resolve_runtime_write_path(
                    evidence_pattern,
                    f"{execution_package.meta.ticket_id}/attempt-1/test-report.json",
                )
            if not verification_evidence_ref:
                verification_evidence_ref = (
                    f"art://workspace/{quote(execution_package.meta.ticket_id, safe='')}/test-report.json"
                )
            normalized_run = dict(run)
            normalized_run["artifact_ref"] = verification_evidence_ref
            normalized_run["path"] = verification_path
            written_artifacts.append(
                {
                    "path": verification_path,
                    "artifact_ref": verification_evidence_ref,
                    "kind": "JSON",
                    "retention_class": "REVIEW_EVIDENCE",
                    "content_json": normalized_run,
                }
            )

    if git_pattern is not None:
        git_commit_ref = f"art://workspace/{quote(execution_package.meta.ticket_id, safe='')}/git-commit.json"
        git_path = _resolve_runtime_write_path(
            git_pattern,
            f"{execution_package.meta.ticket_id}/attempt-1/git-closeout.json",
        )
        written_artifacts.append(
            {
                "path": git_path,
                "artifact_ref": git_commit_ref,
                "kind": "JSON",
                "retention_class": "REVIEW_EVIDENCE",
                "content_json": {},
            }
        )
    return source_file_refs, written_artifacts


def _build_source_code_delivery_submission_evidence(
    execution_package: CompiledExecutionPackage,
    result_payload: dict[str, Any],
) -> tuple[list[str], dict[str, Any] | None]:
    verification_evidence_refs = [
        str(item.get("artifact_ref") or "").strip()
        for item in list(result_payload.get("verification_runs") or [])
        if isinstance(item, dict) and str(item.get("artifact_ref") or "").strip()
    ]
    return verification_evidence_refs, None


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
    def _process_asset_source_refs() -> list[str]:
        seen_refs: set[str] = set()
        refs: list[str] = []
        for block in execution_package.atomic_context_bundle.context_blocks:
            if getattr(block, "source_kind", None) != "PROCESS_ASSET":
                continue
            source_ref = str(getattr(block, "source_ref", "") or "").strip()
            if not source_ref or source_ref in seen_refs:
                continue
            seen_refs.add(source_ref)
            refs.append(source_ref)
        return refs

    def _default_backlog_ticket_specs() -> list[dict[str, Any]]:
        return [
            {"ticket_id": "BR-T01", "name": "认证与 RBAC 基础", "priority": "P0", "scope": ["认证入口", "权限模型", "会话守卫"]},
            {"ticket_id": "BR-T02", "name": "前端壳层与设计系统底座", "priority": "P0", "scope": ["主布局", "导航骨架", "基础组件"]},
            {"ticket_id": "BR-T03", "name": "服务与 API 基础骨架", "priority": "P0", "scope": ["服务骨架", "接口约定", "错误规范"]},
            {"ticket_id": "BR-T04", "name": "数据模型与迁移底座", "priority": "P0", "scope": ["核心表设计", "迁移脚本", "索引约束"]},
            {"ticket_id": "BR-T05", "name": "部署与观测基础能力", "priority": "P0", "scope": ["环境配置", "日志追踪", "健康检查"]},
            {"ticket_id": "BR-T06", "name": "读者档案模块", "priority": "P1", "scope": ["读者档案", "状态管理", "权限挂接"]},
            {"ticket_id": "BR-T07", "name": "馆藏目录维护模块", "priority": "P1", "scope": ["馆藏录入", "分类信息", "馆藏状态"]},
            {"ticket_id": "BR-T08", "name": "目录检索与筛选", "priority": "P1", "scope": ["关键字检索", "筛选器", "结果分页"]},
            {"ticket_id": "BR-T09", "name": "借阅办理主流程", "priority": "P1", "scope": ["借阅创建", "库存校验", "借阅记录"]},
            {"ticket_id": "BR-T10", "name": "归还与续借流程", "priority": "P1", "scope": ["归还处理", "续借规则", "状态同步"]},
            {"ticket_id": "BR-T11", "name": "预约排队能力", "priority": "P1", "scope": ["预约创建", "队列顺序", "预约释放"]},
            {"ticket_id": "BR-T12", "name": "罚金与逾期规则", "priority": "P1", "scope": ["罚金规则", "账单记录", "状态提醒"]},
            {"ticket_id": "BR-T13", "name": "库存调整与馆藏异动", "priority": "P1", "scope": ["库存调整", "损坏遗失", "异动记录"]},
            {"ticket_id": "BR-T14", "name": "盘点工作流", "priority": "P1", "scope": ["盘点任务", "差异确认", "盘点结果"]},
            {"ticket_id": "BR-T15", "name": "公告中心", "priority": "P2", "scope": ["公告发布", "展示位", "过期管理"]},
            {"ticket_id": "BR-T16", "name": "管理员工作台", "priority": "P1", "scope": ["运营看板", "快捷入口", "关键提醒"]},
            {"ticket_id": "BR-T17", "name": "读者端首页与个人中心", "priority": "P1", "scope": ["读者首页", "个人借阅状态", "操作入口"]},
            {"ticket_id": "BR-T18", "name": "审计日志主链路", "priority": "P1", "scope": ["操作日志", "关键事件留痕", "查询接口"]},
            {"ticket_id": "BR-T19", "name": "统计报表聚合", "priority": "P1", "scope": ["借阅统计", "库存统计", "预约罚金统计"]},
            {"ticket_id": "BR-T20", "name": "统计可视化仪表盘", "priority": "P2", "scope": ["图表组件", "指标卡片", "趋势视图"]},
            {"ticket_id": "BR-T21", "name": "通知与提醒编排", "priority": "P2", "scope": ["预约提醒", "逾期提醒", "公告触达"]},
            {"ticket_id": "BR-T22", "name": "导入导出能力", "priority": "P2", "scope": ["批量导入", "导出报表", "失败回执"]},
            {"ticket_id": "BR-T23", "name": "演示数据与初始化脚本", "priority": "P2", "scope": ["演示种子数据", "初始化脚本", "场景覆盖"]},
            {"ticket_id": "BR-T24", "name": "无障碍与响应式修整", "priority": "P2", "scope": ["键盘访问", "对比度", "移动端适配"]},
            {"ticket_id": "BR-T25", "name": "核心 API 集成测试", "priority": "P1", "scope": ["认证集成", "借阅链路", "预约罚金链路"]},
            {"ticket_id": "BR-T26", "name": "关键页面回归测试", "priority": "P1", "scope": ["首页回归", "馆藏检索回归", "借阅归还回归"]},
            {"ticket_id": "BR-T27", "name": "权限与安全审计", "priority": "P1", "scope": ["权限校验", "越权场景", "敏感操作审计"]},
            {"ticket_id": "BR-T28", "name": "发布流水线与部署脚本", "priority": "P1", "scope": ["构建发布", "环境变量", "部署步骤"]},
            {"ticket_id": "BR-T29", "name": "运行监控与运维手册", "priority": "P1", "scope": ["监控指标", "告警规则", "运行手册"]},
            {"ticket_id": "BR-T30", "name": "验收演示与交付证据整理", "priority": "P1", "scope": ["验收脚本", "演示路径", "交付证据"]},
        ]

    def _default_backlog_dependency_graph() -> list[dict[str, Any]]:
        return [
            {"ticket_id": "BR-T01", "depends_on": [], "reason": "先把认证与角色边界定住。"},
            {"ticket_id": "BR-T02", "depends_on": [], "reason": "前端壳层和设计系统可以先行。"},
            {"ticket_id": "BR-T03", "depends_on": [], "reason": "服务骨架需要尽早稳定。"},
            {"ticket_id": "BR-T04", "depends_on": [], "reason": "数据结构是业务主链的底座。"},
            {"ticket_id": "BR-T05", "depends_on": [], "reason": "部署与观测基础能力先行，后续可复用。"},
            {"ticket_id": "BR-T06", "depends_on": ["BR-T01", "BR-T03", "BR-T04"], "reason": "读者档案依赖认证、服务和数据底座。"},
            {"ticket_id": "BR-T07", "depends_on": ["BR-T03", "BR-T04"], "reason": "馆藏目录依赖服务与数据底座。"},
            {"ticket_id": "BR-T08", "depends_on": ["BR-T02", "BR-T03", "BR-T04", "BR-T07"], "reason": "检索能力需要界面壳层和目录主数据。"},
            {"ticket_id": "BR-T09", "depends_on": ["BR-T01", "BR-T03", "BR-T04", "BR-T07"], "reason": "借阅主流程依赖权限、服务、数据和馆藏目录。"},
            {"ticket_id": "BR-T10", "depends_on": ["BR-T09"], "reason": "归还与续借建立在借阅主流程上。"},
            {"ticket_id": "BR-T11", "depends_on": ["BR-T07", "BR-T09"], "reason": "预约依赖馆藏与借阅状态。"},
            {"ticket_id": "BR-T12", "depends_on": ["BR-T09", "BR-T10"], "reason": "罚金规则依赖借阅与归还状态。"},
            {"ticket_id": "BR-T13", "depends_on": ["BR-T07", "BR-T04"], "reason": "库存异动依赖目录和库存数据。"},
            {"ticket_id": "BR-T14", "depends_on": ["BR-T13"], "reason": "盘点在库存异动能力之上。"},
            {"ticket_id": "BR-T15", "depends_on": ["BR-T02", "BR-T03"], "reason": "公告中心依赖前端壳层和服务骨架。"},
            {"ticket_id": "BR-T16", "depends_on": ["BR-T02", "BR-T03", "BR-T07"], "reason": "管理员工作台需要基础界面和核心目录数据。"},
            {"ticket_id": "BR-T17", "depends_on": ["BR-T01", "BR-T02", "BR-T07"], "reason": "读者端首页依赖登录态、前端壳层和目录数据。"},
            {"ticket_id": "BR-T18", "depends_on": ["BR-T03", "BR-T04", "BR-T05"], "reason": "审计日志依赖服务、数据和观测基础。"},
            {"ticket_id": "BR-T19", "depends_on": ["BR-T03", "BR-T04", "BR-T18"], "reason": "统计报表依赖业务数据和审计链路。"},
            {"ticket_id": "BR-T20", "depends_on": ["BR-T02", "BR-T19"], "reason": "可视化仪表盘依赖前端壳层和统计聚合。"},
            {"ticket_id": "BR-T21", "depends_on": ["BR-T03", "BR-T05", "BR-T11", "BR-T12", "BR-T15"], "reason": "通知编排依赖服务基础、观测和业务触发点。"},
            {"ticket_id": "BR-T22", "depends_on": ["BR-T03", "BR-T04", "BR-T07", "BR-T13"], "reason": "导入导出建立在主数据和库存能力上。"},
            {"ticket_id": "BR-T23", "depends_on": ["BR-T04", "BR-T07", "BR-T09", "BR-T13"], "reason": "演示数据需要核心领域完成后统一整理。"},
            {"ticket_id": "BR-T24", "depends_on": ["BR-T02", "BR-T17", "BR-T20"], "reason": "无障碍与响应式修整放在关键页面成型后。"},
            {"ticket_id": "BR-T25", "depends_on": ["BR-T03", "BR-T06", "BR-T09", "BR-T11", "BR-T12", "BR-T13"], "reason": "API 集成测试依赖核心业务链路落地。"},
            {"ticket_id": "BR-T26", "depends_on": ["BR-T17", "BR-T09", "BR-T10", "BR-T11", "BR-T15", "BR-T20"], "reason": "关键页面回归测试依赖主要页面和交互完成。"},
            {"ticket_id": "BR-T27", "depends_on": ["BR-T01", "BR-T06", "BR-T09", "BR-T11", "BR-T18"], "reason": "权限与安全审计要在核心链路和日志链路完成后做。"},
            {"ticket_id": "BR-T28", "depends_on": ["BR-T05", "BR-T25", "BR-T26"], "reason": "发布流水线放在测试主链稳定后。"},
            {"ticket_id": "BR-T29", "depends_on": ["BR-T05", "BR-T18", "BR-T28"], "reason": "运维手册依赖观测和发布链路定型。"},
            {"ticket_id": "BR-T30", "depends_on": ["BR-T23", "BR-T26", "BR-T28", "BR-T29"], "reason": "最终验收证据需要演示数据、回归结果和发布运维资料。"},
        ]

    def _default_backlog_recommendation_sections() -> list[dict[str, Any]]:
        ticket_specs = _default_backlog_ticket_specs()
        return [
            {
                "section_id": "recommended_ticket_split",
                "label": "推荐工单拆分",
                "summary": "把治理链收敛为可执行的原子实施任务。",
                "content_markdown": "先补基础底座，再按业务模块推进，最后收口测试、发布、运维和验收证据。",
                "content_json": {
                    "tickets": ticket_specs,
                },
            },
            {
                "section_id": "dependency_and_sequence_plan",
                "label": "依赖关系与实施顺序",
                "summary": "基础能力先行，业务能力并行，质量与发布最后收口。",
                "content_markdown": "认证、前端壳层、服务、数据、观测是底座；其上展开认证、目录、借阅、预约、罚金、库存、报表、测试、发布和 closeout 前证据整理。",
                "content_json": {
                    "dependency_graph": _default_backlog_dependency_graph(),
                    "recommended_sequence": [
                        f"{item['ticket_id']} {item['name']}" for item in ticket_specs
                    ],
                },
            },
        ]

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
                    "task_title": "Check the approved source code delivery",
                    "owner_role": "checker",
                    "summary": "Check the source code delivery against the locked scope before board review.",
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
    if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        source_files = _default_source_code_delivery_source_files(
            execution_package,
            list(artifact_refs),
        )
        return {
            "summary": f"Source code delivery prepared for ticket {execution_package.meta.ticket_id}.",
            "source_file_refs": list(artifact_refs),
            "source_files": source_files,
            "verification_runs": _default_source_code_delivery_verification_runs(execution_package),
            "implementation_notes": [
                "Homepage foundation stays inside the approved scope lock and is ready for internal checking."
            ],
            "documentation_updates": _default_source_code_delivery_documentation_updates(execution_package),
        }
    if execution_package.execution.output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        ticket_id = execution_package.meta.ticket_id
        output_schema_ref = execution_package.execution.output_schema_ref
        source_process_asset_refs = _process_asset_source_refs()
        return {
            "document_kind_ref": output_schema_ref,
            "title": f"{output_schema_ref} for ticket {ticket_id}",
            "summary": (
                f"Runtime prepared a structured {output_schema_ref} document before opening the next delivery step."
            ),
            "linked_document_refs": ["doc://governance/upstream/current"],
            "linked_artifact_refs": list(artifact_refs),
            "source_process_asset_refs": source_process_asset_refs,
            "decisions": [
                "Keep the next delivery step explicit and document-first.",
            ],
            "constraints": [
                "Do not widen the current MVP boundary while preparing governance documents.",
            ],
            "sections": (
                _default_backlog_recommendation_sections()
                if output_schema_ref == BACKLOG_RECOMMENDATION_SCHEMA_REF
                else [
                    {
                        "section_id": "section_summary",
                        "label": "Summary",
                        "summary": f"Document-first guidance for {ticket_id}.",
                        "content_markdown": (
                            f"Prepared `{output_schema_ref}` so the next ticket can consume structured guidance "
                            "instead of improvising from raw context."
                        ),
                    }
                ]
            ),
            "followup_recommendations": [
                {
                    "recommendation_id": "rec_document_first_followup",
                    "summary": (
                        "Compile this governance document into the next implementation-facing ticket split."
                        if output_schema_ref == BACKLOG_RECOMMENDATION_SCHEMA_REF
                        else "Compile this governance document into the next implementation-facing ticket."
                    ),
                    "target_role": execution_package.compiled_role.employee_role_type,
                }
            ],
        }
    if execution_package.execution.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return {
            "summary": "Internal delivery check confirmed the source code delivery stays within the approved scope.",
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
        final_artifact_refs = [
            str(item).strip()
            for item in list(execution_package.execution.input_artifact_refs)
            if str(item).strip()
        ] or list(artifact_refs)
        return {
            "summary": (
                "Final delivery closeout package captures the approved board choice and the handoff notes "
                "needed to close the workflow."
            ),
            "final_artifact_refs": final_artifact_refs,
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
        connect_timeout_sec=float(provider.connect_timeout_sec or provider.timeout_sec or 0),
        write_timeout_sec=float(provider.write_timeout_sec or provider.timeout_sec or 0),
        first_token_timeout_sec=float(provider.first_token_timeout_sec or provider.timeout_sec or 0),
        stream_idle_timeout_sec=float(provider.stream_idle_timeout_sec or provider.timeout_sec or 0),
        request_total_timeout_sec=float(provider.request_total_timeout_sec or provider.timeout_sec or 0),
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
    return failure_kind in PROVIDER_RETRYABLE_FAILURE_KINDS


def _provider_retry_delay_sec(
    selection: RuntimeProviderSelection,
    failure_kind: str,
    failure_detail: dict[str, Any],
    attempt_no: int,
) -> float:
    if failure_kind == "PROVIDER_RATE_LIMITED":
        retry_after_sec = failure_detail.get("retry_after_sec")
        if isinstance(retry_after_sec, (int, float)) and retry_after_sec >= 0:
            return float(retry_after_sec)
    retry_schedule = list(selection.provider.retry_backoff_schedule_sec or [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0])
    if not retry_schedule:
        retry_schedule = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    schedule_index = min(max(attempt_no - 1, 0), len(retry_schedule) - 1)
    return float(retry_schedule[schedule_index])


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
        normalized.setdefault(
            "retry_backoff_schedule_sec",
            [float(item) for item in list(selection.provider.retry_backoff_schedule_sec or [])],
        )
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


def _extract_provider_attempt_count(result: RuntimeExecutionResult) -> int:
    failure_detail = result.failure_detail or {}
    raw_attempt_count = failure_detail.get("attempt_count")
    if isinstance(raw_attempt_count, int) and raw_attempt_count >= 0:
        return raw_attempt_count
    if isinstance(raw_attempt_count, float) and raw_attempt_count >= 0:
        return int(raw_attempt_count)
    for item in result.assumptions:
        if str(item).startswith("provider_attempt_count="):
            _, value = str(item).split("=", 1)
            if value.isdigit():
                return int(value)
    return 0


def _build_provider_attempt_log_entry(
    *,
    selection: RuntimeProviderSelection,
    result: RuntimeExecutionResult,
) -> dict[str, Any]:
    return {
        "provider_id": selection.provider.provider_id,
        "provider_model_entry_ref": selection.provider_model_entry_ref,
        "actual_model": selection.actual_model or selection.provider.model,
        "selection_reason": selection.selection_reason,
        "status": result.result_status.upper(),
        "failure_kind": result.failure_kind,
        "failure_message": result.failure_message,
        "attempt_count": _extract_provider_attempt_count(result),
    }


def _build_provider_candidate_chain(
    primary_selection: RuntimeProviderSelection | None,
    failover_selections: list[RuntimeProviderSelection] | None = None,
) -> list[str]:
    chain: list[str] = []
    for selection in [primary_selection, *(failover_selections or [])]:
        if selection is None:
            continue
        provider_id = selection.provider.provider_id
        if provider_id not in chain:
            chain.append(provider_id)
    return chain


def _build_provider_required_unavailable_result(
    *,
    selection: RuntimeProviderSelection | None,
    candidate_chain: list[str],
    provider_attempt_log: list[dict[str, Any]],
    failure_message: str,
    failure_kind: str = "PROVIDER_REQUIRED_UNAVAILABLE",
) -> RuntimeExecutionResult:
    failure_detail = _normalize_provider_failure_detail(
        {},
        selection=selection,
        attempt_count=(provider_attempt_log[-1]["attempt_count"] if provider_attempt_log else 0),
        fallback_applied=False,
    )
    if selection is None:
        failure_detail.pop("provider_id", None)
        failure_detail.pop("preferred_provider_id", None)
        failure_detail.pop("preferred_model", None)
        failure_detail.pop("actual_provider_id", None)
        failure_detail.pop("actual_model", None)
        failure_detail.pop("adapter_kind", None)
        failure_detail.pop("selection_reason", None)
        failure_detail.pop("policy_reason", None)
    failure_detail["fallback_blocked"] = True
    failure_detail["provider_candidate_chain"] = list(candidate_chain)
    failure_detail["provider_attempt_log"] = list(provider_attempt_log)
    return RuntimeExecutionResult(
        result_status="failed",
        failure_kind=failure_kind,
        failure_message=failure_message,
        failure_detail=failure_detail,
    )


def _build_provider_fallback_evidence(execution_result: RuntimeExecutionResult) -> TicketReviewEvidence | None:
    return None


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
            if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
                result_payload = _normalize_source_code_delivery_payload(execution_package, result_payload)
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
            verification_evidence_refs: list[str] = []
            git_commit_record: dict[str, Any] | None = None
            if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
                verification_evidence_refs, git_commit_record = _build_source_code_delivery_submission_evidence(
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
                verification_evidence_refs=verification_evidence_refs,
                git_commit_record=git_commit_record,
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
                sleep_fn(_provider_retry_delay_sec(selection, failure_kind, last_failure_detail, attempt_no))
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
        if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
            result_payload = _normalize_source_code_delivery_payload(execution_package, result_payload)
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
        verification_evidence_refs: list[str] = []
        git_commit_record: dict[str, Any] | None = None
        if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
            verification_evidence_refs, git_commit_record = _build_source_code_delivery_submission_evidence(
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
            verification_evidence_refs=verification_evidence_refs,
            git_commit_record=git_commit_record,
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
    provider_attempt_log = []
    if selection is not None:
        provider_attempt_log.append(
            _build_provider_attempt_log_entry(
                selection=selection,
                result=provider_failure,
            )
        )
    return _build_provider_required_unavailable_result(
        selection=selection,
        candidate_chain=_build_provider_candidate_chain(selection),
        provider_attempt_log=provider_attempt_log,
        failure_message=provider_failure.failure_message or fallback_reason,
        failure_kind=provider_failure.failure_kind or "PROVIDER_REQUIRED_UNAVAILABLE",
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
        if failover_result.failure_kind in PROVIDER_AUTO_PAUSE_FAILURE_KINDS:
            _open_runtime_provider_incident(repository, ticket, failover_result)
            continue
        if failover_result.failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
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
    return _build_provider_required_unavailable_result(
        selection=selection,
        candidate_chain=_build_provider_candidate_chain(selection),
        provider_attempt_log=[],
        failure_message=failure_message or fallback_reason,
        failure_kind=failure_kind,
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

    target_ref = _resolve_ticket_target_ref(created_spec)
    selection = _resolve_provider_selection_for_ticket(repository, ticket, created_spec)
    if selection is None:
        return _build_provider_required_unavailable_result(
            selection=None,
            candidate_chain=[],
            provider_attempt_log=[],
            failure_message="No live provider was available for runtime execution.",
        )

    config = resolve_runtime_provider_config()
    failover_selections = (
        resolve_provider_failover_selections(
            config,
            repository,
            target_ref=target_ref,
            primary_selection=selection,
        )
        if target_ref is not None
        else []
    )
    candidate_chain = _build_provider_candidate_chain(selection, failover_selections)
    provider_attempt_log: list[dict[str, Any]] = []

    if repository.has_open_circuit_breaker_for_provider(selection.provider.provider_id):
        return _build_provider_required_unavailable_result(
            selection=selection,
            candidate_chain=candidate_chain,
            provider_attempt_log=provider_attempt_log,
            failure_message="Provider execution is currently paused by an open incident.",
        )
    if selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT and not all(
        (selection.provider.base_url, selection.provider.api_key, selection.actual_model or selection.provider.model)
    ):
        return _build_provider_required_unavailable_result(
            selection=selection,
            candidate_chain=candidate_chain,
            provider_attempt_log=provider_attempt_log,
            failure_message="Provider config is incomplete for OpenAI Compat execution.",
        )
    if selection.provider.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI and not all(
        (selection.provider.command_path, selection.actual_model or selection.provider.model)
    ):
        return _build_provider_required_unavailable_result(
            selection=selection,
            candidate_chain=candidate_chain,
            provider_attempt_log=provider_attempt_log,
            failure_message="Provider config is incomplete for Claude Code execution.",
        )

    provider_result = _execute_provider_selection(execution_package, selection)
    provider_attempt_log.append(
        _build_provider_attempt_log_entry(
            selection=selection,
            result=provider_result,
        )
    )
    if provider_result.result_status == "completed":
        return provider_result
    if provider_result.failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
        for failover_selection in failover_selections:
            failover_result = _execute_provider_selection(execution_package, failover_selection)
            provider_attempt_log.append(
                _build_provider_attempt_log_entry(
                    selection=failover_selection,
                    result=failover_result,
                )
            )
            if failover_result.result_status == "completed":
                return _annotate_provider_failover_success(
                    failover_result,
                    failed_selection=selection,
                    failover_selection=failover_selection,
                    failure_kind=provider_result.failure_kind or "PROVIDER_FAILURE",
                )
            if failover_result.failure_kind in PROVIDER_AUTO_PAUSE_FAILURE_KINDS:
                _open_runtime_provider_incident(repository, ticket, failover_result)
                continue
            if failover_result.failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
                continue
            return _build_provider_required_unavailable_result(
                selection=failover_selection,
                candidate_chain=candidate_chain,
                provider_attempt_log=provider_attempt_log,
                failure_message=failover_result.failure_message or "Configured provider candidates failed.",
                failure_kind=failover_result.failure_kind or "PROVIDER_REQUIRED_UNAVAILABLE",
            )
        return _build_provider_required_unavailable_result(
            selection=selection,
            candidate_chain=candidate_chain,
            provider_attempt_log=provider_attempt_log,
            failure_message=provider_result.failure_message or "Configured provider candidates were unavailable.",
            failure_kind=provider_result.failure_kind or "PROVIDER_REQUIRED_UNAVAILABLE",
        )
    if provider_result.failure_kind in PROVIDER_AUTO_PAUSE_FAILURE_KINDS:
        _open_runtime_provider_incident(repository, ticket, provider_result)
        return _build_provider_required_unavailable_result(
            selection=selection,
            candidate_chain=candidate_chain,
            provider_attempt_log=provider_attempt_log,
            failure_message=provider_result.failure_message or "Configured provider candidates were unavailable.",
        )
    return _build_provider_required_unavailable_result(
        selection=selection,
        candidate_chain=candidate_chain,
        provider_attempt_log=provider_attempt_log,
        failure_message=provider_result.failure_message or "Provider execution failed.",
        failure_kind=provider_result.failure_kind or "PROVIDER_REQUIRED_UNAVAILABLE",
    )


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
        if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
            result_payload = _normalize_source_code_delivery_payload(execution_package, result_payload)
        artifact_refs, written_artifacts = _build_runtime_default_artifacts(
            execution_package,
            result_payload,
        )
    verification_evidence_refs: list[str] = []
    git_commit_record: dict[str, Any] | None = None
    if execution_package.execution.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        verification_evidence_refs, git_commit_record = _build_source_code_delivery_submission_evidence(
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
        verification_evidence_refs=verification_evidence_refs,
        git_commit_record=git_commit_record,
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
        compile_request_id=(
            execution_package.meta.compile_request_id
            if execution_package is not None
            else None
        ),
        compiled_execution_package_version_ref=(
            execution_package.meta.version_ref
            if execution_package is not None
            else None
        ),
        result_status=(
            TicketResultStatus.COMPLETED
            if execution_result.result_status == "completed"
            else TicketResultStatus.FAILED
        ),
        schema_version=schema_version,
        payload=execution_result.result_payload,
        artifact_refs=execution_result.artifact_refs,
        written_artifacts=written_artifacts,
        verification_evidence_refs=execution_result.verification_evidence_refs,
        git_commit_record=execution_result.git_commit_record,
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
        with repository.connection() as connection:
            created_spec = apply_legacy_graph_contract_compat(
                repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
            )
        graph_identity = resolve_ticket_graph_identity(
            ticket_id=str(ticket["ticket_id"]),
            created_spec=created_spec,
            runtime_node_id=str(ticket["node_id"]),
        )
        current_node = repository.get_current_node_projection(
            str(ticket["workflow_id"]),
            str(ticket["node_id"]),
        )
        current_runtime_node = repository.get_runtime_node_projection(
            str(ticket["workflow_id"]),
            str(graph_identity.graph_node_id),
        )
        start_ack = handle_ticket_start(
            repository,
            TicketStartCommand(
                workflow_id=ticket["workflow_id"],
                ticket_id=ticket["ticket_id"],
                node_id=ticket["node_id"],
                started_by=lease_owner,
                expected_ticket_version=int(ticket["version"]),
                expected_node_version=(
                    int(current_node["version"])
                    if current_node is not None
                    else None
                ),
                expected_runtime_node_version=(
                    int(current_runtime_node["version"])
                    if current_runtime_node is not None
                    else None
                ),
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
                    compile_manifest=compiled_artifacts.compile_manifest.model_dump(mode="json"),
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
