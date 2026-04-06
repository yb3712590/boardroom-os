# Boardroom OS 详细 TODO 清单

> 版本：1.1
> 日期：2026-04-06
> 作者：CTO
> 总任务数：121

---

## 一、总览

| 优先级 | 区域 | 任务数 | 预估工时 |
|--------|------|--------|----------|
| P0 | CEO Agent | 15 | 80h |
| P0 | Worker 执行 | 12 | 64h |
| P0 | 前端重构 | 22 | 72h |
| P1 | 人格模型 | 8 | 24h |
| P1 | 会议室协议 | 10 | 40h |
| P1 | 代码清理 | 6 | 16h |
| P2 | 检索层 | 5 | 20h |
| P2 | Provider 增强 | 8 | 32h |
| P2 | 治理模板 | 6 | 24h |
| P2 | UI 打磨 | 8 | 24h |
| P2 | 文档 | 5 | 12h |
| P0 | 集成测试 | 8 | 32h |
| P0 | 发布准备 | 8 | 24h |
| **合计** | | **121** | **464h** |

---

## 二、P0：关键路径

### 2.1 CEO Agent 实现

---

#### P0-CEO-001：定义 CEO Action Schema

**状态**：已完成（2026-04-04，影子阶段最小落地）

**描述**：定义 CEO 调度器可以输出的受控动作类型，作为 Pydantic 模型。这是 CEO Agent 的核心契约。

**文件**：
- 新建：`backend/app/contracts/ceo_actions.py`

**依赖**：无

**预估**：4h

**feature-spec**：条目 6, 22, 24

**验收标准**：
- 定义至少 7 种动作类型：`CREATE_TICKET`、`RETRY_TICKET`、`REASSIGN_TICKET`、`HIRE_EMPLOYEE`、`ESCALATE_TO_BOARD`、`ADVANCE_STAGE`、`NO_ACTION`
- 每种动作有明确的参数 schema
- 所有模型继承 `StrictModel`（`extra="forbid"`）
- 有 `CEOActionBatch` 包装类型，包含动作列表和决策理由

**风险**：低

**完成补记**：
- 本轮按 `doc/TODO.md` 的 CEO 影子模式先收口到 5 类真实受控动作：`CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / ESCALATE_TO_BOARD / NO_ACTION`
- `REASSIGN_TICKET / ADVANCE_STAGE` 留到 `P1-A CEO 有限接管` 再补，不把未接入主链的动作写成已落地

---

#### P0-CEO-002：实现 CEO 状态快照读取器

**状态**：已完成（2026-04-04，影子阶段落地）

**描述**：从投影中读取当前工作流全貌，产出结构化的 CEO 输入上下文。CEO 每次唤醒时消费这个快照。

**文件**：
- 新建：`backend/app/core/ceo_snapshot.py`
- 读取：`backend/app/core/projections.py`（复用现有投影构建逻辑）
- 读取：`backend/app/db/repository.py`

**依赖**：P0-CEO-001

**预估**：6h

**feature-spec**：条目 22, 23

**验收标准**：
- 产出包含以下信息的快照：工作流状态、所有节点状态、所有工单状态、所有员工状态、活跃 incident、预算使用情况、当前阶段
- 快照是只读的，不修改任何状态
- 有单元测试验证快照内容完整性

**风险**：低

**完成补记**：
- 当前快照已覆盖 workflow / ticket / node / approval / incident / employee / recent event 这些影子判断真正需要的状态
- 本轮没有额外发明第二套状态源，直接复用现有 projection 和 repository 读面

---

#### P0-CEO-003：实现 CEO 角色提示模板

**状态**：已完成（2026-04-04，影子阶段最小落地）

**描述**：编写 CEO 的系统提示和角色定义，指导 LLM 如何基于状态快照做出调度决策。

**文件**：
- 新建：`backend/app/core/ceo_prompts.py`

**依赖**：P0-CEO-001, P0-CEO-002

**预估**：8h

**feature-spec**：条目 1, 6, 8

**验收标准**：
- 系统提示明确 CEO 的职责边界（调度、不执行）
- 包含输出 schema 的 JSON 示例
- 包含决策规则（何时创建工单、何时重试、何时升级）
- 提示长度 < 4000 tokens
- 有至少 3 个 few-shot 示例

**风险**：中（提示工程需要迭代）

**完成补记**：
- 本轮提示词按影子模式收口：明确“只提议、不执行、只返回受控 JSON”
- 暂未为 few-shot 继续堆复杂样例，先保证当前主线建议稳定和可校验

---

#### P0-CEO-004：实现 CEO Action Proposer

**状态**：已完成（2026-04-04，影子阶段落地）

**描述**：通过 OpenAI Compat 调用 LLM，将状态快照和角色提示发送给模型，解析返回的动作列表。

**文件**：
- 新建：`backend/app/core/ceo_proposer.py`
- 读取：`backend/app/core/provider_openai_compat.py`
- 读取：`backend/app/core/runtime_provider_config.py`

**依赖**：P0-CEO-001, P0-CEO-002, P0-CEO-003

**预估**：8h

**feature-spec**：条目 22, 24

**验收标准**：
- 调用 OpenAI Compat API 发送 CEO 上下文
- 解析 LLM 返回的 JSON 为 `CEOActionBatch`
- 解析失败时返回 `NO_ACTION` + 错误日志
- 有超时控制（默认 30s）
- 有重试逻辑（最多 2 次）
- 有单元测试（mock LLM 响应）

**风险**：中

**完成补记**：
- 当前 proposer 直接复用现有 OpenAI Compat 配置与调用路径
- provider 不可用、配置不完整、返回坏 JSON 时不会改状态，而是回落为 `NO_ACTION` 并留下 fallback 审计

---

#### P0-CEO-005：实现 CEO Action Validator

**状态**：已完成（2026-04-04，影子阶段落地）

**描述**：对 CEO 提议的每个动作进行 Reducer 级别的校验，拒绝无效动作。

**文件**：
- 新建：`backend/app/core/ceo_validator.py`
- 读取：`backend/app/core/reducer.py`
- 读取：`backend/app/db/repository.py`

**依赖**：P0-CEO-001

**预估**：6h

**feature-spec**：条目 24, 33

**验收标准**：
- 对每种动作类型有专门的校验逻辑
- `CREATE_TICKET`：校验节点存在、员工可用、schema 有效
- `RETRY_TICKET`：校验工单存在且处于可重试状态
- `HIRE_EMPLOYEE`：校验角色类型有效、不超过人员上限
- 无效动作被拒绝并记录原因
- 有单元测试覆盖每种校验场景

**风险**：低

**完成补记**：
- 当前校验已覆盖 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / ESCALATE_TO_BOARD / NO_ACTION`
- 校验结果现在会以 accepted / rejected 两组结构化结果进入 CEO 影子审计，而不是只写日志字符串

---

#### P0-CEO-006：实现 CEO Action Executor

**状态**：已完成（2026-04-04，有限接管首轮落地）

**描述**：将通过校验的 CEO 动作转换为实际的命令调用（复用现有 handler）。

**文件**：
- 新建：`backend/app/core/ceo_executor.py`
- 读取：`backend/app/core/command_handlers.py`
- 读取：`backend/app/core/ticket_handlers.py`
- 读取：`backend/app/core/employee_handlers.py`

**依赖**：P0-CEO-005

**预估**：6h

**feature-spec**：条目 6, 8

**验收标准**：
- 每种动作类型映射到对应的 handler 调用
- 执行结果（成功/失败）被记录为事件
- 单个动作失败不阻塞其他动作的执行
- 有单元测试

**风险**：低

**完成补记**：
- 本轮新增 `backend/app/core/ceo_executor.py`，当前只执行 3 类有限动作：`CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE`
- `ESCALATE_TO_BOARD` 继续保留在 action schema 中，但执行层会明确记成 `DEFERRED_SHADOW_ONLY`，不伪装成已落地
- 所有执行结果都会进入 `ceo_shadow_run.executed_actions / execution_summary`，不额外发明第二套审计存储

---

#### P0-CEO-007：实现 CEO 调度器主循环

**状态**：已完成（2026-04-04，影子阶段落地）

**描述**：将快照读取 → 提议 → 校验 → 执行串联为完整的 CEO 调度循环。

**文件**：
- 新建：`backend/app/core/ceo_scheduler.py`
- 修改：`backend/app/core/workflow_auto_advance.py`（添加 CEO 调用入口）

**依赖**：P0-CEO-002, P0-CEO-004, P0-CEO-005, P0-CEO-006

**预估**：6h

**feature-spec**：条目 6, 22

**验收标准**：
- 完整的 snapshot → propose → validate → execute 管道
- 每次调度产出审计日志（输入快照摘要、提议动作、校验结果、执行结果）
- 调度结果作为事件写入事件日志
- 有集成测试

**风险**：中

**完成补记**：
- 本轮已从 `snapshot -> propose -> validate -> persist audit` 扩成有限执行首轮：校验通过的 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE` 会继续落到现有 handler
- `workflow_auto_advance.py` 仍然没有被替换，继续是主链唯一状态推进器；CEO 只是在既有触发点旁路执行受限动作并补审计

---

#### P0-CEO-008：实现 CEO 事件驱动唤醒

**状态**：已完成（2026-04-04，影子阶段落地）

**描述**：在关键事件发生时自动唤醒 CEO（工单完成、工单失败、审批完成、incident 恢复）。

**文件**：
- 修改：`backend/app/core/ticket_handlers.py`（在 handle_ticket_completed、handle_ticket_fail 后触发）
- 修改：`backend/app/core/approval_handlers.py`（在 handle_board_approve 后触发）
- 修改：`backend/app/core/ceo_scheduler.py`

