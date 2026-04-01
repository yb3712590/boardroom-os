from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    TicketResultStatus,
    TicketResultSubmitCommand,
    TicketWrittenArtifact,
    TicketStartCommand,
)
from app.contracts.runtime import CompiledAuditArtifacts, CompiledExecutionPackage
from app.core.context_compiler import (
    MINIMAL_CONTEXT_COMPILER_VERSION,
    compile_and_persist_execution_artifacts,
)
from app.core.output_schemas import schema_id, validate_output_payload
from app.core.provider_openai_compat import (
    OpenAICompatProviderAuthError,
    OpenAICompatProviderBadResponseError,
    OpenAICompatProviderConfig,
    OpenAICompatProviderRateLimitedError,
    OpenAICompatProviderUnavailableError,
    invoke_openai_compat_response,
)
from app.core.ticket_handlers import (
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


SUPPORTED_RUNTIME_OUTPUT_SCHEMAS = {"ui_milestone_review", "maker_checker_verdict"}
SUPPORTED_RUNTIME_ROLE_PROFILES = {"ui_designer_primary", "checker_primary"}
OPENAI_COMPAT_PROVIDER_ID = "prov_openai_compat"


def _runtime_sort_key(ticket: dict[str, Any]) -> tuple:
    return ticket["updated_at"], ticket["ticket_id"]


def _build_start_idempotency_key(ticket: dict[str, Any]) -> str:
    return f"runtime-start:{ticket['workflow_id']}:{ticket['ticket_id']}:{ticket['lease_owner']}"


def _build_result_submit_idempotency_key(ticket: dict[str, Any], result_status: str) -> str:
    return f"runtime-result-submit:{ticket['workflow_id']}:{ticket['ticket_id']}:{result_status}"


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
) -> tuple[list[str], list[dict[str, Any]]]:
    ticket_id = execution_package.meta.ticket_id
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


def _build_runtime_success_payload(
    execution_package: CompiledExecutionPackage,
    artifact_refs: list[str],
) -> dict[str, Any]:
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
        "summary": "Checker approved the visual milestone with one non-blocking note.",
        "review_status": "APPROVED_WITH_NOTES",
        "findings": [
            {
                "finding_id": "finding_cta_spacing",
                "severity": "low",
                "category": "VISUAL_POLISH",
                "headline": "CTA spacing can be tightened slightly.",
                "summary": "Spacing is acceptable but should be polished downstream.",
                "required_action": "Tighten CTA spacing during implementation.",
                "blocking": False,
            }
        ],
    }


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


def _load_provider_payload(output_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_markdown_code_fence(output_text))
    except ValueError as exc:
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message=f"Provider output was not valid JSON: {exc}",
            failure_detail={},
        ) from exc
    if not isinstance(payload, dict):
        raise OpenAICompatProviderBadResponseError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Provider output JSON root must be an object.",
            failure_detail={},
        )
    return payload


def _openai_compat_provider_is_configured() -> bool:
    settings = get_settings()
    return all(
        (
            settings.provider_openai_compat_base_url,
            settings.provider_openai_compat_api_key,
            settings.provider_openai_compat_model,
        )
    )


def _build_openai_compat_provider_config() -> OpenAICompatProviderConfig:
    settings = get_settings()
    return OpenAICompatProviderConfig(
        base_url=str(settings.provider_openai_compat_base_url or ""),
        api_key=str(settings.provider_openai_compat_api_key or ""),
        model=str(settings.provider_openai_compat_model or ""),
        timeout_sec=float(settings.provider_openai_compat_timeout_sec),
    )


def _execute_openai_compat_provider(
    execution_package: CompiledExecutionPackage,
) -> RuntimeExecutionResult:
    config = _build_openai_compat_provider_config()
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
        failure_detail.setdefault("provider_id", OPENAI_COMPAT_PROVIDER_ID)
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind=failure_kind,
            failure_message=str(exc),
            failure_detail=failure_detail,
        )

    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=(
            f"Provider-backed runtime executed ticket {execution_package.meta.ticket_id} via "
            f"{execution_package.meta.compiler_version}."
        ),
        artifact_refs=[],
        result_payload=result_payload,
        written_artifacts=[],
        assumptions=[
            f"compiler_version={execution_package.meta.compiler_version}",
            f"compile_request_id={execution_package.meta.compile_request_id}",
            f"provider_id={OPENAI_COMPAT_PROVIDER_ID}",
            f"provider_response_id={provider_result.response_id or 'unknown'}",
        ],
        issues=[],
        confidence=0.82,
    )


def _execute_runtime_with_provider_if_configured(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    execution_package: CompiledExecutionPackage,
) -> RuntimeExecutionResult:
    provider_id = _resolve_ticket_provider_id(repository, ticket)
    if provider_id == OPENAI_COMPAT_PROVIDER_ID and _openai_compat_provider_is_configured():
        return _execute_openai_compat_provider(execution_package)
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

    artifact_refs, written_artifacts = _build_runtime_default_artifacts(execution_package)
    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=(
            f"Runtime executed ticket {execution_package.meta.ticket_id} via "
            f"{execution_package.meta.compiler_version}."
        ),
        artifact_refs=artifact_refs,
        result_payload=_build_runtime_success_payload(execution_package, artifact_refs),
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
        review_request=None,
        failure_kind=execution_result.failure_kind,
        failure_message=execution_result.failure_message,
        failure_detail=execution_result.failure_detail,
        idempotency_key=_build_result_submit_idempotency_key(ticket, execution_result.result_status),
    )


def run_leased_ticket_runtime(
    repository: ControlPlaneRepository,
) -> list[RuntimeExecutionOutcome]:
    outcomes: list[RuntimeExecutionOutcome] = []

    for ticket in _list_runtime_startable_leased_tickets(repository):
        if _is_provider_paused_for_ticket(repository, ticket):
            continue
        lease_owner = str(ticket["lease_owner"])
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
            execution_result = _execute_runtime_with_provider_if_configured(
                repository,
                ticket,
                execution_package,
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
                ),
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
            ),
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
