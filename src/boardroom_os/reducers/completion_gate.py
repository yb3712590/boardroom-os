from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.checker.verdict import (
    CheckerVerdict,
    CheckerVerdictRef,
    CheckerVerdictStatus,
)
from boardroom_os.evidence.fallback_registry import (
    FallbackDecisionRecord,
    FallbackDecisionRecordRef,
)
from boardroom_os.evidence.table import (
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableRef,
)
from boardroom_os.evidence.verifier import VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.reducers.ticket_reducer import TicketCompletionSnapshot


class CompletionGateError(ValueError):
    pass


def _reject_malformed_completion_gate_tuple_inputs(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for field_name in (
        "verified_evidence",
        "provider_attempt_refs",
        "work_product_submitted_refs",
        "fallback_decision_records",
    ):
        if field_name in data and not isinstance(data[field_name], list | tuple):
            raise ValueError(f"{field_name} must be a tuple or list")
    return data


class CompletionGateInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: TicketId
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    verified_evidence: tuple[VerifiedEvidence, ...]
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    work_product_submitted_refs: tuple[WorkProductRef, ...]
    fallback_decision_records: tuple[FallbackDecisionRecord, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(_reject_malformed_completion_gate_tuple_inputs(data))
        return _normalize_ref_fields(
            normalized,
            {"ticket_ref": TicketId},
            {
                "provider_attempt_refs": ProviderAttemptRef,
                "work_product_submitted_refs": WorkProductRef,
            },
        )

    @field_validator("final_evidence_table", mode="wrap")
    @classmethod
    def _require_final_evidence_table_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> FinalEvidenceTable:
        if not isinstance(value, FinalEvidenceTable):
            raise ValueError("final_evidence_table must be a FinalEvidenceTable")
        return value

    @field_validator("checker_verdict", mode="wrap")
    @classmethod
    def _require_checker_verdict_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> CheckerVerdict:
        if not isinstance(value, CheckerVerdict):
            raise ValueError("checker_verdict must be a CheckerVerdict")
        return value

    @field_validator("verified_evidence", mode="before")
    @classmethod
    def _require_verified_evidence_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("verified_evidence must be a tuple or list")
        for item in value:
            if not isinstance(item, VerifiedEvidence):
                raise ValueError("verified_evidence must contain VerifiedEvidence values")
        return value

    @field_validator("fallback_decision_records", mode="before")
    @classmethod
    def _require_fallback_decision_record_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("fallback_decision_records must be a tuple or list")
        for item in value:
            if not isinstance(item, FallbackDecisionRecord):
                raise ValueError(
                    "fallback_decision_records must contain FallbackDecisionRecord values"
                )
        return value


class CompletionGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    completion_snapshot: TicketCompletionSnapshot
    provider_attempt_count: int = Field(ge=0)
    final_evidence_table_ref: FinalEvidenceTableRef
    checker_verdict_ref: CheckerVerdictRef
    verified_evidence_refs: tuple[VerifiedEvidenceRef, ...]
    fallback_decision_record_refs: tuple[FallbackDecisionRecordRef, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for field_name in ("verified_evidence_refs", "fallback_decision_record_refs"):
            if field_name in normalized and not isinstance(normalized[field_name], list | tuple):
                raise ValueError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            normalized,
            {
                "final_evidence_table_ref": FinalEvidenceTableRef,
                "checker_verdict_ref": CheckerVerdictRef,
            },
            {
                "verified_evidence_refs": VerifiedEvidenceRef,
                "fallback_decision_record_refs": FallbackDecisionRecordRef,
            },
        )

    @model_validator(mode="after")
    def _validate_derived_fields(self) -> Self:
        if self.provider_attempt_count != self.completion_snapshot.provider_attempt_count:
            raise ValueError(
                "provider_attempt_count must match completion_snapshot.provider_attempt_count"
            )
        self._require_unique_refs(self.verified_evidence_refs, "verified_evidence_refs")
        self._require_unique_refs(
            self.fallback_decision_record_refs,
            "fallback_decision_record_refs",
        )
        return self

    @staticmethod
    def _require_unique_refs(values: tuple[Any, ...], field_name: str) -> None:
        ref_values = [value.value for value in values]
        if len(set(ref_values)) != len(ref_values):
            raise ValueError(f"{field_name} values must be unique")


class CompletionGate:
    def build_completion_snapshot(
        self,
        gate_input: CompletionGateInput,
    ) -> CompletionGateResult:
        if not isinstance(gate_input, CompletionGateInput):
            raise CompletionGateError("gate_input must be a CompletionGateInput")

        self._verify_final_evidence_table(gate_input)
        self._verify_checker_verdict(gate_input)
        provider_attempt_count = self._verify_provider_attempt_refs(gate_input)
        self._verify_work_product_submission(gate_input)
        self._verify_fallback_lineage(gate_input)

        return CompletionGateResult(
            completion_snapshot=TicketCompletionSnapshot(
                ticket_id=gate_input.ticket_ref,
                provider_attempt_count=provider_attempt_count,
                evidence_complete=True,
                checker_approved=True,
                blocking_issue_refs=(),
            ),
            provider_attempt_count=provider_attempt_count,
            final_evidence_table_ref=self._required_final_evidence_table_ref(
                gate_input.final_evidence_table
            ),
            checker_verdict_ref=self._required_checker_verdict_ref(gate_input.checker_verdict),
            verified_evidence_refs=tuple(
                evidence.verified_evidence_id for evidence in gate_input.verified_evidence
            ),
            fallback_decision_record_refs=tuple(
                record.fallback_decision_record_id
                for record in gate_input.fallback_decision_records
            ),
        )

    def _verify_final_evidence_table(self, gate_input: CompletionGateInput) -> None:
        table = gate_input.final_evidence_table
        if any(row.status is FinalEvidenceStatus.FAILED for row in table.rows):
            raise CompletionGateError("final evidence table rows must be satisfied")
        if table.complete is not True:
            raise CompletionGateError("final evidence table must be complete")
        if any(row.status is not FinalEvidenceStatus.SATISFIED for row in table.rows):
            raise CompletionGateError("final evidence table rows must be satisfied")

        verified_evidence_ids: list[str] = []
        for evidence in gate_input.verified_evidence:
            evidence_id = evidence.verified_evidence_id.value
            if evidence_id in verified_evidence_ids:
                raise CompletionGateError("verified_evidence refs must be unique")
            verified_evidence_ids.append(evidence_id)

        table_verified_evidence_refs = {
            ref.value
            for row in table.rows
            for ref in row.verified_evidence_refs
        }
        if table_verified_evidence_refs != set(verified_evidence_ids):
            raise CompletionGateError(
                "verified_evidence refs must exactly match final evidence table refs"
            )

    def _verify_checker_verdict(self, gate_input: CompletionGateInput) -> None:
        table = gate_input.final_evidence_table
        verdict = gate_input.checker_verdict
        table_ref = self._required_final_evidence_table_ref(table)

        if verdict.ticket_ref != gate_input.ticket_ref:
            raise CompletionGateError("checker verdict ticket_ref must match ticket_ref")
        if verdict.final_evidence_table_ref != table_ref:
            raise CompletionGateError(
                "checker verdict final_evidence_table_ref must match final evidence table"
            )
        if verdict.acceptance_contract_ref != table.acceptance_contract_ref:
            raise CompletionGateError(
                "checker verdict acceptance_contract_ref must match final evidence table"
            )
        if verdict.status not in (
            CheckerVerdictStatus.APPROVED,
            CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
        ):
            raise CompletionGateError("checker verdict must be approved")
        if verdict.blockers:
            raise CompletionGateError("checker blockers must be empty")

    def _verify_provider_attempt_refs(self, gate_input: CompletionGateInput) -> int:
        provider_attempt_values = [ref.value for ref in gate_input.provider_attempt_refs]
        if not provider_attempt_values:
            raise CompletionGateError("provider attempt refs must not be empty")
        if len(set(provider_attempt_values)) != len(provider_attempt_values):
            raise CompletionGateError("provider_attempt_refs must be unique")

        allowed_provider_attempt_values = set(provider_attempt_values)
        for evidence in gate_input.verified_evidence:
            if evidence.producer_attempt_ref.value not in allowed_provider_attempt_values:
                raise CompletionGateError(
                    "verified evidence producer_attempt_ref must be included in provider_attempt_refs"
                )
        return len(allowed_provider_attempt_values)

    def _verify_work_product_submission(self, gate_input: CompletionGateInput) -> None:
        submitted_work_product_values = {
            ref.value for ref in gate_input.work_product_submitted_refs
        }
        if gate_input.checker_verdict.work_product_ref.value not in submitted_work_product_values:
            raise CompletionGateError(
                "checker work product must appear in work product submissions"
            )

    def _verify_fallback_lineage(self, gate_input: CompletionGateInput) -> None:
        records_by_ref: dict[str, FallbackDecisionRecord] = {}
        for record in gate_input.fallback_decision_records:
            record_ref_value = record.fallback_decision_record_id.value
            if record_ref_value in records_by_ref:
                raise CompletionGateError("fallback decision record refs must be unique")
            records_by_ref[record_ref_value] = record

        used_record_refs: set[str] = set()
        for evidence in gate_input.verified_evidence:
            record_ref = evidence.fallback_decision_record_ref
            recorded_ref = evidence.fallback_decision_recorded_ref

            if record_ref is None:
                if recorded_ref is not None:
                    raise CompletionGateError(
                        "primary evidence must not include fallback decision recorded ref"
                    )
                continue

            if recorded_ref is None:
                raise CompletionGateError(
                    "fallback evidence requires FALLBACK_DECISION_RECORDED lineage"
                )

            record = records_by_ref.get(record_ref.value)
            if record is None:
                raise CompletionGateError(
                    "fallback evidence requires matching decision record"
                )
            used_record_refs.add(record_ref.value)

            if record.decision.allowed is not True:
                raise CompletionGateError(
                    "fallback decision record must be allowed"
                )
            if record.evidence_claim_ref != evidence.evidence_claim_ref:
                raise CompletionGateError(
                    "fallback decision record evidence_claim_ref must match verified evidence"
                )
            if record.producer_attempt_ref != evidence.producer_attempt_ref:
                raise CompletionGateError(
                    "fallback decision record producer_attempt_ref must match verified evidence"
                )
            if record.required_artifact_type != evidence.required_artifact_type:
                raise CompletionGateError(
                    "fallback decision record required_artifact_type must match verified evidence"
                )
            if record.evaluated_purpose != evidence.expected_purpose:
                raise CompletionGateError(
                    "fallback decision record evaluated_purpose must match verified evidence"
                )
            if record.acceptance_refs != evidence.acceptance_refs:
                raise CompletionGateError(
                    "fallback decision record acceptance_refs must match verified evidence"
                )

        unreferenced_record_refs = set(records_by_ref) - used_record_refs
        if unreferenced_record_refs:
            raise CompletionGateError(
                "unreferenced fallback decision records are not allowed"
            )

    def _required_final_evidence_table_ref(
        self,
        final_evidence_table: FinalEvidenceTable,
    ) -> FinalEvidenceTableRef:
        if final_evidence_table.final_evidence_table_id is None:
            raise CompletionGateError("final evidence table ref is required")
        return final_evidence_table.final_evidence_table_id

    def _required_checker_verdict_ref(
        self,
        checker_verdict: CheckerVerdict,
    ) -> CheckerVerdictRef:
        if checker_verdict.checker_verdict_id is None:
            raise CompletionGateError("checker verdict ref is required")
        return checker_verdict.checker_verdict_id


__all__ = [
    "CompletionGate",
    "CompletionGateError",
    "CompletionGateInput",
    "CompletionGateResult",
]
