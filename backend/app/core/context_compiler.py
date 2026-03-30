from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from app.contracts.commands import DeveloperInspectorRefs, TicketEscalationPolicy
from app.contracts.runtime import (
    AtomicContextBlock,
    AtomicContextBundle,
    CompileManifest,
    CompileManifestArtifactHash,
    CompileManifestBudgetActual,
    CompileManifestBudgetPlan,
    CompileManifestCacheReport,
    CompileManifestDegradation,
    CompileManifestFinalBundleStats,
    CompileManifestInputFingerprint,
    CompileManifestMeta,
    CompileManifestSourceLogEntry,
    CompileManifestTransformLogEntry,
    CompiledAuditArtifacts,
    CompiledArtifactAccessDescriptor,
    CompiledConstraints,
    CompiledContextBlock,
    CompiledContextBundle,
    CompiledContextBundleMeta,
    CompiledContextSelector,
    CompiledExecution,
    CompiledExecutionPackage,
    CompiledExecutionPackageMeta,
    CompiledGovernance,
    CompiledOutputContract,
    CompiledRenderHints,
    CompiledRole,
    CompiledSystemControls,
    CompiledTaskDefinition,
    CompileRequest,
    CompileRequestBudgetPolicy,
    CompileRequestControlRefs,
    CompileRequestExecution,
    CompileRequestExplicitSource,
    CompileRequestGovernance,
    CompileRequestMeta,
    CompileRequestWorkerBinding,
)
from app.core.artifacts import build_artifact_access_descriptor
from app.core.constants import DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID
from app.core.ids import new_prefixed_id
from app.core.output_schemas import get_output_schema_body
from app.core.time import now_local
from app.core.developer_inspector import (
    DeveloperInspectorStore,
    PersistedDeveloperInspectorArtifact,
)
from app.db.repository import ControlPlaneRepository

