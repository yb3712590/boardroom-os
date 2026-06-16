# V2-100E Multi-Round Rework Proving Scenario Expert Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V2-100E Multi-round rework proving scenario（多轮返工证明场景），证明 V2-090K fail-closed（失败关闭）现场可以进入 CEO-governed rework loop（CEO 治理返工循环），并在真实证据下 accepted（接受）或生成 explicit escalation / exhaustion decision（显式升级 / 耗尽决策）。

**Architecture:** 新增 `boardroom_os.proving.v2_100_rework_loop`（V2-100 返工循环证明模块）作为薄编排层，复用 V2-100A-D 已存在的 ReworkRequest（返工请求）、CeoReworkPlannerBoundary（CEO 返工规划边界）、GraphPatchReviewerOutput（图补丁审查输出）、ReworkReducer（返工归约器）和 `recheck_rework_attempt`（返工证据重验）。Runtime（运行时）和 script（脚本）只装载合同、调用 provider（模型供应商）、运行命令、记录事实和导出审计，不写 ReworkPlan（返工计划）、CheckerVerdict（检查结论）或 Closeout verdict（收尾结论）。

**Tech Stack:** Python 3.11+、Pydantic v2、pytest、现有 Boardroom OS V2 contracts/evidence/rework/reducers/closeout/audit modules（合同/证据/返工/归约器/收尾/审计模块）、`ProviderExecutor`（模型执行器）、`OpenAIProviderTransport`（OpenAI 模型传输）、`CommandRunner`（命令执行器）。

---

## Review Status

本文件是 V2-100E 的 expert-review plan（专家评审版实施计划）。它有意避开既有 `doc/04-implementation/v2-100e-multi-round-rework-proving-scenario-implementation-plan.md`（旧实施计划）文件名，因为旧计划在反复修改后包含与当前代码不一致的 API（应用程序接口）假设。

`doc/04-implementation/INDEX.md`（实施索引）已将旧长 plan（实施计划）标记为 `DEPRECATED / REJECTED`（已废弃 / 已否决）。实施 agent（实施智能体）不得把旧长 plan 作为任务入口、代码蓝图或事实来源；如需查阅，只能作为 rejected design notes（被否设计记录）理解为什么不采用硬编码事实源和专用 adapter（适配器）。

实施前必须由专家评审确认：

- 本计划没有把 fake/mock/deterministic provider（模拟/确定性模型供应商）作为 happy path（正向路径）成功来源。
- 本计划没有让 runner/helper（运行器/辅助器）写入 ReworkPlan（返工计划）、GraphPatchReview（图补丁审查）、CheckerVerdict（检查结论）或 CloseoutGateResult（收尾门禁结果）。
- 本计划没有把 `AgentRunResult.status == completed`（智能体运行完成）、单次 live probe（真实探针）、`--check` 或 command success（命令成功）推导为 CloseoutPackage.passed（收尾包通过）。
- 本计划的 provider JSON（模型 JSON 输出）策略与当前配置体系和 `OpenAIProviderTransport`（OpenAI 模型传输）能力闭合：`.env` 只提供 `BOARDROOM_RUNTIME_CONFIG` / `BOARDROOM_PROVIDERS_CONFIG` / `BOARDROOM_ROLES_CONFIG`（运行时/供应商/角色配置路径）和 `OPENAI_API_KEY`（密钥）等启动输入；model/base URL/timeout/response_format（模型、基础地址、超时、响应格式）必须来自 `BoardroomSettings`（Boardroom 配置聚合）按 role seat（角色席位）解析出的 YAML provider profile（供应商配置档）。V2-100E happy path 当前只允许角色绑定 YAML profile 的 `response_format: {type: json_object}`，并在适配 `OpenAIProviderTransport` 时固定使用 `chat_completions` 分支。`responses` protocol（Responses API 协议）没有在当前 adapter（适配器）中传 JSON output constraint（JSON 输出约束），不得作为 V2-100E parseable JSON（可解析 JSON）成功路径，除非先另行实现 responses JSON 支持和 adapter tests（适配器测试）。

## Scope And Non-Goals

V2-100E 负责：

- 从 `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json`（V2-090K 失败摘要）投影 ReworkRequest（返工请求）。
- 建立 resettable failing fixture（可重置失败夹具），稳定复现 response-shape mismatch（响应形状不匹配）、env binding mismatch（环境绑定不一致）、stale acceptance refs（陈旧验收引用）和 stale closeout run refs（陈旧收尾运行引用）。
- 编排多轮链路：verified blocker（已验证阻塞项）-> CEO ReworkPlan（CEO 返工计划）-> TicketGraphPatch（工单图补丁）-> multi-role reviews（多角色审查）-> reducer commit（归约器提交）-> ReworkAttempt（返工尝试）-> EvidenceVerifier / SourceInventory / FinalEvidenceTable / Checker / CloseoutGate（证据验证器 / 源码清单 / 最终证据表 / 检查者 / 收尾门禁）重验。
- 生成 audit export（审计导出），包含 events（事件）、payload refs（载荷引用）、ProviderAttempt refs（模型调用尝试引用）、command evidence refs（命令证据引用）、SourceInventory hash（源码清单哈希）和 terminal decision（终态决策）。

V2-100E 不负责：

- 修改 Rework domain model（返工领域模型）。必要字段已由 V2-100A 负责。
- 修改 ReworkReducer（返工归约器）基础状态机。必要事件和权限已由 V2-100B 负责。
- 放宽 CeoReworkPlannerBoundary（CEO 返工规划边界）或 GraphPatchReviewerOutput（图补丁审查输出）验证。V2-100C 已负责。
- 放宽 EvidenceVerifier（证据验证器）、SourceInventory（源码清单）、FinalEvidenceTableBuilder（最终证据表构建器）、CheckerService（检查服务）或 CloseoutGate（收尾门禁）。V2-100D 已负责。
- 读取 legacy runtime（旧运行时）或从 `backend/app/core/`、`doc/refactor/`、`doc/live-report/`、`doc/tests/` 推导实现。

## File Structure

Create:

- `src/boardroom_os/proving/v2_100_rework_loop.py` — public scenario API（公开场景接口）、fail-closed validators（失败关闭校验器）、real provider role call adapter（真实模型角色调用适配）、reducer event assembly（归约事件装配）、round/loop orchestration（轮次/循环编排）和 audit export（审计导出）。
- `src/boardroom_os/proving/v2_100_resettable_fixture.py` — resettable fixture（可重置夹具），只构造 deterministic input facts（确定性输入事实）和可运行最小 package（项目包），不构造成功证据。
- `scripts/run_v2_100_rework_loop_scenario.py` — CLI（命令行入口），从 `.env` 读取 config paths/secrets（配置路径/密钥），再加载权威 YAML provider profile（供应商配置档），运行 V2-100E scenario（证明场景）并导出审计。
- `tests/proving/fixtures/v2_100_resettable_rework.py` — 测试专用 fixture 变体，只用于构造负例输入和稳定的 typed facts（类型化事实）。
- `tests/proving/test_v2_100_rework_loop.py` — 正向和终态路径测试。
- `tests/negative/test_v2_100_rework_loop_fail_closed.py` — 负例测试，覆盖无 blocker、fake provider success（模拟供应商成功）、helper-written verdict（辅助器写结论）、旧证据复用、命令成功但命题错误、runtime 直接 accepted（运行时直接接受）和预算耗尽无决策。
- `tests/proving/test_v2_100_rework_loop_provider_integration.py` — 显式真实 provider integration test（模型供应商集成测试），只在 `.env` 存在且显式 opt-in（显式启用）时运行；不得 skip 后声称 V2-100E 完成。

Modify:

- `src/boardroom_os/proving/__init__.py` — 导出 V2-100E public API（公开接口）。
- `doc/04-implementation/INDEX.md` — 登记本 expert-review plan（专家评审版实施计划）和后续实现文件。

Completion-only modify after implementation and verification:

- `doc/04-implementation/backlog.md` — 仅在 V2-100E 真实完成后把 V2-100E 状态改为 `DONE`。
- `doc/04-implementation/acceptance-criteria.md` — 仅在真实完成后勾选 Phase 10 V2-100E checkbox（验收勾选）。
- `doc/05-project-log/2026-06.md` — 仅在真实完成后追加 V2-100E 证据记录。
- `doc/05-project-log/decisions.md` — 仅当实施产生新的架构/方法论决策时追加。

## Public API Target

`src/boardroom_os/proving/v2_100_rework_loop.py` must expose these names:

```python
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventPayloadRef, ProjectRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.providers.attempt import ProviderArtifactRef, ProviderAttempt
from boardroom_os.providers.openai_adapter import FileProviderOutputStore, OpenAIProviderSettings
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    GraphPatchReviewPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkProjection,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
)
from boardroom_os.rework.evidence import ReworkEvidenceRecheckInput, ReworkEvidenceRecheckResult
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchReview,
    ReworkCycleId,
    ReworkAttempt,
    ReworkOutcome,
    ReworkRequest,
    ReworkTerminationDecision,
    RunId,
    TicketGraphPatch,
)
from boardroom_os.rework.planner import CeoReworkPlannerOutput
from boardroom_os.rework.reviewer import GraphPatchReviewerOutput


class V2_100ReworkLoopError(ValueError):
    pass


class V2_100ScenarioTerminalStatus(StrEnum):
    ACCEPTED = "accepted"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"


class V2_100PayloadManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payload_ref: EventPayloadRef
    payload_kind: str
    canonical_json: str
    sha256: str


V2_100ReducerPayload = (
    ReworkRequestPayload
    | ReworkPlanPayload
    | GraphPatchReviewPayload
    | GraphPatchApprovalPayload
    | TicketCreatedPayload
    | ReworkAttemptPayload
    | ReworkReviewPayload
    | ReworkTerminalPayload
)


def canonical_payload_manifest_entry(payload_ref: EventPayloadRef, payload: V2_100ReducerPayload) -> V2_100PayloadManifestEntry:
    payload_kind = type(payload).__name__
    payload_body = payload.model_dump(mode="json")
    canonical_json = json.dumps(payload_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return V2_100PayloadManifestEntry(
        payload_ref=payload_ref,
        payload_kind=payload_kind,
        canonical_json=canonical_json,
        sha256="sha256:" + hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    )


class V2_100ProviderAttemptManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_attempt_ref: str
    provider: str
    model: str
    input_package_ref: str
    raw_output_ref: ProviderArtifactRef
    parsed_output_ref: ProviderArtifactRef
    raw_output_sha256: str
    parsed_output_sha256: str


class V2_100ScenarioInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    snapshot_summary_path: Path
    run_id: RunId
    cycle_id: ReworkCycleId
    package_contract_ref: str
    run_manifest_ref: str
    active_acceptance_refs: tuple[str, ...]
    active_source_surface_refs: tuple[str, ...]
    active_evidence_obligation_refs: tuple[str, ...]
    active_contract_refs: tuple[str, ...]
    initial_graph_version: int = Field(gt=0)
    max_rounds: int = Field(gt=0)
    provider_env_path: Path = Path(".env")
    export_root: Path | None = None
    require_real_provider: bool = True


class V2_100ScenarioRoundInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    round_index: int = Field(gt=0)
    request: ReworkRequest
    planner_output: CeoReworkPlannerOutput
    reviewer_outputs: tuple[GraphPatchReviewerOutput, ...]
    approval_set: GraphPatchApprovalSet
    rework_ticket_payload: TicketCreatedPayload
    attempt: ReworkAttempt
    recheck_input: ReworkEvidenceRecheckInput
    terminal_decision: ReworkTerminationDecision | None = None
    started_at_graph_version: int = Field(gt=0)


class V2_100ScenarioRoundResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    round_index: int
    request: ReworkRequest
    plan_output: CeoReworkPlannerOutput
    review_outputs: tuple[GraphPatchReviewerOutput, ...]
    patch: TicketGraphPatch
    approval_set: GraphPatchApprovalSet
    rework_ticket_ref: TicketId
    attempt: ReworkAttempt
    recheck_result: ReworkEvidenceRecheckResult
    outcome: ReworkOutcome
    projection: ReworkProjection
    events: tuple[EventRecord, ...]
    payload_refs: tuple[EventPayloadRef, ...]
    payload_manifest_entries: tuple[V2_100PayloadManifestEntry, ...]
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...]
    accepted_blocker_refs: tuple[BlockerRef, ...]
    remaining_blocker_refs: tuple[BlockerRef, ...]


class V2_100ScenarioAuditExport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    export_root: Path
    summary_path: Path
    event_log_path: Path
    payload_manifest_path: Path
    provider_attempts_path: Path
    evidence_summary_path: Path
    process_timeline_path: Path
    checked_refs: tuple[str, ...]


class V2_100ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    scenario_id: str
    input_hash: str
    terminal_status: V2_100ScenarioTerminalStatus
    request: ReworkRequest
    rounds: tuple[V2_100ScenarioRoundResult, ...]
    final_projection: ReworkProjection
    termination_decision: ReworkTerminationDecision | None
    payload_manifest_entries: tuple[V2_100PayloadManifestEntry, ...]
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...]
    audit_export: V2_100ScenarioAuditExport | None
    created_at: datetime


class ScenarioPayloadResolver(ReworkReducerPayloadResolver, Protocol):
    def payloads(self) -> dict[str, V2_100ReducerPayload]:
        raise NotImplementedError

    def payload_manifest_entries_for(self, events: tuple[EventRecord, ...]) -> tuple[V2_100PayloadManifestEntry, ...]:
        raise NotImplementedError


class ScenarioRoundBuild(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    round_input: V2_100ScenarioRoundInput
    payload_resolver: ScenarioPayloadResolver
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...]


class ScenarioRoundProvider(Protocol):
    def build_round(self, scenario_input: V2_100ScenarioInput, request: ReworkRequest, *, round_index: int, started_at_graph_version: int) -> ScenarioRoundBuild:
        raise NotImplementedError
```

