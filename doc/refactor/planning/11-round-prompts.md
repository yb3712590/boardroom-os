# 每轮推进提示词

## 使用方式

每次新会话或新阶段开始时，复制对应 round 的提示词。每轮默认要求：

1. 先读指定文档，不要全仓库乱读。
2. 只做本轮允许的改动。
3. 做完必须更新本轮指定文档。
4. 运行本轮指定验证。
5. 除非用户明确要求，否则不要 push。
6. 每轮结束时说明：完成项、删除/归档项、验证结果、下一轮入口。

## 当前状态

以下轮次已经完成并提交：

- Round 0：分支与基线盘点。
- Round 1：写入 12 份规划文档。
- Round 2：整理文档入口的最小版本。
- Round 3：仓库瘦身与目录重组。
- Round 4：Backend 废弃代码审计与安全删除。
- Round 5：Directory / Artifact / Write-surface contract 实施。
- Round 6：Provider-only streaming smoke。
- Round 6B：ProviderEvent 标准事件接口。
- Round 6C：Malformed SSE raw archive 与 retry 边界。
- Round 7A：Actor registry 与 capability contract。
- Round 7B：Capability assignment resolver。
- Round 7C：Assignment / Lease identity split。
- Round 7D：Provider provenance 强迁移。
- Round 7E：Phase 3 集成收口与验收。

当前分支：`refactor/autonomous-runtime-docs`。

当前重构控制面入口：

- [INDEX.md](INDEX.md)
- [00-refactor-north-star.md](00-refactor-north-star.md)
- [09-refactor-plan.md](09-refactor-plan.md)
- [10-refactor-acceptance-criteria.md](10-refactor-acceptance-criteria.md)

下一轮新会话应从 **Round 8A：Progression policy contract 与纯函数骨架** 开始。Round 8A–8E 是 Phase 4 Progression policy engine 的连续批次，后续不得在 Phase 4 中重新引入 role name / role_profile_ref / `role_bindings` 作为 runtime execution key、write root、scheduler eligibility 或 provider failover chain；推进规则必须逐步收口到显式 policy。

---

## Round 0：分支与基线盘点（已完成）

```text
你在 D:\Projects\boardroom-os 工作。目标是启动自治 runtime 大重构的准备分支。

必读：
- doc/README.md
- doc/mainline-truth.md
- doc/refactor/planning/INDEX.md
- doc/refactor/planning/00-refactor-north-star.md
- doc/refactor/planning/01-current-state-audit.md

任务：
1. 确认当前分支和 git status。
2. 如尚未创建，创建 refactor/autonomous-runtime-docs 分支。
3. 盘点 tracked generated/cache/log 文件。
4. 不改 runtime 行为。
5. 输出基线摘要。

禁止：
- 删除 backend/frontend runtime code。
- 修改 provider、scheduler、ticket handler 行为。

完成后更新：
- doc/refactor/planning/10-refactor-acceptance-criteria.md 中 Phase 0 对应项。

验收：
- 分支已创建。
- 工作树变更范围清楚。
```

---

## Round 1：写入 12 份规划文档（已完成）

```text
你在 refactor/autonomous-runtime-docs 分支。目标是建立重构控制面。

必读：
- doc/refactor/planning/00-refactor-north-star.md
- doc/tests/intergration-test-015-20260429-final.md
- doc/archive/specs/feature-spec.md
- doc/new-architecture/00-autonomous-machine-overview.md

任务：
1. 确保 doc/refactor/planning/ 下 12 份文档存在。
2. 补齐北极星、当前审计、目标架构、目录契约、写权限、provider、actor lifecycle、progression、deliverable、计划、验收、round prompts。
3. 更新 INDEX.md。
4. 不改代码。

完成后更新：
- doc/refactor/planning/INDEX.md
- doc/refactor/planning/10-refactor-acceptance-criteria.md 中 Phase 0 对应项。

验收：
- 12 份文档可从 INDEX.md 导航。
- 文档明确本轮不承载的愿景。
```

---

## Round 2：整理文档入口（已完成最小版本）

```text
目标：让 doc/README.md 成为清晰入口，并把重构规划纳入默认导航。

必读：
- doc/README.md
- doc/refactor/README.md
- doc/refactor/planning/INDEX.md
- doc/mainline-truth.md

任务：
1. 更新 doc/README.md 的默认首读和工作参考。
2. 新增或更新 doc/refactor/README.md。
3. 明确 doc/new-architecture 是目标 canon，doc/refactor/planning 是执行控制面。
4. 检查相对链接。

禁止：
- 移动 015 报告。
- 移动 feature-spec。

完成后更新：
- doc/refactor/planning/10-refactor-acceptance-criteria.md 中 Phase 0 对应项。

验收：
- 新会话能从 doc/README.md 找到规划文档。
```

---

## Round 3：仓库瘦身与目录重组（已完成）

完成摘要：

- 删除旧 `frontend/` 源码树和本地依赖/构建产物。
- 将旧设计、旧路线、旧任务流水、旧历史记忆、旧会话提示词、旧 refactor 实施资料和 001-014 integration logs 集中归档到 `doc/archive/`。
- 保留 `doc/tests/intergration-test-015-20260429.md` 与 `doc/tests/intergration-test-015-20260429-final.md` 作为 015 压力审计锚点。
- 将 `doc/README.md`、`doc/refactor/README.md`、`doc/archive/README.md`、`01-current-state-audit.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md` 更新为 backend-only runtime rebuild 基线。
- 未修改 provider、scheduler、ticket handler、workflow controller 或 `backend/app/core` runtime 行为。

下一轮从 Round 4 开始。

---

## Round 4：Backend 废弃代码审计与安全删除（已完成）

```text
你在 refactor/autonomous-runtime-docs 分支。Round 3 已完成，仓库目录已经清爽。目标是审计并删除 backend 中明确废弃、无引用、非核心 runtime 的代码。不要开始 provider 或 progression 重构。

必读：
1. doc/README.md
2. doc/mainline-truth.md
3. doc/refactor/planning/00-refactor-north-star.md
4. doc/refactor/planning/01-current-state-audit.md
5. doc/refactor/planning/02-target-architecture.md
6. doc/refactor/planning/03-directory-contract.md
7. doc/refactor/planning/09-refactor-plan.md
8. doc/refactor/planning/10-refactor-acceptance-criteria.md
9. backend/app/core/ 下候选模块
10. backend/tests/ 下对应测试

任务：
1. 列出 backend 当前模块树和测试树。
2. 用 grep 找无引用模块、旧 UI/API 专用模块、旧 scenario-only helper、frozen/compatibility shell。
3. 每个删除候选必须满足：无生产引用、无当前测试引用、非审计证据、非未来目标架构必要入口。
4. 删除安全候选并同步测试。
5. 不拆 ticket_handlers.py/runtime.py/workflow_controller.py 这类核心大模块；只记录拆分建议。
6. 更新 doc/refactor/planning/01-current-state-audit.md 的 backend cleanup 表。
7. 更新 doc/refactor/planning/09-refactor-plan.md 和 10-refactor-acceptance-criteria.md。
8. 提交，message 建议：`refactor-cleanup: remove obsolete backend surfaces`。

禁止：
- 删除 core runtime 行为代码。
- 顺手重构 provider/progression/actor 逻辑。
- 为了让测试过而放宽测试。

验证：
- 后端相关 pytest smoke。
- grep 确认删除路径无引用。
- git diff --stat 以删除废弃代码和文档同步为主。
```

---

## Round 5：Directory / Artifact / Write-surface contract 实施

