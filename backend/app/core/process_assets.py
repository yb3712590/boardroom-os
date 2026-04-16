from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from typing import Any, Iterable
from urllib.parse import quote, unquote

from app.contracts.process_assets import ProcessAssetReference, ResolvedProcessAsset
from app.core.artifacts import (
    build_artifact_access_descriptor,
    is_artifact_readable,
    normalize_artifact_kind,
)
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.core.project_workspaces import load_git_closeout_receipt
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.versioning import build_process_asset_canonical_ref, split_versioned_ref
from app.db.repository import ControlPlaneRepository

_PROCESS_ASSET_PREFIX = "pa://"
_ARTIFACT_FALLBACK_NOT_INDEXED = "ARTIFACT_NOT_INDEXED"
_ARTIFACT_FALLBACK_NOT_READABLE = "ARTIFACT_NOT_READABLE"
_ARTIFACT_FALLBACK_UNSUPPORTED_KIND = "UNSUPPORTED_ARTIFACT_KIND"
_ARTIFACT_FALLBACK_READ_FAILED = "ARTIFACT_READ_FAILED"
_ARTIFACT_FALLBACK_JSON_DECODE_FAILED = "ARTIFACT_JSON_DECODE_FAILED"
_ARTIFACT_FALLBACK_TEXT_DECODE_FAILED = "ARTIFACT_TEXT_DECODE_FAILED"
_ARTIFACT_FALLBACK_MEDIA_REFERENCE_ONLY = "MEDIA_REFERENCE_ONLY"
_ARTIFACT_FALLBACK_BINARY_REFERENCE_ONLY = "BINARY_REFERENCE_ONLY"


