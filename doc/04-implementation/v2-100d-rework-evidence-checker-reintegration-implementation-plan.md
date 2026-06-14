# V2-100D Rework Evidence Checker Reintegration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V2-100D Rework evidence/checker reintegration（返工证据与检查重接入），确保每次 ReworkAttempt（返工尝试）都重新构造 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）和必要的 CloseoutGateResult（收尾门禁结果），旧证据、旧检查结论或旧 closeout passed（收尾通过）不能跨轮次复用。

**Architecture:** 新增 `boardroom_os.rework.evidence`（返工证据模块）作为薄协调层，只编排并校验现有权威组件：EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、build_source_inventory（源码清单构建器）、CheckerService（检查服务）和 CloseoutGate（收尾门禁）。为 FinalEvidenceTable（最终证据表）增加可选 EvidenceNamespaceRef（证据命名空间引用），让返工轮次可以生成唯一表引用，同时保留现有未命名空间 ID 规则。Runtime/executor（运行时/执行器）仍只记录事实，不做返工接受或收尾决策。

**Tech Stack:** Python 3.11+、Pydantic v2、pytest；复用现有 V2 类型：ReworkAttempt（返工尝试）、ReworkOutcome（返工结果）、EvidenceVerificationResult（证据验证结果）、VerifiedEvidence（已验证证据）、FinalEvidenceTable（最终证据表）、SourceInventory（源码清单）、CheckerVerdict（检查结论）、RunManifest（运行清单）、CloseoutGateInput（收尾门禁输入）、CloseoutGateResult（收尾门禁结果）、AcceptanceContract（验收合同）和 PackageContract（包合同）。

---

## Scope And Non-Goals

V2-100D 负责：

- 给返工证据链增加 `run_id + cycle_id + rework_attempt_id + graph_version` 命名空间。
- 校验 ReworkAttempt（返工尝试）必须有 ProviderAttempt（模型调用尝试记录）、command evidence（命令证据）、source lineage（源码来源链）和 workspace mutation（工作区变更）引用。
- 使用 active AcceptanceContract（活跃验收合同）重新构造 FinalEvidenceTable（最终证据表）。
- 使用 active PackageContract（包合同）和当前 SourceLineageRecord（源码来源链记录）重新构造 SourceInventory（源码清单）。
- 只在当前轮证据验证之后调用 CheckerService（检查服务）生成 CheckerVerdict（检查结论）。
- 在 closeout（收尾）受影响时重新调用 CloseoutGate（收尾门禁），并拒绝旧 run、旧 RunManifest（运行清单）、旧 SourceInventory（源码清单）、旧 FinalEvidenceTable（最终证据表）、旧 CheckerVerdict（检查结论）和旧 CloseoutPackage（收尾包）复用。
- 校验 RunManifest（运行清单）运行准备性：run command（运行命令）需要 service contract（服务合同），BehavioralProbe（行为探针）必须绑定 active acceptance refs（活跃验收引用），实现读取的 env vars（环境变量）必须由 RunManifest 声明。

V2-100D 不负责：

- ReworkAttempt（返工尝试）和 ReworkOutcome（返工结果）基础模型，V2-100A 已负责。
- Rework events（返工事件）、GraphPatchReviewGate（图补丁审查门禁）和 ReworkReducer（返工归约器），V2-100B 已负责。
- CEO ReworkPlan（CEO 返工计划）、TicketGraphPatch（工单图补丁）和多角色审查解析，V2-100C 已负责。
- Multi-round proving scenario（多轮证明场景）、resettable failing fixture（可重置失败夹具）和 process audit/replay（流程审计/重放）导出，V2-100E 负责。
- 执行 provider（模型供应商）、atomic-agent（原子智能体）或本地命令；V2-100D 只消费真实记录的事实。

---

## File Structure

- Modify `src/boardroom_os/evidence/table.py`
  - 增加 `EvidenceNamespaceRef`（证据命名空间引用）。
  - 给 `FinalEvidenceTable`（最终证据表）和 `FinalEvidenceTableInput`（最终证据表输入）增加可选 `evidence_namespace_ref` 字段。
  - 保持未命名空间表 ID 兼容，返工表使用命名空间 ID。
- Create `src/boardroom_os/rework/evidence.py`
  - 新增 ReworkEvidenceNamespace（返工证据命名空间）、ReworkEvidenceRecheckInput（返工证据重验输入）、ReworkCloseoutRecheckContext（返工收尾重验上下文）、ReworkEnvironmentUsage（返工环境变量使用记录）、ReworkEvidenceRecheckResult（返工证据重验结果）。
  - 新增新鲜度校验、RunManifest（运行清单）准备性校验、SourceInventory（源码清单）重建、FinalEvidenceTable（最终证据表）重建、CheckerVerdict（检查结论）重建和 CloseoutGate（收尾门禁）重跑函数。
- Modify `src/boardroom_os/rework/__init__.py`
  - 导出 V2-100D 公共 API，不重复导出 EvidenceVerifier（证据验证器）或 CloseoutGate（收尾门禁）权威 API。
- Create `tests/rework/fixtures/rework_evidence.py`
  - 提供 V2-100D 测试用真实 typed fixture（类型化夹具），只构造真实模型，不 mock EvidenceVerifier（证据验证器）、SourceInventory（源码清单）、CheckerVerdict（检查结论）或 CloseoutGate（收尾门禁）结论。
- Create `tests/negative/test_rework_evidence_fail_closed.py`
  - 覆盖缺 ProviderAttempt（模型调用尝试记录）、缺 source lineage（源码来源链）、复用旧 FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）早于证据验证、遗漏 BehavioralProbe（行为探针）失败、缺 service contract（服务合同）和未声明 env usage（环境变量使用）。
- Create `tests/negative/test_rework_closeout_fail_closed.py`
  - 覆盖旧 RunManifest（运行清单）、旧 SourceInventory（源码清单）、旧 FinalEvidenceTable（最终证据表）、旧 CheckerVerdict（检查结论）和旧 CloseoutPackage passed（旧收尾通过包）复用。
- Create `tests/rework/test_rework_evidence_recheck.py`
  - 证明当前 ReworkAttempt（返工尝试）可以重建 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）和 ReworkOutcome（返工结果）。
- Create `tests/rework/test_rework_closeout_fact_chain.py`
  - 证明 CloseoutGate（收尾门禁）只消费同一 run/cycle/attempt（运行/循环/尝试）的当前事实链。
- Modify `doc/04-implementation/INDEX.md`
  - 登记本实施计划。本 plan（计划）阶段不修改 backlog（任务清单）状态，不勾选 acceptance checkbox（验收复选项）。

---

## Public API Target

在 `src/boardroom_os/evidence/table.py` 实现：

- `EvidenceNamespaceRef`
- `FinalEvidenceTable.evidence_namespace_ref: EvidenceNamespaceRef | None`
- `FinalEvidenceTableInput.evidence_namespace_ref: EvidenceNamespaceRef | None`

FinalEvidenceTable ID（最终证据表 ID）规则：

- 未传 `evidence_namespace_ref` 时保持现有 ID：`final-evidence-table.<acceptance_contract_ref>`。
- 传入 `evidence_namespace_ref` 时使用：`final-evidence-table.<acceptance_contract_ref>.<evidence_namespace_ref>`。
- `FinalEvidenceTableBuilder.build(...)` 必须从 `FinalEvidenceTableInput` 透传命名空间。

在 `src/boardroom_os/rework/evidence.py` 实现：

- `ReworkEvidenceError`
- `ReworkEvidenceNamespace`
- `ReworkEnvironmentUsage`
- `ReworkCloseoutRecheckContext`
- `ReworkEvidenceRecheckInput`
- `ReworkEvidenceRecheckResult`
- `rework_evidence_namespace_ref(namespace: ReworkEvidenceNamespace) -> EvidenceNamespaceRef`
- `validate_rework_attempt_fact_refs(attempt: ReworkAttempt) -> ReworkAttempt`
- `validate_rework_evidence_freshness(recheck_input: ReworkEvidenceRecheckInput) -> None`
- `validate_rework_final_evidence_table_freshness(table: FinalEvidenceTable, *, namespace: ReworkEvidenceNamespace, verified_evidence: tuple[VerifiedEvidence, ...]) -> FinalEvidenceTable`
- `validate_rework_run_manifest_readiness(run_manifest: RunManifest, *, active_acceptance_refs: tuple[AcceptanceRef, ...], environment_usage: tuple[ReworkEnvironmentUsage, ...]) -> None`
- `build_rework_source_inventory(recheck_input: ReworkEvidenceRecheckInput) -> SourceInventory`
- `build_rework_final_evidence_table(recheck_input: ReworkEvidenceRecheckInput) -> FinalEvidenceTable`
- `build_rework_checker_verdict(recheck_input: ReworkEvidenceRecheckInput, final_evidence_table: FinalEvidenceTable) -> CheckerVerdict`
- `evaluate_rework_closeout(recheck_input: ReworkEvidenceRecheckInput, source_inventory: SourceInventory, final_evidence_table: FinalEvidenceTable, checker_verdict: CheckerVerdict) -> CloseoutGateResult | None`
- `recheck_rework_attempt(recheck_input: ReworkEvidenceRecheckInput) -> ReworkEvidenceRecheckResult`

`ReworkEvidenceNamespace`（返工证据命名空间）字段：

