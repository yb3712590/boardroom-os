# V2-050C FinalEvidenceTable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-050C FinalEvidenceTable（最终证据表） so active AcceptanceContract（活跃验收合同） blocking criteria（阻塞验收项） are summarized into fail-closed `satisfied / missing / failed` evidence rows.

**Architecture:** Add one focused module, `src/boardroom_os/evidence/table.py`, containing table value objects, row invariants, blocker models, typed input, and a builder that aggregates existing VerifiedEvidence（已验证证据） without re-verifying claims. Keep V2-050C strictly as aggregation: it does not consume EvidenceClaim（证据声明）、EvidenceVerificationResult（证据验证结果） or notes（备注）, and callers must convert verifier blockers into FinalEvidenceBlocker（最终证据阻断项） before calling the builder.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 contracts/evidence models.

---

## File Structure

- Create `src/boardroom_os/evidence/table.py`
  - Own V2-050C table models and builder logic.
  - Do not modify EvidenceVerifier（证据验证器） behavior.
  - Do not add notes（备注） fields.
- Modify `src/boardroom_os/evidence/__init__.py`
  - Export table public types after implementation.
- Create `tests/negative/test_missing_acceptance_map_blocks_closeout.py`
  - Negative/fail-closed tests first.
- Create `tests/evidence/test_final_evidence_table.py`
  - Happy-path, incomplete table, audit JSON, and deterministic ID tests.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add negative tests for table boundaries

**Files:**
- Create: `tests/negative/test_missing_acceptance_map_blocks_closeout.py`
- No production code yet.

- [ ] **Step 1: Write the failing negative test file**

Create `tests/negative/test_missing_acceptance_map_blocks_closeout.py` with this content:

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
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
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
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType

_VERIFY_ERRORS = (ValueError, ValidationError)
_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_GENERATED_AT = datetime(2026, 5, 21, 9, 30, tzinfo=UTC)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _criterion(
    acceptance_ref: str = "AC-BACKEND",
    *,
    blocking: bool = True,
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement=f"{acceptance_ref} must have verified evidence.",
        evidence_required=(EvidenceRequirement(value="verified evidence"),),
        blocking=blocking,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="aggregate verified evidence"),
    )


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.final-evidence"),
        source_type="natural_language",
        content_ref=ContractId(value="content.final-evidence"),
        received_at=datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.final-evidence"),
        board_directive_ref=ContractId(value="directive.final-evidence"),
        project_goal="Aggregate verified evidence into a final evidence table.",
        delivery_type="generated_project_package",
        non_goals=("Do not verify raw claims in the table builder.",),
        constraints=("Final evidence table must fail closed.",),
        risks=("Missing evidence must not reach closeout.",),
        success_summary="Every blocking criterion has verified evidence.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    *,
    status: ContractStatus | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="contract.acceptance.final-evidence"),
        project_charter_ref=ContractId(value="project.charter.final-evidence"),
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
        verified_at=datetime(2026, 5, 21, 9, 10, tzinfo=UTC),
    )


def _blocker(
    acceptance_ref: str = "AC-BACKEND",
    *,
    related_ref: str = "evidence-blocker.backend",
):
    from boardroom_os.evidence.table import (
        FinalEvidenceBlocker,
        FinalEvidenceBlockerCode,
    )

    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Verified evidence failed before final aggregation.",
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        related_ref=related_ref,
        source="evidence_verifier",
    )


def _build_table(**overrides: object):
    from boardroom_os.evidence.table import FinalEvidenceTableBuilder, FinalEvidenceTableInput

    fields = {
        "active_acceptance_contract": _acceptance_contract(),
        "verified_evidence": (_verified_evidence(),),
        "failed_blockers": (),
        "generated_at": _GENERATED_AT,
    }
    fields.update(overrides)
    return FinalEvidenceTableBuilder().build(FinalEvidenceTableInput(**fields))


def test_final_evidence_table_rejects_inactive_acceptance_contract() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="active"):
        _build_table(active_acceptance_contract=_acceptance_contract(status=ContractStatus.draft()))