def dedupe_process_asset_refs(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _process_asset_ref(kind: str, target: str, *, version_int: int | None = None) -> str:
    base_ref = f"{_PROCESS_ASSET_PREFIX}{kind}/{quote(str(target), safe='')}"
    if version_int is None:
        return base_ref
    return build_process_asset_canonical_ref(base_ref, version_int)


def build_artifact_process_asset_ref(artifact_ref: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("artifact", artifact_ref, version_int=version_int)


def build_compiled_context_bundle_process_asset_ref(
    ticket_id: str,
    *,
    version_int: int | None = None,
) -> str:
    return _process_asset_ref("compiled-context-bundle", ticket_id, version_int=version_int)


def build_compile_manifest_process_asset_ref(ticket_id: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("compile-manifest", ticket_id, version_int=version_int)


def build_compiled_execution_package_process_asset_ref(
    ticket_id: str,
    *,
    version_int: int | None = None,
) -> str:
    return _process_asset_ref("compiled-execution-package", ticket_id, version_int=version_int)


def build_decision_summary_process_asset_ref(session_id: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("decision-summary", session_id, version_int=version_int)


def build_failure_fingerprint_process_asset_ref(
    incident_id: str,
    *,
    version_int: int | None = None,
) -> str:
    return _process_asset_ref("failure-fingerprint", incident_id, version_int=version_int)


def build_graph_patch_proposal_process_asset_ref(
    session_id: str,
    *,
    version_int: int | None = None,
) -> str:
    return _process_asset_ref("graph-patch-proposal", session_id, version_int=version_int)


def build_graph_patch_process_asset_ref(
    session_id: str,
    *,
    version_int: int | None = None,
) -> str:
    return _process_asset_ref("graph-patch", session_id, version_int=version_int)


def build_project_map_slice_process_asset_ref(
    workflow_id: str,
    *,
    version_int: int | None = None,
) -> str:
    return _process_asset_ref("project-map-slice", workflow_id, version_int=version_int)


def build_meeting_decision_process_asset_ref(ticket_id: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("meeting-decision-record", ticket_id, version_int=version_int)


def build_source_code_delivery_process_asset_ref(ticket_id: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("source-code-delivery", ticket_id, version_int=version_int)


def build_closeout_summary_process_asset_ref(ticket_id: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("closeout-summary", ticket_id, version_int=version_int)


def build_governance_document_process_asset_ref(ticket_id: str, *, version_int: int | None = None) -> str:
    return _process_asset_ref("governance-document", ticket_id, version_int=version_int)


def artifact_refs_to_process_asset_refs(artifact_refs: Iterable[str]) -> list[str]:
    return dedupe_process_asset_refs(build_artifact_process_asset_ref(value) for value in artifact_refs)


def merge_input_process_asset_refs(
    *,
    existing_process_asset_refs: Iterable[str] = (),
    artifact_refs: Iterable[str] = (),
    produced_process_asset_refs: Iterable[str] = (),
) -> list[str]:
    return dedupe_process_asset_refs(
        [
            *list(existing_process_asset_refs),
            *artifact_refs_to_process_asset_refs(artifact_refs),
            *list(produced_process_asset_refs),
        ]
    )


def parse_process_asset_ref(process_asset_ref: str) -> tuple[str, str]:
    normalized, _ = split_versioned_ref(str(process_asset_ref).strip())
    if not normalized.startswith(_PROCESS_ASSET_PREFIX):
        raise ValueError(f"Unsupported process asset ref: {process_asset_ref}")
    path = normalized.removeprefix(_PROCESS_ASSET_PREFIX)
    kind, _, raw_target = path.partition("/")
    if not kind or not raw_target:
        raise ValueError(f"Unsupported process asset ref: {process_asset_ref}")
    return kind, unquote(raw_target)


def parse_process_asset_version(process_asset_ref: str) -> tuple[str, str, int | None]:
    normalized = str(process_asset_ref).strip()
    base_ref, version_int = split_versioned_ref(normalized)
    kind, target = parse_process_asset_ref(base_ref)
    return kind, target, version_int


def _matches_process_asset_ref(asset_entry: dict[str, Any], requested_ref: str) -> bool:
    entry_ref = str(asset_entry.get("canonical_ref") or asset_entry.get("process_asset_ref") or "").strip()
    requested_base_ref, requested_version_int = split_versioned_ref(requested_ref)
    entry_base_ref, entry_version_int = split_versioned_ref(entry_ref)
    if requested_version_int is None:
        return requested_base_ref == entry_base_ref
    return requested_base_ref == entry_base_ref and requested_version_int == entry_version_int


def get_ticket_output_process_asset_refs(
    repository: ControlPlaneRepository,
    connection: sqlite3.Connection,
    ticket_id: str,
) -> list[str]:
    terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
    if terminal_event is None:
        return []
    payload = terminal_event.get("payload") or {}
    if isinstance(payload, dict):
        produced_assets = payload.get("produced_process_assets") or []
        refs = [
            str(item.get("process_asset_ref") or "").strip()
            for item in produced_assets
            if isinstance(item, dict) and str(item.get("process_asset_ref") or "").strip()
        ]
        if refs:
            return dedupe_process_asset_refs(refs)
        artifact_refs = [
            str(value).strip()
            for value in (payload.get("artifact_refs") or [])
            if str(value).strip()
        ]
        if artifact_refs:
            return artifact_refs_to_process_asset_refs(artifact_refs)
    return []


def build_result_process_assets(
    *,
    ticket_id: str,
    created_spec: dict[str, Any],
    result_payload: dict[str, Any] | None,
    artifact_refs: list[str],
    written_artifacts: list[dict[str, Any]] | None = None,
    verification_evidence_refs: list[str] | None = None,
    git_commit_record: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    produced_assets: list[ProcessAssetReference] = []
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    summary = ""
    if isinstance(result_payload, dict):
        summary = str(result_payload.get("summary") or "").strip()

    for artifact_ref in dedupe_process_asset_refs(artifact_refs):
        produced_assets.append(
            ProcessAssetReference(
                process_asset_ref=build_artifact_process_asset_ref(artifact_ref, version_int=1),
                canonical_ref=build_artifact_process_asset_ref(artifact_ref, version_int=1),
                version_int=1,
                process_asset_kind="ARTIFACT",
                producer_ticket_id=ticket_id,
                summary=summary or artifact_ref,
                consumable_by=["context_compiler", "review", "closeout"],
                source_metadata={"artifact_ref": artifact_ref},
            )
        )

    if output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF and isinstance(result_payload, dict):
        produced_assets.append(
            ProcessAssetReference(
                process_asset_ref=build_source_code_delivery_process_asset_ref(ticket_id, version_int=1),
                canonical_ref=build_source_code_delivery_process_asset_ref(ticket_id, version_int=1),
                version_int=1,
                process_asset_kind="SOURCE_CODE_DELIVERY",
                producer_ticket_id=ticket_id,
                summary=summary or "Source code delivery",
                consumable_by=["context_compiler", "followup_ticket", "review", "closeout"],
                source_metadata={
                    "source_file_refs": list(result_payload.get("source_file_refs") or []),
                    "written_artifact_refs": [
                        str(item.get("artifact_ref") or "").strip()
                        for item in list(written_artifacts or [])
                        if isinstance(item, dict) and str(item.get("artifact_ref") or "").strip()
                    ],
                    "verification_evidence_refs": list(verification_evidence_refs or []),
                    "documentation_updates": list(result_payload.get("documentation_updates") or []),
                    "git_commit_record": dict(git_commit_record or {}),
                },
            )
        )

    if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF and isinstance(result_payload, dict):
        decision_record = result_payload.get("decision_record")
        if isinstance(decision_record, dict):
            produced_assets.append(
                ProcessAssetReference(
                    process_asset_ref=build_meeting_decision_process_asset_ref(ticket_id, version_int=1),
                    canonical_ref=build_meeting_decision_process_asset_ref(ticket_id, version_int=1),
                    version_int=1,
                    process_asset_kind="MEETING_DECISION_RECORD",
                    producer_ticket_id=ticket_id,
                    summary=(
                        str(decision_record.get("decision") or "").strip()
                        or str(result_payload.get("consensus_summary") or "").strip()
                        or summary
                        or "Meeting ADR decision record"
                    ),
                    consumable_by=["context_compiler", "followup_ticket", "review"],
                    source_metadata={"source_artifact_ref": f"art://runtime/{ticket_id}/consensus-document.json"},
                )
            )

    if output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF and isinstance(result_payload, dict):
        produced_assets.append(
            ProcessAssetReference(
                process_asset_ref=build_closeout_summary_process_asset_ref(ticket_id, version_int=1),
                canonical_ref=build_closeout_summary_process_asset_ref(ticket_id, version_int=1),
                version_int=1,
                process_asset_kind="CLOSEOUT_SUMMARY",
                producer_ticket_id=ticket_id,
                summary=summary or "Delivery closeout summary",
                consumable_by=["context_compiler", "review", "closeout"],
                source_metadata={
                    "source_artifact_ref": f"art://runtime/{ticket_id}/delivery-closeout-package.json"
                },
            )
        )

    if output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS and isinstance(result_payload, dict):
        summary = (
            str(result_payload.get("summary") or "").strip()
            or str(result_payload.get("title") or "").strip()
            or f"Governance document for {ticket_id}"
        )
        source_artifact_ref = (
            dedupe_process_asset_refs(artifact_refs)[0]
            if dedupe_process_asset_refs(artifact_refs)
            else f"art://runtime/{ticket_id}/{output_schema_ref.replace('_', '-')}.json"
        )
        produced_assets.append(
            ProcessAssetReference(
                process_asset_ref=build_governance_document_process_asset_ref(ticket_id, version_int=1),
                canonical_ref=build_governance_document_process_asset_ref(ticket_id, version_int=1),
                version_int=1,
                process_asset_kind="GOVERNANCE_DOCUMENT",
                producer_ticket_id=ticket_id,
                summary=summary,
                consumable_by=["context_compiler", "followup_ticket", "review"],
                source_metadata={
                    "document_kind_ref": str(result_payload.get("document_kind_ref") or output_schema_ref),
                    "source_artifact_ref": source_artifact_ref,
                },
            )
        )

    return [asset.model_dump(mode="json", exclude_none=True) for asset in produced_assets]


def resolve_process_asset(
    repository: ControlPlaneRepository,
    process_asset_ref: str,
    *,
    connection: sqlite3.Connection | None = None,
) -> ResolvedProcessAsset:
    kind, target, version_int = parse_process_asset_version(process_asset_ref)
    if kind == "artifact":
        return _resolve_artifact_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            artifact_ref=target,
            connection=connection,
        )
    if kind == "compiled-context-bundle":
        return _resolve_compiled_payload_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            version_int=version_int,
            payload_kind="COMPILED_CONTEXT_BUNDLE",
            schema_ref="compiled_context_bundle@1",
            loader=repository.get_latest_compiled_context_bundle_by_ticket,
            version_loader=repository.get_compiled_context_bundle_version,
            builder=build_compiled_context_bundle_process_asset_ref,
            connection=connection,
        )
    if kind == "compile-manifest":
        return _resolve_compiled_payload_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            version_int=version_int,
            payload_kind="COMPILE_MANIFEST",
            schema_ref="compile_manifest@1",
            loader=repository.get_latest_compile_manifest_by_ticket,
            version_loader=repository.get_compile_manifest_version,
            builder=build_compile_manifest_process_asset_ref,
            connection=connection,
        )
    if kind == "compiled-execution-package":
        return _resolve_compiled_payload_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            version_int=version_int,
            payload_kind="COMPILED_EXECUTION_PACKAGE",
            schema_ref="compiled_execution_package@1",
            loader=repository.get_latest_compiled_execution_package_by_ticket,
            version_loader=repository.get_compiled_execution_package_version,
            builder=build_compiled_execution_package_process_asset_ref,
            connection=connection,
        )
    if kind == "decision-summary":
        return _resolve_decision_summary_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            session_id=target,
            connection=connection,
        )
    if kind == "failure-fingerprint":
        return _resolve_failure_fingerprint_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            incident_id=target,
            connection=connection,
        )
    if kind == "graph-patch-proposal":
        return _resolve_graph_patch_proposal_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            session_id=target,
            connection=connection,
        )
    if kind == "graph-patch":
        return _resolve_graph_patch_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            session_id=target,
            connection=connection,
        )
    if kind == "project-map-slice":
        return _resolve_project_map_slice_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            workflow_id=target,
            connection=connection,
        )
    if kind == "meeting-decision-record":
        return _resolve_meeting_decision_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            connection=connection,
        )
    if kind == "source-code-delivery":
        return _resolve_source_code_delivery_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            connection=connection,
        )
    if kind == "closeout-summary":
        return _resolve_closeout_summary_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            connection=connection,
        )
    if kind == "governance-document":
        return _resolve_governance_document_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            ticket_id=target,
            connection=connection,
        )
    raise ValueError(f"Unsupported process asset ref: {process_asset_ref}")