```text
你在 refactor/autonomous-runtime-docs 分支。Round 4 已完成，backend 废弃 surface 已审计并安全删除。目标是完成 Phase 1：目录 / 产物 / 写权限 contract 的代码化与测试。不要开始 provider、actor lifecycle 或 progression policy 重构。

必读：
1. doc/README.md
2. doc/mainline-truth.md
3. doc/refactor/planning/00-refactor-north-star.md
4. doc/refactor/planning/02-target-architecture.md
5. doc/refactor/planning/03-directory-contract.md
6. doc/refactor/planning/04-write-surface-policy.md
7. doc/refactor/planning/08-deliverable-contract.md
8. doc/refactor/planning/09-refactor-plan.md
9. doc/refactor/planning/10-refactor-acceptance-criteria.md
10. backend/app/core/artifacts.py
11. backend/app/core/artifact_store.py
12. backend/app/core/artifact_handlers.py
13. backend/app/core/ticket_artifacts.py
14. backend/app/core/workspace_path_contracts.py
15. backend/app/core/project_workspaces.py
16. backend/app/core/ticket_handlers.py
17. backend/app/core/workflow_completion.py
18. backend/tests/ 中 artifact、workspace、ticket-result、closeout 相关测试

任务：
1. 盘点当前 artifact ref 类型与实际路径映射，至少覆盖 workspace source、tests evidence、runtime delivery/check/closeout、governance document、upload-import artifact。
2. 将 `03-directory-contract.md` 的 artifact ref -> path 规则落成可独立测试的 contract helper；优先扩展现有 `workspace_path_contracts.py` / artifact helper，不新增大框架。
3. 将 write-set 判断收口到 capability / execution contract 输入；禁止新增 role name -> write root 分支。
4. 为 workspace-managed `source_code_delivery` 增加或补齐 contract tests：source 写入、test evidence、git evidence、doc update refs 都必须落在合法目录。
5. closeout final refs 必须只接受 current delivery/check/verification/closeout evidence；不能引用普通文档、archive、superseded/placeholder/source fallback。
6. placeholder source/test fallback 必须 fail-closed；不要为了让测试过而放宽 schema 或 checker 口径。
7. 更新 `doc/refactor/planning/03-directory-contract.md` 与 `04-write-surface-policy.md` 的实现状态。
8. 更新 `doc/refactor/planning/09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md` 中 Phase 1 对应项。
9. 提交，message 建议：`refactor-contracts: enforce artifact write surfaces`。

禁止：
- 不重构 provider streaming、provider selection 或 model fallback。
- 不重构 actor lifecycle / hiring / capability assignment 主路径；本轮只阻断 role name 决定 write root 的新增或残留写入面。
- 不抽离 progression policy，不改 fanout/rework/closeout 推进判断，除非只是接入 final refs 合法性 guard。
- 不拆 `ticket_handlers.py`、`runtime.py`、`workflow_controller.py` 大模块；如发现拆分点，只记录在 planning docs。
- 不删除审计证据、replay 证据或 `_frozen` 迁移材料。

验证：
- 新增/更新目录契约与 write-surface contract tests。
- 后端相关 pytest smoke，至少覆盖 artifact/workspace/ticket-result/closeout 路径。
- grep 确认没有新增 role name -> write root 判断。
- grep 确认 placeholder fallback 不能进入 final evidence。
- git diff --stat 以 contract helper、测试和 planning docs 为主。
```

---

## Round 6：Provider contract 实施（已完成：provider-only streaming smoke）

```text
目标：重建 provider 稳定性验证，先证明 provider 层，再继续 runtime 重构。

必读：
1. doc/refactor/planning/05-provider-contract.md
2. doc/refactor/planning/09-refactor-plan.md
3. doc/refactor/planning/10-refactor-acceptance-criteria.md
4. backend/app/core/runtime_provider_config.py
5. backend/app/core/runtime.py
6. backend/tests/live/ 相关 provider harness

任务：
1. 建立独立 provider streaming smoke，不依赖 workflow。
2. 区分 connect_timeout、first_token_timeout、stream_idle_timeout、request_total_timeout、ticket_lease_timeout。
3. 分类 malformed SSE、empty assistant、schema validation failure。
4. 记录 preferred/actual provider/model。
5. 不触碰 workflow progression。
6. 更新 provider contract 文档中已实现状态。
7. 更新 acceptance criteria。
8. 提交，message 建议：`refactor-provider: add streaming contract smoke`。

验证：
- provider smoke 可独立运行。
- 相关 provider/parser 单测通过。
```

---

## Round 6B：ProviderEvent 标准事件接口

```text
目标：把 provider adapter 输出从 provider-specific result/audit dict 收口为标准 `ProviderEvent`，但仍不触碰 workflow progression。

必读：
1. doc/refactor/planning/05-provider-contract.md
2. doc/refactor/planning/10-refactor-acceptance-criteria.md
3. backend/app/core/provider_openai_compat.py
4. backend/app/core/runtime_provider_config.py
5. backend/tests/test_provider_openai_compat.py
6. backend/tests/live/openai_compat_reliability_suite.py

任务：
1. 定义最小 `ProviderEvent` 数据结构，覆盖 `request_started`、`connected`、`first_token`、`content_delta`、`heartbeat`、`schema_candidate`、`completed`、`failed_retryable`、`failed_terminal`。
2. 每个 event 必须包含 provider name、model、request id、attempt id、monotonic timestamp、raw byte/text char count、error category。
3. 让 OpenAI-compatible streaming adapter 产生标准事件；可以保留现有 `OpenAICompatProviderResult` 作为聚合结果，但事件必须可独立测试。
4. 更新 provider-only smoke 报告，使其从标准事件中统计 first token、idle gap、stream bytes/chars、failure category。
5. 不写 ticket projection，不创建 workflow/ticket，不改 scheduler/progression。
6. 更新 `05-provider-contract.md` 与 `10-refactor-acceptance-criteria.md`。
7. 提交，message 建议：`refactor-provider: standardize streaming events`。

验证：
- provider event 单测覆盖 request_started/connected/first_token/content_delta/completed/failed。
- provider-only smoke 仍可独立运行。
- `pytest backend/tests/test_provider_openai_compat.py -q` 通过。
```

---

## Round 6C：Malformed SSE raw archive 与 retry 边界

```text
目标：补齐 malformed SSE 的 raw archive 和 provider retryable 分类，不把 malformed stream 简化为普通 bad response。

必读：
1. doc/refactor/planning/05-provider-contract.md
2. doc/refactor/planning/10-refactor-acceptance-criteria.md
3. backend/app/core/provider_openai_compat.py
4. backend/app/core/runtime.py
5. backend/app/core/artifact_store.py
6. backend/tests/test_provider_openai_compat.py
7. backend/tests/test_scheduler_runner.py 中 provider retry/failure 相关测试

任务：
1. 为 malformed SSE 保存 raw event archive，记录 request id、response id、attempt id、provider/model、raw byte count、parse error。
2. 明确 `MALFORMED_STREAM_EVENT` 是否映射为 retryable provider attempt failure，并补齐 runtime retry/failover 测试。
3. 保证 raw archive 不进入 final delivery evidence，不被当作 source/test/closeout artifact。
4. provider adapter 不创建 ticket；runtime 只能消费 failure category 和 archive ref，不能伪造 provider success。
5. 更新 provider contract 和 acceptance criteria。
6. 提交，message 建议：`refactor-provider: archive malformed stream events`。

验证：
- malformed SSE 单测证明 raw archive 写入且 failure kind 为 `MALFORMED_STREAM_EVENT`。
- runtime/provider retry 单测证明该 failure 不被归为 `UPSTREAM_UNAVAILABLE` 或普通 `PROVIDER_BAD_RESPONSE`。
- artifact legality 测试证明 raw archive 不可作为 closeout final evidence。
```

---

## Round 6D：Late provider event projection guard

```text
目标：证明 late provider event 不污染 current ticket projection，并把旧 attempt 输出与 current graph pointer 隔离。

必读：
1. doc/refactor/planning/05-provider-contract.md
2. doc/refactor/planning/07-progression-policy.md
3. doc/refactor/planning/10-refactor-acceptance-criteria.md
4. backend/app/core/runtime.py
5. backend/app/core/ticket_handlers.py
6. backend/app/core/projections.py
7. backend/tests/test_scheduler_runner.py
8. backend/tests/test_ticket_graph.py

任务：
1. 为 timed out / superseded provider attempt 后到达的 heartbeat/completed/output 建立回归测试。
2. late heartbeat 只能归档或记录为旧 attempt event，不能更新 current ticket projection。
3. late completed/output 不能把旧 ticket 标为 completed，不能改写 current graph pointer，不能生成 final evidence。
4. 如需利用 late output，只能产生显式 recovery action，并记录 lineage；本轮先 fail-closed，不做自动采用。
5. 不扩大 progression policy；只加 provider attempt lineage 和 projection guard。
6. 更新 provider contract、progression policy 文档和 acceptance criteria。
7. 提交，message 建议：`refactor-provider: guard late attempt events`。

验证：
- 单测覆盖 old attempt late heartbeat、late completed、late output 三类输入。
- current ticket projection、runtime node pointer、final evidence set 均不被 late event 改写。
- provider-only smoke 不受影响。

实施边界补充：当前 provider 实施以 OpenAI Responses streaming 为唯一范围，沿用已落地的 `ProviderRequest -> ProviderEvent stream -> ProviderResult/ProviderFailure` ticket 调用层接入；暂不抽象 Anthropic/Gemini。Provider 本身只处理请求与返回，并按 cc-switch/Codex-like 体验在 provider 内部最多做 5 次标准重试，以健壮拿到正确返回为目标，不创建 ticket、不推进 workflow、不写 projection、不做额外审计动作。超过 5 次仍失败才返回最终 provider failure，由 runtime 现有异常处理、failover、incident 或 recovery 机制消费；runtime 不能伪造 provider success。
```

---

## Round 7 连续批次总约束：Actor / Role lifecycle 强迁移

Round 7A/7B/7C/7D/7E 是同一 Phase 3 强迁移的连续批次，不是互相独立的改造任务。每个批次开始时必须先确认自己处在这条链路中，并继承前序批次已经确定的模型、命名和边界。