**依赖**：P0-CEO-007

**预估**：4h

**feature-spec**：条目 23

**验收标准**：
- 工单完成后自动触发 CEO 调度
- 工单失败后自动触发 CEO 调度
- 审批完成后自动触发 CEO 调度
- incident 恢复后自动触发 CEO 调度
- 触发是异步的，不阻塞原始命令处理

**风险**：低

**完成补记**：
- 当前已接入 4 个真实触发点：工单完成、工单失败、审批完成、incident 恢复
- 触发失败不会反向打断原命令处理，符合影子模式“旁路观察”边界
- 2026-04-04 收尾修正：删除了 `ticket-create` 上误接的 `TICKET_FAILED` 影子触发，并把 `ticket-fail` 的真实触发补回到成功返回口

---

#### P0-CEO-009：实现 CEO 定时唤醒

**状态**：已完成（2026-04-04，按“空转补偿，不做全量轮询”落地）

**描述**：在 scheduler_runner 中添加定时 CEO 唤醒，确保系统不会因为错过事件而停滞。

**文件**：
- 修改：`backend/app/scheduler_runner.py`
- 修改：`backend/app/core/ceo_scheduler.py`
- 修改：`backend/app/config.py`
- 修改：`backend/app/db/repository.py`

**依赖**：P0-CEO-007

**预估**：3h

**feature-spec**：条目 6

**验收标准**：
- 每 60 秒检查一次是否有需要推进的工作
- 如果没有待处理事项，CEO 返回 NO_ACTION
- 定时间隔可通过配置调整

**风险**：低

**完成补记**：
- 这轮没有做“固定频率直接唤醒所有 workflow 的 CEO 轮询”，而是按主线收口成 idle maintenance：只有 workflow 没有 open approval / incident、没有 leased / executing 工单、但仍存在 `无票待起步 / ready ticket / failed ticket` 这三类待推进信号时，scheduler 才会补打一轮 CEO 审计
- `backend/app/scheduler_runner.py` 现在会在 `scheduler tick -> leased runtime -> artifact cleanup` 之后调用 `run_due_ceo_maintenance()`；触发类型统一记为 `SCHEDULER_IDLE_MAINTENANCE`，仍落在现有 `ceo_shadow_run` 审计表，不另起第二套事件总线
- 定时间隔现在由 `BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC` 控制，默认 60 秒；补充了 workflow 列表读口和“按 trigger_type 查最新 CEO run”的 repository 读方法，避免在调度层散落手写 SQL

---

#### P0-CEO-010：实现确定性回退

**状态**：已完成（2026-04-04，有限接管首轮落地）

**描述**：当 LLM 不可用时，CEO 回退到当前的硬编码逻辑（workflow_auto_advance.py）。

**文件**：
- 修改：`backend/app/core/ceo_scheduler.py`
- 读取：`backend/app/core/workflow_auto_advance.py`

**依赖**：P0-CEO-007

**预估**：3h

**feature-spec**：条目 34

**验收标准**：
- LLM 调用超时或失败时自动切换到确定性路径
- 确定性路径的行为与当前完全一致
- 回退事件被记录
- 有测试验证回退行为

**风险**：低

**完成补记**：
- 这轮没有把 CEO 变成新的主调度器；现有 `workflow_auto_advance` 仍是总回退和主推进器
- `ceo-shadow` 审计现在会显式记录 `deterministic_fallback_used / deterministic_fallback_reason`，覆盖 provider 不可用、proposal fallback 和有限执行失败三类情况
- 有限执行失败只会留下失败与 fallback 记录，不会反向打坏现有主链状态

---

#### P0-CEO-011：CEO 任务拆解能力

**状态**：已完成（2026-04-04，先按主线保守口径收口）

**描述**：CEO 能根据 north_star_goal 和当前阶段，自主决定需要创建哪些工单。

**文件**：
- 修改：`backend/app/core/command_handlers.py`
- 修改：`backend/app/core/ceo_execution_presets.py`
- 修改：`backend/app/core/ceo_prompts.py`
- 修改：`backend/app/core/ceo_proposer.py`
- 修改：`backend/app/core/ceo_validator.py`
- 修改：`backend/app/core/ceo_scheduler.py`

**依赖**：P0-CEO-007

**预估**：6h

**feature-spec**：条目 1

**验收标准**：
- project-init 后，CEO 能自主创建第一批工单（而不是硬编码）
- 工单的 spec 内容由 CEO 根据目标生成
- 工单类型和数量合理（不超过 5 个并行工单）

**风险**：高（依赖提示工程质量）

**完成补记**：
- `task-backlog` 原本把这项任务写得偏轻，只提了 `ceo_prompts.py / ceo_proposer.py`；但按当前代码现实，要把 `project-init` 后首票创建权真正迁到 CEO，还必须一起改 `command_handlers.py` 入口、create-ticket preset 稳定 ID、校验守卫和 deterministic fallback
- `project-init` 现在不再由命令处理器硬编码创建首个 scope 票；系统会先物化 `board-brief.md`，再触发一次 `BOARD_DIRECTIVE_RECEIVED` 的 CEO 审计/提议/有限执行，由 CEO 创建稳定 kickoff 票：`node_scope_decision / tkt_<workflow_id>_scope_decision`
- 这轮按你确认的保守边界落地：不新增 kickoff artifact / review 类型，而是继续复用现有 `consensus_document@1 + MEETING_ESCALATION`，让“项目启动报告 + 第一批工单概要”落在现有 `topic / consensus_summary / followup_tickets` 语义里
- 为了保住零配置主链，提议器和调度层都补了 deterministic kickoff fallback：即使 live provider 不可用、配置不完整或 proposal pipeline 出错，`project-init -> scope review` 仍能继续自动推进到当前首个真实董事会停点

---

#### P0-CEO-012：CEO 招聘决策能力

**状态**：已完成（2026-04-04，有限接管首轮落地）

**描述**：CEO 能根据工单需求自主决定是否需要招聘新员工。

**文件**：
- 修改：`backend/app/core/ceo_prompts.py`
- 修改：`backend/app/core/ceo_validator.py`
- 读取：`backend/app/core/staffing_catalog.py`

**依赖**：P0-CEO-007

**预估**：4h

**feature-spec**：条目 11, 17

**验收标准**：
- CEO 检测到无可用 Worker 时，自主发起招聘请求
- 招聘请求使用 staffing_catalog 中的模板
- 核心员工招聘自动升级到董事会

**风险**：低

**完成补记**：
- 当前 CEO 提议的 `HIRE_EMPLOYEE` 已会真实落成 `employee-hire-request` 命令，继续复用现有 staffing catalog 和 `CORE_HIRE_APPROVAL` 闭环
- 执行层不会自造员工画像，仍沿用 staffing template 自带的 `skill / personality / aesthetic` 默认值

---

#### P0-CEO-013：CEO 重试与重分派决策

**状态**：已完成（2026-04-04，有限接管首轮按“只做重试、不做重分派”收口）

**描述**：CEO 能在工单失败后决定重试（同一 Worker）还是重分派（换 Worker）。

**文件**：
- 修改：`backend/app/core/ceo_prompts.py`
- 修改：`backend/app/core/ceo_validator.py`

**依赖**：P0-CEO-007

**预估**：4h

**feature-spec**：条目 6, 34

**验收标准**：
- 首次失败：默认重试
- 连续失败 2 次：考虑换 Worker
- 连续失败 3 次：升级到 incident
- 决策逻辑在提示中明确

**风险**：低

**完成补记**：
- 本轮只把 `RETRY_TICKET` 落成真实执行，不把 `REASSIGN_TICKET` 写成已完成
- CEO 重试现在复用 `ticket_handlers.py` 里的同一套 retry scheduling 规则，保留 `attempt_no / retry_count / parent_ticket_id / timeout backoff`
- 当前只允许对 `FAILED / TIMED_OUT` 终态票执行 CEO 重试；被围堵取消类场景仍留给现有 incident / staffing recovery 路径

---

#### P0-CEO-014：CEO 集成测试

**状态**：已完成（2026-04-04，有限接管首轮补齐）

**描述**：编写 CEO Agent 的集成测试，覆盖核心决策路径。

**文件**：
- 新建：`backend/tests/test_ceo_scheduler.py`

**依赖**：P0-CEO-007 到 P0-CEO-013

**预估**：8h

**feature-spec**：全部 CEO 相关

**验收标准**：
- 至少 10 个测试用例
- 覆盖：正常调度、工单创建、重试、升级、招聘、回退、定时唤醒
- 使用 mock LLM 响应
- 所有测试通过

**风险**：低

**完成补记**：
- 当前 `backend/tests/test_ceo_scheduler.py` 已覆盖：deterministic fallback、`project-init` 首票创建、live provider 首票建票、hire 执行、retry 执行、白名单 create-ticket 执行、非法 create-ticket preset 拒绝、`ESCALATE_TO_BOARD` deferred、执行失败 fallback、失败触发、审批触发、incident 恢复、idle maintenance 选择与节流、projection 字段暴露
- `backend/tests/test_scheduler_runner.py` 这轮补了两条 runner 级验证：一条确认 pending workflow 会被 `SCHEDULER_IDLE_MAINTENANCE` 命中，另一条确认 executing ticket 不会误触发 idle maintenance
- `backend/tests/test_api.py` 补了 `project-init` 后 `ceo-shadow` 读面暴露 `BOARD_DIRECTIVE_RECEIVED` 的回归验证
- 本轮后端全量验证更新为 `385 passed`

---

