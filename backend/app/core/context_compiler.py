from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import nullcontext
from dataclasses import dataclass
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
    CompiledContextLayerSummary,
    CompiledOutputContract,
    CompiledRenderHints,
    CompiledRole,
    CompiledSystemControls,
    CompiledTaskDefinition,
    CompiledTaskFrame,
    ContextLayerSectionSummary,
    CompileRequest,
    CompileRequestBudgetPolicy,
    CompileRequestControlRefs,
    CompileRequestExecution,
    CompileRequestExplicitSource,
    CompileRequestGovernance,
    CompileRequestMeta,
    CompileRequestOrgContext,
    CompileRequestOrgRelation,
    CompileRequestResponsibilityBoundary,
    CompileRequestRetrievedSummary,
    CompileRequestRetrievalPlan,
    CompileRequestWorkerBinding,
    CompileRequestEscalationPath,
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.artifacts import (
    build_artifact_access_descriptor,
    is_artifact_readable,
    normalize_artifact_kind,
)
from app.core.constants import (
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    TICKET_STATUS_COMPLETED,
)
from app.core.governance_profiles import require_governance_profile, governance_profile_to_mode_slice
from app.core.graph_identity import (
    GRAPH_LANE_EXECUTION,
    apply_legacy_graph_contract_compat,
    resolve_graph_lane_kind,
    resolve_ticket_graph_identity,
)
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    get_output_schema_body,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.project_workspaces import (
    project_workspace_manifest_exists,
    resolve_ticket_checkout_truth,
    write_worker_preflight_receipt,
)
from app.core.runtime_node_lifecycle import (
    REASON_CODE_RUNTIME_NODE_TRUTH_CONFLICT,
    RuntimeNodeLifecycleError,
    require_materialized_runtime_node,
)
from app.core.process_assets import (
    build_failure_fingerprint_process_asset_ref,
    build_project_map_slice_process_asset_ref,
    dedupe_process_asset_refs,
    merge_input_process_asset_refs,
    resolve_process_asset,
)
from app.core.skill_runtime import resolve_skill_binding
from app.core.time import now_local
from app.core.workflow_relationships import WorkflowTicketSnapshot, list_workflow_ticket_snapshots
from app.core.developer_inspector import (
    DeveloperInspectorStore,
    PersistedDeveloperInspectorArtifact,
)
from app.db.repository import ControlPlaneRepository

MINIMAL_CONTEXT_COMPILER_VERSION = "context-compiler.min.v1"
MINIMAL_CONTEXT_COMPILER_MODEL_PROFILE = "boardroom_os.runtime.min"
MINIMAL_CONTEXT_COMPILER_RENDER_TARGET = "json_messages_v1"
REFERENCE_ONLY_WARNING = (
    "Some explicit sources stayed as descriptors instead of being fully inlined."
)
REFERENCE_ONLY_REASON = (
    "Persist explicit source as a reference descriptor."
)
REFERENCE_ONLY_TRANSFORM = "NORMALIZE_REFERENCE_DESCRIPTOR"
INLINE_TEXT_TRANSFORM = "HYDRATE_TEXT_BODY"
INLINE_JSON_TRANSFORM = "HYDRATE_JSON_BODY"
TRUNCATE_TEXT_TRANSFORM = "TRUNCATE_TEXT_PREVIEW"
TRUNCATE_JSON_TRANSFORM = "TRUNCATE_JSON_PREVIEW"

FALLBACK_REASON_ARTIFACT_NOT_INDEXED = "ARTIFACT_NOT_INDEXED"
FALLBACK_REASON_ARTIFACT_NOT_READABLE = "ARTIFACT_NOT_READABLE"
FALLBACK_REASON_UNSUPPORTED_ARTIFACT_KIND = "UNSUPPORTED_ARTIFACT_KIND"
FALLBACK_REASON_ARTIFACT_READ_FAILED = "ARTIFACT_READ_FAILED"
FALLBACK_REASON_ARTIFACT_JSON_DECODE_FAILED = "ARTIFACT_JSON_DECODE_FAILED"
FALLBACK_REASON_ARTIFACT_TEXT_DECODE_FAILED = "ARTIFACT_TEXT_DECODE_FAILED"
FALLBACK_REASON_MEDIA_REFERENCE_ONLY = "MEDIA_REFERENCE_ONLY"
FALLBACK_REASON_BINARY_REFERENCE_ONLY = "BINARY_REFERENCE_ONLY"
FALLBACK_REASON_INLINE_BUDGET_EXCEEDED = "INLINE_BUDGET_EXCEEDED"
FALLBACK_REASON_RETRIEVAL_DROPPED_FOR_BUDGET = "RETRIEVAL_DROPPED_FOR_BUDGET"
RETRIEVAL_MATCH_REASON_REVIEW = "RETRIEVAL_REVIEW_MATCH"
RETRIEVAL_MATCH_REASON_INCIDENT = "RETRIEVAL_INCIDENT_MATCH"
RETRIEVAL_MATCH_REASON_ARTIFACT = "RETRIEVAL_ARTIFACT_MATCH"
FRAGMENT_MARKDOWN_STRATEGY = "MARKDOWN_SECTION_MATCH"
FRAGMENT_TEXT_STRATEGY = "TEXT_KEYWORD_WINDOWS"
FRAGMENT_JSON_STRATEGY = "JSON_PATH_MATCH"
_TEXT_WINDOW_RADIUS = 36
_TEXT_HEAD_WINDOW_CHARS = 40
_MAX_FRAGMENT_TEXT_WINDOWS = 2
_MAX_FRAGMENT_MARKDOWN_SECTIONS = 2
_MAX_FRAGMENT_JSON_PATHS = 3
_MAX_FRAGMENT_JSON_DEPTH = 3
_MARKDOWN_FRAGMENT_EXCERPT_CHARS = 96
_GOVERNANCE_FRAGMENT_TERMS = ("acceptance", "constraint", "output", "review", "risk")

_RETRIEVAL_REASON_BY_CHANNEL = {
    "review_summaries": RETRIEVAL_MATCH_REASON_REVIEW,
    "incident_summaries": RETRIEVAL_MATCH_REASON_INCIDENT,
    "artifact_summaries": RETRIEVAL_MATCH_REASON_ARTIFACT,
}

_AUTO_INJECTED_PROCESS_ASSET_OUTPUT_SCHEMAS = {
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    *GOVERNANCE_DOCUMENT_SCHEMA_REFS,
}


@dataclass(frozen=True)
class _PreparedInlineSource:
    content_type: str | None = None
    content_text: str | None = None
    content_json: dict[str, Any] | None = None
    content_truncated: bool = False
    preview_strategy: str | None = None
    fallback_reason: str | None = None
    fallback_reason_code: str | None = None


@dataclass(frozen=True)
class _CompiledSourceDecision:
    block: CompiledContextBlock | None
    source_log: CompileManifestSourceLogEntry
    transform_log: CompileManifestTransformLogEntry
    warning: str | None = None


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


def _normalize_retrieval_terms(*values: str) -> list[str]:
    terms: set[str] = set()
    for value in values:
        for term in re.findall(r"[a-z0-9]+", value.lower()):
            if len(term) >= 3:
                terms.add(term)
    return sorted(terms)


def _auto_injected_failure_fingerprint_refs(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    connection: sqlite3.Connection | None,
) -> list[str]:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        rows = resolved_connection.execute(
            """
            SELECT *
            FROM incident_projection
            WHERE workflow_id = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 10
            """,
            (workflow_id,),
        ).fetchall()
        incidents = [
            repository._convert_incident_projection_row(row)
            for row in rows
        ]
        ranked_incidents = sorted(
            incidents,
            key=lambda incident: (
                0
                if str(incident.get("ticket_id") or "").strip() == ticket_id
                or str(incident.get("node_id") or "").strip() == node_id
                else 1
                if str(incident.get("ticket_id") or "").strip()
                or str(incident.get("node_id") or "").strip()
                else 2,
                -(
                    incident["opened_at"].timestamp()
                    if incident.get("opened_at") is not None
                    else 0.0
                ),
                str(incident.get("incident_id") or ""),
            ),
        )
        incident_refs = [
            build_failure_fingerprint_process_asset_ref(str(incident.get("incident_id") or "").strip())
            for incident in ranked_incidents
            if str(incident.get("incident_id") or "").strip()
        ]
    return dedupe_process_asset_refs(incident_refs)[:3]


def _auto_injected_process_asset_refs(
    repository: ControlPlaneRepository,
    *,
    ticket: dict[str, Any],
    created_spec: dict[str, Any],
    connection: sqlite3.Connection | None,
) -> list[str]:
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if output_schema_ref not in _AUTO_INJECTED_PROCESS_ASSET_OUTPUT_SCHEMAS:
        return []
    workflow_id = str(ticket["workflow_id"])
    injected_refs = [
        build_project_map_slice_process_asset_ref(workflow_id),
        *_auto_injected_failure_fingerprint_refs(
            repository,
            workflow_id=workflow_id,
            ticket_id=str(ticket["ticket_id"]),
            node_id=str(ticket["node_id"]),
            connection=connection,
        ),
    ]
    return dedupe_process_asset_refs(injected_refs)