```python
class ReworkEvidenceNamespace(BaseModel):
    run_id: RunId
    cycle_id: ReworkCycleId | str
    rework_attempt_id: ReworkAttemptId
    graph_version: int
    config_hash_refs: tuple[str, ...]
```

`ReworkEvidenceRecheckInput`（返工证据重验输入）字段：

```python
class ReworkEvidenceRecheckInput(BaseModel):
    attempt: ReworkAttempt
    namespace: ReworkEvidenceNamespace
    active_acceptance_contract: AcceptanceContract
    active_package_contract: PackageContract
    package_assembly: PackageAssembly
    package_commit_ref: PackageCommitRef
    source_files: tuple[SourceFileRecord, ...]
    source_lineage_records: tuple[SourceLineageRecord, ...]
    evidence_verification_results: tuple[EvidenceVerificationResult, ...]
    failed_final_evidence_blockers: tuple[FinalEvidenceBlocker, ...]
    target_blocker_refs: tuple[BlockerRef, ...]
    work_product: WorkProduct
    source_diff_ref: SourceDiffRef
    run_manifest: RunManifest
    environment_usage: tuple[ReworkEnvironmentUsage, ...]
    checked_at: datetime
    closeout_context: ReworkCloseoutRecheckContext | None
```

`ReworkEvidenceRecheckResult`（返工证据重验结果）字段：

```python
class ReworkEvidenceRecheckResult(BaseModel):
    namespace: ReworkEvidenceNamespace
    attempt_ref: ReworkAttemptId
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    closeout_gate_result: CloseoutGateResult | None
    status: ReworkOutcomeStatus
    remaining_blocker_refs: tuple[BlockerRef, ...]
    accepted_blocker_refs: tuple[BlockerRef, ...]
    checked_refs: tuple[str, ...]
    rejected_stale_refs: tuple[str, ...]
    created_at: datetime

    def to_rework_outcome(self) -> ReworkOutcome:
        return ReworkOutcome(
            rework_outcome_id=ReworkOutcomeId(value=f"rework-outcome.{self.attempt_ref.value}"),
            rework_attempt_ref=self.attempt_ref,
            final_evidence_table_ref=self.final_evidence_table.final_evidence_table_id.value,
            source_inventory_ref=self.source_inventory.source_inventory_id.value,
            checker_verdict_ref=self.checker_verdict.checker_verdict_id.value,
            closeout_gate_ref=(
                self.closeout_gate_result.closeout_gate_result_id.value
                if self.closeout_gate_result is not None
                else None
            ),
            status=self.status,
            remaining_blocker_refs=self.remaining_blocker_refs,
            accepted_blocker_refs=self.accepted_blocker_refs,
            created_at=self.created_at,
        )
```

关键校验规则：

- ReworkAttempt（返工尝试）必须有 provider attempts（模型调用尝试）、command evidence（命令证据）、source lineage（源码来源链）和 workspace mutation（工作区变更）引用。
- `namespace.rework_attempt_id` 必须等于 `attempt.rework_attempt_id`。
- 所有成功的 EvidenceVerificationResult（证据验证结果）必须携带 VerifiedEvidence（已验证证据），且 `producer_attempt_ref` 必须来自当前 ReworkAttempt。
- 当前轮 VerifiedEvidenceRef（已验证证据引用）和 FinalEvidenceTableRef（最终证据表引用）必须包含 rework evidence namespace（返工证据命名空间）。
- SourceLineageRecord（源码来源链记录）的 `producer_attempt_ref` 必须来自当前 ReworkAttempt，`evidence_refs` 必须来自当前轮 VerifiedEvidence。
- CheckerVerdict（检查结论）必须在当前轮证据验证之后创建，并引用当前轮 FinalEvidenceTable。
- CloseoutGateInput（收尾门禁输入）必须消费当前 SourceInventory、FinalEvidenceTable、CheckerVerdict、RunManifest、VerifiedEvidence 和 command bindings（命令绑定）对象。PackageCommitRef（包提交引用）继续表达真实 package commit（包提交），不能被改造成返工命名空间。
- ReworkOutcome.accepted_blocker_refs（返工结果已接受阻塞项引用）必须来自 `target_blocker_refs`，不能从 command success（命令成功）或 ProviderAttempt completed（模型调用完成）推断。
- 旧 CloseoutPackage（收尾包）和旧 closeout passed state（收尾通过状态）不得作为返工接受输入。

---

## Pre-Flight Before Implementation

- [ ] **Step 1: 确认分支与任务状态**

Run:

```bash
git status --short --branch
git diff --quiet --cached || echo "有已暂存的更改，请先处理"
test ! -e src/boardroom_os/rework/evidence.py
test ! -e tests/rework/test_rework_evidence_recheck.py
test ! -e tests/negative/test_rework_evidence_fail_closed.py
```

Expected: 分支为 `rebuild/v2-clean-foundation`；若命令输出 `有已暂存的更改，请先处理`，先确认这些 staged changes（已暂存变更）是否属于当前任务；`doc/04-implementation/backlog.md` 中 V2-100A/B/C 为 `DONE`，V2-100D 为 `TODO`；目标实现文件尚不存在。若文件已存在，先读取并保留用户改动。

- [ ] **Step 2: 确认现有权威 API 可导入**

Run:

```bash
PYTHONPATH=src python - <<'PY'
from boardroom_os.checker.checker import CheckerService, CheckerServiceInput
from boardroom_os.closeout.gate import CloseoutGate, CloseoutGateInput
from boardroom_os.evidence.table import FinalEvidenceTableBuilder, FinalEvidenceTableInput
from boardroom_os.evidence.verifier import EvidenceVerifier, EvidenceVerificationResult
from boardroom_os.workspace.source_inventory import build_source_inventory

print("v2-100d authoritative api ok")
PY
```

Expected: 输出 `v2-100d authoritative api ok`。

- [ ] **Step 3: 运行 V2-100A/B/C 回归测试**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_rework_model.py \
  tests/rework/test_v2_090k_failure_snapshot_projection.py \
  tests/rework/test_ceo_rework_planner.py \
  tests/rework/test_multi_role_graph_patch_reviews.py \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/negative/test_ceo_rework_planner_fail_closed.py \
  tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py \
  -q
```

Expected: V2-100A/B/C 相关测试在实施 V2-100D 前通过。

---

### Task 1: 建立 V2-100D 测试夹具

**Files:**
- Create `tests/rework/fixtures/rework_evidence.py`

- [ ] **Step 1: 写入共享常量与 namespace helper**

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.checker.verdict import CheckerVerdict
from boardroom_os.evidence.table import FinalEvidenceBlocker, FinalEvidenceBlockerCode
from boardroom_os.evidence.table import FinalEvidenceTable
from boardroom_os.evidence.verifier import EvidenceVerificationResult, VerifiedEvidence
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.rework.evidence import ReworkEvidenceNamespace
from boardroom_os.rework.model import BlockerRef, ReworkAttemptId, ReworkCycleId, RunId
from boardroom_os.workspace.source_inventory import SourceInventory

NOW = datetime(2026, 6, 14, 9, 0, tzinfo=UTC)
RUN_ID = RunId(value="run-v2-100d")
CYCLE_ID = ReworkCycleId(value="rework-cycle.v2-100d")
ATTEMPT_ID = ReworkAttemptId(value="rework-attempt.v2-100d.1")
ACCEPTANCE_REF = AcceptanceRef(value="acceptance.book.add")
SOURCE_SURFACE_REF = SourceSurfaceRef(value="surface.backend.api")
EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.book.add.api")
PACKAGE_CONTRACT_REF = ContractId(value="package.v2-100d")
ACCEPTANCE_CONTRACT_REF = ContractId(value="acceptance.v2-100d")
PROVIDER_ATTEMPT_REF = ProviderAttemptRef(value="provider-attempt.worker.rework.v2-100d.1")
TARGET_BLOCKER_REF = BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe")


def namespace() -> ReworkEvidenceNamespace:
    return ReworkEvidenceNamespace(
        run_id=RUN_ID,
        cycle_id=CYCLE_ID,
        rework_attempt_id=ATTEMPT_ID,
        graph_version=42,
        config_hash_refs=("config-hash.roles.v2-100d", "config-hash.runtime.v2-100d"),
    )


class FreshRecheckParts(NamedTuple):
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    old_source_inventory: SourceInventory
    old_final_evidence_table: FinalEvidenceTable
    old_checker_verdict: CheckerVerdict
```

- [ ] **Step 2: 添加 typed fixture builder（类型化夹具构建器）**

同一文件继续实现下列函数，每个函数都返回真实模型实例，不返回 dict（字典）或 mock（模拟对象）：