共同目标：让 runtime 执行身份从 role template 迁移到 actor/capability/assignment/lease 模型，并最终覆盖 `10-refactor-acceptance-criteria.md` 的 Phase 3 全部验收项。Round 7 的实现策略是强迁移优先、简洁高效达成验收；旧 employee/role_profile_ref 路径只作为待迁移输入来源或测试历史，不作为需要长期兼容的目标架构。

连续性规则：

1. 每个 7x 批次都必须阅读本节总约束、自己的批次提示词、`06-actor-role-lifecycle.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`。
2. 7B–7E 必须先阅读前序 7x 批次在 `06-actor-role-lifecycle.md`、`09-refactor-plan.md`、`10-refactor-acceptance-criteria.md` 中留下的实现状态和未完成项，不得重新设计一套不兼容模型。
3. 统一术语：`actor_id` 是 runtime 执行身份；`employee_id` 是产品/公司化表示；`role_profile_ref` / RoleTemplate 只能映射默认 capability/provider preference，不能作为 runtime 执行键；`assignment_id` 表示谁被选中；`lease_id` 表示当前执行窗口。
4. 为了简洁高效完成强迁移，允许在当前批次内新增或修改必要的 DB schema、projection、repository API、command/event payload 和测试 fixture；不要因为旧实现已有 employee/role_profile_ref 字段而回避结构性替换。
5. 每批优先删除或替换旧 runtime 决策路径，而不是包一层长期兼容 adapter；仅当外部 API、历史事件 replay 或测试 fixture 暂时需要时保留兼容读取，并明确标注迁移边界和后续移除点。
6. 每批结束必须更新对应 planning docs，写清：本批完成项、仍依赖后续批次的接口、已删除/替换的旧路径、不能破坏的新模型边界、下一批入口。
7. 每批只勾选 `10-refactor-acceptance-criteria.md` 中已有证据支撑的 Phase 3 checkbox；没有测试或 grep 证据不得提前勾选。
8. 不得把 Phase 4 progression policy、Phase 5 deliverable contract 或 Phase 6 replay/resume 的范围提前混入 Round 7；如发现依赖，只记录为后续 phase blocker。
9. 不得新增 role name -> write root、role name -> provider execution key、role name -> scheduler eligibility 的分支；任何保留的 role 字段都必须证明不在 runtime kernel 决策路径上。
10. 每批提交前必须运行本批指定测试和相关 grep；失败不得声称完成。

---

## Round 7A：Actor registry 与 capability contract

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 7A/7B/7C/7D/7E 连续批次的第 1 批，目标是建立 Phase 3 的 Actor registry 和 RoleTemplate -> Capability contract。按强迁移实施：允许新增/修改必要 DB schema、projection、repository API、事件 payload 和测试 fixture；不要为了兼容旧 employee/role_profile_ref 实现而把 actor_projection 降级为临时内存 helper。不要开始 assignment/lease/provider 全链路迁移。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 7 连续批次总约束
2. doc/refactor/planning/06-actor-role-lifecycle.md
3. doc/refactor/planning/04-write-surface-policy.md
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/constants.py
7. backend/app/core/reducer.py
8. backend/app/core/projections.py
9. backend/app/db/repository.py
10. backend/tests/test_reducer.py
11. backend/tests/test_execution_targets.py

任务：
1. 建立 Actor registry：定义 actor lifecycle 状态与事件/投影语义，覆盖 enable/suspend/deactivate/replace；如需要持久化 actor projection，直接新增/修改 DB schema 与 repository 读取 API。
2. 将现有 employee projection 与 actor runtime identity 明确分层：employee 只保留为产品/公司化表示或历史输入来源，runtime 后续以 actor eligibility 作为执行资格。
3. 建立 RoleTemplate -> CapabilitySet 映射 helper；RoleTemplate 只能输出 capability/provider preference，不能输出 runtime execution key。
4. 将能直接迁移的 employee/role_profile_ref runtime 读取点替换为 actor/capability 读取点；确需保留的 role_profile_ref 只允许作为输入编译 capability 或展示字段。
5. 为 actor enable/suspend/deactivate/replace、RoleTemplate 只映射 capability 补单测。
6. 更新 `06-actor-role-lifecycle.md`：写清 7A 已落地的数据结构、事件、投影和后续批次依赖。
7. 更新 `09-refactor-plan.md` 与 `10-refactor-acceptance-criteria.md`：只勾 7A 已有测试证据支撑的 Phase 3 项。
8. 提交，message 建议：`refactor-actors: add lifecycle registry`。

禁止：
- 不改 scheduler 主派工算法。
- 不把 Assignment 与 Lease 一次性做完。
- 不改 provider selection 行为。
- 不回避必要 DB schema / projection / repository API 修改；本批要产出可被后续 7B–7E 直接使用的持久化 actor registry。
- 不保留旧 employee lifecycle 作为 runtime 资格判断的主路径；需要保留时只能作为历史输入或产品展示边界。

验证：
- 单测覆盖 actor enable/suspend/deactivate/replace 状态机。
- 单测覆盖 RoleTemplate 只映射 capability、不作为 runtime execution key。
- grep 确认 7A 未新增 role name -> write root / execution key 分支。
- 相关 reducer/projection/repository 测试通过。
```

---

## Round 7B：Capability-driven Assignment 与 scoped exclusion

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 7A/7B/7C/7D/7E 连续批次的第 2 批，必须继承 7A 的 actor registry 和 RoleTemplate -> Capability contract。目标是把派工选择输入收口为 required capabilities + actor eligibility，并修复 scoped exclusion 与 no eligible actor 显式动作。按强迁移实施：优先替换旧 role_profile_ref/employee matching 派工路径，不要新增长期兼容分支。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 7 连续批次总约束
2. doc/refactor/planning/06-actor-role-lifecycle.md 中 7A 实现状态
3. doc/refactor/planning/04-write-surface-policy.md
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/workflow_controller.py
7. backend/app/core/ticket_handlers.py
8. backend/app/core/execution_targets.py
9. backend/app/core/runtime_provider_config.py 中 provider health/circuit breaker 读取点
10. backend/tests/test_scheduler_runner.py
11. backend/tests/test_api.py 中 retry/rework/excluded_employee_ids 相关测试

任务：
1. 抽出 assignment resolver：输入为 ticket required capabilities、actor registry/projection、actor status、provider health、current active leases、scoped exclusion policy。
2. 将 ready ticket / scheduler candidate 判断从 role_profile_ref matching 替换为 actor capability eligibility；role_profile_ref 只能作为迁移期输入编译 capability，不得继续参与 runtime eligibility 判断。
3. 定义 `excluded_employee_ids` 的迁移解释和新 scoped exclusion 语义，至少覆盖 attempt/ticket/node/capability/workflow；禁止无作用域复制旧 ticket excluded list。
4. 修复 retry/rework 的 exclusion 污染风险；必要时将 legacy `excluded_employee_ids` 转换为 scoped exclusion 后再使用，而不是继续沿用旧列表语义。
5. no eligible actor 时必须生成显式 action 或 incident payload，包含 required capabilities、候选 actor 排除原因、建议动作（CREATE_ACTOR / REASSIGN_EXECUTOR / REQUEST_HUMAN_DECISION / BLOCK_NODE_NO_CAPABLE_ACTOR）。
6. 为 capability-driven assignment、scoped exclusion、no eligible actor 显式 action/incident 补单测。
7. 更新 `06-actor-role-lifecycle.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`，写明 7B 完成项与 7C 对 lease 分离的依赖。
8. 提交，message 建议：`refactor-actors: assign by capability eligibility`。

禁止：
- 不把 role_profile_ref 重新包装成 actor execution key。
- 不保留 role_profile_ref/employee matching 作为并行派工 fallback；发现测试依赖时应迁移测试 fixture 和断言到 actor/capability。
- 不用 ticket summary 文本、hardcoded employee id 或 role name fallback 选择 executor。
- 不改 closeout/fanout/rework progression policy 业务判断；只处理派工 eligibility 和显式 no-eligible 输出。

验证：
- 单测覆盖派工由 required capabilities + actor eligibility 驱动。
- 单测覆盖 scoped `excluded_employee_ids` 不污染无关派工。
- 单测覆盖 no eligible actor 生成显式 action 或 incident，不能 silent stall。
- grep 确认 scheduler/controller/ticket handler 未新增 role name -> execution key 分支。
```

---