MINIMAL_CONTEXT_COMPILER_VERSION = "context-compiler.min.v1"
MINIMAL_CONTEXT_COMPILER_MODEL_PROFILE = "boardroom_os.runtime.min"
REFERENCE_ONLY_WARNING = (
    "Current MVP compiles explicit source references only; artifact bodies are not hydrated."
)
REFERENCE_ONLY_REASON = (
    "Persist explicit source as a reference descriptor because artifact hydration is not "
    "implemented in the current MVP."
)
REFERENCE_ONLY_TRANSFORM = "NORMALIZE_REFERENCE_DESCRIPTOR"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _estimate_tokens(value: Any) -> int:
    return max(1, (len(_canonical_json(value)) + 3) // 4)


def _require_ticket_create_spec(
    repository: ControlPlaneRepository,
    ticket_id: str,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if connection is not None:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
    else:
        with repository.connection() as owned_connection:
            created_spec = repository.get_latest_ticket_created_payload(owned_connection, ticket_id)
    if created_spec is None:
        raise ValueError("Ticket create spec is missing for runtime compilation.")
    return created_spec


def _require_worker_binding(
    repository: ControlPlaneRepository,
    lease_owner: str | None,
    connection: sqlite3.Connection | None = None,
) -> tuple[str, dict[str, Any]]:
    if lease_owner is None:
        raise ValueError("Ticket lease owner is missing for runtime compilation.")

    employee = repository.get_employee_projection(lease_owner, connection=connection)
    if employee is None:
        raise ValueError(f"Employee {lease_owner} is missing from employee_projection.")

    return lease_owner, employee


def _build_compiled_role(compile_request: CompileRequest) -> CompiledRole:
    return CompiledRole(
        role_profile_ref=compile_request.control_refs.role_profile_ref,
        employee_id=compile_request.worker_binding.employee_id,
        employee_role_type=compile_request.worker_binding.employee_role_type,
        skill_profile=compile_request.worker_binding.skill_profile,
        personality_profile=compile_request.worker_binding.personality_profile,
        aesthetic_profile=compile_request.worker_binding.aesthetic_profile,
    )


def _build_compiled_constraints(compile_request: CompileRequest) -> CompiledConstraints:
    return CompiledConstraints(
        constraints_ref=compile_request.control_refs.constraints_ref,
        global_rules=[],
        board_constraints=[],
        budget_constraints={},
    )


def _build_execution_package_meta(compile_request: CompileRequest) -> CompiledExecutionPackageMeta:
    return CompiledExecutionPackageMeta(
        compile_request_id=compile_request.meta.compile_request_id,
        ticket_id=compile_request.meta.ticket_id,
        workflow_id=compile_request.meta.workflow_id,
        node_id=compile_request.meta.node_id,
        attempt_no=compile_request.meta.attempt_no,
        lease_owner=compile_request.worker_binding.lease_owner,
        tenant_id=compile_request.meta.tenant_id,
        workspace_id=compile_request.meta.workspace_id,
        compiler_version=MINIMAL_CONTEXT_COMPILER_VERSION,
    )


def _build_reference_block(
    source: CompileRequestExplicitSource,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=source.source_ref,
    )
    content_payload = {
        "source_ref": source.source_ref,
        "source_kind": source.source_kind,
        "is_mandatory": source.is_mandatory,
    }
    if source.artifact_access is not None:
        artifact_access = source.artifact_access.model_dump(mode="json")
        content_payload["artifact_access"] = artifact_access
        content_payload.update(artifact_access)
    token_estimate = _estimate_tokens(content_payload)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
        trust_level=1,
        instruction_authority="DATA_ONLY",
        priority_class="P1" if source.is_mandatory else "P2",
        selector=selector,
        transform_chain=[REFERENCE_ONLY_TRANSFORM],
        content_type="JSON",
        content_payload=content_payload,
        token_estimate=token_estimate,
        relevance_score=1.0 if source.is_mandatory else 0.7,
        source_hash=_stable_hash(content_payload),
        trust_note=REFERENCE_ONLY_WARNING,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
        priority_class=block.priority_class,
        trust_level=block.trust_level,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        critical=source.is_mandatory,
        status="USED",
        tokens_before=token_estimate,
        tokens_after=token_estimate,
        reason=REFERENCE_ONLY_REASON,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="NORMALIZE_SOURCES",
        operation_type="NORMALIZE",
        target_ref=source.source_ref,
        output_block_id=block.block_id,
        reason=REFERENCE_ONLY_REASON,
    )
    return block, source_log, transform_log


def _build_atomic_context_bundle(context_blocks: list[CompiledContextBlock], token_budget: int) -> AtomicContextBundle:
    return AtomicContextBundle(
        context_blocks=[
            AtomicContextBlock(
                block_id=block.block_id,
                source_ref=block.source_ref,
                source_kind="ARTIFACT",
                content_type="SOURCE_DESCRIPTOR",
                content_payload=dict(block.content_payload),
            )
            for block in context_blocks
        ],
        token_budget=token_budget,
    )


def build_compile_request(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    connection: sqlite3.Connection | None = None,
) -> CompileRequest:
    created_spec = _require_ticket_create_spec(repository, ticket["ticket_id"], connection=connection)
    lease_owner, employee = _require_worker_binding(
        repository,
        ticket.get("lease_owner"),
        connection=connection,
    )

    context_query_plan = dict(created_spec.get("context_query_plan") or {})
    max_input_tokens = int(context_query_plan.get("max_context_tokens") or 0)
    if max_input_tokens <= 0:
        raise ValueError("Ticket context_query_plan.max_context_tokens is missing for runtime compilation.")

    attempt_no = int(created_spec.get("attempt_no") or 0)
    if attempt_no <= 0:
        raise ValueError("Ticket attempt_no is missing for runtime compilation.")
    tenant_id = str(ticket.get("tenant_id") or created_spec.get("tenant_id") or DEFAULT_TENANT_ID)
    workspace_id = str(
        ticket.get("workspace_id") or created_spec.get("workspace_id") or DEFAULT_WORKSPACE_ID
    )

    return CompileRequest(
        meta=CompileRequestMeta(
            compile_request_id=new_prefixed_id("creq"),
            ticket_id=ticket["ticket_id"],
            workflow_id=ticket["workflow_id"],
            node_id=ticket["node_id"],
            attempt_no=attempt_no,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        ),
        control_refs=CompileRequestControlRefs(
            role_profile_ref=str(created_spec.get("role_profile_ref") or ""),
            constraints_ref=str(created_spec.get("constraints_ref") or ""),
            output_schema_ref=str(created_spec.get("output_schema_ref") or ""),
            output_schema_version=int(created_spec.get("output_schema_version") or 0),
        ),
        worker_binding=CompileRequestWorkerBinding(
            lease_owner=lease_owner,
            employee_id=lease_owner,
            employee_role_type=str(employee.get("role_type") or "unknown"),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            skill_profile=dict(employee.get("skill_profile_json") or {}),
            personality_profile=dict(employee.get("personality_profile_json") or {}),
            aesthetic_profile=dict(employee.get("aesthetic_profile_json") or {}),
        ),
        budget_policy=CompileRequestBudgetPolicy(
            max_input_tokens=max_input_tokens,
            overflow_policy="FAIL_CLOSED",
        ),
        explicit_sources=[
            CompileRequestExplicitSource(
                source_ref=str(source_ref),
                source_kind="ARTIFACT",
                is_mandatory=True,
                artifact_access=CompiledArtifactAccessDescriptor.model_validate(
                    build_artifact_access_descriptor(
                        repository.get_artifact_by_ref(str(source_ref), connection=connection),
                        artifact_ref=str(source_ref),
                    )
                ),
            )
            for source_ref in list(created_spec.get("input_artifact_refs") or [])
        ],
        execution=CompileRequestExecution(
            acceptance_criteria=list(created_spec.get("acceptance_criteria") or []),
            allowed_tools=list(created_spec.get("allowed_tools") or []),
            allowed_write_set=list(created_spec.get("allowed_write_set") or []),
        ),
        governance=CompileRequestGovernance(
            retry_budget=int(created_spec.get("retry_budget") or 0),
            timeout_sla_sec=int(created_spec.get("timeout_sla_sec") or 0),
            escalation_policy=TicketEscalationPolicy.model_validate(
                created_spec.get("escalation_policy") or {}
            ),
        ),
    )


def compile_audit_artifacts(
    compile_request: CompileRequest,
) -> CompiledAuditArtifacts:
    compiled_at = now_local()
    bundle_id = new_prefixed_id("ctx")
    compile_id = new_prefixed_id("cmp")
    compiled_role = _build_compiled_role(compile_request)
    compiled_constraints = _build_compiled_constraints(compile_request)

    built_blocks = [_build_reference_block(source) for source in compile_request.explicit_sources]
    context_blocks = [item[0] for item in built_blocks]
    source_log = [item[1] for item in built_blocks]
    transform_log = [item[2] for item in built_blocks]

    compiled_context_bundle = CompiledContextBundle(
        meta=CompiledContextBundleMeta(
            bundle_id=bundle_id,
            compile_request_id=compile_request.meta.compile_request_id,
            ticket_id=compile_request.meta.ticket_id,
            workflow_id=compile_request.meta.workflow_id,
            node_id=compile_request.meta.node_id,
            attempt_no=compile_request.meta.attempt_no,
            compiler_version=MINIMAL_CONTEXT_COMPILER_VERSION,
            compiled_at=compiled_at,
            model_profile=MINIMAL_CONTEXT_COMPILER_MODEL_PROFILE,
            render_target="compiled_execution_package",
            is_degraded=True,
        ),
        system_controls=CompiledSystemControls(
            role_profile=compiled_role.model_dump(mode="json"),
            hard_rules=[],
            board_constraints=[],
            output_contract=CompiledOutputContract(
                schema_ref=compile_request.control_refs.output_schema_ref,
                schema_version=compile_request.control_refs.output_schema_version,
                schema_body=get_output_schema_body(
                    compile_request.control_refs.output_schema_ref,
                    compile_request.control_refs.output_schema_version,
                ),
            ),
            allowed_write_set=compile_request.execution.allowed_write_set,
        ),
        task_definition=CompiledTaskDefinition(
            task_type="EXECUTION",
            atomic_task=(
                "Produce output that conforms to "
                f"{compile_request.control_refs.output_schema_ref} for ticket "
                f"{compile_request.meta.ticket_id}."
            ),
            acceptance_criteria=compile_request.execution.acceptance_criteria,
            risk_class="medium",
            budget_profile=compile_request.budget_policy.overflow_policy,
        ),
        context_blocks=context_blocks,
        render_hints=CompiledRenderHints(
            preferred_section_order=[
                "system_controls",
                "task_definition",
                "context_blocks",
                "output_contract",
            ],
            sandbox_untrusted_data=True,
            preferred_markup="json_messages",
        ),
    )

    used_p1 = sum(block.token_estimate for block in context_blocks if block.priority_class == "P1")
    used_p2 = sum(block.token_estimate for block in context_blocks if block.priority_class == "P2")
    used_p3 = sum(block.token_estimate for block in context_blocks if block.priority_class == "P3")
    final_bundle_tokens = sum(block.token_estimate for block in context_blocks)

    compile_manifest = CompileManifest(
        compile_meta=CompileManifestMeta(
            compile_id=compile_id,
            bundle_id=bundle_id,
            compile_request_id=compile_request.meta.compile_request_id,
            ticket_id=compile_request.meta.ticket_id,
            workflow_id=compile_request.meta.workflow_id,
            node_id=compile_request.meta.node_id,
            compiler_version=MINIMAL_CONTEXT_COMPILER_VERSION,
            compiled_at=compiled_at,
            duration_ms=0,
            model_profile=MINIMAL_CONTEXT_COMPILER_MODEL_PROFILE,
            cache_key=_stable_hash(
                {
                    "compile_request": compile_request.model_dump(mode="json"),
                    "compiler_version": MINIMAL_CONTEXT_COMPILER_VERSION,
                    "model_profile": MINIMAL_CONTEXT_COMPILER_MODEL_PROFILE,
                }
            ),
        ),
        input_fingerprint=CompileManifestInputFingerprint(
            ticket_hash=_stable_hash(compile_request.model_dump(mode="json")),
            role_profile_version=compile_request.control_refs.role_profile_ref,
            constraints_version=compile_request.control_refs.constraints_ref,
            output_schema_version=(
                f"{compile_request.control_refs.output_schema_ref}@"
                f"{compile_request.control_refs.output_schema_version}"
            ),
            artifact_hashes=[
                CompileManifestArtifactHash(
                    artifact_id=block.source_ref,
                    hash=block.source_hash,
                )
                for block in context_blocks
            ],
        ),
        budget_plan=CompileManifestBudgetPlan(
            total_budget_tokens=compile_request.budget_policy.max_input_tokens,
            reserved_p0=0,
            reserved_p1=compile_request.budget_policy.max_input_tokens,
            reserved_p2=0,
            reserved_p3=0,
            soft_limit_tokens=compile_request.budget_policy.max_input_tokens,
            hard_limit_tokens=compile_request.budget_policy.max_input_tokens,
        ),
        budget_actual=CompileManifestBudgetActual(
            used_p0=0,
            used_p1=used_p1,
            used_p2=used_p2,
            used_p3=used_p3,
            final_bundle_tokens=final_bundle_tokens,
            truncated_tokens=0,
        ),
        source_log=source_log,
        transform_log=transform_log,
        degradation=CompileManifestDegradation(
            is_degraded=True,
            fail_mode=compile_request.budget_policy.overflow_policy,
            missing_critical_sources=[],
            warnings=[
                REFERENCE_ONLY_WARNING,
                "Token counts are deterministic estimates, not provider tokenizer results.",
            ],
        ),
        cache_report=CompileManifestCacheReport(
            cache_hit=False,
            reused_from_compile_id=None,
            invalidated_by=[],
        ),
        final_bundle_stats=CompileManifestFinalBundleStats(
            context_block_count=len(context_blocks),
            trusted_block_count=len(context_blocks),
            reference_block_count=len(context_blocks),
            negative_pattern_count=0,
        ),
    )

    compiled_execution_package = CompiledExecutionPackage(
        meta=_build_execution_package_meta(compile_request),
        compiled_role=compiled_role,
        compiled_constraints=compiled_constraints,
        atomic_context_bundle=_build_atomic_context_bundle(
            context_blocks,
            compile_request.budget_policy.max_input_tokens,
        ),
        execution=CompiledExecution(
            acceptance_criteria=compile_request.execution.acceptance_criteria,
            allowed_tools=compile_request.execution.allowed_tools,
            allowed_write_set=compile_request.execution.allowed_write_set,
            output_schema_ref=compile_request.control_refs.output_schema_ref,
            output_schema_version=compile_request.control_refs.output_schema_version,
        ),
        governance=CompiledGovernance(
            retry_budget=compile_request.governance.retry_budget,
            timeout_sla_sec=compile_request.governance.timeout_sla_sec,
            escalation_policy=compile_request.governance.escalation_policy,
        ),
    )

    return CompiledAuditArtifacts(
        compiled_context_bundle=compiled_context_bundle,
        compile_manifest=compile_manifest,
        compiled_execution_package=compiled_execution_package,
    )



def _validate_matching_compiled_audit_artifacts(
    bundle_row: dict[str, Any],
    manifest_row: dict[str, Any],
) -> None:
    bundle_payload = bundle_row["payload"]
    manifest_payload = manifest_row["payload"]
    bundle_id = str(bundle_row["bundle_id"])
    compile_request_id = str(bundle_row["compile_request_id"])
    ticket_id = str(bundle_row["ticket_id"])

    if str(manifest_row["bundle_id"]) != bundle_id:
        raise RuntimeError("Latest compile manifest does not match the latest compiled context bundle.")
    if str(manifest_row["compile_request_id"]) != compile_request_id:
        raise RuntimeError("Latest compile manifest uses a different compile request than the latest bundle.")
    if str(manifest_row["ticket_id"]) != ticket_id:
        raise RuntimeError("Latest compile manifest belongs to a different ticket than the latest bundle.")
    if bundle_payload["meta"]["bundle_id"] != bundle_id:
        raise RuntimeError("Compiled context bundle payload does not match its persisted bundle id.")
    if bundle_payload["meta"]["compile_request_id"] != compile_request_id:
        raise RuntimeError("Compiled context bundle payload does not match its persisted compile request id.")
    if manifest_payload["compile_meta"]["bundle_id"] != bundle_id:
        raise RuntimeError("Compile manifest payload does not match the persisted bundle id.")
    if manifest_payload["compile_meta"]["compile_request_id"] != compile_request_id:
        raise RuntimeError("Compile manifest payload does not match the persisted compile request id.")
    if manifest_payload["compile_meta"]["ticket_id"] != ticket_id:
        raise RuntimeError("Compile manifest payload does not match the persisted ticket id.")


def export_latest_compile_artifacts_to_developer_inspector(
    repository: ControlPlaneRepository,
    developer_inspector_store: DeveloperInspectorStore,
    ticket_id: str,
    refs: DeveloperInspectorRefs,
    connection: sqlite3.Connection | None = None,
) -> list[PersistedDeveloperInspectorArtifact]:
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket(
        ticket_id,
        connection=connection,
    )
    latest_manifest = repository.get_latest_compile_manifest_by_ticket(
        ticket_id,
        connection=connection,
    )

    if (
        refs.compiled_context_bundle_ref is not None
        and refs.compile_manifest_ref is not None
        and latest_bundle is not None
        and latest_manifest is not None
    ):
        _validate_matching_compiled_audit_artifacts(latest_bundle, latest_manifest)

    persisted: list[PersistedDeveloperInspectorArtifact] = []
    if refs.compiled_context_bundle_ref is not None and latest_bundle is not None:
        persisted.append(
            developer_inspector_store.write_json(
                refs.compiled_context_bundle_ref,
                latest_bundle["payload"],
            )
        )
    if refs.compile_manifest_ref is not None and latest_manifest is not None:
        persisted.append(
            developer_inspector_store.write_json(
                refs.compile_manifest_ref,
                latest_manifest["payload"],
            )
        )
    return persisted


def compile_execution_package(
    compile_request: CompileRequest,
) -> CompiledExecutionPackage:
    return compile_audit_artifacts(compile_request).compiled_execution_package


def compile_and_persist_execution_artifacts(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
) -> CompiledAuditArtifacts:
    with repository.transaction() as connection:
        compile_request = build_compile_request(repository, ticket, connection=connection)
        artifacts = compile_audit_artifacts(compile_request)
        repository.save_compiled_context_bundle(connection, artifacts.compiled_context_bundle)
        repository.save_compile_manifest(connection, artifacts.compile_manifest)
        repository.save_compiled_execution_package(
            connection,
            artifacts.compiled_execution_package,
            compiled_at=artifacts.compile_manifest.compile_meta.compiled_at,
        )
        return artifacts