def _build_descriptor_payload(source: CompileRequestExplicitSource) -> dict[str, Any]:
    display_ref = _display_source_ref(source)
    content_payload = {
        "source_ref": display_ref,
        "is_mandatory": source.is_mandatory,
    }
    if source.process_asset_kind != "ARTIFACT":
        content_payload["process_asset_ref"] = source.source_ref
        content_payload["source_kind"] = source.source_kind
        content_payload["process_asset_kind"] = source.process_asset_kind
    if source.producer_ticket_id is not None:
        content_payload["producer_ticket_id"] = source.producer_ticket_id
    if source.source_summary and source.process_asset_kind != "ARTIFACT":
        content_payload["summary"] = source.source_summary
    if source.consumable_by and source.process_asset_kind != "ARTIFACT":
        content_payload["consumable_by"] = list(source.consumable_by)
    if source.source_metadata and source.process_asset_kind != "ARTIFACT":
        content_payload["source_metadata"] = dict(source.source_metadata)
    if source.artifact_access is not None:
        artifact_access = source.artifact_access.model_dump(mode="json")
        content_payload["artifact_access"] = artifact_access
        if artifact_ref := artifact_access.get("artifact_ref"):
            content_payload["artifact_ref"] = artifact_ref
        if preview_kind := artifact_access.get("preview_kind"):
            content_payload["preview_kind"] = preview_kind
        if display_hint := artifact_access.get("display_hint"):
            content_payload["display_hint"] = display_hint
    return content_payload


def _display_source_ref(source: CompileRequestExplicitSource) -> str:
    if source.process_asset_kind == "ARTIFACT":
        if source.artifact_access is not None:
            return source.artifact_access.artifact_ref
        artifact_ref = source.source_metadata.get("artifact_ref")
        if isinstance(artifact_ref, str) and artifact_ref.strip():
            return artifact_ref
    return source.source_ref


def _set_inline_display_hint(content_payload: dict[str, Any]) -> None:
    content_payload["display_hint"] = "INLINE_BODY"
    artifact_access = content_payload.get("artifact_access")
    if isinstance(artifact_access, dict):
        artifact_access["display_hint"] = "INLINE_BODY"


def _estimate_reference_only_tokens(source: CompileRequestExplicitSource) -> int:
    return _estimate_tokens(_build_descriptor_payload(source))


def _prepare_inline_source(
    repository: ControlPlaneRepository,
    artifact: dict[str, Any] | None,
) -> _PreparedInlineSource:
    if artifact is None:
        return _PreparedInlineSource(
            fallback_reason_code=FALLBACK_REASON_ARTIFACT_NOT_INDEXED,
            fallback_reason="Artifact is not indexed yet, so the compiler kept only its descriptor.",
        )
    if not is_artifact_readable(artifact):
        lifecycle_status = str(artifact.get("lifecycle_status") or "ACTIVE")
        if artifact.get("deleted_at") is not None:
            lifecycle_status = "DELETED"
        return _PreparedInlineSource(
            fallback_reason_code=FALLBACK_REASON_ARTIFACT_NOT_READABLE,
            fallback_reason=(
                "Artifact is not readable for inline hydration "
                f"(materialization={artifact.get('materialization_status')}, lifecycle={lifecycle_status})."
            ),
        )

    artifact_store = repository.artifact_store
    if artifact_store is None:
        return _PreparedInlineSource(
            fallback_reason_code=FALLBACK_REASON_ARTIFACT_READ_FAILED,
            fallback_reason="Artifact store is unavailable, so the compiler kept only the descriptor.",
        )

    normalized_kind = normalize_artifact_kind(str(artifact.get("kind") or ""))
    preview_kind = build_artifact_access_descriptor(
        artifact,
        artifact_ref=str(artifact.get("artifact_ref") or ""),
    ).get("preview_kind")
    if normalized_kind not in {"TEXT", "MARKDOWN", "JSON"}:
        if preview_kind == "INLINE_MEDIA":
            return _PreparedInlineSource(
                fallback_reason_code=FALLBACK_REASON_MEDIA_REFERENCE_ONLY,
                fallback_reason=(
                    f"Artifact kind {normalized_kind} is preserved as a structured media reference "
                    "for the current MVP instead of inlining its raw binary body."
                ),
            )
        if preview_kind == "DOWNLOAD_ONLY":
            return _PreparedInlineSource(
                fallback_reason_code=FALLBACK_REASON_BINARY_REFERENCE_ONLY,
                fallback_reason=(
                    f"Artifact kind {normalized_kind} is preserved as a structured binary reference "
                    "for the current MVP instead of inlining its raw binary body."
                ),
            )
        return _PreparedInlineSource(
            fallback_reason_code=FALLBACK_REASON_UNSUPPORTED_ARTIFACT_KIND,
            fallback_reason=(
                f"Artifact kind {normalized_kind} is not eligible for inline hydration in the current MVP."
            ),
        )

    try:
        body = artifact_store.read_bytes(
            artifact.get("storage_relpath"),
            storage_object_key=artifact.get("storage_object_key"),
        )
    except Exception as exc:
        return _PreparedInlineSource(
            fallback_reason_code=FALLBACK_REASON_ARTIFACT_READ_FAILED,
            fallback_reason=f"Artifact body could not be read for inline hydration: {exc}",
        )

    if normalized_kind == "JSON":
        try:
            return _PreparedInlineSource(
                content_type="JSON",
                content_json=json.loads(body.decode("utf-8")),
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _PreparedInlineSource(
                fallback_reason_code=FALLBACK_REASON_ARTIFACT_JSON_DECODE_FAILED,
                fallback_reason=f"Artifact JSON body could not be decoded for inline hydration: {exc}",
            )

    try:
        return _PreparedInlineSource(
            content_type="TEXT",
            content_text=body.decode("utf-8"),
        )
    except UnicodeDecodeError as exc:
        return _PreparedInlineSource(
            fallback_reason_code=FALLBACK_REASON_ARTIFACT_TEXT_DECODE_FAILED,
            fallback_reason=f"Artifact text body could not be decoded for inline hydration: {exc}",
        )


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
    normalized_profiles = normalize_persona_profiles(
        compile_request.worker_binding.employee_role_type,
        skill_profile=compile_request.worker_binding.skill_profile,
        personality_profile=compile_request.worker_binding.personality_profile,
        aesthetic_profile=compile_request.worker_binding.aesthetic_profile,
    )
    return CompiledRole(
        role_profile_ref=compile_request.control_refs.role_profile_ref,
        employee_id=compile_request.worker_binding.employee_id,
        employee_role_type=compile_request.worker_binding.employee_role_type,
        skill_profile=normalized_profiles["skill_profile"],
        personality_profile=normalized_profiles["personality_profile"],
        aesthetic_profile=normalized_profiles["aesthetic_profile"],
        persona_summary=normalized_profiles["profile_summary"],
    )


def _build_compiled_constraints(compile_request: CompileRequest) -> CompiledConstraints:
    return CompiledConstraints(
        constraints_ref=compile_request.control_refs.constraints_ref,
        global_rules=[],
        board_constraints=[],
        budget_constraints={},
    )


_ROLE_PROFILE_TO_ROLE_TYPE = {
    "ui_designer_primary": "frontend_engineer",
    "frontend_engineer_primary": "frontend_engineer",
    "checker_primary": "checker",
    "backend_engineer_primary": "backend_engineer",
    "database_engineer_primary": "database_engineer",
    "platform_sre_primary": "platform_sre",
    "architect_primary": "governance_architect",
    "cto_primary": "governance_cto",
}


def _role_type_for_profile(role_profile_ref: str | None, *, fallback: str | None = None) -> str:
    normalized_profile = str(role_profile_ref or "").strip()
    if normalized_profile in _ROLE_PROFILE_TO_ROLE_TYPE:
        return _ROLE_PROFILE_TO_ROLE_TYPE[normalized_profile]
    normalized_fallback = str(fallback or "").strip()
    return normalized_fallback or "unknown"


def _build_org_relation(
    snapshot: WorkflowTicketSnapshot,
    *,
    relation_reason: str,
    fallback_role_type: str | None = None,
) -> CompileRequestOrgRelation | None:
    if snapshot.ticket_id is None:
        return None
    return CompileRequestOrgRelation(
        ticket_id=snapshot.ticket_id,
        node_id=snapshot.node_id,
        role_profile_ref=str(snapshot.role_profile_ref or "unknown"),
        role_type=_role_type_for_profile(snapshot.role_profile_ref, fallback=fallback_role_type),
        employee_id=snapshot.lease_owner,
        status=snapshot.ticket_status,
        relation_reason=relation_reason,
    )


def _build_expected_downstream_reviewer(
    ticket: dict[str, Any],
    created_spec: dict[str, Any],
    *,
    fallback_role_type: str,
) -> CompileRequestOrgRelation:
    role_profile_ref = str(created_spec.get("role_profile_ref") or "").strip()
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF or role_profile_ref == "ui_designer_primary":
        expected_role_profile = "frontend_engineer_primary"
    elif role_profile_ref == "checker_primary":
        expected_role_profile = "frontend_engineer_primary"
    else:
        expected_role_profile = "checker_primary"
    return CompileRequestOrgRelation(
        ticket_id=str(ticket["ticket_id"]),
        node_id=str(ticket["node_id"]),
        role_profile_ref=expected_role_profile,
        role_type=_role_type_for_profile(expected_role_profile, fallback=fallback_role_type),
        employee_id=None,
        status="EXPECTED",
        relation_reason="EXPECTED_DOWNSTREAM_REVIEWER",
    )


def _build_org_context(
    repository: ControlPlaneRepository,
    *,
    ticket: dict[str, Any],
    created_spec: dict[str, Any],
    employee_role_type: str,
    connection: sqlite3.Connection | None = None,
) -> CompileRequestOrgContext:
    with repository.connection() if connection is None else nullcontext(connection) as active_connection:
        snapshots = list_workflow_ticket_snapshots(
            repository,
            str(ticket["workflow_id"]),
            connection=active_connection,
        )

    snapshot_by_ticket_id = {
        str(snapshot.ticket_id): snapshot
        for snapshot in snapshots
        if snapshot.ticket_id is not None
    }
    current_snapshot = snapshot_by_ticket_id.get(str(ticket["ticket_id"]))
    parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip() or None
    upstream_provider = (
        _build_org_relation(
            snapshot_by_ticket_id[parent_ticket_id],
            relation_reason="PARENT_TICKET",
        )
        if parent_ticket_id and parent_ticket_id in snapshot_by_ticket_id
        else None
    )

    dependent_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.parent_ticket_id == str(ticket["ticket_id"]) and snapshot.ticket_id is not None
    ]
    dependent_snapshots.sort(
        key=lambda snapshot: (
            0 if _role_type_for_profile(snapshot.role_profile_ref) == "checker" else 1,
            snapshot.sort_updated_at or now_local(),
            snapshot.ticket_id or "",
        )
    )
    downstream_reviewer = None
    if dependent_snapshots:
        downstream_reviewer = _build_org_relation(
            dependent_snapshots[0],
            relation_reason="DIRECT_DEPENDENT_TICKET",
        )
    if downstream_reviewer is None:
        downstream_reviewer = _build_expected_downstream_reviewer(
            ticket,
            created_spec,
            fallback_role_type=employee_role_type,
        )

    excluded_ticket_ids = {
        str(ticket["ticket_id"]),
        str(upstream_provider.ticket_id) if upstream_provider is not None else "",
        str(downstream_reviewer.ticket_id) if downstream_reviewer is not None else "",
    }
    collaborators: list[CompileRequestOrgRelation] = []
    if parent_ticket_id:
        for snapshot in snapshots:
            if (
                snapshot.parent_ticket_id != parent_ticket_id
                or snapshot.ticket_id is None
                or snapshot.ticket_id in excluded_ticket_ids
                or snapshot.ticket_status == TICKET_STATUS_COMPLETED
            ):
                continue
            relation = _build_org_relation(snapshot, relation_reason="ACTIVE_SIBLING_TICKET")
            if relation is not None:
                collaborators.append(relation)

    current_node_id = str(ticket["node_id"])
    current_ticket_id = str(ticket["ticket_id"])
    open_review_pack_id = None
    for approval in repository.list_open_approvals():
        if str(approval.get("workflow_id") or "") != str(ticket["workflow_id"]):
            continue
        subject = (((approval.get("payload") or {}).get("review_pack") or {}).get("subject") or {})
        if (
            str(subject.get("source_node_id") or "").strip() == current_node_id
            or str(subject.get("source_ticket_id") or "").strip() == current_ticket_id
        ):
            open_review_pack_id = str(approval["review_pack_id"])
            break

    open_incident_id = None
    for incident in repository.list_open_incidents():
        if str(incident.get("workflow_id") or "") != str(ticket["workflow_id"]):
            continue
        if (
            str(incident.get("node_id") or "").strip() == current_node_id
            or str(incident.get("ticket_id") or "").strip() == current_ticket_id
        ):
            open_incident_id = str(incident["incident_id"])
            break

    escalation_policy = TicketEscalationPolicy.model_validate(created_spec.get("escalation_policy") or {})
    current_blocking_reason = str(ticket.get("blocking_reason_code") or "").strip() or None
    responsibility_boundary = CompileRequestResponsibilityBoundary(
        delivery_stage=(
            current_snapshot.delivery_stage
            if current_snapshot is not None and current_snapshot.delivery_stage is not None
            else (str(created_spec.get("delivery_stage") or "").strip().upper() or None)
        ),
        output_schema_ref=str(created_spec.get("output_schema_ref") or ""),
        allowed_write_set=list(created_spec.get("allowed_write_set") or []),
        board_review_possible=(
            current_blocking_reason == BLOCKING_REASON_BOARD_REVIEW_REQUIRED
            or open_review_pack_id is not None
        ),
        incident_path_possible=True,
    )
    return CompileRequestOrgContext(
        upstream_provider=upstream_provider,
        downstream_reviewer=downstream_reviewer,
        collaborators=collaborators,
        escalation_path=CompileRequestEscalationPath(
            current_blocking_reason=current_blocking_reason,
            open_review_pack_id=open_review_pack_id,
            open_incident_id=open_incident_id,
            path=[
                str(action)
                for action in (
                    escalation_policy.on_timeout,
                    escalation_policy.on_schema_error,
                    escalation_policy.on_repeat_failure,
                )
            ],
        ),
        responsibility_boundary=responsibility_boundary,
    )