- `active_acceptance_contract()`：返回 active AcceptanceContract（活跃验收合同），包含 blocking criterion（阻塞验收项） `ACCEPTANCE_REF`，evidence_required（所需证据）覆盖 `source`、`verification_run` 和 `live_blackbox` 对应 artifact type（产物类型）。
- `active_package_contract()`：返回 PackageContract（包合同），package root（包根）为 `10-project`，source surface（源码面）包含 `SOURCE_SURFACE_REF`，run/test commands（运行/测试命令）包含 backend service run（后端服务运行）和 pytest command（pytest 命令）。
- `package_assembly()`：返回 PackageAssembly（包装配结果），包含 backend source file（后端源码文件）和 test file（测试文件）两个 implementation-bearing artifacts（承载实现的产物）。
- `source_files()`：返回与 PackageAssembly artifacts（包装配产物）路径一一对应的 SourceFileRecord（源码文件记录），hash 使用固定 64 位小写十六进制字符串。
- `verified_evidence(namespace_ref)`：返回 VerifiedEvidence（已验证证据），`verified_evidence_id.value` 必须包含 `namespace_ref.value`，producer attempt（产出尝试）必须为 `PROVIDER_ATTEMPT_REF`。
- `evidence_results(namespace_ref)`：返回单个成功 `EvidenceVerificationResult(verified_evidence=verified_evidence(namespace_ref))`。
- `source_lineage_records(namespace_ref)`：返回 SourceLineageRecord（源码来源链记录），`producer_attempt_ref` 等于 `PROVIDER_ATTEMPT_REF`，`evidence_refs` 引用当前 namespace（命名空间）中的 VerifiedEvidence。
- `rework_attempt()`：返回 ReworkAttempt（返工尝试），包含 provider attempt、workspace mutation、command evidence、source lineage 和 RunManifest refs（运行清单引用）。
- `work_product()`：返回 WorkProduct（工作产物），其 `producer_attempt_ref` 与 `PROVIDER_ATTEMPT_REF` 一致，artifact/claim refs（产物/声明引用）非空。
- `source_diff_ref()`：返回 SourceDiffRef（源码差异引用），值包含当前 attempt id（尝试 ID）。
- `run_manifest_with_service_and_probe()`：返回含 run command、test command、service contract、env bindings、readiness probe 和 behavioral probe（行为探针）的 RunManifest（运行清单）。
- `old_run_manifest_with_service_and_probe()`：返回与当前 run manifest（运行清单）结构等价但 `run_manifest_id` 不同的旧 RunManifest（旧运行清单），用于 stale run manifest（陈旧运行清单）负例。
- `run_manifest_with_run_command_and_no_service_contracts()`：返回带 run command 但 `service_contracts=None` 的 RunManifest（运行清单）负例输入。
- `run_manifest_with_host_port_only()`：返回只声明 `HOST` / `PORT` 的 RunManifest（运行清单）负例输入。
- `closeout_gate_input(...)`：接收当前 ReworkEvidenceRecheckInput（返工证据重验输入）、SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）和 RunManifest（运行清单），并构造 closeout-ready（收尾就绪）的真实 CloseoutGateInput（收尾门禁输入）。这个 helper（辅助函数）不是 5 个对象的薄包装，必须补齐 `package_contract`（包合同）、`workspace_evidence_bundle`（工作区证据包）、`verification_runs`（验证运行）、`service_run_evidence`（服务运行证据）、`verified_evidence`（已验证证据）、`provider_attempt_refs`（模型调用尝试引用）、`final_command_bindings`（最终命令绑定）、`replay_readiness`（重放就绪）、`git_audit_readiness`（Git 审计就绪）和 `process_audit_readiness`（流程审计就绪）。
- `environment_usage_declared()`：返回只包含 RunManifest 已声明 env vars（环境变量）的 ReworkEnvironmentUsage（返工环境变量使用记录）。
- `environment_usage_undeclared()`：返回包含 `LIBRARY_DB_PATH` 的 ReworkEnvironmentUsage（返工环境变量使用记录）。
- `rework_input_with_verified_evidence()`：返回完整 ReworkEvidenceRecheckInput（返工证据重验输入），使用当前 namespace、active contracts、真实 source lineage、成功 evidence results、target blocker refs 和 declared env usage。
- `rework_input_with_behavioral_probe_failure()`：返回包含 behavioral probe failure（行为探针失败）的 ReworkEvidenceRecheckInput，其失败必须通过 `failed_final_evidence_blockers` 映射到 active acceptance ref（活跃验收引用）。
- `fresh_recheck_parts()`：在 Task 6 Step 0.5 实现；返回 FreshRecheckParts（新鲜重验部件），其中 fresh fields（新鲜字段）由 Task 5 builder（构建器）生成，old fields（陈旧字段）必须故意不含当前 namespace（命名空间）或不等于当前轮对象。
- `rework_input_with_closeout_context()`：在 Task 6 Step 0.5 实现；返回带真实 CloseoutGateInput（收尾门禁输入）的 ReworkEvidenceRecheckInput（返工证据重验输入）。

共同实现要求：

- `verified_evidence(namespace_ref)` 生成的 `VerifiedEvidence.verified_evidence_id.value` 必须包含 `namespace_ref.value`。
- `source_lineage_records(namespace_ref)` 中的 `producer_attempt_ref` 必须等于 `PROVIDER_ATTEMPT_REF`，`evidence_refs` 必须引用当前 namespace 的 VerifiedEvidence。
- `run_manifest_with_service_and_probe()` 必须包含 run command、test command、service contract、env bindings、readiness probe 和 behavioral probes，且 behavioral probe 绑定 `ACCEPTANCE_REF`。
- `closeout_gate_input(...)` 必须满足 CloseoutGate（收尾门禁）当前 `PASSED`（通过）门槛：
  - `verification_runs` 非空，全部 `PASSED` 且 `exit_code=0`。
  - `service_run_evidence` 覆盖 run command（运行命令），readiness probe status code（就绪探针状态码）在 200-299。
  - `final_command_bindings` 精确覆盖 RunManifest（运行清单）所有 declared commands（声明命令）：`TEST` command 绑定 VerificationRun（验证运行），`RUN` command 绑定 ServiceRunEvidence（服务运行证据），并且 command id、command tuple（命令元组）、cwd（工作目录）与 RunManifest 完全一致。
  - `workspace_evidence_bundle` 非空且 closeout-ready（收尾就绪），artifact kinds（产物类型）覆盖 source/test/run manifest/package contract/final evidence 等必要类型，refs（引用）精确等于当前 `verified_evidence + verification_runs + service_run_evidence` 可推导的事实集合。
  - `provider_attempt_refs` 非空、无重复，并覆盖所有 VerifiedEvidence（已验证证据）和 verified artifacts（已验证产物）的 producer attempt（产出模型调用尝试）。
  - `replay_readiness` 非空，`replay_passed`、`hash_chain_verified` 和 `payload_sha256_verified` 全为 true，projection versions（投影版本）非空。
  - `git_audit_readiness` 非空，`git_clean`、`source_inventory_hash_matches` 和 `final_command_evidence_at_final_commit` 全为 true，`final_commit_sha` 必须与 `source_inventory.package_commit_ref` 的 `package-commit.<sha>` 语义一致。
  - `process_audit_readiness` 非空，所有 readiness boolean（就绪布尔值）为 true，artifact paths（产物路径）必须精确等于 CloseoutGate（收尾门禁）要求的 10 个路径：`30-audit/process-audit.md`、`30-audit/timeline.json`、`30-audit/decision-log.md`、`30-audit/agent-context-index.json`、`30-audit/ticket-graph.md`、`30-audit/artifact-lineage.json`、`30-audit/evidence-map.json`、`30-audit/git-version-audit.md`、`30-audit/closeout-summary.md`、`30-audit/replay-bundle-report.json`。
  - 上述所有 ids/refs（标识/引用）必须来自当前 namespace（命名空间）或当前 `recheck_input`（重验输入）事实链；陈旧对象只能放在 `old_*` 夹具字段中用于负例。
- 可参考 `tests/closeout/test_closeout_gate.py::_ready_input()` 的构造顺序理解 CloseoutGateInput（收尾门禁输入）事实链，但不得 import（导入）该 private helper（私有辅助函数），也不得复用非当前 namespace（命名空间）的现成 closeout fixture（收尾夹具）作为通过证据。
- Task 1 不允许创建 placeholder CloseoutGateInput（占位收尾门禁输入）或 mock closeout success（模拟收尾成功）。CloseoutGateInput 必须等 Task 5 的 builder 可用后在 Task 6 Step 0.5 由真实 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）和 CheckerVerdict（检查结论）组装。

- [ ] **Step 3: 运行夹具导入检查**

Run:

```bash
PYTHONPATH=src:. python - <<'PY'
from tests.rework.fixtures.rework_evidence import namespace, rework_attempt

print(namespace().rework_attempt_id.value)
print(rework_attempt().rework_attempt_id.value)
PY
```

Expected before implementation: 可能因 `boardroom_os.rework.evidence` 不存在而失败。Expected after implementation: 输出同一个 `rework-attempt.v2-100d.1`。

---

### Task 2: 先写 evidence freshness 负例测试

**Files:**
- Create `tests/negative/test_rework_evidence_fail_closed.py`

- [ ] **Step 1: 写入 imports**

```python
from datetime import timedelta

import pytest
from pydantic import ValidationError

from boardroom_os.evidence.table import EvidenceNamespaceRef
from boardroom_os.rework.evidence import (
    ReworkEnvironmentUsage,
    ReworkEvidenceError,
    build_rework_final_evidence_table,
    rework_evidence_namespace_ref,
    validate_rework_evidence_freshness,
    validate_rework_final_evidence_table_freshness,
    validate_rework_run_manifest_readiness,
)
from tests.rework.fixtures import rework_evidence as fx
```

- [ ] **Step 2: 写旧 FinalEvidenceTable（最终证据表）复用负例**