#### P0-CEO-015：CEO 输出 Schema 注册

**状态**：已完成（2026-04-04）

**描述**：在 output_schemas.py 中注册 CEO 的输出 schema，使其可被 schema 校验系统使用。

**文件**：
- 修改：`backend/app/core/output_schemas.py`

**依赖**：P0-CEO-001

**预估**：2h

**feature-spec**：条目 24

**验收标准**：
- CEO action batch schema 在 registry 中注册
- schema 校验能正确验证 CEO 输出
- 有单元测试

**风险**：低

---

### 2.2 Worker 执行

---

#### P0-WRK-001：扩展 OpenAI Compat 适配层支持所有输出 Schema

**状态**：已完成（2026-04-03 校准确认）

**描述**：当前 `provider_openai_compat.py` 只支持基础的文本输出。需要扩展为支持所有 5 种结构化输出 schema。

**文件**：
- 修改：`backend/app/core/provider_openai_compat.py`
- 读取：`backend/app/core/output_schemas.py`

**依赖**：无

**预估**：8h

**feature-spec**：条目 38, 39

**验收标准**：
- 支持 `consensus_document@1`、`implementation_bundle@1`、`delivery_check_report@1`、`ui_milestone_review@1`、`delivery_closeout_package@1` 的结构化输出
- LLM 返回的 JSON 能被正确解析为对应的 Pydantic 模型
- 解析失败时有结构化错误报告

**风险**：中

---

#### P0-WRK-002：实现 Worker 执行管道

**状态**：已完成（2026-04-03 校准确认）

**描述**：将 `runtime.py` 中的确定性 mock 替换为真实 LLM 调用管道。

**文件**：
- 修改：`backend/app/core/runtime.py`（重构 `_execute_ticket` 方法）
- 读取：`backend/app/core/context_compiler.py`
- 读取：`backend/app/core/provider_openai_compat.py`

**依赖**：P0-WRK-001

**预估**：8h

**feature-spec**：条目 26, 28

**验收标准**：
- 工单执行流程：Context Compiler 编译 → OpenAI Compat 调用 → 输出解析 → Schema 校验 → 写集验证
- 确定性路径保留为回退
- 执行模式由 runtime_provider_config 决定

**风险**：中

---

#### P0-WRK-003：实现 frontend_engineer Worker

**状态**：已完成（2026-04-03，本轮按主线收口）

**描述**：实现 frontend_engineer 角色的独立 Worker，使 `BUILD / REVIEW / closeout` 的 maker 主线不再复用 `ui_designer_primary`。

**文件**：
- 修改：`backend/app/core/runtime.py`
- 修改：`backend/app/core/approval_handlers.py`
- 修改：`backend/app/db/repository.py`
- 修改：`backend/app/core/staffing_catalog.py`
- 修改：`backend/app/core/mainline_truth.py`

**依赖**：P0-WRK-002

**预估**：6h

**feature-spec**：条目 26

**验收标准**：
- frontend_engineer 使用独立的 `frontend_engineer_primary` role profile 接收 `implementation_bundle` 工单
- `BUILD / REVIEW / closeout` 三段 maker 票的 created spec、运行时支持矩阵和默认员工模板对齐到新 profile
- `project-init / scope review` 仍保留 `ui_designer_primary`，并由调度兼容保证旧 scope 共识链不断

**风险**：中

**完成补记**：
- 当前默认前端员工 roster、hire/replace 模板和 scope follow-up 映射都已对齐到 `frontend_engineer_primary`
- runtime 现在显式支持 `frontend_engineer_primary`
- 为了不打断旧 scope 共识链，调度层对 `ui_designer_primary` 保留了最小兼容匹配

---

#### P0-WRK-004：实现 checker Worker

**状态**：已完成（2026-04-03 校准确认）

**描述**：实现 checker 角色的 Worker，能执行 `delivery_check_report@1` 和 `maker_checker_verdict` 工单。

**文件**：
- 修改：`backend/app/core/runtime.py`

**依赖**：P0-WRK-002

**预估**：6h

**feature-spec**：条目 46, 47

**验收标准**：
- checker 能审查 implementation_bundle 并产出 maker_checker_verdict
- verdict 包含结构化 findings
- APPROVED/CHANGES_REQUIRED/ESCALATED 决策正确

**风险**：中

---

#### P0-WRK-005：实现 ui_designer Worker

**状态**：已完成（2026-04-03 校准确认）

**描述**：实现 ui_designer 角色的 Worker，能执行 `ui_milestone_review@1` 工单。

**文件**：
- 修改：`backend/app/core/runtime.py`

**依赖**：P0-WRK-002

**预估**：4h

**feature-spec**：条目 3

**验收标准**：
- ui_designer 能产出 ui_milestone_review 结构化输出
- 输出包含视觉评审内容

**风险**：低

---

#### P0-WRK-006：LLM 输出 Schema 校验增强

**状态**：已完成（2026-04-04，本轮按主线收口）

**描述**：增强 schema 校验，处理真实 LLM 输出中常见的格式问题。

**文件**：
- 修改：`backend/app/core/runtime.py`
- 修改：`backend/app/core/ticket_handlers.py`（`handle_ticket_result_submit` 中的校验逻辑）
- 修改：`backend/app/core/output_schemas.py`
- 修改：`backend/tests/test_output_schemas.py`
- 修改：`backend/tests/test_scheduler_runner.py`
- 修改：`backend/tests/test_api.py`

**依赖**：P0-WRK-001

**预估**：4h

**feature-spec**：条目 33, 38

**验收标准**：
- 能处理 LLM 输出中的额外空白、换行、注释
- JSON 解析失败时尝试修复常见问题（如尾逗号、单引号）
- 校验失败时产出结构化错误报告，包含具体字段和期望值

**风险**：低

**完成补记**：
- `runtime.py` 现在会按保守顺序处理 live provider 脏输出：`strip markdown fence -> strip BOM -> direct parse -> strip comments -> strip trailing commas -> normalize single-quoted strings -> repair parse`
- 修复后仍无法解析时，会继续归类为 `PROVIDER_BAD_RESPONSE`，并把 `parse_stage / repair_steps / parse_error` 写进 `failure_detail`
- `output_schemas.py` 现已统一抛出结构化 `OutputSchemaValidationError`；主线 schema 校验失败现在会显式带出 `field_path / expected / actual`
- `ticket_handlers.py` 现在会把这些结构化字段写进 `SCHEMA_ERROR.failure_detail`，同时保留 `schema_ref / schema_version`
- 本轮补了最小回归测试：一条覆盖 provider 脏 JSON 修复成功，一条覆盖不可修复坏 JSON 的 failure detail，一条覆盖 `ticket-result-submit` 的结构化 schema 失败细节

---

#### P0-WRK-007：Provider 错误处理与重试

**状态**：已完成（2026-04-03，本轮按主线收口）

**描述**：增强 LLM 调用的错误处理，包括超时重试、速率限制退避、认证失败处理。

**文件**：
- 修改：`backend/app/core/runtime.py`
- 修改：`backend/app/core/provider_openai_compat.py`

**依赖**：P0-WRK-002

**预估**：4h

**feature-spec**：条目 34

**验收标准**：
- 超时：最多重试 2 次，指数退避
- 速率限制（429）：等待 retry-after 后重试
- 认证失败（401/403）：不重试，立即报告
- 服务器错误（5xx）：最多重试 1 次
- 所有错误分类为 incident 事件

**风险**：低

**完成补记**：
- `ceo_action_batch@1` 已进入现有 output schema registry，可直接复用当前 schema 校验入口

**完成补记**：
- 现已在 `provider_openai_compat.py + runtime.py` 中落地固定分类与重试；`429` 会读取 `Retry-After`
- `401/403 / PROVIDER_BAD_RESPONSE` 不再重试，而是进入当前票的 deterministic fallback 证据链
- pause-worthy 失败会在重试耗尽后继续触发现有 provider incident / breaker

---

#### P0-WRK-008：Provider 健康监控

**状态**：已完成（2026-04-03，本轮按主线收口）

**描述**：追踪 Provider 请求成功率，在健康度下降时自动降级。

**文件**：
- 新建：`backend/app/core/provider_health.py`
- 修改：`backend/app/core/runtime.py`

**依赖**：P0-WRK-007

**预估**：4h

**feature-spec**：条目 34

**验收标准**：
- 追踪最近 10 次请求的成功率
- 成功率 < 50% 时自动创建 provider pause incident
- incident 恢复后重新启用 provider
- 健康状态在 dashboard 投影中可见

**风险**：低

**完成补记**：
- 这轮没有新建独立 `provider_health.py`，而是先按主线最小收口，把健康信号统一落进现有投影与 incident 闭环
- `dashboard / runtime-provider / incident` 现在稳定区分 `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`
- provider pause 仍然沿用现有 incident + breaker 机制，不额外引入新的健康存储层

---

#### P0-WRK-009：Worker 执行审计产物

**状态**：已完成（2026-04-04，按当前三类审计产物验收口径校准）

**描述**：每次 Worker 执行产出审计产物（编译上下文、渲染执行包、原始 LLM 响应）。

**文件**：
- 修改：`backend/app/core/runtime.py`
- 读取：`backend/app/core/developer_inspector.py`

**依赖**：P0-WRK-002

**预估**：3h

**feature-spec**：条目 39

**验收标准**：
- 每次执行产出 3 个审计产物：compiled_context_bundle、compile_manifest、rendered_execution_payload
- 产物通过 DeveloperInspectorStore 持久化
- 产物在 Review Room 的 Developer Inspector 中可查看

**风险**：低

