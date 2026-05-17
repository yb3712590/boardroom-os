# V2-030E Fallback Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V2-030E fallback policy classification（降级策略分类） so fallback（降级） cannot satisfy implementation evidence（实施证据） while contract-declared deterministic transforms（合同声明的确定性转换） can satisfy only narrow deterministic evidence（确定性证据）.

**Architecture:** Add one focused module, `src/boardroom_os/execution/fallback.py`, containing immutable Pydantic models（Pydantic 模型）, closed enums（封闭枚举）, and one pure decision function. Reuse existing `FallbackPolicyRef`（降级策略引用）, `RequiredArtifactType`（必需产物类型）, and `AcceptanceRef`（验收引用） value objects; do not modify `ExecutionPackageCompiler`（执行包编译器） and do not introduce `EvidenceClaim`（证据声明） or `EvidenceVerifier`（证据验证器）.

**Tech Stack:** Python, Pydantic v2, pytest, existing `NonEmptyTextValue`（非空文本值对象）, `AcceptanceRef`（验收引用）, `RequiredArtifactType`（必需产物类型）, and `FallbackPolicyRef`（降级策略引用）.

---

## File Structure

- Create: `src/boardroom_os/execution/fallback.py`
  - Owns `EvidencePurpose`（证据用途）, `FallbackKind`（降级类型）, `FallbackPolicy`（降级策略）, `FallbackEvidenceRequest`（降级证据请求）, `FallbackEvidenceDecision`（降级证据判定）, and `evaluate_fallback_evidence`（降级证据判定函数）.
  - Imports `FallbackPolicyRef` from `boardroom_os.execution.package`, `RequiredArtifactType` from `boardroom_os.contracts.evidence_obligation`, and `AcceptanceRef` from `boardroom_os.contracts.types`.
  - Does not import provider（模型供应商）, work product（工作产物）, command runner（命令运行器）, or evidence verifier（证据验证器） modules.
- Modify: `src/boardroom_os/execution/__init__.py`
  - Re-export public fallback policy（降级策略） types and decision function.
- Create: `tests/negative/test_fallback_cannot_satisfy_implementation.py`
  - Proves fallback（降级） cannot satisfy implementation evidence（实施证据） and schema construction fails closed.
- Create: `tests/execution/test_fallback_policy.py`
  - Proves narrow deterministic transform（确定性转换） and tooling diagnostic（工具诊断） happy paths, plus audit-field serialization.
- Modify: `doc/05-project-log/decisions.md`
  - Add DEC-0014 documenting removal of the `TEST_ONLY_SIMULATION` failure-path exception.
- Modify after implementation: `doc/04-implementation/backlog.md`, `doc/04-implementation/acceptance-criteria.md`, `doc/05-project-log/2026-05.md`
  - Apply the work package completion protocol.

---

### Task 1: Negative fallback implementation evidence tests

**Files:**
- Create: `tests/negative/test_fallback_cannot_satisfy_implementation.py`
- Create later in Task 2: `src/boardroom_os/execution/fallback.py`

- [ ] **Step 1: Write the failing negative tests**

Create `tests/negative/test_fallback_cannot_satisfy_implementation.py` with this content:

