# 每轮推进提示词

## 使用方式

每次新会话或新阶段开始时，复制对应 round 的提示词。每轮默认要求：

1. 先读指定文档。
2. 只做本轮允许的改动。
3. 完成后更新相关文档和验收项。
4. 运行指定验证。
5. 单独提交。

## Round 0：分支与基线盘点

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

验收：
- 分支已创建。
- 工作树变更范围清楚。
```

## Round 1：写入 12 份规划文档

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

验收：
- 12 份文档可从 INDEX.md 导航。
- 文档明确本轮不承载的愿景。
```

## Round 2：整理文档入口

```text
目标：让 doc/README.md 成为清晰入口，并把重构规划纳入默认导航。

必读：
- doc/README.md
- doc/refactor/planning/INDEX.md
- doc/mainline-truth.md

任务：
1. 更新 doc/README.md 的默认首读和工作参考。
2. 新增 doc/refactor/README.md。
3. 明确 doc/new-architecture 是目标 canon，doc/refactor/planning 是执行控制面。
4. 检查相对链接。

禁止：
- 移动 015 报告。
- 移动 feature-spec。

验收：
- 新会话能从 doc/README.md 找到规划文档。
```

## Round 3：目录契约与写权限审计

```text
目标：把目录和写入面从文档契约映射到当前代码差距。

必读：
- doc/refactor/planning/03-directory-contract.md
- doc/refactor/planning/04-write-surface-policy.md
- backend/app/core/project_workspaces.py
- backend/app/core/runtime.py
- backend/app/core/ticket_handlers.py

任务：
1. 搜索 role_profile_ref 决定 write root 的代码。
2. 搜索 default source/test fallback。
3. 搜索 closeout final artifact refs 筛选逻辑。
4. 写出 gap list，不急于大改。
5. 补最小 contract test，如安全可行。

禁止：
- 一次性重写 runtime。

验收：
- 有明确 code gap list。
- 没有新增角色名硬编码。
```

## Round 4：Provider contract 实施

```text
目标：重建 provider 稳定性验证。

必读：
- doc/refactor/planning/05-provider-contract.md
- backend/app/core/runtime_provider_config.py
- backend/app/core/runtime.py
- backend/tests/live/run_configured.py 或相关 provider harness

任务：
1. 建立独立 provider streaming smoke。
2. 区分 timeout 类型。
3. 分类 malformed SSE、empty assistant、schema validation failure。
4. 记录 preferred/actual provider/model。
5. 不触碰 workflow progression。

验收：
- provider smoke 可不依赖 workflow 运行。
- 同 API 配置可输出稳定性报告。
```

## Round 5：Actor / Role lifecycle 实施

```text
目标：让派工从 role name 转向 capability。

必读：
- doc/refactor/planning/06-actor-role-lifecycle.md
- doc/refactor/planning/04-write-surface-policy.md
- backend/app/core/workflow_controller.py
- backend/app/core/projections.py
- backend/app/core/ticket_handlers.py

任务：
1. 找到 role_profile_ref 作为执行键的路径。
2. 建立 capability mapping 的最小模型。
3. 给 excluded_employee_ids 增加作用域设计或测试。
4. no eligible actor 必须显式 incident/action。

验收：
- 新增测试覆盖 no eligible actor。
- 不再新增 role name -> write root 逻辑。
```

## Round 6：Progression policy engine 抽离

```text
目标：把推进规则从 controller/runtime 中抽为显式 policy。

必读：
- doc/refactor/planning/07-progression-policy.md
- backend/app/core/workflow_progression.py
- backend/app/core/workflow_controller.py
- backend/app/core/workflow_autopilot.py
- backend/app/core/ceo_proposer.py

任务：
1. 定义 decide_next_actions(snapshot, policy)。
2. 从最小场景开始迁移 closeout/fanout/rework 判断。
3. 保留旧路径直到测试覆盖。
4. 删除 substring/hardcoded milestone 前先补测试。

验收：
- 相同 snapshot 输出稳定 action proposals。
- orphan pending 不阻断 graph complete。
```

## Round 7：Deliverable contract + checker/rework

```text
目标：closeout 证明 PRD 满足，而不是 graph 完成。

必读：
- doc/refactor/planning/08-deliverable-contract.md
- backend/app/core/workflow_completion.py
- backend/app/core/ticket_handlers.py
- backend/app/core/runtime.py

任务：
1. 定义 DeliverableContract 结构。
2. 加 placeholder detection。
3. 改 checker/rework target 选择。
4. closeout final refs 只允许 current final evidence。

验收：
- 015 中 BR-040/BR-041 placeholder 不能通过。
- APPROVED_WITH_NOTES 不放行 blocker。
```

## Round 8：Replay / resume / checkpoint

```text
目标：replay/resume 一等化。

必读：
- doc/refactor/planning/10-refactor-acceptance-criteria.md
- backend/app/core/projections.py
- backend/app/core/reducer.py
- backend/app/scheduler_runner.py

任务：
1. 定义 resume from event/version/ticket/incident。
2. 建立 projection checkpoint 策略。
3. 避免每次全量 JSON replay。
4. 写 replay consistency tests。

验收：
- 不需要人工补 projection。
- replay 后 materialized view hash 一致。
```

## Round 9：015 replay 包验证

```text
目标：用 D:\Projects\boardroom-os-replay 验证新规则。

必读：
- doc/refactor/planning/01-current-state-audit.md
- doc/refactor/planning/08-deliverable-contract.md
- doc/tests/intergration-test-015-20260429-final.md

任务：
1. 导入 015 replay 包。
2. 重放关键 provider/rework/closeout 路径。
3. 验证 placeholder、orphan pending、manual closeout recovery 都被新规则处理。
4. 输出 replay audit report。

验收：
- 无人工 DB/projection 注入。
- closeout 必须经过 deliverable contract。
```

## Round 10：新 live scenario clean run

```text
目标：证明新 runtime 可 clean run。

必读：
- doc/refactor/planning/09-refactor-plan.md
- doc/refactor/planning/10-refactor-acceptance-criteria.md
- backend/data/live-tests/ 或当前 live config 目录

任务：
1. 设计小而完整的新 PRD scenario。
2. 先跑 provider soak。
3. 再跑 live scenario。
4. 禁止人工 DB/projection/event 注入。
5. 产出 closeout、evidence、replay bundle。

验收：
- final deliverable contract pass。
- replay from checkpoint pass。
- provider failure attribution clear。
```

## 提交通用模板

```text
<phase-id>: <一句话说明>

- 更新/实现内容
- 验证命令与结果
- 后续风险

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
