# Boardroom OS 详细 TODO 清单

> 版本：1.0
> 日期：2026-04-03
> 作者：CTO
> 总任务数：112

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
| P2 | Provider 增强 | 5 | 20h |
| P2 | UI 打磨 | 8 | 24h |
| P2 | 文档 | 5 | 12h |
| P0 | 集成测试 | 8 | 32h |
| P0 | 发布准备 | 8 | 24h |
| **合计** | | **112** | **428h** |

---

## 二、P0：关键路径

### 2.1 CEO Agent 实现

---

#### P0-CEO-001：定义 CEO Action Schema

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

---

#### P0-CEO-002：实现 CEO 状态快照读取器

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

---

#### P0-CEO-003：实现 CEO 角色提示模板

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

---

#### P0-CEO-004：实现 CEO Action Proposer

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

---

#### P0-CEO-005：实现 CEO Action Validator

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

---

#### P0-CEO-006：实现 CEO Action Executor

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

---

#### P0-CEO-007：实现 CEO 调度器主循环

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

---

#### P0-CEO-008：实现 CEO 事件驱动唤醒

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

---

#### P0-CEO-009：实现 CEO 定时唤醒

**描述**：在 scheduler_runner 中添加定时 CEO 唤醒，确保系统不会因为错过事件而停滞。

**文件**：
- 修改：`backend/app/scheduler_runner.py`
- 修改：`backend/app/core/ceo_scheduler.py`

**依赖**：P0-CEO-007

**预估**：3h

**feature-spec**：条目 6

**验收标准**：
- 每 60 秒检查一次是否有需要推进的工作
- 如果没有待处理事项，CEO 返回 NO_ACTION
- 定时间隔可通过配置调整

**风险**：低

---

#### P0-CEO-010：实现确定性回退

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

---

#### P0-CEO-011：CEO 任务拆解能力

**描述**：CEO 能根据 north_star_goal 和当前阶段，自主决定需要创建哪些工单。

**文件**：
- 修改：`backend/app/core/ceo_prompts.py`
- 修改：`backend/app/core/ceo_proposer.py`

**依赖**：P0-CEO-007

**预估**：6h

**feature-spec**：条目 1

**验收标准**：
- project-init 后，CEO 能自主创建第一批工单（而不是硬编码）
- 工单的 spec 内容由 CEO 根据目标生成
- 工单类型和数量合理（不超过 5 个并行工单）

**风险**：高（依赖提示工程质量）

---

#### P0-CEO-012：CEO 招聘决策能力

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

---

#### P0-CEO-013：CEO 重试与重分派决策

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

---

#### P0-CEO-014：CEO 集成测试

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

---

#### P0-CEO-015：CEO 输出 Schema 注册

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

**描述**：增强 schema 校验，处理真实 LLM 输出中常见的格式问题。

**文件**：
- 修改：`backend/app/core/ticket_handlers.py`（`handle_ticket_result_submit` 中的校验逻辑）
- 修改：`backend/app/core/output_schemas.py`

**依赖**：P0-WRK-001

**预估**：4h

**feature-spec**：条目 33, 38

**验收标准**：
- 能处理 LLM 输出中的额外空白、换行、注释
- JSON 解析失败时尝试修复常见问题（如尾逗号、单引号）
- 校验失败时产出结构化错误报告，包含具体字段和期望值

**风险**：低

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

---

#### P0-FE-012：创建通用 Drawer 组件

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

---

#### P0-FE-013：创建共享基础组件

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

---

#### P0-FE-014：创建布局组件

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

---

#### P0-FE-015：提取仪表盘组件

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

---

#### P0-FE-016：提取 WorkforcePanel 和 EventTicker

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

---

#### P0-FE-017：重构覆盖层组件使用通用 Drawer

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

---

#### P0-FE-018：创建 DashboardPage

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

---

#### P0-FE-019：简化 App.tsx

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

---

#### P0-FE-020：拆分 CSS

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

---

#### P0-FE-021：创建工具函数模块

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

---

#### P0-FE-022：前端核心测试

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

---

