from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictStatus,
    SourceDiffRef,
)
from boardroom_os.contracts.types import AcceptanceRef, ContractId
from boardroom_os.evidence.table import FinalEvidenceTableRef
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId, TicketNode, TicketStatus
from boardroom_os.reducers.ticket_reducer import (
    TicketCheckSnapshot,
    TicketCompletionSnapshot,
    TicketReducer,
    TicketReducerPayloadResolver,
    TicketRefPayload,
)
from boardroom_os.checker.rework import (
    ReworkTicketGenerationError,
    ReworkTicketGenerationInput,
    ReworkTicketGenerator,
)

_VERIFY_ERRORS = (ValidationError, ReworkTicketGenerationError)
_GENERATED_AT = datetime(2026, 5, 21, 14, 0, tzinfo=UTC)
_CHECKED_AT = datetime(2026, 5, 21, 13, 45, tzinfo=UTC)


def _seat_demand() -> SeatDemand:
    return SeatDemand(
        required_role_category=RoleCategory.IMPLEMENTATION,
        required_capability_tags=(
            CapabilityTag(value="task.implementation"),
            CapabilityTag(value="surface.backend"),
        ),
    )


def _ticket_node(**overrides: object) -> TicketNode:
    values: dict[str, object] = {
        "ticket_id": TicketId(value="ticket.backend"),
        "purpose": "Implement backend API surface.",
        "seat_demand": _seat_demand(),
        "depends_on": (),
        "acceptance_refs": ("AC-BACKEND", "AC-TESTS"),
        "source_surface_refs": ("surface.backend", "surface.tests"),
        "evidence_obligations": ("evidence.backend-source", "evidence.backend-tests"),
        "allowed_read_refs": ("contract.acceptance.backend",),
        "allowed_write_set": ("10-project/backend/**", "10-project/tests/**"),
        "attempt_count": 1,
        "status": TicketStatus.READY,
    }
    values.update(overrides)
    return TicketNode(**values)


def _malformed_ticket(**overrides: object) -> TicketNode:
    return _ticket_node().model_copy(update=overrides)


def _blocker(
    *,
    code: CheckerBlockerCode = CheckerBlockerCode.FINAL_EVIDENCE_MISSING,
    acceptance_ref: AcceptanceRef | None = AcceptanceRef(value="AC-TESTS"),
    related_ref: str = "final-evidence-row.AC-TESTS",
) -> CheckerVerdictBlocker:
    return CheckerVerdictBlocker(
        code=code,
        message="Required test evidence is missing.",
        acceptance_ref=acceptance_ref,
        related_ref=related_ref,
        source="final_evidence_table",
    )


def _verdict(**overrides: object) -> CheckerVerdict:
    values: dict[str, object] = {
        "ticket_ref": TicketId(value="ticket.backend"),
        "work_product_ref": WorkProductRef(value="work-product.backend"),
        "source_diff_ref": SourceDiffRef(value="source-diff.backend"),
        "acceptance_contract_ref": ContractId(value="contract.acceptance.backend"),
        "final_evidence_table_ref": FinalEvidenceTableRef(value="final-evidence-table.contract.acceptance.backend"),
        "status": CheckerVerdictStatus.REWORK_REQUIRED,
        "notes": (),
        "blockers": (_blocker(),),
        "checked_at": _CHECKED_AT,
    }
    values.update(overrides)
    return CheckerVerdict(**values)


def _generate(**overrides: object):
    fields: dict[str, object] = {
        "original_ticket": _ticket_node(),
        "checker_verdict": _verdict(),
        "generated_at": _GENERATED_AT,
    }
    fields.update(overrides)
    return ReworkTicketGenerator().generate(ReworkTicketGenerationInput(**fields))


# Negative tests first.


def test_rework_generator_rejects_approved_verdict() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="rework_required"):
        _generate(checker_verdict=_verdict(status=CheckerVerdictStatus.APPROVED, blockers=()))


def test_rework_generator_rejects_approved_with_notes_verdict() -> None:
    from boardroom_os.checker.verdict import CheckerNote

    with pytest.raises(_VERIFY_ERRORS, match="rework_required"):
        _generate(
            checker_verdict=_verdict(
                status=CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
                notes=(CheckerNote(message="non-blocking", related_ref="work-product.backend"),),
                blockers=(),
            )
        )


def test_rework_generator_rejects_escalate_verdict() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="rework_required"):
        _generate(checker_verdict=_verdict(status=CheckerVerdictStatus.ESCALATE))