```python
def test_old_final_evidence_table_cannot_satisfy_rework_attempt() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    current_table = build_rework_final_evidence_table(recheck_input)
    old_table = current_table.model_copy(
        update={"evidence_namespace_ref": EvidenceNamespaceRef(value="rework-evidence.run-old.cycle-old.attempt-old.g1")}
    )
    verified = tuple(
        result.verified_evidence
        for result in recheck_input.evidence_verification_results
        if result.verified_evidence is not None
    )

    with pytest.raises(ReworkEvidenceError, match="final evidence table namespace"):
        validate_rework_final_evidence_table_freshness(
            old_table,
            namespace=recheck_input.namespace,
            verified_evidence=verified,
        )
```

- [ ] **Step 3: 写缺 ProviderAttempt（模型调用尝试记录）和 source lineage（源码来源链）负例**

```python
def test_workspace_mutation_without_provider_attempt_fails() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    attempt = recheck_input.attempt.model_copy(update={"provider_attempt_refs": ()})
    stale_input = recheck_input.model_copy(update={"attempt": attempt})

    with pytest.raises((ReworkEvidenceError, ValidationError), match="provider_attempt"):
        validate_rework_evidence_freshness(stale_input)


def test_source_edits_without_source_lineage_records_fail() -> None:
    recheck_input = fx.rework_input_with_verified_evidence().model_copy(
        update={"source_lineage_records": ()}
    )

    with pytest.raises((ReworkEvidenceError, ValidationError), match="source lineage"):
        validate_rework_evidence_freshness(recheck_input)
```

- [ ] **Step 4: 写 CheckerVerdict（检查结论）早于证据验证负例**

```python
def test_checker_review_before_current_evidence_verification_fails() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    stale_input = recheck_input.model_copy(update={"checked_at": fx.NOW - timedelta(minutes=5)})

    with pytest.raises(ReworkEvidenceError, match="checker.*after.*verified evidence"):
        validate_rework_evidence_freshness(stale_input)
```

- [ ] **Step 5: 写行为探针和 RunManifest（运行清单）负例**

```python
def test_behavioral_probe_failure_omitted_from_final_evidence_table_fails() -> None:
    recheck_input = fx.rework_input_with_behavioral_probe_failure().model_copy(
        update={"failed_final_evidence_blockers": ()}
    )

    with pytest.raises(ReworkEvidenceError, match="behavioral probe.*final evidence"):
        build_rework_final_evidence_table(recheck_input)


def test_run_commands_require_explicit_service_contracts() -> None:
    with pytest.raises(ReworkEvidenceError, match="service contracts"):
        validate_rework_run_manifest_readiness(
            fx.run_manifest_with_run_command_and_no_service_contracts(),
            active_acceptance_refs=(fx.ACCEPTANCE_REF,),
            environment_usage=(),
        )


def test_implementation_env_usage_must_be_declared_in_run_manifest() -> None:
    with pytest.raises(ReworkEvidenceError, match="undeclared environment"):
        validate_rework_run_manifest_readiness(
            fx.run_manifest_with_host_port_only(),
            active_acceptance_refs=(fx.ACCEPTANCE_REF,),
            environment_usage=(
                ReworkEnvironmentUsage(
                    source_ref="source-file.backend.app",
                    env_names=("LIBRARY_DB_PATH",),
                ),
            ),
        )
```

- [ ] **Step 6: 运行负例并确认 red**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_rework_evidence_fail_closed.py -q
```

Expected: 在实现前失败，失败原因是 `boardroom_os.rework.evidence` 或新 API 尚不存在；实现后这些负例必须通过。

---

### Task 3: 给 FinalEvidenceTable 增加可选 namespace

**Files:**
- Modify `src/boardroom_os/evidence/table.py`
- Modify `tests/evidence/test_final_evidence_table.py`

- [ ] **Step 1: 先写 namespaced table 正例测试**

在 `tests/evidence/test_final_evidence_table.py` 追加：

```python
from boardroom_os.evidence.table import EvidenceNamespaceRef


def test_final_evidence_table_can_be_namespaced_for_rework_round() -> None:
    contract = _active_contract()
    evidence = _verified_evidence(acceptance_ref="acceptance.book.add")
    namespace = EvidenceNamespaceRef(
        value="rework-evidence.run-v2-100d.rework-cycle.v2-100d.rework-attempt.v2-100d.1.g42"
    )

    table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=contract,
            verified_evidence=(evidence,),
            failed_blockers=(),
            generated_at=NOW,
            evidence_namespace_ref=namespace,
        )
    )

    assert table.evidence_namespace_ref == namespace
    assert table.final_evidence_table_id.value == (
        f"final-evidence-table.{contract.acceptance_contract_id.value}.{namespace.value}"
    )
```

若 `tests/evidence/test_final_evidence_table.py` 中现有 helper 名不同，使用该文件已有 helper 创建 active AcceptanceContract（活跃验收合同）和 VerifiedEvidence（已验证证据），但断言保持一致。

- [ ] **Step 2: 实现 EvidenceNamespaceRef（证据命名空间引用）**

在 `src/boardroom_os/evidence/table.py` 增加：

```python
class EvidenceNamespaceRef(NonEmptyTextValue):
    pass
```

- [ ] **Step 3: 实现 ID 派生 helper**

```python
def _expected_table_ref(
    acceptance_contract_ref: ContractId,
    evidence_namespace_ref: EvidenceNamespaceRef | None,
) -> FinalEvidenceTableRef:
    base = f"final-evidence-table.{acceptance_contract_ref.value}"
    if evidence_namespace_ref is None:
        return FinalEvidenceTableRef(value=base)
    return FinalEvidenceTableRef(value=f"{base}.{evidence_namespace_ref.value}")
```

- [ ] **Step 4: 给 FinalEvidenceTable 和 input 增加字段**

在 `FinalEvidenceTable`（最终证据表）现有字段块中加入：

```python
evidence_namespace_ref: EvidenceNamespaceRef | None = None
```

在 `FinalEvidenceTableInput`（最终证据表输入）现有字段块中加入：

```python
evidence_namespace_ref: EvidenceNamespaceRef | None = None
```

更新 `_normalize_refs` 和 `_validate_derived_fields` 使用 `_expected_table_ref(...)`。

- [ ] **Step 5: 更新 builder 透传 namespace**

```python
return FinalEvidenceTable(
    acceptance_contract_ref=contract.acceptance_contract_id,
    evidence_namespace_ref=table_input.evidence_namespace_ref,
    generated_at=table_input.generated_at,
    rows=tuple(rows),
)
```

将 `EvidenceNamespaceRef` 加入 `__all__`。

- [ ] **Step 6: 运行 FinalEvidenceTable 测试**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/evidence/test_final_evidence_table.py -q
```

Expected: 现有未命名空间 ID 测试仍通过，新 namespace 测试通过。

---

### Task 4: 实现 ReworkEvidence models 和 freshness validators

**Files:**
- Create `src/boardroom_os/rework/evidence.py`

- [ ] **Step 1: 创建模块 imports 和错误类型**

```python
from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.checker.checker import CheckerService, CheckerServiceInput
from boardroom_os.checker.verdict import CheckerVerdict, SourceDiffRef
from boardroom_os.closeout.gate import CloseoutGate, CloseoutGateInput, CloseoutGateResult
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.evidence.claim import EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    EvidenceNamespaceRef,
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import EvidenceVerificationResult, VerifiedEvidence
from boardroom_os.execution.work_product import WorkProduct
from boardroom_os.rework.model import (
    BlockerRef,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    RunId,
)
from boardroom_os.workspace.assembler import PackageAssembly
from boardroom_os.workspace.run_manifest import RunManifest, RunManifestCommandKind
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFileRecord,
    SourceInventory,
    SourceLineageRecord,
    build_source_inventory,
)


class ReworkEvidenceError(ValueError):
    pass
```

- [ ] **Step 2: 实现 namespace 和 input/result models**

```python
class ReworkEvidenceNamespace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId
    cycle_id: ReworkCycleId | str
    rework_attempt_id: ReworkAttemptId
    graph_version: int = Field(gt=0)
    config_hash_refs: tuple[str, ...]

    @field_validator("config_hash_refs")
    @classmethod
    def _reject_empty_or_duplicate_config_hash_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ReworkEvidenceError("config_hash_refs must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ReworkEvidenceError("config_hash_refs must be unique")
        return normalized


def rework_evidence_namespace_ref(namespace: ReworkEvidenceNamespace) -> EvidenceNamespaceRef:
    cycle_id = namespace.cycle_id.value if hasattr(namespace.cycle_id, "value") else str(namespace.cycle_id)
    return EvidenceNamespaceRef(
        value=(
            "rework-evidence."
            f"{namespace.run_id.value}."
            f"{cycle_id}."
            f"{namespace.rework_attempt_id.value}."
            f"g{namespace.graph_version}"
        )
    )
```

```python
class ReworkEnvironmentUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str
    env_names: tuple[str, ...]

    @field_validator("source_ref")
    @classmethod
    def _reject_empty_source_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ReworkEvidenceError("source_ref must not be empty")
        return normalized

    @field_validator("env_names")
    @classmethod
    def _reject_empty_or_duplicate_env_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ReworkEvidenceError("env_names must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ReworkEvidenceError("env_names must be unique")
        return normalized


class ReworkCloseoutRecheckContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    closeout_input: CloseoutGateInput
```

