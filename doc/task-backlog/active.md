# Active Task Backlog

> 说明：这里只保留当前仍未关闭、仍可能被反复读取的任务。已完成的详细任务卡片和完成补记统一看 `done.md`。

## 快速定位

| 方向 | 任务范围 | 默认状态 | 备注 |
|------|----------|----------|------|
| 架构解耦前置 | `P2-DEC-004` | 当前主线 | `P2-DEC-001 / P2-DEC-002 / P2-DEC-003` 已完成；下一步继续收 CEO 防停滞与定时唤醒边界 |
| 冻结后置 | `P1-CLN-002` 到 `P1-CLN-003` | 冻结后置 | blocker 仍在，但不再占用当前主线 |
| Provider 增强 | `P2-PRV-007` 到 `P2-PRV-008` | 后置增强 | `P2-PRV-001/002/003/004/005/006` 已于 2026-04-07 手动纳入并收口 |
| 治理模板与文档链 | `P2-GOV-003` 到 `P2-GOV-006` | 后置增强 | `P2-GOV-001`、`P2-GOV-002` 已于 2026-04-07 手动纳入并收口；`P2-GOV-007` 已在 2026-04-06 收口；当前顺序排在 `P2-DEC-*` 之后 |
| 角色纳入链 | `P2-RLS-001` 到 `P2-RLS-003` | 后续工作链纳入 | 统一目录已就位，但 staffing / CEO / runtime 仍未接入；等待 `P2-DEC-*` 与 `P2-GOV-003/004` |

## 当前判断

- `P2-M7-001` 到 `P2-M7-005` 已于 2026-04-06 收口：主线 evidence / completion 的最小证据消费面现在已经接到统一只读查看入口
- `P2-RET-006` 已于 2026-04-06 显式纳入并收口：execution package 与 rendered `SYSTEM_CONTROLS` 现在会暴露结构化 `org_context`，继续保持 `L1` 边界，不引入新存储或新检索通道
- `P2-CEO-001` 已于 2026-04-07 手动纳入并收口：`project-init` 现在可先打开 `REQUIREMENT_ELICITATION` 板审，董事会在现有 Review Room 里提交结构化答卷后，再继续 scope kickoff / scope review
- `P2-MTG-011` 已于 2026-04-07 手动纳入并收口：会议 `consensus_document@1` 现在可选携带 ADR 化 `decision_record`，Meeting Room 默认先看决策视图，会议来源 follow-up ticket 会额外带 ADR 摘要
- `P2-CEO-002` 已于 2026-04-07 手动纳入并收口：OpenAI Compat live CEO 现在会先消费当前 workflow 内 `reuse_candidates`，优先复用已有完成交付、已关闭会议或恢复现有工作；deterministic fallback 保持不变
- `P2-PRV-001 / P2-PRV-005 / P2-PRV-006` 已于 2026-04-07 手动纳入并收口：runtime provider 已从单一 OpenAI 表单升级为最小 registry，当前真实支持 `OpenAI Compat / Claude Code CLI`，并开放现有真实角色的默认 provider / model 绑定
- `P2-PRV-002 / P2-PRV-003 / P2-PRV-004` 已于 2026-04-07 手动纳入并收口：provider registry 现在会暴露结构化 `capability_tags[]`、每个 provider 的 `health_status / health_reason`，并支持最小 `fallback_provider_ids[]`；运行时与 CEO 只在 `PROVIDER_RATE_LIMITED / UPSTREAM_UNAVAILABLE` 时尝试满足目标能力底线的备选 provider
- `P2-GOV-001` 已于 2026-04-07 手动纳入并收口：后端先补了治理模板基础目录，给后续角色目录和文档链打底
- `P2-GOV-002` 已于 2026-04-07 手动纳入并收口：当前统一只读 `role_templates_catalog` 已覆盖 `3` 个 live 执行模板、`3` 个未来执行模板、`2` 个治理模板、`5` 类文档 metadata ref 和 `9` 个模板片段；`workforce` worker 还会返回 `source_template_id / source_fragment_refs`
- `runtime-provider.future_binding_slots` 现在不再只看治理角色，而是从统一目录筛出未启用模板；当前最小覆盖 `backend_engineer / database_engineer / platform_sre / architect / cto`
- `P2-DEC-001` 已于 2026-04-07 完成：ticket create spec 现已补入 `execution_contract / dispatch_intent`，CEO create-ticket 校验会拒绝不存在、非激活或能力不匹配的 assignee，runtime/provider 会优先按 `execution_contract.execution_target_ref` 选路，同时兼容 legacy `role_profile:*` binding
- `P2-DEC-002` 已于 2026-04-07 完成：scheduler 现在会在 `dispatch_intent.assignee_employee_id` 存在时只租约给该 assignee，并把 `dependency_gate_refs / selected_by / wakeup_policy` 收进 `dispatch_intent`；ticket-create 会拒绝自依赖、缺失依赖和简单 dependency cycle；显式 dependency gate 的坏依赖会被 scheduler 转成结构化失败并触发 CEO 重决策
- 对现有 `delivery_stage + parent_ticket_id` staged follow-up 主链，这轮按最保守口径只把 `missing / cancelled` 视为硬坏依赖；`FAILED / TIMED_OUT` 仍继续等待同节点 retry / recovery，不提前把下游 staged ticket 全部打死
- `P2-DEC-003` 已于 2026-04-07 完成：ticket create spec 与 compile request 现已补入 `input_process_asset_refs[]`，`Context Compiler` 会先把 `input_artifact_refs[]` 兼容映射到过程资产，再统一走 resolver；当前已纳入 `artifact / compiled_context_bundle / compile_manifest / compiled_execution_package / meeting_decision_record / closeout_summary` 六类过程资产
- runtime 完成事件现在会写回结构化 `produced_process_assets[]`；meeting ADR、closeout summary 和 runtime 默认 artifact 都会自动映射回 follow-up / maker-checker 输入，避免 Context Compiler 继续直接猜底层存储类型
- 当前新的唯一主线任务是 `P2-DEC-004`：继续收 CEO 定时唤醒、防停滞与 runner 编排边界；之后才继续文档型角色链或角色纳入链