def _resolve_compiled_payload_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    ticket_id: str,
    version_int: int | None,
    payload_kind: str,
    schema_ref: str,
    loader,
    version_loader,
    builder,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    row = (
        loader(ticket_id, connection=connection)
        if version_int is None
        else version_loader(ticket_id, version_int, connection=connection)
    )
    if row is None:
        raise ValueError(f"Process asset {process_asset_ref} is missing.")
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"Process asset {process_asset_ref} has no structured payload.")
    resolved_version_int = int(row.get("version_int") or 0)
    canonical_ref = builder(ticket_id, version_int=resolved_version_int)
    supersedes_ref = (
        builder(ticket_id, version_int=resolved_version_int - 1)
        if resolved_version_int > 1
        else None
    )
    return ResolvedProcessAsset(
        process_asset_ref=canonical_ref,
        canonical_ref=canonical_ref,
        version_int=resolved_version_int,
        supersedes_ref=supersedes_ref,
        process_asset_kind=payload_kind,
        producer_ticket_id=ticket_id,
        summary=f"{payload_kind.lower()} for {ticket_id}",
        consumable_by=["context_compiler", "audit"],
        source_metadata={key: row.get(key) for key in ("bundle_id", "compile_id", "compile_request_id") if row.get(key)},
        content_type="JSON",
        json_content=dict(payload),
        schema_ref=schema_ref,
    )


