from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerBlockerRef,
    CheckerVerdict,
    CheckerVerdictRef,
    CheckerVerdictStatus,
)
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceTableRef
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId, TicketNode, TicketStatus
from boardroom_os.reducers.ticket_reducer import TicketCheckSnapshot, TicketRefPayload


class ReworkTicketGenerationError(ValueError):
    pass


class ReworkTicketPlanRef(NonEmptyTextValue):
    pass


def _non_empty_string_tuple(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    if not values:
        raise ReworkTicketGenerationError(f"{field_name} must not be empty")
    normalized_values: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ReworkTicketGenerationError(f"{field_name} must contain strings")
        normalized = value.strip()
        if not normalized:
            raise ReworkTicketGenerationError(f"{field_name} must not contain empty values")
        normalized_values.append(normalized)
    return tuple(normalized_values)


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return tuple(deduped)


class ReworkTicketOverrides(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    purpose: str | None = None
    allowed_read_refs: tuple[str, ...] = ()
    allowed_write_set: tuple[str, ...] | None = None

    @field_validator("purpose")
    @classmethod
    def _reject_blank_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("purpose must not be empty")
        return normalized

    @field_validator("allowed_read_refs")
    @classmethod
    def _normalize_allowed_read_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            return ()
        return _non_empty_string_tuple(values, field_name="allowed_read_refs")

    @field_validator("allowed_write_set")
    @classmethod
    def _reject_empty_override_write_set(
        cls,
        values: tuple[str, ...] | None,
    ) -> tuple[str, ...] | None:
        if values is None:
            return None
        return _non_empty_string_tuple(values, field_name="allowed_write_set")


class ReworkTicketPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    rework_plan_id: ReworkTicketPlanRef | None = None
    original_ticket_ref: TicketId
    rework_ticket_ref: TicketId
    checker_verdict_ref: CheckerVerdictRef
    final_evidence_table_ref: FinalEvidenceTableRef
    work_product_ref: WorkProductRef
    blocker_refs: tuple[CheckerBlockerRef, ...]
    acceptance_refs: tuple[str, ...]
    source_surface_refs: tuple[str, ...]
    evidence_obligations: tuple[str, ...]
    allowed_write_set: tuple[str, ...]
    generated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = _normalize_ref_fields(
            data,
            {
                "rework_plan_id": ReworkTicketPlanRef,
                "original_ticket_ref": TicketId,
                "rework_ticket_ref": TicketId,
                "checker_verdict_ref": CheckerVerdictRef,
                "final_evidence_table_ref": FinalEvidenceTableRef,
                "work_product_ref": WorkProductRef,
            },
            {"blocker_refs": CheckerBlockerRef},
        )
        rework_ticket_ref = normalized.get("rework_ticket_ref")
        if "rework_plan_id" not in normalized and isinstance(rework_ticket_ref, TicketId):
            normalized["rework_plan_id"] = ReworkTicketPlanRef(
                value=f"rework-plan.{rework_ticket_ref.value}"
            )
        return normalized

    @field_validator("blocker_refs")
    @classmethod
    def _reject_empty_blocker_refs(
        cls,
        values: tuple[CheckerBlockerRef, ...],
    ) -> tuple[CheckerBlockerRef, ...]:
        if not values:
            raise ValueError("blocker_refs must not be empty")
        return values

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _non_empty_string_tuple(values, field_name="acceptance_refs")

    @field_validator("source_surface_refs")
    @classmethod
    def _reject_empty_source_surface_refs(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _non_empty_string_tuple(values, field_name="source_surface_refs")

    @field_validator("evidence_obligations")
    @classmethod
    def _reject_empty_evidence_obligations(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _non_empty_string_tuple(values, field_name="evidence_obligations")

    @field_validator("allowed_write_set")
    @classmethod
    def _reject_empty_allowed_write_set(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _non_empty_string_tuple(values, field_name="allowed_write_set")

    @field_validator("generated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_derived_fields(self) -> Self:
        expected_plan_id = ReworkTicketPlanRef(
            value=f"rework-plan.{self.rework_ticket_ref.value}"
        )
        if self.rework_plan_id != expected_plan_id:
            raise ValueError(
                "rework_plan_id must be rework-plan.<rework_ticket_ref>"
            )
        if self.rework_ticket_ref == self.original_ticket_ref:
            raise ValueError("rework_ticket_ref must differ from original_ticket_ref")
        return self


class ReworkTicketGenerationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    original_ticket: TicketNode
    checker_verdict: CheckerVerdict
    overrides: ReworkTicketOverrides | None = None
    generated_at: datetime

    @field_validator("original_ticket", mode="wrap")
    @classmethod
    def _require_original_ticket_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> TicketNode:
        if not isinstance(value, TicketNode):
            raise ValueError("original_ticket must be a TicketNode")
        return handler(value)

    @field_validator("checker_verdict", mode="wrap")
    @classmethod
    def _require_checker_verdict_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> CheckerVerdict:
        if not isinstance(value, CheckerVerdict):
            raise ValueError("checker_verdict must be a CheckerVerdict")
        return handler(value)

    @field_validator("overrides", mode="wrap")
    @classmethod
    def _require_overrides_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> ReworkTicketOverrides | None:
        if value is None:
            return None
        if not isinstance(value, ReworkTicketOverrides):
            raise ValueError("overrides must be a ReworkTicketOverrides")
        return handler(value)

    @field_validator("generated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value


class ReworkTicketGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: ReworkTicketPlan
    rework_ticket_payload: TicketCreatedPayload
    original_ticket_check_snapshot: TicketCheckSnapshot
    original_ticket_reworked_payload: TicketRefPayload

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        plan = self.plan
        payload = self.rework_ticket_payload
        snapshot = self.original_ticket_check_snapshot
        reworked_payload = self.original_ticket_reworked_payload

        if payload.ticket_id != plan.rework_ticket_ref:
            raise ValueError("rework_ticket_payload.ticket_id must match plan.rework_ticket_ref")
        if payload.depends_on:
            raise ValueError("rework_ticket_payload.depends_on must be empty")
        if snapshot.ticket_id != plan.original_ticket_ref:
            raise ValueError(
                "original_ticket_check_snapshot.ticket_id must match plan.original_ticket_ref"
            )
        if reworked_payload.ticket_id != plan.original_ticket_ref:
            raise ValueError(
                "original_ticket_reworked_payload.ticket_id must match plan.original_ticket_ref"
            )
        if snapshot.checker_approved:
            raise ValueError("original_ticket_check_snapshot.checker_approved must be false")
        if snapshot.blocking_issue_refs != tuple(ref.value for ref in plan.blocker_refs):
            raise ValueError(
                "original_ticket_check_snapshot.blocking_issue_refs must match plan.blocker_refs"
            )
        if payload.acceptance_refs != plan.acceptance_refs:
            raise ValueError("rework_ticket_payload.acceptance_refs must match plan.acceptance_refs")
        if payload.source_surface_refs != plan.source_surface_refs:
            raise ValueError(
                "rework_ticket_payload.source_surface_refs must match plan.source_surface_refs"
            )
        if payload.evidence_obligations != plan.evidence_obligations:
            raise ValueError(
                "rework_ticket_payload.evidence_obligations must match plan.evidence_obligations"
            )
        if payload.allowed_write_set != plan.allowed_write_set:
            raise ValueError(
                "rework_ticket_payload.allowed_write_set must match plan.allowed_write_set"
            )
        return self


class ReworkTicketGenerator:
    def generate(
        self,
        generation_input: ReworkTicketGenerationInput,
    ) -> ReworkTicketGenerationResult:
        if not isinstance(generation_input, ReworkTicketGenerationInput):
            raise ReworkTicketGenerationError(
                "generation_input must be a ReworkTicketGenerationInput"
            )
        ticket = generation_input.original_ticket
        verdict = generation_input.checker_verdict
        if verdict.status is not CheckerVerdictStatus.REWORK_REQUIRED:
            raise ReworkTicketGenerationError(
                "checker_verdict status must be rework_required"
            )
        if verdict.ticket_ref != ticket.ticket_id:
            raise ReworkTicketGenerationError("checker_verdict ticket_ref must match original ticket")
        if not verdict.blockers:
            raise ReworkTicketGenerationError("checker_verdict blockers must not be empty")
        if ticket.status is TicketStatus.COMPLETED:
            raise ReworkTicketGenerationError("completed original ticket cannot be reworked")
        self._require_ticket_scope(ticket)
        blocker_refs = self._blocker_refs(verdict)
        acceptance_refs = self._rework_acceptance_refs(ticket, verdict)
        return self._build_result(
            ticket=ticket,
            verdict=verdict,
            blocker_refs=blocker_refs,
            acceptance_refs=acceptance_refs,
            generation_input=generation_input,
        )

    def _require_ticket_scope(self, ticket: TicketNode) -> None:
        if not ticket.acceptance_refs:
            raise ReworkTicketGenerationError("original ticket acceptance_refs must not be empty")
        if not ticket.source_surface_refs:
            raise ReworkTicketGenerationError("original ticket source_surface_refs must not be empty")
        if not ticket.evidence_obligations:
            raise ReworkTicketGenerationError("original ticket evidence_obligations must not be empty")
        if not ticket.allowed_write_set:
            raise ReworkTicketGenerationError("original ticket allowed_write_set must not be empty")

    def _blocker_refs(self, verdict: CheckerVerdict) -> tuple[CheckerBlockerRef, ...]:
        refs: list[CheckerBlockerRef] = []
        for blocker in verdict.blockers:
            if blocker.blocker_id is None:
                raise ReworkTicketGenerationError("checker_verdict.blockers[*].blocker_id must not be empty")
            self._require_blocker_text_fields(blocker)
            refs.append(blocker.blocker_id)
        return tuple(refs)

    def _require_blocker_text_fields(self, blocker: Any) -> None:
        for field_name in ("message", "related_ref", "source"):
            value = getattr(blocker, field_name, None)
            if not isinstance(value, str) or not value.strip():
                raise ReworkTicketGenerationError(
                    f"checker_verdict.blockers[*].{field_name} must not be empty"
                )

    def _rework_acceptance_refs(self, ticket: TicketNode, verdict: CheckerVerdict) -> tuple[str, ...]:
        original_refs = self._string_tuple(
            tuple(ticket.acceptance_refs),
            field_name="acceptance_refs",
        )
        original_ref_set = set(original_refs)
        scoped_refs: list[str] = []
        for blocker in verdict.blockers:
            if blocker.code in {
                CheckerBlockerCode.FINAL_EVIDENCE_MISSING,
                CheckerBlockerCode.FINAL_EVIDENCE_FAILED,
            } and blocker.acceptance_ref is None:
                raise ReworkTicketGenerationError("final evidence blocker requires acceptance_ref")
            if blocker.acceptance_ref is None:
                continue
            acceptance_value = blocker.acceptance_ref.value
            if acceptance_value not in original_ref_set:
                raise ReworkTicketGenerationError("blocker acceptance_ref must belong to original ticket")
            if acceptance_value not in scoped_refs:
                scoped_refs.append(acceptance_value)
        if scoped_refs:
            return tuple(scoped_refs)
        return original_refs

    def _build_result(
        self,
        *,
        ticket: TicketNode,
        verdict: CheckerVerdict,
        blocker_refs: tuple[CheckerBlockerRef, ...],
        acceptance_refs: tuple[str, ...],
        generation_input: ReworkTicketGenerationInput,
    ) -> ReworkTicketGenerationResult:
        checker_verdict_ref = self._required_verdict_ref(verdict)
        rework_ticket_ref = self._rework_ticket_ref(ticket, checker_verdict_ref)
        source_surface_refs = self._string_tuple(
            tuple(ticket.source_surface_refs),
            field_name="source_surface_refs",
        )
        evidence_obligations = self._string_tuple(
            tuple(ticket.evidence_obligations),
            field_name="evidence_obligations",
        )
        allowed_write_set = self._allowed_write_set(ticket, generation_input.overrides)
        allowed_read_refs = self._allowed_read_refs(ticket, verdict, blocker_refs, generation_input.overrides)
        purpose = self._purpose(ticket, verdict, blocker_refs, generation_input.overrides)
        plan = ReworkTicketPlan(
            original_ticket_ref=ticket.ticket_id,
            rework_ticket_ref=rework_ticket_ref,
            checker_verdict_ref=checker_verdict_ref,
            final_evidence_table_ref=verdict.final_evidence_table_ref,
            work_product_ref=verdict.work_product_ref,
            blocker_refs=blocker_refs,
            acceptance_refs=acceptance_refs,
            source_surface_refs=source_surface_refs,
            evidence_obligations=evidence_obligations,
            allowed_write_set=allowed_write_set,
            generated_at=generation_input.generated_at,
        )
        rework_ticket_payload = TicketCreatedPayload(
            ticket_id=rework_ticket_ref,
            purpose=purpose,
            seat_demand=ticket.seat_demand,
            depends_on=(),
            acceptance_refs=acceptance_refs,
            source_surface_refs=source_surface_refs,
            evidence_obligations=evidence_obligations,
            allowed_read_refs=allowed_read_refs,
            allowed_write_set=allowed_write_set,
            attempt_count=0,
        )
        original_ticket_check_snapshot = TicketCheckSnapshot(
            ticket_id=ticket.ticket_id,
            checker_approved=False,
            blocking_issue_refs=tuple(ref.value for ref in blocker_refs),
        )
        original_ticket_reworked_payload = TicketRefPayload(ticket_id=ticket.ticket_id)
        return ReworkTicketGenerationResult(
            plan=plan,
            rework_ticket_payload=rework_ticket_payload,
            original_ticket_check_snapshot=original_ticket_check_snapshot,
            original_ticket_reworked_payload=original_ticket_reworked_payload,
        )

    def _required_verdict_ref(self, verdict: CheckerVerdict) -> CheckerVerdictRef:
        if verdict.checker_verdict_id is None:
            raise ReworkTicketGenerationError("checker_verdict.checker_verdict_id must not be empty")
        return verdict.checker_verdict_id

    def _string_tuple(self, values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
        return _non_empty_string_tuple(values, field_name=field_name)

    def _rework_ticket_ref(
        self,
        ticket: TicketNode,
        checker_verdict_ref: CheckerVerdictRef,
    ) -> TicketId:
        return TicketId(value=f"rework.{ticket.ticket_id.value}.{checker_verdict_ref.value}")

    def _allowed_write_set(
        self,
        ticket: TicketNode,
        overrides: ReworkTicketOverrides | None,
    ) -> tuple[str, ...]:
        original_write_set = _non_empty_string_tuple(
            tuple(ticket.allowed_write_set),
            field_name="allowed_write_set",
        )
        if overrides is None or overrides.allowed_write_set is None:
            return original_write_set
        narrowed_write_set = _non_empty_string_tuple(
            overrides.allowed_write_set,
            field_name="allowed_write_set",
        )
        original_write_paths = tuple(_write_scope_prefix(path) for path in original_write_set)
        if any(
            not any(
                path == original_path or path.startswith(f"{original_path}/")
                for original_path in original_write_paths
            )
            for path in tuple(_write_scope_prefix(path) for path in narrowed_write_set)
        ):
            raise ReworkTicketGenerationError(
                "overrides.allowed_write_set must not expand original ticket allowed_write_set"
            )
        return narrowed_write_set

    def _allowed_read_refs(
        self,
        ticket: TicketNode,
        verdict: CheckerVerdict,
        blocker_refs: tuple[CheckerBlockerRef, ...],
        overrides: ReworkTicketOverrides | None,
    ) -> tuple[str, ...]:
        required_refs = (
            tuple(ticket.allowed_read_refs)
            + (
                self._required_verdict_ref(verdict).value,
                verdict.final_evidence_table_ref.value,
                verdict.work_product_ref.value,
            )
            + tuple(ref.value for ref in blocker_refs)
        )
        if overrides is None:
            return _dedupe(_non_empty_string_tuple(required_refs, field_name="allowed_read_refs"))
        merged_refs = required_refs + overrides.allowed_read_refs
        return _dedupe(_non_empty_string_tuple(merged_refs, field_name="allowed_read_refs"))

    def _purpose(
        self,
        ticket: TicketNode,
        verdict: CheckerVerdict,
        blocker_refs: tuple[CheckerBlockerRef, ...],
        overrides: ReworkTicketOverrides | None,
    ) -> str:
        blocker_ref_values = ", ".join(ref.value for ref in blocker_refs)
        if overrides is not None and overrides.purpose is not None:
            return (
                f"{overrides.purpose} "
                f"(original: {ticket.ticket_id.value}; blockers: {blocker_ref_values})"
            )
        blocker_codes = ", ".join(sorted({blocker.code.value for blocker in verdict.blockers}))
        return (
            f"Rework {ticket.purpose} for checker blockers: "
            f"{blocker_codes} ({blocker_ref_values})"
        )


def _write_scope_prefix(value: str) -> str:
    stripped = value.rstrip("*").rstrip("/")
    if not stripped:
        raise ValueError("allowed_write_set must not contain empty values")
    return stripped


__all__ = [
    "ReworkTicketGenerationError",
    "ReworkTicketGenerationInput",
    "ReworkTicketGenerationResult",
    "ReworkTicketGenerator",
    "ReworkTicketOverrides",
    "ReworkTicketPlan",
    "ReworkTicketPlanRef",
]
