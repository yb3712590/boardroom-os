# V2-050D CheckerVerdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-050D CheckerVerdict（检查结论） so checker review（检查者审查） blocks incomplete evidence, preserves non-blocking notes, and cannot replace EvidenceVerifier（证据验证器） or FinalEvidenceTable（最终证据表）.

**Architecture:** Add a focused `boardroom_os.checker` package with one model module (`verdict.py`) and one service module (`checker.py`). The model layer owns status/notes/blocker invariants and deterministic IDs; the service layer consumes typed WorkProduct（工作产物）、SourceDiffRef（源码差异引用）、active AcceptanceContract（活跃验收合同） and FinalEvidenceTable（最终证据表）, deriving rework blockers from missing/failed evidence rows without accepting raw evidence inputs.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 contracts/evidence/execution models.

---

## File Structure

- Create `src/boardroom_os/checker/__init__.py`
  - Export the V2-050D public checker API.
- Create `src/boardroom_os/checker/verdict.py`
  - Own CheckerVerdict（检查结论）, CheckerNote（检查备注）, CheckerVerdictBlocker（检查结论阻断项）, status enums, ref value objects, and model invariants.
- Create `src/boardroom_os/checker/checker.py`
  - Own CheckerServiceInput（检查服务输入） and CheckerService.review（检查服务审查函数）.
- Create `tests/evidence/test_checker_verdict.py`
  - Contains negative tests first, then happy-path tests.
- Modify `doc/04-implementation/backlog.md`
  - Only after verification passes: mark V2-050D DONE, move current package to V2-050E, update counts and completion evidence.
- Modify `doc/04-implementation/acceptance-criteria.md`
  - Only after verification passes: check AC-V2-CHECKER-001 and AC-V2-CHECKER-002, update Phase 5 completion count to 5/7.
- Modify `doc/05-project-log/2026-05.md`
  - Only after verification passes: append V2-050D completion entry.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.

Do not modify EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、WorkProduct（工作产物）、TicketReducer（任务状态归约器）, RuntimeExecutor（运行时执行器） or EventType（事件类型） in this work package.

---

### Task 1: Add negative tests for checker boundaries

**Files:**
- Create: `tests/evidence/test_checker_verdict.py`
- No production code yet.

- [ ] **Step 1: Write the failing negative test file**

Create `tests/evidence/test_checker_verdict.py` with the following content:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import (
    ArtifactSha256,
    EvidenceVerificationBlocker,
    EvidenceVerificationBlockerCode,
    EvidenceVerificationResult,
    VerifiedArtifact,
    VerifiedEvidence,
    VerifiedEvidenceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.execution.work_product import (
    WorkProduct,
    WorkProductArtifactRef,
    WorkProductClaimDraftRef,
    WorkProductRef,
)
from boardroom_os.graph.ticket import TicketId

_VERIFY_ERRORS = (ValueError, ValidationError)
_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_CHECKED_AT = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
_GENERATED_AT = datetime(2026, 5, 21, 11, 30, tzinfo=UTC)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _criterion(
    acceptance_ref: str = "AC-BACKEND",
    *,
    statement: str | None = None,
    blocking: bool = True,
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement=statement or f"{acceptance_ref} must have verified evidence.",
        evidence_required=(EvidenceRequirement(value="verified evidence"),),
        blocking=blocking,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="aggregate verified evidence"),
    )


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.checker-verdict"),
        source_type="natural_language",
        content_ref=ContractId(value="content.checker-verdict"),
        received_at=datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.checker-verdict"),
        board_directive_ref=ContractId(value="directive.checker-verdict"),
        project_goal="Review worker output without replacing evidence verification.",
        delivery_type="generated_project_package",
        non_goals=("Do not generate rework tickets in V2-050D.",),
        constraints=("Checker notes must not clear blockers.",),
        risks=("Checker could accidentally become another verifier.",),
        success_summary="Checker emits an auditable verdict from existing evidence facts.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    *,
    status: ContractStatus | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="contract.acceptance.checker-verdict"),
        project_charter_ref=ContractId(value="project.charter.checker-verdict"),
        status=status or ContractStatus.active(),
        criteria=criteria or (_criterion(),),
    )


