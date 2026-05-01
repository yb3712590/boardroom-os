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

当前分支：`refactor/autonomous-runtime-docs`。

当前重构控制面入口：

- [INDEX.md](INDEX.md)
- [00-refactor-north-star.md](00-refactor-north-star.md)
- [09-refactor-plan.md](09-refactor-plan.md)
- [10-refactor-acceptance-criteria.md](10-refactor-acceptance-criteria.md)

下一轮新会话应从 **Round 6B：ProviderEvent 标准事件接口** 开始。Round 6B/6C/6D 补齐 Phase 2 剩余 provider 验收后，再进入 Round 7 Actor / Role lifecycle。

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
目标：让 runtime 执行身份从 role template 迁移到 actor/capability/assignment/lease 模型，覆盖 Phase 3 全部验收项。

必读：
1. doc/refactor/planning/06-actor-role-lifecycle.md
2. doc/refactor/planning/04-write-surface-policy.md
3. doc/refactor/planning/05-provider-contract.md
4. doc/refactor/planning/09-refactor-plan.md
5. doc/refactor/planning/10-refactor-acceptance-criteria.md
6. backend/app/core/workflow_controller.py
7. backend/app/core/projections.py
8. backend/app/core/ticket_handlers.py
9. backend/app/core/runtime_provider_config.py
10. backend/tests/ 中 actor、assignment、lease、provider selection 相关测试

任务：
1. 建立最小 Actor registry，并覆盖 enable/suspend/deactivate/replace 状态机；RoleTemplate 只能映射 capability，不能作为 runtime 执行键。
2. 将派工输入收口为 required capabilities + actor eligibility；不得新增 role name -> write root 或 role name -> execution key 分支。
3. 将 Assignment 与 Lease 分离：assignment 表示谁被选中，lease 表示当前执行窗口；二者事件、projection 和过期规则必须可独立测试。
4. 修复或证明 `excluded_employee_ids` 有作用域，不会从旧 retry/rework 污染后续无关派工。
5. no eligible actor 必须生成显式 action 或 incident，不能 silent stall。
6. provider preferred/actual provider/model 必须在 actor assignment / execution attempt / result evidence 中完整记录，并与 provider smoke 字段一致。
7. 更新 actor lifecycle、write-surface、provider contract 文档和 acceptance criteria。
8. 提交，message 建议：`refactor-actors: introduce capability-driven assignment`。

验证：
- 单测覆盖 actor enable/suspend/deactivate/replace。
- 单测覆盖 RoleTemplate 只映射 capability、不作为 runtime 执行键。
- 单测覆盖 Assignment 与 Lease 分离及 lease 过期。
- 单测覆盖 scoped `excluded_employee_ids`。
- 单测覆盖 no eligible actor 显式 incident/action。
- 单测覆盖 provider preferred/actual 记录完整。
- grep 确认没有新增 role name -> write root / execution key 判断。
```

---

## Round 8：Progression policy engine 抽离

```text
目标：把推进规则从 controller/runtime 中抽为显式 policy，覆盖 Phase 4 全部验收项。

必读：
1. doc/refactor/planning/07-progression-policy.md
2. doc/refactor/planning/09-refactor-plan.md
3. doc/refactor/planning/10-refactor-acceptance-criteria.md
4. backend/app/core/workflow_progression.py
5. backend/app/core/workflow_controller.py
6. backend/app/core/workflow_autopilot.py
7. backend/app/core/ceo_proposer.py
8. backend/app/core/projections.py
9. backend/tests/ 中 progression、graph、workflow autopilot、scheduler 相关测试

任务：
1. 定义并实现可独立测试的 `decide_next_actions(snapshot, policy)`。
2. 为 `CREATE_TICKET`、`WAIT`、`REWORK`、`CLOSEOUT`、`INCIDENT`、`NO_ACTION` 输出稳定 reason code。
3. Effective graph pointer 必须不受 orphan pending 干扰；CANCELLED/SUPERSEDED 节点不得参与 effective edges。
4. 从最小场景迁移 closeout/fanout/rework 判断，旧路径只可作为兼容入口，不能继续承载业务判断。
5. 删除 substring hint / hardcoded milestone fanout 前必须先补回归测试；会议/架构 gate 不得由字符串提示驱动。
6. 更新 progression policy、provider late-event、refactor plan 和 acceptance criteria。
7. 提交，message 建议：`refactor-policy: extract explicit progression decisions`。

验证：
- 相同 snapshot 输出稳定 action proposals。
- 每个 action kind 都有 reason code 测试。
- orphan pending 不阻断 graph complete。
- CANCELLED/SUPERSEDED effective edges 测试通过。
- grep 确认 substring hint / hardcoded milestone 不再驱动会议、架构 gate 或 backlog fanout。
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
2. Required source surfaces 必须包含路径、capability、evidence 映射；Evidence pack 必须可映射到 acceptance criteria。
3. checker verdict 与 deliverable contract 解耦；`APPROVED_WITH_NOTES` 不得放行 blocking contract gap。
4. rework target 必须指向能修复 blocking gap 的 upstream node，而不是默认回到 graph terminal 或 checker。
5. closeout package 必须包含 contract version 和 final evidence table。
6. superseded/placeholder/archive/unknown evidence 不得进入 final evidence set；placeholder source/evidence 不能通过 closeout。
7. 更新 deliverable contract、write-surface、refactor plan 和 acceptance criteria。
8. 提交，message 建议：`refactor-delivery: enforce deliverable contract closeout`。