def _build_execution_package_meta(compile_request: CompileRequest) -> CompiledExecutionPackageMeta:
    return CompiledExecutionPackageMeta(
        compile_request_id=compile_request.meta.compile_request_id,
        ticket_id=compile_request.meta.ticket_id,
        workflow_id=compile_request.meta.workflow_id,
        node_id=compile_request.meta.node_id,
        attempt_no=compile_request.meta.attempt_no,
        governance_profile_ref=compile_request.meta.governance_profile_ref,
        lease_owner=compile_request.worker_binding.lease_owner,
        tenant_id=compile_request.meta.tenant_id,
        workspace_id=compile_request.meta.workspace_id,
        compiler_version=MINIMAL_CONTEXT_COMPILER_VERSION,
        ticket_projection_version=compile_request.meta.ticket_projection_version,
        node_projection_version=compile_request.meta.node_projection_version,
        runtime_node_projection_version=compile_request.meta.runtime_node_projection_version,
        source_projection_version=compile_request.meta.source_projection_version,
    )


def _resolve_task_category(compile_request: CompileRequest) -> str:
    if compile_request.meta.attempt_no > 1 or compile_request.org_context.escalation_path.open_incident_id is not None:
        return "debugging"
    output_schema_ref = str(compile_request.control_refs.output_schema_ref or "").strip()
    deliverable_kind = str(compile_request.execution.deliverable_kind or "").strip()
    if deliverable_kind == "structured_document_delivery":
        return "planning"
    if output_schema_ref in {"maker_checker_verdict", "delivery_check_report", "ui_milestone_review"}:
        return "review"
    return "implementation"


def _build_task_frame(compile_request: CompileRequest) -> CompiledTaskFrame:
    task_category = _resolve_task_category(compile_request)
    completion_definition = list(compile_request.execution.acceptance_criteria)
    if not completion_definition:
        completion_definition = [
            (
                "Return output that matches "
                f"{compile_request.control_refs.output_schema_ref}@{compile_request.control_refs.output_schema_version}."
            )
        ]
    return CompiledTaskFrame(
        task_category=task_category,
        goal=(
            "Produce output for ticket "
            f"{compile_request.meta.ticket_id} that satisfies {compile_request.control_refs.output_schema_ref}."
        ),
        completion_definition=completion_definition,
        failure_definition=[
            "Reject schema-invalid output.",
            "Reject write-set violations.",
            "Reject missing required documentation surfaces or evidence.",
        ],
        deliverable_kind=compile_request.execution.deliverable_kind,
    )


def _build_context_layer_summary(
    compile_request: CompileRequest,
    *,
    context_block_count: int,
) -> CompiledContextLayerSummary:
    governance_profile_ref = compile_request.governance_mode_slice.governance_profile_ref
    return CompiledContextLayerSummary(
        w0_constitution=ContextLayerSectionSummary(
            label="W0 Constitution",
            item_count=1,
            notes=[
                f"approval_mode={compile_request.governance_mode_slice.approval_mode}",
                f"audit_mode={compile_request.governance_mode_slice.audit_mode}",
            ],
            governance_profile_ref=governance_profile_ref,
        ),
        w1_task_frame=ContextLayerSectionSummary(
            label="W1 Task Frame",
            item_count=max(len(compile_request.execution.acceptance_criteria), 1),
            notes=[f"output_schema={compile_request.control_refs.output_schema_ref}"],
        ),
        w2_evidence=ContextLayerSectionSummary(
            label="W2 Evidence Slice",
            item_count=context_block_count,
            notes=[f"required_read_refs={len(compile_request.execution.required_read_refs)}"],
        ),
        w3_runtime_guard=ContextLayerSectionSummary(
            label="W3 Runtime Guard",
            item_count=(
                len(compile_request.execution.allowed_tools)
                + len(compile_request.execution.allowed_write_set)
                + len(compile_request.execution.doc_update_requirements)
            ),
            notes=[f"forced_skill_ids={len(compile_request.execution.forced_skill_ids)}"],
            allowed_tool_count=len(compile_request.execution.allowed_tools),
            allowed_write_set_count=len(compile_request.execution.allowed_write_set),
        ),
    )


def _build_reference_block(
    source: CompileRequestExplicitSource,
    *,
    reason: str | None = None,
    reason_code: str | None = None,
    status: str = "USED",
    tokens_before: int | None = None,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=_display_source_ref(source),
    )
    content_payload = _build_descriptor_payload(source)
    token_estimate = _estimate_tokens(content_payload)
    source_tokens_before = max(tokens_before or token_estimate, token_estimate)
    fallback_reason = reason or source.inline_fallback_reason or REFERENCE_ONLY_REASON
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        trust_level=1,
        instruction_authority="DATA_ONLY",
        priority_class="P1" if source.is_mandatory else "P2",
        selector=selector,
        transform_chain=[REFERENCE_ONLY_TRANSFORM],
        content_type="SOURCE_DESCRIPTOR",
        content_mode="REFERENCE_ONLY",
        content_payload=content_payload,
        degradation_reason_code=reason_code or source.inline_fallback_reason_code,
        token_estimate=token_estimate,
        relevance_score=1.0 if source.is_mandatory else 0.7,
        source_hash=_stable_hash(content_payload),
        trust_note=fallback_reason,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        priority_class=block.priority_class,
        trust_level=block.trust_level,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        content_mode=block.content_mode,
        critical=source.is_mandatory,
        status=status,
        tokens_before=source_tokens_before,
        tokens_after=token_estimate,
        reason=fallback_reason,
        reason_code=reason_code or source.inline_fallback_reason_code,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="NORMALIZE_SOURCES",
        operation_type="NORMALIZE",
        target_ref=_display_source_ref(source),
        output_block_id=block.block_id,
        reason=fallback_reason,
    )
    return block, source_log, transform_log


