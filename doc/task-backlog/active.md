# Active Task Backlog

> 说明：这里只保留当前仍未关闭、仍可能被反复读取的任务。已完成的详细任务卡片和完成补记统一看 `done.md`。

## 快速定位

| 方向 | 任务范围 | 默认状态 | 备注 |
|------|----------|----------|------|
| 冻结后置 | `P1-CLN-002` 到 `P1-CLN-003` | 冻结后置 | blocker 仍在，但不再占用当前主线 |
| Provider 增强 | `P2-PRV-007` 到 `P2-PRV-008` | 后置增强 | `P2-PRV-001/002/003/004/005/006` 已于 2026-04-07 手动纳入并收口 |
| 治理模板与交付口径 | `P2-GOV-002` 到 `P2-GOV-006` | 后置增强 | `P2-GOV-001` 已于 2026-04-07 手动纳入并收口；`P2-GOV-007` 已在 2026-04-06 收口 |

## 当前判断

- `P2-M7-001` 到 `P2-M7-005` 已于 2026-04-06 收口：主线 evidence / completion 的最小证据消费面现在已经接到统一只读查看入口
- `P2-RET-006` 已于 2026-04-06 显式纳入并收口：execution package 与 rendered `SYSTEM_CONTROLS` 现在会暴露结构化 `org_context`，继续保持 `L1` 边界，不引入新存储或新检索通道
- `P2-CEO-001` 已于 2026-04-07 手动纳入并收口：`project-init` 现在可先打开 `REQUIREMENT_ELICITATION` 板审，董事会在现有 Review Room 里提交结构化答卷后，再继续 scope kickoff / scope review
- `P2-MTG-011` 已于 2026-04-07 手动纳入并收口：会议 `consensus_document@1` 现在可选携带 ADR 化 `decision_record`，Meeting Room 默认先看决策视图，会议来源 follow-up ticket 会额外带 ADR 摘要
- `P2-CEO-002` 已于 2026-04-07 手动纳入并收口：OpenAI Compat live CEO 现在会先消费当前 workflow 内 `reuse_candidates`，优先复用已有完成交付、已关闭会议或恢复现有工作；deterministic fallback 保持不变
- `P2-PRV-001 / P2-PRV-005 / P2-PRV-006` 已于 2026-04-07 手动纳入并收口：runtime provider 已从单一 OpenAI 表单升级为最小 registry，当前真实支持 `OpenAI Compat / Claude Code CLI`，并开放现有真实角色的默认 provider / model 绑定
- `P2-PRV-002 / P2-PRV-003 / P2-PRV-004` 已于 2026-04-07 手动纳入并收口：provider registry 现在会暴露结构化 `capability_tags[]`、每个 provider 的 `health_status / health_reason`，并支持最小 `fallback_provider_ids[]`；运行时与 CEO 只在 `PROVIDER_RATE_LIMITED / UPSTREAM_UNAVAILABLE` 时尝试满足目标能力底线的备选 provider
- `P2-GOV-001` 已于 2026-04-07 手动纳入并收口：后端新增单点 `governance_templates` catalog，`workforce` 投影与 `runtime-provider.future_binding_slots` 现在都从同一份只读治理模板真相派生；当前仍不启用治理角色执行
- 当前未关闭任务里，没有可以直接开启的默认主线任务；剩余项都属于冻结后置或后置增强
- 如果没有新任务被纳入当前批次、且条件任务也未触发，本轮应明确判定为“无可直接开启任务”

## P1：冻结后置

### 3.3 代码清理

当前这两条任务仍未关闭，但已降级为冻结后置：

- `P1-CLN-002`：主线 command 已经不再直接依赖 `tenant_id/workspace_id`，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留这组 data shape
- `P1-CLN-003`：主线结果提交已与 upload session 解耦，但 upload 导入入口和 upload session 存储仍保留

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P1-CLN-002 | 移动多租户代码到 _frozen/ | 2h | 冻结后置 |
| P1-CLN-003 | 移动对象存储代码到 _frozen/ | 2h | 冻结后置 |

## P2：增强

### 4.1 Provider 增强

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-PRV-007 | 任务级模型覆盖与 preferred/actual model 追踪 | 4h | 后置增强 |
| P2-PRV-008 | 成本分层与高价模型低频路由 | 4h | 后置增强 |

### 4.2 治理模板与交付口径

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-GOV-002 | 定义 CTO / 架构师低频角色模板 | 4h | 后置增强 |
| P2-GOV-003 | 治理文档产物契约与可编译输入 | 4h | 后置增强 |
| P2-GOV-004 | CEO 按治理模板触发文档型任务 | 4h | 后置增强 |
| P2-GOV-005 | 文档型角色默认不参与日常编码 / 测试执行约束 | 3h | 后置增强 |
| P2-GOV-006 | 治理模板与文档型角色测试和文档 | 5h | 后置增强 |

## 依赖提醒

- `P1-CLN-*` 只有在 blocker 真正松动后才重新打开物理迁移
- `P2-RET-*`、`P2-PRV-*`、`P2-GOV-*` 目前都不是默认主线
- 条件纳入任务进入执行前，必须先把触发原因写回 `TODO.md`