## Round 7C：Assignment 与 Lease 分离

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 7A/7B/7C/7D/7E 连续批次的第 3 批，必须继承 7A actor registry 和 7B assignment resolver。目标是把 Assignment 与 Lease 分离，并证明 replace 后旧 actor 不再 eligible、新 actor 不继承旧 lease。按强迁移实施：ticket lease/start/timeout、context compiler 和 runtime package 都应迁到 actor/assignment/lease identity；旧 lease_owner 只允许作为历史展示/迁移字段，不得继续作为执行身份。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 7 连续批次总约束
2. doc/refactor/planning/06-actor-role-lifecycle.md 中 7A/7B 实现状态
3. doc/refactor/planning/05-provider-contract.md 的 ticket_lease_timeout / late event 边界
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/ticket_handlers.py
7. backend/app/core/runtime.py
8. backend/app/core/context_compiler.py
9. backend/app/core/projections.py
10. backend/app/core/reducer.py
11. backend/tests/test_context_compiler.py
12. backend/tests/test_scheduler_runner.py
13. backend/tests/test_reducer.py

任务：
1. 引入 assignment 与 lease 的独立事件/投影语义：assignment 表示 actor 被选中，lease 表示有限时间执行窗口。
2. ticket lease/start/timeout 路径必须改为携带 actor_id、assignment_id、lease_id；旧 `lease_owner` 只能作为历史展示或迁移字段，不得继续驱动 runtime execution identity。
3. lease timeout 只终止 lease/execution attempt，不得撤销 assignment 历史，也不得恢复过期 actor eligibility。
4. replace 场景必须证明：旧 actor 被 REPLACED / DEACTIVATED / SUSPENDED 后不再 eligible；新 actor 可继承 capability/assignment 资格，但不继承旧 lease。
5. context compiler / runtime execution package 读取 assignment/lease identity，不再以 role template 作为 runtime execution identity。
6. 为 Assignment 与 Lease 分离、lease 过期、replace 后旧 actor 不 eligible、新 actor 不继承旧 lease 补单测。
7. 更新 `06-actor-role-lifecycle.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`，写明 7C 完成项与 7D provider provenance 依赖。
8. 提交，message 建议：`refactor-actors: separate assignment leases`。

禁止：
- 不让 `ASSIGNED` 等同于 `LEASED`。
- 不让 `LEASED` 等同于 `EXECUTING`。
- 不允许 late provider completion 自动恢复过期 lease。
- 不把 replace 实现成简单新建 employee 后继续沿用旧 lease。

验证：
- 单测覆盖 Assignment 与 Lease 分离及 lease 过期。
- 单测覆盖 replace 后旧 actor 不再 eligible、新 actor 不继承旧 lease。
- 单测覆盖 execution package 中 actor/assignment/lease identity。
- 相关 scheduler/runtime/context compiler 测试通过。
```

---

## Round 7D：Provider provenance 贯穿 Actor Assignment / Execution

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 7A/7B/7C/7D/7E 连续批次的第 4 批，必须继承 7A actor registry、7B assignment resolver 和 7C assignment/lease 分离。目标是把 provider preferred/actual provider/model 贯穿 actor assignment、execution attempt 和 result evidence，并与 provider smoke 字段一致。按强迁移实施：provider selection 以 actor/capability/provider preference 为输入，旧 role binding 只能作为 RoleTemplate 默认 preference 的来源，不得继续作为 provider execution key。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 7 连续批次总约束
2. doc/refactor/planning/06-actor-role-lifecycle.md 中 7A/7B/7C 实现状态
3. doc/refactor/planning/05-provider-contract.md
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/runtime_provider_config.py
7. backend/app/core/runtime.py
8. backend/app/core/ticket_handlers.py
9. backend/app/core/ticket_context_archive.py
10. backend/tests/test_runtime_provider_center.py
11. backend/tests/test_scheduler_runner.py 中 provider failover/provenance 相关测试
12. backend/tests/live/openai_compat_reliability_suite.py

任务：
1. provider selection 输入从 role binding execution key 替换为 actor assignment/capability/provider preference；role template 只提供默认 preference，不是不可变执行事实。
2. actor assignment payload 记录 preferred_provider_id、preferred_model、actual_provider_id、actual_model、selection_reason、fallback_reason/policy_reason、provider health snapshot、cost/latency class（能从现有字段取得的先落地）。
3. execution attempt / provider audit / result evidence 必须保留同一套 preferred/actual provider/model 字段，并与 provider-only smoke 报告字段命名一致。
4. provider failover 不得静默伪装成原 provider 成功；actual provider/model 必须反映最终执行 provider。
5. 更新 runtime/provider tests，覆盖 actor assignment provenance、execution attempt provenance、result evidence provenance 和 failover 字段一致性。
6. 更新 `05-provider-contract.md`、`06-actor-role-lifecycle.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`，写明 7D 完成项与 7E integration cleanup 依赖。
7. 提交，message 建议：`refactor-actors: record provider provenance`。

禁止：
- 不保留 role binding 作为 runtime provider execution fallback；需要读取旧配置时必须先转换为 actor/capability/provider preference。
- 不把 provider fallback 的 actual provider/model 写成 preferred provider/model。
- 不改 provider-only smoke 的独立性；它仍不得创建 workflow/ticket/lease。

验证：
- 单测覆盖 provider preferred/actual 在 actor assignment / execution attempt / result evidence 中记录完整。
- 单测覆盖 provider failover 的 preferred/actual 字段差异与 selection_reason/policy_reason。
- provider smoke 字段与 runtime provenance 字段一致。
- grep 确认 provider selection 路径未新增 role name -> execution key 判断。
```

---

## Round 7E：Phase 3 集成收口与验收

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 7A/7B/7C/7D/7E 连续批次的第 5 批，也是 Phase 3 Actor / Role lifecycle 的集成收口。必须继承 7A–7D 的所有实现状态，不得重新设计模型。目标是清理残余 role-template runtime key、补齐文档和验收证据，然后把下一轮入口交给 Round 8。按强迁移收口：优先删除旧 runtime 决策路径和测试依赖，而不是为旧 employee/role_profile_ref 行为留长期兼容。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 7 连续批次总约束
2. doc/refactor/planning/06-actor-role-lifecycle.md 中 7A–7D 实现状态
3. doc/refactor/planning/04-write-surface-policy.md
4. doc/refactor/planning/05-provider-contract.md
5. doc/refactor/planning/09-refactor-plan.md
6. doc/refactor/planning/10-refactor-acceptance-criteria.md
7. backend/app/core/workflow_controller.py
8. backend/app/core/ticket_handlers.py
9. backend/app/core/runtime.py
10. backend/app/core/runtime_provider_config.py
11. backend/app/core/projections.py
12. backend/tests/ 中 actor、assignment、lease、provider selection、scheduler/runtime 相关测试

任务：
1. 全面 grep runtime、scheduler、controller、ticket handler、provider selection、context compiler，确认 role name / role_profile_ref / `role_bindings` / binding target refs 不再作为 runtime execution key、write root、scheduler eligibility 或 provider failover chain。
2. 对确需保留的 role_profile_ref 字段逐一标注其边界：治理模板、产品展示、legacy input 编译 capability、测试 fixture；不得留在 runtime kernel 决策路径。
3. 补齐或收敛 7A–7D 留下的 Phase 3 测试缺口，确保 actor lifecycle、replace、RoleTemplate capability mapping、assignment/lease、scoped exclusion、no eligible actor、provider provenance 都有测试证据。
4. 清理或隔离 `runtime_provider_config.py` 中仍为历史配置 shape 保留的 `role_bindings` / `provider_model_entries`：可删除的旧 helper 和测试依赖直接删除；确需保留的只允许作为配置导入/展示/RoleTemplate 默认 preference 来源，并在文档中写清边界。
5. 更新 `06-actor-role-lifecycle.md` 的最终实现状态和剩余后续 phase 依赖。
6. 更新 `04-write-surface-policy.md`：确认 Phase 3 未重新引入 role name -> write root。
7. 更新 `05-provider-contract.md`：确认 provider provenance 与 actor assignment/execution attempt/result evidence 字段一致。
8. 更新 `09-refactor-plan.md` 与 `10-refactor-acceptance-criteria.md`：只有在测试/grep 证据存在时勾选 Phase 3 全部 checkbox。
9. 更新本文件当前状态：Round 7A–7E 已完成后，下一轮应从 Round 8 Progression policy engine 开始。
9. 提交，message 建议：`refactor-actors: close phase3 acceptance`。

禁止：
- 不为了让 grep 通过删除仍被测试证明需要的产品/治理字段；正确做法是把它们移出 runtime 决策路径或迁移测试到 actor/capability 语义。
- 不把 Phase 4 progression policy 改造塞进本轮。
- 不用“计划后续覆盖”冒充 Phase 3 checkbox 完成。