def _build_inline_block(
    source: CompileRequestExplicitSource,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=_display_source_ref(source),
    )
    content_payload = _build_descriptor_payload(source)
    transform = INLINE_TEXT_TRANSFORM
    content_type = "TEXT"
    reason = "Inlined active materialized artifact body into the execution package."
    if source.inline_content_type == "JSON":
        content_payload["content_json"] = dict(source.inline_content_json or {})
        content_type = "JSON"
        transform = INLINE_JSON_TRANSFORM
    else:
        content_payload["content_text"] = source.inline_content_text or ""
    content_payload["content_truncated"] = source.inline_content_truncated
    if source.inline_preview_strategy is not None:
        content_payload["content_preview_strategy"] = source.inline_preview_strategy
    _set_inline_display_hint(content_payload)

    token_estimate = _estimate_tokens(content_payload)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        trust_level=1,
        instruction_authority="DATA_ONLY",
        priority_class="P1" if source.is_mandatory else "P2",
        selector=selector,
        transform_chain=[transform],
        content_type=content_type,
        content_mode="INLINE_FULL",
        content_payload=content_payload,
        degradation_reason_code=None,
        token_estimate=token_estimate,
        relevance_score=1.0 if source.is_mandatory else 0.7,
        source_hash=_stable_hash(content_payload),
        trust_note=reason,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        priority_class=block.priority_class,
        trust_level=block.trust_level,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        content_mode=block.content_mode,
        critical=source.is_mandatory,
        status="USED",
        tokens_before=token_estimate,
        tokens_after=token_estimate,
        reason=reason,
        reason_code=None,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="HYDRATE_SOURCES",
        operation_type="HYDRATE",
        target_ref=_display_source_ref(source),
        output_block_id=block.block_id,
        reason=reason,
    )
    return block, source_log, transform_log


def _build_json_preview_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        preview: dict[str, Any] = {
            "_preview": {
                "strategy": "TOP_LEVEL_PREVIEW",
                "truncated": True,
                "type": "object",
                "key_count": len(value),
                "keys": list(value.keys())[:8],
            }
        }
        for key, item in list(value.items())[:4]:
            if isinstance(item, (str, int, float, bool)) or item is None:
                preview[key] = item
            elif isinstance(item, list):
                preview[key] = {
                    "_preview_type": "list",
                    "length": len(item),
                    "sample": [
                        sample if isinstance(sample, (str, int, float, bool)) or sample is None else type(sample).__name__
                        for sample in item[:3]
                    ],
                }
            elif isinstance(item, dict):
                preview[key] = {
                    "_preview_type": "object",
                    "key_count": len(item),
                    "keys": list(item.keys())[:6],
                }
            else:
                preview[key] = str(item)
        return preview
    if isinstance(value, list):
        return {
            "_preview": {
                "strategy": "TOP_LEVEL_PREVIEW",
                "truncated": True,
                "type": "list",
                "length": len(value),
            },
            "sample": [
                item if isinstance(item, (str, int, float, bool)) or item is None else type(item).__name__
                for item in value[:3]
            ],
        }
    return {
        "_preview": {
            "strategy": "TOP_LEVEL_PREVIEW",
            "truncated": True,
            "type": type(value).__name__,
        },
        "value": value if isinstance(value, (str, int, float, bool)) or value is None else str(value),
    }


def _terms_match_text(value: str, terms: list[str]) -> bool:
    lower_value = value.lower()
    return any(term in lower_value for term in terms)


def _build_fragment_terms(
    retrieval_plan: CompileRequestRetrievalPlan,
    acceptance_criteria: list[str],
) -> list[str]:
    return sorted(
        set(retrieval_plan.normalized_terms).union(
            _normalize_retrieval_terms(*acceptance_criteria)
        )
        - {"must", "keep", "with", "from", "into", "that", "this", "then", "than", "when", "where", "while", "have", "has", "had", "were", "will", "and"}
    )


def _split_markdown_sections(content_text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Document Start"
    current_lines: list[str] = []

    for line in content_text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading is not None:
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = heading.group(2).strip()
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, raw) for title, raw in sections if raw]


def _build_markdown_fragment_source(
    source: CompileRequestExplicitSource,
    fragment_terms: list[str],
) -> CompileRequestExplicitSource | None:
    content_text = str(source.inline_content_text or "")
    if not content_text.strip():
        return None

    sections = _split_markdown_sections(content_text)
    if not sections:
        return None

    selected_titles: list[str] = []
    selected_raw_sections: list[str] = []
    for title, raw in sections:
        lower_raw = raw.lower()
        matched = _terms_match_text(raw, fragment_terms)
        governance_matched = any(term in lower_raw for term in _GOVERNANCE_FRAGMENT_TERMS)
        if matched or governance_matched:
            selected_titles.append(title)
            selected_raw_sections.append(raw)
        if len(selected_titles) >= _MAX_FRAGMENT_MARKDOWN_SECTIONS:
            break

    if len(selected_titles) < _MAX_FRAGMENT_MARKDOWN_SECTIONS:
        first_title, first_raw = sections[0]
        if first_title not in selected_titles:
            selected_titles.append(first_title)
            selected_raw_sections.append(first_raw)

    if not selected_titles:
        return None

    selected_titles = selected_titles[:_MAX_FRAGMENT_MARKDOWN_SECTIONS]
    selected_raw_sections = selected_raw_sections[:_MAX_FRAGMENT_MARKDOWN_SECTIONS]
    selector_value = "|".join(selected_titles)
    fragment_parts: list[str] = []
    for raw in selected_raw_sections:
        raw_lines = raw.splitlines()
        heading_line = raw_lines[0].strip() if raw_lines else ""
        body_excerpt = " ".join(line.strip() for line in raw_lines[1:] if line.strip())[
            :_MARKDOWN_FRAGMENT_EXCERPT_CHARS
        ].strip()
        if body_excerpt:
            fragment_parts.append(f"{heading_line}\n\n{body_excerpt}")
        else:
            fragment_parts.append(heading_line)
    fragment_text = "\n\n".join(part for part in fragment_parts if part).strip()
    if not fragment_text:
        return None

    return source.model_copy(
        update={
            "fragment_selector_type": "MARKDOWN_SECTION",
            "fragment_selector_value": selector_value,
            "fragment_content_type": "TEXT",
            "fragment_content_text": fragment_text,
            "fragment_content_json": None,
            "fragment_metadata": {
                "content_fragment_strategy": FRAGMENT_MARKDOWN_STRATEGY,
                "selected_sections": selected_titles,
                "omitted_section_count": max(0, len(sections) - len(selected_titles)),
            },
        }
    )


def _merge_text_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not windows:
        return []
    ordered = sorted(windows)
    merged: list[tuple[int, int]] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 8:
            merged[-1] = (last_start, max(last_end, end))
            continue
        merged.append((start, end))
    return merged


def _build_text_fragment_source(
    source: CompileRequestExplicitSource,
    fragment_terms: list[str],
) -> CompileRequestExplicitSource | None:
    content_text = str(source.inline_content_text or "")
    if not content_text.strip():
        return None

    lower_text = content_text.lower()
    match_windows: list[tuple[int, int]] = []
    for term in fragment_terms:
        term_index = lower_text.find(term)
        if term_index < 0:
            continue
        start = max(0, term_index - _TEXT_WINDOW_RADIUS)
        end = min(len(content_text), term_index + len(term) + _TEXT_WINDOW_RADIUS)
        match_windows.append((start, end))
        if len(match_windows) >= _MAX_FRAGMENT_TEXT_WINDOWS:
            break

    if not match_windows:
        return None

    windows = [(0, min(len(content_text), _TEXT_HEAD_WINDOW_CHARS))]
    windows.extend(match_windows)
    merged_windows = _merge_text_windows(windows)
    fragment_text = "\n...\n".join(
        content_text[start:end].strip() for start, end in merged_windows if content_text[start:end].strip()
    ).strip()
    if not fragment_text:
        return None

    return source.model_copy(
        update={
            "fragment_selector_type": "TEXT_WINDOW",
            "fragment_selector_value": ";".join(f"{start}:{end}" for start, end in merged_windows),
            "fragment_content_type": "TEXT",
            "fragment_content_text": fragment_text,
            "fragment_content_json": None,
            "fragment_metadata": {
                "content_fragment_strategy": FRAGMENT_TEXT_STRATEGY,
                "selected_windows": [
                    {"start": start, "end": end} for start, end in merged_windows
                ],
                "omitted_window_count": max(0, len(match_windows) - _MAX_FRAGMENT_TEXT_WINDOWS),
            },
        }
    )


def _json_node_matches(key: str, value: Any, fragment_terms: list[str]) -> bool:
    if _terms_match_text(key, fragment_terms):
        return True
    if isinstance(value, str):
        return _terms_match_text(value, fragment_terms)
    if isinstance(value, dict):
        for child_value in value.values():
            if isinstance(child_value, str) and _terms_match_text(child_value, fragment_terms):
                return True
    if isinstance(value, list):
        for item in value[:4]:
            if isinstance(item, str) and _terms_match_text(item, fragment_terms):
                return True
    return False


def _collect_json_fragment_paths(
    value: Any,
    *,
    path: str,
    fragment_terms: list[str],
    depth: int,
) -> list[str]:
    if depth > _MAX_FRAGMENT_JSON_DEPTH or not isinstance(value, dict):
        return []

    paths: list[str] = []
    for key, child in value.items():
        child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
        if _json_node_matches(str(key), child, fragment_terms):
            paths.append(child_path)
            continue
        if isinstance(child, dict):
            paths.extend(
                _collect_json_fragment_paths(
                    child,
                    path=child_path,
                    fragment_terms=fragment_terms,
                    depth=depth + 1,
                )
            )
    return paths