```python
import pytest
from pydantic import ValidationError

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackEvidenceRequest,
    FallbackKind,
    FallbackPolicy,
    evaluate_fallback_evidence,
)
from boardroom_os.execution.package import FallbackPolicyRef


NON_CONTRACT_FALLBACK_KINDS = (
    FallbackKind.PROVIDER_UNAVAILABLE,
    FallbackKind.TEST_ONLY_SIMULATION,
    FallbackKind.DETERMINISTIC_GOVERNANCE_DRAFT,
    FallbackKind.TOOLING_PREFLIGHT,
)


def _policy(kind: FallbackKind) -> FallbackPolicy:
    if kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
        return FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
            kind=kind,
            allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
            allowed_acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        )
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value=f"fallback.{kind.value.lower()}"),
        kind=kind,
    )


def _request(purpose: EvidencePurpose) -> FallbackEvidenceRequest:
    return FallbackEvidenceRequest(
        purpose=purpose,
        artifact_type=RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
    )


@pytest.mark.parametrize("kind", NON_CONTRACT_FALLBACK_KINDS)
def test_non_contract_fallback_kinds_cannot_satisfy_implementation_evidence(kind):
    decision = evaluate_fallback_evidence(
        policy=_policy(kind),
        request=_request(EvidencePurpose.IMPLEMENTATION),
    )

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=_policy(kind).fallback_policy_ref,
        applied_kind=kind,
        evaluated_purpose=EvidencePurpose.IMPLEMENTATION,
        allowed=False,
        blocking_reasons=(
            "implementation evidence cannot be satisfied by fallback",
            f"fallback kind cannot satisfy evidence: {kind.value}",
        ),
    )


def test_contract_deterministic_transform_cannot_satisfy_implementation_purpose():
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM),
        request=_request(EvidencePurpose.IMPLEMENTATION),
    )

    assert decision.allowed is False
    assert decision.fallback_policy_ref == FallbackPolicyRef(value="fallback.hash-manifest")
    assert decision.applied_kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM
    assert decision.evaluated_purpose is EvidencePurpose.IMPLEMENTATION
    assert "implementation evidence cannot be satisfied by fallback" in decision.blocking_reasons
    assert "deterministic transform can satisfy only deterministic evidence" in decision.blocking_reasons


def test_contract_deterministic_transform_requires_allowed_artifact_type_scope():
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM),
        request=FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="source_patch"),
            acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        ),
    )

    assert decision.allowed is False
    assert "artifact_type is outside fallback policy scope" in decision.blocking_reasons


def test_contract_deterministic_transform_requires_allowed_acceptance_scope():
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM),
        request=FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="hash_manifest"),
            acceptance_refs=(AcceptanceRef(value="AC-OUTSIDE-SCOPE"),),
        ),
    )

    assert decision.allowed is False
    assert "acceptance_refs are outside fallback policy scope" in decision.blocking_reasons


def test_contract_deterministic_transform_policy_requires_explicit_allow_lists():
    with pytest.raises(ValidationError, match="deterministic transform policies require allowed artifact types"):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.missing-artifacts"),
            kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
            allowed_artifact_types=(),
            allowed_acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        )

    with pytest.raises(ValidationError, match="deterministic transform policies require allowed acceptance refs"):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.missing-acceptance"),
            kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
            allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
            allowed_acceptance_refs=(),
        )


@pytest.mark.parametrize("kind", NON_CONTRACT_FALLBACK_KINDS)
def test_only_contract_deterministic_transform_policy_may_declare_allow_lists(kind):
    with pytest.raises(
        ValidationError,
        match="only contract-allowed deterministic transform policies may declare allow lists",
    ):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.invalid-allow-list"),
            kind=kind,
            allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
            allowed_acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        )


def test_fallback_request_requires_non_empty_acceptance_refs():
    with pytest.raises(ValidationError, match="acceptance_refs must not be empty"):
        FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="hash_manifest"),
            acceptance_refs=(),
        )


def test_fallback_models_reject_unknown_extra_fields():
    with pytest.raises(ValidationError):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.extra"),
            kind=FallbackKind.TOOLING_PREFLIGHT,
            unexpected="not allowed",
        )

    with pytest.raises(ValidationError):
        FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="hash_manifest"),
            acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
            unexpected="not allowed",
        )

    with pytest.raises(ValidationError):
        FallbackEvidenceDecision(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.extra"),
            applied_kind=FallbackKind.TOOLING_PREFLIGHT,
            evaluated_purpose=EvidencePurpose.DIAGNOSTIC,
            allowed=True,
            unexpected="not allowed",
        )
```

- [ ] **Step 2: Run tests to verify they fail before implementation**

Run:

```bash
PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.execution.fallback'`.

---

### Task 2: Minimal fallback policy implementation

**Files:**
- Create: `src/boardroom_os/execution/fallback.py`
- Modify: `src/boardroom_os/execution/__init__.py`
- Test: `tests/negative/test_fallback_cannot_satisfy_implementation.py`

