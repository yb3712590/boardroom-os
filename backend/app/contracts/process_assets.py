from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.contracts.common import StrictModel

ProcessAssetKind = Literal[
    "ARTIFACT",
    "COMPILED_CONTEXT_BUNDLE",
    "COMPILE_MANIFEST",
    "COMPILED_EXECUTION_PACKAGE",
    "DECISION_SUMMARY",
    "FAILURE_FINGERPRINT",
    "GRAPH_PATCH",
    "GRAPH_PATCH_PROPOSAL",
    "PROJECT_MAP_SLICE",
    "SOURCE_CODE_DELIVERY",
    "MEETING_DECISION_RECORD",
    "CLOSEOUT_SUMMARY",
    "GOVERNANCE_DOCUMENT",
]

ProcessAssetContentType = Literal["TEXT", "JSON"]


class ProcessAssetReference(StrictModel):
    process_asset_ref: str = Field(min_length=1)
    canonical_ref: str | None = None
    version_int: int | None = Field(default=None, ge=1)
    supersedes_ref: str | None = None
    process_asset_kind: ProcessAssetKind
    producer_ticket_id: str | None = None
    summary: str | None = None
    consumable_by: list[str] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedProcessAsset(ProcessAssetReference):
    content_type: ProcessAssetContentType | None = None
    text_content: str | None = None
    json_content: dict[str, Any] | None = None
    schema_ref: str | None = None
    artifact_ref: str | None = None
    artifact_access: dict[str, Any] | None = None
    fallback_reason: str | None = None
    fallback_reason_code: str | None = None