```python
class ReworkEvidenceRecheckInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    attempt: ReworkAttempt
    namespace: ReworkEvidenceNamespace
    active_acceptance_contract: AcceptanceContract
    active_package_contract: PackageContract
    package_assembly: PackageAssembly
    package_commit_ref: PackageCommitRef
    source_files: tuple[SourceFileRecord, ...]
    source_lineage_records: tuple[SourceLineageRecord, ...]
    evidence_verification_results: tuple[EvidenceVerificationResult, ...]
    failed_final_evidence_blockers: tuple[FinalEvidenceBlocker, ...] = ()
    target_blocker_refs: tuple[BlockerRef, ...]
    work_product: WorkProduct
    source_diff_ref: SourceDiffRef
    run_manifest: RunManifest
    environment_usage: tuple[ReworkEnvironmentUsage, ...] = ()
    checked_at: datetime
    closeout_context: ReworkCloseoutRecheckContext | None = None

    @model_validator(mode="after")
    def _validate_attempt_namespace(self) -> Self:
        if self.namespace.rework_attempt_id != self.attempt.rework_attempt_id:
            raise ReworkEvidenceError("namespace rework_attempt_id must match attempt")
        if not self.target_blocker_refs:
            raise ReworkEvidenceError("target_blocker_refs must not be empty")
        return self
```

```python
class ReworkEvidenceRecheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    namespace: ReworkEvidenceNamespace
    attempt_ref: ReworkAttemptId
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    closeout_gate_result: CloseoutGateResult | None = None
    status: ReworkOutcomeStatus
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    checked_refs: tuple[str, ...]
    rejected_stale_refs: tuple[str, ...] = ()
    created_at: datetime

    def to_rework_outcome(self) -> ReworkOutcome:
        return ReworkOutcome(
            rework_outcome_id=ReworkOutcomeId(value=f"rework-outcome.{self.attempt_ref.value}"),
            rework_attempt_ref=self.attempt_ref,
            final_evidence_table_ref=self.final_evidence_table.final_evidence_table_id.value,
            source_inventory_ref=self.source_inventory.source_inventory_id.value,
            checker_verdict_ref=self.checker_verdict.checker_verdict_id.value,
            closeout_gate_ref=(
                self.closeout_gate_result.closeout_gate_result_id.value
                if self.closeout_gate_result is not None
                else None
            ),
            status=self.status,
            remaining_blocker_refs=self.remaining_blocker_refs,
            accepted_blocker_refs=self.accepted_blocker_refs,
            created_at=self.created_at,
        )
```

- [ ] **Step 3: 实现 freshness validators**

```python
def validate_rework_attempt_fact_refs(attempt: ReworkAttempt) -> ReworkAttempt:
    if not attempt.provider_attempt_refs:
        raise ReworkEvidenceError("rework attempt requires provider_attempt_refs")
    if not attempt.command_evidence_refs:
        raise ReworkEvidenceError("rework attempt requires command_evidence_refs")
    if not attempt.source_lineage_refs:
        raise ReworkEvidenceError("rework attempt requires source_lineage_refs")
    if not attempt.workspace_mutation_refs:
        raise ReworkEvidenceError("rework attempt requires workspace_mutation_refs")
    return attempt


def _verified_evidence(results: tuple[EvidenceVerificationResult, ...]) -> tuple[VerifiedEvidence, ...]:
    return tuple(result.verified_evidence for result in results if result.verified_evidence is not None)


def validate_rework_evidence_freshness(recheck_input: ReworkEvidenceRecheckInput) -> None:
    validate_rework_attempt_fact_refs(recheck_input.attempt)
    namespace_ref = rework_evidence_namespace_ref(recheck_input.namespace).value
    provider_attempt_refs = {ref.value for ref in recheck_input.attempt.provider_attempt_refs}
    current_evidence = _verified_evidence(recheck_input.evidence_verification_results)
    if not current_evidence:
        raise ReworkEvidenceError("rework evidence verification requires current verified evidence")

    for evidence in current_evidence:
        if evidence.producer_attempt_ref.value not in provider_attempt_refs:
            raise ReworkEvidenceError("verified evidence producer_attempt_ref is not from current attempt")
        if namespace_ref not in evidence.verified_evidence_id.value:
            raise ReworkEvidenceError("verified evidence ref must include rework namespace")
        if evidence.verified_at > recheck_input.checked_at:
            raise ReworkEvidenceError("checker verdict must be after current verified evidence")

    current_evidence_refs = {evidence.verified_evidence_id.value for evidence in current_evidence}
    for lineage in recheck_input.source_lineage_records:
        if lineage.producer_attempt_ref.value not in provider_attempt_refs:
            raise ReworkEvidenceError("source lineage producer_attempt_ref is not from current attempt")
        lineage_evidence_refs = {ref.value for ref in lineage.evidence_refs}
        if not lineage_evidence_refs.issubset(current_evidence_refs):
            raise ReworkEvidenceError("source lineage evidence_refs are not from current attempt")
```

```python
def validate_rework_final_evidence_table_freshness(
    table: FinalEvidenceTable,
    *,
    namespace: ReworkEvidenceNamespace,
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> FinalEvidenceTable:
    namespace_ref = rework_evidence_namespace_ref(namespace)
    if table.evidence_namespace_ref != namespace_ref:
        raise ReworkEvidenceError("final evidence table namespace mismatch")
    current_evidence_refs = {evidence.verified_evidence_id.value for evidence in verified_evidence}
    table_evidence_refs = {
        ref.value
        for row in table.rows
        for ref in row.verified_evidence_refs
    }
    if not table_evidence_refs.issubset(current_evidence_refs):
        raise ReworkEvidenceError("final evidence table contains stale verified evidence refs")
    return table
```

- [ ] **Step 4: 实现 RunManifest readiness（运行清单准备性）校验**

```python
def validate_rework_run_manifest_readiness(
    run_manifest: RunManifest,
    *,
    active_acceptance_refs: tuple[AcceptanceRef, ...],
    environment_usage: tuple[ReworkEnvironmentUsage, ...],
) -> None:
    run_commands = tuple(
        command for command in run_manifest.commands if command.kind is RunManifestCommandKind.RUN
    )
    if run_commands and not run_manifest.service_contracts:
        raise ReworkEvidenceError("run commands require explicit service contracts")

    active_acceptance_ref_values = {ref.value for ref in active_acceptance_refs}
    for probe in run_manifest.behavioral_probes or ():
        for acceptance_ref in probe.acceptance_refs:
            if acceptance_ref.value not in active_acceptance_ref_values:
                raise ReworkEvidenceError("behavioral probe acceptance_ref is not active")

    declared_env_names = {
        binding.name
        for service in run_manifest.service_contracts or ()
        for binding in service.env_bindings
    }
    observed_env_names = {env_name for usage in environment_usage for env_name in usage.env_names}
    undeclared = observed_env_names - declared_env_names
    if undeclared:
        names = ", ".join(sorted(undeclared))
        raise ReworkEvidenceError(f"undeclared environment usage: {names}")
```

- [ ] **Step 5: 导出 public names**

在 `src/boardroom_os/rework/evidence.py` 添加 `__all__`，包含 Public API Target 列出的所有名称。

- [ ] **Step 6: 运行 V2-100D evidence 负例**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_rework_evidence_fail_closed.py -q
```

Expected: 负例通过。

---

### Task 5: 重建 SourceInventory / FinalEvidenceTable / CheckerVerdict

**Files:**
- Modify `src/boardroom_os/rework/evidence.py`
- Create `tests/rework/test_rework_evidence_recheck.py`

- [ ] **Step 1: 写正例测试**

```python
from boardroom_os.checker.verdict import CheckerVerdictStatus
from boardroom_os.evidence.table import FinalEvidenceStatus
from boardroom_os.rework.evidence import recheck_rework_attempt, rework_evidence_namespace_ref
from boardroom_os.rework.model import ReworkOutcomeStatus
from tests.rework.fixtures import rework_evidence as fx


def test_rework_attempt_rebuilds_source_inventory_table_and_checker() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    result = recheck_rework_attempt(recheck_input)
    namespace_ref = rework_evidence_namespace_ref(recheck_input.namespace)

    assert result.final_evidence_table.evidence_namespace_ref == namespace_ref
    assert all(row.status is FinalEvidenceStatus.SATISFIED for row in result.final_evidence_table.rows)
    assert result.source_inventory.entries
    assert result.checker_verdict.status is CheckerVerdictStatus.APPROVED
    assert result.status is ReworkOutcomeStatus.ACCEPTED
    assert result.accepted_blocker_refs == (fx.TARGET_BLOCKER_REF,)

    outcome = result.to_rework_outcome()
    assert outcome.status is ReworkOutcomeStatus.ACCEPTED
    assert outcome.final_evidence_table_ref == result.final_evidence_table.final_evidence_table_id.value
```

- [ ] **Step 2: 实现 SourceInventory（源码清单）重建**

```python
def build_rework_source_inventory(recheck_input: ReworkEvidenceRecheckInput) -> SourceInventory:
    validate_rework_evidence_freshness(recheck_input)
    return build_source_inventory(
        package_assembly=recheck_input.package_assembly,
        package_contract=recheck_input.active_package_contract,
        package_commit_ref=recheck_input.package_commit_ref,
        source_files=recheck_input.source_files,
        lineage_records=recheck_input.source_lineage_records,
    )