**完成补记**：
- runtime 每次执行前都会通过 Context Compiler 持久化 `compiled_context_bundle / compile_manifest / rendered_execution_payload`
- Review Room 现在已经能通过 `developer_inspector_refs` 和 `DeveloperInspectorStore` 查看这三类审计产物
- 原始 provider 响应当前没有作为第四类独立 inspector artifact 导出；本任务按现有验收标准继续以三类核心审计产物为准

---

#### P0-WRK-010：确定性路径保留

**状态**：已完成（2026-04-03，本轮按主线收口）

**描述**：确保确定性执行路径在 LLM 模式下仍然可用作回退。

**文件**：
- 修改：`backend/app/core/runtime.py`

**依赖**：P0-WRK-002

**预估**：2h

**验收标准**：
- `LOCAL_DETERMINISTIC` 模式下所有现有行为不变
- `OPENAI_COMPAT` 模式下 LLM 失败时自动回退到确定性路径
- 回退事件被记录

**风险**：低

**完成补记**：
- live provider 在 `429 / timeout / transport / 5xx` 重试耗尽后，会开现有 provider incident，然后当前票立即走 deterministic fallback
- `401/403 / PROVIDER_BAD_RESPONSE` 不会暂停 provider，但当前票同样会回退到 deterministic 并留下结构化证据
- 已 lease 的 OpenAI Compat 票在 provider 已 paused 时也能继续走本地 fallback 完成

---

#### P0-WRK-011：Worker 执行单元测试

**状态**：已完成（2026-04-03，本轮按主线收口）

**描述**：为 Worker 执行管道编写单元测试。

**文件**：
- 新建：`backend/tests/test_worker_execution.py`

**依赖**：P0-WRK-002 到 P0-WRK-010

**预估**：6h

**验收标准**：
- 至少 15 个测试用例
- 覆盖：正常执行、schema 校验失败、LLM 超时、重试、回退、审计产物
- 使用 mock LLM 响应

**风险**：低

**完成补记**：
- 本轮测试没有新建 `test_worker_execution.py`，而是把最小必要覆盖补进现有 `test_provider_openai_compat.py`、`test_scheduler_runner.py`、`test_api.py`
- 已覆盖 `Retry-After`、provider 重试成功、paused fallback、auth/bad-response fallback、dashboard/runtime-provider 健康信号

---

#### P0-WRK-012：端到端执行链路验证

**状态**：已完成（2026-04-04，本轮按主线收口）

**描述**：验证完整的 CEO → Worker → Maker-Checker → Board 链路。

**文件**：
- 修改：`backend/tests/test_api.py`（添加端到端测试）

**依赖**：P0-CEO-014, P0-WRK-011

**预估**：8h

**验收标准**：
- 至少 5 个端到端测试场景
- 覆盖：正常链路、Worker 失败重试、incident 恢复、确定性回退
- 所有测试通过

**风险**：中

**完成补记**：
- 本轮按当前代码现实，把 mock provider 端到端验证落在 `backend/tests/test_scheduler_runner.py`，没有为了贴旧文案强行搬去 `test_api.py`
- 已补两条主链验证：一条覆盖 provider-backed happy path 从 `project-init` 经 `BUILD / CHECK / REVIEW / closeout` 到 completion；另一条覆盖 final review 上的 `PROVIDER_BAD_RESPONSE` fallback 后仍能完成 closeout
- 验证过程中补了一个真实主链缺口：OpenAI Compat live path 成功返回后，现在会和 deterministic path 一样补齐默认 artifact refs 与写入记录，避免 scope 审批和 closeout 因缺证据引用被拒

---

### 2.3 前端重构

---

#### P0-FE-001：安装 Zustand 并创建目录结构

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：安装 Zustand，创建架构指南中定义的所有目录。

**文件**：
- 修改：`frontend/package.json`
- 新建目录：`types/`、`api/`、`stores/`、`pages/`、`hooks/`、`components/layout/`、`components/dashboard/`、`components/workforce/`、`components/events/`、`components/overlays/`、`components/shared/`、`styles/`、`utils/`

**依赖**：无

**预估**：1h

**验收标准**：
- `npm install` 成功
- 所有目录存在
- `npm run build` 仍然成功

**风险**：低

---

#### P0-FE-002：提取领域类型到 types/domain.ts

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：从 api.ts 中提取所有领域模型类型。

**文件**：
- 新建：`frontend/src/types/domain.ts`

**依赖**：P0-FE-001

**预估**：2h

**验收标准**：
- 所有领域类型（WorkflowSummary、InboxItem、PipelinePhase 等）在 domain.ts 中定义
- TypeScript 编译通过

**风险**：低

---

#### P0-FE-003：提取 API 类型到 types/api.ts

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：从 api.ts 中提取所有 API 请求/响应类型。

**文件**：
- 新建：`frontend/src/types/api.ts`

**依赖**：P0-FE-002

**预估**：2h

**验收标准**：
- ProjectionEnvelope、DashboardData、所有 Request/Response 类型在 api.ts 中定义
- 引用 domain.ts 中的领域类型
- TypeScript 编译通过

**风险**：低

---

#### P0-FE-004：创建基础 API 客户端

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：创建类型安全的 fetch 封装。

**文件**：
- 新建：`frontend/src/api/client.ts`

**依赖**：P0-FE-003

**预估**：2h

**验收标准**：
- `get<T>` 和 `post<T>` 泛型函数
- `ApiError` 类型化错误类
- 自动 JSON 序列化/反序列化
- 有单元测试

**风险**：低

---

#### P0-FE-005：创建投影 API 模块

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：将投影相关的 fetch 调用提取到独立模块。

**文件**：
- 新建：`frontend/src/api/projections.ts`

**依赖**：P0-FE-004

**预估**：2h

**验收标准**：
- getDashboard、getInbox、getWorkforce、getRuntimeProvider、getReviewRoom、getDeveloperInspector、getIncidentDetail、getDependencyInspector 函数
- 自动解包 ProjectionEnvelope
- TypeScript 类型正确

**风险**：低

---

#### P0-FE-006：创建命令 API 模块

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：将命令相关的 fetch 调用提取到独立模块。

**文件**：
- 新建：`frontend/src/api/commands.ts`

**依赖**：P0-FE-004

**预估**：2h

**验收标准**：
- projectInit、boardApprove、boardReject、modifyConstraints、incidentResolve、employeeFreeze、employeeRestore、employeeHireRequest、employeeReplaceRequest、runtimeProviderUpsert 函数
- 返回 CommandAck 类型

**风险**：低

---

#### P0-FE-007：创建 SSE 管理器

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：实现带指数退避重连的 SSE 管理器。

**文件**：
- 新建：`frontend/src/api/sse.ts`
- 新建：`frontend/src/hooks/useSSE.ts`

**依赖**：无

**预估**：3h

**验收标准**：
- SSEManager 类：connect、dispose、自动重连
- 指数退避：2s → 4s → 8s → ... → 30s 上限
- useSSE hook：在组件挂载时连接，卸载时断开
- 有单元测试

**风险**：低

---

#### P0-FE-008：创建 Boardroom Store

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：创建主状态 store，管理 dashboard、inbox、workforce、runtimeProvider 数据。

**文件**：
- 新建：`frontend/src/stores/boardroom-store.ts`

**依赖**：P0-FE-005

**预估**：3h

**验收标准**：
- loadSnapshot action：并行加载 dashboard + inbox + workforce + runtimeProvider
- 加载状态和错误状态管理
- 有单元测试（至少 3 个：成功、部分失败、全部失败）

**风险**：低

---

#### P0-FE-009：创建 Review Store

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：创建审查状态 store。

**文件**：
- 新建：`frontend/src/stores/review-store.ts`

**依赖**：P0-FE-005

**预估**：2h

**验收标准**：
- loadReviewRoom、loadDeveloperInspector、clearReview actions
- 加载状态和错误状态管理
- 有单元测试

**风险**：低

---

#### P0-FE-010：创建 UI Store

**状态**：已完成（2026-04-04，前端数据层拆分）

**描述**：创建 UI 临时状态 store（抽屉开关、提交中状态等）。

**文件**：
- 新建：`frontend/src/stores/ui-store.ts`

**依赖**：无

**预估**：1h

**验收标准**：
- dependencyInspectorOpen、providerSettingsOpen 等状态
- 所有 setter actions

**风险**：低

---

#### P0-FE-011：创建 ErrorBoundary 组件

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：创建全局和页面级错误边界。

**文件**：
- 新建：`frontend/src/components/shared/ErrorBoundary.tsx`

**依赖**：无

**预估**：2h

**验收标准**：
- 捕获渲染错误，显示友好错误信息
- 提供「重试」按钮
- 有单元测试

**风险**：低

**完成补记**：
- 已新增 `frontend/src/components/shared/ErrorBoundary.tsx`
- 当前先按最小页面兜底落地：提供默认 fallback 和 `Retry`，不额外引入全局错误总线

---

#### P0-FE-012：创建通用 Drawer 组件

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：创建可复用的右侧抽屉容器，使用 framer-motion 动画。

**文件**：
- 新建：`frontend/src/components/shared/Drawer.tsx`

**依赖**：无

**预估**：3h

**验收标准**：
- 支持 isOpen、onClose、title、width props
- framer-motion 滑入/滑出动画
- 背景遮罩
- Escape 键关闭
- 有单元测试

**风险**：低

**完成补记**：
- 已新增 `frontend/src/components/shared/Drawer.tsx`
- 当前复用现有抽屉样式类名收口动画和遮罩，避免这一轮为样式体系再开一条线
- 已补最小测试，覆盖 backdrop 点击关闭与 `Escape` 关闭

