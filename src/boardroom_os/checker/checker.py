from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerNote,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictError,
    CheckerVerdictStatus,
    SourceDiffRef,
)
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.evidence.table import FinalEvidenceStatus, FinalEvidenceTable
from boardroom_os.execution.work_product import WorkProduct
from boardroom_os.graph.ticket import TicketId


class CheckerServiceInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    ticket_ref: TicketId
    work_product: WorkProduct
    source_diff_ref: SourceDiffRef
    active_acceptance_contract: AcceptanceContract
    final_evidence_table: FinalEvidenceTable
    notes: tuple[CheckerNote, ...] = ()
    checker_blockers: tuple[CheckerVerdictBlocker, ...] = ()
    checked_at: datetime

    @field_validator("work_product", mode="wrap")
    @classmethod
    def _require_work_product_instance(cls, value: Any, handler: Any) -> WorkProduct:
        if not isinstance(value, WorkProduct):
            raise CheckerVerdictError("work_product must be a WorkProduct")
        return value

    @field_validator("source_diff_ref", mode="wrap")
    @classmethod
    def _require_source_diff_ref_instance(cls, value: Any, handler: Any) -> SourceDiffRef:
        if not isinstance(value, SourceDiffRef):
            raise CheckerVerdictError("source_diff_ref must be a SourceDiffRef")
        return value

    @field_validator("active_acceptance_contract", mode="wrap")
    @classmethod
    def _require_acceptance_contract_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> AcceptanceContract:
        if not isinstance(value, AcceptanceContract):
            raise CheckerVerdictError(
                "active_acceptance_contract must be an AcceptanceContract"
            )
        return value

    @field_validator("final_evidence_table", mode="wrap")
    @classmethod
    def _require_final_evidence_table_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> FinalEvidenceTable:
        if not isinstance(value, FinalEvidenceTable):
            raise CheckerVerdictError("final_evidence_table must be a FinalEvidenceTable")
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def _require_note_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise CheckerVerdictError("notes must be a tuple or list")
        for item in value:
            if not isinstance(item, CheckerNote):
                raise CheckerVerdictError("notes must contain CheckerNote values")
        return value

    @field_validator("checker_blockers", mode="before")
    @classmethod
    def _require_checker_blocker_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise CheckerVerdictError("checker_blockers must be a tuple or list")
        for item in value:
            if not isinstance(item, CheckerVerdictBlocker):
                raise CheckerVerdictError(
                    "checker_blockers must contain CheckerVerdictBlocker values"
                )
        return value

    @field_validator("checked_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise CheckerVerdictError("checked_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_input_consistency(self) -> "CheckerServiceInput":
        if self.active_acceptance_contract.status.value != "active":
            raise CheckerVerdictError("active_acceptance_contract must be active")
        if not isinstance(self.source_diff_ref.value, str) or not self.source_diff_ref.value.strip():
            raise CheckerVerdictError("source_diff_ref must not be empty")
        if not self.work_product.artifact_refs:
            raise CheckerVerdictError("work_product.artifact_refs must not be empty")
        if not self.work_product.claim_refs:
            raise CheckerVerdictError("work_product.claim_refs must not be empty")
        if (
            self.final_evidence_table.acceptance_contract_ref
            != self.active_acceptance_contract.acceptance_contract_id
        ):
            raise CheckerVerdictError(
                "final_evidence_table acceptance contract must match active contract"
            )
        if self.work_product.ticket_ref != self.ticket_ref:
            raise CheckerVerdictError("work_product.ticket_ref must match ticket_ref")
        self._validate_final_evidence_table_shape()
        return self

    def _validate_final_evidence_table_shape(self) -> None:
        rows = self.final_evidence_table.rows
        if not rows:
            raise CheckerVerdictError("final_evidence_table rows must not be empty")

        acceptance_ref_values = [row.acceptance_ref.value for row in rows]
        if len(set(acceptance_ref_values)) != len(acceptance_ref_values):
            raise CheckerVerdictError("final_evidence_table acceptance_ref values must be unique")

        expected_acceptance_refs = {
            criterion.acceptance_ref.value
            for criterion in self.active_acceptance_contract.blocking_criteria()
        }
        if set(acceptance_ref_values) != expected_acceptance_refs:
            raise CheckerVerdictError(
                "final_evidence_table rows must match active blocking acceptance refs"
            )

        derived_complete = True
        for row in rows:
            if not isinstance(row.status, FinalEvidenceStatus):
                raise CheckerVerdictError("final_evidence_table row status must be valid")
            if row.status is not FinalEvidenceStatus.SATISFIED:
                derived_complete = False

            if row.status is FinalEvidenceStatus.SATISFIED:
                if not row.verified_evidence_refs:
                    raise CheckerVerdictError(
                        "satisfied final_evidence_table row requires verified_evidence_refs"
                    )
                if row.missing_required_artifact_types:
                    raise CheckerVerdictError(
                        "satisfied final_evidence_table row must not include missing artifact types"
                    )
                if row.blockers:
                    raise CheckerVerdictError(
                        "satisfied final_evidence_table row must not include blockers"
                    )
            if row.status is FinalEvidenceStatus.MISSING:
                if row.blockers:
                    raise CheckerVerdictError(
                        "missing final_evidence_table row must not include blockers"
                    )
                if not row.missing_required_artifact_types:
                    raise CheckerVerdictError(
                        "missing final_evidence_table row requires missing artifact types"
                    )
            if row.status is FinalEvidenceStatus.FAILED and not row.blockers:
                raise CheckerVerdictError("failed final_evidence_table row requires blockers")

        if self.final_evidence_table.complete is not derived_complete:
            raise CheckerVerdictError("final_evidence_table complete must be derived from rows")


class CheckerService:
    def review(self, checker_input: CheckerServiceInput) -> CheckerVerdict:
        if not isinstance(checker_input, CheckerServiceInput):
            raise CheckerVerdictError("checker_input must be a CheckerServiceInput")
        checker_input._validate_input_consistency()

        blockers = list(self._blockers_from_final_evidence_table(checker_input))
        blockers.extend(checker_input.checker_blockers)

        if blockers:
            status = CheckerVerdictStatus.REWORK_REQUIRED
        elif checker_input.notes:
            status = CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES
        else:
            status = CheckerVerdictStatus.APPROVED

        return CheckerVerdict(
            ticket_ref=checker_input.ticket_ref,
            work_product_ref=checker_input.work_product.work_product_id,
            source_diff_ref=checker_input.source_diff_ref,
            acceptance_contract_ref=checker_input.active_acceptance_contract.acceptance_contract_id,
            final_evidence_table_ref=checker_input.final_evidence_table.final_evidence_table_id,
            status=status,
            notes=checker_input.notes,
            blockers=tuple(blockers),
            checked_at=checker_input.checked_at,
        )

    def _blockers_from_final_evidence_table(
        self,
        checker_input: CheckerServiceInput,
    ) -> tuple[CheckerVerdictBlocker, ...]:
        blockers: list[CheckerVerdictBlocker] = []
        for row in checker_input.final_evidence_table.rows:
            if row.status is FinalEvidenceStatus.MISSING:
                blockers.append(
                    CheckerVerdictBlocker(
                        code=CheckerBlockerCode.FINAL_EVIDENCE_MISSING,
                        message="Final evidence table is missing blocking evidence.",
                        acceptance_ref=row.acceptance_ref,
                        related_ref=row.acceptance_ref.value,
                        source="final_evidence_table",
                    )
                )
                continue

            if row.status is FinalEvidenceStatus.FAILED:
                for final_blocker in row.blockers:
                    related_ref = (
                        final_blocker.blocker_id.value
                        if final_blocker.blocker_id is not None
                        else final_blocker.related_ref
                    )
                    blockers.append(
                        CheckerVerdictBlocker(
                            code=CheckerBlockerCode.FINAL_EVIDENCE_FAILED,
                            message=final_blocker.message,
                            acceptance_ref=row.acceptance_ref,
                            related_ref=related_ref,
                            source="final_evidence_table",
                        )
                    )
        return tuple(blockers)


__all__ = ["CheckerService", "CheckerServiceInput"]