def test_final_evidence_table_rejects_empty_acceptance_map() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance map|blocking"):
        _build_table(
            active_acceptance_contract=_acceptance_contract(
                criteria=(_criterion("AC-OPTIONAL", blocking=False),)
            )
        )


def test_final_evidence_table_marks_blocking_criterion_missing() -> None:
    table = _build_table(verified_evidence=())

    assert table.complete is False
    assert len(table.rows) == 1
    assert table.rows[0].status.value == "missing"
    assert table.rows[0].verified_evidence_refs == ()
    assert table.rows[0].blockers == ()


def test_final_evidence_table_rejects_unknown_verified_evidence_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="unknown acceptance_ref"):
        _build_table(
            verified_evidence=(
                _verified_evidence(acceptance_refs=(AcceptanceRef(value="AC-UNKNOWN"),)),
            )
        )


def test_final_evidence_table_rejects_unknown_failed_blocker_acceptance_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="failed blocker acceptance_ref"):
        _build_table(failed_blockers=(_blocker("AC-UNKNOWN"),))


def test_final_evidence_table_rejects_notes_input() -> None:
    from boardroom_os.evidence.table import FinalEvidenceTableInput

    with pytest.raises(_VERIFY_ERRORS, match="notes|extra"):
        FinalEvidenceTableInput(
            active_acceptance_contract=_acceptance_contract(),
            verified_evidence=(_verified_evidence(),),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
            notes=("human accepted risk",),
        )


def test_verified_evidence_cannot_clear_failed_evidence_blocker() -> None:
    table = _build_table(failed_blockers=(_blocker(),))

    assert table.complete is False
    assert table.rows[0].status.value == "failed"
    assert tuple(ref.value for ref in table.rows[0].verified_evidence_refs) == (
        "verified-evidence.backend",
    )
    assert table.rows[0].blockers == (_blocker(),)


def test_complete_table_cannot_contain_missing_rows() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.MISSING,
        verified_evidence_refs=(),
        blockers=(),
    )
    with pytest.raises(_VERIFY_ERRORS, match="complete"):
        FinalEvidenceTable(
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row,),
            complete=True,
        )


def test_complete_table_cannot_contain_failed_rows() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.FAILED,
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        blockers=(_blocker(),),
    )
    with pytest.raises(_VERIFY_ERRORS, match="complete"):
        FinalEvidenceTable(
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row,),
            complete=True,
        )


def test_final_evidence_row_rejects_satisfied_without_verified_evidence_refs() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus

    with pytest.raises(_VERIFY_ERRORS, match="satisfied"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.SATISFIED,
            verified_evidence_refs=(),
            blockers=(),
        )


def test_final_evidence_row_rejects_satisfied_with_blockers() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus

    with pytest.raises(_VERIFY_ERRORS, match="satisfied"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.SATISFIED,
            verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
            blockers=(_blocker(),),
        )


def test_final_evidence_row_rejects_failed_without_blockers() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus

    with pytest.raises(_VERIFY_ERRORS, match="failed"):
        FinalEvidenceRow(
            acceptance_ref=_acceptance_ref(),
            statement="AC-BACKEND must have verified evidence.",
            status=FinalEvidenceStatus.FAILED,
            verified_evidence_refs=(),
            blockers=(),
        )


def test_final_evidence_table_rejects_duplicate_acceptance_rows() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.SATISFIED,
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        blockers=(),
    )
    with pytest.raises(_VERIFY_ERRORS, match="unique"):
        FinalEvidenceTable(
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row, row),
            complete=True,
        )


def test_final_evidence_table_rejects_claim_dict_as_verified_evidence() -> None:
    from boardroom_os.evidence.table import FinalEvidenceTableInput

    with pytest.raises(_VERIFY_ERRORS, match="VerifiedEvidence"):
        FinalEvidenceTableInput(
            active_acceptance_contract=_acceptance_contract(),
            verified_evidence=(
                {"evidence_claim_id": {"value": "claim.fake"}},
            ),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
        )