def _resolve_artifact_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    artifact_ref: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    artifact = repository.get_artifact_by_ref(artifact_ref, connection=connection)
    if artifact is None:
        return ResolvedProcessAsset(
            process_asset_ref=process_asset_ref,
            process_asset_kind="ARTIFACT",
            producer_ticket_id=None,
            summary=artifact_ref,
            consumable_by=["context_compiler", "review", "closeout"],
            source_metadata={"artifact_ref": artifact_ref},
            artifact_ref=artifact_ref,
            fallback_reason="Artifact is not indexed, so the compiler kept only the descriptor.",
            fallback_reason_code=_ARTIFACT_FALLBACK_NOT_INDEXED,
        )

    artifact_access = build_artifact_access_descriptor(artifact, artifact_ref=artifact_ref)
    resolved = ResolvedProcessAsset(
        process_asset_ref=process_asset_ref,
        process_asset_kind="ARTIFACT",
        producer_ticket_id=str(artifact.get("ticket_id") or "").strip() or None,
        summary=str(artifact.get("logical_path") or artifact_ref),
        consumable_by=["context_compiler", "review", "closeout"],
        source_metadata={
            "artifact_ref": artifact_ref,
            "kind": artifact.get("kind"),
            "media_type": artifact.get("media_type"),
            "logical_path": artifact.get("logical_path"),
        },
        artifact_ref=artifact_ref,
        artifact_access=dict(artifact_access),
    )
    if not is_artifact_readable(artifact):
        resolved.fallback_reason = (
            "Artifact is not readable for inline hydration "
            f"(materialization={artifact.get('materialization_status')}, "
            f"lifecycle={artifact.get('lifecycle_status')})."
        )
        resolved.fallback_reason_code = _ARTIFACT_FALLBACK_NOT_READABLE
        return resolved

    artifact_store = repository.artifact_store
    if artifact_store is None:
        resolved.fallback_reason = "Artifact store is unavailable, so the compiler kept only the descriptor."
        resolved.fallback_reason_code = _ARTIFACT_FALLBACK_READ_FAILED
        return resolved

    normalized_kind = normalize_artifact_kind(str(artifact.get("kind") or ""))
    preview_kind = artifact_access.get("preview_kind")
    if normalized_kind not in {"TEXT", "MARKDOWN", "JSON"}:
        resolved.fallback_reason_code = (
            _ARTIFACT_FALLBACK_MEDIA_REFERENCE_ONLY
            if preview_kind == "INLINE_MEDIA"
            else _ARTIFACT_FALLBACK_BINARY_REFERENCE_ONLY
            if preview_kind == "DOWNLOAD_ONLY"
            else _ARTIFACT_FALLBACK_UNSUPPORTED_KIND
        )
        resolved.fallback_reason = (
            f"Artifact kind {normalized_kind} is preserved as a structured reference in the current MVP."
        )
        return resolved

    try:
        body = artifact_store.read_bytes(
            artifact.get("storage_relpath"),
            storage_object_key=artifact.get("storage_object_key"),
        )
    except Exception as exc:
        resolved.fallback_reason = f"Artifact body could not be read for inline hydration: {exc}"
        resolved.fallback_reason_code = _ARTIFACT_FALLBACK_READ_FAILED
        return resolved

    if normalized_kind == "JSON":
        try:
            resolved.content_type = "JSON"
            decoded = json.loads(body.decode("utf-8"))
            resolved.json_content = decoded if isinstance(decoded, dict) else {"value": decoded}
            resolved.schema_ref = "artifact_json@1"
            return resolved
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            resolved.fallback_reason = f"Artifact JSON body could not be decoded for inline hydration: {exc}"
            resolved.fallback_reason_code = _ARTIFACT_FALLBACK_JSON_DECODE_FAILED
            return resolved

    try:
        resolved.content_type = "TEXT"
        resolved.text_content = body.decode("utf-8")
        resolved.schema_ref = "artifact_text@1"
        return resolved
    except UnicodeDecodeError as exc:
        resolved.fallback_reason = f"Artifact text body could not be decoded for inline hydration: {exc}"
        resolved.fallback_reason_code = _ARTIFACT_FALLBACK_TEXT_DECODE_FAILED
        return resolved


def _resolve_json_payload_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    process_asset_kind: str,
    ticket_id: str,
    artifact_ref: str,
    schema_ref: str,
    summary: str,
    transform_payload,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    artifact = repository.get_artifact_by_ref(artifact_ref, connection=connection)
    if artifact is None:
        raise ValueError(f"Process asset {process_asset_ref} is missing its source artifact.")
    if not is_artifact_readable(artifact):
        raise ValueError(f"Process asset {process_asset_ref} source artifact is not readable.")
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise ValueError(f"Process asset {process_asset_ref} source artifact store is unavailable.")
    try:
        payload = json.loads(
            artifact_store.read_bytes(
                artifact.get("storage_relpath"),
                storage_object_key=artifact.get("storage_object_key"),
            ).decode("utf-8")
        )
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Process asset {process_asset_ref} could not read source artifact: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Process asset {process_asset_ref} source payload is invalid.")
    return ResolvedProcessAsset(
        process_asset_ref=process_asset_ref,
        process_asset_kind=process_asset_kind,
        producer_ticket_id=ticket_id,
        summary=summary,
        consumable_by=["context_compiler", "review", "closeout"],
        source_metadata={"source_artifact_ref": artifact_ref},
        content_type="JSON",
        json_content=transform_payload(payload),
        schema_ref=schema_ref,
    )