`ScenarioRoundBuild.payload_resolver`（轮次构建载荷解析器） may contain only current-round payloads（本轮载荷）. `run_v2_100_rework_loop_scenario`（运行返工循环场景） owns the cumulative payload store（累计载荷存储） and must call `merge_payload_resolvers`（合并载荷解析器） before reducing `prior_events + round_events`（既有事件 + 本轮事件）. Direct calls to `run_v2_100_rework_round`（运行返工轮次） with non-empty `prior_events` must pass the same cumulative resolver through the optional `payload_resolver` argument.

Implementation functions to add with the exact names and signatures:

| Function | Signature |
|---|---|
| `project_snapshot_request` | `(scenario_input: V2_100ScenarioInput) -> ReworkRequest` |
| `validate_scenario_request` | `(request: ReworkRequest, scenario_input: V2_100ScenarioInput) -> ReworkRequest` |
| `validate_real_provider_attempt` | `(attempt: ProviderAttempt, *, expected_input_package_ref: str, expected_hook_ref: str) -> ProviderAttempt` |
| `validate_agent_authored_plan` | `(output: CeoReworkPlannerOutput) -> CeoReworkPlannerOutput` |
| `validate_agent_authored_review` | `(output: GraphPatchReviewerOutput) -> GraphPatchReviewerOutput` |
| `validate_round_input` | `(round_input: V2_100ScenarioRoundInput) -> V2_100ScenarioRoundInput` |
| `load_v2_100e_openai_settings` | `(scenario_input: V2_100ScenarioInput, *, seat_ref: str) -> OpenAIProviderSettings` |
| `canonical_payload_manifest_entry` | `(payload_ref: EventPayloadRef, payload: V2_100ReducerPayload) -> V2_100PayloadManifestEntry` |
| `merge_payload_resolvers` | `(*resolvers: ScenarioPayloadResolver) -> ScenarioPayloadResolver` |
| `provider_attempt_manifest_entry` | `(attempt: ProviderAttempt, *, artifact_store: FileProviderOutputStore, expected_input_package_ref: str, expected_hook_ref: str) -> V2_100ProviderAttemptManifestEntry` |
| `build_rework_reducer_events` | `(round_input: V2_100ScenarioRoundInput, *, outcome: ReworkOutcome, prior_projection: ReworkProjection \| None = None) -> tuple[EventRecord, ...]` |
| `run_v2_100_rework_round` | `(round_build: ScenarioRoundBuild, *, prior_events: tuple[EventRecord, ...] = (), payload_resolver: ScenarioPayloadResolver \| None = None) -> V2_100ScenarioRoundResult` |
| `validate_loop_budget` | `(rounds: tuple[V2_100ScenarioRoundResult, ...], *, max_rounds: int, terminal_decision: ReworkTerminationDecision \| None) -> None` |
| `run_v2_100_rework_loop_scenario` | `(scenario_input: V2_100ScenarioInput, *, round_provider: ScenarioRoundProvider \| None = None) -> V2_100ScenarioResult` |
| `export_v2_100_rework_audit` | `(result: V2_100ScenarioResult, export_root: Path) -> V2_100ScenarioAuditExport` |

Validation rules:

- `snapshot_summary_path` must exist and must be named `failure-summary.json`.
- `provider_env_path` must exist when `require_real_provider=True`; it may only supply config paths（配置路径） and secrets（密钥） such as `BOARDROOM_RUNTIME_CONFIG`、`BOARDROOM_PROVIDERS_CONFIG`、`BOARDROOM_ROLES_CONFIG` and `OPENAI_API_KEY`. Non-empty `BOARDROOM_OPENAI_*` model/config keys are stale env execution config（陈旧环境执行配置） and must be rejected to avoid a second provider config source（第二供应商配置源）.
- For V2-100E happy path, `load_v2_100e_openai_settings`（加载 V2-100E OpenAI 设置） must load `BoardroomSettings`（Boardroom 配置聚合） through `load_boardroom_settings`（加载 Boardroom 设置） and select the provider via `settings.role_slot_by_seat(seat_ref).provider_profile_ref`（按席位解析供应商配置引用） followed by `settings.provider_by_id(...)`（按 ID 取供应商配置）. It must not read `BoardroomProvidersConfig`（供应商配置集合） directly, must not use `providers[0]`（供应商列表第一个元素）, and must not depend on YAML order（YAML 顺序）. The resolved role-bound provider profile（角色绑定供应商配置档） must have `response_format == {"type": "json_object"}` and must map to `OpenAIProviderSettings.response_format == "json_object"`. `OpenAIProviderSettings.api_protocol` must be `chat_completions` as a V2-100E adapter capability boundary（适配器能力边界）, not as an env-sourced policy knob（环境来源策略开关）. This requirement is intentional because the current `responses` branch of `OpenAIProviderTransport` does not pass a JSON schema or `json_object` response format.
- `active_acceptance_refs`、`active_source_surface_refs`、`active_evidence_obligation_refs` and `active_contract_refs` must be non-empty and unique.
- Every planner/reviewer output must contain a succeeded `ProviderAttempt`（模型调用尝试记录） with `ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT`（主供应商输出） and role hook binding matching the ExecutionPackage（执行包） used for that role.
- Worker/Tester/Release DevOps（实施/测试/发布运维） attempt provider lineage（尝试模型调用来源链） must be read from `ReworkAttempt.provider_attempt_refs`（返工尝试的模型调用引用） and the provider attempt artifact store（模型调用产物存储）. Do not add a parallel `attempt_provider_attempts` tuple or any second provider-attempt truth source（第二模型调用事实源） to the V2-100E public API.
- `provider_attempt_manifest_entry`（模型调用清单条目构造） must receive expected `ExecutionPackage` ref（执行包引用） and `RolePromptHook` ref（角色提示词钩子引用） from the caller. Passing the attempt's own refs back as expected refs is a self-comparison（自我比较） and is invalid.
- `ScenarioPayloadResolver`（场景载荷解析器） must support cumulative construction when reducing `prior_events + round_events`（既有事件 + 本轮事件）. A `ScenarioRoundBuild`（轮次构建结果） may carry only current-round payloads（本轮载荷）, but the loop must merge all historical payloads referenced by prior events plus current payloads before reducer execution（归约执行）. Missing historical payloads must fail closed（失败关闭） before audit export.
- `FakeProviderTransport`（模拟模型传输） and fallback attempts are invalid for happy path. They may appear only in negative tests where validators reject them.
- A round cannot be accepted unless `recheck_rework_attempt`（返工证据重验） returns current-round SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论） and required CloseoutGateResult（收尾门禁结果）。
- `export_v2_100_rework_audit`（导出 V2-100 返工审计） must use `V2_100ScenarioResult.payload_manifest_entries`（场景结果载荷清单条目） for payload content hashes（载荷内容哈希）. It must not reconstruct payload content from `payload_refs`（载荷引用） alone.
- `provider-attempts.json`（模型调用尝试审计文件） must use `V2_100ScenarioResult.provider_attempt_manifest_entries`（场景结果模型调用清单条目）. A provider attempt ref（模型调用引用） without raw/parsed artifact refs（原始/解析产物引用） and artifact sha256（产物哈希） is not sufficient.

## Task 0: Pre-Flight, Drift Check, And Expert Review Gate

**Files:**

- Inspect: `doc/04-implementation/backlog.md`
- Inspect: `doc/04-implementation/acceptance-criteria.md`
- Inspect: `doc/04-implementation/INDEX.md`
- Inspect: `doc/04-implementation/v2-100-agent-team-rework-loop-spec.md`

- [ ] **Step 1: Record worktree state**

Run:

```bash
git status --short --branch --untracked-files=all
```

Expected: record existing changes. Do not revert unrelated changes.

- [ ] **Step 2: Confirm V2-100E is still open**

Run:

```bash
rg -n "V2-100E|Phase 10|AC-V2-REWORK-005" doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md
```

Expected: `backlog.md` shows V2-100E status `TODO`; Phase 10 V2-100E checkbox is unchecked.

- [ ] **Step 3: Confirm implementation outputs do not already exist**

Run:

```bash
test ! -e scripts/run_v2_100_rework_loop_scenario.py
test ! -e tests/proving/test_v2_100_rework_loop.py
test ! -e tests/negative/test_v2_100_rework_loop_fail_closed.py
```

Expected: all three commands exit 0 before implementation. If any command fails, stop and inspect the existing file before editing.

- [ ] **Step 4: Stop for expert review**

Before implementation, send this exact review summary to the expert reviewer:

```text
V2-100E plan is ready for expert review. It requires real provider-backed CEO/reviewer happy path through ProviderExecutor + OpenAIProviderTransport, uses fake provider only for rejected negative paths, and keeps runtime bounded to fact execution. Backlog and acceptance checkbox remain unchanged until implementation evidence exists.
Provider JSON path is intentionally restricted to role-bound provider profiles resolved through BoardroomSettings with response_format {type: json_object}; .env only supplies BOARDROOM_RUNTIME_CONFIG / BOARDROOM_PROVIDERS_CONFIG / BOARDROOM_ROLES_CONFIG and secrets. V2-100E maps each role's bound profile into the OpenAIProviderTransport chat_completions branch until responses JSON output support is implemented separately.
```

Expected: do not implement until expert review approves or requests changes.

## Task 1: Negative Tests For Proving Scenario Fail-Closed Boundaries

**Files:**

- Create: `tests/negative/test_v2_100_rework_loop_fail_closed.py`
- Test: `src/boardroom_os/proving/v2_100_rework_loop.py`

- [ ] **Step 1: Write import-level failing test**

Create `tests/negative/test_v2_100_rework_loop_fail_closed.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from boardroom_os.events.types import ProjectRef
from boardroom_os.rework.model import ReworkCycleId, RunId


SNAPSHOT = Path("examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json")


def _input(**overrides: object):
    from boardroom_os.proving.v2_100_rework_loop import V2_100ScenarioInput

    fields: dict[str, object] = {
        "project_ref": ProjectRef(value="project-tiny-fullstack"),
        "snapshot_summary_path": SNAPSHOT,
        "run_id": RunId(value="run-v2-100e"),
        "cycle_id": ReworkCycleId(value="rework-cycle.v2-100e"),
        "package_contract_ref": "package.v2-100e",
        "run_manifest_ref": "run-manifest.v2-100e",
        "active_acceptance_refs": ("acceptance.add_book",),
        "active_source_surface_refs": ("surface.backend.api",),
        "active_evidence_obligation_refs": ("evidence.add_book.live",),
        "active_contract_refs": ("acceptance.v2-100e", "package.v2-100e"),
        "initial_graph_version": 40,
        "max_rounds": 2,
        "provider_env_path": Path(".env"),
        "require_real_provider": False,
    }
    fields.update(overrides)
    return V2_100ScenarioInput(**fields)


def test_missing_snapshot_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="failure-summary.json"):
        _input(snapshot_summary_path=tmp_path / "missing.json")
```