验证：
- actor lifecycle 全套单测通过。
- replace 后旧 actor 不再 eligible、新 actor 不继承旧 lease 测试通过。
- RoleTemplate 只映射 capability、不作为 runtime execution key 测试通过。
- Assignment 与 Lease 分离及 lease 过期测试通过。
- scoped `excluded_employee_ids` 测试通过。
- no eligible actor 显式 action/incident 测试通过。
- provider preferred/actual 记录完整测试通过。
- grep 确认没有保留或新增 role name -> write root / execution key 判断，尤其检查 runtime、scheduler、provider selection、context compiler 路径。
- Phase 3 acceptance criteria 每个勾选项都有测试命令或 grep 证据。
```

---

## Round 8 连续批次总约束：Progression policy engine 抽离

Round 8A/8B/8C/8D/8E 是同一 Phase 4 强迁移的连续批次，不是互相独立的改造任务。每个批次开始时必须先确认自己处在这条链路中，并继承前序批次已经确定的 snapshot、policy、action proposal、reason code、idempotency key 和 graph pointer 语义。

共同目标：把推进规则从 controller/runtime/scheduler/CEO proposer 中迁移到显式 `decide_next_actions(snapshot, policy)` policy engine，并最终覆盖 `10-refactor-acceptance-criteria.md` 的 Phase 4 全部验收项。Round 8 的实现策略是先立纯函数 contract，再按 graph pointer、governance/fanout、closeout/recovery、orchestration 收口顺序强迁移；旧 controller/runtime/scheduler/proposer 路径只允许作为 policy 输入组装、调用入口或临时兼容壳，不得继续承载新的业务判断。

连续性规则：

1. 每个 8x 批次都必须阅读本节总约束、自己的批次提示词、`07-progression-policy.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`。
2. 8B–8E 必须先阅读前序 8x 批次在 `07-progression-policy.md`、`09-refactor-plan.md`、`10-refactor-acceptance-criteria.md` 中留下的实现状态和未完成项，不得重新设计一套不兼容 policy contract。
3. 统一术语：`ProgressionSnapshot` 是结构化只读输入；`ProgressionPolicy` 是显式策略输入；`ActionProposal` 是 policy 输出；`source_graph_version` 是所有 action 的来源版本；`idempotency_key` 必须由稳定结构化字段生成；`affected_node_refs` 必须指向 graph/runtime node ref，而不是 freeform 文本。
4. `decide_next_actions(snapshot, policy)` 必须保持纯函数：不得读取 DB、markdown 正文、provider raw transcript、artifact 文件正文或 freeform `hard_constraints` substring；这些数据必须先被外层编译成结构化 snapshot/policy 字段。
5. 每个 action proposal 至少包含：action type、reason code、idempotency key、source graph version、affected node refs、expected state transition、policy ref；`CREATE_TICKET`、`WAIT`、`REWORK`、`CLOSEOUT`、`INCIDENT`、`NO_ACTION` 六类 action 必须逐步补齐测试证据。
6. Effective graph pointer 必须由 graph version、node/ticket lineage、replacement/supersession/cancellation 结构化关系决定，不得由 ticket `updated_at`、orphan pending、stale snapshot node 或 provider late output 决定。
7. `CANCELLED` / `SUPERSEDED` 节点和 ticket 不得参与 effective edges、readiness、graph complete 或 closeout；`FAILED` / `TIMED_OUT` 只有被 recovery action 明确引用时才参与恢复判断。
8. 删除 substring hint / hardcoded milestone fanout 前必须先补回归测试；会议 gate、架构 gate、backlog fanout 必须由 policy input / graph patch / structured governance requirement 驱动。
9. 每批优先替换旧业务判断路径，而不是包一层长期兼容 adapter；仅当外部 API、历史事件 replay 或测试 fixture 暂时需要时保留兼容读取，并明确标注迁移边界和后续移除点。
10. 不得把 Phase 5 deliverable contract、Phase 6 replay/resume 或 Phase 7 015 replay 包验证提前混入 Round 8；如发现依赖，只记录为后续 phase blocker 或明确归入 replay 验证。
11. 每批结束必须更新对应 planning docs，写清：本批完成项、仍依赖后续批次的接口、已删除/替换的旧路径、不能破坏的新 policy 边界、下一批入口。
12. 每批只勾选 `10-refactor-acceptance-criteria.md` 中已有测试或 grep 证据支撑的 Phase 4 checkbox；没有证据不得提前勾选。
13. 每批提交前必须运行本批指定测试和相关 grep；失败不得声称完成。

---

## Round 8A：Progression policy contract 与纯函数骨架

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 8A/8B/8C/8D/8E 连续批次的第 1 批，目标是建立 Phase 4 的显式 progression policy contract 和可独立测试的 `decide_next_actions(snapshot, policy)` 纯函数骨架。不要迁移全部 controller/fanout/closeout/recovery 行为；本批只立稳定输入输出、metadata、reason code/idempotency 规则和最小兼容调用入口。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 8 连续批次总约束
2. doc/refactor/planning/07-progression-policy.md
3. doc/refactor/planning/09-refactor-plan.md
4. doc/refactor/planning/10-refactor-acceptance-criteria.md
5. backend/app/core/workflow_progression.py
6. backend/app/core/workflow_controller.py
7. backend/app/core/ceo_proposer.py
8. backend/app/core/ticket_graph.py
9. backend/tests/test_workflow_progression.py
10. backend/tests/test_ceo_scheduler.py 中 controller/proposer fallback 相关测试

任务：
1. 定义 `ProgressionSnapshot`、`ProgressionPolicy`、`ActionProposal` 的最小数据结构；字段必须覆盖 graph version、node/ticket refs、ready/blocked/in-flight indexes、incidents/approvals、actor/provider availability summary、governance/fanout/closeout/recovery policy input。
2. 实现 `decide_next_actions(snapshot, policy)` 纯函数骨架；本批可以只覆盖明确结构化输入下的 `WAIT`、`NO_ACTION` 和最小 `CREATE_TICKET` proposal，但函数签名和返回 contract 必须能承载六类 action。
3. 为 `CREATE_TICKET`、`WAIT`、`REWORK`、`CLOSEOUT`、`INCIDENT`、`NO_ACTION` 建立统一 action metadata helper：reason code、idempotency key、source graph version、affected node refs、expected state transition、policy ref。
4. 补纯函数单测：相同 snapshot + policy 输出稳定 action proposals；六类 action metadata helper 输出稳定且不依赖 dict/list 非确定顺序。
5. 让旧 `workflow_progression.py` 或 controller/proposer 只在最小范围内能调用新 policy helper；不得在本批大规模迁移业务判断。
6. 更新 `07-progression-policy.md`：记录 8A 已落地的 snapshot/policy/action proposal contract、纯函数边界和后续批次依赖。
7. 更新 `09-refactor-plan.md` 与 `10-refactor-acceptance-criteria.md`：只勾 8A 已有测试证据支撑的 Phase 4 项；如六类 action 仅完成 metadata helper，不得声称 controller/scheduler 已迁移。
8. 提交，message 建议：`refactor-policy: add progression action contract`。

禁止：
- 不读取 DB、markdown 正文、provider raw transcript、artifact 文件正文或 freeform hard_constraints substring。
- 不迁移 backlog fanout、meeting/architect gate、closeout、rework/restore、scheduler orchestration 主路径。
- 不修改 Phase 5 deliverable contract 或 Phase 6 replay/resume 行为。
- 不为了让旧测试通过而把旧 controller state dict 直接定义成新 policy contract。

验证：
- `decide_next_actions(snapshot, policy)` 纯函数单测通过。
- 六类 action proposal metadata helper 单测通过，覆盖 reason code / idempotency key / source graph version / affected node refs / expected state transition。
- 相同 snapshot + policy 重复调用输出完全一致。
- grep 确认新 policy 模块未读取 DB、markdown 正文、provider raw transcript 或 hard_constraints substring。
```

---

## Round 8B：Effective graph pointer 与 readiness policy

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 8A/8B/8C/8D/8E 连续批次的第 2 批，必须继承 8A 的 ProgressionSnapshot / ProgressionPolicy / ActionProposal contract。目标是把 effective graph pointer、ready/blocked/complete 判断收口到 policy，证明 orphan pending 不阻断 graph complete，CANCELLED/SUPERSEDED 不参与 effective edges。不要开始 governance/backlog fanout 或 closeout/recovery 强迁移。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 8 连续批次总约束
2. doc/refactor/planning/07-progression-policy.md 中 8A 实现状态
3. doc/refactor/planning/05-provider-contract.md 的 late provider event / current pointer 边界
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/ticket_graph.py
7. backend/app/core/runtime_node_lifecycle.py
8. backend/app/core/runtime_node_views.py
9. backend/app/core/projections.py
10. backend/tests/test_ticket_graph.py
11. backend/tests/test_workflow_progression.py
12. backend/tests/test_scheduler_runner.py 中 graph/ready/blocked 相关测试