def _resolve_decision_summary_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    session_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        session = repository.get_board_advisory_session(session_id, connection=resolved_connection)
        if session is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        board_decision = dict(session.get("board_decision") or {})
        artifact_ref = str(board_decision.get("source_artifact_ref") or "").strip()
        if not artifact_ref:
            raise ValueError(f"Process asset {process_asset_ref} is missing its source artifact.")

        def _transform(payload: dict[str, Any]) -> dict[str, Any]:
            return dict(payload)

        base = _resolve_json_payload_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            process_asset_kind="DECISION_SUMMARY",
            ticket_id=str(session.get("approval_id") or session_id),
            artifact_ref=artifact_ref,
            schema_ref="decision_summary@1",
            summary=(
                str(board_decision.get("board_comment") or "").strip()
                or f"Board advisory decision summary for {session_id}"
            ),
            transform_payload=_transform,
            connection=resolved_connection,
        )
        canonical_ref = build_decision_summary_process_asset_ref(session_id, version_int=1)
        base.process_asset_ref = canonical_ref
        base.canonical_ref = canonical_ref
        base.version_int = 1
        base.process_asset_kind = "DECISION_SUMMARY"
        base.consumable_by = ["ceo", "review"]
        if isinstance(base.source_metadata, dict):
            base.source_metadata["approval_id"] = session.get("approval_id")
            base.source_metadata["review_pack_id"] = session.get("review_pack_id")
        return base


def _related_process_asset_refs_for_incident(
    repository: ControlPlaneRepository,
    *,
    incident: dict[str, Any],
    connection: sqlite3.Connection | None,
) -> list[str]:
    ticket_id = str(incident.get("ticket_id") or "").strip()
    if not ticket_id:
        return []
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        terminal_event = repository.get_latest_ticket_terminal_event(resolved_connection, ticket_id)
    if terminal_event is None:
        return []
    payload = terminal_event.get("payload") or {}
    produced_assets = list(payload.get("produced_process_assets") or [])
    allowed_kinds = {
        "SOURCE_CODE_DELIVERY",
        "GOVERNANCE_DOCUMENT",
        "DECISION_SUMMARY",
        "CLOSEOUT_SUMMARY",
    }
    refs = [
        str(item.get("process_asset_ref") or "").strip()
        for item in produced_assets
        if isinstance(item, dict)
        and str(item.get("process_asset_kind") or "").strip() in allowed_kinds
        and str(item.get("process_asset_ref") or "").strip()
    ]
    if refs:
        return dedupe_process_asset_refs(refs)

    created_spec = repository.get_latest_ticket_created_payload(resolved_connection, ticket_id) or {}
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        refs.append(build_source_code_delivery_process_asset_ref(ticket_id, version_int=1))
    elif output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        refs.append(build_closeout_summary_process_asset_ref(ticket_id, version_int=1))
    elif output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        refs.append(build_governance_document_process_asset_ref(ticket_id, version_int=1))
    return dedupe_process_asset_refs(refs)


def _resolve_graph_patch_proposal_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    session_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        session = repository.get_board_advisory_session(session_id, connection=resolved_connection)
        if session is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        payload = dict(session.get("latest_patch_proposal") or {})
        if not payload:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        canonical_ref = build_graph_patch_proposal_process_asset_ref(session_id, version_int=1)
        return ResolvedProcessAsset(
            process_asset_ref=canonical_ref,
            canonical_ref=canonical_ref,
            version_int=1,
            supersedes_ref=None,
            process_asset_kind="GRAPH_PATCH_PROPOSAL",
            producer_ticket_id=None,
            summary=str(payload.get("proposal_summary") or "").strip() or f"Graph patch proposal for {session_id}",
            consumable_by=["ceo", "review"],
            source_metadata={
                "workflow_id": session.get("workflow_id"),
                "approval_id": session.get("approval_id"),
                "review_pack_id": session.get("review_pack_id"),
            },
            content_type="JSON",
            json_content=payload,
            schema_ref="graph_patch_proposal@1",
        )


def _resolve_graph_patch_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    session_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        session = repository.get_board_advisory_session(session_id, connection=resolved_connection)
        if session is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        payload = dict(session.get("approved_patch") or {})
        if not payload:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        canonical_ref = build_graph_patch_process_asset_ref(session_id, version_int=1)
        return ResolvedProcessAsset(
            process_asset_ref=canonical_ref,
            canonical_ref=canonical_ref,
            version_int=1,
            supersedes_ref=None,
            process_asset_kind="GRAPH_PATCH",
            producer_ticket_id=None,
            summary=str(payload.get("reason_summary") or "").strip() or f"Graph patch for {session_id}",
            consumable_by=["ceo", "review", "ticket_graph"],
            source_metadata={
                "workflow_id": session.get("workflow_id"),
                "approval_id": session.get("approval_id"),
                "review_pack_id": session.get("review_pack_id"),
                "patched_graph_version": session.get("patched_graph_version"),
            },
            content_type="JSON",
            json_content=payload,
            schema_ref="graph_patch@1",
        )