def test_final_evidence_table_rejects_verification_result_input() -> None:
    from boardroom_os.evidence.table import FinalEvidenceTableInput

    blocker = EvidenceVerificationBlocker(
        code=EvidenceVerificationBlockerCode.MISSING_ARTIFACT,
        message="claim artifact_ref is missing from artifact manifest",
        related_ref="artifact.missing",
    )
    with pytest.raises(_VERIFY_ERRORS, match="VerifiedEvidence"):
        FinalEvidenceTableInput(
            active_acceptance_contract=_acceptance_contract(),
            verified_evidence=(EvidenceVerificationResult(blockers=(blocker,)),),
            failed_blockers=(),
            generated_at=_GENERATED_AT,
        )


def test_final_evidence_table_rejects_non_deterministic_table_id() -> None:
    from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable, FinalEvidenceTableRef

    row = FinalEvidenceRow(
        acceptance_ref=_acceptance_ref(),
        statement="AC-BACKEND must have verified evidence.",
        status=FinalEvidenceStatus.SATISFIED,
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        blockers=(),
    )
    with pytest.raises(_VERIFY_ERRORS, match="final-evidence-table"):
        FinalEvidenceTable(
            final_evidence_table_id=FinalEvidenceTableRef(value="final-evidence-table.custom"),
            acceptance_contract_ref=ContractId(value="contract.acceptance.final-evidence"),
            generated_at=_GENERATED_AT,
            rows=(row,),
            complete=True,
        )
```

- [ ] **Step 2: Run the negative tests to verify RED**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.evidence.table'`.

- [ ] **Step 3: Commit the negative tests only if this task is run manually**

Do not commit unless the user explicitly asks for commits. If committing is requested, use:

```bash
git add tests/negative/test_missing_acceptance_map_blocks_closeout.py
git commit -m "test(evidence): 添加最终证据表负例"
```

---

### Task 2: Implement FinalEvidenceTable models and builder

**Files:**
- Create: `src/boardroom_os/evidence/table.py`
- Modify: `src/boardroom_os/evidence/__init__.py`
- Test: `tests/negative/test_missing_acceptance_map_blocks_closeout.py`

- [ ] **Step 1: Implement table models and builder**

Create `src/boardroom_os/evidence/table.py` with this content:

```python
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
        if self.status is FinalEvidenceStatus.SATISFIED:
            if not self.verified_evidence_refs:
                raise ValueError("satisfied row requires verified_evidence_refs")
            if self.blockers:
                raise ValueError("satisfied row must not include blockers")
        if self.status is FinalEvidenceStatus.MISSING:
            if self.verified_evidence_refs or self.blockers:
                raise ValueError("missing row must not include evidence refs or blockers")
        if self.status is FinalEvidenceStatus.FAILED:
            if not self.blockers:
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
            raise ValueError("final_evidence_table_id must be final-evidence-table.<acceptance_contract_ref>")

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
                    f"failed blocker acceptance_ref is not active blocking: {blocker.acceptance_ref.value}"
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
```

- [ ] **Step 2: Export table symbols**

Modify `src/boardroom_os/evidence/__init__.py` by adding this import block after the verifier imports:

```python
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableError,
    FinalEvidenceTableInput,
    FinalEvidenceTableRef,
)
```

Then add these names to `__all__`:

```python
    "FinalEvidenceBlocker",
    "FinalEvidenceBlockerCode",
    "FinalEvidenceRow",
    "FinalEvidenceStatus",
    "FinalEvidenceTable",
    "FinalEvidenceTableBuilder",
    "FinalEvidenceTableError",
    "FinalEvidenceTableInput",
    "FinalEvidenceTableRef",
```

- [ ] **Step 3: Run negative tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
```

Expected: PASS for all negative tests.

- [ ] **Step 4: Commit only if requested**

Do not commit unless the user explicitly asks for commits. If committing is requested, use:

```bash
git add src/boardroom_os/evidence/table.py src/boardroom_os/evidence/__init__.py tests/negative/test_missing_acceptance_map_blocks_closeout.py
git commit -m "feat(evidence): 实现最终证据表门禁"
```

---

### Task 3: Add happy-path and serialization tests

**Files:**
- Create: `tests/evidence/test_final_evidence_table.py`
- Modify if needed: `src/boardroom_os/evidence/table.py`

- [ ] **Step 1: Write happy-path tests**

Create `tests/evidence/test_final_evidence_table.py` with this content:

```python
from __future__ import annotations