任务：
1. 将 graph version、runtime nodes、ticket lineage、replacement/supersession/cancellation、ready/blocked/in-flight indexes 编译进结构化 snapshot；policy 只消费 snapshot，不直接查 repository。
2. 在 policy 中实现 effective graph pointer 规则：`REPLACES` 指向的新 ticket 是 current；`SUPERSEDED` / `CANCELLED` 不参与 readiness/effective edges；orphan pending 不阻断 graph complete；late old attempt 只保留 lineage，不影响 current pointer。
3. 为 ready/blocked/complete 输出 `WAIT` / `NO_ACTION` / `INCIDENT` proposal：包括 open approval、open incident、in-flight runtime、graph reduction issue、stale/orphan pending、blocked node 无恢复动作等 reason code。
4. 补 015 stale gate、orphan pending 的 policy 回归测试；如某些 015 细节必须等 replay DB 才能验证，必须在文档中明确归入 Phase 7 replay 验证并说明本批覆盖的结构化等价场景。
5. 将 controller/scheduler 中能安全替换的 graph wait / ready / blocked 判断改为调用 policy 输出；不能安全替换的路径必须保留为兼容壳并标注后续 8E 收口。
6. 更新 `07-progression-policy.md`、`05-provider-contract.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`，写明 8B 完成项与 8C fanout 依赖。
7. 提交，message 建议：`refactor-policy: resolve effective graph pointers`。

禁止：
- 不用 ticket `updated_at` 作为 current graph pointer。
- 不让 orphan pending、stale snapshot node 或 old provider late output 阻断 graph complete。
- 不把 CANCELLED/SUPERSEDED 节点纳入 effective edges、readiness 或 closeout。
- 不迁移 backlog fanout、meeting/architect gate、closeout/rework 主判断。

验证：
- policy 单测覆盖 orphan pending 不阻断 graph complete。
- policy 单测覆盖 CANCELLED/SUPERSEDED effective edges 不参与 readiness/complete。
- policy 单测覆盖 stale gate / blocked / in-flight / approval / incident 的 WAIT 或 NO_ACTION reason code。
- 相关 `test_ticket_graph.py`、`test_workflow_progression.py`、scheduler graph smoke 通过。
- grep 确认新增 graph pointer policy 不读取 DB 或 provider raw transcript。
```

---

## Round 8C：Governance gate 与 backlog fanout policy

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 8A/8B/8C/8D/8E 连续批次的第 3 批，必须继承 8A 的 policy contract 和 8B 的 effective graph pointer/readiness 语义。目标是把 governance chain、architect gate、meeting gate、backlog followup fanout 从 controller/CEO proposer 迁移到 policy input / graph patch / structured governance requirement；删除 substring hint 和 hardcoded milestone fanout 作为推进依据。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 8 连续批次总约束
2. doc/refactor/planning/07-progression-policy.md 中 8A/8B 实现状态
3. doc/refactor/planning/09-refactor-plan.md
4. doc/refactor/planning/10-refactor-acceptance-criteria.md
5. backend/app/core/workflow_progression.py
6. backend/app/core/workflow_controller.py
7. backend/app/core/ceo_proposer.py
8. backend/app/core/ceo_execution_presets.py
9. backend/app/core/output_schemas.py
10. backend/tests/test_ceo_scheduler.py
11. backend/tests/test_workflow_progression.py
12. backend/tests/test_workflow_autopilot.py 中 governance/fanout 相关测试

任务：
1. 把 governance progression 输入建成结构化 policy 字段：governance chain order、completed governance outputs、required governance gates、meeting requirements、approved meeting evidence、backlog implementation handoff、fanout graph patch plan。
2. 将 `resolve_next_governance_schema`、governance followup planning、required architect governance gate、meeting candidate、backlog followup ticket plan 转为 policy 决策或 policy input 编译 helper；controller 只负责组装 snapshot/policy 和执行 proposal。
3. hardcoded backlog milestone fanout 必须被 policy input / graph patch 替代；CREATE_TICKET proposal 必须携带稳定 reason code、idempotency key、source graph version、affected node refs 和 expected transition。
4. 删除或停用 freeform `hard_constraints` substring 驱动的 `requires_architect` / `requires_meeting`；会议/架构 gate 只能由结构化 governance requirement 或 graph patch 决定。
5. 删除 substring hint / hardcoded milestone fanout 前先补回归测试，覆盖：无结构化 gate 时不因字符串触发会议/架构 gate；有结构化 gate 时产生正确 CREATE_TICKET / WAIT / NO_ACTION。
6. 将 CEO proposer 中可安全迁移的 backlog followup fallback 改为消费 policy proposal；retry/restore 仍留给 8D。
7. 更新 `07-progression-policy.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`，写明 8C 已替换的旧路径和仍留给 8D/8E 的 closeout/recovery/orchestration 路径。
8. 提交，message 建议：`refactor-policy: drive fanout from structured policy`。

禁止：
- 不用 freeform hard_constraints substring 判断会议 gate、架构 gate 或 fanout。
- 不把 backlog recommendation artifact 正文读取放进 `decide_next_actions()`；artifact 内容必须由外层编译为结构化 policy input。
- 不让 role name / role_profile_ref / role_bindings 重新成为 runtime execution key、scheduler eligibility 或 provider failover chain。
- 不迁移 closeout、retry/restore、BR-100 loop 主判断。

验证：
- policy 单测覆盖 governance followup CREATE_TICKET proposal 的稳定 metadata。
- policy 单测覆盖 structured architect/meeting gate；grep 确认 substring hint 不再驱动 gate。
- policy 单测覆盖 backlog fanout 由 structured input / graph patch 产生，不由 hardcoded milestone fanout 产生。
- 相关 `test_ceo_scheduler.py` / `test_workflow_progression.py` governance/fanout 测试通过。
- grep 确认 controller/proposer 中不再用 hard_constraints substring 驱动会议、架构 gate 或 backlog fanout。
```

---

## Round 8D：Closeout、rework、restore policy

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 8A/8B/8C/8D/8E 连续批次的第 4 批，必须继承 8A policy contract、8B graph pointer/readiness 和 8C structured governance/fanout 语义。目标是把 closeout、rework、retry/restore、incident followup 和 BR-100 loop 相关推进判断迁移到 policy；旧 workflow_completion / auto_advance / proposer 路径只可作为 contract helper、policy input 编译器或执行壳。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 8 连续批次总约束
2. doc/refactor/planning/07-progression-policy.md 中 8A/8B/8C 实现状态
3. doc/refactor/planning/05-provider-contract.md
4. doc/refactor/planning/08-deliverable-contract.md
5. doc/refactor/planning/09-refactor-plan.md
6. doc/refactor/planning/10-refactor-acceptance-criteria.md
7. backend/app/core/workflow_completion.py
8. backend/app/core/workflow_auto_advance.py
9. backend/app/core/ceo_proposer.py
10. backend/app/core/projections.py
11. backend/tests/test_workflow_autopilot.py
12. backend/tests/test_ceo_scheduler.py 中 retry/restore/closeout 相关测试
13. backend/tests/test_ticket_graph.py 中 rework/lineage 相关测试

任务：
1. 将 closeout readiness 输入结构化：effective graph complete、open blocking incident、open approval、delivery/checker gate issue、existing closeout ticket、closeout parent ticket、final evidence legality summary；policy 不直接查 DB 或 artifact 正文。
2. 将 closeout CREATE/CLOSEOUT proposal 迁移到 policy；`workflow_completion.py` 可以保留 evidence/gate helper，但不得继续作为 controller/proposer 的业务决策入口。
3. 将 retry/restore-needed/rework 判断结构化：failed/timed-out terminal state、retry budget、failure kind、recovery action lineage、completed-ticket reuse gate、superseded/invalidated lineage、incident followup action。
4. 为 `REWORK`、`CLOSEOUT`、`INCIDENT` proposal 补稳定 reason code、idempotency key、source graph version、affected node refs、expected state transition 测试。
5. 覆盖 015 restore-needed missing ticket id 和 BR-100 loop 的 policy 回归测试；如必须等 Phase 7 replay DB 才能验证，必须在文档中明确归入 replay 验证，并提供本批结构化等价测试。
6. 将 `workflow_auto_advance.py`、CEO proposer 中可安全替换的 incident followup / closeout / restore 判断改为调用 policy 输出；不能安全替换的兼容壳必须标注 8E 收口。
7. 更新 `07-progression-policy.md`、`05-provider-contract.md`、`09-refactor-plan.md` 和 `10-refactor-acceptance-criteria.md`，写明 8D 完成项与 8E scheduler/controller 收口依赖。
8. 提交，message 建议：`refactor-policy: route closeout recovery decisions`。

禁止：
- 不让 closeout fallback 读 stale snapshot nodes 而忽略 effective graph pointer。
- 不让 `APPROVED_WITH_NOTES` 在本阶段扩大为 Phase 5 deliverable contract 放行规则；Phase 5 才处理 PRD acceptance contract。
- 不把 provider raw transcript、artifact 正文或 markdown 正文作为 rework/closeout 推进依据。
- 不通过新增并行旧判断来绕过 policy proposal。