def _resolve_failure_fingerprint_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    incident_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        incident = repository.get_incident_projection(incident_id, connection=resolved_connection)
        if incident is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        canonical_ref = build_failure_fingerprint_process_asset_ref(incident_id, version_int=1)
        related_process_asset_refs = _related_process_asset_refs_for_incident(
            repository,
            incident=incident,
            connection=resolved_connection,
        )
        return ResolvedProcessAsset(
            process_asset_ref=canonical_ref,
            canonical_ref=canonical_ref,
            version_int=1,
            supersedes_ref=None,
            process_asset_kind="FAILURE_FINGERPRINT",
            producer_ticket_id=str(incident.get("ticket_id") or "").strip() or None,
            summary=(
                f"{str(incident.get('incident_type') or 'INCIDENT').strip()} "
                f"fingerprint for {incident_id}"
            ),
            consumable_by=["context_compiler", "ceo", "review"],
            source_metadata={
                "incident_id": incident_id,
                "workflow_id": incident.get("workflow_id"),
                "node_id": incident.get("node_id"),
                "ticket_id": incident.get("ticket_id"),
            },
            content_type="JSON",
            json_content={
                "incident_id": incident_id,
                "workflow_id": str(incident.get("workflow_id") or ""),
                "node_id": incident.get("node_id"),
                "ticket_id": incident.get("ticket_id"),
                "incident_type": str(incident.get("incident_type") or ""),
                "severity": incident.get("severity"),
                "fingerprint": str(incident.get("fingerprint") or ""),
                "payload": dict(incident.get("payload") or {}),
                "related_process_asset_refs": related_process_asset_refs,
            },
            schema_ref="failure_fingerprint@1",
        )