def _verified_evidence(
    *,
    verified_evidence_id: str = "verified-evidence.backend",
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=verified_evidence_id),
        evidence_claim_ref=EvidenceClaimRef(value=f"claim.{verified_evidence_id}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence.backend"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.backend",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        acceptance_refs=acceptance_refs or (_acceptance_ref(),),
        source_surface_refs=(_source_surface_ref(),),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value="artifact.backend"),
                sha256=ArtifactSha256(value=_VALID_SHA256),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
                source_ref="work-product.backend",
                artifact_kind="source_patch",
            ),
        ),
        verified_at=datetime(2026, 5, 21, 11, 0, tzinfo=UTC),
    )


def _work_product(**overrides: object) -> WorkProduct:
    fields: dict[str, object] = {
        "work_product_id": WorkProductRef(value="work-product.backend"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.backend"),
        "ticket_ref": TicketId(value="ticket.backend"),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
        "artifact_refs": (
            WorkProductArtifactRef(value="artifact.backend.raw"),
            WorkProductArtifactRef(value="artifact.backend.parsed"),
        ),
        "claim_refs": (WorkProductClaimDraftRef(value="claim-draft.backend"),),
        "summary": "Backend work product.",
    }
    fields.update(overrides)
    return WorkProduct(**fields)


def _final_evidence_blocker(acceptance_ref: str = "AC-BACKEND") -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Evidence verification failed.",
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        related_ref="evidence-blocker.backend",
        source="evidence_verifier",
    )


def _final_evidence_table(
    *,
    contract: AcceptanceContract | None = None,
    verified_evidence: tuple[VerifiedEvidence, ...] | None = None,
    failed_blockers: tuple[FinalEvidenceBlocker, ...] = (),
) -> FinalEvidenceTable:
    return FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=contract or _acceptance_contract(),
            verified_evidence=verified_evidence
            if verified_evidence is not None
            else (_verified_evidence(),),
            failed_blockers=failed_blockers,
            generated_at=_GENERATED_AT,
        )
    )


def _missing_final_evidence_table() -> FinalEvidenceTable:
    return _final_evidence_table(verified_evidence=())


def _failed_final_evidence_table() -> FinalEvidenceTable:
    return _final_evidence_table(verified_evidence=(), failed_blockers=(_final_evidence_blocker(),))


def _checker_note():
    from boardroom_os.checker.verdict import CheckerNote

    return CheckerNote(
        message="Implementation is acceptable; consider renaming a local variable later.",
        related_ref="work-product.backend",
    )


def _checker_blocker():
    from boardroom_os.checker.verdict import CheckerBlockerCode, CheckerVerdictBlocker

    return CheckerVerdictBlocker(
        code=CheckerBlockerCode.CHECKER_BLOCKER,
        message="Source diff does not match the work product summary.",
        acceptance_ref=None,
        related_ref="source-diff.backend",
        source="checker_manual_review",
    )


def _service_input(**overrides: object):
    from boardroom_os.checker.checker import CheckerServiceInput
    from boardroom_os.checker.verdict import SourceDiffRef

    fields = {
        "ticket_ref": TicketId(value="ticket.backend"),
        "work_product": _work_product(),
        "source_diff_ref": SourceDiffRef(value="source-diff.backend"),
        "active_acceptance_contract": _acceptance_contract(),
        "final_evidence_table": _final_evidence_table(),
        "notes": (),
        "checker_blockers": (),
        "checked_at": _CHECKED_AT,
    }
    fields.update(overrides)
    return CheckerServiceInput(**fields)


def _review(**overrides: object):
    from boardroom_os.checker.checker import CheckerService

    return CheckerService().review(_service_input(**overrides))


# Negative tests first.