def _lookup_json_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.removeprefix("$.").split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _assign_json_fragment_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.removeprefix("$.").split(".")
    current = target
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _build_json_fragment_source(
    source: CompileRequestExplicitSource,
    fragment_terms: list[str],
) -> CompileRequestExplicitSource | None:
    content_json = source.inline_content_json or {}
    if not isinstance(content_json, dict):
        return None

    candidate_paths = sorted(set(_collect_json_fragment_paths(content_json, path="$", fragment_terms=fragment_terms, depth=1)))
    if not candidate_paths:
        return None

    selected_paths = candidate_paths[:_MAX_FRAGMENT_JSON_PATHS]
    fragment_json: dict[str, Any] = {}
    for path in selected_paths:
        path_value = _lookup_json_path(content_json, path)
        if path_value is None:
            continue
        _assign_json_fragment_path(fragment_json, path, path_value)
    if not fragment_json:
        return None

    return source.model_copy(
        update={
            "fragment_selector_type": "JSON_PATH",
            "fragment_selector_value": "|".join(selected_paths),
            "fragment_content_type": "JSON",
            "fragment_content_text": None,
            "fragment_content_json": fragment_json,
            "fragment_metadata": {
                "content_fragment_strategy": FRAGMENT_JSON_STRATEGY,
                "selected_json_paths": selected_paths,
                "omitted_path_count": max(0, len(candidate_paths) - len(selected_paths)),
            },
        }
    )


def _build_fragment_candidate(
    source: CompileRequestExplicitSource,
    *,
    fragment_terms: list[str],
) -> CompileRequestExplicitSource:
    if source.inline_content_type is None or not fragment_terms:
        return source

    artifact_kind = str((source.artifact_access.kind if source.artifact_access is not None else "") or "")
    if source.inline_content_type == "JSON":
        return _build_json_fragment_source(source, fragment_terms) or source
    if artifact_kind == "MARKDOWN":
        return _build_markdown_fragment_source(source, fragment_terms) or source
    return _build_text_fragment_source(source, fragment_terms) or source


def _build_budget_preview_source(source: CompileRequestExplicitSource) -> CompileRequestExplicitSource | None:
    if source.inline_content_type == "TEXT":
        content_text = str(source.inline_content_text or "")
        excerpt = content_text[:160].rstrip()
        if not excerpt:
            excerpt = content_text[:160]
        if not excerpt:
            return None
        return source.model_copy(
            update={
                "inline_content_text": excerpt,
                "inline_content_truncated": True,
                "inline_preview_strategy": "HEAD_EXCERPT",
            }
        )
    if source.inline_content_type == "JSON":
        return source.model_copy(
            update={
                "inline_content_json": _build_json_preview_payload(source.inline_content_json or {}),
                "inline_content_truncated": True,
                "inline_preview_strategy": "TOP_LEVEL_PREVIEW",
            }
        )
    return None


def _build_fragment_block(
    source: CompileRequestExplicitSource,
    *,
    tokens_before: int | None = None,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type=str(source.fragment_selector_type or "SOURCE_REF"),
        selector_value=str(source.fragment_selector_value or _display_source_ref(source)),
    )
    content_payload = _build_descriptor_payload(source)
    content_payload.update(source.fragment_metadata)
    if source.fragment_content_type == "JSON":
        content_type = "JSON"
        content_payload["content_json"] = dict(source.fragment_content_json or {})
    else:
        content_type = "TEXT"
        content_payload["content_text"] = source.fragment_content_text or ""
    content_payload["content_truncated"] = True
    _set_inline_display_hint(content_payload)

    reason = (
        f"Inline hydration for {_display_source_ref(source)} exceeded the full-body budget, so the compiler kept "
        "deterministic relevant fragments instead of only the head preview."
    )
    token_estimate = _estimate_tokens(content_payload)
    source_tokens_before = max(tokens_before or token_estimate, token_estimate)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        trust_level=1,
        instruction_authority="DATA_ONLY",
        priority_class="P1" if source.is_mandatory else "P2",
        selector=selector,
        transform_chain=["SUMMARIZE"],
        content_type=content_type,
        content_mode="INLINE_FRAGMENT",
        content_payload=content_payload,
        degradation_reason_code=None,
        token_estimate=token_estimate,
        relevance_score=1.0 if source.is_mandatory else 0.7,
        source_hash=_stable_hash(content_payload),
        trust_note=reason,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        priority_class=block.priority_class,
        trust_level=block.trust_level,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        content_mode=block.content_mode,
        critical=source.is_mandatory,
        status="SUMMARIZED",
        tokens_before=source_tokens_before,
        tokens_after=token_estimate,
        reason=reason,
        reason_code=FALLBACK_REASON_INLINE_BUDGET_EXCEEDED,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="BUDGET_ENFORCEMENT",
        operation_type="SUMMARIZE",
        target_ref=_display_source_ref(source),
        output_block_id=block.block_id,
        reason=reason,
    )
    return block, source_log, transform_log


def _build_partial_inline_block(
    source: CompileRequestExplicitSource,
    *,
    tokens_before: int | None = None,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=_display_source_ref(source),
    )
    content_payload = _build_descriptor_payload(source)
    content_payload["content_truncated"] = True
    preview_strategy = source.inline_preview_strategy or "HEAD_EXCERPT"
    transform = TRUNCATE_TEXT_TRANSFORM
    content_type = "TEXT"
    if source.inline_content_type == "JSON":
        content_type = "JSON"
        transform = TRUNCATE_JSON_TRANSFORM
        content_payload["content_json"] = dict(source.inline_content_json or {})
    else:
        content_payload["content_text"] = source.inline_content_text or ""
    content_payload["content_preview_strategy"] = preview_strategy
    _set_inline_display_hint(content_payload)

    reason = (
        f"Inline hydration for {_display_source_ref(source)} exceeded the token budget, so the compiler kept "
        "a deterministic preview instead of the full body."
    )
    token_estimate = _estimate_tokens(content_payload)
    source_tokens_before = max(tokens_before or token_estimate, token_estimate)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        trust_level=1,
        instruction_authority="DATA_ONLY",
        priority_class="P1" if source.is_mandatory else "P2",
        selector=selector,
        transform_chain=[transform],
        content_type=content_type,
        content_mode="INLINE_PARTIAL",
        content_payload=content_payload,
        degradation_reason_code=FALLBACK_REASON_INLINE_BUDGET_EXCEEDED,
        token_estimate=token_estimate,
        relevance_score=1.0 if source.is_mandatory else 0.7,
        source_hash=_stable_hash(content_payload),
        trust_note=reason,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        priority_class=block.priority_class,
        trust_level=block.trust_level,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        content_mode=block.content_mode,
        critical=source.is_mandatory,
        status="TRUNCATED",
        tokens_before=source_tokens_before,
        tokens_after=token_estimate,
        reason=reason,
        reason_code=FALLBACK_REASON_INLINE_BUDGET_EXCEEDED,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="BUDGET_ENFORCEMENT",
        operation_type="TRUNCATE",
        target_ref=_display_source_ref(source),
        output_block_id=block.block_id,
        reason=reason,
    )
    return block, source_log, transform_log


def _build_dropped_explicit_source_logs(
    source: CompileRequestExplicitSource,
    *,
    reason: str,
    reason_code: str | None,
    tokens_before: int,
) -> tuple[CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=_display_source_ref(source),
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=_display_source_ref(source),
        source_kind="PROCESS_ASSET",
        priority_class="P1" if source.is_mandatory else "P2",
        trust_level=1,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        content_mode=None,
        critical=source.is_mandatory,
        status="DROPPED",
        tokens_before=max(tokens_before, 0),
        tokens_after=0,
        reason=reason,
        reason_code=reason_code,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="BUDGET_ENFORCEMENT",
        operation_type="DROP",
        target_ref=_display_source_ref(source),
        output_block_id=None,
        reason=reason,
    )
    return source_log, transform_log


def _raise_mandatory_source_budget_error(
    source: CompileRequestExplicitSource,
    *,
    remaining_budget: int,
) -> None:
    raise ValueError(
        "Mandatory explicit source "
        f"{_display_source_ref(source)} cannot fit within the remaining token budget "
        f"({remaining_budget}) even as a reference descriptor."
    )


