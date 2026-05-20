from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue
from boardroom_os.evidence.verifier import VerifiedEvidence, VerifiedEvidenceRef


class FinalEvidenceTableError(ValueError):
    pass


class FinalEvidenceTableRef(NonEmptyTextValue):
    pass


class FinalEvidenceStatus(StrEnum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    FAILED = "failed"


class FinalEvidenceBlockerCode(StrEnum):
    FAILED_EVIDENCE = "failed_evidence"
    UNKNOWN_ACCEPTANCE_REF = "unknown_acceptance_ref"
    INVALID_ACCEPTANCE_MAP = "invalid_acceptance_map"
    INACTIVE_ACCEPTANCE_CONTRACT = "inactive_acceptance_contract"


class FinalEvidenceBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocker_id: NonEmptyTextValue | None = None
    code: FinalEvidenceBlockerCode
    message: str
    acceptance_ref: AcceptanceRef
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
                "blocker_id": NonEmptyTextValue,
                "acceptance_ref": AcceptanceRef,
            },
        )
        if "blocker_id" not in normalized:
            code = normalized.get("code")
            acceptance_ref = normalized.get("acceptance_ref")
            related_ref = normalized.get("related_ref")
            code_value = getattr(code, "value", str(code))
            if isinstance(acceptance_ref, AcceptanceRef):
                acceptance_ref_value = acceptance_ref.value
            elif isinstance(acceptance_ref, dict):
                acceptance_ref_value = acceptance_ref.get("value", "unknown")
            else:
                acceptance_ref_value = str(acceptance_ref)
            normalized["blocker_id"] = NonEmptyTextValue(
                value=f"final-evidence-blocker.{code_value}.{acceptance_ref_value}.{related_ref}"
            )
        return normalized

    @field_validator("message", "related_ref", "source")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized


class FinalEvidenceRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptance_ref: AcceptanceRef
    statement: str
    status: FinalEvidenceStatus
    verified_evidence_refs: tuple[VerifiedEvidenceRef, ...]
    blockers: tuple[FinalEvidenceBlocker, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "verified_evidence_refs" in data and not isinstance(
            data["verified_evidence_refs"], list | tuple
        ):
            raise ValueError("verified_evidence_refs must be a tuple or list")
        if "blockers" in data and not isinstance(data["blockers"], list | tuple):
            raise ValueError("blockers must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {"acceptance_ref": AcceptanceRef},
            {"verified_evidence_refs": VerifiedEvidenceRef},
        )

    @field_validator("statement")
    @classmethod
    def _reject_empty_statement(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("statement must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_status_shape(self) -> Self:
        verified_ref_values = [ref.value for ref in self.verified_evidence_refs]
        if len(set(verified_ref_values)) != len(verified_ref_values):
            raise ValueError("verified_evidence_refs must be unique")
        if self.status is FinalEvidenceStatus.SATISFIED:
            if not self.verified_evidence_refs:
                raise ValueError("satisfied row requires verified_evidence_refs")
            if self.blockers:
                raise ValueError("satisfied row must not include blockers")
        if self.status is FinalEvidenceStatus.MISSING:
            if self.verified_evidence_refs or self.blockers:
                raise ValueError("missing row must not include evidence refs or blockers")
        if self.status is FinalEvidenceStatus.FAILED and not self.blockers:
            raise ValueError("failed row requires blockers")
        return self


class FinalEvidenceTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    final_evidence_table_id: FinalEvidenceTableRef | None = None
    acceptance_contract_ref: ContractId
    generated_at: datetime
    rows: tuple[FinalEvidenceRow, ...]
    complete: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "rows" in normalized and not isinstance(normalized["rows"], list | tuple):
            raise ValueError("rows must be a tuple or list")
        if "final_evidence_table_id" not in normalized and "acceptance_contract_ref" in normalized:
            contract_ref = normalized["acceptance_contract_ref"]
            if isinstance(contract_ref, ContractId):
                contract_ref_value = contract_ref.value
            elif isinstance(contract_ref, dict):
                contract_ref_value = contract_ref.get("value")
            else:
                contract_ref_value = str(contract_ref)
            normalized["final_evidence_table_id"] = FinalEvidenceTableRef(
                value=f"final-evidence-table.{contract_ref_value}"
            )
        return _normalize_ref_fields(
            normalized,
            {
                "final_evidence_table_id": FinalEvidenceTableRef,
                "acceptance_contract_ref": ContractId,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @field_validator("rows")
    @classmethod
    def _reject_empty_or_duplicate_rows(
        cls,
        rows: tuple[FinalEvidenceRow, ...],
    ) -> tuple[FinalEvidenceRow, ...]:
        if not rows:
            raise ValueError("acceptance map rows must not be empty")
        acceptance_refs = [row.acceptance_ref.value for row in rows]
        if len(set(acceptance_refs)) != len(acceptance_refs):
            raise ValueError("row acceptance_ref values must be unique")
        return rows

    @model_validator(mode="after")
    def _validate_derived_fields(self) -> Self:
        expected_id = FinalEvidenceTableRef(
            value=f"final-evidence-table.{self.acceptance_contract_ref.value}"
        )
        if self.final_evidence_table_id != expected_id:
            raise ValueError(
                "final_evidence_table_id must be final-evidence-table.<acceptance_contract_ref>"
            )

        derived_complete = all(row.status is FinalEvidenceStatus.SATISFIED for row in self.rows)
        if self.complete is None:
            object.__setattr__(self, "complete", derived_complete)
        elif self.complete is not derived_complete:
            raise ValueError("complete must be derived from rows")
        return self


class FinalEvidenceTableInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    active_acceptance_contract: AcceptanceContract
    verified_evidence: tuple[VerifiedEvidence, ...] = ()
    failed_blockers: tuple[FinalEvidenceBlocker, ...] = ()
    generated_at: datetime

    @field_validator("active_acceptance_contract", mode="wrap")
    @classmethod
    def _require_acceptance_contract_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> AcceptanceContract:
        if not isinstance(value, AcceptanceContract):
            raise ValueError("active_acceptance_contract must be an AcceptanceContract")
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

    @field_validator("failed_blockers", mode="before")
    @classmethod
    def _require_failed_blocker_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("failed_blockers must be a tuple or list")
        for item in value:
            if not isinstance(item, FinalEvidenceBlocker):
                raise ValueError("failed_blockers must contain FinalEvidenceBlocker values")
        return value

    @field_validator("generated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value


class FinalEvidenceTableBuilder:
    def build(self, table_input: FinalEvidenceTableInput) -> FinalEvidenceTable:
        contract = table_input.active_acceptance_contract
        if contract.status.value != "active":
            raise FinalEvidenceTableError("active_acceptance_contract must be active")

        blocking_criteria = contract.blocking_criteria()
        if not blocking_criteria:
            raise FinalEvidenceTableError("acceptance map requires at least one blocking criterion")

        active_acceptance_refs = {criterion.acceptance_ref.value for criterion in contract.criteria}
        blocking_acceptance_refs = {criterion.acceptance_ref.value for criterion in blocking_criteria}

        evidence_refs_by_acceptance: dict[str, list[VerifiedEvidenceRef]] = {
            acceptance_ref: [] for acceptance_ref in blocking_acceptance_refs
        }
        for evidence in table_input.verified_evidence:
            for acceptance_ref in evidence.acceptance_refs:
                if acceptance_ref.value not in active_acceptance_refs:
                    raise FinalEvidenceTableError(
                        f"unknown acceptance_ref in verified evidence: {acceptance_ref.value}"
                    )
                if acceptance_ref.value in blocking_acceptance_refs:
                    evidence_refs_by_acceptance[acceptance_ref.value].append(
                        evidence.verified_evidence_id
                    )

        blockers_by_acceptance: dict[str, list[FinalEvidenceBlocker]] = {
            acceptance_ref: [] for acceptance_ref in blocking_acceptance_refs
        }
        for blocker in table_input.failed_blockers:
            if blocker.acceptance_ref.value not in blocking_acceptance_refs:
                raise FinalEvidenceTableError(
                    "failed blocker acceptance_ref is not active blocking: "
                    f"{blocker.acceptance_ref.value}"
                )
            blockers_by_acceptance[blocker.acceptance_ref.value].append(blocker)

        rows: list[FinalEvidenceRow] = []
        for criterion in blocking_criteria:
            acceptance_ref_value = criterion.acceptance_ref.value
            verified_refs = tuple(evidence_refs_by_acceptance[acceptance_ref_value])
            blockers = tuple(blockers_by_acceptance[acceptance_ref_value])
            if blockers:
                status = FinalEvidenceStatus.FAILED
            elif verified_refs:
                status = FinalEvidenceStatus.SATISFIED
            else:
                status = FinalEvidenceStatus.MISSING
            rows.append(
                FinalEvidenceRow(
                    acceptance_ref=criterion.acceptance_ref,
                    statement=criterion.statement,
                    status=status,
                    verified_evidence_refs=verified_refs,
                    blockers=blockers,
                )
            )

        return FinalEvidenceTable(
            acceptance_contract_ref=contract.acceptance_contract_id,
            generated_at=table_input.generated_at,
            rows=tuple(rows),
        )


__all__ = [
    "FinalEvidenceBlocker",
    "FinalEvidenceBlockerCode",
    "FinalEvidenceRow",
    "FinalEvidenceStatus",
    "FinalEvidenceTable",
    "FinalEvidenceTableBuilder",
    "FinalEvidenceTableError",
    "FinalEvidenceTableInput",
    "FinalEvidenceTableRef",
]