from datetime import UTC, datetime

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
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceStatus,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
    FinalEvidenceTableRef,
)
from boardroom_os.evidence.verifier import (
    ArtifactSha256,
    VerifiedArtifact,
    VerifiedEvidence,
    VerifiedEvidenceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose

_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_GENERATED_AT = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)


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
        board_directive_id=ContractId(value="directive.final-evidence"),
        source_type="natural_language",
        content_ref=ContractId(value="content.final-evidence"),
        received_at=datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.final-evidence"),
        board_directive_ref=ContractId(value="directive.final-evidence"),
        project_goal="Aggregate verified evidence into a final evidence table.",
        delivery_type="generated_project_package",
        non_goals=("Do not verify raw claims in the table builder.",),
        constraints=("Final evidence table must fail closed.",),
        risks=("Missing evidence must not reach closeout.",),
        success_summary="Every blocking criterion has verified evidence.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="contract.acceptance.final-evidence"),
        project_charter_ref=ContractId(value="project.charter.final-evidence"),
        status={"value": "active"},
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
        verified_at=datetime(2026, 5, 21, 9, 45, tzinfo=UTC),
    )


def _blocker(acceptance_ref: str = "AC-BACKEND") -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Verifier produced a blocker for this acceptance ref.",
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        related_ref="evidence-blocker.backend",
        source="evidence_verifier",
    )


def _build_table(
    *,
    contract: AcceptanceContract | None = None,
    verified_evidence: tuple[VerifiedEvidence, ...] | None = None,
    failed_blockers: tuple[FinalEvidenceBlocker, ...] = (),
):
    return FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=contract or _acceptance_contract(),
            verified_evidence=verified_evidence if verified_evidence is not None else (_verified_evidence(),),
            failed_blockers=failed_blockers,
            generated_at=_GENERATED_AT,
        )
    )


def test_single_blocking_criterion_is_satisfied_by_verified_evidence() -> None:
    table = _build_table()

    assert table.complete is True
    assert table.final_evidence_table_id == FinalEvidenceTableRef(
        value="final-evidence-table.contract.acceptance.final-evidence"
    )
    assert table.rows[0].acceptance_ref == _acceptance_ref()
    assert table.rows[0].status is FinalEvidenceStatus.SATISFIED
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend"),
    )
    assert table.rows[0].blockers == ()


def test_multiple_blocking_criteria_are_all_satisfied() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-FRONTEND", statement="Frontend has verified evidence."),
            _criterion("AC-COMMAND", statement="Commands have verified evidence."),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend",
                acceptance_refs=(_acceptance_ref("AC-BACKEND"),),
            ),
            _verified_evidence(
                verified_evidence_id="verified-evidence.frontend",
                acceptance_refs=(_acceptance_ref("AC-FRONTEND"),),
            ),
            _verified_evidence(
                verified_evidence_id="verified-evidence.command",
                acceptance_refs=(_acceptance_ref("AC-COMMAND"),),
            ),
        ),
    )

    assert table.complete is True
    assert tuple(row.acceptance_ref.value for row in table.rows) == (
        "AC-BACKEND",
        "AC-FRONTEND",
        "AC-COMMAND",
    )
    assert all(row.status is FinalEvidenceStatus.SATISFIED for row in table.rows)


def test_verified_evidence_can_cover_multiple_acceptance_refs() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-COMMAND", statement="Commands have verified evidence."),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(
                verified_evidence_id="verified-evidence.backend-and-command",
                acceptance_refs=(
                    _acceptance_ref("AC-BACKEND"),
                    _acceptance_ref("AC-COMMAND"),
                ),
            ),
        ),
    )

    assert table.complete is True
    assert tuple(row.verified_evidence_refs for row in table.rows) == (
        (VerifiedEvidenceRef(value="verified-evidence.backend-and-command"),),
        (VerifiedEvidenceRef(value="verified-evidence.backend-and-command"),),
    )