def _workflow_incidents(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM incident_projection
        WHERE workflow_id = ?
        ORDER BY opened_at DESC, incident_id DESC
        """,
        (workflow_id,),
    ).fetchall()
    return [repository._convert_incident_projection_row(row) for row in rows]


def _workflow_ticket_ids(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection: sqlite3.Connection,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id,),
    ).fetchall()
    return [
        str(row["ticket_id"]).strip()
        for row in rows
        if str(row["ticket_id"]).strip()
    ]


def _top_level_module_path(path: str) -> str | None:
    normalized = str(path).strip().strip("/")
    if not normalized:
        return None
    return normalized.split("/", 1)[0] or None


def _resolve_project_map_slice_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    workflow_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        workflow = repository.get_workflow_projection(workflow_id, connection=resolved_connection)
        if workflow is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")

        graph_snapshot = build_ticket_graph_snapshot(
            repository,
            workflow_id,
            connection=resolved_connection,
        )
        ticket_ids = _workflow_ticket_ids(
            repository,
            workflow_id=workflow_id,
            connection=resolved_connection,
        )

        module_paths: list[str] = []
        document_surfaces: list[str] = []
        decision_asset_refs: list[str] = []
        source_process_asset_refs: list[str] = []

        for ticket_id in ticket_ids:
            created_spec = repository.get_latest_ticket_created_payload(resolved_connection, ticket_id) or {}
            output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
            terminal_event = repository.get_latest_ticket_terminal_event(resolved_connection, ticket_id)
            if terminal_event is None:
                continue
            payload = terminal_event.get("payload") or {}
            result_payload = payload.get("payload") or {}
            if not isinstance(result_payload, dict):
                result_payload = {}
            produced_assets = list(payload.get("produced_process_assets") or [])
            if output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
                for source_file in list(result_payload.get("source_files") or []):
                    if not isinstance(source_file, dict):
                        continue
                    module_path = _top_level_module_path(str(source_file.get("path") or ""))
                    if module_path:
                        module_paths.append(module_path)
                for written_artifact in list(payload.get("written_artifacts") or []):
                    if not isinstance(written_artifact, dict):
                        continue
                    module_path = _top_level_module_path(str(written_artifact.get("path") or ""))
                    if module_path:
                        module_paths.append(module_path)
                for artifact in repository.list_ticket_artifacts(ticket_id, connection=resolved_connection):
                    module_path = _top_level_module_path(str(artifact.get("logical_path") or ""))
                    if module_path:
                        module_paths.append(module_path)
                if not module_paths:
                    for allowed_pattern in list(created_spec.get("allowed_write_set") or []):
                        module_path = _top_level_module_path(str(allowed_pattern).replace("*", ""))
                        if module_path:
                            module_paths.append(module_path)
            documentation_updates = list(result_payload.get("documentation_updates") or [])
            if not documentation_updates:
                documentation_updates = list(payload.get("documentation_updates") or [])
            for documentation_update in documentation_updates:
                if not isinstance(documentation_update, dict):
                    continue
                doc_ref = str(documentation_update.get("doc_ref") or "").strip()
                if doc_ref:
                    document_surfaces.append(doc_ref)
            for asset in produced_assets:
                if not isinstance(asset, dict):
                    continue
                asset_ref = str(asset.get("process_asset_ref") or "").strip()
                asset_kind = str(asset.get("process_asset_kind") or "").strip()
                if not asset_ref:
                    continue
                if asset_kind in {"GOVERNANCE_DOCUMENT", "MEETING_DECISION_RECORD"}:
                    decision_asset_refs.append(asset_ref)
                if asset_kind in {"GOVERNANCE_DOCUMENT", "SOURCE_CODE_DELIVERY"}:
                    source_process_asset_refs.append(asset_ref)
                if asset_kind == "SOURCE_CODE_DELIVERY":
                    resolved_delivery_asset = resolve_process_asset(
                        repository,
                        asset_ref,
                        connection=resolved_connection,
                    )
                    delivery_payload = dict(resolved_delivery_asset.json_content or {})
                    for documentation_update in list(delivery_payload.get("documentation_updates") or []):
                        if not isinstance(documentation_update, dict):
                            continue
                        doc_ref = str(documentation_update.get("doc_ref") or "").strip()
                        if doc_ref:
                            document_surfaces.append(doc_ref)

        for session in repository.list_board_advisory_sessions(workflow_id, connection=resolved_connection):
            approved_patch_ref = str(session.get("approved_patch_ref") or "").strip()
            if approved_patch_ref:
                decision_asset_refs.append(approved_patch_ref)

        failure_fingerprint_refs = [
            build_failure_fingerprint_process_asset_ref(str(incident["incident_id"]), version_int=1)
            for incident in _workflow_incidents(
                repository,
                workflow_id=workflow_id,
                connection=resolved_connection,
            )
        ]

        canonical_ref = build_project_map_slice_process_asset_ref(workflow_id, version_int=1)
        return ResolvedProcessAsset(
            process_asset_ref=canonical_ref,
            canonical_ref=canonical_ref,
            version_int=1,
            supersedes_ref=None,
            process_asset_kind="PROJECT_MAP_SLICE",
            producer_ticket_id=None,
            summary=f"Workflow project map slice for {workflow_id}",
            consumable_by=["context_compiler", "ceo", "review"],
            source_metadata={
                "workflow_id": workflow_id,
                "graph_version": graph_snapshot.graph_version,
            },
            content_type="JSON",
            json_content={
                "workflow_id": workflow_id,
                "graph_version": graph_snapshot.graph_version,
                "module_paths": sorted(dedupe_process_asset_refs(module_paths)),
                "document_surfaces": sorted(dedupe_process_asset_refs(document_surfaces)),
                "decision_asset_refs": sorted(dedupe_process_asset_refs(decision_asset_refs)),
                "failure_fingerprint_refs": sorted(dedupe_process_asset_refs(failure_fingerprint_refs)),
                "source_process_asset_refs": sorted(dedupe_process_asset_refs(source_process_asset_refs)),
            },
            schema_ref="project_map_slice@1",
        )


def _resolve_meeting_decision_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    ticket_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    artifact_ref = f"art://runtime/{ticket_id}/consensus-document.json"

    def _transform(payload: dict[str, Any]) -> dict[str, Any]:
        record = payload.get("decision_record")
        if not isinstance(record, dict):
            raise ValueError(f"Process asset {process_asset_ref} has no decision_record.")
        return dict(record)

    base = _resolve_json_payload_process_asset(
        repository,
        process_asset_ref=process_asset_ref,
        process_asset_kind="MEETING_DECISION_RECORD",
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        schema_ref="consensus_document.decision_record@ADR_V1",
        summary=f"Meeting ADR for {ticket_id}",
        transform_payload=_transform,
        connection=connection,
    )
    if isinstance(base.json_content, dict):
        decision = str(base.json_content.get("decision") or "").strip()
        if decision:
            base.summary = decision
    return base


def _resolve_source_code_delivery_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    ticket_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        terminal_event = repository.get_latest_ticket_terminal_event(resolved_connection, ticket_id)
        if terminal_event is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        payload = terminal_event.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Process asset {process_asset_ref} source payload is invalid.")
        result_payload = payload.get("payload") or {}
        if not isinstance(result_payload, dict):
            result_payload = {}
        produced_assets = list(payload.get("produced_process_assets") or [])
        asset_entry = next(
            (
                item
                for item in produced_assets
                if isinstance(item, dict)
                and _matches_process_asset_ref(item, process_asset_ref)
                and str(item.get("process_asset_kind") or "") == "SOURCE_CODE_DELIVERY"
            ),
            None,
        )
        if asset_entry is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        source_metadata = dict(asset_entry.get("source_metadata") or {})
        source_file_refs = list(result_payload.get("source_file_refs") or [])
        if not source_file_refs:
            source_file_refs = [
                str(item).strip()
                for item in list(source_metadata.get("source_file_refs") or [])
                if str(item).strip()
            ] or [
                str(item).strip()
                for item in list(source_metadata.get("written_artifact_refs") or [])
                if str(item).strip()
            ]
        verification_evidence_refs = list(payload.get("verification_evidence_refs") or [])
        if not verification_evidence_refs:
            verification_evidence_refs = [
                str(item).strip()
                for item in list(source_metadata.get("verification_evidence_refs") or [])
                if str(item).strip()
            ]
        git_commit_record = payload.get("git_commit_record")
        if not isinstance(git_commit_record, dict):
            git_commit_record = dict(source_metadata.get("git_commit_record") or {})
        documentation_updates = list(result_payload.get("documentation_updates") or [])
        if not documentation_updates:
            documentation_updates = [
                item
                for item in list(source_metadata.get("documentation_updates") or [])
                if isinstance(item, dict)
            ]
        if terminal_event.get("workflow_id"):
            latest_git_closeout = load_git_closeout_receipt(str(terminal_event["workflow_id"]), ticket_id)
            if latest_git_closeout:
                git_commit_record = latest_git_closeout
        canonical_ref = str(asset_entry.get("canonical_ref") or asset_entry.get("process_asset_ref") or "").strip()
        return ResolvedProcessAsset(
            process_asset_ref=canonical_ref or process_asset_ref,
            canonical_ref=canonical_ref or process_asset_ref,
            version_int=asset_entry.get("version_int"),
            supersedes_ref=asset_entry.get("supersedes_ref"),
            process_asset_kind="SOURCE_CODE_DELIVERY",
            producer_ticket_id=ticket_id,
            summary=(
                str(result_payload.get("summary") or "").strip()
                or str(asset_entry.get("summary") or "").strip()
                or f"Source code delivery for {ticket_id}"
            ),
            consumable_by=["context_compiler", "followup_ticket", "review", "closeout"],
            source_metadata=source_metadata,
            content_type="JSON",
            json_content={
                "summary": (
                    result_payload.get("summary")
                    or asset_entry.get("summary")
                    or f"Source code delivery for {ticket_id}"
                ),
                "source_file_refs": source_file_refs,
                "implementation_notes": list(result_payload.get("implementation_notes") or []),
                "documentation_updates": documentation_updates,
                "verification_evidence_refs": verification_evidence_refs,
                "git_commit_record": git_commit_record,
            },
            schema_ref="source_code_delivery@1",
        )


def _resolve_closeout_summary_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    ticket_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    artifact_ref = f"art://runtime/{ticket_id}/delivery-closeout-package.json"

    def _transform(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": payload.get("summary"),
            "final_artifact_refs": list(payload.get("final_artifact_refs") or []),
            "handoff_notes": list(payload.get("handoff_notes") or []),
            "documentation_updates": list(payload.get("documentation_updates") or []),
        }

    base = _resolve_json_payload_process_asset(
        repository,
        process_asset_ref=process_asset_ref,
        process_asset_kind="CLOSEOUT_SUMMARY",
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        schema_ref="delivery_closeout_summary@1",
        summary=f"Delivery closeout summary for {ticket_id}",
        transform_payload=_transform,
        connection=connection,
    )
    if isinstance(base.json_content, dict):
        summary = str(base.json_content.get("summary") or "").strip()
        if summary:
            base.summary = summary
    return base


def _resolve_governance_document_process_asset(
    repository: ControlPlaneRepository,
    *,
    process_asset_ref: str,
    ticket_id: str,
    connection: sqlite3.Connection | None,
) -> ResolvedProcessAsset:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        terminal_event = repository.get_latest_ticket_terminal_event(resolved_connection, ticket_id)
        if terminal_event is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        payload = terminal_event.get("payload") or {}
        produced_assets = list(payload.get("produced_process_assets") or [])
        asset_entry = next(
            (
                item
                for item in produced_assets
                if isinstance(item, dict)
                and _matches_process_asset_ref(item, process_asset_ref)
                and str(item.get("process_asset_kind") or "") == "GOVERNANCE_DOCUMENT"
            ),
            None,
        )
        if asset_entry is None:
            raise ValueError(f"Process asset {process_asset_ref} is missing.")
        source_metadata = dict(asset_entry.get("source_metadata") or {})
        artifact_ref = str(source_metadata.get("source_artifact_ref") or "").strip()
        if not artifact_ref:
            raise ValueError(f"Process asset {process_asset_ref} is missing its source artifact.")

        def _transform(governance_payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "title": governance_payload.get("title"),
                "summary": governance_payload.get("summary"),
                "document_kind_ref": governance_payload.get("document_kind_ref"),
                "linked_document_refs": list(governance_payload.get("linked_document_refs") or []),
                "linked_artifact_refs": list(governance_payload.get("linked_artifact_refs") or []),
                "source_process_asset_refs": list(governance_payload.get("source_process_asset_refs") or []),
                "decisions": list(governance_payload.get("decisions") or []),
                "constraints": list(governance_payload.get("constraints") or []),
                "sections": list(governance_payload.get("sections") or []),
                "followup_recommendations": list(
                    governance_payload.get("followup_recommendations") or []
                ),
            }

        base = _resolve_json_payload_process_asset(
            repository,
            process_asset_ref=process_asset_ref,
            process_asset_kind="GOVERNANCE_DOCUMENT",
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            schema_ref=f"{source_metadata.get('document_kind_ref') or 'governance_document'}@1",
            summary=str(asset_entry.get("summary") or f"Governance document for {ticket_id}"),
            transform_payload=_transform,
            connection=resolved_connection,
        )
        canonical_ref = str(asset_entry.get("canonical_ref") or asset_entry.get("process_asset_ref") or "").strip()
        base.process_asset_ref = canonical_ref or process_asset_ref
        base.canonical_ref = canonical_ref or process_asset_ref
        base.version_int = asset_entry.get("version_int")
        base.supersedes_ref = asset_entry.get("supersedes_ref")
        base.consumable_by = ["context_compiler", "followup_ticket", "review"]
        if isinstance(base.source_metadata, dict):
            base.source_metadata["document_kind_ref"] = source_metadata.get("document_kind_ref")
        if isinstance(base.json_content, dict):
            summary = str(base.json_content.get("summary") or "").strip()
            if summary:
                base.summary = summary
        return base