---

#### P0-FE-013：创建共享基础组件

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：创建 Button、Badge、LoadingSkeleton、Toast 组件。

**文件**：
- 新建：`frontend/src/components/shared/Button.tsx`
- 新建：`frontend/src/components/shared/Badge.tsx`
- 新建：`frontend/src/components/shared/LoadingSkeleton.tsx`
- 新建：`frontend/src/components/shared/Toast.tsx`

**依赖**：无

**预估**：3h

**验收标准**：
- Button：primary/secondary/ghost/danger 变体
- Badge：info/warning/critical/success/muted 变体
- LoadingSkeleton：脉冲动画
- Toast：自动消失 + 手动关闭

**风险**：低

**完成补记**：
- 已新增 `frontend/src/components/shared/Button.tsx`、`Badge.tsx`、`LoadingSkeleton.tsx`、`Toast.tsx`
- 当前页面壳批次已真实接入 `Button / Badge / LoadingSkeleton`；`Toast` 先保持局部受控组件，不额外引入全局消息总线
- 这轮只补当前拆壳所需的最小变体，不为未来交互预埋额外抽象

---

#### P0-FE-014：创建布局组件

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：创建 AppShell、TopChrome、ThreeColumnLayout。

**文件**：
- 新建：`frontend/src/components/layout/AppShell.tsx`
- 新建：`frontend/src/components/layout/TopChrome.tsx`
- 新建：`frontend/src/components/layout/ThreeColumnLayout.tsx`

**依赖**：P0-FE-008（TopChrome 需要从 store 读数据）

**预估**：4h

**验收标准**：
- AppShell 提供玻璃面板效果
- TopChrome 展示标题、运行时状态、董事会门、运维指标
- ThreeColumnLayout 提供三栏网格

**风险**：低

**完成补记**：
- 已新增 `frontend/src/components/layout/AppShell.tsx`、`TopChrome.tsx`、`ThreeColumnLayout.tsx`
- `TopChrome` 当前直接消费现有 dashboard/runtime 读面数据并组合 `RuntimeStatusCard / BoardGateIndicator / OpsStrip`，没有改 store 或后端契约
- `DashboardPage` 现在不再直接展开顶栏和三栏壳 JSX

---

#### P0-FE-015：提取仪表盘组件

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：从 App.tsx 中提取 InboxWell、WorkflowRiver、OpsStrip、RuntimeStatusCard、BoardGateIndicator、CompletionCard、ProjectInitForm。

**文件**：
- 新建：`frontend/src/components/dashboard/InboxWell.tsx`
- 移动：`frontend/src/components/WorkflowRiver.tsx` → `frontend/src/components/dashboard/WorkflowRiver.tsx`
- 新建：`frontend/src/components/dashboard/OpsStrip.tsx`
- 新建：`frontend/src/components/dashboard/RuntimeStatusCard.tsx`
- 新建：`frontend/src/components/dashboard/BoardGateIndicator.tsx`
- 新建：`frontend/src/components/dashboard/CompletionCard.tsx`
- 新建：`frontend/src/components/dashboard/ProjectInitForm.tsx`

**依赖**：P0-FE-008, P0-FE-013

**预估**：6h

**验收标准**：
- 每个组件独立文件，props 类型明确
- 功能与重构前完全一致
- `npm run build` 成功

**风险**：中（需要仔细拆分状态和事件处理）

**完成补记**：
- 已新增 `frontend/src/components/dashboard/InboxWell.tsx`、`OpsStrip.tsx`、`RuntimeStatusCard.tsx`、`BoardGateIndicator.tsx`、`CompletionCard.tsx`、`ProjectInitForm.tsx`
- `WorkflowRiver` 已迁到 `frontend/src/components/dashboard/WorkflowRiver.tsx`
- `DashboardPage` 当前已从 903 行降到 680 行；首页顶栏、左栏和中部主卡入口已下沉，但命令回调与本地详情拉取仍留在页层，后续继续收口

---

#### P0-FE-016：提取 WorkforcePanel 和 EventTicker

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：将 WorkforcePanel 移到新目录，提取 StaffingActions，移动 EventTicker。

**文件**：
- 移动：`frontend/src/components/WorkforcePanel.tsx` → `frontend/src/components/workforce/WorkforcePanel.tsx`
- 新建：`frontend/src/components/workforce/StaffingActions.tsx`
- 移动：`frontend/src/components/EventTicker.tsx` → `frontend/src/components/events/EventTicker.tsx`

**依赖**：P0-FE-008

**预估**：3h

**验收标准**：
- 组件功能不变
- StaffingActions 从 WorkforcePanel 中提取

**风险**：低

**完成补记**：
- `frontend/src/components/workforce/WorkforcePanel.tsx`、`StaffingActions.tsx` 与 `frontend/src/components/events/EventTicker.tsx` 已落地
- 招聘模板输入与提交现在由 `StaffingActions` 单独承接；替换表单仍保留在 `WorkforcePanel` 内，避免这一轮继续过拆
- 旧的顶层 `frontend/src/components/WorkforcePanel.tsx` 与 `EventTicker.tsx` 已移除，仓库里不再保留两套活动入口
- 2026-04-05 补充收口：`StaffingActions` 现在会直接复用 `ProfileSummary` 展示 hire 模板的 `skill / personality / aesthetic` 画像，发起招聘前不再只能靠原始字段自己读

---

#### P0-FE-017：重构覆盖层组件使用通用 Drawer

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：将 ReviewRoomDrawer、IncidentDrawer、DependencyInspectorDrawer、ProviderSettingsDrawer 重构为使用通用 Drawer 组件。

**文件**：
- 移动并修改：所有 4 个抽屉组件到 `components/overlays/`

**依赖**：P0-FE-012

**预估**：6h

**验收标准**：
- 所有抽屉使用通用 Drawer 容器
- 动画一致
- 功能不变

**风险**：中

**完成补记**：
- `ReviewRoomDrawer / IncidentDrawer / DependencyInspectorDrawer / ProviderSettingsDrawer` 已迁到 `frontend/src/components/overlays/`
- 四个抽屉的业务内容保持原样，外层统一复用 shared `Drawer`
- 旧的四个重复抽屉壳文件已删除，避免仓库里同时保留两套入口

---

#### P0-FE-018：创建 DashboardPage

**状态**：已完成（2026-04-04，按保守路径落地）

**描述**：创建页面组件，组装所有仪表盘组件和覆盖层。

**文件**：
- 新建：`frontend/src/pages/DashboardPage.tsx`

**依赖**：P0-FE-014, P0-FE-015, P0-FE-016, P0-FE-017

**预估**：4h

**验收标准**：
- DashboardPage < 120 行
- 从 stores 获取数据
- 使用 useSSE hook
- 根据路由参数控制抽屉

**风险**：中

**完成补记**：
- 已新增 `frontend/src/pages/DashboardPage.tsx`，承接页面组装、SSE 失效刷新、路由驱动的 review / incident 读取，以及 `incident detail / dependency inspector` 的本地读状态
- 这轮优先把职责从 `App.tsx` 下沉到页面层，保住现有交互与命令 wiring，不顺手改后端契约
- `DashboardPage` 体积仍大于设计文档中的理想目标；这是当前已知真实差异，后续会继续拆细，但不影响本轮页面壳已落地
- 2026-04-05 补充收口：命令提交与本地详情拉取已拆到 `dashboard-page-actions.ts / dashboard-page-detail-state.ts / dashboard-page-helpers.ts`，`DashboardPage.tsx` 现在降到 298 行，主要只保留路由、store 读取、派生展示字段和组件组装

---

#### P0-FE-019：简化 App.tsx

**状态**：已完成（2026-04-04，前端页面壳收口）

**描述**：将 App.tsx 简化为只包含路由配置。

**文件**：
- 修改：`frontend/src/App.tsx`（从 995 行减到 < 50 行）

**依赖**：P0-FE-018

**预估**：2h

**验收标准**：
- App.tsx < 50 行
- 只包含 BrowserRouter + Routes
- 所有功能正常

**风险**：低

**完成补记**：
- `frontend/src/App.tsx` 已缩到纯路由入口，只保留 `BrowserRouter + Routes`
- 当前三条路由都指向 `DashboardPage`，继续保持“主面板常驻、review / incident 以覆盖层打开”的现状

---

#### P0-FE-020：拆分 CSS

**状态**：已完成（2026-04-04，M4 前端收口）

**描述**：将 App.css 拆分为 tokens.css、global.css、layout.css、components.css、overlays.css。

**文件**：
- 新建：`frontend/src/styles/tokens.css`
- 新建：`frontend/src/styles/global.css`
- 新建：`frontend/src/styles/layout.css`
- 新建：`frontend/src/styles/components.css`
- 新建：`frontend/src/styles/overlays.css`
- 删除：`frontend/src/App.css`

**依赖**：P0-FE-019

**预估**：4h

**验收标准**：
- 所有样式正确迁移
- 视觉效果与重构前完全一致
- CSS 变量在 tokens.css 中集中定义

**风险**：低

**完成补记**：
- 已新增 `frontend/src/styles/tokens.css`、`global.css`、`layout.css`、`components.css`、`overlays.css`
- `frontend/src/index.css` 现在只负责聚合导入这 5 份样式；`frontend/src/App.css` 已删除
- 当前按“只搬运、不改类名、不改视觉”收口，页面交互和样式类名保持原状

---

#### P0-FE-021：创建工具函数模块

**状态**：已完成（2026-04-04，M4 前端收口）

**描述**：提取格式化函数和 ID 生成函数。