```

- [ ] **Step 3: 实现 FinalEvidenceTable（最终证据表）重建**

```python
def _behavioral_probe_acceptance_refs(run_manifest: RunManifest) -> set[str]:
    return {
        acceptance_ref.value
        for probe in run_manifest.behavioral_probes or ()
        for acceptance_ref in probe.acceptance_refs
    }


def _verified_live_acceptance_refs(verified_evidence: tuple[VerifiedEvidence, ...]) -> set[str]:
    return {
        acceptance_ref.value
        for evidence in verified_evidence
        if evidence.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
        for acceptance_ref in evidence.acceptance_refs
    }


def _failed_blocker_acceptance_refs(blockers: tuple[FinalEvidenceBlocker, ...]) -> set[str]:
    return {blocker.acceptance_ref.value for blocker in blockers}


def _validate_behavioral_probe_coverage(recheck_input: ReworkEvidenceRecheckInput) -> None:
    verified = _verified_evidence(recheck_input.evidence_verification_results)
    probe_refs = _behavioral_probe_acceptance_refs(recheck_input.run_manifest)
    covered = _verified_live_acceptance_refs(verified) | _failed_blocker_acceptance_refs(
        recheck_input.failed_final_evidence_blockers
    )
    missing = probe_refs - covered
    if missing:
        raise ReworkEvidenceError("behavioral probe failure must be represented in final evidence")
```

```python
def build_rework_final_evidence_table(recheck_input: ReworkEvidenceRecheckInput) -> FinalEvidenceTable:
    validate_rework_evidence_freshness(recheck_input)
    validate_rework_run_manifest_readiness(
        recheck_input.run_manifest,
        active_acceptance_refs=tuple(
            criterion.acceptance_ref for criterion in recheck_input.active_acceptance_contract.criteria
        ),
        environment_usage=recheck_input.environment_usage,
    )
    _validate_behavioral_probe_coverage(recheck_input)
    verified = _verified_evidence(recheck_input.evidence_verification_results)
    table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=recheck_input.active_acceptance_contract,
            verified_evidence=verified,
            failed_blockers=recheck_input.failed_final_evidence_blockers,
            generated_at=recheck_input.checked_at,
            evidence_namespace_ref=rework_evidence_namespace_ref(recheck_input.namespace),
        )
    )
    return validate_rework_final_evidence_table_freshness(
        table,
        namespace=recheck_input.namespace,
        verified_evidence=verified,
    )
```

- [ ] **Step 4: 实现 CheckerVerdict（检查结论）重建**

```python
def build_rework_checker_verdict(
    recheck_input: ReworkEvidenceRecheckInput,
    final_evidence_table: FinalEvidenceTable,
) -> CheckerVerdict:
    validate_rework_evidence_freshness(recheck_input)
    return CheckerService().review(
        CheckerServiceInput(
            ticket_ref=recheck_input.attempt.ticket_ref,
            work_product=recheck_input.work_product,
            source_diff_ref=recheck_input.source_diff_ref,
            active_acceptance_contract=recheck_input.active_acceptance_contract,
            final_evidence_table=final_evidence_table,
            notes=(),
            checker_blockers=(),
            checked_at=recheck_input.checked_at,
        )
    )
```

- [ ] **Step 5: 实现 recheck orchestration（重验编排）**

```python
def _blocker_refs_from_checker(verdict: CheckerVerdict) -> tuple[BlockerRef, ...]:
    return tuple(BlockerRef(value=blocker.blocker_id.value) for blocker in verdict.blockers if blocker.blocker_id)


def recheck_rework_attempt(recheck_input: ReworkEvidenceRecheckInput) -> ReworkEvidenceRecheckResult:
    source_inventory = build_rework_source_inventory(recheck_input)
    final_evidence_table = build_rework_final_evidence_table(recheck_input)
    checker_verdict = build_rework_checker_verdict(recheck_input, final_evidence_table)
    closeout_gate_result = evaluate_rework_closeout(
        recheck_input,
        source_inventory,
        final_evidence_table,
        checker_verdict,
    )

    remaining = _blocker_refs_from_checker(checker_verdict)
    if closeout_gate_result is not None:
        remaining = remaining + tuple(
            BlockerRef(value=blocker.blocker_id.value)
            for blocker in closeout_gate_result.blockers
            if blocker.blocker_id is not None
        )

    if remaining:
        status = ReworkOutcomeStatus.REWORK_REQUIRED
        accepted = ()
    else:
        status = ReworkOutcomeStatus.ACCEPTED
        accepted = recheck_input.target_blocker_refs

    return ReworkEvidenceRecheckResult(
        namespace=recheck_input.namespace,
        attempt_ref=recheck_input.attempt.rework_attempt_id,
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        closeout_gate_result=closeout_gate_result,
        status=status,
        remaining_blocker_refs=remaining,
        accepted_blocker_refs=accepted,
        checked_refs=tuple(
            dict.fromkeys(
                (
                    source_inventory.source_inventory_id.value,
                    final_evidence_table.final_evidence_table_id.value,
                    checker_verdict.checker_verdict_id.value,
                    *(closeout_gate_result.checked_refs if closeout_gate_result else ()),
                )
            )
        ),
        created_at=recheck_input.checked_at,
    )
```

- [ ] **Step 6: 运行正例**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/rework/test_rework_evidence_recheck.py -q
```

Expected: 当前轮证据重建链通过，且 ReworkOutcome.accepted_blocker_refs（返工结果已接受阻塞项引用）来自 `target_blocker_refs`。

---

### Task 6: 强化 closeout same-run fact chain

**Files:**
- Modify `src/boardroom_os/rework/evidence.py`
- Modify `tests/rework/fixtures/rework_evidence.py`
- Create `tests/negative/test_rework_closeout_fail_closed.py`
- Create `tests/rework/test_rework_closeout_fact_chain.py`

- [ ] **Step 0.5: 补齐 closeout-ready fact chain fixture（收尾就绪事实链夹具）**

Task 5 的 `build_rework_source_inventory()`（返工源码清单构建器）、`build_rework_final_evidence_table()`（返工最终证据表构建器）和 `build_rework_checker_verdict()`（返工检查结论构建器）可用后，回到 `tests/rework/fixtures/rework_evidence.py` 实现：

先实现 `closeout_gate_input(...)`，它必须一次性构造完整 CloseoutGateInput（收尾门禁输入）事实链，而不是只把 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）和 CheckerVerdict（检查结论）塞进 gate（门禁）：

- 从当前 `recheck_input` 读取 active PackageContract（活跃包合同）、RunManifest（运行清单）和 VerifiedEvidence（已验证证据）。
- 构造至少一个 `VerificationRun`（验证运行）覆盖 test command（测试命令），状态为 `PASSED` 且 `exit_code=0`。
- 构造至少一个 `ServiceRunEvidence`（服务运行证据）覆盖 run command（运行命令），readiness probe（就绪探针）状态码为 2xx，并与 RunManifest command id / command / cwd（命令标识/命令/工作目录）一致。
- 调用现有 `build_workspace_evidence_bundle()`（工作区证据包构建器），确保 bundle（包）引用当前 SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）、ServiceRunEvidence（服务运行证据）、VerifiedEvidence（已验证证据）和 FinalEvidenceTable（最终证据表）。
- 调用现有 `validate_run_manifest_binding()`（运行清单绑定校验器）为每个 declared command（声明命令）生成 `CloseoutCommandEvidenceBinding`（收尾命令证据绑定）；run command（运行命令）绑定 ServiceRunEvidence（服务运行证据），test command（测试命令）绑定 VerificationRun（验证运行）。
- 组装 `provider_attempt_refs`（模型调用尝试引用），必须覆盖所有 VerifiedEvidence（已验证证据）和 verified artifacts（已验证产物）的 producer attempt（产出模型调用尝试），且无重复。
- 组装 `ReplayBundleReadiness`（重放包就绪）、`GitAuditReadiness`（Git 审计就绪）和 `ProcessAuditReadiness`（流程审计就绪），所有 readiness flags（就绪标志）必须为通过状态；`GitAuditReadiness.final_commit_sha`（最终提交 SHA）必须匹配 `SourceInventory.package_commit_ref`（源码清单包提交引用）的 `package-commit.<sha>`。
- 所有 generated ids/refs（生成标识/引用）必须包含当前 namespace（命名空间）或当前 run/cycle/attempt（运行/循环/尝试）段。若某个现有 helper（辅助函数）默认生成非命名空间 ref（引用），必须用真实 `model_copy(update=...)` 重写为当前命名空间值，而不是接受旧 ref。

此步骤可参考 `tests/closeout/test_closeout_gate.py::_ready_input()` 的对象关系，但不得 import（导入）该 private helper（私有辅助函数）。`tests/proving/fixtures/tiny_closeout.py` 也只能作为字段覆盖范围参考，不得把其非当前 namespace（命名空间）的对象直接作为 V2-100D closeout passed（收尾通过）证据。