def _select_explicit_source_for_budget(
    source: CompileRequestExplicitSource,
    *,
    remaining_budget: int,
) -> _CompiledSourceDecision:
    inline_tokens_before: int | None = None
    if source.inline_content_type is not None:
        inline_block, inline_source_log, inline_transform_log = _build_inline_block(source)
        inline_tokens_before = inline_block.token_estimate
        if inline_block.token_estimate <= remaining_budget:
            return _CompiledSourceDecision(
                block=inline_block,
                source_log=inline_source_log,
                transform_log=inline_transform_log,
            )

        if source.fragment_content_type is not None:
            fragment_block, fragment_source_log, fragment_transform_log = _build_fragment_block(
                source,
                tokens_before=inline_tokens_before,
            )
            if fragment_block.token_estimate <= remaining_budget:
                return _CompiledSourceDecision(
                    block=fragment_block,
                    source_log=fragment_source_log,
                    transform_log=fragment_transform_log,
                    warning=fragment_source_log.reason,
                )

        preview_source = _build_budget_preview_source(source)
        if preview_source is not None:
            partial_block, partial_source_log, partial_transform_log = _build_partial_inline_block(
                preview_source,
                tokens_before=inline_tokens_before,
            )
            if partial_block.token_estimate <= remaining_budget:
                return _CompiledSourceDecision(
                    block=partial_block,
                    source_log=partial_source_log,
                    transform_log=partial_transform_log,
                    warning=partial_source_log.reason,
                )

        fallback_reason = (
            f"Inline hydration for {_display_source_ref(source)} exceeded the token budget, so the compiler kept "
            "the source descriptor instead."
        )
        reference_block, reference_source_log, reference_transform_log = _build_reference_block(
            source,
            reason=fallback_reason,
            reason_code=FALLBACK_REASON_INLINE_BUDGET_EXCEEDED,
            status="TRUNCATED",
            tokens_before=inline_tokens_before,
        )
        if reference_block.token_estimate <= remaining_budget:
            return _CompiledSourceDecision(
                block=reference_block,
                source_log=reference_source_log,
                transform_log=reference_transform_log,
                warning=reference_source_log.reason,
            )

        if source.is_mandatory:
            _raise_mandatory_source_budget_error(source, remaining_budget=remaining_budget)

        dropped_source_log, dropped_transform_log = _build_dropped_explicit_source_logs(
            source,
            reason=fallback_reason,
            reason_code=FALLBACK_REASON_INLINE_BUDGET_EXCEEDED,
            tokens_before=max(inline_tokens_before or 0, reference_block.token_estimate),
        )
        return _CompiledSourceDecision(
            block=None,
            source_log=dropped_source_log,
            transform_log=dropped_transform_log,
            warning=dropped_source_log.reason,
        )

    fallback_reason = source.inline_fallback_reason or REFERENCE_ONLY_REASON
    reference_block, reference_source_log, reference_transform_log = _build_reference_block(
        source,
        reason=fallback_reason,
        reason_code=source.inline_fallback_reason_code,
        status="USED",
    )
    if reference_block.token_estimate <= remaining_budget:
        return _CompiledSourceDecision(
            block=reference_block,
            source_log=reference_source_log,
            transform_log=reference_transform_log,
            warning=reference_source_log.reason,
        )

    if source.is_mandatory:
        _raise_mandatory_source_budget_error(source, remaining_budget=remaining_budget)

    dropped_source_log, dropped_transform_log = _build_dropped_explicit_source_logs(
        source,
        reason=fallback_reason,
        reason_code=source.inline_fallback_reason_code,
        tokens_before=reference_block.token_estimate,
    )
    return _CompiledSourceDecision(
        block=None,
        source_log=dropped_source_log,
        transform_log=dropped_transform_log,
        warning=dropped_source_log.reason,
    )


def _build_atomic_context_bundle(context_blocks: list[CompiledContextBlock], token_budget: int) -> AtomicContextBundle:
    return AtomicContextBundle(
        context_blocks=[
            AtomicContextBlock(
                block_id=block.block_id,
                source_ref=block.source_ref,
                source_kind="PROCESS_ASSET" if block.source_kind == "PROCESS_ASSET" else "RETRIEVAL",
                selector=block.selector,
                content_type=block.content_type,
                content_mode=block.content_mode,
                content_payload=dict(block.content_payload),
                degradation_reason_code=block.degradation_reason_code,
            )
            for block in context_blocks
        ],
        token_budget=token_budget,
    )


def _build_rendered_execution_payload(
    *,
    compiled_context_bundle: CompiledContextBundle,
    compile_manifest: CompileManifest,
) -> RenderedExecutionPayload:
    messages: list[RenderedExecutionMessage] = [
        RenderedExecutionMessage(
            role="system",
            channel="SYSTEM_CONTROLS",
            content_type="JSON",
            content_payload=compiled_context_bundle.system_controls.model_dump(mode="json"),
        ),
        RenderedExecutionMessage(
            role="user",
            channel="TASK_DEFINITION",
            content_type="JSON",
            content_payload=compiled_context_bundle.task_definition.model_dump(mode="json"),
        ),
    ]
    retrieval_message_count = 0
    degraded_data_message_count = 0
    reference_message_count = 0
    for block in compiled_context_bundle.context_blocks:
        if block.source_kind == "RETRIEVAL_SUMMARY":
            retrieval_message_count += 1
        if block.content_mode != "INLINE_FULL":
            degraded_data_message_count += 1
        if block.content_mode == "REFERENCE_ONLY":
            reference_message_count += 1
        messages.append(
            RenderedExecutionMessage(
                role="user",
                channel="CONTEXT_BLOCK",
                content_type=block.content_type,
                block_id=block.block_id,
                source_ref=block.source_ref,
                content_payload={
                    "source_kind": block.source_kind,
                    "priority_class": block.priority_class,
                    "content_mode": block.content_mode,
                    "selector": block.selector.model_dump(mode="json"),
                    "degradation_reason_code": block.degradation_reason_code,
                    **block.content_payload,
                },
            )
        )
    messages.append(
        RenderedExecutionMessage(
            role="system",
            channel="OUTPUT_CONTRACT_REMINDER",
            content_type="JSON",
            content_payload={
                "output_schema_ref": compiled_context_bundle.system_controls.output_contract.schema_ref,
                "output_schema_version": compiled_context_bundle.system_controls.output_contract.schema_version,
                "output_schema_body": compiled_context_bundle.system_controls.output_contract.schema_body,
            },
        )
    )
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id=compiled_context_bundle.meta.bundle_id,
            compile_id=compile_manifest.compile_meta.compile_id,
            compile_request_id=compiled_context_bundle.meta.compile_request_id,
            ticket_id=compiled_context_bundle.meta.ticket_id,
            workflow_id=compiled_context_bundle.meta.workflow_id,
            node_id=compiled_context_bundle.meta.node_id,
            compiler_version=compiled_context_bundle.meta.compiler_version,
            model_profile=compiled_context_bundle.meta.model_profile,
            render_target=MINIMAL_CONTEXT_COMPILER_RENDER_TARGET,
            rendered_at=compile_manifest.compile_meta.compiled_at,
        ),
        messages=messages,
        summary=RenderedExecutionPayloadSummary(
            total_message_count=len(messages),
            control_message_count=3,
            data_message_count=len(compiled_context_bundle.context_blocks),
            retrieval_message_count=retrieval_message_count,
            degraded_data_message_count=degraded_data_message_count,
            reference_message_count=reference_message_count,
        ),
    )


def _build_retrieval_plan(
    *,
    tenant_id: str,
    workspace_id: str,
    workflow_id: str,
    context_query_plan: dict[str, Any],
) -> CompileRequestRetrievalPlan:
    normalized_terms = _normalize_retrieval_terms(
        *[str(value) for value in list(context_query_plan.get("keywords") or [])],
        *[str(value) for value in list(context_query_plan.get("semantic_queries") or [])],
    )
    return CompileRequestRetrievalPlan(
        scope_tenant_id=tenant_id,
        scope_workspace_id=workspace_id,
        exclude_workflow_id=workflow_id,
        normalized_terms=normalized_terms,
        max_hits_by_channel={
            "review_summaries": 2,
            "incident_summaries": 2,
            "artifact_summaries": 3,
        },
    )


def _build_retrieved_summaries(
    repository: ControlPlaneRepository,
    retrieval_plan: CompileRequestRetrievalPlan,
    connection: sqlite3.Connection | None = None,
) -> list[CompileRequestRetrievedSummary]:
    if not retrieval_plan.normalized_terms:
        return []

    summaries: list[CompileRequestRetrievedSummary] = []
    channel_loaders = (
        (
            "review_summaries",
            repository.list_retrieval_review_summary_candidates,
        ),
        (
            "incident_summaries",
            repository.list_retrieval_incident_summary_candidates,
        ),
        (
            "artifact_summaries",
            repository.list_retrieval_artifact_summary_candidates,
        ),
    )
    for channel, loader in channel_loaders:
        rows = loader(
            tenant_id=retrieval_plan.scope_tenant_id,
            workspace_id=retrieval_plan.scope_workspace_id,
            exclude_workflow_id=retrieval_plan.exclude_workflow_id,
            normalized_terms=list(retrieval_plan.normalized_terms),
            limit=int(retrieval_plan.max_hits_by_channel.get(channel, 0)),
            connection=connection,
        )
        summaries.extend(
            CompileRequestRetrievedSummary.model_validate(
                {key: value for key, value in row.items() if key != "updated_at"}
            )
            for row in rows
        )
    return summaries


def _build_retrieval_block(
    summary: CompileRequestRetrievedSummary,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=summary.source_ref,
    )
    content_payload = summary.model_dump(mode="json", exclude_none=True)
    reason_code = _RETRIEVAL_REASON_BY_CHANNEL[summary.channel]
    token_estimate = _estimate_tokens(content_payload)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=summary.source_ref,
        source_kind="RETRIEVAL_SUMMARY",
        trust_level=1,
        instruction_authority="DATA_ONLY",
        priority_class="P2",
        selector=selector,
        transform_chain=["RETRIEVE"],
        content_type="JSON",
        content_mode="INLINE_FULL",
        content_payload=content_payload,
        degradation_reason_code=None,
        token_estimate=token_estimate,
        relevance_score=0.6 + (0.1 * min(len(summary.matched_terms), 3)),
        source_hash=_stable_hash(content_payload),
        trust_note=summary.why_it_matched,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=summary.source_ref,
        source_kind=reason_code,
        priority_class=block.priority_class,
        trust_level=block.trust_level,
        selector_used=f"{selector.selector_type}:{selector.selector_value}",
        content_mode=block.content_mode,
        critical=False,
        status="USED",
        tokens_before=token_estimate,
        tokens_after=token_estimate,
        reason=summary.why_it_matched,
        reason_code=reason_code,
    )
    transform_log = CompileManifestTransformLogEntry(
        stage="RETRIEVAL",
        operation_type="RETRIEVE",
        target_ref=summary.source_ref,
        output_block_id=block.block_id,
        reason=summary.why_it_matched,
    )
    return block, source_log, transform_log