def test_missing_criterion_produces_incomplete_table() -> None:
    contract = _acceptance_contract(
        criteria=(
            _criterion("AC-BACKEND"),
            _criterion("AC-FRONTEND", statement="Frontend has verified evidence."),
        )
    )
    table = _build_table(
        contract=contract,
        verified_evidence=(
            _verified_evidence(acceptance_refs=(_acceptance_ref("AC-BACKEND"),)),
        ),
    )

    assert table.complete is False
    statuses = {row.acceptance_ref.value: row.status for row in table.rows}
    assert statuses == {
        "AC-BACKEND": FinalEvidenceStatus.SATISFIED,
        "AC-FRONTEND": FinalEvidenceStatus.MISSING,
    }


def test_failed_evidence_produces_incomplete_table() -> None:
    table = _build_table(verified_evidence=(), failed_blockers=(_blocker(),))

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.FAILED
    assert table.rows[0].blockers == (_blocker(),)


def test_verified_evidence_and_failed_blocker_preserve_audit_refs() -> None:
    table = _build_table(failed_blockers=(_blocker(),))

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.FAILED
    assert table.rows[0].verified_evidence_refs == (
        VerifiedEvidenceRef(value="verified-evidence.backend"),
    )
    assert table.rows[0].blockers == (_blocker(),)


def test_final_evidence_table_serializes_as_audit_friendly_json() -> None:
    table = _build_table()

    assert table.model_dump(mode="json") == {
        "version": 1,
        "final_evidence_table_id": {
            "value": "final-evidence-table.contract.acceptance.final-evidence"
        },
        "acceptance_contract_ref": {"value": "contract.acceptance.final-evidence"},
        "generated_at": "2026-05-21T10:00:00Z",
        "rows": [
            {
                "acceptance_ref": {"value": "AC-BACKEND"},
                "statement": "AC-BACKEND must have verified evidence.",
                "status": "satisfied",
                "verified_evidence_refs": [{"value": "verified-evidence.backend"}],
                "blockers": [],
            }
        ],
        "complete": True,
    }


def test_complete_is_derived_from_rows() -> None:
    table = _build_table(verified_evidence=())

    assert table.complete is False
    assert table.rows[0].status is FinalEvidenceStatus.MISSING


def test_final_evidence_table_uses_deterministic_contract_id() -> None:
    table = _build_table()

    assert table.final_evidence_table_id.value == (
        "final-evidence-table.contract.acceptance.final-evidence"
    )
```

- [ ] **Step 2: Run happy-path tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py -q
```

Expected: PASS.