```python
def fresh_recheck_parts() -> FreshRecheckParts:
    recheck_input = rework_input_with_verified_evidence()
    source_inventory = build_rework_source_inventory(recheck_input)
    final_evidence_table = build_rework_final_evidence_table(recheck_input)
    checker_verdict = build_rework_checker_verdict(recheck_input, final_evidence_table)
    old_source_inventory = source_inventory.model_copy(
        update={"source_inventory_id": SourceInventoryRef(value="source-inventory.old-run")}
    )
    old_namespace = EvidenceNamespaceRef(value="rework-evidence.run-old.cycle-old.attempt-old.g1")
    old_final_evidence_table = final_evidence_table.model_copy(
        update={
            "evidence_namespace_ref": old_namespace,
            "final_evidence_table_id": FinalEvidenceTableRef(
                value=f"final-evidence-table.{ACCEPTANCE_CONTRACT_REF.value}.{old_namespace.value}"
            ),
        }
    )
    old_checker_verdict = checker_verdict.model_copy(
        update={"final_evidence_table_ref": old_final_evidence_table.final_evidence_table_id}
    )
    return FreshRecheckParts(
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        old_source_inventory=old_source_inventory,
        old_final_evidence_table=old_final_evidence_table,
        old_checker_verdict=old_checker_verdict,
    )


def rework_input_with_closeout_context(*, old_run_manifest: bool = False) -> ReworkEvidenceRecheckInput:
    recheck_input = rework_input_with_verified_evidence()
    parts = fresh_recheck_parts()
    run_manifest_for_closeout = (
        old_run_manifest_with_service_and_probe() if old_run_manifest else recheck_input.run_manifest
    )
    closeout_input = closeout_gate_input(
        recheck_input=recheck_input,
        source_inventory=parts.source_inventory,
        final_evidence_table=parts.final_evidence_table,
        checker_verdict=parts.checker_verdict,
        run_manifest=run_manifest_for_closeout,
    )
    return recheck_input.model_copy(
        update={
            "closeout_context": ReworkCloseoutRecheckContext(closeout_input=closeout_input),
        }
    )
```

补齐上述代码需要在 fixture 文件导入 `build_rework_source_inventory`（返工源码清单构建器）、`build_rework_final_evidence_table`（返工最终证据表构建器）、`build_rework_checker_verdict`（返工检查结论构建器）、`ReworkCloseoutRecheckContext`（返工收尾重验上下文）、`EvidenceNamespaceRef`（证据命名空间引用）、`FinalEvidenceTableRef`（最终证据表引用）、`SourceInventoryRef`（源码清单引用）以及本文件内的 `closeout_gate_input()` 和 `old_run_manifest_with_service_and_probe()` helper（辅助函数）。`old_run_manifest=True` 只能替换 CloseoutGateInput（收尾门禁输入）内嵌的 RunManifest（运行清单），不得覆盖外层 `recheck_input.run_manifest`（重验输入运行清单）；这样才能制造当前 attempt（尝试）和 closeout context（收尾上下文）的 run manifest namespace mismatch（运行清单命名空间不一致）。这些 helper 必须构造真实 CloseoutGateInput（收尾门禁输入）和 RunManifest（运行清单），不得返回占位对象。

- [ ] **Step 1: 写 closeout stale ref 负例**

```python
import pytest

from boardroom_os.rework.evidence import ReworkEvidenceError, evaluate_rework_closeout
from tests.rework.fixtures import rework_evidence as fx


def test_rework_closeout_rejects_old_run_manifest_ref() -> None:
    recheck_input = fx.rework_input_with_closeout_context(old_run_manifest=True)
    fresh = fx.fresh_recheck_parts()

    with pytest.raises(ReworkEvidenceError, match="run manifest namespace"):
        evaluate_rework_closeout(recheck_input, fresh.source_inventory, fresh.final_evidence_table, fresh.checker_verdict)


def test_rework_closeout_rejects_old_source_inventory() -> None:
    recheck_input = fx.rework_input_with_closeout_context()
    fresh = fx.fresh_recheck_parts()

    with pytest.raises(ReworkEvidenceError, match="source inventory namespace"):
        evaluate_rework_closeout(recheck_input, fresh.old_source_inventory, fresh.final_evidence_table, fresh.checker_verdict)


def test_rework_closeout_rejects_old_checker_verdict() -> None:
    recheck_input = fx.rework_input_with_closeout_context()
    fresh = fx.fresh_recheck_parts()

    with pytest.raises(ReworkEvidenceError, match="checker verdict namespace"):
        evaluate_rework_closeout(recheck_input, fresh.source_inventory, fresh.final_evidence_table, fresh.old_checker_verdict)
```

- [ ] **Step 2: 写 closeout 正例**

```python
from boardroom_os.closeout.gate import CloseoutGateVerdict
from boardroom_os.rework.evidence import recheck_rework_attempt
from boardroom_os.rework.model import ReworkOutcomeStatus
from tests.rework.fixtures import rework_evidence as fx


def test_rework_closeout_consumes_current_attempt_fact_chain() -> None:
    result = recheck_rework_attempt(fx.rework_input_with_closeout_context())

    assert result.closeout_gate_result is not None
    assert result.closeout_gate_result.verdict is CloseoutGateVerdict.PASSED
    assert result.status is ReworkOutcomeStatus.ACCEPTED
    assert result.final_evidence_table.final_evidence_table_id.value in result.checked_refs
    assert result.source_inventory.source_inventory_id.value in result.checked_refs
```

- [ ] **Step 3: 实现 closeout freshness validator**

```python
def _namespace_value(recheck_input: ReworkEvidenceRecheckInput) -> str:
    return rework_evidence_namespace_ref(recheck_input.namespace).value


def _require_ref_contains_namespace(ref_value: str, namespace_value: str, label: str) -> None:
    if namespace_value not in ref_value:
        raise ReworkEvidenceError(f"{label} namespace mismatch")


def _validate_closeout_context_freshness(
    recheck_input: ReworkEvidenceRecheckInput,
    source_inventory: SourceInventory,
    final_evidence_table: FinalEvidenceTable,
    checker_verdict: CheckerVerdict,
) -> CloseoutGateInput:
    if recheck_input.closeout_context is None:
        raise ReworkEvidenceError("closeout_context is required for closeout recheck")
    gate_input = recheck_input.closeout_context.closeout_input
    namespace_value = _namespace_value(recheck_input)
    _require_ref_contains_namespace(final_evidence_table.final_evidence_table_id.value, namespace_value, "final evidence table")
    _require_ref_contains_namespace(checker_verdict.checker_verdict_id.value, namespace_value, "checker verdict")
    if gate_input.run_manifest.run_manifest_id != recheck_input.run_manifest.run_manifest_id:
        raise ReworkEvidenceError("run manifest namespace mismatch")
    if gate_input.source_inventory != source_inventory:
        raise ReworkEvidenceError("source inventory namespace mismatch")
    if gate_input.final_evidence_table != final_evidence_table:
        raise ReworkEvidenceError("final evidence table namespace mismatch")
    if gate_input.checker_verdict != checker_verdict:
        raise ReworkEvidenceError("checker verdict namespace mismatch")

    current_evidence_refs = {
        evidence.verified_evidence_id.value
        for evidence in _verified_evidence(recheck_input.evidence_verification_results)
    }
    inventory_evidence_refs = {
        ref.value
        for entry in source_inventory.entries
        for ref in entry.evidence_refs
    }
    if not inventory_evidence_refs.issubset(current_evidence_refs):
        raise ReworkEvidenceError("source inventory namespace mismatch")
    return gate_input


def evaluate_rework_closeout(
    recheck_input: ReworkEvidenceRecheckInput,
    source_inventory: SourceInventory,
    final_evidence_table: FinalEvidenceTable,
    checker_verdict: CheckerVerdict,
) -> CloseoutGateResult | None:
    if recheck_input.closeout_context is None:
        return None
    gate_input = _validate_closeout_context_freshness(
        recheck_input,
        source_inventory,
        final_evidence_table,
        checker_verdict,
    )
    return CloseoutGate().evaluate(gate_input)
```

注意：`PackageCommitRef`（包提交引用）必须保持真实提交语义，不得被塞入返工命名空间。SourceInventory（源码清单）的新鲜度通过当前 source lineage（源码来源链）、provider attempts（模型调用尝试）、verified evidence refs（已验证证据引用）和 CloseoutGateInput（收尾门禁输入）对象一致性证明。

- [ ] **Step 4: 运行 closeout 测试**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_rework_closeout_fail_closed.py \
  tests/rework/test_rework_closeout_fact_chain.py \
  -q
```

Expected: stale fact-chain（陈旧事实链）负例失败关闭，当前轮 closeout fact-chain（收尾事实链）正例通过。

---

### Task 7: 导出 API 并跑回归

**Files:**
- Modify `src/boardroom_os/rework/__init__.py`

- [ ] **Step 1: 导出 V2-100D API**

```python
from boardroom_os.rework.evidence import (
    ReworkCloseoutRecheckContext,
    ReworkEnvironmentUsage,
    ReworkEvidenceError,
    ReworkEvidenceNamespace,
    ReworkEvidenceRecheckInput,
    ReworkEvidenceRecheckResult,
    build_rework_checker_verdict,
    build_rework_final_evidence_table,
    build_rework_source_inventory,
    evaluate_rework_closeout,
    recheck_rework_attempt,
    rework_evidence_namespace_ref,
    validate_rework_attempt_fact_refs,
    validate_rework_evidence_freshness,
    validate_rework_final_evidence_table_freshness,
    validate_rework_run_manifest_readiness,
)
```

把同名条目加入 `__all__`。

- [ ] **Step 2: 运行 V2-100D focused tests（聚焦测试）**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_rework_evidence_fail_closed.py \
  tests/negative/test_rework_closeout_fail_closed.py \
  tests/rework/test_rework_evidence_recheck.py \
  tests/rework/test_rework_closeout_fact_chain.py \
  -q
```