验证：
- policy 单测覆盖 CLOSEOUT proposal metadata 与 duplicate closeout NO_ACTION。
- policy 单测覆盖 REWORK / INCIDENT / restore-needed missing ticket id / retry budget / completed-ticket reuse gate。
- policy 单测覆盖 BR-100 loop 的结构化 loop threshold 或明确 replay 验证归属。
- 相关 workflow autopilot / ceo scheduler / ticket graph 回归测试通过。
- grep 确认 closeout/rework/restore 新业务判断不再新增到 controller/proposer/scheduler。
```

---

## Round 8E：Controller / runtime / scheduler policy 收口与 Phase 4 验收

```text
你在 D:\Projects\boardroom-os 工作。本轮是 Round 8A/8B/8C/8D/8E 连续批次的第 5 批，也是 Phase 4 Progression policy engine 的集成收口。必须继承 8A–8D 的所有实现状态，不得重新设计 policy contract。目标是清理 controller/runtime/scheduler/proposer 中残余 closeout/fanout/rework 业务判断，补齐 Phase 4 验收证据，然后把下一轮入口交给 Round 9。

必读：
1. doc/refactor/planning/11-round-prompts.md 的 Round 8 连续批次总约束
2. doc/refactor/planning/07-progression-policy.md 中 8A–8D 实现状态
3. doc/refactor/planning/05-provider-contract.md
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/workflow_progression.py
7. backend/app/core/workflow_controller.py
8. backend/app/core/workflow_autopilot.py
9. backend/app/core/workflow_auto_advance.py
10. backend/app/core/ceo_proposer.py
11. backend/app/core/ceo_scheduler.py
12. backend/app/scheduler_runner.py
13. backend/app/core/projections.py
14. backend/tests/ 中 progression、graph、workflow autopilot、ceo scheduler、scheduler runner 相关测试

任务：
1. 全面 grep controller、runtime、scheduler、CEO proposer、workflow_auto_advance、projections，确认 closeout/fanout/rework/restore/meeting/architect gate 业务判断已迁移到 policy；旧路径只保留 snapshot/policy 编译、policy 调用、proposal 执行或兼容展示。
2. scheduler 不得直接做 closeout/fanout/rework 业务判断；只能调用 policy、执行 policy proposal，或在无法推进时输出显式 incident/action。
3. 补齐或收敛 8A–8D 留下的 Phase 4 测试缺口，确保 `CREATE_TICKET`、`WAIT`、`REWORK`、`CLOSEOUT`、`INCIDENT`、`NO_ACTION` 六类 action 都有 reason code / idempotency key / source graph version / affected node refs / expected state transition 测试。
4. 确认 orphan pending 不阻断 graph complete、CANCELLED/SUPERSEDED 不参与 effective edges、substring hint 不再驱动会议/架构 gate、hardcoded backlog milestone fanout 已被 policy input / graph patch 替代。
5. 对 015 stale gate、orphan pending、restore-needed missing ticket id、BR-100 loop 逐项标注：policy 回归测试证据，或明确归入 Phase 7 replay 验证的原因和结构化等价覆盖；不得遗漏。
6. 清理或隔离残余旧 helper：可删除的旧 controller/proposer 业务 helper 直接删除；确需保留的只允许作为 input compiler / execution shell / API display，并在文档中写清边界。
7. 更新 `07-progression-policy.md` 的最终实现状态和剩余 Phase 5/6/7 依赖。
8. 更新 `05-provider-contract.md`：确认 late provider event/current pointer 与 policy graph pointer 边界一致。
9. 更新 `09-refactor-plan.md` 与 `10-refactor-acceptance-criteria.md`：只有在测试/grep 证据存在时勾选 Phase 4 全部 checkbox。
10. 更新本文件当前状态：Round 8A–8E 已完成后，下一轮应从 Round 9 Deliverable contract + checker/rework 开始。
11. 提交，message 建议：`refactor-policy: close phase4 acceptance`。

禁止：
- 不用“计划后续覆盖”冒充 Phase 4 checkbox 完成；没有测试或 grep 证据就保持未勾。
- 不把 Phase 5 deliverable contract 或 Phase 6 replay/resume 的范围塞进本轮。
- 不为了让 grep 通过删除仍被测试证明需要的 API/display 字段；正确做法是把它们移出 runtime 决策路径或迁移测试断言到 policy 语义。
- 不 push，除非用户明确要求。

验证：
- `decide_next_actions(snapshot, policy)` 纯函数测试通过；相同 snapshot + policy 输出稳定 action proposals。
- `CREATE_TICKET`、`WAIT`、`REWORK`、`CLOSEOUT`、`INCIDENT`、`NO_ACTION` 六类 action 都有 reason code / idempotency key / source graph version / affected node refs / expected state transition 测试。
- orphan pending 不阻断 graph complete 测试通过。
- CANCELLED/SUPERSEDED effective edges 测试通过。
- scheduler/controller/proposer 不再直接做 closeout/fanout/rework 业务判断，只调用 policy 或输出显式 incident/action。
- grep 确认 substring hint / hardcoded milestone 不再驱动会议、架构 gate 或 backlog fanout。
- Phase 4 acceptance criteria 每个勾选项都有测试命令或 grep 证据。
```

---

## Round 9：Deliverable contract + checker/rework

```text
目标：closeout 证明 PRD acceptance 满足，而不是只证明 graph terminal，覆盖 Phase 5 全部验收项。

必读：
1. doc/refactor/planning/08-deliverable-contract.md
2. doc/refactor/planning/04-write-surface-policy.md
3. doc/refactor/planning/09-refactor-plan.md
4. doc/refactor/planning/10-refactor-acceptance-criteria.md
5. backend/app/core/workflow_completion.py
6. backend/app/core/ticket_handlers.py
7. backend/app/core/runtime.py
8. backend/app/core/output_schemas.py
9. backend/tests/ 中 deliverable、checker、rework、closeout、artifact legality 相关测试

任务：
1. 定义 `DeliverableContract`，能从 PRD acceptance criteria 编译 required capabilities、required source surfaces、required evidence 和 closeout obligations。
2. Required source surfaces 必须包含路径、capability、evidence 映射；Evidence pack 必须可映射到 acceptance criteria，且每条关键 acceptance 都能追溯到 source/test/check/git/closeout evidence。
3. checker verdict 与 deliverable contract 解耦；`APPROVED_WITH_NOTES` 不得放行 blocking contract gap。
4. rework target 必须指向能修复 blocking gap 的 upstream node，而不是默认回到 graph terminal 或 checker。
5. failed delivery report 只有在结构化 convergence policy 明确允许时才可放行；不能用 checker notes 或 graph terminal 代替 contract satisfaction。
6. closeout package 必须包含 contract version 和 final evidence table；final evidence table 必须列出 acceptance criterion、evidence ref、producer ticket、artifact kind 和 legality status。
7. superseded/placeholder/archive/unknown evidence 不得进入 final evidence set；placeholder source/evidence 不能通过 closeout。
8. 更新 deliverable contract、write-surface、refactor plan 和 acceptance criteria。
9. 提交，message 建议：`refactor-delivery: enforce deliverable contract closeout`。

验证：
- PRD acceptance -> DeliverableContract 编译单测。
- Required source surfaces path/capability/evidence 映射单测。
- Evidence pack -> acceptance criteria 映射单测，覆盖关键 acceptance 缺 evidence 的 fail-closed 场景。
- `APPROVED_WITH_NOTES` blocking gap 回归。
- failed delivery report 无结构化 convergence policy 时不得放行。
- closeout package contract version/final evidence table 测试。
- superseded/placeholder/archive/unknown evidence 被拒绝。
- 015 中 BR-040/BR-041 placeholder 不能通过。
```

---

## Round 10：Replay / resume / checkpoint

```text
目标：replay/resume 一等化，覆盖 Phase 6 的 resume/checkpoint/materialized view 验收项。

必读：
1. doc/refactor/planning/10-refactor-acceptance-criteria.md
2. doc/refactor/planning/07-progression-policy.md
3. doc/refactor/planning/08-deliverable-contract.md
4. backend/app/core/projections.py
5. backend/app/core/reducer.py
6. backend/app/scheduler_runner.py
7. backend/tests/ 中 replay、projection、scheduler resume、materialized view 相关测试

任务：
1. 定义并测试 resume from event id；恢复点必须包含 event cursor、projection version 和 replay watermark。
2. 定义并测试 resume from graph version；恢复后 effective graph pointer 与同一事件集全量 replay 一致。
3. 定义并测试 resume from ticket id；必须能定位 ticket terminal/in-flight 状态并恢复相关 runtime node view。
4. 定义并测试 resume from incident id；必须保留 incident status、recovery action lineage 和 source ticket context。
5. 建立 projection checkpoint 策略，避免每次全量 JSON replay；记录 checkpoint version、event watermark、schema version、invalidated_by 和 hash。
6. replay 后 artifact/doc/materialized view hash 必须可验证；Round 10 可以先定义 hash contract 与 checkpoint 接口，若 document materializer 留给 Round 10B，必须留下 failing/xfail 标记或明确验收依赖。
7. 证明正常路径不需要人工补写 projection/index；禁止通过手写 DB row、手工 event 注入或 projection repair 通过测试。
8. 更新 replay/resume、progression、refactor plan 和 acceptance criteria。
9. 提交，message 建议：`refactor-replay: add checkpointed resume path`。