def test_checker_service_rejects_inactive_acceptance_contract() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="active"):
        _service_input(active_acceptance_contract=_acceptance_contract(status=ContractStatus.draft()))


def test_checker_service_rejects_contract_mismatch() -> None:
    other_contract = _acceptance_contract(
        criteria=(_criterion("AC-FRONTEND", statement="Frontend evidence is complete."),)
    )
    with pytest.raises(_VERIFY_ERRORS, match="contract"):
        _service_input(active_acceptance_contract=other_contract)


def test_checker_service_rejects_work_product_ticket_mismatch() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="ticket"):
        _service_input(work_product=_work_product(ticket_ref=TicketId(value="ticket.other")))


def test_checker_service_rejects_missing_source_diff_ref() -> None:
    from boardroom_os.checker.verdict import SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="empty|source_diff"):
        _service_input(source_diff_ref=SourceDiffRef(value=""))


def test_checker_service_rejects_evidence_claim_inputs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|evidence_claims"):
        _service_input(evidence_claims=("claim.fake",))


def test_checker_service_rejects_verified_evidence_inputs() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|verified_evidence"):
        _service_input(verified_evidence=(_verified_evidence(),))


def test_checker_service_rejects_verification_result_inputs() -> None:
    blocker = EvidenceVerificationBlocker(
        code=EvidenceVerificationBlockerCode.MISSING_ARTIFACT,
        message="claim artifact_ref is missing from artifact manifest",
        related_ref="artifact.missing",
    )
    with pytest.raises(_VERIFY_ERRORS, match="extra|evidence_verification_results"):
        _service_input(evidence_verification_results=(EvidenceVerificationResult(blockers=(blocker,)),))


def test_checker_service_rejects_force_approved_override() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="extra|force_approved"):
        _service_input(force_approved=True)


def test_incomplete_final_evidence_table_cannot_be_approved() -> None:
    verdict = _review(final_evidence_table=_missing_final_evidence_table())

    assert verdict.status.value == "rework_required"
    assert verdict.blockers


def test_missing_evidence_row_becomes_rework_blocker() -> None:
    verdict = _review(final_evidence_table=_missing_final_evidence_table())

    assert tuple(blocker.code.value for blocker in verdict.blockers) == ("final_evidence_missing",)
    assert verdict.blockers[0].acceptance_ref == AcceptanceRef(value="AC-BACKEND")


def test_failed_evidence_row_becomes_rework_blocker() -> None:
    verdict = _review(final_evidence_table=_failed_final_evidence_table())

    assert tuple(blocker.code.value for blocker in verdict.blockers) == ("final_evidence_failed",)
    assert verdict.blockers[0].acceptance_ref == AcceptanceRef(value="AC-BACKEND")
    assert verdict.blockers[0].related_ref == _final_evidence_blocker().blocker_id.value


def test_notes_cannot_clear_evidence_blocker() -> None:
    verdict = _review(final_evidence_table=_failed_final_evidence_table(), notes=(_checker_note(),))

    assert verdict.status.value == "rework_required"
    assert verdict.notes == (_checker_note(),)
    assert verdict.blockers


def test_checker_blocker_forces_rework_even_when_evidence_complete() -> None:
    verdict = _review(checker_blockers=(_checker_blocker(),))

    assert verdict.status.value == "rework_required"
    assert verdict.blockers == (_checker_blocker(),)


def test_approved_verdict_rejects_notes() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="approved"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(_checker_note(),),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_approved_verdict_rejects_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="approved"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(_checker_blocker(),),
            checked_at=_CHECKED_AT,
        )


def test_approved_with_notes_requires_notes() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="notes"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_approved_with_notes_rejects_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
            notes=(_checker_note(),),
            blockers=(_checker_blocker(),),
            checked_at=_CHECKED_AT,
        )


def test_rework_required_requires_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.REWORK_REQUIRED,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_escalate_requires_blockers() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="blockers"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.ESCALATE,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_checker_verdict_rejects_non_deterministic_id() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictRef, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="checker-verdict"):
        CheckerVerdict(
            checker_verdict_id=CheckerVerdictRef(value="checker-verdict.custom"),
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
        )