### 2.4 集成测试

---

#### P0-INT-001 到 P0-INT-008：端到端集成测试

（8 个任务，覆盖完整链路、故障恢复、确定性回退、前后端联调等场景）

**预估**：共 32h

---

### 2.5 发布准备

---

#### P0-REL-001 到 P0-REL-008：回归测试、安全审查、Docker 打包、文档更新等

**预估**：共 24h

---

## 三、P1：重要

### 3.1 人格模型 (P1-PER-001 到 P1-PER-008)

| ID | 标题 | 预估 |
|----|------|------|
| P1-PER-001 | 定义 skill_profile 维度 | 3h |
| P1-PER-002 | 定义 personality_profile 维度 | 3h |
| P1-PER-003 | 定义 aesthetic_profile 维度 | 2h |
| P1-PER-004 | 创建 6 种预设人格模板 | 4h |
| P1-PER-005 | 人格注入 Context Compiler | 4h |
| P1-PER-006 | 多样性约束实现 | 3h |
| P1-PER-007 | 更新 staffing_catalog.py | 2h |
| P1-PER-008 | 人格模型测试 | 3h |

### 3.2 会议室协议 (P1-MTG-001 到 P1-MTG-010)

| ID | 标题 | 预估 |
|----|------|------|
| P1-MTG-001 | 定义会议事件类型 | 3h |
| P1-MTG-002 | 定义会议请求契约 | 3h |
| P1-MTG-003 | 实现会议状态机 | 6h |
| P1-MTG-004 | 实现立场轮执行 | 4h |
| P1-MTG-005 | 实现质疑轮执行 | 4h |
| P1-MTG-006 | 实现收敛轮执行 | 4h |
| P1-MTG-007 | 共识文档生成 | 3h |
| P1-MTG-008 | CEO 触发会议决策 | 4h |
| P1-MTG-009 | 会议事件投影 | 3h |
| P1-MTG-010 | 会议室测试 | 6h |

### 3.3 代码清理 (P1-CLN-001 到 P1-CLN-006)

> 当前状态补记：这 6 个任务本轮**没有执行**。这轮只借用了它们的边界梳理思路来完成文档隔离，没有做 `_frozen/` 物理迁移。

| ID | 标题 | 预估 |
|----|------|------|
| P1-CLN-001 | 移动 worker-admin 代码到 _frozen/ | 3h |
| P1-CLN-002 | 移动多租户代码到 _frozen/ | 2h |
| P1-CLN-003 | 移动对象存储代码到 _frozen/ | 2h |
| P1-CLN-004 | 移动远程 handoff 代码到 _frozen/ | 2h |
| P1-CLN-005 | 更新 import 路径 | 3h |
| P1-CLN-006 | 标记或移除 frozen 测试 | 4h |

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

### 4.2 Provider 增强 (P2-PRV-001 到 P2-PRV-005)

| ID | 标题 | 预估 |
|----|------|------|
| P2-PRV-001 | 多 Provider 配置支持 | 4h |
| P2-PRV-002 | 能力标签定义 | 3h |
| P2-PRV-003 | 基础健康检查 | 3h |
| P2-PRV-004 | 简单 fallback 路由 | 4h |
| P2-PRV-005 | Provider 增强测试 | 6h |

### 4.3 UI 打磨 (P2-UI-001 到 P2-UI-008)

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

### 4.4 文档 (P2-DOC-001 到 P2-DOC-005)

| ID | 标题 | 预估 |
|----|------|------|
| P2-DOC-001 | 更新 README.md | 2h |
| P2-DOC-002 | 更新 doc/TODO.md | 2h |
| P2-DOC-003 | 编写运维指南 | 3h |
| P2-DOC-004 | 更新 memory-log.md | 2h |
| P2-DOC-005 | 编写 API 文档 | 3h |

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
| 总任务数 | 112 |
| P0 任务数 | 65 |
| P1 任务数 | 24 |
| P2 任务数 | 23 |
| 总预估工时 | 428h |
| P0 预估工时 | 304h |
| 预计完成周数（2人） | 10-13 周 |