Expected: V2-100D 聚焦测试全部通过。

- [ ] **Step 3: 运行 V2-100 regression tests（回归测试）**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/negative/test_ceo_rework_planner_fail_closed.py \
  tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py \
  tests/negative/test_rework_evidence_fail_closed.py \
  tests/negative/test_rework_closeout_fail_closed.py \
  -q
```

Expected: V2-100 相关测试全部通过。

- [ ] **Step 4: 运行 evidence/checker/closeout 相关回归**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/evidence/test_final_evidence_table.py \
  tests/evidence/test_checker_verdict.py \
  tests/proving/test_source_inventory.py \
  tests/workspace/test_run_manifest_behavioral_probe.py \
  tests/workspace/test_run_manifest_service_contract.py \
  tests/closeout/test_closeout_gate.py \
  tests/negative/test_source_inventory_ref_only_rejected.py \
  tests/negative/test_run_manifest_command_coverage.py \
  tests/negative/test_missing_acceptance_map_blocks_closeout.py \
  -q
```

Expected: namespace（命名空间）扩展不破坏既有证据、检查、源码清单和收尾门禁测试。

---

### Task 8: 实施完成后的文档更新协议

**Files:**
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/04-implementation/acceptance-criteria.md`
- Modify `doc/05-project-log/2026-06.md`
- Modify `doc/04-implementation/INDEX.md` only if implementation adds more docs than this plan

- [ ] **Step 1: 更新 backlog（任务清单）**

在 `doc/04-implementation/backlog.md`：

- 将 `### V2-100D` 状态从 `TODO` 改为 `DONE`。
- 增加完成证据，列出：
  - `src/boardroom_os/rework/evidence.py`
  - `src/boardroom_os/evidence/table.py` namespace 扩展
  - V2-100D negative / happy tests（负例/正例测试）
  - 实际验证命令和 pass count（通过数量）
- 顶部 TL;DR 当前未完成工作包从 `V2-100D` 改为 `V2-100E`。
- Phase 10 进度从 `3 / 5` 改为 `4 / 5`。
- 总进度从 `72 / 75` 改为 `73 / 75`。

- [ ] **Step 2: 更新 acceptance checkbox（验收复选项）**

在 `doc/04-implementation/acceptance-criteria.md` 只勾选 V2-100D：

```markdown
- [x] AC-V2-REWORK-004 / AC-V2-EVIDENCE-002 / AC-V2-CHECKER-001（返工每轮重新进入证据和检查门禁）— 由 V2-100D 证明：...
```

不得勾选 V2-100E 或 Phase 10 前置项。

- [ ] **Step 3: 更新月度日志**

在 `doc/05-project-log/2026-06.md` 追加一个 `2026-06-14 / V2-100D` 条目，包含：

- 关键产出文件。
- 负例测试：旧 FinalEvidenceTable（最终证据表）、过早 CheckerVerdict（检查结论）、旧 CloseoutGate refs（收尾门禁引用）、缺 service contract（服务合同）、未声明 env usage（环境变量使用）。
- 正例测试：当前轮 SourceInventory / FinalEvidenceTable / CheckerVerdict / CloseoutGate chain（源码清单/最终证据表/检查结论/收尾门禁链）。
- 验证命令和 pass count（通过数量）。

- [ ] **Step 4: 增量日志建议**

若 V2-100D implementation（实施）跨多个会话或中途产生重要发现，可以在每个 Task 完成后先在 `doc/05-project-log/2026-06.md` 维护同一个 `2026-06-14 / V2-100D` 条目，按“已完成 Task / 验证命令 / 发现”增量补充。最终关闭工作包前必须去重并收敛为单条 V2-100D 日志记录，避免重复追加。

- [ ] **Step 5: decisions.md 更新规则**

只有实现改变核心架构语义时才更新 `doc/05-project-log/decisions.md`。按本计划实现 optional EvidenceNamespaceRef（可选证据命名空间引用）和 V2-100D spec（规格）内既定重验链路时，不需要新增 decision（决策记录）。

---

## Verification Commands

完成 V2-100D implementation（实施）前必须运行：

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_rework_evidence_fail_closed.py \
  tests/negative/test_rework_closeout_fail_closed.py \
  tests/rework/test_rework_evidence_recheck.py \
  tests/rework/test_rework_closeout_fact_chain.py \
  -q
```

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/negative/test_ceo_rework_planner_fail_closed.py \
  tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py \
  tests/negative/test_rework_evidence_fail_closed.py \
  tests/negative/test_rework_closeout_fail_closed.py \
  -q
```

```bash
PYTHONPATH=src:. python -m pytest \
  tests/evidence/test_final_evidence_table.py \
  tests/evidence/test_checker_verdict.py \
  tests/proving/test_source_inventory.py \
  tests/workspace/test_run_manifest_behavioral_probe.py \
  tests/workspace/test_run_manifest_service_contract.py \
  tests/closeout/test_closeout_gate.py \
  tests/negative/test_source_inventory_ref_only_rejected.py \
  tests/negative/test_run_manifest_command_coverage.py \
  tests/negative/test_missing_acceptance_map_blocks_closeout.py \
  -q
```

若准备关闭工作包，再运行更宽回归：

```bash
PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/closeout tests/rework tests/negative -q
```

---

## Self-Review

**Spec coverage（规格覆盖）:** 本计划覆盖 `v2-100-agent-team-rework-loop-spec.md` 中 V2-100D 的要求：每次 ReworkAttempt（返工尝试）重新进入 SourceInventory（源码清单）、EvidenceVerifier/VerifiedEvidence（证据验证器/已验证证据）、FinalEvidenceTableBuilder（最终证据表构建器）、CheckerService（检查服务）和必要 CloseoutGate（收尾门禁）；拒绝旧 satisfied row（已满足行）、旧 Checker approved verdict（检查通过结论）、旧 CloseoutPackage passed（收尾通过包）、旧 RunManifest（运行清单）和旧 SourceInventory（源码清单）跨轮复用；覆盖 BehavioralProbe（行为探针）、RunManifest service contract（运行清单服务合同）和 env binding（环境变量绑定）缺口。V2-100E 多轮 proving scenario（证明场景）明确留给下一包。

**Review feedback closure（评审反馈闭合）:** 已补充 `FreshRecheckParts`（新鲜重验部件）NamedTuple（命名元组）和 `fresh_recheck_parts()` fixture（测试夹具）定义，消除 Task 6 对未定义 helper（辅助函数）的依赖；已把 `rework_input_with_closeout_context()`（带收尾上下文的返工输入）移到 Task 6 Step 0.5，在 Task 5 builder（构建器）可用后用真实 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）和 CheckerVerdict（检查结论）组装 CloseoutGateInput（收尾门禁输入），避免 Task 1 循环依赖和占位成功路径；已修正 `old_run_manifest=True` 负例夹具，只替换内嵌 CloseoutGateInput.run_manifest（收尾门禁输入运行清单），不覆盖外层当前 ReworkEvidenceRecheckInput.run_manifest（返工证据重验输入运行清单），确保 run manifest namespace mismatch（运行清单命名空间不一致）会触发；已展开 `closeout_gate_input(...)`（收尾门禁输入构造器）为完整 closeout-ready fact chain（收尾就绪事实链）构造要求，明确 `verification_runs`（验证运行）、`service_run_evidence`（服务运行证据）、`final_command_bindings`（最终命令绑定）、`workspace_evidence_bundle`（工作区证据包）、`provider_attempt_refs`（模型调用尝试引用）、`replay_readiness`（重放就绪）、`git_audit_readiness`（Git 审计就绪）和 `process_audit_readiness`（流程审计就绪）都必须由当前 namespace（命名空间）事实链生成；已增强 Pre-flight（预检）、返回类型和增量日志建议。

**Placeholder scan（占位扫描）:** 本计划没有 `TBD`、`implement later`、`fill in details` 或“类似上一步”式占位；`TODO` 仅作为 backlog（任务清单）状态值出现。测试步骤、目标文件、公共 API、命令和 expected result（预期结果）均已列出。测试夹具函数给出固定函数名和约束，实施时必须返回真实 typed models（类型化模型）。

**Type consistency（类型一致性）:** Public API Target（公共 API 目标）与任务步骤一致使用 ReworkEvidenceNamespace（返工证据命名空间）、ReworkEvidenceRecheckInput（返工证据重验输入）、ReworkEvidenceRecheckResult（返工证据重验结果）、EvidenceNamespaceRef（证据命名空间引用）、ReworkAttempt（返工尝试）和 ReworkOutcome（返工结果）。`accepted_blocker_refs`（已接受阻塞项引用）来自 `target_blocker_refs`，不从 command success（命令成功）推断。PackageCommitRef（包提交引用）保持真实提交语义，不作为 namespace（命名空间）替代品。

**Hard-rule check（硬约束检查）:** 本计划没有 silent fallback（静默降级）、mocked success path（模拟成功路径）、第二套证据实现或 runtime governance（运行时治理决策）。它复用现有 EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、build_source_inventory（源码清单构建器）、CheckerService（检查服务）和 CloseoutGate（收尾门禁）作为权威入口，并把缺 ProviderAttempt（模型调用尝试记录）、缺 command evidence（命令证据）、缺 source lineage（源码来源链）、缺 acceptance map（验收映射）和旧证据复用都设计为 fail closed（失败关闭）。