def test_checker_verdict_rejects_naive_checked_at() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="timezone"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(),
            checked_at=datetime(2026, 5, 21, 12, 0),
        )


def test_checker_note_rejects_override_fields() -> None:
    from boardroom_os.checker.verdict import CheckerNote

    with pytest.raises(_VERIFY_ERRORS, match="extra|override|blocking"):
        CheckerNote(
            message="Looks fine despite the blocker.",
            related_ref="work-product.backend",
            blocking=False,
            evidence_refs=("verified-evidence.fake",),
        )


def test_checker_blocker_rejects_empty_related_ref() -> None:
    from boardroom_os.checker.verdict import CheckerBlockerCode, CheckerVerdictBlocker

    with pytest.raises(_VERIFY_ERRORS, match="empty|related_ref"):
        CheckerVerdictBlocker(
            code=CheckerBlockerCode.CHECKER_BLOCKER,
            message="Blocking issue.",
            acceptance_ref=None,
            related_ref="",
            source="checker_manual_review",
        )


def test_checker_verdict_rejects_extra_evidence_refs() -> None:
    from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef

    with pytest.raises(_VERIFY_ERRORS, match="extra|evidence_refs"):
        CheckerVerdict(
            ticket_ref=TicketId(value="ticket.backend"),
            work_product_ref=WorkProductRef(value="work-product.backend"),
            source_diff_ref=SourceDiffRef(value="source-diff.backend"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.checker-verdict"),
            final_evidence_table_ref=_final_evidence_table().final_evidence_table_id,
            status=CheckerVerdictStatus.APPROVED,
            notes=(),
            blockers=(),
            checked_at=_CHECKED_AT,
            evidence_refs=("verified-evidence.fake",),
        )
```

- [ ] **Step 2: Run the negative tests to verify RED**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.checker'` or import failure for `boardroom_os.checker.checker` / `boardroom_os.checker.verdict`.

- [ ] **Step 3: Do not commit unless requested**

This repository workflow does not require commits unless the user explicitly asks. If commits are requested later, commit after each task with the repository's Chinese commit summary style.

---

### Task 2: Implement CheckerVerdict model layer

**Files:**
- Create: `src/boardroom_os/checker/__init__.py`
- Create: `src/boardroom_os/checker/verdict.py`
- Test: `tests/evidence/test_checker_verdict.py`

- [ ] **Step 1: Create the checker package exports**

Create `src/boardroom_os/checker/__init__.py` with:

```python
"""Checker-layer primitives for Boardroom OS V2."""

from boardroom_os.checker.checker import CheckerService, CheckerServiceInput
from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerBlockerRef,
    CheckerNote,
    CheckerNoteRef,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictError,
    CheckerVerdictRef,
    CheckerVerdictStatus,
    SourceDiffRef,
)

__all__ = [
    "CheckerBlockerCode",
    "CheckerBlockerRef",
    "CheckerNote",
    "CheckerNoteRef",
    "CheckerService",
    "CheckerServiceInput",
    "CheckerVerdict",
    "CheckerVerdictBlocker",
    "CheckerVerdictError",
    "CheckerVerdictRef",
    "CheckerVerdictStatus",
    "SourceDiffRef",
]
```

This import will still fail until Task 3 creates `checker.py`; keep it because the public API is defined now.

- [ ] **Step 2: Implement `verdict.py`**

Create `src/boardroom_os/checker/verdict.py` with:

```python
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
        if "note_id" not in normalized:
            related_ref = normalized.get("related_ref")
            normalized["note_id"] = CheckerNoteRef(value=f"checker-note.{related_ref}")
        return normalized

    @field_validator("message", "related_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
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
        if "blocker_id" not in normalized:
            code = normalized.get("code")
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
            related_ref = normalized.get("related_ref")
            normalized["blocker_id"] = CheckerBlockerRef(
                value=f"checker-blocker.{code_value}.{acceptance_ref_value}.{related_ref}"
            )
        return normalized

    @field_validator("message", "related_ref", "source")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
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
            raise ValueError("notes must be a tuple or list")
        if "blockers" in normalized and not isinstance(normalized["blockers"], list | tuple):
            raise ValueError("blockers must be a tuple or list")
        if (
            "checker_verdict_id" not in normalized
            and "ticket_ref" in normalized
            and "final_evidence_table_ref" in normalized
        ):
            ticket_ref = normalized["ticket_ref"]
            table_ref = normalized["final_evidence_table_ref"]
            if isinstance(ticket_ref, TicketId):
                ticket_ref_value = ticket_ref.value
            elif isinstance(ticket_ref, dict):
                ticket_ref_value = ticket_ref.get("value")
            else:
                ticket_ref_value = str(ticket_ref)
            if isinstance(table_ref, FinalEvidenceTableRef):
                table_ref_value = table_ref.value
            elif isinstance(table_ref, dict):
                table_ref_value = table_ref.get("value")
            else:
                table_ref_value = str(table_ref)
            normalized["checker_verdict_id"] = CheckerVerdictRef(
                value=f"checker-verdict.{ticket_ref_value}.{table_ref_value}"
            )
        return _normalize_ref_fields(
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

    @field_validator("checked_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
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
            raise ValueError(
                "checker_verdict_id must be checker-verdict.<ticket_ref>.<final_evidence_table_ref>"
            )

        if self.status is CheckerVerdictStatus.APPROVED:
            if self.notes:
                raise ValueError("approved verdict must not include notes")
            if self.blockers:
                raise ValueError("approved verdict must not include blockers")
        if self.status is CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES:
            if not self.notes:
                raise ValueError("approved_with_non_blocking_notes requires notes")
            if self.blockers:
                raise ValueError("approved_with_non_blocking_notes must not include blockers")
        if self.status is CheckerVerdictStatus.REWORK_REQUIRED and not self.blockers:
            raise ValueError("rework_required verdict requires blockers")
        if self.status is CheckerVerdictStatus.ESCALATE and not self.blockers:
            raise ValueError("escalate verdict requires blockers")
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
```

- [ ] **Step 3: Run model-focused tests and observe remaining service failures**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q
```

Expected: tests that import `boardroom_os.checker.checker` still fail because `checker.py` is not implemented; direct model invariant tests should no longer fail due to missing `verdict.py`.

---

### Task 3: Implement CheckerService input and review logic

**Files:**
- Create: `src/boardroom_os/checker/checker.py`
- Modify if needed: `src/boardroom_os/checker/__init__.py`
- Test: `tests/evidence/test_checker_verdict.py`

- [ ] **Step 1: Implement `checker.py`**

Create `src/boardroom_os/checker/checker.py` with:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.evidence.table import FinalEvidenceStatus, FinalEvidenceTable
from boardroom_os.execution.work_product import WorkProduct
from boardroom_os.graph.ticket import TicketId
from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerNote,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictError,
    CheckerVerdictStatus,
    SourceDiffRef,
)


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
            raise ValueError("work_product must be a WorkProduct")
        return value

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

    @field_validator("notes", mode="before")
    @classmethod
    def _require_note_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("notes must be a tuple or list")
        for item in value:
            if not isinstance(item, CheckerNote):
                raise ValueError("notes must contain CheckerNote values")
        return value

    @field_validator("checker_blockers", mode="before")
    @classmethod
    def _require_blocker_instances(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("checker_blockers must be a tuple or list")
        for item in value:
            if not isinstance(item, CheckerVerdictBlocker):
                raise ValueError("checker_blockers must contain CheckerVerdictBlocker values")
        return value

    @field_validator("checked_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_input_consistency(self) -> "CheckerServiceInput":
        if self.active_acceptance_contract.status.value != "active":
            raise CheckerVerdictError("active_acceptance_contract must be active")
        if (
            self.final_evidence_table.acceptance_contract_ref
            != self.active_acceptance_contract.acceptance_contract_id
        ):
            raise CheckerVerdictError(
                "final_evidence_table acceptance contract must match active contract"
            )
        if self.work_product.ticket_ref != self.ticket_ref:
            raise CheckerVerdictError("work_product.ticket_ref must match ticket_ref")
        return self


class CheckerService:
    def review(self, checker_input: CheckerServiceInput) -> CheckerVerdict:
        if not isinstance(checker_input, CheckerServiceInput):
            raise CheckerVerdictError("checker_input must be a CheckerServiceInput")

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
            if row.status is FinalEvidenceStatus.FAILED:
                for final_blocker in row.blockers:
                    blockers.append(
                        CheckerVerdictBlocker(
                            code=CheckerBlockerCode.FINAL_EVIDENCE_FAILED,
                            message=final_blocker.message,
                            acceptance_ref=row.acceptance_ref,
                            related_ref=final_blocker.blocker_id.value,
                            source="final_evidence_table",
                        )
                    )
        return tuple(blockers)


__all__ = ["CheckerService", "CheckerServiceInput"]
```

- [ ] **Step 2: Run checker verdict tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q
```

Expected: PASS for all negative tests currently in the file.

- [ ] **Step 3: Fix only V2-050D model/service issues if tests fail**

If a failure appears, modify only:

- `src/boardroom_os/checker/verdict.py`
- `src/boardroom_os/checker/checker.py`
- `src/boardroom_os/checker/__init__.py`
- `tests/evidence/test_checker_verdict.py`

Do not modify EvidenceVerifier（证据验证器）, FinalEvidenceTableBuilder（最终证据表构建器）, WorkProduct（工作产物）, EventType（事件类型） or reducer（状态归约器） code.

---

### Task 4: Add happy-path and audit-shape tests

**Files:**
- Modify: `tests/evidence/test_checker_verdict.py`
- Modify if needed: `src/boardroom_os/checker/verdict.py`
- Modify if needed: `src/boardroom_os/checker/checker.py`

- [ ] **Step 1: Append happy-path tests**

Append this content to `tests/evidence/test_checker_verdict.py`:

```python

# Happy path and audit-shape tests.

def test_complete_evidence_without_notes_is_approved() -> None:
    verdict = _review()

    assert verdict.status.value == "approved"
    assert verdict.notes == ()
    assert verdict.blockers == ()


def test_complete_evidence_with_notes_is_approved_with_non_blocking_notes() -> None:
    verdict = _review(notes=(_checker_note(),))

    assert verdict.status.value == "approved_with_non_blocking_notes"
    assert verdict.notes == (_checker_note(),)
    assert verdict.blockers == ()


def test_missing_evidence_returns_rework_required() -> None:
    verdict = _review(final_evidence_table=_missing_final_evidence_table())

    assert verdict.status.value == "rework_required"
    assert tuple(blocker.code.value for blocker in verdict.blockers) == (
        "final_evidence_missing",
    )


def test_failed_evidence_returns_rework_required_and_preserves_related_refs() -> None:
    verdict = _review(final_evidence_table=_failed_final_evidence_table())

    assert verdict.status.value == "rework_required"
    assert tuple(blocker.related_ref for blocker in verdict.blockers) == (
        _final_evidence_blocker().blocker_id.value,
    )


def test_checker_blocker_returns_rework_required_with_complete_evidence() -> None:
    verdict = _review(checker_blockers=(_checker_blocker(),))

    assert verdict.status.value == "rework_required"
    assert verdict.blockers == (_checker_blocker(),)


def test_checker_verdict_serializes_as_audit_friendly_json() -> None:
    verdict = _review(notes=(_checker_note(),))

    assert verdict.model_dump(mode="json") == {
        "version": 1,
        "checker_verdict_id": {
            "value": (
                "checker-verdict.ticket.backend."
                "final-evidence-table.contract.acceptance.checker-verdict"
            )
        },
        "ticket_ref": {"value": "ticket.backend"},
        "work_product_ref": {"value": "work-product.backend"},
        "source_diff_ref": {"value": "source-diff.backend"},
        "acceptance_contract_ref": {"value": "contract.acceptance.checker-verdict"},
        "final_evidence_table_ref": {
            "value": "final-evidence-table.contract.acceptance.checker-verdict"
        },
        "status": "approved_with_non_blocking_notes",
        "notes": [
            {
                "note_id": {"value": "checker-note.work-product.backend"},
                "message": "Implementation is acceptable; consider renaming a local variable later.",
                "related_ref": "work-product.backend",
            }
        ],
        "blockers": [],
        "checked_at": "2026-05-21T12:00:00Z",
    }


def test_checker_verdict_uses_deterministic_id() -> None:
    verdict = _review()

    assert verdict.checker_verdict_id.value == (
        "checker-verdict.ticket.backend."
        "final-evidence-table.contract.acceptance.checker-verdict"
    )


def test_checker_service_preserves_core_audit_refs() -> None:
    verdict = _review()

    assert verdict.ticket_ref == TicketId(value="ticket.backend")
    assert verdict.work_product_ref == WorkProductRef(value="work-product.backend")
    assert verdict.source_diff_ref.value == "source-diff.backend"
    assert verdict.acceptance_contract_ref == ContractId(value="contract.acceptance.checker-verdict")
    assert verdict.final_evidence_table_ref == _final_evidence_table().final_evidence_table_id
```

- [ ] **Step 2: Run checker verdict tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q
```

Expected: PASS for 32 tests.

- [ ] **Step 3: Run targeted evidence regression**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
```

Expected: PASS. Record the observed pass count for the project log.

---

### Task 5: Run full relevant suite and update completion docs

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Run full relevant suite**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

Expected: PASS. Record the observed pass count.

- [ ] **Step 2: Update `doc/04-implementation/backlog.md`**

Make these exact semantic changes after tests pass:

1. Top TL;DR current package from `V2-050D` to `V2-050E`.
2. Top TL;DR current focus from CheckerVerdict（检查结论） to rework ticket generation（返工任务触发）.
3. Progress table Phase 5 from `4 / 7` to `5 / 7`.
4. Progress table total from `32 / 53` to `33 / 53`.
5. V2-050D status from `TODO` to `DONE`.
6. Add completion evidence under V2-050D listing:
   - `src/boardroom_os/checker/verdict.py`
   - `src/boardroom_os/checker/checker.py`
   - `tests/evidence/test_checker_verdict.py`
   - exact verification commands and pass counts from Task 4 Step 2, Task 4 Step 3 and Task 5 Step 1.

Use this completion evidence paragraph shape:

```markdown
- 完成证据：2026-05-21 新增 CheckerVerdict（检查结论）、CheckerNote（检查备注）、CheckerVerdictBlocker（检查结论阻断项）、CheckerServiceInput（检查服务输入）和 CheckerService（检查服务）；负例证明 inactive contract、contract/table mismatch、work product ticket mismatch、缺 source diff、EvidenceClaim / VerifiedEvidence / EvidenceVerificationResult / force_approved 输入、incomplete evidence approved、notes 覆盖 blocker、approved/status 不变量、非确定性 verdict id、无时区 checked_at 和 extra evidence refs 均 fail closed；正例证明 complete FinalEvidenceTable 可 APPROVED，有非阻断 notes 可 APPROVED_WITH_NON_BLOCKING_NOTES，missing/failed evidence 或 checker blocker 会 REWORK_REQUIRED，并保留 work product / source diff / contract / evidence table 审计引用。验证命令：`...`。
```

- [ ] **Step 3: Update `doc/04-implementation/acceptance-criteria.md`**

Make these exact semantic changes:

1. In Phase 5 checklist, check AC-V2-CHECKER-001.
2. In Phase 5 checklist, check AC-V2-CHECKER-002.
3. Update `V2-050A ~ V2-050F 七个工作包全部 DONE（含 V2-050A1；当前 4/7）` to `当前 5/7`.
4. Keep Rework 闭环 unchecked.
5. Keep Completion gate 接入 reducer unchecked.
6. Do not check Phase 5 prerequisites.

- [ ] **Step 4: Update `doc/05-project-log/2026-05.md`**

Append a `2026-05-21 — V2-050D CheckerVerdict（检查结论）` entry with:

- key files
- negative tests
- happy tests
- exact verification commands and pass counts
- boundary note: Checker（检查者） consumes FinalEvidenceTable（最终证据表） only and does not accept raw EvidenceClaim（证据声明）、VerifiedEvidence（已验证证据） or EvidenceVerificationResult（证据验证结果） inputs.

- [ ] **Step 5: Update `doc/04-implementation/INDEX.md`**

Add this row under the V2-050D spec row if it is not already present:

```markdown
| `v2-050d-checker-verdict-implementation-plan.md` | V2-050D CheckerVerdict（检查结论）实施计划 |
```

- [ ] **Step 6: Review docs diff**

Run:

```bash
git diff -- doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-05.md doc/04-implementation/INDEX.md
```

Expected: only V2-050D completion protocol updates and the implementation plan index row.

---

### Task 6: Final verification and completion review

**Files:**
- All changed files from Tasks 1-5.

- [ ] **Step 1: Run required V2-050D verification commands again**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

Expected: all PASS.

- [ ] **Step 2: Run git status**

Run:

```bash
git status --short
```

Expected: changed files are limited to V2-050D code/tests/docs plus this implementation plan and prior reviewed spec/index updates.

- [ ] **Step 3: Confirm no legacy paths were read or modified**

Run:

```bash
git diff --name-only | grep -E '^(backend/app/core|doc/refactor|doc/live-report|doc/tests)' && exit 1 || true
```

Expected: no output and exit code 0.

- [ ] **Step 4: Report results**

Report:

- files changed
- verification commands with observed pass counts
- whether backlog/acceptance/project log updates were completed
- next current work package should be V2-050E

Do not claim success unless Step 1 commands passed.

---

## Self-Review Checklist

- Spec coverage:
  - Checker statuses: Tasks 2-4.
  - Notes cannot clear blockers: Tasks 1-4.
  - Incomplete FinalEvidenceTable -> REWORK_REQUIRED: Tasks 1, 3, 4.
  - Missing/failed final evidence rows -> blocker refs: Tasks 1, 3, 4.
  - Checker cannot accept EvidenceClaim / VerifiedEvidence / EvidenceVerificationResult: Tasks 1 and 3 via `extra="forbid"`.
  - Structural input errors raise CheckerVerdictError: Tasks 1 and 3.
  - ESCALATE is schema-only in service path: Tasks 1 and 3.
  - SourceDiffRef remains a ref-only NonEmptyTextValue: Tasks 1-3.
  - CheckerNote.related_ref required: Tasks 1-2.
  - Evidence-derived blockers require acceptance_ref: Tasks 1 and 3.
  - No `CHECKER_VERDICT_RECORDED` event: Task 3 explicitly avoids EventType changes.
  - Documentation completion protocol: Task 5.
- Placeholder scan: no unfinished-marker text or placeholder instruction remains.
- Type consistency:
  - `CheckerVerdictStatus.APPROVED / APPROVED_WITH_NON_BLOCKING_NOTES / REWORK_REQUIRED / ESCALATE` is used consistently.
  - `CheckerBlockerCode.FINAL_EVIDENCE_MISSING / FINAL_EVIDENCE_FAILED / CHECKER_BLOCKER` is used consistently.
  - `CheckerService().review(CheckerServiceInput(...))` is the only service entrypoint.
  - `checker_verdict_id` is deterministic from ticket ref and final evidence table ref.
  - No `SourceDiffSummary`, `escalation_reason`, or checker event type is introduced.