验证：
- PRD acceptance -> DeliverableContract 编译单测。
- Required source surfaces path/capability/evidence 映射单测。
- Evidence pack -> acceptance criteria 映射单测。
- `APPROVED_WITH_NOTES` blocking gap 回归。
- closeout package contract version/final evidence table 测试。
- superseded/placeholder evidence 被拒绝。
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
1. 定义并测试 resume from event id。
2. 定义并测试 resume from graph version。
3. 定义并测试 resume from ticket id。
4. 定义并测试 resume from incident id。
5. 建立 projection checkpoint 策略，避免每次全量 JSON replay；记录 checkpoint version、event watermark 和 invalidation 规则。
6. replay 后 doc/materialized view hash 必须可验证；不允许人工补写 projection/index 作为正常路径。
7. 更新 replay/resume、progression、refactor plan 和 acceptance criteria。
8. 提交，message 建议：`refactor-replay: add checkpointed resume path`。

验证：
- resume from event/version/ticket/incident 四类测试通过。
- projection checkpoint 避免每次全量 JSON replay 的性能/行为测试通过。
- replay 后 doc/materialized view hash 一致。
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
1. 定义 event/process asset -> document view materializer 的输入、输出、hash 和版本规则。
2. 文档视图不得依赖手工补写文件；必须能从 event log、process asset 和 artifact metadata 重新物化。
3. replay 后 materialized document hash 必须稳定；缺失 artifact 或非法 process asset 必须 fail-closed 并输出诊断。
4. 将 document materialization 验证接入 replay bundle/report。
5. 更新 target architecture、deliverable contract、acceptance criteria。
6. 提交，message 建议：`refactor-replay: materialize document views from events`。

验证：
- document materializer 单测覆盖正常、缺失 artifact、非法 process asset。
- replay 后 document view hash 一致。
- 无人工文件补写即可重建 document view。
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
1. 导入 015 replay DB/artifacts，不允许人工 DB/projection/event 注入。
2. 定位并重放关键 provider failure，验证新的 failure taxonomy、raw archive、late event guard 和 retry/recovery 边界。
3. 重放 BR-032 auth contract mismatch，验证 contract gap 进入正确 incident/rework 路径。
4. 重放 BR-040/BR-041 placeholder delivery，验证 placeholder source/evidence 被 deliverable contract 阻断。
5. 重放 orphan pending 场景，验证不阻断 graph complete。
6. 能生成 closeout，但必须满足 deliverable contract，不得绕过 final evidence table。
7. 输出新的 replay audit report，并更新 current-state audit、acceptance criteria 和 refactor plan。
8. 提交，message 建议：`test-replay: validate integration 015 without manual projection repair`。

验证：
- 015 replay DB/artifacts 可导入。
- 关键 provider failure 可定位并重放。
- BR-032、BR-040、BR-041 回归通过。
- orphan pending 不阻断 graph complete。
- closeout 必须经过 deliverable contract。
- 输出 replay audit report。
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
1. 设计小而完整的后端-only PRD scenario。
2. 先跑 provider soak，并把 provider noise / provider bad response / timeout / schema failure 与 runtime bug 区分记录。
3. 再跑 live scenario，禁止人工 DB/projection/event 注入。
4. 所有 source delivery 必须有非 placeholder source inventory。
5. 所有关键 acceptance 必须有 evidence refs，并能映射到 deliverable contract。
6. final closeout package 必须合法，包含 contract version 和 final evidence table。
7. 必须可从中间 checkpoint resume。
8. 最终报告必须区分 provider noise、runtime bug、product defect。
9. 产出 closeout、evidence、replay bundle，并更新 acceptance criteria、refactor plan 和测试报告。
10. 提交，message 建议：`test-live: complete backend-only autonomous runtime scenario`。

验证：
- provider soak 前置通过。
- live scenario zero manual intervention。
- 所有 source delivery 有非 placeholder source inventory。
- 所有关键 acceptance 有 evidence refs。
- final closeout package 合法。
- replay from checkpoint pass。
- 最终报告区分 provider noise、runtime bug、product defect。
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
1. 逐项核对总验收和 Phase 0-8 验收，标出证据文件、测试命令、commit id。
2. 如有未勾项，只做最小补齐；不得扩大 scope 或跳过证据。
3. 确认无人工 DB/projection/event 注入完成 replay/resume。
4. 确认无 placeholder source/evidence 能通过 deliverable closeout。
5. 确认 Provider streaming smoke 达到稳定性阈值。
6. 确认 Runtime kernel 不硬编码 CEO、员工、角色模板或业务 milestone。
7. 确认 Closeout 证明 PRD acceptance，而不是只证明 graph terminal。
8. 确认文档视图可从 event/process asset 重新物化。
9. 更新 acceptance criteria、refactor plan 和最终 handoff。
10. 提交，message 建议：`refactor-acceptance: close autonomous runtime rebuild criteria`。

验证：
- 全部相关 provider/actor/progression/deliverable/replay/live 测试通过。
- acceptance criteria 每个勾选项都有证据链接或测试命令。
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