- [ ] **Step 1: Implement fallback policy models and decision function**

Create `src/boardroom_os/execution/fallback.py` with this content:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.execution.package import FallbackPolicyRef


class EvidencePurpose(StrEnum):
    IMPLEMENTATION = "implementation"
    DIAGNOSTIC = "diagnostic"
    DETERMINISTIC = "deterministic"


class FallbackKind(StrEnum):
    DETERMINISTIC_GOVERNANCE_DRAFT = "DETERMINISTIC_GOVERNANCE_DRAFT"
    TOOLING_PREFLIGHT = "TOOLING_PREFLIGHT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TEST_ONLY_SIMULATION = "TEST_ONLY_SIMULATION"
    CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM = "CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM"


class FallbackPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_policy_ref: FallbackPolicyRef
    kind: FallbackKind
    allowed_artifact_types: tuple[RequiredArtifactType, ...] = ()
    allowed_acceptance_refs: tuple[AcceptanceRef, ...] = ()

    @model_validator(mode="after")
    def _validate_transform_scope(self) -> FallbackPolicy:
        if self.kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
            if not self.allowed_artifact_types:
                raise ValueError(
                    "deterministic transform policies require allowed artifact types"
                )
            if not self.allowed_acceptance_refs:
                raise ValueError(
                    "deterministic transform policies require allowed acceptance refs"
                )
        elif self.allowed_artifact_types or self.allowed_acceptance_refs:
            raise ValueError(
                "only contract-allowed deterministic transform policies may declare allow lists"
            )
        return self


class FallbackEvidenceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    purpose: EvidencePurpose
    artifact_type: RequiredArtifactType
    acceptance_refs: tuple[AcceptanceRef, ...]

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance_refs must not be empty")
        return values


class FallbackEvidenceDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_policy_ref: FallbackPolicyRef
    applied_kind: FallbackKind
    evaluated_purpose: EvidencePurpose
    allowed: bool
    blocking_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_reasons(self) -> FallbackEvidenceDecision:
        if self.allowed and self.blocking_reasons:
            raise ValueError("allowed fallback decisions must not include blocking reasons")
        if not self.allowed and not self.blocking_reasons:
            raise ValueError("blocked fallback decisions must include blocking reasons")
        return self


def evaluate_fallback_evidence(
    *,
    policy: FallbackPolicy,
    request: FallbackEvidenceRequest,
) -> FallbackEvidenceDecision:
    blockers: list[str] = []

    if request.purpose is EvidencePurpose.IMPLEMENTATION:
        blockers.append("implementation evidence cannot be satisfied by fallback")

    if policy.kind is FallbackKind.TOOLING_PREFLIGHT:
        if request.purpose is not EvidencePurpose.DIAGNOSTIC:
            blockers.append("tooling preflight fallback is diagnostic only")
    elif policy.kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
        if request.purpose is not EvidencePurpose.DETERMINISTIC:
            blockers.append("deterministic transform can satisfy only deterministic evidence")
        allowed_artifact_types = {
            artifact_type.value for artifact_type in policy.allowed_artifact_types
        }
        if request.artifact_type.value not in allowed_artifact_types:
            blockers.append("artifact_type is outside fallback policy scope")
        allowed_acceptance_refs = {
            acceptance_ref.value for acceptance_ref in policy.allowed_acceptance_refs
        }
        request_acceptance_refs = {
            acceptance_ref.value for acceptance_ref in request.acceptance_refs
        }
        if not request_acceptance_refs.issubset(allowed_acceptance_refs):
            blockers.append("acceptance_refs are outside fallback policy scope")
    else:
        blockers.append(f"fallback kind cannot satisfy evidence: {policy.kind.value}")

    if blockers:
        return FallbackEvidenceDecision(
            fallback_policy_ref=policy.fallback_policy_ref,
            applied_kind=policy.kind,
            evaluated_purpose=request.purpose,
            allowed=False,
            blocking_reasons=tuple(dict.fromkeys(blockers)),
        )
    return FallbackEvidenceDecision(
        fallback_policy_ref=policy.fallback_policy_ref,
        applied_kind=policy.kind,
        evaluated_purpose=request.purpose,
        allowed=True,
    )


