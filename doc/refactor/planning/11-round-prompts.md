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

当前分支：`refactor/autonomous-runtime-docs`。

当前重构控制面入口：

- [INDEX.md](INDEX.md)
- [00-refactor-north-star.md](00-refactor-north-star.md)
- [09-refactor-plan.md](09-refactor-plan.md)
- [10-refactor-acceptance-criteria.md](10-refactor-acceptance-criteria.md)

下一轮新会话应从 **Round 5：Directory / Artifact / Write-surface contract 实施** 开始。Round 5 只实现 Phase 1 目录、产物、write-set 和 closeout evidence 合法性 contract，不开始 provider、actor lifecycle 或 progression policy 重构。

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
```

---

## Round 7：Actor / Role lifecycle 实施

```text
目标：让派工从 role name 转向 capability。

必读：
1. doc/refactor/planning/06-actor-role-lifecycle.md
2. doc/refactor/planning/04-write-surface-policy.md
3. doc/refactor/planning/09-refactor-plan.md
4. doc/refactor/planning/10-refactor-acceptance-criteria.md
5. backend/app/core/workflow_controller.py
6. backend/app/core/projections.py
7. backend/app/core/ticket_handlers.py

任务：
1. 找到 role_profile_ref 作为执行键的路径。
2. 建立 capability mapping 的最小模型。
3. 给 excluded_employee_ids 增加作用域设计或测试。
4. no eligible actor 必须显式 incident/action。
5. 更新 actor lifecycle 和 write-surface 文档。
6. 更新 acceptance criteria。
7. 提交，message 建议：`refactor-actors: introduce capability-driven assignment`。

验证：
- 新增/更新测试覆盖 no eligible actor。
- 不再新增 role name -> write root 逻辑。
```

---

## Round 8：Progression policy engine 抽离

```text
目标：把推进规则从 controller/runtime 中抽为显式 policy。

必读：
1. doc/refactor/planning/07-progression-policy.md
2. doc/refactor/planning/09-refactor-plan.md
3. doc/refactor/planning/10-refactor-acceptance-criteria.md
4. backend/app/core/workflow_progression.py
5. backend/app/core/workflow_controller.py
6. backend/app/core/workflow_autopilot.py
7. backend/app/core/ceo_proposer.py

任务：
1. 定义 decide_next_actions(snapshot, policy)。
2. 从最小场景开始迁移 closeout/fanout/rework 判断。
3. 保留旧路径直到测试覆盖。
4. 删除 substring/hardcoded milestone 前先补测试。
5. 更新 progression policy 文档和 acceptance criteria。
6. 提交，message 建议：`refactor-policy: extract explicit progression decisions`。

验证：
- 相同 snapshot 输出稳定 action proposals。
- orphan pending 不阻断 graph complete。
```

---

## Round 9：Deliverable contract + checker/rework

```text
目标：closeout 证明 PRD 满足，而不是 graph 完成。

必读：
1. doc/refactor/planning/08-deliverable-contract.md
2. doc/refactor/planning/04-write-surface-policy.md
3. doc/refactor/planning/09-refactor-plan.md
4. doc/refactor/planning/10-refactor-acceptance-criteria.md
5. backend/app/core/workflow_completion.py
6. backend/app/core/ticket_handlers.py
7. backend/app/core/runtime.py

任务：
1. 定义 DeliverableContract 结构。
2. 加 placeholder detection。
3. 改 checker/rework target 选择。
4. closeout final refs 只允许 current final evidence。
5. 更新 deliverable contract 文档和 acceptance criteria。
6. 提交，message 建议：`refactor-delivery: enforce deliverable contract closeout`。

验证：
- 015 中 BR-040/BR-041 placeholder 不能通过。
- APPROVED_WITH_NOTES 不放行 blocker。
```

---

## Round 10：Replay / resume / checkpoint

```text
目标：replay/resume 一等化。

必读：
1. doc/refactor/planning/10-refactor-acceptance-criteria.md
2. doc/refactor/planning/07-progression-policy.md
3. backend/app/core/projections.py
4. backend/app/core/reducer.py
5. backend/app/scheduler_runner.py

任务：
1. 定义 resume from event/version/ticket/incident。
2. 建立 projection checkpoint 策略。
3. 避免每次全量 JSON replay。
4. 写 replay consistency tests。
5. 更新 refactor plan 和 acceptance criteria。
6. 提交，message 建议：`refactor-replay: add checkpointed resume path`。

验证：
- 不需要人工补 projection。
- replay 后 materialized view hash 一致。
```

---

## Round 11：015 replay 包验证

```text
目标：用 D:\Projects\boardroom-os-replay 验证新规则。

必读：
1. doc/refactor/planning/01-current-state-audit.md
2. doc/refactor/planning/08-deliverable-contract.md
3. doc/refactor/planning/10-refactor-acceptance-criteria.md
4. doc/tests/intergration-test-015-20260429-final.md

任务：
1. 导入 015 replay 包。
2. 重放关键 provider/rework/closeout 路径。
3. 验证 placeholder、orphan pending、manual closeout recovery 都被新规则处理。
4. 输出 replay audit report。
5. 更新 current-state audit、acceptance criteria 和 refactor plan。
6. 提交，message 建议：`test-replay: validate integration 015 without manual projection repair`。

验证：
- 无人工 DB/projection 注入。
- closeout 必须经过 deliverable contract。
```

---

## Round 12：后端-only live scenario clean run

```text
目标：证明新 backend runtime 可以 clean run。此时 frontend 已删除，不再作为 live 成功条件。

必读：
1. doc/refactor/planning/09-refactor-plan.md
2. doc/refactor/planning/10-refactor-acceptance-criteria.md
3. doc/refactor/planning/05-provider-contract.md
4. backend/data/live-tests/ 或当前 live config 目录

任务：
1. 设计小而完整的后端-only PRD scenario。
2. 先跑 provider soak。
3. 再跑 live scenario。
4. 禁止人工 DB/projection/event 注入。
5. 产出 closeout、evidence、replay bundle。
6. 更新 acceptance criteria、refactor plan 和测试报告。
7. 提交，message 建议：`test-live: complete backend-only autonomous runtime scenario`。

验证：
- final deliverable contract pass。
- replay from checkpoint pass。
- provider failure attribution clear。
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