def test_rework_generator_rejects_ticket_verdict_mismatch() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="ticket_ref"):
        _generate(checker_verdict=_verdict(ticket_ref=TicketId(value="ticket.other")))


def test_rework_generator_rejects_verdict_without_blockers() -> None:
    malformed = CheckerVerdict.model_construct(
        ticket_ref=TicketId(value="ticket.backend"),
        checker_verdict_id=_verdict().checker_verdict_id,
        work_product_ref=WorkProductRef(value="work-product.backend"),
        source_diff_ref=SourceDiffRef(value="source-diff.backend"),
        acceptance_contract_ref=ContractId(value="contract.acceptance.backend"),
        final_evidence_table_ref=FinalEvidenceTableRef(value="final-evidence-table.contract.acceptance.backend"),
        status=CheckerVerdictStatus.REWORK_REQUIRED,
        notes=(),
        blockers=(),
        checked_at=_CHECKED_AT,
    )
    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        _generate(checker_verdict=malformed)


def test_rework_generator_rejects_completed_original_ticket() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="completed"):
        _generate(original_ticket=_ticket_node(status=TicketStatus.COMPLETED))


def test_rework_generator_rejects_blocker_without_id() -> None:
    blocker = CheckerVerdictBlocker.model_construct(
        blocker_id=None,
        code=CheckerBlockerCode.CHECKER_BLOCKER,
        message="Manual blocker.",
        acceptance_ref=None,
        related_ref="source-diff.backend",
        source="checker_manual_review",
    )
    malformed = _verdict(blockers=(blocker,))
    with pytest.raises(_VERIFY_ERRORS, match="blocker_id"):
        _generate(checker_verdict=malformed)


def test_rework_generator_rejects_blocker_with_empty_text_fields() -> None:
    blocker = CheckerVerdictBlocker.model_construct(
        blocker_id=_blocker().blocker_id,
        code=CheckerBlockerCode.CHECKER_BLOCKER,
        message=" ",
        acceptance_ref=None,
        related_ref="source-diff.backend",
        source="checker_manual_review",
    )
    malformed = _verdict(blockers=(blocker,))
    with pytest.raises(_VERIFY_ERRORS, match="message"):
        _generate(checker_verdict=malformed)


def test_final_evidence_missing_blocker_requires_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance_ref"):
        _generate(checker_verdict=_verdict(blockers=(_blocker(acceptance_ref=None),)))


def test_final_evidence_failed_blocker_requires_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance_ref"):
        _generate(
            checker_verdict=_verdict(
                blockers=(
                    _blocker(
                        code=CheckerBlockerCode.FINAL_EVIDENCE_FAILED,
                        acceptance_ref=None,
                    ),
                )
            )
        )


def test_rework_generator_rejects_unknown_blocker_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance_ref"):
        _generate(
            checker_verdict=_verdict(
                blockers=(_blocker(acceptance_ref=AcceptanceRef(value="AC-UNKNOWN")),)
            )
        )


def test_rework_generator_rejects_malformed_ticket_without_acceptance_refs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance_refs"):
        _generate(original_ticket=_malformed_ticket(acceptance_refs=()))


def test_rework_generator_rejects_malformed_ticket_without_source_surfaces() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source_surface_refs"):
        _generate(original_ticket=_malformed_ticket(source_surface_refs=()))


def test_rework_generator_rejects_malformed_ticket_without_evidence_obligations() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="evidence_obligations"):
        _generate(original_ticket=_malformed_ticket(evidence_obligations=()))


def test_rework_generator_rejects_malformed_ticket_without_allowed_write_set() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="allowed_write_set"):
        _generate(original_ticket=_malformed_ticket(allowed_write_set=()))


def test_rework_generator_rejects_non_string_allowed_read_refs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="allowed_read_refs"):
        _generate(original_ticket=_malformed_ticket(allowed_read_refs=(ContractId(value="contract.bad"),)))


def test_rework_overrides_cannot_expand_allowed_write_set() -> None:
    from boardroom_os.checker.rework import ReworkTicketOverrides

    with pytest.raises(_VERIFY_ERRORS, match="allowed_write_set"):
        _generate(overrides=ReworkTicketOverrides(allowed_write_set=("10-project/frontend/**",)))


def test_rework_generator_rejects_naive_generated_at() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="timezone"):
        ReworkTicketGenerationInput(
            original_ticket=_ticket_node(),
            checker_verdict=_verdict(),
            generated_at=datetime(2026, 5, 21, 14, 0),
        )


