from __future__ import annotations

import hashlib
import json
import re
import sqlite3
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
    CompileRequestRetrievedSummary,
    CompileRequestRetrievalPlan,
    CompileRequestWorkerBinding,
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


def _build_descriptor_payload(source: CompileRequestExplicitSource) -> dict[str, Any]:
    content_payload = {
        "source_ref": source.source_ref,
        "source_kind": source.source_kind,
        "is_mandatory": source.is_mandatory,
    }
    if source.artifact_access is not None:
        artifact_access = source.artifact_access.model_dump(mode="json")
        content_payload["artifact_access"] = artifact_access
        content_payload.update(artifact_access)
    return content_payload


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
    *,
    reason: str | None = None,
    reason_code: str | None = None,
    status: str = "USED",
    tokens_before: int | None = None,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=source.source_ref,
    )
    content_payload = _build_descriptor_payload(source)
    token_estimate = _estimate_tokens(content_payload)
    source_tokens_before = max(tokens_before or token_estimate, token_estimate)
    fallback_reason = reason or source.inline_fallback_reason or REFERENCE_ONLY_REASON
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        target_ref=source.source_ref,
        output_block_id=block.block_id,
        reason=fallback_reason,
    )
    return block, source_log, transform_log


def _build_inline_block(
    source: CompileRequestExplicitSource,
) -> tuple[CompiledContextBlock, CompileManifestSourceLogEntry, CompileManifestTransformLogEntry]:
    selector = CompiledContextSelector(
        selector_type="SOURCE_REF",
        selector_value=source.source_ref,
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

    token_estimate = _estimate_tokens(content_payload)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        target_ref=source.source_ref,
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
        selector_value=str(source.fragment_selector_value or source.source_ref),
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

    reason = (
        f"Inline hydration for {source.source_ref} exceeded the full-body budget, so the compiler kept "
        "deterministic relevant fragments instead of only the head preview."
    )
    token_estimate = _estimate_tokens(content_payload)
    source_tokens_before = max(tokens_before or token_estimate, token_estimate)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        target_ref=source.source_ref,
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
        selector_value=source.source_ref,
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

    reason = (
        f"Inline hydration for {source.source_ref} exceeded the token budget, so the compiler kept "
        "a deterministic preview instead of the full body."
    )
    token_estimate = _estimate_tokens(content_payload)
    source_tokens_before = max(tokens_before or token_estimate, token_estimate)
    block = CompiledContextBlock(
        block_id=new_prefixed_id("ctxblk"),
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        target_ref=source.source_ref,
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
        selector_value=source.source_ref,
    )
    source_log = CompileManifestSourceLogEntry(
        source_ref=source.source_ref,
        source_kind="ARTIFACT_REFERENCE",
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
        target_ref=source.source_ref,
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
        f"{source.source_ref} cannot fit within the remaining token budget "
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
            f"Inline hydration for {source.source_ref} exceeded the token budget, so the compiler kept "
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
                source_kind="ARTIFACT" if block.source_kind == "ARTIFACT_REFERENCE" else "RETRIEVAL",
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

    explicit_sources = []
    for source_ref in list(created_spec.get("input_artifact_refs") or []):
        artifact = repository.get_artifact_by_ref(str(source_ref), connection=connection)
        prepared_inline_source = _prepare_inline_source(repository, artifact)
        explicit_source = CompileRequestExplicitSource(
                source_ref=str(source_ref),
                source_kind="ARTIFACT",
                is_mandatory=True,
                artifact_access=CompiledArtifactAccessDescriptor.model_validate(
                    build_artifact_access_descriptor(
                        artifact,
                        artifact_ref=str(source_ref),
                    )
                ),
                inline_content_type=prepared_inline_source.content_type,
                inline_content_text=prepared_inline_source.content_text,
                inline_content_json=prepared_inline_source.content_json,
                inline_fallback_reason=prepared_inline_source.fallback_reason,
                inline_fallback_reason_code=prepared_inline_source.fallback_reason_code,
                inline_content_truncated=prepared_inline_source.content_truncated,
                inline_preview_strategy=prepared_inline_source.preview_strategy,
            )
        explicit_sources.append(
            _build_fragment_candidate(
                explicit_source,
                fragment_terms=fragment_terms,
            )
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
        retrieval_plan=retrieval_plan,
        explicit_sources=explicit_sources,
        retrieved_summaries=_build_retrieved_summaries(repository, retrieval_plan),
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
        atomic_context_bundle=_build_atomic_context_bundle(
            context_blocks,
            compile_request.budget_policy.max_input_tokens,
        ),
        rendered_execution_payload=rendered_execution_payload,
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