- [ ] **Step 2: Add tests rejecting empty active refs**

Append:

```python
@pytest.mark.parametrize(
    "field_name",
    [
        "active_acceptance_refs",
        "active_source_surface_refs",
        "active_evidence_obligation_refs",
        "active_contract_refs",
    ],
)
def test_active_refs_are_required(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        _input(**{field_name: ()})


def test_duplicate_active_refs_are_rejected() -> None:
    with pytest.raises(ValueError, match="active_acceptance_refs"):
        _input(active_acceptance_refs=("acceptance.add_book", "acceptance.add_book"))
```

- [ ] **Step 3: Add test rejecting fake/fallback provider success**

Append:

```python
from datetime import UTC, datetime

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef, RolePromptHookSha256
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import ProviderArtifactRef, ProviderAttempt, ProviderAttemptOutcome, ProviderAttemptStatus


def _provider_attempt(*, provider: str = "openai", outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT) -> ProviderAttempt:
    now = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    return ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value="provider-attempt.ceo.v2-100e.1"),
        provider=provider,
        model="gpt-5.5",
        reasoning_effort="high",
        input_package_ref=ExecutionPackageRef(value="execution-package.ceo.v2-100e"),
        seat_ref=AgentSeatRef(value="seat.ceo.delivery"),
        role_prompt_hook_ref=RolePromptHookRef(value="role-prompt-hook.baseline.ceo.v1"),
        role_prompt_hook_version="v1",
        role_prompt_hook_sha256=RolePromptHookSha256(value="a" * 64),
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=outcome,
        fallback_kind=FallbackKind.PROVIDER_UNAVAILABLE if outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT else None,
        started_at=now,
        finished_at=now,
        raw_output_ref=ProviderArtifactRef(value="provider-artifact.raw.v2-100e"),
        parsed_output_ref=ProviderArtifactRef(value="provider-artifact.parsed.v2-100e"),
    )


def test_fake_provider_attempt_cannot_satisfy_happy_path() -> None:
    from boardroom_os.proving.v2_100_rework_loop import validate_real_provider_attempt

    with pytest.raises(ValueError, match="real provider"):
        validate_real_provider_attempt(
            _provider_attempt(provider="fake"),
            expected_input_package_ref="execution-package.ceo.v2-100e",
            expected_hook_ref="role-prompt-hook.baseline.ceo.v1",
        )


def test_fallback_provider_attempt_cannot_satisfy_happy_path() -> None:
    from boardroom_os.proving.v2_100_rework_loop import validate_real_provider_attempt

    with pytest.raises(ValueError, match="primary provider"):
        validate_real_provider_attempt(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
            expected_input_package_ref="execution-package.ceo.v2-100e",
            expected_hook_ref="role-prompt-hook.baseline.ceo.v1",
        )
```

- [ ] **Step 4: Add tests rejecting unsupported provider JSON settings and stale env config**

Append:

```python
def test_v2_100e_rejects_responses_protocol_until_json_output_is_supported() -> None:
    from boardroom_os.proving.v2_100_rework_loop import validate_v2_100e_provider_json_settings
    from boardroom_os.providers.openai_adapter import OpenAIProviderSettings

    settings = OpenAIProviderSettings(
        api_key="sk-test",
        base_url="https://example.invalid/v1",
        model="gpt-5.5",
        api_protocol="responses",
        response_format="json_object",
        timeout_seconds=30,
    )

    with pytest.raises(ValueError, match="chat_completions"):
        validate_v2_100e_provider_json_settings(settings)


def test_v2_100e_requires_json_object_response_format() -> None:
    from boardroom_os.proving.v2_100_rework_loop import validate_v2_100e_provider_json_settings
    from boardroom_os.providers.openai_adapter import OpenAIProviderSettings

    settings = OpenAIProviderSettings(
        api_key="sk-test",
        base_url="https://example.invalid/v1",
        model="gpt-5.5",
        api_protocol="chat_completions",
        response_format="text",
        timeout_seconds=30,
    )

    with pytest.raises(ValueError, match="json_object"):
        validate_v2_100e_provider_json_settings(settings)


def test_v2_100e_rejects_boardroom_openai_env_knobs(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_rework_loop import load_v2_100e_openai_settings

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml",
                "BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml",
                "BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml",
                "OPENAI_API_KEY=sk-test",
                "BOARDROOM_OPENAI_API_PROTOCOL=chat_completions",
            )
        ),
        encoding="utf-8",
    )
    scenario_input = _input(provider_env_path=env_file, require_real_provider=True)

    with pytest.raises(ValueError, match="stale env"):
        load_v2_100e_openai_settings(scenario_input, seat_ref="seat.ceo.delivery")


def test_v2_100e_selects_role_bound_provider_not_first_yaml_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.config.test_boardroom_config import _write_config_files
    from boardroom_os.proving.v2_100_rework_loop import load_v2_100e_openai_settings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    paths = _write_config_files(tmp_path)
    first_provider = """
  - provider_profile_id: provider.openai-compatible.first
    provider_type: openai_compatible
    provider_label: order-trap
    base_url: https://first.example.invalid/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-order-trap
    context_window_tokens: 400000
    max_output_tokens: 128000
    stream_idle_timeout_seconds: 120
    total_timeout_seconds: 600
    reasoning_effort: high
    temperature: null
    top_p: null
    presence_penalty: null
    frequency_penalty: null
    seed: null
    stop: null
    response_format:
      type: json_object
    stream_options: null
    service_tier: null
    user: boardroom-os
"""
    providers_text = paths.providers_config.read_text(encoding="utf-8")
    providers_text = providers_text.replace("providers:\n  - provider_profile_id:", "providers:\n" + first_provider + "  - provider_profile_id:", 1)
    providers_text = providers_text.replace("response_format: null", "response_format:\n      type: json_object")
    paths.providers_config.write_text(providers_text, encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                f"BOARDROOM_RUNTIME_CONFIG={paths.runtime_config.as_posix()}",
                f"BOARDROOM_PROVIDERS_CONFIG={paths.providers_config.as_posix()}",
                f"BOARDROOM_ROLES_CONFIG={paths.roles_config.as_posix()}",
                "OPENAI_API_KEY=sk-test",
            )
        ),
        encoding="utf-8",
    )
    scenario_input = _input(provider_env_path=env_file, require_real_provider=True)

    resolved = load_v2_100e_openai_settings(scenario_input, seat_ref="seat.worker.implementation")

    assert resolved.model == "gpt-5.5"
    assert resolved.model != "gpt-order-trap"
```

- [ ] **Step 5: Add tests rejecting runtime acceptance and budget exhaustion without decision**

Append:

```python
def test_runtime_direct_acceptance_is_rejected_by_reducer() -> None:
    from tests.negative.test_rework_reducer_fail_closed import _event, _payload_resolver
    from boardroom_os.events.types import ActorRef, EventType
    from boardroom_os.reducers.rework import ReworkReducer, ReworkReducerError

    events = (
        _event(EventType.REWORK_REQUESTED, 41, "payload.request"),
        _event(EventType.REWORK_ACCEPTED, 42, "payload.terminal", actor=ActorRef(value="runtime:executor")),
    )

    with pytest.raises(ReworkReducerError, match="runtime/executor/atomic-agent"):
        ReworkReducer(_payload_resolver()).reduce(events)


def test_budget_exhaustion_requires_terminal_decision() -> None:
    from boardroom_os.proving.v2_100_rework_loop import validate_loop_budget
    from types import SimpleNamespace
    from typing import cast
    from boardroom_os.proving.v2_100_rework_loop import V2_100ScenarioRoundResult

    exhausted_rounds = cast(
        tuple[V2_100ScenarioRoundResult, ...],
        (SimpleNamespace(remaining_blocker_refs=("blocker.probe-response-shape-mismatch",)),),
    )

    with pytest.raises(ValueError, match="termination decision"):
        validate_loop_budget(exhausted_rounds, max_rounds=1, terminal_decision=None)
```

