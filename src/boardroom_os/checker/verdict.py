from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceTableRef
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketId


class CheckerVerdictError(ValueError):
    pass


class CheckerVerdictRef(NonEmptyTextValue):
    pass


class SourceDiffRef(NonEmptyTextValue):
    pass


class CheckerNoteRef(NonEmptyTextValue):
    pass


class CheckerBlockerRef(NonEmptyTextValue):
    pass


class CheckerVerdictStatus(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_NON_BLOCKING_NOTES = "approved_with_non_blocking_notes"
    REWORK_REQUIRED = "rework_required"
    ESCALATE = "escalate"


class CheckerBlockerCode(StrEnum):
    FINAL_EVIDENCE_FAILED = "final_evidence_failed"
    FINAL_EVIDENCE_MISSING = "final_evidence_missing"
    CHECKER_BLOCKER = "checker_blocker"
    CONTRACT_MISMATCH = "contract_mismatch"
    WORK_PRODUCT_MISMATCH = "work_product_mismatch"
    INVALID_CHECKER_INPUT = "invalid_checker_input"


class CheckerNote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    note_id: CheckerNoteRef | None = None
    message: str
    related_ref: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = _normalize_ref_fields(data, {"note_id": CheckerNoteRef})
        related_ref = normalized.get("related_ref")
        if "note_id" not in normalized and isinstance(related_ref, str) and related_ref.strip():
            normalized["note_id"] = CheckerNoteRef(value=f"checker-note.{related_ref.strip()}")
        return normalized

    @field_validator("message", "related_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise CheckerVerdictError("text fields must not be empty")
        return normalized


class CheckerVerdictBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocker_id: CheckerBlockerRef | None = None
    code: CheckerBlockerCode
    message: str
    acceptance_ref: AcceptanceRef | None = None
    related_ref: str
    source: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = _normalize_ref_fields(
            data,
            {
                "blocker_id": CheckerBlockerRef,
                "acceptance_ref": AcceptanceRef,
            },
        )
        code = normalized.get("code")
        related_ref = normalized.get("related_ref")
        if "blocker_id" not in normalized and code is not None and isinstance(related_ref, str) and related_ref.strip():
            code_value = getattr(code, "value", str(code))
            acceptance_ref = normalized.get("acceptance_ref")
            if isinstance(acceptance_ref, AcceptanceRef):
                acceptance_ref_value = acceptance_ref.value
            elif acceptance_ref is None:
                acceptance_ref_value = "unscoped"
            elif isinstance(acceptance_ref, dict):
                acceptance_ref_value = acceptance_ref.get("value", "unknown")
            else:
                acceptance_ref_value = str(acceptance_ref)
            normalized["blocker_id"] = CheckerBlockerRef(
                value=(
                    f"checker-blocker.{code_value}."
                    f"{acceptance_ref_value}.{related_ref.strip()}"
                )
            )
        return normalized

    @field_validator("message", "related_ref", "source")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise CheckerVerdictError("text fields must not be empty")
        return normalized


class CheckerVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    checker_verdict_id: CheckerVerdictRef | None = None
    ticket_ref: TicketId
    work_product_ref: WorkProductRef
    source_diff_ref: SourceDiffRef
    acceptance_contract_ref: ContractId
    final_evidence_table_ref: FinalEvidenceTableRef
    status: CheckerVerdictStatus
    notes: tuple[CheckerNote, ...] = ()
    blockers: tuple[CheckerVerdictBlocker, ...] = ()
    checked_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "notes" in normalized and not isinstance(normalized["notes"], list | tuple):
            raise CheckerVerdictError("notes must be a tuple or list")
        if "blockers" in normalized and not isinstance(normalized["blockers"], list | tuple):
            raise CheckerVerdictError("blockers must be a tuple or list")
        normalized = _normalize_ref_fields(
            normalized,
            {
                "checker_verdict_id": CheckerVerdictRef,
                "ticket_ref": TicketId,
                "work_product_ref": WorkProductRef,
                "source_diff_ref": SourceDiffRef,
                "acceptance_contract_ref": ContractId,
                "final_evidence_table_ref": FinalEvidenceTableRef,
            },
        )
        ticket_ref = normalized.get("ticket_ref")
        table_ref = normalized.get("final_evidence_table_ref")
        if (
            "checker_verdict_id" not in normalized
            and isinstance(ticket_ref, TicketId)
            and isinstance(table_ref, FinalEvidenceTableRef)
        ):
            normalized["checker_verdict_id"] = CheckerVerdictRef(
                value=f"checker-verdict.{ticket_ref.value}.{table_ref.value}"
            )
        return normalized

    @field_validator("checked_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise CheckerVerdictError("checked_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_verdict_shape(self) -> Self:
        expected_id = CheckerVerdictRef(
            value=(
                f"checker-verdict.{self.ticket_ref.value}."
                f"{self.final_evidence_table_ref.value}"
            )
        )
        if self.checker_verdict_id != expected_id:
            raise CheckerVerdictError(
                "checker_verdict_id must be checker-verdict.<ticket_ref>.<final_evidence_table_ref>"
            )

        if self.status is CheckerVerdictStatus.APPROVED:
            if self.notes:
                raise CheckerVerdictError("approved verdict must not include notes")
            if self.blockers:
                raise CheckerVerdictError("approved verdict must not include blockers")
        if self.status is CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES:
            if not self.notes:
                raise CheckerVerdictError("approved_with_non_blocking_notes requires notes")
            if self.blockers:
                raise CheckerVerdictError(
                    "approved_with_non_blocking_notes must not include blockers"
                )
        if self.status is CheckerVerdictStatus.REWORK_REQUIRED and not self.blockers:
            raise CheckerVerdictError("rework_required verdict requires blockers")
        if self.status is CheckerVerdictStatus.ESCALATE and not self.blockers:
            raise CheckerVerdictError("escalate verdict requires blockers")
        return self


__all__ = [
    "CheckerBlockerCode",
    "CheckerBlockerRef",
    "CheckerNote",
    "CheckerNoteRef",
    "CheckerVerdict",
    "CheckerVerdictBlocker",
    "CheckerVerdictError",
    "CheckerVerdictRef",
    "CheckerVerdictStatus",
    "SourceDiffRef",
]