## P1：冻结后置

### 3.3 代码清理

当前这两条任务仍未关闭，但已降级为冻结后置：

- `P1-CLN-002`：主线 command 已经不再直接依赖 `tenant_id/workspace_id`，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留这组 data shape
- `P1-CLN-003`：主线结果提交已与 upload session 解耦，但 upload 导入入口和 upload session 存储仍保留

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P1-CLN-002 | 移动多租户代码到 _frozen/ | 2h | 冻结后置 |
| P1-CLN-003 | 移动对象存储代码到 _frozen/ | 2h | 冻结后置 |

## P2：当前主线与增强

### 4.1 架构解耦前置

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-DEC-004 | CEO 定时唤醒、防停滞与回归/文档收口 | 4h | 当前主线 |

### 4.2 Provider 增强

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-PRV-007 | 任务级模型覆盖与 preferred/actual model 追踪 | 4h | 后置增强 |
| P2-PRV-008 | 成本分层与高价模型低频路由 | 4h | 后置增强 |

### 4.3 治理模板与文档链

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-GOV-003 | 文档/设计型角色产物契约与可编译输入 | 4h | 后置增强 |
| P2-GOV-004 | CEO 按统一目录触发文档/设计链 | 4h | 后置增强 |
| P2-GOV-005 | 角色纳入顺序与工作链路边界 | 3h | 后置增强 |
| P2-GOV-006 | 统一角色目录的测试、前端说明与文档真相收口 | 5h | 后置增强 |

### 4.4 角色纳入链

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-RLS-001 | staffing 模板与 workforce lane 纳入新增角色 | 4h | 后续工作链纳入 |
| P2-RLS-002 | CEO 建票 preset、meeting policy 与 follow-up 纳入新增角色 | 4h | 后续工作链纳入 |
| P2-RLS-003 | runtime 支持矩阵、context compiler 与 provider target label 纳入新增角色 | 5h | 后续工作链纳入 |

## 依赖提醒

- `P1-CLN-*` 只有在 blocker 真正松动后才重新打开物理迁移
- `P2-DEC-004` 是当前默认主线；`P2-DEC-003` 已完成，本轮如果继续实现，应优先收 CEO 防停滞边界
- 虽然 `P2-DEC-002` 已完成，但当前批次还没收口；默认不跳到 `P2-GOV-*` 或 `P2-RLS-*`
- `P2-RLS-*` 只有在 `P2-DEC-*` 与 `P2-GOV-003/004` 完成后，才适合继续接 staffing / CEO / runtime
- `P2-PRV-*` 的后置增强如果会继续碰运行时路由，也应以后续 `P2-DEC-003/004` 的边界收口为前置
- 条件纳入任务进入执行前，必须先把触发原因写回 `TODO.md`