__all__ = [
    "EvidencePurpose",
    "FallbackEvidenceDecision",
    "FallbackEvidenceRequest",
    "FallbackKind",
    "FallbackPolicy",
    "evaluate_fallback_evidence",
]
```

- [ ] **Step 2: Re-export fallback policy API**

Modify `src/boardroom_os/execution/__init__.py` to include these imports near the top:

```python
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackEvidenceRequest,
    FallbackKind,
    FallbackPolicy,
    evaluate_fallback_evidence,
)
```

Then add these names to `__all__`:

```python
    "EvidencePurpose",
    "FallbackEvidenceDecision",
    "FallbackEvidenceRequest",
    "FallbackKind",
    "FallbackPolicy",
    "evaluate_fallback_evidence",
```

- [ ] **Step 3: Run negative tests to verify they pass**

Run:

```bash
PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py -q
```

Expected: PASS, with all tests in `tests/negative/test_fallback_cannot_satisfy_implementation.py` passing.

---

### Task 3: Happy path tests and regression verification

**Files:**
- Create: `tests/execution/test_fallback_policy.py`
- Modify if needed: `src/boardroom_os/execution/fallback.py`
- Verify: `tests/negative/test_fallback_cannot_satisfy_implementation.py`

- [ ] **Step 1: Write happy path and decision invariant tests**

Create `tests/execution/test_fallback_policy.py` with this content:

```python
import pytest
from pydantic import ValidationError

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackEvidenceRequest,
    FallbackKind,
    FallbackPolicy,
    evaluate_fallback_evidence,
)
from boardroom_os.execution.package import FallbackPolicyRef


def test_contract_allowed_deterministic_transform_can_satisfy_scoped_deterministic_evidence():
    policy = FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
        kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
        allowed_acceptance_refs=(AcceptanceRef(value="AC-HASH-MANIFEST"),),
    )
    request = FallbackEvidenceRequest(
        purpose=EvidencePurpose.DETERMINISTIC,
        artifact_type=RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-HASH-MANIFEST"),),
    )

    decision = evaluate_fallback_evidence(policy=policy, request=request)

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
        applied_kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        evaluated_purpose=EvidencePurpose.DETERMINISTIC,
        allowed=True,
    )
    assert decision.model_dump(mode="json") == {
        "fallback_policy_ref": {"value": "fallback.hash-manifest"},
        "applied_kind": "CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM",
        "evaluated_purpose": "deterministic",
        "allowed": True,
        "blocking_reasons": [],
    }


def test_tooling_preflight_can_only_return_diagnostic_eligibility():
    policy = FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling-preflight"),
        kind=FallbackKind.TOOLING_PREFLIGHT,
    )
    request = FallbackEvidenceRequest(
        purpose=EvidencePurpose.DIAGNOSTIC,
        artifact_type=RequiredArtifactType(value="preflight_report"),
        acceptance_refs=(AcceptanceRef(value="AC-PREFLIGHT"),),
    )

    decision = evaluate_fallback_evidence(policy=policy, request=request)

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling-preflight"),
        applied_kind=FallbackKind.TOOLING_PREFLIGHT,
        evaluated_purpose=EvidencePurpose.DIAGNOSTIC,
        allowed=True,
    )


def test_tooling_preflight_cannot_satisfy_deterministic_evidence():
    policy = FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling-preflight"),
        kind=FallbackKind.TOOLING_PREFLIGHT,
    )
    request = FallbackEvidenceRequest(
        purpose=EvidencePurpose.DETERMINISTIC,
        artifact_type=RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-HASH-MANIFEST"),),
    )

    decision = evaluate_fallback_evidence(policy=policy, request=request)

    assert decision.allowed is False
    assert decision.blocking_reasons == ("tooling preflight fallback is diagnostic only",)