- [ ] **Step 6: Run tests and verify initial failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_100_rework_loop_fail_closed.py -q --tb=short
```

Expected before implementation: FAIL with import errors for `boardroom_os.proving.v2_100_rework_loop` or missing `validate_v2_100e_provider_json_settings` / `load_v2_100e_openai_settings`.

## Task 2: Scenario Models, Snapshot Projection, And Core Validators

**Files:**

- Create: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Modify: `src/boardroom_os/proving/__init__.py`
- Test: `tests/negative/test_v2_100_rework_loop_fail_closed.py`
- Test: `tests/rework/test_v2_090k_failure_snapshot_projection.py`

- [ ] **Step 1: Implement scenario models and input validation**

Add the public API models from the “Public API Target” section. Implement `_non_empty_unique_strings`:

```python
def _non_empty_unique_strings(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized or any(not value for value in normalized):
        raise V2_100ReworkLoopError(f"{field_name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise V2_100ReworkLoopError(f"{field_name} must be unique")
    return normalized
```

Use Pydantic validators on `V2_100ScenarioInput` so each active ref field calls `_non_empty_unique_strings`.

- [ ] **Step 2: Implement `project_snapshot_request` using V2-100A projection**

```python
from datetime import UTC, datetime

from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.rework.blocker_projection import BlockerProjectionContext, project_v2_090k_failure_summary
from boardroom_os.rework.model import ReworkActorKind


def project_snapshot_request(scenario_input: V2_100ScenarioInput) -> ReworkRequest:
    path = scenario_input.snapshot_summary_path
    if not path.exists() or path.name != "failure-summary.json":
        raise V2_100ReworkLoopError("snapshot_summary_path must exist and point to failure-summary.json")
    context = BlockerProjectionContext(
        cycle_id=scenario_input.cycle_id,
        run_id=scenario_input.run_id,
        package_contract_ref=ContractId(value=scenario_input.package_contract_ref),
        run_manifest_ref=scenario_input.run_manifest_ref,
        active_acceptance_refs=tuple(AcceptanceRef(value=value) for value in scenario_input.active_acceptance_refs),
        active_source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in scenario_input.active_source_surface_refs),
        active_evidence_obligation_refs=tuple(EvidenceObligationRef(value=value) for value in scenario_input.active_evidence_obligation_refs),
        active_graph_version=scenario_input.initial_graph_version,
        requested_by_actor=ReworkActorKind.GOVERNANCE_ADAPTER,
        requested_at=datetime.now(UTC),
    )
    request = project_v2_090k_failure_summary(path, context)
    return validate_scenario_request(request, scenario_input)
```

- [ ] **Step 3: Implement request, provider config, and provider attempt validators**

```python
import os
from collections.abc import Iterator
from contextlib import contextmanager

from boardroom_os.config.boardroom import BoardroomConfigPaths, BoardroomSettings, load_boardroom_settings
from boardroom_os.providers.attempt import ProviderAttemptOutcome, ProviderAttemptStatus
from boardroom_os.providers.openai_adapter import OpenAIProviderSettings


def validate_scenario_request(request: ReworkRequest, scenario_input: V2_100ScenarioInput) -> ReworkRequest:
    if request.run_id != scenario_input.run_id:
        raise V2_100ReworkLoopError("request run_id mismatch")
    if request.cycle_id != scenario_input.cycle_id:
        raise V2_100ReworkLoopError("request cycle_id mismatch")
    if not request.issues:
        raise V2_100ReworkLoopError("request requires verified blocker issues")
    return request


def validate_v2_100e_provider_json_settings(settings: OpenAIProviderSettings) -> OpenAIProviderSettings:
    if settings.api_protocol != "chat_completions":
        raise V2_100ReworkLoopError("V2-100E provider JSON path requires chat_completions")
    if settings.response_format != "json_object":
        raise V2_100ReworkLoopError("V2-100E provider JSON path requires json_object response_format")
    return settings


def _load_v2_100e_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        raise V2_100ReworkLoopError("provider_env_path is required for real provider scenario")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    stale_keys = sorted(key for key, value in values.items() if key.startswith("BOARDROOM_OPENAI_") and value.strip())
    if stale_keys:
        raise V2_100ReworkLoopError("stale env provider config keys are not allowed: " + ", ".join(stale_keys))
    return values


def _config_paths_from_v2_100e_env(path: Path) -> BoardroomConfigPaths:
    env_values = _load_v2_100e_env_values(path)
    return BoardroomConfigPaths(
        runtime_config=Path(env_values.get("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")),
        providers_config=Path(env_values.get("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")),
        roles_config=Path(env_values.get("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")),
    )


@contextmanager
def _temporary_env_overlay(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def load_v2_100e_boardroom_settings(scenario_input: V2_100ScenarioInput) -> BoardroomSettings:
    env_values = _load_v2_100e_env_values(scenario_input.provider_env_path)
    paths = _config_paths_from_v2_100e_env(scenario_input.provider_env_path)
    with _temporary_env_overlay(env_values):
        return load_boardroom_settings(paths, env_values=env_values)


def load_v2_100e_openai_settings(scenario_input: V2_100ScenarioInput, *, seat_ref: str) -> OpenAIProviderSettings:
    env_values = _load_v2_100e_env_values(scenario_input.provider_env_path)
    settings = load_v2_100e_boardroom_settings(scenario_input)
    role_slot = settings.role_slot_by_seat(seat_ref)
    provider_profile = settings.provider_by_id(role_slot.provider_profile_ref)
    if provider_profile.response_format != {"type": "json_object"}:
        raise V2_100ReworkLoopError("V2-100E role-bound provider profile requires response_format {type: json_object}")
    api_key = env_values.get(provider_profile.api_key_env, "")
    if not api_key:
        raise V2_100ReworkLoopError("provider api key env is required")
    return validate_v2_100e_provider_json_settings(
        OpenAIProviderSettings(
            api_key=api_key,
            base_url=provider_profile.base_url,
            model=provider_profile.model,
            api_protocol="chat_completions",
            reasoning_effort=provider_profile.reasoning_effort or "high",
            response_format="json_object",
            max_output_tokens=provider_profile.max_output_tokens,
            context_window=provider_profile.context_window_tokens,
            timeout_seconds=provider_profile.total_timeout_seconds,
        )
    )


def validate_real_provider_attempt(attempt: ProviderAttempt, *, expected_input_package_ref: str, expected_hook_ref: str) -> ProviderAttempt:
    if attempt.provider.lower() in {"fake", "mock", "deterministic"}:
        raise V2_100ReworkLoopError("real provider attempt is required")
    if attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise V2_100ReworkLoopError("provider attempt must be succeeded")
    if attempt.outcome is not ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT:
        raise V2_100ReworkLoopError("primary provider output is required")
    if attempt.input_package_ref.value != expected_input_package_ref:
        raise V2_100ReworkLoopError("provider input package mismatch")
    if attempt.role_prompt_hook_ref.value != expected_hook_ref:
        raise V2_100ReworkLoopError("provider role prompt hook mismatch")
    return attempt
```

`load_v2_100e_openai_settings`（加载 V2-100E OpenAI 设置） is the only V2-100E path from local config to `OpenAIProviderTransport`（OpenAI 模型传输）. It must resolve provider config through `BoardroomSettings.role_slot_by_seat(seat_ref)`（按席位取角色配置） and `BoardroomSettings.provider_by_id(...)`（按 ID 取供应商配置） so role binding（角色绑定） remains the authority. It may map YAML `response_format: {type: json_object}`（YAML 响应格式） into `OpenAIProviderSettings.response_format == "json_object"`（OpenAI 设置响应格式）, but it must not accept model/base URL/timeout/protocol from `BOARDROOM_OPENAI_*` env keys, must not read `BoardroomProvidersConfig`（供应商配置集合） directly, and must not select `providers[0]`（供应商列表第一个元素）.

- [ ] **Step 4: Export names from package init**

Modify `src/boardroom_os/proving/__init__.py`:

```python
from boardroom_os.proving.v2_100_rework_loop import (
    V2_100ReworkLoopError,
    V2_100ScenarioInput,
    V2_100ScenarioResult,
    project_snapshot_request,
    run_v2_100_rework_loop_scenario,
)
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_100_rework_loop_fail_closed.py tests/rework/test_v2_090k_failure_snapshot_projection.py -q
```

Expected after Task 2: the input/projection/provider-validator tests pass; later round orchestration tests are not present yet.

## Task 3: Resettable Fixture With Real Evidence Gate Inputs

**Files:**

- Create: `src/boardroom_os/proving/v2_100_resettable_fixture.py`
- Create: `tests/proving/fixtures/v2_100_resettable_rework.py`
- Test: `tests/proving/test_v2_100_rework_loop.py`
- Test: `tests/negative/test_v2_100_rework_loop_fail_closed.py`

- [ ] **Step 1: Add resettable fixture API**

In `src/boardroom_os/proving/v2_100_resettable_fixture.py`, define:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.rework.evidence import ReworkEvidenceRecheckInput
from boardroom_os.rework.model import ReworkRequest

if TYPE_CHECKING:
    from boardroom_os.proving.v2_100_rework_loop import (
        ScenarioRoundBuild,
        ScenarioRoundProvider,
        ScenarioPayloadResolver,
        V2_100ScenarioInput,
        V2_100ScenarioRoundInput,
    )


@dataclass(frozen=True)
class V2_100ResettableFixture:
    package_root: Path
    request: ReworkRequest
    failing_recheck_input: ReworkEvidenceRecheckInput
    accepted_recheck_input: ReworkEvidenceRecheckInput

    def without_provider_attempt(self) -> "V2_100ResettableFixture":
        return replace_attempt(self, provider_attempt_refs=())

    def with_stale_final_evidence(self) -> "V2_100ResettableFixture":
        return replace_with_previous_namespace_evidence(self)

    def with_command_success_wrong_claim(self) -> "V2_100ResettableFixture":
        return replace_with_failed_behavioral_blocker_despite_passed_command(self)

    def with_old_closeout_run_ref(self) -> "V2_100ResettableFixture":
        return replace_with_old_closeout_readiness_refs(self)


def replace_attempt(
    base: V2_100ResettableFixture,
    *,
    provider_attempt_refs: tuple[ProviderAttemptRef, ...],
) -> V2_100ResettableFixture:
    invalid_attempt = base.accepted_recheck_input.attempt.model_copy(update={"provider_attempt_refs": provider_attempt_refs})
    invalid_recheck = base.accepted_recheck_input.model_copy(update={"attempt": invalid_attempt})
    return V2_100ResettableFixture(
        package_root=base.package_root,
        request=base.request,
        failing_recheck_input=base.failing_recheck_input,
        accepted_recheck_input=invalid_recheck,
    )


def replace_with_previous_namespace_evidence(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    previous_namespace = base.failing_recheck_input.namespace
    invalid_recheck = base.accepted_recheck_input.model_copy(update={"namespace": previous_namespace})
    return V2_100ResettableFixture(
        package_root=base.package_root,
        request=base.request,
        failing_recheck_input=base.failing_recheck_input,
        accepted_recheck_input=invalid_recheck,
    )


def replace_with_failed_behavioral_blocker_despite_passed_command(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    invalid_recheck = base.accepted_recheck_input.model_copy(
        update={"failed_final_evidence_blockers": base.failing_recheck_input.failed_final_evidence_blockers}
    )
    return V2_100ResettableFixture(
        package_root=base.package_root,
        request=base.request,
        failing_recheck_input=base.failing_recheck_input,
        accepted_recheck_input=invalid_recheck,
    )


def replace_with_old_closeout_readiness_refs(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    old_context = base.failing_recheck_input.closeout_context
    invalid_recheck = base.accepted_recheck_input.model_copy(update={"closeout_context": old_context})
    return V2_100ResettableFixture(
        package_root=base.package_root,
        request=base.request,
        failing_recheck_input=base.failing_recheck_input,
        accepted_recheck_input=invalid_recheck,
    )
```

The fixture may deterministically write a tiny package under a temporary package root, but it must run `CommandRunner`（命令执行器） for verification runs and `EvidenceVerifier`（证据验证器） for verified evidence before building `ReworkEvidenceRecheckInput`（返工证据重验输入）.

- [ ] **Step 2: Build fixture from V2-100D public builders and production models**

Do not use `tests/rework/fixtures/rework_evidence.py`（测试夹具） as a design source, shape template, or fact source for `src/`（源码）. The resettable fixture（可重置夹具） must derive its structure only from V2-100D public builders（公开构建器）、production models（生产模型） and active contracts（活跃合同）. Use these production constructors and validators directly:

- `create_acceptance_contract`（创建验收合同）
- `create_package_contract`（创建包合同）
- `build_run_manifest`（构建运行清单）
- `assemble_package`（装配项目包）
- `build_source_inventory`（构建源码清单）
- `EvidenceVerifier().verify(...)`（证据验证器校验）
- `CommandRunner().run(...)`（命令执行器运行）
- `ReworkEvidenceRecheckInput`（返工证据重验输入）
- `recheck_rework_attempt`（返工证据重验）

The test fixture module may import `src/boardroom_os/proving/v2_100_resettable_fixture.py`（生产证明夹具） and corrupt returned objects to create negative cases（负例）， but production code must not import from `tests/` and must not mirror hidden constants from test fixtures（测试夹具隐藏常量）.

- [ ] **Step 3: Add production builder functions before tests reference them**

In `src/boardroom_os/proving/v2_100_resettable_fixture.py`, define these builder functions in this order. These functions are production proving helpers（生产证明辅助器）, not test-only fixtures（测试专用夹具）:

```python
DEFAULT_FAILURE_SUMMARY_PATH = Path(
    "examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json"
)


def build_v2_100_resettable_fixture(*, package_root: Path) -> V2_100ResettableFixture:
    """Build failing and accepted ReworkEvidenceRecheckInput objects from active contracts and real evidence gates."""


def build_v2_100_scenario_input(
    *,
    snapshot_summary_path: Path = DEFAULT_FAILURE_SUMMARY_PATH,
    export_root: Path | None = None,
    provider_env_path: Path = Path(".env"),
    require_real_provider: bool = True,
    max_rounds: int = 2,
    package_root: Path | None = None,
) -> V2_100ScenarioInput:
    """Build V2_100ScenarioInput from the same active contracts and refs used by build_v2_100_resettable_fixture."""


def build_accepted_round_input(tmp_path: Path) -> ScenarioRoundBuild:
    """Build one accepted round input, its payload resolver, and provider-attempt manifest entries."""


def build_two_round_provider(tmp_path: Path) -> ScenarioRoundProvider:
    """Return a provider whose first round remains blocked and second round passes recheck_rework_attempt."""


def build_exhausted_round_provider(tmp_path: Path) -> ScenarioRoundProvider:
    """Return a provider whose single round remains blocked and carries an exhausted_budget ReworkTerminationDecision."""
```

Implementation order:

1. `build_v2_100_resettable_fixture` constructs active AcceptanceContract（活跃验收合同）、PackageContract（包合同）、RunManifest（运行清单）、PackageAssembly（包装配结果）、CommandRunner evidence（命令证据）、EvidenceVerifier result（证据验证结果）、SourceLineageRecord（源码来源链记录） and two typed `ReworkAttempt`（返工尝试） objects. The failing round keeps a real verified blocker; the accepted round removes blockers only through fresh current-round evidence.
2. `build_v2_100_scenario_input` derives `package_contract_ref`、`run_manifest_ref`、`active_acceptance_refs`、`active_source_surface_refs`、`active_evidence_obligation_refs` and `active_contract_refs` from those active contracts, and passes through `snapshot_summary_path` to `V2_100ScenarioInput`（场景输入）. The default snapshot path must be the explicit `DEFAULT_FAILURE_SUMMARY_PATH` constant above, not an inline hardcoded string inside CLI（命令行入口） or tests（测试）. It must not duplicate hidden constants or read `tests/`（测试目录）.
3. `build_accepted_round_input` assembles CEO planner output（CEO 规划输出）、reviewer outputs（审查输出）、approval set（审批集合）、ticket payload（工单载荷）、`ReworkAttempt`（返工尝试） and `ReworkEvidenceRecheckInput`（返工证据重验输入） for one accepted round. It returns `ScenarioRoundBuild`（轮次构建结果） whose `payload_resolver`（载荷解析器） stores the exact payloads referenced by the returned events and whose `provider_attempt_manifest_entries`（模型调用清单条目） come from the actual ProviderAttempt（模型调用尝试记录） objects used in the round. It must not synthesize a passed `ReworkOutcome`（返工结果）.
4. `build_two_round_provider` returns deterministic typed `ScenarioRoundBuild`（轮次构建结果） values for tests only when `require_real_provider=False`. Round 1 uses `fixture.failing_recheck_input`; round 2 uses `fixture.accepted_recheck_input`. Both rounds still run production `recheck_rework_attempt`（返工证据重验） and `ReworkReducer`（返工归约器） inside the scenario loop.
5. `build_exhausted_round_provider` uses `fixture.failing_recheck_input` and attaches a typed `ReworkTerminationDecision`（返工终止决策） whose `reason` is `ReworkTerminationReason.EXHAUSTED_BUDGET`（预算耗尽）. It returns `ScenarioRoundBuild`（轮次构建结果） with remaining blocker refs, current evidence refs and provider attempt manifest entries from the failing round.

Do not add `attempt_provider_attempts`（并行尝试模型调用记录集合） to any builder return type. Worker/Tester/Release DevOps provider lineage（实施/测试/发布运维模型调用来源链） must stay on `ReworkAttempt.provider_attempt_refs`（返工尝试模型调用引用） and the provider attempt artifact store（模型调用产物存储）.

- [ ] **Step 4: Add negative fixture variants**

In `tests/proving/fixtures/v2_100_resettable_rework.py`, expose functions:

```python
def without_provider_attempt(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.without_provider_attempt()


def with_stale_final_evidence(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.with_stale_final_evidence()


def with_command_success_wrong_claim(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.with_command_success_wrong_claim()


def with_old_closeout_run_ref(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.with_old_closeout_run_ref()
```

Each variant must create invalid inputs that production validators reject. Do not use variants as accepted happy path.

- [ ] **Step 5: Add fixture tests**

Create `tests/proving/test_v2_100_rework_loop.py` with:

```python
def test_resettable_fixture_builds_failing_and_accepted_recheck_inputs(tmp_path):
    from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_resettable_fixture

    fixture = build_v2_100_resettable_fixture(package_root=tmp_path / "package")

    assert fixture.failing_recheck_input.target_blocker_refs
    assert fixture.accepted_recheck_input.target_blocker_refs
    assert fixture.failing_recheck_input.attempt.rework_attempt_id != fixture.accepted_recheck_input.attempt.rework_attempt_id
```

- [ ] **Step 6: Run focused fixture tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop.py tests/negative/test_rework_evidence_fail_closed.py tests/negative/test_rework_closeout_fail_closed.py -q
```

Expected after Task 3: fixture test and existing V2-100D fail-closed tests pass.

## Task 4: Real Provider Role Calls For CEO And Reviewers

**Files:**

- Modify: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Test: `tests/proving/test_v2_100_rework_loop_provider_integration.py`
- Test: `tests/negative/test_v2_100_rework_loop_fail_closed.py`

- [ ] **Step 1: Add role-call helper that loads authoritative provider profile**

Implement:

```python
from boardroom_os.execution.provider_executor import ProviderExecutor, ProviderExecutorInput
from boardroom_os.execution.package import ExecutionPackage
from boardroom_os.providers.openai_adapter import OpenAIProviderTransport


def _assert_role_package_provider_binding(scenario_input: V2_100ScenarioInput, execution_package: ExecutionPackage) -> None:
    settings = load_v2_100e_boardroom_settings(scenario_input)
    role_slot = settings.role_slot_by_seat(execution_package.seat_ref.value)
    provider_profile = settings.provider_by_id(role_slot.provider_profile_ref)
    profile = execution_package.model_execution_profile
    if (
        profile.provider != "openai-compatible"
        or profile.model != provider_profile.model
        or profile.reasoning_effort != (provider_profile.reasoning_effort or profile.reasoning_effort)
        or profile.context_window != provider_profile.context_window_tokens
    ):
        raise V2_100ReworkLoopError("role-bound provider profile does not match execution package")


def _real_provider_transport(scenario_input: V2_100ScenarioInput, *, seat_ref: str) -> OpenAIProviderTransport:
    settings = load_v2_100e_openai_settings(scenario_input, seat_ref=seat_ref)
    return OpenAIProviderTransport(settings=settings)


def _execute_role_package(execution_package: ExecutionPackage, scenario_input: V2_100ScenarioInput):
    _assert_role_package_provider_binding(scenario_input, execution_package)
    transport = _real_provider_transport(scenario_input, seat_ref=execution_package.seat_ref.value)
    return ProviderExecutor().execute(
        ProviderExecutorInput(execution_package=execution_package, provider_adapter=transport)
    )
```

This is a deliberate V2-100E boundary. `.env`（环境文件） must not carry `BOARDROOM_OPENAI_*` model/config knobs（模型/配置开关）; it only supplies `BOARDROOM_RUNTIME_CONFIG` / `BOARDROOM_PROVIDERS_CONFIG` / `BOARDROOM_ROLES_CONFIG`（运行时/供应商/角色配置路径） and the provider secret named by the role-bound YAML profile（角色绑定 YAML 配置档声明的密钥名）. `_assert_role_package_provider_binding`（角色包供应商绑定校验） must fail before provider invocation（模型调用） when the role slot（角色席位）、provider profile（供应商配置档） and `ExecutionPackage.model_execution_profile`（执行包模型执行配置） disagree. Do not silently downgrade to `responses` protocol（Responses API 协议） or text response parsing. If a future provider profile must use `responses`, create a separate adapter hardening task first: pass the official JSON output option through `_invoke_responses_api`（Responses API 调用分支）, add `tests/execution/test_openai_provider_adapter.py` coverage, and only then loosen this validator.

- [ ] **Step 2: Build CEO and reviewer ExecutionPackage objects with strict JSON output contracts**

When constructing role `ExecutionPackage`（执行包） objects for CEO planner（CEO 规划者） and graph patch reviewers（图补丁审查者）, inject the parseable JSON shape into fields that `ProviderExecutor`（模型执行器） actually renders: `constraints`（约束）、`required_outputs`（必需输出） and `audit_requirements`（审计要求）. Do not rely on invisible local parser assumptions.

CEO planner package requirements:

```python
from boardroom_os.execution.package import AuditRequirement, RequiredOutput

CEO_JSON_CONSTRAINTS = (
    "Return exactly one JSON object and no Markdown, no prose, no code fence.",
    'The JSON object must have exactly two top-level keys: "plan" and "patch".',
    '"plan" must contain the ReworkPlan fields required by parse_ceo_rework_planner_payload.',
    '"patch" must contain the TicketGraphPatch fields required by parse_ceo_rework_planner_payload.',
    "Every blocker_ref, acceptance_ref, source_surface_ref, evidence_obligation_ref, ticket_ref, and graph_version must match the supplied planner input; do not invent refs.",
)

CEO_REQUIRED_OUTPUTS = (
    RequiredOutput(value="json:ceo_rework_planner:{plan,patch}"),
)

CEO_AUDIT_REQUIREMENTS = (
    AuditRequirement(value="provider.output.strict_json.no_markdown"),
    AuditRequirement(value="provider.output.refs.match_planner_input"),
    AuditRequirement(value="provider.output.parse_with.parse_ceo_rework_planner_payload"),
)
```

Reviewer package requirements:

```python
REVIEWER_JSON_CONSTRAINTS = (
    "Return exactly one JSON object and no Markdown, no prose, no code fence.",
    'The JSON object must have exactly one top-level key: "review".',
    '"review" must contain the GraphPatchReview fields required by parse_graph_patch_review_payload.',
    "Every blocker_ref, acceptance_ref, source_surface_ref, evidence_obligation_ref, patch_ref, and graph_version must match the supplied reviewer input; do not invent refs.",
)

REVIEWER_REQUIRED_OUTPUTS = (
    RequiredOutput(value="json:graph_patch_review:{review}"),
)

REVIEWER_AUDIT_REQUIREMENTS = (
    AuditRequirement(value="provider.output.strict_json.no_markdown"),
    AuditRequirement(value="provider.output.refs.match_reviewer_input"),
    AuditRequirement(value="provider.output.parse_with.parse_graph_patch_review_payload"),
)
```

The implementation may append these tuples to the baseline `ExecutionPackage`（执行包） constraints/output/audit fields, but it must not replace contract-derived acceptance refs（验收引用）、source surface refs（源码面引用）、allowed read/write refs（允许读写引用） or evidence obligations（证据义务）. This step is required because current `ProviderExecutor` renders only the package fields listed in `_PROMPT_FIELDS`（提示字段列表） and does not receive a separate JSON schema channel.

- [ ] **Step 3: Parse CEO provider output through existing parser**

Implement role adapter:

```python
import json
from boardroom_os.rework.planner import CeoReworkPlannerOutput, parse_ceo_rework_planner_payload, validate_ceo_rework_plan


def _parse_ceo_output(provider_result, planner_input, artifact_reader) -> CeoReworkPlannerOutput:
    parsed_text = artifact_reader(provider_result.provider_attempt.parsed_output_ref)
    parsed_payload = parse_ceo_rework_planner_payload(json.loads(parsed_text))
    output = CeoReworkPlannerOutput(
        planner_input=planner_input,
        provider_attempt=provider_result.provider_attempt,
        plan=parsed_payload.plan,
        patch=parsed_payload.patch,
        parsed_payload_ref=provider_result.provider_attempt.parsed_output_ref,
        validated_at=provider_result.provider_attempt.finished_at,
    )
    return validate_ceo_rework_plan(output)
```

The final implementation may use `FileProviderOutputStore.read_text`（文件供应商输出存储读取） as `artifact_reader`; it must not hand-copy provider JSON into local dicts.

- [ ] **Step 4: Parse reviewer provider output through existing parser**

Implement reviewer adapter using:

- `parse_graph_patch_review_payload`（解析图补丁审查载荷）
- `validate_graph_patch_review`（校验图补丁审查）
- `architect_graph_patch_review_input`（架构师审查输入）
- `checker_graph_patch_review_input`（检查者审查输入）
- `tester_graph_patch_review_input`（测试者审查输入）
- `release_devops_graph_patch_review_input`（发布运维审查输入）
- `closeout_graph_patch_review_input`（收尾审查输入）

- [ ] **Step 5: Add worker/tester/release-devops provider attempt capture**

Happy path must include real ProviderAttempt（模型调用尝试记录） objects for Worker / Tester / Release DevOps（实施者 / 测试者 / 发布运维） when their round produces implementation, probe, command, run-env or package changes. The implementation must:

1. Build a role `ExecutionPackage`（执行包） per role using the active AcceptanceContract（验收合同）、PackageContract（包合同）、source surfaces（源码面）、allowed_write_set（允许写集合）、required_outputs（必需输出） and evidence obligations（证据义务） for that role.
2. Execute each role package through `ProviderExecutor`（模型执行器） backed by `OpenAIProviderTransport`（OpenAI 模型传输） or through the existing atomic executor（原子执行器） path when that path returns a real primary `ProviderAttempt`（主模型调用尝试记录）.
3. Persist raw/parsed provider artifacts through `FileProviderOutputStore`（文件供应商输出存储） or the existing executor artifact store（执行器产物存储）; `raw_output_ref`（原始输出引用） and `parsed_output_ref`（解析输出引用） must be present.
4. Build `ReworkAttempt.provider_attempt_refs`（返工尝试模型调用引用） from the actual returned attempts for the current round only.
5. Build WorkProduct（工作产物）、EvidenceClaim（证据声明）、SourceLineageRecord（源码来源链记录） and EvidenceVerificationResult（证据验证结果） from those same provider attempt refs. Evidence whose `producer_attempt_ref`（生产者调用引用） is missing from `ReworkAttempt.provider_attempt_refs` must fail in `recheck_rework_attempt`（返工证据重验）.
6. Convert every actual ProviderAttempt（模型调用尝试记录） used by CEO/Reviewer/Worker/Tester/Release DevOps（CEO/审查者/实施/测试/发布运维） into `V2_100ProviderAttemptManifestEntry`（模型调用清单条目） with `provider_attempt_manifest_entry(attempt, artifact_store=..., expected_input_package_ref=..., expected_hook_ref=...)`. Expected refs must come from the `ExecutionPackage`（执行包） and `RolePromptHook`（角色提示词钩子） used to execute that role, not from the attempt itself. This function must call `artifact_store.get(attempt.raw_output_ref)` and `artifact_store.get(attempt.parsed_output_ref)` so the manifest records real artifact refs and sha256 values.
7. Before manifest construction, build a `role_attempt_bindings` map（角色调用绑定表） keyed by ProviderAttempt ref（模型调用引用）. Each entry must contain the actual role name、`ExecutionPackage.execution_package_id`（执行包编号） and `ExecutionPackage.role_prompt_hook.hook_ref`（执行包角色提示词钩子引用） used by ProviderExecutor（模型执行器） or atomic executor（原子执行器）. Missing binding for any Worker/Tester/Release DevOps attempt ref is fail-closed（失败关闭）.

Do not let resettable deterministic round providers（可重置确定性轮次供应器） stand in for real Worker/Tester/Release DevOps provider attempts when `require_real_provider=True`（要求真实模型供应商）。 Deterministic providers are allowed only in tests with `require_real_provider=False`（不要求真实模型供应商）, and even then their returned typed facts must pass production evidence/reducer gates（生产证据/归约门禁） rather than bypass them.

Implement:

```python
from boardroom_os.providers.openai_adapter import FileProviderOutputStore


def provider_attempt_manifest_entry(
    attempt: ProviderAttempt,
    *,
    artifact_store: FileProviderOutputStore,
    expected_input_package_ref: str,
    expected_hook_ref: str,
) -> V2_100ProviderAttemptManifestEntry:
    validate_real_provider_attempt(
        attempt,
        expected_input_package_ref=expected_input_package_ref,
        expected_hook_ref=expected_hook_ref,
    )
    if attempt.raw_output_ref is None or attempt.parsed_output_ref is None:
        raise V2_100ReworkLoopError("provider attempt manifest requires raw and parsed artifact refs")
    raw_artifact = artifact_store.get(attempt.raw_output_ref)
    parsed_artifact = artifact_store.get(attempt.parsed_output_ref)
    return V2_100ProviderAttemptManifestEntry(
        provider_attempt_ref=attempt.provider_attempt_id.value,
        provider=attempt.provider,
        model=attempt.model,
        input_package_ref=attempt.input_package_ref.value,
        raw_output_ref=attempt.raw_output_ref,
        parsed_output_ref=attempt.parsed_output_ref,
        raw_output_sha256="sha256:" + raw_artifact.content_hash.value,
        parsed_output_sha256="sha256:" + parsed_artifact.content_hash.value,
    )
```

The implementation must never call `provider_attempt_manifest_entry`（模型调用清单条目构造） with `expected_input_package_ref=attempt.input_package_ref.value` or `expected_hook_ref=attempt.role_prompt_hook_ref.value`. That self-comparison（自我比较） fails to prove the ProviderAttempt（模型调用尝试记录） is bound to the role `ExecutionPackage`（角色执行包）.

- [ ] **Step 6: Add provider integration test with explicit opt-in**

Create `tests/proving/test_v2_100_rework_loop_provider_integration.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.provider_integration


def test_v2_100e_real_provider_roles_produce_parseable_plan_and_reviews(tmp_path: Path) -> None:
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_TESTS") != "1":
        pytest.skip("set BOARDROOM_RUN_REAL_PROVIDER_TESTS=1 to run real provider V2-100E test")

    from boardroom_os.proving.v2_100_rework_loop import run_v2_100_rework_loop_scenario
    from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_scenario_input

    scenario_input = build_v2_100_scenario_input(
        export_root=tmp_path / "audit",
        provider_env_path=Path(".env"),
        require_real_provider=True,
        max_rounds=2,
    )

    result = run_v2_100_rework_loop_scenario(scenario_input)

    assert result.rounds
    assert all(round_result.plan_output.provider_attempt is not None for round_result in result.rounds)
    assert all(review.provider_attempt is not None for round_result in result.rounds for review in round_result.review_outputs)
    assert all(round_result.attempt.provider_attempt_refs for round_result in result.rounds)
    ceo_attempt_refs = {
        round_result.plan_output.provider_attempt.provider_attempt_id.value
        for round_result in result.rounds
    }
    reviewer_attempt_refs = {
        review.provider_attempt.provider_attempt_id.value
        for round_result in result.rounds
        for review in round_result.review_outputs
    }
    rework_attempt_refs = {
        ref.value
        for round_result in result.rounds
        for ref in round_result.attempt.provider_attempt_refs
    }
    attempt_refs = ceo_attempt_refs | reviewer_attempt_refs | rework_attempt_refs
    manifest_refs = {entry.provider_attempt_ref for entry in result.provider_attempt_manifest_entries}
    assert attempt_refs.issubset(manifest_refs)
    assert all(entry.raw_output_ref and entry.parsed_output_ref for entry in result.provider_attempt_manifest_entries)
    assert all(entry.raw_output_sha256.startswith("sha256:") for entry in result.provider_attempt_manifest_entries)
    assert all(entry.parsed_output_sha256.startswith("sha256:") for entry in result.provider_attempt_manifest_entries)
```

- [ ] **Step 7: Run provider test only when explicitly enabled**

Run for local non-provider verification:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop_provider_integration.py -q
```

Expected without `BOARDROOM_RUN_REAL_PROVIDER_TESTS=1`: skipped. This skip is not V2-100E completion evidence.

Run for V2-100E completion evidence:

```bash
BOARDROOM_RUN_REAL_PROVIDER_TESTS=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop_provider_integration.py -q -s
```

Expected before completion claim: PASS with real ProviderAttempt artifacts written by `OpenAIProviderTransport`（OpenAI 模型传输）.

## Task 5: Reducer Event Assembly And One-Round Execution

**Files:**

- Modify: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Test: `tests/proving/test_v2_100_rework_loop.py`
- Test: `tests/negative/test_v2_100_rework_loop_fail_closed.py`

- [ ] **Step 1: Implement in-memory payload resolver**

Add a private resolver:

```python
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    GraphPatchReviewPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
)


class _ScenarioPayloadResolver(ReworkReducerPayloadResolver):
    def __init__(self, payloads: dict[str, V2_100ReducerPayload]) -> None:
        self._payloads = dict(payloads)

    def payloads(self) -> dict[str, V2_100ReducerPayload]:
        return dict(self._payloads)

    def _get(self, payload_ref):
        try:
            return self._payloads[payload_ref.value]
        except KeyError as error:
            raise V2_100ReworkLoopError(f"missing payload: {payload_ref.value}") from error

    def payload_manifest_entries_for(self, events: tuple[EventRecord, ...]) -> tuple[V2_100PayloadManifestEntry, ...]:
        entries: list[V2_100PayloadManifestEntry] = []
        for event in events:
            for payload_ref in event.payload_refs:
                entries.append(canonical_payload_manifest_entry(payload_ref, self._get(payload_ref)))
        return tuple(entries)


def merge_payload_resolvers(*resolvers: ScenarioPayloadResolver) -> ScenarioPayloadResolver:
    merged: dict[str, V2_100ReducerPayload] = {}
    for resolver in resolvers:
        for payload_ref, payload in resolver.payloads().items():
            if payload_ref in merged and merged[payload_ref] != payload:
                raise V2_100ReworkLoopError(f"payload ref conflict: {payload_ref}")
            merged[payload_ref] = payload
    return _ScenarioPayloadResolver(merged)
```

Implement all resolver methods with exact payload model types from `src/boardroom_os/reducers/rework.py`. `_ScenarioPayloadResolver`（场景载荷解析器） stores a round-local or cumulative payload map（本轮或累计载荷映射） and fails closed（失败关闭） on missing refs. `merge_payload_resolvers`（合并载荷解析器） is the only allowed way for the loop to combine historical payloads and current-round payloads; it must reject duplicate payload refs with different payload bytes. Audit export（审计导出） must hash payloads from this cumulative store, not from reconstructed refs（重建引用）.

- [ ] **Step 2: Implement event assembly**

`build_rework_reducer_events(round_input, *, outcome, prior_projection=None)` must emit the round-local event suffix. For a still-blocked round（仍阻塞轮次）, emit no terminal event so `ReworkReducer`（返工归约器） keeps `terminal_status=open`（终态状态为开放） and later rounds can append events. Only accepted/escalated/exhausted terminal rounds emit terminal events.

First round event suffix:

```text
REWORK_REQUESTED
REWORK_PLANNED
REWORK_GRAPH_PATCH_REVIEWED one per reviewer
REWORK_GRAPH_PATCH_APPROVED
REWORK_TICKET_CREATED
REWORK_ATTEMPT_STARTED
REWORK_ATTEMPT_SUBMITTED
REWORK_REVIEWED
optional terminal: REWORK_ACCEPTED or REWORK_ESCALATED or REWORK_EXHAUSTED
```

Later round event suffix for the same cycle/request:

```text
REWORK_PLANNED
REWORK_GRAPH_PATCH_REVIEWED one per reviewer
REWORK_GRAPH_PATCH_APPROVED
REWORK_TICKET_CREATED
REWORK_ATTEMPT_STARTED
REWORK_ATTEMPT_SUBMITTED
REWORK_REVIEWED
optional terminal: REWORK_ACCEPTED or REWORK_ESCALATED or REWORK_EXHAUSTED
```

Rules:

- Event graph versions must be strictly increasing from `started_at_graph_version + 1`.
- When `prior_projection is not None`, the new event graph versions must be strictly greater than `prior_projection.graph_version`; do not replay or renumber prior events.
- When `prior_projection is not None`, do not emit another `REWORK_REQUESTED` event because the current `ReworkReducer`（返工归约器） rejects duplicate request events.
- Terminal event actor must be `governance-command-handler:v2-100e`, not runtime/executor/atomic-agent.
- Attempt start/submit actor may be runtime/executor because those are factual events.
- Every event must have one `EventPayloadRef`（事件载荷引用）.
- If `outcome.status.value == "rework_required"`（仍需返工）, stop after `REWORK_REVIEWED`; do not emit `REWORK_ESCALATED` or `REWORK_EXHAUSTED` just to close the round.
- If `outcome.status.value == "accepted"`（接受）, emit `REWORK_ACCEPTED` and require `remaining_blocker_refs`（剩余阻塞引用） to be empty.
- If `terminal_decision`（终止决策） is present and the loop is exhausted or escalated, emit `REWORK_EXHAUSTED` or `REWORK_ESCALATED` only on the final round.

- [ ] **Step 3: Implement round execution**

```python
from boardroom_os.reducers.rework import ReworkReducer
from boardroom_os.rework.evidence import recheck_rework_attempt


def run_v2_100_rework_round(
    round_build: ScenarioRoundBuild,
    *,
    prior_events: tuple[EventRecord, ...] = (),
    payload_resolver: ScenarioPayloadResolver | None = None,
) -> V2_100ScenarioRoundResult:
    round_input = round_build.round_input
    active_payload_resolver = payload_resolver or round_build.payload_resolver
    round_input = validate_round_input(round_input)
    recheck_result = recheck_rework_attempt(round_input.recheck_input)
    outcome = recheck_result.to_rework_outcome()
    prior_projection = ReworkReducer(active_payload_resolver).reduce(prior_events) if prior_events else None
    round_events = build_rework_reducer_events(
        round_input.model_copy(update={"recheck_input": round_input.recheck_input}),
        outcome=outcome,
        prior_projection=prior_projection,
    )
    events = prior_events + round_events
    projection = ReworkReducer(active_payload_resolver).reduce(events)
    if outcome.status.value == "accepted" and projection.terminal_status.value != "accepted":
        raise V2_100ReworkLoopError("accepted outcome must produce accepted projection")
    if outcome.status.value == "rework_required" and projection.terminal_status.value != "open":
        raise V2_100ReworkLoopError("still-blocked round must leave projection open")
    return V2_100ScenarioRoundResult(
        round_index=round_input.round_index,
        request=round_input.request,
        plan_output=round_input.planner_output,
        review_outputs=round_input.reviewer_outputs,
        patch=round_input.planner_output.patch,
        approval_set=round_input.approval_set,
        rework_ticket_ref=round_input.rework_ticket_payload.ticket_id,
        attempt=round_input.attempt,
        recheck_result=recheck_result,
        outcome=outcome,
        projection=projection,
        events=round_events,
        payload_refs=tuple(payload_ref for event in round_events for payload_ref in event.payload_refs),
        payload_manifest_entries=active_payload_resolver.payload_manifest_entries_for(round_events),
        provider_attempt_manifest_entries=round_build.provider_attempt_manifest_entries,
        accepted_blocker_refs=recheck_result.accepted_blocker_refs,
        remaining_blocker_refs=recheck_result.remaining_blocker_refs,
    )
```

Fill `V2_100ScenarioRoundResult` with actual typed values. Do not infer accepted blockers from command status or provider completion; copy them only from `ReworkEvidenceRecheckResult.accepted_blocker_refs`（返工证据重验结果接受阻塞引用）. When `prior_events`（既有事件） is not empty, callers must pass an active cumulative resolver（当前累计载荷解析器） that can resolve both prior and current round payload refs（既有与本轮载荷引用）. The resolver method `payload_manifest_entries_for(round_events)`（按轮次事件生成载荷清单条目） must canonicalize the already-stored payload objects referenced by events; it must not reconstruct payloads from refs.

- [ ] **Step 4: Add one-round accepted test**

In `tests/proving/test_v2_100_rework_loop.py`:

```python
def test_one_round_accepted_path_reduces_to_accepted_projection(tmp_path):
    from boardroom_os.proving.v2_100_resettable_fixture import build_accepted_round_input
    from boardroom_os.proving.v2_100_rework_loop import run_v2_100_rework_round

    round_build = build_accepted_round_input(tmp_path)
    result = run_v2_100_rework_round(round_build)

    assert result.outcome.status.value == "accepted"
    assert result.projection.terminal_status.value == "accepted"
    assert result.accepted_blocker_refs == result.recheck_result.accepted_blocker_refs
```

- [ ] **Step 5: Add missing historical payload negative test**

In `tests/negative/test_v2_100_rework_loop_fail_closed.py`:

```python
def test_second_round_requires_historical_payloads(tmp_path):
    from boardroom_os.proving.v2_100_resettable_fixture import build_two_round_provider, build_v2_100_scenario_input
    from boardroom_os.proving.v2_100_rework_loop import project_snapshot_request, run_v2_100_rework_round

    scenario_input = build_v2_100_scenario_input(
        require_real_provider=False,
        max_rounds=2,
    )
    request = project_snapshot_request(scenario_input)
    provider = build_two_round_provider(tmp_path)
    first_build = provider.build_round(
        scenario_input,
        request,
        round_index=1,
        started_at_graph_version=scenario_input.initial_graph_version,
    )
    first_result = run_v2_100_rework_round(first_build)
    second_build = provider.build_round(
        scenario_input,
        first_result.request,
        round_index=2,
        started_at_graph_version=first_result.projection.graph_version,
    )

    with pytest.raises(ValueError, match="missing payload"):
        run_v2_100_rework_round(second_build, prior_events=first_result.events)
```

The point of this negative test is fixed: using the second round's round-local resolver（本轮局部载荷解析器） to reduce first-round historical events must fail closed.

- [ ] **Step 6: Run reducer-focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop.py tests/reducers/test_rework_reducer.py tests/negative/test_rework_reducer_fail_closed.py -q
```

Expected after Task 5: all listed tests pass.

## Task 6: Multi-Round Loop, Explicit Escalation, And Exhaustion

**Files:**

- Modify: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Modify: `tests/proving/test_v2_100_rework_loop.py`
- Modify: `tests/negative/test_v2_100_rework_loop_fail_closed.py`

- [ ] **Step 1: Implement loop budget validation**

```python
def validate_loop_budget(rounds: tuple[V2_100ScenarioRoundResult, ...], *, max_rounds: int, terminal_decision: ReworkTerminationDecision | None) -> None:
    if max_rounds <= 0:
        raise V2_100ReworkLoopError("max_rounds must be positive")
    if len(rounds) >= max_rounds:
        last_remaining = rounds[-1].remaining_blocker_refs if rounds else ()
        if last_remaining and terminal_decision is None:
            raise V2_100ReworkLoopError("termination decision is required when budget is exhausted")
```

- [ ] **Step 2: Implement scenario loop**

`run_v2_100_rework_loop_scenario` must:

1. Validate `V2_100ScenarioInput`（场景输入）.
2. Call `project_snapshot_request`（投影失败快照返工请求）.
3. If `round_provider is None`, construct a real-provider round provider that uses `load_v2_100e_openai_settings`（加载 V2-100E OpenAI 设置） and role ExecutionPackage（执行包） objects.
4. For each round, call `round_provider.build_round(...)`（轮次供应器构建轮次） and require a `ScenarioRoundBuild`（轮次构建结果） containing `round_input`（轮次输入）、`payload_resolver`（载荷解析器） and `provider_attempt_manifest_entries`（模型调用清单条目）.
5. Keep an accumulated `events` tuple（累计事件元组） and an accumulated `cumulative_payload_resolver`（累计载荷解析器）. Before each reduce, set `cumulative_payload_resolver = merge_payload_resolvers(cumulative_payload_resolver, round_build.payload_resolver)`; for the first round, initialize it with the round resolver. Pass that cumulative resolver to `run_v2_100_rework_round(round_build, prior_events=events, payload_resolver=cumulative_payload_resolver)`（运行返工轮次）. Reducer projection（归约投影） must be computed from all prior + current events so later rounds continue the same ReworkCycle（返工循环） and can resolve historical payloads（历史载荷）.
6. After each result, append `round_result.events` to `events`. Do not replace cumulative payloads with a round-local resolver. If any prior event payload cannot be resolved by the cumulative resolver, fail closed before proceeding to the next round.
7. Run rounds until accepted or max budget. Still-blocked rounds must have `projection.terminal_status == "open"`（投影终态为开放） and must not emit terminal events（终态事件）.
8. If budget is exhausted with remaining blockers, require a `ReworkTerminationDecision`（返工终止决策） with reason `exhausted_budget` or `escalated_human_review`, then run a final terminal suffix that emits `REWORK_EXHAUSTED` or `REWORK_ESCALATED`.
9. Set `V2_100ScenarioResult.payload_manifest_entries`（场景结果载荷清单条目） from `cumulative_payload_resolver.payload_manifest_entries_for(events)`（累计载荷解析器按全部事件生成清单） rather than concatenating round-local manifests blindly. Set `provider_attempt_manifest_entries`（模型调用清单条目） to the canonical de-duplicated entries from every round. Export audit only from real round results; do not write a passed summary if no accepted or terminal decision exists.

- [ ] **Step 3: Add accepted two-round test**

In `tests/proving/test_v2_100_rework_loop.py`:

```python
def test_multi_round_loop_rechecks_after_initial_failure(tmp_path):
    from boardroom_os.events.types import EventType
    from boardroom_os.proving.v2_100_resettable_fixture import build_two_round_provider, build_v2_100_scenario_input
    from boardroom_os.proving.v2_100_rework_loop import (
        V2_100ScenarioTerminalStatus,
        run_v2_100_rework_loop_scenario,
    )

    scenario_input = build_v2_100_scenario_input(
        export_root=tmp_path / "audit",
        require_real_provider=False,
        max_rounds=2,
    )
    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_two_round_provider(tmp_path),
    )

    assert result.terminal_status is V2_100ScenarioTerminalStatus.ACCEPTED
    assert len(result.rounds) == 2
    assert result.rounds[0].remaining_blocker_refs
    assert result.rounds[0].projection.terminal_status.value == "open"
    assert not any(event.event_type in {EventType.REWORK_ACCEPTED, EventType.REWORK_ESCALATED, EventType.REWORK_EXHAUSTED} for event in result.rounds[0].events)
    all_events = tuple(event for round_result in result.rounds for event in round_result.events)
    historical_payload_refs = {payload_ref.value for event in all_events for payload_ref in event.payload_refs}
    manifest_payload_refs = {entry.payload_ref.value for entry in result.payload_manifest_entries}
    assert historical_payload_refs.issubset(manifest_payload_refs)
    assert len(result.final_projection.committed_event_refs) == len(all_events)
    assert not result.rounds[-1].remaining_blocker_refs
    assert any(event.event_type is EventType.REWORK_ACCEPTED for event in result.rounds[-1].events)
```

This test may use deterministic typed round inputs, but the accepted round must still pass production `recheck_rework_attempt`（返工证据重验） and ReworkReducer（返工归约器）. It must not construct a fake `ReworkOutcome`（返工结果）.

- [ ] **Step 4: Add exhausted path test**

```python
def test_exhausted_loop_requires_auditable_termination(tmp_path):
    from boardroom_os.proving.v2_100_resettable_fixture import build_exhausted_round_provider, build_v2_100_scenario_input
    from boardroom_os.proving.v2_100_rework_loop import V2_100ScenarioTerminalStatus, run_v2_100_rework_loop_scenario

    scenario_input = build_v2_100_scenario_input(
        export_root=tmp_path / "audit",
        require_real_provider=False,
        max_rounds=1,
    )
    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_exhausted_round_provider(tmp_path),
    )

    assert result.terminal_status is V2_100ScenarioTerminalStatus.EXHAUSTED
    assert result.termination_decision is not None
    assert result.termination_decision.reason.value == "exhausted_budget"