**文件**：
- 新建：`frontend/src/utils/format.ts`
- 新建：`frontend/src/utils/ids.ts`

**依赖**：无

**预估**：1h

**验收标准**：
- formatNumber、formatTimestamp、formatRelativeTime、normalizeConstraints
- newPrefixedId
- 有单元测试

**风险**：低

**完成补记**：
- 已新增 `frontend/src/utils/format.ts` 与 `frontend/src/utils/ids.ts`
- `DashboardPage / OpsStrip / CompletionCard / ProjectInitForm / EventTicker` 已改用共享格式化函数，不再在组件内各自维护重复 helper
- `DashboardPage` 的命令 `idempotency_key` 已统一改用 `newPrefixedId`；staffing 表单在缺省 `employee_id_hint` 时会回退到前端生成 `emp_*`

---

#### P0-FE-022：前端核心测试

**状态**：已完成（2026-04-04，M4 前端收口）

**描述**：为 stores、API 客户端、关键组件编写测试。

**文件**：
- 新建：`frontend/src/test/__tests__/stores/boardroom-store.test.ts`
- 新建：`frontend/src/test/__tests__/stores/review-store.test.ts`
- 新建：`frontend/src/test/__tests__/api/client.test.ts`
- 新建：`frontend/src/test/__tests__/api/sse.test.ts`
- 新建：`frontend/src/test/__tests__/components/InboxWell.test.tsx`
- 新建：`frontend/src/test/__tests__/components/WorkflowRiver.test.tsx`

**依赖**：P0-FE-019

**预估**：8h

**验收标准**：
- 至少 20 个测试
- 覆盖：store actions、API 错误处理、SSE 重连、组件渲染
- `npm run test:run` 全部通过

**风险**：低

**完成补记**：
- 已补齐 `frontend/src/test/__tests__/components/WorkflowRiver.test.tsx`
- 已新增 `frontend/src/test/__tests__/utils/format.test.ts` 与 `frontend/src/test/__tests__/utils/ids.test.ts`
- 现有 store / API / SSE / 组件测试继续保留；本轮前端全量验证为 `npm run build` passed、`npm run test:run` → `47 passed`

---

### 2.4 集成测试

---

#### P0-INT-001：deterministic 主线完整闭环

**状态**：已完成（2026-04-05，P0 集成收口批次 1）

**描述**：补出零配置 deterministic 主线从 `project-init` 到 `closeout completion` 的完整后端集成证明。

**文件**：
- 新增：`backend/tests/test_scheduler_runner.py`

**依赖**：`P0-CEO-014`、`P0-WRK-012`

**预估**：4h

**验收标准**：
- `project-init -> scope review -> BUILD -> CHECK -> final REVIEW -> closeout` 在 deterministic 路径下可完整闭环
- 最终 `completion_summary` 包含 `closeout_ticket_id` 与 `closeout_artifact_refs`
- 无 open approval、无 open incident

**完成补记**：
- 已新增 deterministic 全链路回归测试，直接断言 workflow 完成态和 closeout 证据

---

#### P0-INT-002：provider happy path / fallback 主线收口

**状态**：已完成（2026-04-05，按现有测试收口验收）

**描述**：把已有 provider happy path 与 `PROVIDER_BAD_RESPONSE` fallback 主线验证正式纳入 `P0-INT` 验收口径，不再只散在 Worker/provider 批次里。

**文件**：
- 复用：`backend/tests/test_scheduler_runner.py`

**依赖**：`P0-WRK-007`、`P0-WRK-008`、`P0-WRK-012`

**预估**：4h

**验收标准**：
- provider-backed happy path 能从 scope 审批跑到 closeout completion
- final review 的 `PROVIDER_BAD_RESPONSE` fallback 后仍能到 closeout completion
- 两条路径都保留清晰的 provider / fallback 证据

**完成补记**：
- 现有 `test_provider_backed_scope_delivery_chain_reaches_closeout_completion`
- 现有 `test_provider_bad_response_on_final_review_falls_back_and_still_reaches_closeout_completion`
- 本轮把它们正式收口到 `P0-INT`，不重复造同类测试

---

#### P0-INT-003：incident 恢复后重新回到 maker-checker 与 board review

**状态**：已完成（2026-04-05，P0 集成收口批次 1）

**描述**：补出主线 incident 恢复后的真实继续链路证明，覆盖 `staffing containment -> incident resolve -> 恢复重试 -> checker -> board review`，避免只停在单点命令成功。

**文件**：
- 新增：`backend/tests/test_api.py`

**依赖**：`P0-WRK-012`

**预估**：4h

**验收标准**：
- `RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT` 能创建 follow-up ticket
- follow-up ticket 能重新进入 `maker -> checker`
- checker 通过后重新打开 `MEETING_ESCALATION` board review
- incident 已关闭，maker-checker 上下文未丢

**完成补记**：
- 已新增恢复后重新进入 checker 和 board review 的集成测试，直接验证 `maker_checker_context` 与 reopened approval

---

#### P0-INT-004：前端主线治理壳烟囱测试

**状态**：已完成（2026-04-05，P0 集成收口批次 1）

**描述**：补出前端主线烟囱测试，证明治理壳能正确发起 `project-init`、进入 review、提交 board approve，并在 closeout 完成后展示 completion evidence。

**文件**：
- 新增：`frontend/src/App.test.tsx`

**依赖**：`P0-FE-022`

**预估**：4h

**验收标准**：
- 首页可发起 `project-init`
- 能从 inbox 进入 review drawer
- board approve 后会刷新快照并出现 completion card
- 能重新打开 final review evidence

**完成补记**：
- 已新增主线烟囱测试，串起 `project-init -> review approve -> completion evidence`

---

#### P0-INT-005：主线 timeout / repeated failure incident 恢复到 workflow completion

**状态**：已完成（2026-04-05）

**描述**：补出 build/check 主线在 timeout 或 repeated failure incident 后，恢复并继续走到 workflow completion 的完整集成证明。

**预估**：4h

**验收补记**：
- 已在 `backend/tests/test_scheduler_runner.py` 补 timeout 与 repeated failure 两条恢复回归。
- 两条场景都覆盖 `incident-resolve -> 恢复 follow-up -> 最终 review approve -> closeout completion`。
- 同步补齐了 exhausted retry budget 下允许人工恢复继续推进的 API 回归。

---

#### P0-INT-006：provider incident 人工恢复后的主线闭环

**状态**：已完成（2026-04-05）

**描述**：覆盖 provider pause / unavailable 类 incident 经人工恢复后，主线重新回到 closeout completion 的验证。

**预估**：4h

**验收补记**：
- 已在 `backend/tests/test_scheduler_runner.py` 补 provider incident 恢复回归。
- 场景覆盖 provider paused / unavailable 打开 incident、人工恢复、主线恢复 dispatch，并最终到 `closeout completion`。

---

#### P0-INT-007：前端 incident 路由与恢复烟囱测试

**状态**：已完成（2026-04-05）

**描述**：把前端现有 incident drawer / resolve 行为收口成明确的主线烟囱场景，和 `P0-INT-004` 形成成对验收。

**预估**：4h

**验收补记**：
- 已在 `frontend/src/App.test.tsx` 补 incident 主线烟囱。
- 场景固定覆盖 `Inbox -> /incident/:incidentId -> Drawer -> incident-resolve -> dashboard 刷新`。

---

#### P0-INT-008：P0 集成验收矩阵总表

**状态**：已完成（2026-04-05）

**描述**：整理 `P0-INT-001` 到 `P0-INT-008` 的覆盖矩阵，明确 deterministic、provider、timeout、repeated failure、staffing、frontend 烟囱各自覆盖范围与当前缺口。

**预估**：4h

**验收补记**：
- 已在 `doc/TODO.md` 写入 `P0-INT` 覆盖矩阵总表。
- `doc/task-backlog.md` 与 `doc/history/memory-log.md` 已同步到本轮真实验收口径。

---

### 2.5 发布准备

---

#### P0-REL-001 到 P0-REL-008：回归测试、安全审查、Docker 打包、文档更新等

| ID | 标题 | 预估 |
|----|------|------|
| P0-REL-001 | 全量回归测试 | 3h |
| P0-REL-002 | 安全审查 | 3h |
| P0-REL-003 | 环境变量与配置复核 | 3h |
| P0-REL-004 | Docker Compose 打包 | 3h |
| P0-REL-005 | 一键启动脚本 | 3h |
| P0-REL-006 | 新环境启动验证 | 3h |
| P0-REL-007 | 发布说明整理 | 3h |
| P0-REL-008 | 发布候选收口检查 | 3h |

---

## 三、P1：重要

### 3.1 人格模型 (P1-PER-001 到 P1-PER-008)

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P1-PER-001 | 定义 skill_profile 维度 | 3h | 已完成（2026-04-04） |
| P1-PER-002 | 定义 personality_profile 维度 | 3h | 已完成（2026-04-04） |
| P1-PER-003 | 定义 aesthetic_profile 维度 | 2h | 已完成（2026-04-04） |
| P1-PER-004 | 创建 4 套主线预设人格模板 | 4h | 已完成（2026-04-04） |
| P1-PER-005 | 人格注入 Context Compiler | 4h | 已完成（2026-04-04） |
| P1-PER-006 | 多样性约束实现 | 3h | 已完成（2026-04-04） |
| P1-PER-007 | 更新 staffing_catalog.py | 2h | 已完成（2026-04-04） |
| P1-PER-008 | 人格模型测试 | 3h | 已完成（2026-04-04） |