def test_blocked_decision_must_include_reasons():
    with pytest.raises(ValidationError, match="blocked fallback decisions must include blocking reasons"):
        FallbackEvidenceDecision(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.blocked"),
            applied_kind=FallbackKind.TOOLING_PREFLIGHT,
            evaluated_purpose=EvidencePurpose.DETERMINISTIC,
            allowed=False,
        )


def test_allowed_decision_must_not_include_reasons():
    with pytest.raises(ValidationError, match="allowed fallback decisions must not include blocking reasons"):
        FallbackEvidenceDecision(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.allowed"),
            applied_kind=FallbackKind.TOOLING_PREFLIGHT,
            evaluated_purpose=EvidencePurpose.DIAGNOSTIC,
            allowed=True,
            blocking_reasons=("not allowed",),
        )
```

- [ ] **Step 2: Run happy path tests**

Run:

```bash
PYTHONPATH=src pytest tests/execution/test_fallback_policy.py -q
```

Expected: PASS, with all tests in `tests/execution/test_fallback_policy.py` passing.

- [ ] **Step 3: Run V2-030E targeted tests together**

Run:

```bash
PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q
```

Expected: PASS for both V2-030E test files.

- [ ] **Step 4: Run execution and negative regression tests**

Run:

```bash
PYTHONPATH="src;." pytest tests/execution tests/negative -q
```

Expected: PASS. This confirms existing `ExecutionPackage`（执行包）, `ExecutionPackageCompiler`（执行包编译器）, agent profiles（智能体配置）, and negative fail-closed（失败关闭） tests still pass.

---

### Task 4: Work package completion documentation

**Files:**
- Modify: `doc/05-project-log/decisions.md`
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`

- [ ] **Step 1: Add DEC-0014**

Append to `doc/05-project-log/decisions.md`:

```markdown
## DEC-0014: TEST_ONLY_SIMULATION 不能作为 fallback evidence 例外

- 状态：Accepted
- 日期：2026-05-17

### 决策

V2-030E 不保留 `TEST_ONLY_SIMULATION`（测试环境模拟）可在“测试明确验证失败路径”时满足 evidence（证据）的例外。`TEST_ONLY_SIMULATION` 与 `PROVIDER_UNAVAILABLE`（模型供应商不可用）、`DETERMINISTIC_GOVERNANCE_DRAFT`（确定性治理草案）一样，不能满足 implementation evidence（实施证据）、diagnostic evidence（诊断证据）或 deterministic evidence（确定性证据）。

### 理由

上一版系统失败的核心风险之一是 fallback kind（降级类型）本身隐式承载了成功语义。failure-path validation（失败路径验证）必须通过 contract-declared deterministic transform（合同声明的确定性转换）显式表达，并受 `RequiredArtifactType`（必需产物类型）与 `AcceptanceRef`（验收引用）scope（作用域）约束。

### 影响

- `TEST_ONLY_SIMULATION` 只能作为测试环境中的场景标签，不具备证据资格。
- V2-050 `EvidenceVerifier`（证据验证器）处理 fallback artifact（降级产物）时，必须先解析 `fallback_policy_ref`（降级策略引用）得到 `FallbackPolicy`（降级策略）并调用 `evaluate_fallback_evidence`（降级证据判定函数）；若 registry（注册表）尚未提供可解析 policy，必须 fail closed（失败关闭）。
```

- [ ] **Step 2: Update backlog status and progress**

In `doc/04-implementation/backlog.md`:

1. Change the TL;DR line:

```markdown
**当前未完成工作包**：`V2-030F`
```

2. Keep the current focus on Phase 3 and update the next step:

```markdown
**当前重点**：Phase 3 Agent + Execution Package（智能体与执行包）继续推进；下一步实现 V2-030F agent context index（智能体上下文索引）草稿。
```

3. Change Phase 3 progress:

```markdown
| Phase 3：Agent + Execution Package | V2-030 | 5 / 6 | 进行中 |
```

4. Change total progress:

```markdown
| **合计** | **V2-000 ~ V2-080** | **22 / 52** | **Phase 3 进行中** |
```