def build_compile_request(
    repository: ControlPlaneRepository,
    ticket: dict[str, Any],
    connection: sqlite3.Connection | None = None,
) -> CompileRequest:
    created_spec = apply_legacy_graph_contract_compat(
        _require_ticket_create_spec(repository, ticket["ticket_id"], connection=connection)
    )
    graph_identity = resolve_ticket_graph_identity(
        ticket_id=str(ticket["ticket_id"]),
        created_spec=created_spec,
        runtime_node_id=str(ticket["node_id"]),
    )
    governance_profile = require_governance_profile(
        repository,
        workflow_id=str(ticket["workflow_id"]),
        connection=connection,
    )
    governance_mode_slice = governance_profile_to_mode_slice(governance_profile)
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
    node_projection = repository.get_current_node_projection(
        str(ticket["workflow_id"]),
        str(ticket["node_id"]),
        connection=connection,
    )
    runtime_node_projection = None
    if graph_identity.graph_lane_kind == GRAPH_LANE_EXECUTION:
        node_view = require_materialized_runtime_node(
            repository,
            str(ticket["workflow_id"]),
            str(ticket["node_id"]),
            operation="runtime compilation",
            connection=connection,
        )
        runtime_node_projection = repository.get_runtime_node_projection(
            str(ticket["workflow_id"]),
            str(node_view.graph_node_id or graph_identity.graph_node_id or ""),
            connection=connection,
        )
        if runtime_node_projection is None:
            raise RuntimeNodeLifecycleError(
                workflow_id=str(ticket["workflow_id"]),
                node_id=str(ticket["node_id"]),
                reason_code=REASON_CODE_RUNTIME_NODE_TRUTH_CONFLICT,
                operation="runtime compilation",
                detail="runtime_node_projection is missing after lifecycle gate accepted the node as materialized.",
            )
    else:
        runtime_node_projection = repository.get_runtime_node_projection(
            str(ticket["workflow_id"]),
            str(graph_identity.graph_node_id or ""),
            connection=connection,
        )
        if runtime_node_projection is None:
            raise RuntimeNodeLifecycleError(
                workflow_id=str(ticket["workflow_id"]),
                node_id=str(ticket["node_id"]),
                reason_code=REASON_CODE_RUNTIME_NODE_TRUTH_CONFLICT,
                operation="runtime compilation",
                detail=(
                    "runtime_node_projection is missing for the current graph lane "
                    f"{graph_identity.graph_node_id!r}."
                ),
            )
    _, source_projection_version = repository.get_cursor_and_version(connection=connection)
    if source_projection_version <= 0:
        raise ValueError("Source projection version is missing for runtime compilation.")
    tenant_id = str(ticket.get("tenant_id") or created_spec.get("tenant_id") or DEFAULT_TENANT_ID)
    workspace_id = str(
        ticket.get("workspace_id") or created_spec.get("workspace_id") or DEFAULT_WORKSPACE_ID
    )
    retrieval_plan = _build_retrieval_plan(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        workflow_id=ticket["workflow_id"],
        context_query_plan=context_query_plan,
    )
    fragment_terms = _build_fragment_terms(
        retrieval_plan,
        list(created_spec.get("acceptance_criteria") or []),
    )

    input_process_asset_refs = merge_input_process_asset_refs(
        existing_process_asset_refs=[
            *list(created_spec.get("input_process_asset_refs") or []),
            *_auto_injected_process_asset_refs(
                repository,
                ticket=ticket,
                created_spec=created_spec,
                connection=connection,
            ),
        ],
        artifact_refs=list(created_spec.get("input_artifact_refs") or [])
        + list(created_spec.get("required_read_refs") or []),
    )
    if project_workspace_manifest_exists(str(ticket["workflow_id"])):
        write_worker_preflight_receipt(
            repository,
            workflow_id=ticket["workflow_id"],
            ticket_id=ticket["ticket_id"],
            node_id=ticket["node_id"],
            required_read_refs=list(created_spec.get("required_read_refs") or []),
            input_process_asset_refs=input_process_asset_refs,
            connection=connection,
        )
    explicit_sources = []
    for source_ref in input_process_asset_refs:
        resolved_asset = resolve_process_asset(repository, str(source_ref), connection=connection)
        explicit_source = CompileRequestExplicitSource(
                source_ref=str(resolved_asset.process_asset_ref),
                source_kind="PROCESS_ASSET",
                process_asset_kind=resolved_asset.process_asset_kind,
                producer_ticket_id=resolved_asset.producer_ticket_id,
                source_summary=resolved_asset.summary,
                consumable_by=list(resolved_asset.consumable_by),
                source_metadata=(
                    dict(resolved_asset.source_metadata)
                    | {
                        "canonical_ref": resolved_asset.canonical_ref,
                        "version_int": resolved_asset.version_int,
                        "supersedes_ref": resolved_asset.supersedes_ref,
                    }
                ),
                is_mandatory=True,
                artifact_access=(
                    CompiledArtifactAccessDescriptor.model_validate(resolved_asset.artifact_access)
                    if resolved_asset.artifact_access is not None
                    else None
                ),
                inline_content_type=resolved_asset.content_type,
                inline_content_text=resolved_asset.text_content,
                inline_content_json=resolved_asset.json_content,
                inline_fallback_reason=resolved_asset.fallback_reason,
                inline_fallback_reason_code=resolved_asset.fallback_reason_code,
                inline_content_truncated=False,
                inline_preview_strategy=None,
            )
        explicit_sources.append(
            _build_fragment_candidate(
                explicit_source,
                fragment_terms=fragment_terms,
            )
        )

    normalized_profiles = normalize_persona_profiles(
        str(employee.get("role_type") or "unknown"),
        skill_profile=employee.get("skill_profile_json"),
        personality_profile=employee.get("personality_profile_json"),
        aesthetic_profile=employee.get("aesthetic_profile_json"),
    )
    org_context = _build_org_context(
        repository,
        ticket=ticket,
        created_spec=created_spec,
        employee_role_type=str(employee.get("role_type") or "unknown"),
        connection=connection,
    )

    checkout_truth = resolve_ticket_checkout_truth(
        str(ticket["workflow_id"]),
        str(ticket["ticket_id"]),
        created_spec,
    )
    return CompileRequest(
        meta=CompileRequestMeta(
            compile_request_id=new_prefixed_id("creq"),
            ticket_id=ticket["ticket_id"],
            workflow_id=ticket["workflow_id"],
            node_id=ticket["node_id"],
            attempt_no=attempt_no,
            governance_profile_ref=governance_profile.profile_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            ticket_projection_version=int(ticket["version"]),
            node_projection_version=(
                int(node_projection["version"]) if node_projection is not None else None
            ),
            runtime_node_projection_version=(
                int(runtime_node_projection["version"])
                if runtime_node_projection is not None
                else None
            ),
            source_projection_version=source_projection_version,
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
            skill_profile=normalized_profiles["skill_profile"],
            personality_profile=normalized_profiles["personality_profile"],
            aesthetic_profile=normalized_profiles["aesthetic_profile"],
        ),
        budget_policy=CompileRequestBudgetPolicy(
            max_input_tokens=max_input_tokens,
            overflow_policy="FAIL_CLOSED",
        ),
        governance_mode_slice=governance_mode_slice,
        org_context=org_context,
        retrieval_plan=retrieval_plan,
        explicit_sources=explicit_sources,
        retrieved_summaries=_build_retrieved_summaries(
            repository,
            retrieval_plan,
            connection=connection,
        ),
        execution=CompileRequestExecution(
            acceptance_criteria=list(created_spec.get("acceptance_criteria") or []),
            allowed_tools=list(created_spec.get("allowed_tools") or []),
            allowed_write_set=list(created_spec.get("allowed_write_set") or []),
            forced_skill_ids=list(created_spec.get("forced_skill_ids") or []),
            input_artifact_refs=list(created_spec.get("input_artifact_refs") or []),
            input_process_asset_refs=input_process_asset_refs,
            required_read_refs=list(created_spec.get("required_read_refs") or []),
            doc_update_requirements=list(created_spec.get("doc_update_requirements") or []),
            project_workspace_ref=created_spec.get("project_workspace_ref"),
            project_checkout_ref=created_spec.get("project_checkout_ref") or checkout_truth["project_checkout_ref"],
            project_checkout_path=checkout_truth["project_checkout_path"],
            git_branch_ref=created_spec.get("git_branch_ref") or checkout_truth["git_branch_ref"],
            deliverable_kind=created_spec.get("deliverable_kind"),
            git_policy=created_spec.get("git_policy"),
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

    context_blocks: list[CompiledContextBlock] = []
    source_log: list[CompileManifestSourceLogEntry] = []
    transform_log: list[CompileManifestTransformLogEntry] = []
    warnings: list[str] = []
    hydrated_block_count = 0
    fragment_block_count = 0
    partially_hydrated_block_count = 0
    reference_block_count = 0
    retrieved_block_count = 0
    dropped_retrieval_count = 0
    dropped_explicit_source_count = 0
    remaining_budget = compile_request.budget_policy.max_input_tokens
    planned_retrieval_budget = (
        min(
            compile_request.budget_policy.max_input_tokens // 4,
            800,
        )
        if compile_request.retrieved_summaries
        else 0
    )
    minimum_descriptor_tokens = [
        _estimate_reference_only_tokens(source) if source.is_mandatory else 0
        for source in compile_request.explicit_sources
    ]

    for index, source in enumerate(compile_request.explicit_sources):
        reserved_for_remaining_sources = sum(minimum_descriptor_tokens[index + 1 :])
        available_budget_for_source = max(remaining_budget - reserved_for_remaining_sources, 0)
        decision = _select_explicit_source_for_budget(
            source,
            remaining_budget=available_budget_for_source,
        )
        source_log.append(decision.source_log)
        transform_log.append(decision.transform_log)
        if decision.warning:
            warnings.append(decision.warning)
        if decision.block is None:
            dropped_explicit_source_count += 1
            continue

        context_blocks.append(decision.block)
        remaining_budget -= decision.block.token_estimate
        if decision.block.content_mode == "INLINE_FULL":
            hydrated_block_count += 1
        elif decision.block.content_mode == "INLINE_FRAGMENT":
            fragment_block_count += 1
        elif decision.block.content_mode == "INLINE_PARTIAL":
            partially_hydrated_block_count += 1
            reference_block_count += 1
        else:
            reference_block_count += 1

    retrieval_budget = min(
        planned_retrieval_budget,
        remaining_budget,
    )
    retrieval_remaining_budget = max(0, retrieval_budget)
    for summary in compile_request.retrieved_summaries:
        retrieval_block, retrieval_source_log, retrieval_transform_log = _build_retrieval_block(summary)
        if retrieval_block.token_estimate <= retrieval_remaining_budget:
            context_blocks.append(retrieval_block)
            source_log.append(retrieval_source_log)
            transform_log.append(retrieval_transform_log)
            retrieved_block_count += 1
            retrieval_remaining_budget -= retrieval_block.token_estimate
            remaining_budget -= retrieval_block.token_estimate
            continue

        source_log.append(
            CompileManifestSourceLogEntry(
                source_ref=summary.source_ref,
                source_kind=_RETRIEVAL_REASON_BY_CHANNEL[summary.channel],
                priority_class="P2",
                trust_level=1,
                selector_used=f"SOURCE_REF:{summary.source_ref}",
                content_mode=None,
                critical=False,
                status="DROPPED",
                tokens_before=retrieval_block.token_estimate,
                tokens_after=0,
                reason=(
                    f"Retrieval summary for {summary.source_ref} was dropped because the retrieval "
                    "budget was exhausted after higher-priority local history matches."
                ),
                reason_code=FALLBACK_REASON_RETRIEVAL_DROPPED_FOR_BUDGET,
            )
        )
        transform_log.append(
            CompileManifestTransformLogEntry(
                stage="BUDGET_ENFORCEMENT",
                operation_type="DROP",
                target_ref=summary.source_ref,
                output_block_id=None,
                reason="Dropped retrieval summary because the retrieval budget was exhausted.",
            )
        )
        warnings.append(f"Dropped retrieval summary for {summary.source_ref} because retrieval budget was exhausted.")
        dropped_retrieval_count += 1

    is_degraded = (
        reference_block_count > 0
        or fragment_block_count > 0
        or partially_hydrated_block_count > 0
        or dropped_retrieval_count > 0
        or dropped_explicit_source_count > 0
    )
    task_frame = _build_task_frame(compile_request)
    required_doc_surfaces = list(compile_request.execution.doc_update_requirements)
    context_layer_summary = _build_context_layer_summary(
        compile_request,
        context_block_count=len(context_blocks),
    )
    skill_binding = resolve_skill_binding(
        compile_request=compile_request,
        task_frame=task_frame,
    )

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
            render_target=MINIMAL_CONTEXT_COMPILER_RENDER_TARGET,
            is_degraded=is_degraded,
        ),
        system_controls=CompiledSystemControls(
            role_profile=compiled_role.model_dump(mode="json"),
            organization_context=compile_request.org_context,
            governance_mode_slice=compile_request.governance_mode_slice,
            required_doc_surfaces=required_doc_surfaces,
            skill_binding=skill_binding.model_dump(mode="json"),
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
            task_type=task_frame.task_category.upper(),
            atomic_task=task_frame.goal,
            acceptance_criteria=task_frame.completion_definition,
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
    truncated_tokens = sum(
        max(int(entry.tokens_before or 0) - int(entry.tokens_after or 0), 0)
        for entry in source_log
        if entry.status in {"SUMMARIZED", "TRUNCATED", "DROPPED"}
    )

    compile_manifest = CompileManifest(
        compile_meta=CompileManifestMeta(
            compile_id=compile_id,
            bundle_id=bundle_id,
            compile_request_id=compile_request.meta.compile_request_id,
            ticket_id=compile_request.meta.ticket_id,
            workflow_id=compile_request.meta.workflow_id,
            node_id=compile_request.meta.node_id,
            attempt_no=compile_request.meta.attempt_no,
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
            reserved_p1=max(compile_request.budget_policy.max_input_tokens - planned_retrieval_budget, 0),
            reserved_p2=planned_retrieval_budget,
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
            truncated_tokens=truncated_tokens,
        ),
        source_log=source_log,
        transform_log=transform_log,
        degradation=CompileManifestDegradation(
            is_degraded=is_degraded,
            fail_mode=compile_request.budget_policy.overflow_policy,
            missing_critical_sources=[],
            warnings=warnings + ["Token counts are deterministic estimates, not provider tokenizer results."],
        ),
        cache_report=CompileManifestCacheReport(
            cache_hit=False,
            reused_from_compile_id=None,
            invalidated_by=[],
        ),
        final_bundle_stats=CompileManifestFinalBundleStats(
            context_block_count=len(context_blocks),
            trusted_block_count=len(context_blocks),
            reference_block_count=reference_block_count,
            hydrated_block_count=hydrated_block_count,
            fragment_block_count=fragment_block_count,
            partially_hydrated_block_count=partially_hydrated_block_count,
            negative_pattern_count=0,
            retrieved_block_count=retrieved_block_count,
            dropped_retrieval_count=dropped_retrieval_count,
            dropped_explicit_source_count=dropped_explicit_source_count,
        ),
    )

    rendered_execution_payload = _build_rendered_execution_payload(
        compiled_context_bundle=compiled_context_bundle,
        compile_manifest=compile_manifest,
    )

    compiled_execution_package = CompiledExecutionPackage(
        meta=_build_execution_package_meta(compile_request),
        compiled_role=compiled_role,
        compiled_constraints=compiled_constraints,
        governance_mode_slice=compile_request.governance_mode_slice,
        task_frame=task_frame,
        required_doc_surfaces=required_doc_surfaces,
        context_layer_summary=context_layer_summary,
        org_context=compile_request.org_context,
        atomic_context_bundle=_build_atomic_context_bundle(
            context_blocks,
            compile_request.budget_policy.max_input_tokens,
        ),
        rendered_execution_payload=rendered_execution_payload,
        execution=CompiledExecution(
            acceptance_criteria=compile_request.execution.acceptance_criteria,
            allowed_tools=compile_request.execution.allowed_tools,
            allowed_write_set=compile_request.execution.allowed_write_set,
            forced_skill_ids=compile_request.execution.forced_skill_ids,
            input_artifact_refs=compile_request.execution.input_artifact_refs,
            input_process_asset_refs=compile_request.execution.input_process_asset_refs,
            required_read_refs=compile_request.execution.required_read_refs,
            doc_update_requirements=compile_request.execution.doc_update_requirements,
            project_workspace_ref=compile_request.execution.project_workspace_ref,
            project_checkout_ref=compile_request.execution.project_checkout_ref,
            project_checkout_path=compile_request.execution.project_checkout_path,
            git_branch_ref=compile_request.execution.git_branch_ref,
            deliverable_kind=compile_request.execution.deliverable_kind,
            git_policy=compile_request.execution.git_policy,
            output_schema_ref=compile_request.control_refs.output_schema_ref,
            output_schema_version=compile_request.control_refs.output_schema_version,
        ),
        governance=CompiledGovernance(
            retry_budget=compile_request.governance.retry_budget,
            timeout_sla_sec=compile_request.governance.timeout_sla_sec,
            escalation_policy=compile_request.governance.escalation_policy,
        ),
        skill_binding=skill_binding,
    )

    return CompiledAuditArtifacts(
        compiled_context_bundle=compiled_context_bundle,
        compile_manifest=compile_manifest,
        compiled_execution_package=compiled_execution_package,
    )



def _validate_matching_compiled_audit_artifacts(
    bundle_row: dict[str, Any],
    manifest_row: dict[str, Any],
    execution_package_row: dict[str, Any] | None = None,
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
    if execution_package_row is None:
        return
    execution_payload = execution_package_row["payload"]
    if str(execution_package_row["compile_request_id"]) != compile_request_id:
        raise RuntimeError("Latest compiled execution package uses a different compile request than the latest bundle.")
    if str(execution_package_row["ticket_id"]) != ticket_id:
        raise RuntimeError("Latest compiled execution package belongs to a different ticket than the latest bundle.")
    if execution_payload["meta"]["compile_request_id"] != compile_request_id:
        raise RuntimeError("Compiled execution package payload does not match its persisted compile request id.")
    rendered_meta = execution_payload.get("rendered_execution_payload", {}).get("meta") or {}
    if rendered_meta.get("bundle_id") != bundle_id:
        raise RuntimeError("Rendered execution payload does not match the persisted bundle id.")
    if rendered_meta.get("compile_id") != manifest_payload["compile_meta"]["compile_id"]:
        raise RuntimeError("Rendered execution payload does not match the persisted compile manifest id.")


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
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(
        ticket_id,
        connection=connection,
    )

    if (
        refs.compiled_context_bundle_ref is not None
        and refs.compile_manifest_ref is not None
        and latest_bundle is not None
        and latest_manifest is not None
    ):
        _validate_matching_compiled_audit_artifacts(
            latest_bundle,
            latest_manifest,
            latest_execution_package,
        )

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
    if refs.rendered_execution_payload_ref is not None and latest_execution_package is not None:
        persisted.append(
            developer_inspector_store.write_json(
                refs.rendered_execution_payload_ref,
                latest_execution_package["payload"]["rendered_execution_payload"],
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