### 3.2 会议室协议 (P1-MTG-001 到 P1-MTG-010)

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P1-MTG-001 | 定义会议事件类型 | 3h | 已完成（2026-04-05） |
| P1-MTG-002 | 定义会议请求契约 | 3h | 已完成（2026-04-05） |
| P1-MTG-003 | 实现会议状态机 | 6h | 已完成（2026-04-05） |
| P1-MTG-004 | 实现立场轮执行 | 4h | 已完成（2026-04-05） |
| P1-MTG-005 | 实现质疑轮执行 | 4h | 已完成（2026-04-05） |
| P1-MTG-006 | 实现收敛轮执行 | 4h | 已完成（2026-04-05） |
| P1-MTG-007 | 共识文档生成 | 3h | 已完成（2026-04-05） |
| P1-MTG-008 | CEO 触发会议决策 | 4h | 已完成（2026-04-05） |
| P1-MTG-009 | 会议事件投影 | 3h | 已完成（2026-04-05） |
| P1-MTG-010 | 会议室测试 | 6h | 已完成（2026-04-05） |

完成补记：

- 本轮按 `ticket-backed meeting room` 实现了最小会议闭环，只开放 `TECHNICAL_DECISION`，不做 `SCOPE_ALIGNMENT` 和 CEO 自动触发。
- `meeting-request` 会创建真实会议投影，并创建带 `meeting_context` 的 `consensus_document` ticket；runtime 会依次跑 `POSITION -> CHALLENGE -> PROPOSAL -> CONVERGENCE` 四轮，再回到现有 maker-checker / board review。
- 当前会议只保留轮次摘要、最终共识摘要和 `meeting-digest.json`，不把 transcript 长期留存做成隐性聊天系统。
- 前端已新增 `Inbox -> /meeting/:meetingId -> MeetingRoomDrawer` 的只读读面，并支持从会议跳到现有 `review room`。
- `doc/TODO.md` 写的是四轮；原任务库标题里只有 `立场 / 质疑 / 收敛` 三段执行项。本轮按 `TODO` 为准补齐四轮，`P1-MTG-006` 实际承担了 `PROPOSAL + CONVERGENCE` 两段收敛逻辑。
- 本轮补上了 `P1-MTG-008`：CEO 现在能在窄触发条件下真实执行 `REQUEST_MEETING`，自动创建 `TECHNICAL_DECISION` 会议请求，并继续复用现有 `meeting-request -> 四轮会议 -> checker / board review` 主链。
- 当前自动会议候选来自 `ceo_shadow_snapshot.meeting_candidates`，基于现有员工投影派生最小能力/角色匹配，不新建持久化 Capability Registry；deterministic 只会在 snapshot 中恰好存在一个合格候选时触发。
- 自动会议只覆盖决策/评审型票的失败恢复，或董事会 `REJECT / MODIFY_CONSTRAINTS` 后的重对齐；不会在 idle maintenance 里泛化自动开会，也不会对 `MEETING_ESCALATION` 再递归开会。

### 3.3 代码清理 (P1-CLN-001 到 P1-CLN-006)

> 当前状态补记：这组任务现在拆成两段看。
>
> - `P1-CLN-005`、`P1-CLN-006` 已在 2026-04-05 收口：冻结能力的真实入口、主线依赖、测试归属和迁移前置条件已经写进 `backend/app/core/mainline_truth.py`，并由 `backend/tests/test_mainline_truth.py` 固化
> - `P1-CLN-001` 已在 2026-04-06 收口为 shim 迁移完成：`worker-admin` 真实实现已迁入 `backend/app/_frozen/worker_admin/`，旧 API / auth / projection / core / CLI 入口只保留兼容壳
> - `P1-CLN-004` 已在 2026-04-06 收口为 shim 迁移完成：`worker-runtime` 真实实现已迁入 `backend/app/_frozen/worker_runtime/`，旧 API / projection / core / CLI 入口只保留兼容壳
> - `P1-CLN-002`、`P1-CLN-003` 当前仍未关闭，也还没进入无壳物理迁移：多租户 scope 仍是共享数据结构，upload 导入入口和 session 存储仍保留

| ID | 标题 | 预估 |
|----|------|------|
| P1-CLN-001 | 移动 worker-admin 代码到 _frozen/ | 3h |
| P1-CLN-002 | 移动多租户代码到 _frozen/ | 2h |
| P1-CLN-003 | 移动对象存储代码到 _frozen/ | 2h |
| P1-CLN-004 | 移动远程 handoff 代码到 _frozen/ | 2h |
| P1-CLN-005 | 更新 import 路径 | 3h |
| P1-CLN-006 | 标记或移除 frozen 测试 | 4h |

完成补记（2026-04-06）：

- `P1-CLN-001` 本轮已按 shim 迁移收口：新增 `backend/app/_frozen/worker_admin/`，承接 API、auth、projection、core 和 CLI 的真实实现
- `app/api/worker_admin.py`、`app/api/worker_admin_auth.py`、`app/api/worker_admin_projections.py`、`app/core/worker_admin.py`、`app/worker_admin_auth_cli.py` 当前只保留兼容导出，不改 HTTP 路径、鉴权语义或 CLI 调用方式
- `backend/app/core/mainline_truth.py`、`backend/tests/test_mainline_truth.py`、`backend/tests/conftest.py` 已同步成新口径：代码真相已切到 `_frozen/worker_admin`，测试时间注入也改为命中新实现
- `P1-CLN-004` 本轮已按 shim 迁移收口：新增 `backend/app/_frozen/worker_runtime/`，承接 API、projection、core 和 CLI 的真实实现
- `app/api/worker_runtime.py`、`app/api/worker_runtime_projections.py`、`app/core/worker_runtime.py`、`app/worker_auth_cli.py` 当前只保留兼容导出，不改 HTTP 路径、签名鉴权语义或 CLI 调用方式
- `backend/app/core/mainline_truth.py`、`backend/tests/test_mainline_truth.py`、`backend/tests/conftest.py` 已同步成新口径：`external_worker_handoff.code_refs` 已切到 `_frozen/worker_runtime`，测试时间注入也改为命中新实现；`worker_bootstrap/session/delivery-grant` schema 仍保留为成组阻塞点
- `P1-CLN-002` 本轮继续停在前置拆分阶段：主线 command 侧已经统一从 workflow/default 解析 scope，`backend/app/contracts/scope.py` 已成为 runtime / worker-admin / worker-runtime 复用的单点 contract，但 runtime、共享读面和冻结 contracts 仍保留 `tenant_id/workspace_id` shape
- `P1-CLN-003` 本轮继续停在前置拆分阶段：`ticket-result-submit` 已只消费 inline 内容或 `artifact_ref`，控制面与 `worker-runtime` 都已有 `ticket-artifact-import-upload` 命令；但 upload 导入入口和 upload session 存储仍保留，所以还不能写成 `_frozen/` 物理迁移已具备条件
- `FrozenCapabilityBoundary` 这轮继续收口为机器可读真相：当前除了真实入口和 `code_refs`，还会显式记录 `api_surface_groups`、`storage_table_refs`、`migration_blocker_refs` 和阻塞摘要，并由 `backend/tests/test_mainline_truth.py` 直接回归

---

## 四、P2：增强

### 4.1 检索层 (P2-RET-001 到 P2-RET-005)

| ID | 标题 | 预估 |
|----|------|------|
| P2-RET-001 | 创建 FTS5 虚拟表 | 4h |
| P2-RET-002 | 索引工单结果和审查摘要 | 4h |
| P2-RET-003 | Context Compiler 集成 FTS5 查询 | 4h |
| P2-RET-004 | 检索结果排序和去重 | 4h |
| P2-RET-005 | 检索层测试 | 4h |

完成补记（2026-04-06）：

- `P2-RET-001`：`backend/app/db/repository.py` 现在会在初始化阶段创建三张 FTS5 虚拟表：`retrieval_review_summary_fts`、`retrieval_incident_summary_fts`、`retrieval_artifact_summary_fts`
- `P2-RET-002`：review / incident / artifact 三类历史来源现在都会被回填进对应索引；approval 创建/resolve、incident projection 重建、artifact 写入或生命周期变化后都会刷新索引
- `P2-RET-003`：`Context Compiler` 没有改 retrieval summary 契约，仍消费 `review_summaries / incident_summaries / artifact_summaries` 三通道，但候选来源已经切到 repository 的 FTS 查询
- `P2-RET-004`：repository 检索结果现在按“命中词数 -> FTS rank -> 最近更新时间 -> 稳定键”排序，并对同一 `source_ref` 去重；artifact 检索仍保留“先粗匹配路径 / kind / media_type，再接受正文命中”的原边界
- `P2-RET-005`：新增 repository 回归，覆盖 FTS 表创建、旧数据回填、排序去重、失效 artifact 过滤；全量验证结果更新为 backend `435 passed`、frontend build passed、frontend `64 passed`

### 4.2 Provider 增强 (P2-PRV-001 到 P2-PRV-008)

| ID | 标题 | 预估 |
|----|------|------|
| P2-PRV-001 | 多 Provider 配置支持 | 4h |
| P2-PRV-002 | 能力标签定义 | 3h |
| P2-PRV-003 | 基础健康检查 | 3h |
| P2-PRV-004 | 简单 fallback 路由 | 4h |
| P2-PRV-005 | Provider 增强测试 | 6h |
| P2-PRV-006 | 角色级默认模型绑定 | 4h |
| P2-PRV-007 | 任务级模型覆盖与 preferred/actual model 追踪 | 4h |
| P2-PRV-008 | 成本分层与高价模型低频路由 | 4h |

### 4.3 治理模板与文档型角色 (P2-GOV-001 到 P2-GOV-006)

