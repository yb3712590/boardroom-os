from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.contracts.common import StrictModel

ProcessAssetKind = Literal[
    "ARTIFACT",
    "COMPILED_CONTEXT_BUNDLE",
    "COMPILE_MANIFEST",
    "COMPILED_EXECUTION_PACKAGE",
    "MEETING_DECISION_RECORD",
    "CLOSEOUT_SUMMARY",
    "GOVERNANCE_DOCUMENT",
]

ProcessAssetContentType = Literal["TEXT", "JSON"]


class ProcessAssetReference(StrictModel):
    process_asset_ref: str = Field(min_length=1)
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
