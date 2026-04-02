from __future__ import annotations

import json
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
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
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
from app.core.runtime_provider_config import resolve_runtime_provider_config
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


SUPPORTED_RUNTIME_OUTPUT_SCHEMAS = {
    "ui_milestone_review",
    "maker_checker_verdict",
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
}
SUPPORTED_RUNTIME_ROLE_PROFILES = {"ui_designer_primary", "checker_primary"}
OPENAI_COMPAT_PROVIDER_ID = "prov_openai_compat"


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
        IMPLEMENTATION_BUNDLE_SCHEMA_REF,
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
    }:
        filename_by_schema = {
            CONSENSUS_DOCUMENT_SCHEMA_REF: "consensus-document.json",
            IMPLEMENTATION_BUNDLE_SCHEMA_REF: "implementation-bundle.json",
            DELIVERY_CHECK_REPORT_SCHEMA_REF: "delivery-check-report.json",
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


def _build_runtime_success_payload(
    execution_package: CompiledExecutionPackage,
    artifact_refs: list[str],
) -> dict[str, Any]:
    if execution_package.execution.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        owner_role = execution_package.compiled_role.employee_role_type
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
                    "owner_role": owner_role,
                    "summary": "Build the approved homepage foundation without widening scope.",
                    "delivery_stage": DeliveryStage.BUILD.value,
                },
                {
                    "ticket_id": f"{ticket_id}_followup_check",
                    "owner_role": "checker",
                    "summary": "Check the implementation bundle against the locked scope before board review.",
                    "delivery_stage": DeliveryStage.CHECK.value,
                },
                {
                    "ticket_id": f"{ticket_id}_followup_review",
                    "owner_role": owner_role,
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
    review_summary = str(
        result_payload.get("consensus_summary")
        or result_payload.get("summary")
        or execution_result.completion_summary
        or review_request.recommendation_summary
    )

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
    config = resolve_runtime_provider_config()
    return all(
        (
            config.mode == "OPENAI_COMPAT",
            config.base_url,
            config.api_key,
            config.model,
        )
    )


def _build_openai_compat_provider_config() -> OpenAICompatProviderConfig:
    config = resolve_runtime_provider_config()
    return OpenAICompatProviderConfig(
        base_url=str(config.base_url or ""),
        api_key=str(config.api_key or ""),
        model=str(config.model or ""),
        timeout_sec=float(config.timeout_sec),
        reasoning_effort=config.reasoning_effort,
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

    if execution_package.execution.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        result_payload = _build_runtime_success_payload(execution_package, [])
        artifact_refs, written_artifacts = _build_runtime_default_artifacts(
            execution_package,
            result_payload,
        )
    else:
        artifact_refs, written_artifacts = _build_runtime_default_artifacts(execution_package, {})
        result_payload = _build_runtime_success_payload(execution_package, artifact_refs)
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
    developer_inspector_store = DeveloperInspectorStore(get_settings().developer_inspector_root)

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
            with repository.connection() as connection:
                created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
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