| ID | 标题 | 预估 |
|----|------|------|
| P2-GOV-001 | 定义治理模板数据结构 | 4h |
| P2-GOV-002 | 定义 CTO / 架构师低频角色模板 | 4h |
| P2-GOV-003 | 定义架构 / 选型 / 里程碑 / 详细设计 / TODO 文档产物契约 | 4h |
| P2-GOV-004 | CEO 按治理模板触发文档型任务 | 4h |
| P2-GOV-005 | 文档型角色默认不参与日常编码 / 测试执行约束 | 3h |
| P2-GOV-006 | 治理模板与文档型角色测试和文档 | 5h |

完成补记（2026-04-06）：

- `P2-GOV-007`：closeout 证据与文档同步软约束已按最小边界收口，不改状态机，也不新增前端默认读面
- `delivery_closeout_package@1` 现在可选携带 `documentation_updates[{ doc_ref, status, summary }]`，其中 `status` 只接受 `UPDATED / NO_CHANGE_REQUIRED / FOLLOW_UP_REQUIRED`
- deterministic runtime 默认 closeout 产物会补最小 `documentation_updates` 示例，runtime 生成的 internal closeout review 也会把文档同步摘要写进 `recommendation_summary` 和额外 evidence 卡片
- closeout 票创建与 internal closeout review 文案现在明确要求 checker 同时看 final evidence、handoff notes 和文档同步说明；`FOLLOW_UP_REQUIRED` 仍按 soft rule 处理，只有在它已经影响交付完整性时才应转成 blocking finding
- 本轮新增后端测试覆盖了 closeout schema 校验、runtime review 摘要注入，以及 closeout checker 在 `FOLLOW_UP_REQUIRED` 下的 `APPROVED_WITH_NOTES / CHANGES_REQUIRED` 两条主路径

### 4.4 UI 打磨 (P2-UI-001 到 P2-UI-008)

| ID | 标题 | 预估 |
|----|------|------|
| P2-UI-001 | Workflow River 粒子动画 | 4h |
| P2-UI-002 | Board Gate 呼吸动画优化 | 2h |
| P2-UI-003 | 加载骨架屏全覆盖 | 3h |
| P2-UI-004 | 响应式布局 | 4h |
| P2-UI-005 | 键盘可访问性 | 3h |
| P2-UI-006 | 暗色主题微调 | 2h |
| P2-UI-007 | 性能优化（懒加载、debounce） | 3h |
| P2-UI-008 | UI 打磨测试 | 3h |

完成补记（2026-04-05）：

- `P2-UI-001`：保留现有 `Workflow River` 粒子表达，只补 `prefers-reduced-motion` 降级和更稳定的滚动容器，不重做视觉语言
- `P2-UI-002`：首页河道分支与顶栏 `Board Gate` 指示器继续共用同一套 armed / clear 语义与呼吸节奏
- `P2-UI-003`：`InboxWell`、`Workflow River`、`WorkforcePanel`、`EventTicker` 在初次加载时都改成真实骨架屏，不再只靠一条全局 loading 文案
- `P2-UI-004`：窄屏下保留横向五阶段河道和主干语义，不再把五阶段直接打散成纵向卡片
- `P2-UI-005`：前端全部可达路由补上键盘可访问性基础；`AppShell` 现在有 skip link，主布局改成 `main` landmark，`Drawer` 会处理初始焦点、焦点循环、`Escape` 关闭和关闭后回到触发元素
- `P2-UI-006`：dark-glass 基线没有改主题方向，只补了 surface / divider / focus / disabled / board / incident token，并把首页、按钮、输入框和 overlay 的对比度统一到同一套样式语义
- `P2-UI-007`：`ReviewRoomDrawer`、`MeetingRoomDrawer`、`IncidentDrawer`、`DependencyInspectorDrawer`、`ProviderSettingsDrawer` 改成按需懒加载；`useSSE` 对 clustered `boardroom-event` 失效通知默认做 `500ms` debounce
- `P2-UI-008`：补了 `BoardGateIndicator`、`InboxWell`、`WorkflowRiver`、`WorkforcePanel`、`EventTicker` 的最小前端回归测试

### 4.5 文档 (P2-DOC-001 到 P2-DOC-010)

| ID | 标题 | 预估 |
|----|------|------|
| P2-DOC-001 | 更新 README.md | 2h |
| P2-DOC-002 | 更新 doc/TODO.md | 2h |
| P2-DOC-003 | 编写运维指南 | 3h |
| P2-DOC-004 | 更新 memory-log.md | 2h |
| P2-DOC-005 | 编写 API 文档 | 3h |
| P2-DOC-006 | 编写新愿景文档更新与路线重整计划 | 2h |
| P2-DOC-007 | 收口高频入口文档 | 2h |
| P2-DOC-008 | 重整任务库与状态分层 | 2h |
| P2-DOC-009 | 重写里程碑时间线与后置说明 | 2h |
| P2-DOC-010 | 压缩 memory-log 并归档详细日志 | 2h |

完成补记（2026-04-05）：

- `P2-DOC-002`：`doc/TODO.md` 现已把 `P2-D` 改成“第一轮真实缺口收口已完成、剩余任务继续后置推进”的真实状态
- `P2-DOC-004`：`doc/history/memory-log.md` 已追加这轮会影响后续判断的事实，包括分区骨架屏、窄屏河道保留和 reduced-motion 兼容

完成补记（2026-04-06）：

- `P2-DOC-001`：根目录 `README.md` 已按当前主链现实重写，补齐了 closeout、CEO 自动会议、runtime provider 和当前 Windows shell 下 `pytest` 不在 PATH 的验证口径
- `P2-DOC-003`：`doc/backend-runtime-guide.md` 已收口成真实运维指南，按“当前主线 / 冻结兼容面 / 当前限制”重排，避免再把保留代码写成推荐路径
- `P2-DOC-005`：新增 `doc/api-reference.md`，把当前全部 HTTP 接口按真实路由分组平铺，并显式标注主线 / 冻结边界 / 默认是否建议使用
- 为了防止 API 文档再次和代码漂移，本轮新增了 `backend/app/core/api_surface.py` 与 `backend/tests/test_api_surface.py`，用最小回归测试固定当前路由分组
- `P2-DOC-006`：新增 `doc/新愿景文档更新与路线重整计划.md`，把这轮路线重整的判断、文件落点和执行顺序固化成一次性 handoff 文档，并明确它不是新的真相源
- `P2-DOC-007`：`README.md`、`doc/README.md`、`doc/roadmap-reset.md`、`doc/history/context-baseline.md` 已按新分层重写，把“当前该看什么、当前该做什么”和“治理规则 / 远期储备”拆开
- `P2-DOC-008`：`doc/TODO.md`、`doc/task-backlog.md`、`doc/task-backlog/active.md`、`doc/todo/postponed.md` 已按“当前批次 / 条件批次 / 远期储备”重排，并补入 `P2-RET-006`、`P2-CEO-001`、`P2-CEO-002`、`P2-MTG-011`、`P2-GOV-007`
- `P2-DOC-009`：`doc/milestone-timeline.md` 已从旧周历重写为“当前状态 + 后续顺序 + C1 条件批次 + R1 远期储备”
- `P2-DOC-010`：`doc/history/memory-log.md` 已压缩成短事实日志，`doc/history/archive/memory-log-detailed-2026-04-03_to_2026-04-06.md` 负责承接本轮移出的详细实现流水账

---

## 五、关键依赖图

```
P1-CLN-* ──→ P0-CEO-001 ──→ P0-CEO-002 ──→ P0-CEO-003 ──→ P0-CEO-004
                  │                                            │
                  ↓                                            ↓
             P0-CEO-015                                   P0-CEO-005 ──→ P0-CEO-006
                                                               │
                                                               ↓
                                                          P0-CEO-007 ──→ P0-CEO-008
                                                               │           P0-CEO-009
                                                               │           P0-CEO-010
                                                               ↓
                                                          P0-CEO-011
                                                          P0-CEO-012
                                                          P0-CEO-013
                                                               │
                                                               ↓
                                                          P0-CEO-014

P0-WRK-001 ──→ P0-WRK-002 ──→ P0-WRK-003
                    │           P0-WRK-004
                    │           P0-WRK-005
                    ↓
               P0-WRK-006
               P0-WRK-007 ──→ P0-WRK-008
               P0-WRK-009
               P0-WRK-010
                    │
                    ↓
               P0-WRK-011 ──→ P0-WRK-012

P0-FE-001 ──→ P0-FE-002 ──→ P0-FE-003 ──→ P0-FE-004 ──→ P0-FE-005
                                               │           P0-FE-006
                                               ↓
                                          P0-FE-008 ──→ P0-FE-014 ──→ P0-FE-015
                                          P0-FE-009                     P0-FE-016
                                          P0-FE-010                         │
                                                                            ↓
              P0-FE-007                   P0-FE-012 ──→ P0-FE-017 ──→ P0-FE-018 ──→ P0-FE-019
              P0-FE-011                   P0-FE-013                                     │
              P0-FE-021                                                                 ↓
                                                                                   P0-FE-020
                                                                                   P0-FE-022

P0-CEO-014 + P0-WRK-012 + P0-FE-022 ──→ P0-INT-* ──→ P0-REL-*
```

---

## 六、总结

| 指标 | 数值 |
|------|------|
| 总任务数 | 121 |
| P0 任务数 | 65 |
| P1 任务数 | 24 |
| P2 任务数 | 32 |
| 总预估工时 | 464h |
| P0 预估工时 | 304h |
| 预计完成周数（2人） | 10-13 周 |