```

- [ ] **Step 5: Run loop tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop.py tests/negative/test_v2_100_rework_loop_fail_closed.py -q
```

Expected after Task 6: multi-round accepted and exhausted paths pass; negative tests still prove missing terminal decision fails.

## Task 7: Audit Export And CLI

**Files:**

- Modify: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Create: `scripts/run_v2_100_rework_loop_scenario.py`
- Test: `tests/proving/test_v2_100_rework_loop.py`
- Test: `tests/proving/test_v2_100_rework_loop_provider_integration.py`

- [ ] **Step 1: Implement audit export**

`export_v2_100_rework_audit(result, export_root)` must write:

- `summary.json` — scenario id（场景编号）、terminal status（终态状态）、round count（轮次数）、accepted/remaining blockers（接受/剩余阻塞项）、termination decision（终止决策）。
- `event-log.json` — `EventRecord.stable_dump()`（事件稳定序列化） for all rounds.
- `payload-manifest.json` — payload refs（载荷引用）、payload kinds（载荷类型）、canonical JSON（规范 JSON） and payload hashes（载荷哈希） from `result.payload_manifest_entries`（结果载荷清单条目）.
- `provider-attempts.json` — provider attempt refs and artifact refs（模型调用尝试引用和产物引用）.
- `evidence-summary.json` — SourceInventory ref/hash（源码清单引用/哈希）、FinalEvidenceTable ref（最终证据表引用）、CheckerVerdict ref（检查结论引用）、CloseoutGateResult ref（收尾门禁结果引用）.
- `process-timeline.md` — human-readable timeline（人类可读时间线）.