def test_rework_result_rejects_plan_payload_mismatch() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()
    mismatched_payload = result.rework_ticket_payload.model_copy(
        update={"ticket_id": TicketId(value="rework.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="ticket_id"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=mismatched_payload,
            original_ticket_check_snapshot=result.original_ticket_check_snapshot,
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_check_snapshot_must_mark_checker_not_approved() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()

    with pytest.raises(_VERIFY_ERRORS, match="approved"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=result.rework_ticket_payload,
            original_ticket_check_snapshot=TicketCheckSnapshot(
                ticket_id=TicketId(value="ticket.backend"),
                checker_approved=True,
                blocking_issue_refs=result.original_ticket_check_snapshot.blocking_issue_refs,
            ),
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_check_snapshot_must_preserve_blocking_issue_refs() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()

    with pytest.raises(_VERIFY_ERRORS, match="blocking_issue_refs"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=result.rework_ticket_payload,
            original_ticket_check_snapshot=TicketCheckSnapshot(
                ticket_id=TicketId(value="ticket.backend"),
                checker_approved=False,
                blocking_issue_refs=("checker-blocker.other",),
            ),
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_ref_payload_must_point_to_original_ticket() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()

    with pytest.raises(_VERIFY_ERRORS, match="original_ticket_ref"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=result.rework_ticket_payload,
            original_ticket_check_snapshot=result.original_ticket_check_snapshot,
            original_ticket_reworked_payload=TicketRefPayload(ticket_id=TicketId(value="ticket.other")),
        )


def test_rework_payload_must_preserve_plan_acceptance_refs() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()
    mismatched_payload = result.rework_ticket_payload.model_copy(
        update={"acceptance_refs": ("AC-BACKEND",)}
    )

    with pytest.raises(_VERIFY_ERRORS, match="acceptance_refs"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=mismatched_payload,
            original_ticket_check_snapshot=result.original_ticket_check_snapshot,
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_payload_must_preserve_plan_source_surface_refs() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()
    mismatched_payload = result.rework_ticket_payload.model_copy(
        update={"source_surface_refs": ("surface.other",)}
    )

    with pytest.raises(_VERIFY_ERRORS, match="source_surface_refs"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=mismatched_payload,
            original_ticket_check_snapshot=result.original_ticket_check_snapshot,
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_payload_must_preserve_plan_evidence_obligations() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()
    mismatched_payload = result.rework_ticket_payload.model_copy(
        update={"evidence_obligations": ("evidence.other",)}
    )

    with pytest.raises(_VERIFY_ERRORS, match="evidence_obligations"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=mismatched_payload,
            original_ticket_check_snapshot=result.original_ticket_check_snapshot,
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_payload_must_preserve_plan_allowed_write_set() -> None:
    from boardroom_os.checker.rework import ReworkTicketGenerationResult

    result = _generate()
    mismatched_payload = result.rework_ticket_payload.model_copy(
        update={"allowed_write_set": ("10-project/other/**",)}
    )

    with pytest.raises(_VERIFY_ERRORS, match="allowed_write_set"):
        ReworkTicketGenerationResult(
            plan=result.plan,
            rework_ticket_payload=mismatched_payload,
            original_ticket_check_snapshot=result.original_ticket_check_snapshot,
            original_ticket_reworked_payload=result.original_ticket_reworked_payload,
        )


def test_rework_ticket_id_must_be_deterministic() -> None:
    first = _generate()
    second = _generate()

    assert first.plan.rework_ticket_ref == second.plan.rework_ticket_ref
    assert first.rework_ticket_payload.ticket_id == second.rework_ticket_payload.ticket_id


def test_rework_input_rejects_force_ready_override() -> None:
    with pytest.raises(_VERIFY_ERRORS):
        ReworkTicketGenerationInput(
            original_ticket=_ticket_node(),
            checker_verdict=_verdict(),
            generated_at=_GENERATED_AT,
            force_ready=True,
        )


def test_rework_input_rejects_completion_snapshot_override() -> None:
    with pytest.raises(_VERIFY_ERRORS):
        ReworkTicketGenerationInput(
            original_ticket=_ticket_node(),
            checker_verdict=_verdict(),
            generated_at=_GENERATED_AT,
            completion_snapshot={"ticket_id": "ticket.backend"},
        )


def test_rework_generator_does_not_emit_event_records() -> None:
    result = _generate()

    assert not hasattr(result, "events")
    assert not hasattr(result, "event_records")


# Happy path tests.


def test_missing_test_evidence_generates_rework_ticket_and_original_rework_payloads() -> None:
    blocker_ref = _verdict().blockers[0].blocker_id
    assert blocker_ref is not None

    result = _generate()

    plan = result.plan
    assert plan.original_ticket_ref == TicketId(value="ticket.backend")
    assert plan.rework_ticket_ref != TicketId(value="ticket.backend")
    assert plan.checker_verdict_ref == _verdict().checker_verdict_id
    assert plan.final_evidence_table_ref == FinalEvidenceTableRef(
        value="final-evidence-table.contract.acceptance.backend"
    )
    assert plan.work_product_ref == WorkProductRef(value="work-product.backend")
    assert plan.acceptance_refs == ("AC-TESTS",)
    assert plan.source_surface_refs == ("surface.backend", "surface.tests")
    assert plan.evidence_obligations == (
        "evidence.backend-source",
        "evidence.backend-tests",
    )
    assert plan.allowed_write_set == ("10-project/backend/**", "10-project/tests/**")

    assert result.rework_ticket_payload.ticket_id == plan.rework_ticket_ref
    assert result.rework_ticket_payload.depends_on == ()
    assert result.rework_ticket_payload.acceptance_refs == ("AC-TESTS",)
    assert result.rework_ticket_payload.attempt_count == 0

    assert result.original_ticket_check_snapshot == TicketCheckSnapshot(
        ticket_id=TicketId(value="ticket.backend"),
        checker_approved=False,
        blocking_issue_refs=(blocker_ref.value,),
    )
    assert result.original_ticket_reworked_payload == TicketRefPayload(
        ticket_id=TicketId(value="ticket.backend")
    )


def test_rework_overrides_can_narrow_allowed_write_set_to_subpath() -> None:
    from boardroom_os.checker.rework import ReworkTicketOverrides

    result = _generate(
        overrides=ReworkTicketOverrides(allowed_write_set=("10-project/tests/unit/**",))
    )

    assert result.plan.allowed_write_set == ("10-project/tests/unit/**",)
    assert result.rework_ticket_payload.allowed_write_set == ("10-project/tests/unit/**",)


def test_rework_override_purpose_preserves_original_and_blocker_trace() -> None:
    from boardroom_os.checker.rework import ReworkTicketOverrides

    verdict = _verdict()
    blocker_ref = verdict.blockers[0].blocker_id
    assert blocker_ref is not None

    result = _generate(
        checker_verdict=verdict,
        overrides=ReworkTicketOverrides(purpose="Repair failing tests."),
    )

    assert result.rework_ticket_payload.purpose.startswith("Repair failing tests.")
    assert "ticket.backend" in result.rework_ticket_payload.purpose
    assert blocker_ref.value in result.rework_ticket_payload.purpose


def test_failed_evidence_generates_rework_ticket_with_failed_blocker_refs() -> None:
    result = _generate(
        checker_verdict=_verdict(
            blockers=(
                _blocker(
                    code=CheckerBlockerCode.FINAL_EVIDENCE_FAILED,
                    acceptance_ref=AcceptanceRef(value="AC-BACKEND"),
                    related_ref="final-evidence-blocker.backend",
                ),
            )
        )
    )

    assert result.plan.acceptance_refs == ("AC-BACKEND",)
    assert "final-evidence-blocker.backend" in result.rework_ticket_payload.purpose


def test_checker_manual_blocker_inherits_original_acceptance_scope() -> None:
    result = _generate(
        checker_verdict=_verdict(
            blockers=(
                _blocker(
                    code=CheckerBlockerCode.CHECKER_BLOCKER,
                    acceptance_ref=None,
                    related_ref="source-diff.backend",
                ),
            )
        )
    )

    assert result.plan.acceptance_refs == ("AC-BACKEND", "AC-TESTS")
    assert result.rework_ticket_payload.acceptance_refs == ("AC-BACKEND", "AC-TESTS")


def test_rework_ticket_inherits_original_source_surfaces_and_evidence_obligations() -> None:
    result = _generate()

    assert result.rework_ticket_payload.source_surface_refs == ("surface.backend", "surface.tests")
    assert result.rework_ticket_payload.evidence_obligations == (
        "evidence.backend-source",
        "evidence.backend-tests",
    )


def test_rework_ticket_inherits_seat_demand() -> None:
    result = _generate()

    assert result.rework_ticket_payload.seat_demand == _ticket_node().seat_demand


def test_rework_ticket_allowed_read_refs_include_verdict_table_work_product_and_blockers() -> None:
    verdict = _verdict()
    blocker_ref = verdict.blockers[0].blocker_id
    assert blocker_ref is not None
    assert verdict.checker_verdict_id is not None

    result = _generate(checker_verdict=verdict)

    assert verdict.checker_verdict_id.value in result.rework_ticket_payload.allowed_read_refs
    assert verdict.final_evidence_table_ref.value in result.rework_ticket_payload.allowed_read_refs
    assert verdict.work_product_ref.value in result.rework_ticket_payload.allowed_read_refs
    assert blocker_ref.value in result.rework_ticket_payload.allowed_read_refs
    assert all(isinstance(ref, str) for ref in result.rework_ticket_payload.allowed_read_refs)


def test_rework_allowed_read_ref_overrides_are_appended_without_removing_required_refs() -> None:
    from boardroom_os.checker.rework import ReworkTicketOverrides

    verdict = _verdict()
    blocker_ref = verdict.blockers[0].blocker_id
    assert blocker_ref is not None
    assert verdict.checker_verdict_id is not None

    result = _generate(
        checker_verdict=verdict,
        overrides=ReworkTicketOverrides(allowed_read_refs=("extra.audit.context",)),
    )

    assert result.rework_ticket_payload.allowed_read_refs == (
        "contract.acceptance.backend",
        verdict.checker_verdict_id.value,
        verdict.final_evidence_table_ref.value,
        verdict.work_product_ref.value,
        blocker_ref.value,
        "extra.audit.context",
    )


def test_rework_ticket_generation_is_deterministic() -> None:
    first = _generate()
    second = _generate()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_rework_generation_serializes_as_audit_friendly_json() -> None:
    result = _generate()
    dumped = result.model_dump(mode="json")

    assert dumped["plan"]["original_ticket_ref"] == {"value": "ticket.backend"}
    assert dumped["rework_ticket_payload"]["depends_on"] == []
    assert dumped["original_ticket_check_snapshot"]["checker_approved"] is False


class _Resolver(TicketReducerPayloadResolver):
    def __init__(self, *, result) -> None:
        self._result = result
        self._original = _ticket_node()

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        if payload_ref.value == "payload:original-created":
            return TicketCreatedPayload(**self._original.model_dump(exclude={"status"}))
        if payload_ref.value == "payload:rework-created":
            return self._result.rework_ticket_payload
        raise KeyError(payload_ref.value)

    def resolve_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        if payload_ref.value == "payload:original-reworked":
            return self._result.original_ticket_reworked_payload
        raise KeyError(payload_ref.value)

    def resolve_work_product_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        raise KeyError(payload_ref.value)

    def resolve_ticket_check(self, payload_ref: EventPayloadRef) -> TicketCheckSnapshot:
        if payload_ref.value == "payload:original-check":
            return self._result.original_ticket_check_snapshot
        raise KeyError(payload_ref.value)

    def resolve_ticket_completion(self, payload_ref: EventPayloadRef) -> TicketCompletionSnapshot:
        raise KeyError(payload_ref.value)


def _event(event_type: EventType, payload_ref: str, graph_version: int) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=f"evt.{graph_version}.{event_type.value}"),
        event_type=event_type,
        project_ref=ProjectRef(value="project.rework"),
        actor_ref=ActorRef(value="seat-checker"),
        timestamp=datetime(2026, 5, 21, 15, graph_version, tzinfo=UTC),
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def test_rework_payloads_make_original_ticket_blocked_and_rework_ticket_ready_through_ticket_reducer() -> None:
    result = _generate()
    graph = TicketReducer(_Resolver(result=result)).reduce(
        (
            _event(EventType.TICKET_CREATED, "payload:original-created", 1),
            _event(EventType.TICKET_CHECKED, "payload:original-check", 2),
            _event(EventType.TICKET_REWORKED, "payload:original-reworked", 3),
            _event(EventType.TICKET_CREATED, "payload:rework-created", 4),
        )
    )

    assert graph.nodes[TicketId(value="ticket.backend")].status is TicketStatus.BLOCKED
    assert graph.nodes[result.plan.rework_ticket_ref].status is TicketStatus.READY
    assert result.plan.rework_ticket_ref in graph.ready_queue
    assert result.plan.rework_ticket_ref not in graph.blocked_by


def test_checker_package_exports_rework_generator() -> None:
    from boardroom_os.checker import ReworkTicketGenerator as ExportedGenerator

    assert ExportedGenerator is ReworkTicketGenerator