5. In `### V2-030E: 实现 fallback policy 分类`, change:

```markdown
- 状态：DONE
```

6. Add completion evidence under the V2-030E acceptance text:

```markdown
- 完成证据：2026-05-17 新增 EvidencePurpose（证据用途）、FallbackPolicy（降级策略）、FallbackKind（降级类型）、FallbackEvidenceRequest（降级证据请求）、FallbackEvidenceDecision（降级证据判定）和 evaluate_fallback_evidence（降级证据判定函数），复用 FallbackPolicyRef（降级策略引用）、RequiredArtifactType（必需产物类型）和 AcceptanceRef（验收引用）；负例证明 PROVIDER_UNAVAILABLE、TEST_ONLY_SIMULATION、DETERMINISTIC_GOVERNANCE_DRAFT、TOOLING_PREFLIGHT 以及越界 CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM 均不能满足 implementation evidence（实施证据）；正例证明合同显式允许的 deterministic transform（确定性转换）只能满足窄范围 deterministic evidence（确定性证据），tooling preflight（工具预检）只能满足 diagnostic evidence（诊断证据）。验证命令：`PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q` 通过；`PYTHONPATH="src;." pytest tests/execution tests/negative -q` 通过。
```

- [ ] **Step 3: Update acceptance criteria checkbox**

In `doc/04-implementation/acceptance-criteria.md`, change the Phase 3 checkbox:

```markdown
- [x] AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence）— 由 V2-030E `test_fallback_cannot_satisfy_implementation.py` 证明：PROVIDER_UNAVAILABLE / TEST_ONLY_SIMULATION / DETERMINISTIC_GOVERNANCE_DRAFT / TOOLING_PREFLIGHT / 越界 deterministic transform 均不能满足 implementation evidence；合同显式允许的 deterministic transform 只能满足窄范围 deterministic evidence；EvidencePurpose.IMPLEMENTATION 覆盖 source / integration / acceptance / closeout 四类 evidence
```

Do not check V2-030F or Phase 3 completion checkboxes yet.

- [ ] **Step 4: Update monthly project log**

Append one entry to `doc/05-project-log/2026-05.md` if no existing `2026-05-17 V2-030E` entry exists:

```markdown
### 2026-05-17 — V2-030E fallback policy 分类

- 关键产出：`src/boardroom_os/execution/fallback.py`、`tests/negative/test_fallback_cannot_satisfy_implementation.py`、`tests/execution/test_fallback_policy.py`。
- Negative tests：证明 `PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`DETERMINISTIC_GOVERNANCE_DRAFT`、`TOOLING_PREFLIGHT` 和越界 `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 均不能满足 implementation evidence（实施证据）。
- Happy path：证明合同显式允许的 deterministic transform（确定性转换）只能满足窄范围 deterministic evidence（确定性证据），tooling preflight（工具预检）只能满足 diagnostic evidence（诊断证据）。
- 决策：新增 DEC-0014，明确 `TEST_ONLY_SIMULATION` 不再保留“失败路径测试例外”。
- 验证证据：`PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q`；`PYTHONPATH="src;." pytest tests/execution tests/negative -q`。
```

- [ ] **Step 5: Run final targeted checks**

Run:

```bash
PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q
```

Expected: PASS.

Run:

```bash
PYTHONPATH="src;." pytest tests/execution tests/negative -q
```

Expected: PASS.

---

## Self-Review

- Spec coverage: Tasks cover `EvidencePurpose`, typed value reuse, audit fields on `FallbackEvidenceDecision`, truth table semantics, TEST_ONLY_SIMULATION exception removal via DEC-0014, V2-050 call contract documentation, negative tests, happy paths, exports, verification, and work package completion docs.
- Placeholder scan: No TBD/TODO placeholders remain; all code steps include concrete snippets and commands.
- Type consistency: `EvidencePurpose`, `FallbackKind`, `FallbackPolicy`, `FallbackEvidenceRequest`, `FallbackEvidenceDecision`, and `evaluate_fallback_evidence` are defined before use and reused consistently.