Every JSON file must be written with sorted keys and UTF-8. `payload-manifest.json` must include the canonical JSON bytes used for each hash or a sibling payload file path whose bytes are re-read and hashed. Ref-only manifest（仅引用清单） is invalid because AC-V2-CLOSEOUT-008 requires payload content binding（载荷内容绑定）.

- [ ] **Step 2: Add audit export test**

```python
def test_audit_export_contains_events_provider_attempts_and_evidence_refs(tmp_path):
    from boardroom_os.proving.v2_100_resettable_fixture import build_two_round_provider, build_v2_100_scenario_input
    from boardroom_os.proving.v2_100_rework_loop import export_v2_100_rework_audit, run_v2_100_rework_loop_scenario

    scenario_input = build_v2_100_scenario_input(export_root=tmp_path / "audit", require_real_provider=False, max_rounds=2)
    result = run_v2_100_rework_loop_scenario(scenario_input, round_provider=build_two_round_provider(tmp_path))
    export = export_v2_100_rework_audit(result, tmp_path / "audit")

    assert export.summary_path.exists()
    assert export.event_log_path.exists()
    assert export.provider_attempts_path.exists()
    assert export.evidence_summary_path.exists()
    assert export.checked_refs
    assert result.payload_manifest_entries
    manifest = export.payload_manifest_path.read_text(encoding="utf-8")
    assert "canonical_json" in manifest
    assert "sha256:" in manifest
    provider_manifest = export.provider_attempts_path.read_text(encoding="utf-8")
    assert "raw_output_ref" in provider_manifest
    assert "parsed_output_ref" in provider_manifest
    assert "raw_output_sha256" in provider_manifest
    assert "parsed_output_sha256" in provider_manifest
```