- [ ] **Step 3: Run targeted evidence table suite**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_missing_acceptance_map_blocks_closeout.py tests/evidence/test_final_evidence_table.py -q
```

Expected: PASS.

- [ ] **Step 4: Fix only V2-050C issues if tests fail**

If a failure appears, modify only:

- `src/boardroom_os/evidence/table.py`
- `tests/negative/test_missing_acceptance_map_blocks_closeout.py`
- `tests/evidence/test_final_evidence_table.py`

Do not change EvidenceVerifier（证据验证器） or AcceptanceContract（验收合同） semantics.

---

### Task 4: Run integration regression and update documentation

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Run targeted regression**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py tests/evidence/test_final_evidence_table.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full relevant suite**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

Expected: PASS.

- [ ] **Step 3: Update `doc/04-implementation/backlog.md`**

Make these exact semantic changes after tests pass:

1. Top TL;DR current package from `V2-050C` to `V2-050D`.
2. Top TL;DR current focus from FinalEvidenceTable（最终证据表） to CheckerVerdict（检查结论）.
3. Progress table Phase 5 from `3 / 7` to `4 / 7`.
4. Progress table total from `31 / 53` to `32 / 53`.
5. V2-050C status from its current pending value to `DONE`.
6. Add completion evidence under V2-050C listing:
   - `src/boardroom_os/evidence/table.py`
   - `tests/evidence/test_final_evidence_table.py`
   - `tests/negative/test_missing_acceptance_map_blocks_closeout.py`
   - exact verification commands and pass counts from Steps 1-2.

Use this completion evidence paragraph shape:

```markdown
- 完成证据：2026-05-21 新增 FinalEvidenceTable（最终证据表）、FinalEvidenceRow（最终证据行）、FinalEvidenceBlocker（最终证据阻断项）和 FinalEvidenceTableBuilder（最终证据表构建器）；负例证明 inactive contract、空 acceptance map、missing blocking criterion、未知 acceptance_ref、notes 输入、EvidenceClaim / EvidenceVerificationResult 误入、非确定性 table id、satisfied/failed/complete 不变量破坏均 fail closed；正例证明单个与多个 blocking criteria 可由 VerifiedEvidence 覆盖，单条 VerifiedEvidence 可覆盖多个 acceptance_ref，missing/failed row 使 table incomplete，failed blocker 不能被 VerifiedEvidence 覆盖，table 可审计 JSON 序列化且使用确定性 id。验证命令：`...`。
```

- [ ] **Step 4: Update `doc/04-implementation/acceptance-criteria.md`**

Make these exact semantic changes:

1. In Phase 5 checklist, check AC-V2-EVIDENCE-003.
2. Keep AC-V2-CHECKER-001 unchecked.
3. Keep AC-V2-CHECKER-002 unchecked unless V2-050D is also completed; V2-050C only proves the table layer has no notes field.
4. Update `V2-050A ~ V2-050F 七个工作包全部 DONE（含 V2-050A1；当前 3/7）` to `当前 4/7`.
5. Do not check Phase 5 prerequisites.

- [ ] **Step 5: Update `doc/05-project-log/2026-05.md`**

Append a `2026-05-21 — V2-050C FinalEvidenceTable（最终证据表）` entry with:

- key files
- negative tests
- happy tests
- exact verification commands and pass counts from Steps 1-2
- boundary note: V2-050C does not consume notes（备注） or EvidenceVerificationResult（证据验证结果）.

- [ ] **Step 6: Update `doc/04-implementation/INDEX.md`**

Add this row under the V2-050C spec row:

```markdown
| `v2-050c-final-evidence-table-implementation-plan.md` | V2-050C FinalEvidenceTable（最终证据表）实施计划 |
```

- [ ] **Step 7: Review docs diff**

Run:

```bash
git diff -- doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-05.md doc/04-implementation/INDEX.md
```

Expected: only V2-050C completion protocol updates and the implementation plan index row.

---

### Task 5: Final verification and completion review

**Files:**
- All changed files from Tasks 1-4.

- [ ] **Step 1: Run required V2-050C verification commands again**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py tests/evidence/test_final_evidence_table.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

Expected: all PASS.

- [ ] **Step 2: Run git status**

Run:

```bash
git status --short
```

Expected: changed files are limited to V2-050C code/tests/docs and the previously reviewed V2-050C spec/index updates.

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
- next current work package should be V2-050D

Do not claim success unless Step 1 commands passed.

---

## Self-Review Checklist

- Spec coverage:
  - Active AcceptanceContract（活跃验收合同） blocking criteria coverage: Tasks 1-3.
  - `satisfied / missing / failed` statuses: Tasks 1-3.
  - Empty acceptance map / no blocking criteria failure: Task 1 and Task 2.
  - Unknown acceptance refs fail closed: Task 1 and Task 2.
  - EvidenceClaim（证据声明） and EvidenceVerificationResult（证据验证结果） rejected: Task 1 and Task 2.
  - Notes（备注） rejected: Task 1 and Task 2.
  - Failed blockers override VerifiedEvidence（已验证证据）: Task 1 and Task 3.
  - Deterministic `final-evidence-table.<contract_id>` id: Task 1, Task 2, Task 3.
  - Audit-friendly JSON: Task 3.
  - Documentation completion protocol: Task 4.
- Placeholder scan: no unfinished-marker text or placeholder instruction remains.
- Type consistency:
  - `FinalEvidenceStatus.SATISFIED/MISSING/FAILED` is used consistently.
  - `FinalEvidenceBlockerCode.FAILED_EVIDENCE` is used consistently.
  - `FinalEvidenceTableBuilder().build(FinalEvidenceTableInput(...))` is the only builder entrypoint.
  - `FinalEvidenceTable.complete` is derived from rows.
  - No `FinalEvidenceNote` type is introduced.