验证：
- resume from event/version/ticket/incident 四类测试通过。
- projection checkpoint 避免每次全量 JSON replay 的性能/行为测试通过。
- checkpoint invalidation 测试覆盖 schema/version/hash 不匹配。
- replay 后 artifact hash 一致；doc/materialized view hash contract 有测试或由 Round 10B 补齐的明确验收链接。
- 测试证明不需要人工补 projection/index。
```

---

## Round 10B：Document materialization from events/process assets

```text
目标：补齐总验收中的“文档视图可从 event/process asset 重新物化”，并把它接入 replay/resume 验证。

必读：
1. doc/refactor/planning/02-target-architecture.md
2. doc/refactor/planning/08-deliverable-contract.md
3. doc/refactor/planning/10-refactor-acceptance-criteria.md
4. backend/app/core/artifact_store.py
5. backend/app/core/projections.py
6. backend/app/core/reducer.py
7. backend/tests/ 中 document/materialized view/replay 相关测试

任务：
1. 定义 event/process asset -> document view materializer 的输入、输出、hash 和版本规则，并接入 Round 10 的 checkpoint/hash contract。
2. 文档视图不得依赖手工补写文件；必须能从 event log、process asset、artifact metadata 和 artifact content 重新物化。
3. replay 后 materialized document hash 必须稳定；缺失 artifact、非法 process asset、非法 evidence lineage 必须 fail-closed 并输出诊断。
4. 将 document materialization 验证接入 replay bundle/report，报告必须列出 source event range、process asset refs、artifact refs 和 hash。
5. 更新 target architecture、deliverable contract、acceptance criteria。
6. 提交，message 建议：`refactor-replay: materialize document views from events`。

验证：
- document materializer 单测覆盖正常、缺失 artifact、非法 process asset、非法 evidence lineage。
- replay 后 document view hash 与全量重物化一致。
- 无人工文件补写即可重建 document view。
- replay bundle/report 包含 document materialization hash、source refs 和诊断。
```

---

## Round 11：015 replay 包验证

```text
目标：用 D:\Projects\boardroom-os-replay 验证新规则，覆盖 Phase 7 全部验收项。

必读：
1. doc/refactor/planning/01-current-state-audit.md
2. doc/refactor/planning/05-provider-contract.md
3. doc/refactor/planning/07-progression-policy.md
4. doc/refactor/planning/08-deliverable-contract.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. doc/tests/intergration-test-015-20260429-final.md
7. D:\Projects\boardroom-os-replay 中 015 replay DB/artifacts/日志

任务：
1. 导入 015 replay DB/artifacts，不允许人工 DB/projection/event 注入；导入步骤必须可重复、可脚本化，并记录输入路径、hash 和版本。
2. 定位并重放关键 provider failure，验证新的 failure taxonomy、raw archive、late event guard 和 retry/recovery 边界。
3. 重放 BR-032 auth contract mismatch，验证 contract gap 进入正确 incident/rework 路径。
4. 重放 BR-040/BR-041 placeholder delivery，验证 placeholder source/evidence 被 deliverable contract 阻断。
5. 重放 orphan pending 场景，验证不阻断 graph complete，且 CANCELLED/SUPERSEDED effective edges 不参与完成判断。
6. 能生成 closeout，但必须满足 deliverable contract 和 final evidence table；禁止 manual closeout recovery 绕过 contract。
7. replay audit report 必须区分 provider failure、runtime bug、product defect、contract gap 和 replay/import issue，并列出证据 refs、事件区间、checkpoint/hash。
8. 更新 current-state audit、acceptance criteria 和 refactor plan。
9. 提交，message 建议：`test-replay: validate integration 015 without manual projection repair`。

验证：
- 015 replay DB/artifacts 可无人工注入导入，重复导入结果稳定。
- 关键 provider failure 可定位并重放。
- BR-032、BR-040、BR-041 回归通过。
- orphan pending 不阻断 graph complete，CANCELLED/SUPERSEDED effective edges 不参与完成判断。
- closeout 必须经过 deliverable contract 和 final evidence table。
- 输出 replay audit report，且报告分类 provider/runtime/product/contract/replay issue。
```

---

## Round 12：后端-only live scenario clean run

```text
目标：证明新 backend runtime 可以 clean run，覆盖 Phase 8 全部验收项。此时 frontend 已删除，不再作为 live 成功条件。

必读：
1. doc/refactor/planning/09-refactor-plan.md
2. doc/refactor/planning/10-refactor-acceptance-criteria.md
3. doc/refactor/planning/05-provider-contract.md
4. doc/refactor/planning/08-deliverable-contract.md
5. backend/data/live-tests/ 或当前 live config 目录
6. backend/tests/live/ 相关 live harness

任务：
1. 设计小而完整的后端-only PRD scenario，PRD acceptance 必须能编译为 DeliverableContract。
2. 先跑 provider soak，并把 provider noise / provider bad response / timeout / schema failure 与 runtime bug 区分记录；soak 未过不得启动 clean run。
3. 再跑 live scenario，禁止人工 DB/projection/event 注入，且运行日志必须记录所有自动 recovery/incident/action。
4. 所有 source delivery 必须有非 placeholder source inventory，包含 path、artifact_ref、producer ticket、git/test evidence。
5. 所有关键 acceptance 必须有 evidence refs，并能映射到 deliverable contract 和 final evidence table。
6. final closeout package 必须合法，包含 contract version、final evidence table、source inventory summary 和 replay bundle ref。
7. 必须可从中间 checkpoint resume；resume 后 closeout/evidence/hash 与 uninterrupted run 等价。
8. 最终报告必须区分 provider noise、runtime bug、product defect、contract gap 和 operator/replay issue。
9. 产出 closeout、evidence、replay bundle，并更新 acceptance criteria、refactor plan 和测试报告。
10. 提交，message 建议：`test-live: complete backend-only autonomous runtime scenario`。

验证：
- provider soak 前置通过，报告 first-token/idle/timeout/schema/malformed 分类。
- live scenario zero manual intervention。
- 所有 source delivery 有非 placeholder source inventory。
- 所有关键 acceptance 有 evidence refs，并映射到 DeliverableContract。
- final closeout package 合法，包含 contract version、final evidence table、source inventory summary。
- replay from checkpoint pass，且 hash 与 uninterrupted run 等价。
- 最终报告区分 provider noise、runtime bug、product defect、contract gap 和 operator/replay issue。
- 工作树干净。
```

---

## Round 13：总验收收口

```text
目标：对照 `10-refactor-acceptance-criteria.md` 做最终总验收收口，只修验收缺口，不再引入新架构范围。

必读：
1. doc/refactor/planning/09-refactor-plan.md
2. doc/refactor/planning/10-refactor-acceptance-criteria.md
3. doc/refactor/planning/11-round-prompts.md
4. 最新 replay audit report
5. 最新 backend-only live scenario report

任务：
1. 逐项核对总验收和 Phase 0-8 验收，标出证据文件、测试命令、commit id、报告路径和当前状态。
2. 如有未勾项，只做最小补齐；不得扩大 scope、跳过证据或用“计划覆盖”冒充验收完成。
3. 确认无人工 DB/projection/event 注入完成 replay/resume，并列出 replay/resume 命令和输入 hash。
4. 确认无 placeholder source/evidence 能通过 deliverable closeout，并链接阻断测试和 replay/live 证据。
5. 确认 Provider streaming smoke 达到稳定性阈值，并列出同一 API 配置、success rate、first token p95、idle gap p95、failure counts。
6. 确认 Runtime kernel 不硬编码 CEO、员工、角色模板或业务 milestone；grep 结果必须覆盖 runtime、scheduler、controller、policy、ticket handlers。
7. 确认 Closeout 证明 PRD acceptance，而不是只证明 graph terminal；每个 final evidence ref 必须能追溯到 DeliverableContract acceptance。
8. 确认文档视图可从 event/process asset 重新物化，并列出 materialized view hash、source refs 和 replay report。
9. 对 Phase 0-8 每个 checkbox 只在证据存在时勾选；缺证据保持未勾并写明 blocker。
10. 更新 acceptance criteria、refactor plan 和最终 handoff。
11. 提交，message 建议：`refactor-acceptance: close autonomous runtime rebuild criteria`。

验证：
- 全部相关 provider/actor/progression/deliverable/replay/live 测试通过。
- acceptance criteria 每个勾选项都有证据链接或测试命令；无证据项不得勾选。
- final handoff 包含 commit id、报告路径、测试命令、风险和未完成项。
- 工作树干净。
```

---

## 提交通用模板

```text
<phase-id>: <一句话说明>

- 更新/实现内容
- 验证命令与结果
- 后续风险

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