- [ ] **Step 3: Implement CLI**

Create `scripts/run_v2_100_rework_loop_scenario.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from boardroom_os.proving.v2_100_resettable_fixture import DEFAULT_FAILURE_SUMMARY_PATH, build_v2_100_scenario_input
from boardroom_os.proving.v2_100_rework_loop import export_v2_100_rework_audit, run_v2_100_rework_loop_scenario


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=DEFAULT_FAILURE_SUMMARY_PATH.as_posix())
    parser.add_argument("--env", default=".env")
    parser.add_argument("--export-root", required=True)
    parser.add_argument("--max-rounds", type=int, default=2)
    args = parser.parse_args()

    scenario_input = build_v2_100_scenario_input(
        snapshot_summary_path=Path(args.snapshot),
        provider_env_path=Path(args.env),
        export_root=Path(args.export_root),
        require_real_provider=True,
        max_rounds=args.max_rounds,
    )
    result = run_v2_100_rework_loop_scenario(scenario_input)
    audit_export = export_v2_100_rework_audit(result, Path(args.export_root))
    result = result.model_copy(update={"audit_export": audit_export})
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add CLI smoke test without provider call**

Add a parser/import smoke test that does not invoke `main()` with real provider:

```python
def test_cli_module_imports() -> None:
    import scripts.run_v2_100_rework_loop_scenario as cli

    assert callable(cli.main)
```

- [ ] **Step 5: Run CLI/provider proof command for completion evidence**

Run after unit tests pass:

```bash
PYTHONPATH=src:. python scripts/run_v2_100_rework_loop_scenario.py \
  --env .env \
  --export-root examples/generated-workspaces/tiny-fullstack/20-evidence/v2-100e-rework-loop \
  --max-rounds 2
```

Expected for completion: exit 0 with real provider attempts and audit files. If provider returns a valid escalation/exhaustion decision instead of accepted, the result is acceptable only if blockers, budget and terminal decision are fully auditable.

## Task 8: Regression Verification And Completion Protocol

**Files:**

- Modify after evidence exists: `doc/04-implementation/backlog.md`
- Modify after evidence exists: `doc/04-implementation/acceptance-criteria.md`
- Modify after evidence exists: `doc/05-project-log/2026-06.md`
- Modify if needed: `doc/05-project-log/decisions.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Run focused V2-100 regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/rework tests/reducers/test_rework_reducer.py tests/negative/test_rework_model_fail_closed.py tests/negative/test_rework_reducer_fail_closed.py tests/negative/test_ceo_rework_planner_fail_closed.py tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py tests/negative/test_rework_evidence_fail_closed.py tests/negative/test_rework_closeout_fail_closed.py tests/proving/test_v2_100_rework_loop.py tests/negative/test_v2_100_rework_loop_fail_closed.py -q
```

Expected: PASS.

- [ ] **Step 2: Run evidence/checker/closeout regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/evidence tests/closeout tests/negative/test_missing_acceptance_map_blocks_closeout.py tests/negative/test_service_run_closeout_gate.py tests/negative/test_run_manifest_command_coverage.py -q
```

Expected: PASS.

- [ ] **Step 3: Run real provider V2-100E proof**

Run:

```bash
BOARDROOM_RUN_REAL_PROVIDER_TESTS=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop_provider_integration.py -q -s
PYTHONPATH=src:. python scripts/run_v2_100_rework_loop_scenario.py --env .env --export-root examples/generated-workspaces/tiny-fullstack/20-evidence/v2-100e-rework-loop --max-rounds 2
```

Expected: `.env` supplies `BOARDROOM_RUNTIME_CONFIG` / `BOARDROOM_PROVIDERS_CONFIG` / `BOARDROOM_ROLES_CONFIG`（运行时/供应商/角色配置路径） and the provider secret such as `OPENAI_API_KEY`（模型供应商密钥）; each role-bound YAML provider profile（角色绑定 YAML 供应商配置档） supplies model/base URL/timeout and `response_format: {type: json_object}`. Both commands pass or the script exits with explicit auditable escalation/exhaustion. A skipped provider test is not acceptable completion evidence.

- [ ] **Step 4: Update backlog and acceptance criteria only after real evidence**

After Steps 1-3 produce real evidence:

- In `doc/04-implementation/backlog.md`, set V2-100E status to `DONE`, update Phase 10 progress to `5 / 5`, and update top TL;DR current package to the next open work package.
- In `doc/04-implementation/acceptance-criteria.md`, check Phase 10 V2-100E checkbox and Phase 10 entering-next-stage prerequisites.
- In `doc/05-project-log/2026-06.md`, add one V2-100E entry with command lines and audit export path.
- In `doc/04-implementation/INDEX.md`, ensure new code/test/script files are listed.

- [ ] **Step 5: Final verification after docs update**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop.py tests/negative/test_v2_100_rework_loop_fail_closed.py -q
git diff --check
```

Expected: tests pass and `git diff --check` reports no whitespace errors.

## Self-Review

Spec coverage:

- AC-V2-REWORK-001 / AC-V2-REWORK-002（返工由图治理且需要已验证阻塞项）：Task 2 uses `project_v2_090k_failure_summary`（V2-090K 失败摘要投影） and validates non-empty ReworkIssue（返工问题）.
- AC-V2-REWORK-003（返工范围受合同约束）：Task 4 validates CEO plan and graph patch via existing `validate_ceo_rework_plan`（CEO 返工计划校验） and `validate_graph_patch_review`（图补丁审查校验）.
- AC-V2-REWORK-004（每轮重入证据和检查门禁）：Task 3 and Task 5 require `recheck_rework_attempt`（返工证据重验） and reject stale evidence（陈旧证据）.
- AC-V2-REWORK-005（显式终止）：Task 6 requires `ReworkTerminationDecision`（返工终止决策） when budget is exhausted.
- AC-V2-CLOSEOUT-001~003 / AC-V2-CLOSEOUT-011（收尾证据、重放、流程审计、行为命题）：Task 7 exports event/evidence/provider timeline（事件/证据/模型调用时间线） and Task 8 requires real provider proof before docs completion.
- Provider JSON strategy（模型 JSON 策略）：Task 1 adds negative tests rejecting stale `BOARDROOM_OPENAI_*` env knobs（陈旧环境开关）、`responses` protocol（Responses API 协议）、text output and provider selection by YAML order（按 YAML 顺序选供应商） for V2-100E; Task 2 adds `load_v2_100e_openai_settings`（加载 V2-100E OpenAI 设置） and `validate_v2_100e_provider_json_settings`（V2-100E 供应商 JSON 设置校验器）；Task 4 calls the loader with each `ExecutionPackage.seat_ref`（执行包席位引用） before constructing `OpenAIProviderTransport`（OpenAI 模型传输）.

Placeholder scan:

- No step depends on a future “helper-written passed verdict”（辅助器写通过结论）.
- No happy path uses `FakeProviderTransport`（模拟模型传输） or fallback provider output（降级供应商输出）.
- No happy path assumes `responses` protocol（Responses API 协议） can produce parseable strict JSON under the current adapter（适配器）.
- No task asks implementation workers to read legacy runtime（旧运行时）.
- No production task uses `tests/rework/fixtures/rework_evidence.py`（测试夹具） as design source, shape template, or fact source.
- No task updates backlog（任务清单） or acceptance checkbox（验收勾选） before real verification commands.

Type consistency:

- ReworkReducer（返工归约器） is referenced from `src/boardroom_os/reducers/rework.py`, not from a non-existent `src/boardroom_os/rework/reducer.py`.
- GraphPatchReviewGate（图补丁审查门禁） is referenced through `src/boardroom_os/reducers/rework.py`.
- Planner/reviewer parsers use existing `parse_ceo_rework_planner_payload`（解析 CEO 返工规划载荷） and `parse_graph_patch_review_payload`（解析图补丁审查载荷）.
- Evidence recheck uses existing `ReworkEvidenceRecheckInput`（返工证据重验输入） and `recheck_rework_attempt`（返工证据重验）.
- V2-100E round input/result use `ReworkAttempt`（返工尝试） directly; public payload hashing uses `V2_100ReducerPayload`（归约器载荷联合类型） rather than `Any`（弱类型）, and parallel `attempt_provider_attempts`（并行模型调用记录集合） is not part of the public API（公开接口）.
- Task 3 defines `build_v2_100_resettable_fixture`（构建可重置夹具）、`build_v2_100_scenario_input`（构建场景输入）、`build_accepted_round_input`（构建已接受轮次输入）、`build_two_round_provider`（构建两轮供应器） and `build_exhausted_round_provider`（构建耗尽供应器） before tests reference them, with signatures, return values and implementation order.
- Budget exhaustion negative test（预算耗尽负例） now uses one exhausted round with remaining blockers（剩余阻塞项）, matching `validate_loop_budget`（循环预算校验） semantics.
- Task 4 requires strict CEO/reviewer JSON output shape（严格 JSON 输出形状） inside `ExecutionPackage.constraints`（执行包约束）、`required_outputs`（必需输出） and `audit_requirements`（审计要求） because `ProviderExecutor`（模型执行器） renders those fields and has no separate JSON schema channel.
- Provider profile selection（供应商配置档选择） is role-bound（角色绑定）：`load_v2_100e_openai_settings`（加载 V2-100E OpenAI 设置） loads `BoardroomSettings`（Boardroom 配置聚合） and resolves `role_slot_by_seat(seat_ref)`（按席位取角色配置） then `provider_by_id`（按 ID 取供应商配置）；no code path may use `BoardroomProvidersConfig.providers[0]`（供应商配置集合第一个供应商）.
- Multi-round reducer semantics（多轮归约语义） now keep still-blocked rounds（仍阻塞轮次） open by stopping after `REWORK_REVIEWED`（返工已审查）; only final accepted/escalated/exhausted rounds emit terminal events（终态事件）.
- Payload content binding（载荷内容绑定） is explicit: `V2_100PayloadManifestEntry`（载荷清单条目） stores canonical JSON（规范 JSON） and sha256（哈希）, `V2_100ScenarioResult`（场景结果） carries all entries, and audit export（审计导出） reads entries from result rather than reconstructing payloads from refs（引用）.
- CLI and builder API（命令行与构建器接口） are aligned through `snapshot_summary_path`（失败摘要路径） and `DEFAULT_FAILURE_SUMMARY_PATH`（默认失败摘要路径）.
- Real provider lineage（真实模型供应商来源链） now includes Worker/Tester/Release DevOps（实施/测试/发布运维） ProviderAttempt（模型调用尝试记录） capture and artifact store（产物存储） binding, not only CEO/reviewer（CEO/审查者） calls.
- `ScenarioRoundProvider`（轮次供应器） returns `ScenarioRoundBuild`（轮次构建结果） so each round carries its current-round `payload_resolver`（本轮载荷解析器） and provider-attempt manifest entries（模型调用清单条目） with the input; `run_v2_100_rework_loop_scenario`（运行返工循环场景） owns cumulative resolver merging（累计解析器合并） before reducing historical events.
- Provider integration tests（模型供应商集成测试） inspect `result.provider_attempt_manifest_entries`（结果模型调用清单条目） and require manifest coverage（清单覆盖） for CEO planner attempts（CEO 规划调用）、all reviewer attempts（所有审查者调用） and Worker/Tester/Release DevOps attempts（实施/测试/发布运维调用） from `ReworkAttempt.provider_attempt_refs`（返工尝试模型调用引用）. They inspect `round_result.recheck_result`（轮次重验证结果） rather than a non-existent `round_result.recheck_input`（轮次结果重验输入） field.
- CLI（命令行入口） explicitly calls `export_v2_100_rework_audit`（导出返工审计） after scenario execution and includes the returned audit export（审计导出） in printed result.
- `provider-attempts.json`（模型调用尝试审计文件） is sourced from `V2_100ProviderAttemptManifestEntry`（模型调用清单条目）, including raw/parsed artifact refs（原始/解析产物引用） and sha256 hashes（哈希）.

Expert review gate:

- Implementation must not start until this plan is reviewed and either accepted or amended.
