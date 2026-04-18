# 新架构重构实施计划

> 状态：`active`
> 当前阶段：`P4`
> 当前切片：`P4-S7`
> 最后更新：`2026-04-18 07:57`
> 负责人：`Codex / 人工协作`
> 计划性质：`可续跑主计划`
> 架构文档状态：`只读，不修改`

---

## 1. 这份计划是干什么的

这份文档只负责一件事：  
把 `doc/new-architecture/` 定下来的目标架构，拆成可以连续推进、可中断恢复、可逐阶段验收的重构计划。

这份计划允许更新。  
`doc/new-architecture/` 下的架构决策文档默认只读，不在实施阶段顺手改写。  
如果发现架构和代码现实冲突，只能记录到“偏差与待决策”区，不能直接改架构文档。

---

## 2. 固定输入文档

每次新会话开始，先按这个顺序读，不跳步：

1. `README.md`
2. `doc/README.md`
3. `doc/mainline-truth.md`
4. `doc/roadmap-reset.md`
5. `doc/TODO.md`
6. `doc/new-architecture/README.md`
7. 本计划文档
8. 本计划里“当前阶段”对应的相关架构文档
9. 只有在需要历史原因时，再读 `doc/history/context-baseline.md` 和 `doc/history/memory-log.md`

---

## 3. 实施铁律

- `doc/new-architecture/**` 默认只读。
- 实施必须以当前代码现实为基础，做增量重构，不重建骨架。
- 每轮只选一个主方向，连续完成 `2` 到 `4` 个强相关切片。
- 每个切片都必须有：目标、边界、代码改动、验证方式、文档同步动作。
- 每阶段结束后，必须核对任务清单并更新本计划。
- 只能把“已实现、已验证、已同步文档”的内容勾成完成。
- 发现偏差、阻塞、设计疑点，先记到文档，不要临场扩范围。
- 如果某项需要改架构决策，先停在“待决策”，由单独决策流程处理。
- 不允许为了省事重写本计划结构。只更新状态、勾选框、时间戳、会话记录和必要说明。

---

## 4. 总目标

把当前主线从“多口径协议 + 文档提醒式收口”收正成“事件、图、执行包、hook 驱动的单一自治状态机主链”。

---

## 5. 阶段总览

| 阶段 | 名称 | 目标 | 状态 | 完成标准 |
|---|---|---|---|---|
| `P0` | 前置协议收口 | 先补初始化、并发、版本、物化这些地基 | `done` | 关键前置协议有代码入口和最小验证 |
| `P1` | 图与控制面收口 | 收正图协议、controller、ready 节点选择 | `done` | 图成为正式真相面 |
| `P2` | 恢复与 Hook 收口 | Incident、Recovery、Hook 门禁接管主链 | `done` | 失败显式化、后置动作制度化 |
| `P3` | 执行包与 CEO 收口 | 执行包、CEO 快照、技能绑定接管运行时 | `done` | CEO / Worker 不再靠长提示词兜底 |
| `P4` | 顾问环与地图接入 | Board 顾问环、ProjectMap、健康监视接入 | `in_progress` | 可重规划、可诊断、可复盘 |

状态只允许用：

- `todo`
- `in_progress`
- `blocked`
- `done`

---

## 6. 当前阶段

### 当前阶段编号
`P4`

### 当前阶段目标
先把 Board 顾问环、`ProjectMap` 和 `GraphHealth` 收进正式主链；在这条边界已经落稳后，继续把 placeholder 从 graph truth 进入 runtime truth 的生命周期协议收硬，避免执行态再从 `node_projection` 缺失反向猜状态。

### 当前阶段入口条件
- [x] 当前代码现实已核对
- [x] 本阶段相关架构文档已重读
- [x] 上一阶段的未完成项已转移
- [x] 本阶段切片范围已锁定
- [x] 验证方式已明确

### 当前阶段出口条件
- [ ] 本阶段所有必做切片完成
- [x] `BoardAdvisorySession` 已进入正式合同、持久化和只读投影
- [x] `MODIFY_CONSTRAINTS` 已收成显式顾问决策、`DECISION_SUMMARY` 过程资产和可选治理档位 supersede
- [x] `build_ceo_shadow_snapshot()` 已输出 `board_advisory_sessions / latest_advisory_decision`，CEO prompt 已切到新读面
- [x] `Review Room` 已暴露 `advisory_context`，现有抽屉已能显示最小 advisory 摘要和治理档位 patch 控件
- [x] `ProjectMap` 已进入正式合同和可消费读面
- [x] `GraphHealthMonitor` 已进入正式合同和 incident / snapshot 主链
- [x] placeholder lifecycle 已在 `ticket-create / CEO create-ticket / compile / ticket-start / ticket-result-submit` 收成显式 gate
- [x] 每个已完成切片都有最小验证证据
- [x] 涉及的运行文档已同步
- [x] `doc/history/memory-log.md` 已补记

---

## 7. 当前阶段切片清单

### 切片 `P0-S1`
**名称：**  
`Bootstrap / 初始化序列落地`

**现实问题：**  
`Projection、Graph、Snapshot 冷启动时不能互相卡死。`

**对应架构文档：**
- `doc/new-architecture/00-autonomous-machine-overview.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/12-architecture-audit-report.md`
- `doc/new-architecture/13-cross-cutting-concerns.md`

**实施边界：**
- 做什么：
  - [x] 定义初始化阶段状态
  - [x] 建最小 bootstrap 入口
  - [x] 让初始 Projection / Graph 可生成
- 不做什么：
  - [x] 不顺手重写调度器
  - [x] 不顺手补 UI

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] 冷启动命令可跑通
- [x] 最小测试通过
- [x] 能生成初始状态快照

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P0-S2`
**名称：**  
`统一版本协议接线`

**现实问题：**  
`graph_version、asset version、profile version 现在不是一套规则，后面恢复和回放会乱。`

**对应架构文档：**
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/11-governance-profile-and-audit-modes.md`
- `doc/new-architecture/13-cross-cutting-concerns.md`

**实施边界：**
- 做什么：
  - [x] 建版本标识和 supersede 链
  - [x] 让关键对象带显式版本
  - [x] 接最小版本校验
- 不做什么：
  - [x] 不补完整历史 diff UI
  - [x] 不扩远期版本管理平台层

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] 新版本创建可追踪
- [x] supersede 链可查询
- [x] 冲突场景有失败保护

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`

**状态：** `done`

### 切片 `P0-S3`
**名称：**  
`并发控制与写保护`

**现实问题：**  
`CEO、Hook、Materializer 可能抢写同一资源。`

**对应架构文档：**
- `doc/new-architecture/01-document-constitution.md`
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/13-cross-cutting-concerns.md`

**实施边界：**
- 做什么：
  - [x] 给关键写路径补版本检查
  - [x] 建最小冲突失败保护
  - [x] 接必要租约或独占写规则
- 不做什么：
  - [x] 不一次做完整分布式并发层
  - [x] 不顺手重构无关 repository

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] 关键写路径有版本检查
- [x] 冲突时 fail-closed
- [x] 有最小并发测试或模拟验证

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`

**状态：** `done`

### 切片 `P0-S4`
**名称：**  
`Document Materializer 最小闭环`

**现实问题：**  
`文档现在还主要靠提示词提醒，不是事件和投影的物化视图。`

**对应架构文档：**
- `doc/new-architecture/01-document-constitution.md`
- `doc/new-architecture/12-architecture-audit-report.md`

**实施边界：**
- 做什么：
  - [x] 让至少一类视图文档自动物化
  - [x] 记录文档来源版本
  - [x] 建最小一致性检查
- 不做什么：
  - [x] 不一次覆盖所有文档面
  - [x] 不改架构决策文档正文

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] 至少一类视图文档能自动物化
- [x] 文档落后时可被检测
- [x] 不允许人工正文反推真相

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`

**状态：** `done`

### 切片 `P1-S1`
**名称：**  
`TicketGraph 基础合同与最小读索引`

**现实问题：**  
`workflow_controller / ceo_snapshot 还在直接拼 ticket_projection、node_projection、parent_ticket_id 和 dependency_gate_refs，图协议还不是真正的一等真相。`

**对应架构文档：**
- `doc/new-architecture/02-ticket-graph-engine.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/12-architecture-audit-report.md`
- `doc/new-architecture/13-cross-cutting-concerns.md`

**实施边界：**
- 做什么：
  - [x] 新增正式 `TicketGraphSnapshot / TicketGraphNode / TicketGraphEdge / TicketGraphIndexSummary`
  - [x] 用 legacy ticket/node/projection 归约最小 `PARENT_OF / DEPENDS_ON / REVIEWS` 边
  - [x] 让 `ceo_snapshot / workflow_controller` 开始读图摘要
- 不做什么：
  - [x] 不引入 graph patch 写路径
  - [x] 不重写 controller 决策内核
  - [x] 不顺手扩到 hook / recovery / ProjectMap

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] governance / backlog / maker-checker 主线都能归约出稳定边
- [x] invalid legacy dependency 会显式 blocked，不做静默 fallback
- [x] `ceo_snapshot / scheduler_runner` 相关回归通过

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P1-S2`
**名称：**  
`TicketGraph 正式索引与 controller / dashboard 对齐`

**现实问题：**  
`workflow_controller` 对 ready/blocked/runtime 仍混用 ticket status 和图摘要，dashboard 的 blocked / critical-path 也还在各拼各的，图索引还没真正变成共享协议面。`

**对应架构文档：**
- `doc/new-architecture/02-ticket-graph-engine.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/12-architecture-audit-report.md`
- `doc/new-architecture/13-cross-cutting-concerns.md`

**实施边界：**
- 做什么：
  - [x] 扩 `TicketGraphIndexSummary`，补齐 `in_flight_* / critical_path_node_ids / blocked_reasons`
  - [x] 让 `workflow_controller` 的 ready / blocked / in-flight gate 正式消费图索引
  - [x] 让 dashboard 的 `blocked_node_ids / critical_path_node_ids / ops_strip.blocked_nodes` 优先复用同一套图索引
- 不做什么：
  - [x] 不引入 graph patch 写路径
  - [x] 不提前改 `Dependency Inspector`
  - [x] 不重写 dashboard 的 phase 分桶逻辑

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `TicketGraph` 已能归约 `in_flight / critical_path / blocked_reasons`
- [x] `workflow_controller / ceo_snapshot` 已继续沿同一套图索引判断 runtime gate 和 ready count
- [x] dashboard blocked / critical-path 相关 API 回归通过

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P1-S3`
**名称：**  
`Dependency Inspector 与图读面清尾`

**现实问题：**  
`Dependency Inspector` 还在按 legacy ticket snapshot 和 parent-only 路径解释依赖；dashboard blocked 读面虽然已优先吃图索引，但兼容层还没退出。`

**对应架构文档：**
- `doc/new-architecture/02-ticket-graph-engine.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/12-architecture-audit-report.md`
- `doc/new-architecture/14-graph-health-monitor.md`

**实施边界：**
- 做什么：
  - [x] 让 `Dependency Inspector` 正式消费 `TicketGraph` 边和索引
  - [x] 明确 dashboard blocked 兼容层的退出条件
  - [x] 给后续图健康读面预留最小只读接线点
- 不做什么：
  - [x] 不引入 graph patch 写路径
  - [x] 不提前做 `GraphHealthMonitor` incident 自动化
  - [x] 不顺手改 hook / recovery / ProjectMap

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `Dependency Inspector` 的节点顺序、阻断原因和关键路径改成按图真相输出
- [x] dashboard 不再新增第二套 blocked 解释逻辑
- [x] 相关 API / UI 最小回归通过

**文档更新：**
- [x] 更新本计划文档
- [x] 视影响更新 `doc/TODO.md`
- [x] 视影响更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P2-S1`
**名称：**  
`TicketGraph 故障显式化与恢复入口`

**现实问题：**  
`graph_unavailable` 之前只停在 dashboard 的只读状态；`workflow_auto_advance` 命中 `build_ceo_shadow_snapshot()` 异常时会直接中断，不会留下正式 incident、恢复动作和门禁轨迹。`

**对应架构文档：**
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/06-role-hook-system.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/14-graph-health-monitor.md`

**实施边界：**
- 做什么：
  - [x] 给 `TicketGraph` 真不可用补正式 `TICKET_GRAPH_UNAVAILABLE` incident 和去重指纹
  - [x] 把 `workflow_auto_advance` 接到这条 incident 主链，禁止继续静默推进
  - [x] 给 incident detail / resolve / Incident Drawer 补最小恢复动作 `REBUILD_TICKET_GRAPH`
- 不做什么：
  - [x] 不做正式 `RoleHook` registry
  - [x] 不做 `GraphHealthMonitor` 全量落地
  - [x] 不改 dashboard GET 为写路径，也不在读接口里开 incident

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `workflow_auto_advance` 命中图快照异常时会打开正式 incident，并且同指纹不重复开单
- [x] incident detail / resolve 已补 `REBUILD_TICKET_GRAPH`，重建失败会 reject，不会静默关 breaker
- [x] 前端 `IncidentDrawer` 已补图故障说明和默认恢复动作

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P2-S2`
**名称：**  
`最小 RoleHook registry 与 required hook gate`

**现实问题：**  
`worker-preflight / worker-postrun / evidence-capture / git-closeout` 之前只是散点 receipt 和散点校验；源码票即使缺 hook 也没有统一 gate、正式 incident 和幂等 replay。`

**对应架构文档：**
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/06-role-hook-system.md`
- `doc/new-architecture/10-migration-map.md`

**实施边界：**
- 做什么：
  - [x] 新增最小 `RoleHook` protocol module，并让 gate evaluator 直接消费 registry
  - [x] 只把 `workspace-managed source_code_delivery` 接进 required hook gate，缺 hook 时显式打开 `REQUIRED_HOOK_GATE_BLOCKED`
  - [x] 新增 `REPLAY_REQUIRED_HOOKS` 幂等恢复动作，并让 `TicketGraph / workflow_auto_advance / IncidentDrawer` 读到统一 stop reason
- 不做什么：
  - [x] 不扩 governance / review / closeout 全票型
  - [x] 不新增完整 Hook Runner
  - [x] 不改 Worker prompt、结果 payload 或 `doc/new-architecture/**`

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `source_code_delivery` 缺 required hook receipt 时，gate 会给出结构化 `BLOCKED` 结果，`TicketGraph` 会显式落 `REQUIRED_HOOK_PENDING:*`
- [x] `workflow_auto_advance` 会给缺 hook 的源码票正式打开 `REQUIRED_HOOK_GATE_BLOCKED`，并按稳定指纹去重
- [x] `incident-resolve` 已支持 `REPLAY_REQUIRED_HOOKS`；缺失 receipt 可按持久化 terminal truth 幂等补写，前端 `IncidentDrawer` 已补说明和默认恢复动作

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P2-S5`
**名称：**  
`Provider 前置门禁、显式阻断与幂等解阻`

**现实问题：**  
`project-init -> node_ceo_architecture_brief` 在无 live provider 时会误走成普通执行失败，继续触发 retry / repeated failure / incident 噪音，既不符合 fail-closed，也不符合幂等审计。`

**对应架构文档：**
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/12-architecture-audit-report.md`

**实施边界：**
- 做什么：
  - [x] 给 scheduler dispatch 和 ticket start 补统一 provider precondition gate
  - [x] 新增 `TICKET_EXECUTION_PRECONDITION_BLOCKED / CLEARED`，把“无 live provider”显式写成 append-only 真相
  - [x] 给 ticket/node/graph/dashboard 接 `BLOCKING_REASON_PROVIDER_REQUIRED`
- 不做什么：
  - [x] 不新增新的 provider incident type
  - [x] 不改 `doc/new-architecture/**`
  - [x] 不顺手重做 scheduler_runner 的 legacy env-config provider 测试体系

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `project-init` 在无 live provider 时会写 `PRECONDITION_BLOCKED`，且不再产出 `TICKET_FAILED / TICKET_RETRY_SCHEDULED / REPEATED_FAILURE_ESCALATION`
- [x] provider 恢复后会写 `PRECONDITION_CLEARED`，同一阻断不会重复记事件
- [x] 3 条历史 API 噪音用例已转绿，provider incident 主链 API / autopilot 子集未回归

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P2-S6`
**名称：**  
`scheduler_runner provider recovery 历史测试收口`

**现实问题：**  
`scheduler_runner` 的 provider incident / recovery 历史测试还在沿旧 env-config / deterministic fallback 口径写断言；即使 `P2-S5` 主线已经收口，这组测试仍会把旧假设误报成主线回归。`

**对应架构文档：**
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/12-architecture-audit-report.md`

**实施边界：**
- 做什么：
  - [x] 给 `scheduler_runner` 测试补最小 provider center + target binding helper
  - [x] 把 provider auth / bad response / rate limit 相关断言收正到显式失败与 incident 真相
  - [x] 把 mainline recovery 测试从旧 `project-init -> MEETING_ESCALATION` 假设改成“先有 governance-first 前置，再测 provider 恢复”
- 不做什么：
  - [x] 不改 `run_ceo_shadow_for_trigger` 的异常 fallback 主链
  - [x] 不重做 scheduler / runtime / provider center
  - [x] 不顺手清扫全部历史测试桶

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "provider_incident or provider_recovery" -q` 通过（`5 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q` 通过（`3 passed, 8 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q` 通过（`3 passed, 284 deselected`）
- [x] `python3 -m py_compile backend/tests/test_scheduler_runner.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py` 通过

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P4-S1`
**名称：**  
`BoardAdvisorySession 最小合同与存储`

**现实问题：**  
`当前 board review 只有 approval 结果，没有正式顾问环真相；Review Room 能改 constraints，但系统里没有一等 advisory session 可追。`

**对应架构文档：**
- `doc/new-architecture/08-board-advisor-and-replanning.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/11-governance-profile-and-audit-modes.md`

**实施边界：**
- 做什么：
  - [x] 新增最小 `BoardAdvisorySession` 合同
  - [x] 给 repository / schema 补 advisory session 持久化和只读查询
  - [x] 让 `requires_constraint_patch_on_modify=true` 的 review pack 自动绑定单条 advisory session
- 不做什么：
  - [x] 不新开 advisory 页面
  - [x] 不补 graph patch engine
  - [x] 不补 `ProjectMap`

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] 新 advisory session 能自动创建
- [x] review room 已能读到 advisory 上下文
- [x] 相关 API 测试通过

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P4-S2`
**名称：**  
`顾问决策真相与治理档位 supersede`

**现实问题：**  
`MODIFY_CONSTRAINTS` 之前只会 resolve approval 并触发后续动作，没有正式顾问决策资产，也不会把治理档位变更收成 append-only 真相。`

**对应架构文档：**
- `doc/new-architecture/08-board-advisor-and-replanning.md`
- `doc/new-architecture/10-migration-map.md`
- `doc/new-architecture/11-governance-profile-and-audit-modes.md`

**实施边界：**
- 做什么：
  - [x] 给 `modify-constraints` 增加显式 advisory decision 链
  - [x] 新增 `DECISION_SUMMARY` 过程资产和 artifact 留痕
  - [x] 支持最小 `governance_patch(approval_mode / audit_mode)` 并 append-only supersede `GovernanceProfile`
- 不做什么：
  - [x] 不静默忽略非法 `governance_patch`
  - [x] 不新建独立 graph patch 结构
  - [x] 不顺手扩 `ProjectMap / GraphHealth`

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `MODIFY_CONSTRAINTS` 会写顾问决策真相和 `DECISION_SUMMARY`
- [x] 非法 `governance_patch` 会 fail-closed reject
- [x] 治理档位 supersede 和板审 idempotency 行为可验证

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`

**状态：** `done`

### 切片 `P4-S3`
**名称：**  
`CEO Snapshot / Review Room 顾问摘要接线`

**现实问题：**  
`就算 advisory 决策已经存在，CEO snapshot 和现有 Review Room 也看不到；系统仍可能继续按旧约束推进。`

**对应架构文档：**
- `doc/new-architecture/04-ceo-memory-model.md`
- `doc/new-architecture/08-board-advisor-and-replanning.md`
- `doc/new-architecture/10-migration-map.md`

**实施边界：**
- 做什么：
  - [x] 给 `ProjectionSnapshot` 补 `board_advisory_sessions[]`
  - [x] 给 `ReplanFocus` 补 `latest_advisory_decision`
  - [x] 给现有 `Review Room / ReviewRoomDrawer` 补 advisory 摘要和最小 governance patch 控件
- 不做什么：
  - [x] 不改 CEO hidden fallback 语义
  - [x] 不新开前端路由
  - [x] 不把 advisory 扩成通用项目地图

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] `ceo_shadow_snapshot` 能读到最新 advisory 决策
- [x] `ceo_prompts` 已显式消费 advisory 摘要
- [x] `ReviewRoomDrawer` 测试和 frontend build 通过

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/TODO.md`
- [x] 更新 `doc/history/memory-log.md`
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

### 切片 `P4-S5`
**名称：**  
`Placeholder Lifecycle 协议收口`

**现实问题：**  
`placeholder 已经进入 graph truth 和 runtime read/create path，但执行态 compile / start / result-submit 还会从 node_projection 缺失反向猜状态，错误不够显式。`

**对应架构文档：**
- `doc/new-architecture/02-ticket-graph-engine.md`
- `doc/new-architecture/03-worker-context-and-execution-package.md`
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`
- `doc/new-architecture/10-migration-map.md`

**实施边界：**
- 做什么：
  - [x] 新增单点 runtime node lifecycle gate 和 typed reason code
  - [x] 让 `ticket-create / CEO create-ticket` 统一走 lifecycle gate 判断 placeholder absorb 或 materialized reject
  - [x] 让 `context_compiler / ticket-start / ticket-result-submit` 命中 planned placeholder 时显式 fail-closed
- 不做什么：
  - [x] 不给 placeholder 增持久化 `node_projection`
  - [x] 不补 scheduler 自动 materialization
  - [x] 不顺手拆 runtime identity 或 graph/liveness policy

**代码任务：**
- [x] 任务 1
- [x] 任务 2
- [x] 任务 3

**验证：**
- [x] graph-only placeholder 仍不进入 ready 队列
- [x] `ticket-create` 仍可吸收 placeholder 并沿现有 `EVENT_TICKET_CREATED -> node_projection` 主链物化
- [x] compile / `ticket-start` / `ticket-result-submit` 命中 planned placeholder 时会显式暴露稳定 reason code

**文档更新：**
- [x] 更新本计划文档
- [x] 更新 `doc/history/memory-log.md`
- [x] `doc/TODO.md` 未更新，并在收尾说明原因
- [x] 如果没改 `README.md`，在收尾说明原因

**状态：** `done`

---

## 8. 任务清单核对区

每次阶段结束后，必须逐项核对，不允许跳过。

### 已完成
- [x] `P0-S1` 已完成：系统冷启动现在会在 `repository.initialize()` 幂等写入单条 `SYSTEM_INITIALIZED`，`project-init` 不再兼任系统初始化入口
- [x] `P0-S2` 已完成：最小版本协议骨架现已落地；process asset canonical ref 改成 versioned ref，compiled bundle / manifest / execution package 会追加版本与 supersede 链，`GovernanceProfile` 与 workflow graph version 也已有只读查询入口
- [x] `P0-S3` 已完成：主线写路径现在已有显式 optimistic guard；`ticket-start` 可拒绝 stale ticket/node projection version，`ticket-result-submit` 可拒绝 stale `compiled_execution_package` ref，compile meta 也会写入 `ticket_projection_version / node_projection_version / source_projection_version`
- [x] `P0-S4` 已完成：`active-worktree-index.md` 与 ticket dossier 核心视图现在会走共享 `Boardroom` materializer；文档头固定带 `view_kind / generated_at / source_projection_version / source_refs / stale_check_key`，`doc-impact.md` 只读 `worker-postrun` receipt，`git-closeout.md` 只读 checkout/git closeout 事实输入
- [x] `P1-S1` 已完成：`TicketGraph` 最小合同和 legacy adapter 已落地；`ceo_snapshot / workflow_controller` 现在会读正式图摘要，invalid legacy dependency 会显式 blocked，graph version 也已把 `WORKFLOW_CREATED` 算进正式事件序列
- [x] `P1-S2` 已完成：`TicketGraphIndexSummary` 现已补齐 `in_flight / critical_path / blocked_reasons`；`workflow_controller` 和 dashboard 主读面已开始复用同一套图索引
- [x] `P1-S3` 已完成：`Dependency Inspector` 现已改成直接消费 `TicketGraph` 边和索引，`dependency_ticket_ids[] / graph_summary` 已成为正式只读合同；dashboard 的 `blocked_node_ids` legacy fallback 已移除，图不可用时改成显式 `blocked_node_source=graph_unavailable`
- [x] `P2-S1` 已完成：`workflow_auto_advance` 命中 `build_ceo_shadow_snapshot()` 的图不可用异常时，现已打开正式 `TICKET_GRAPH_UNAVAILABLE` incident；incident detail / resolve 与 `IncidentDrawer` 已补 `REBUILD_TICKET_GRAPH`
- [x] `P2-S2` 已完成：`backend/app/core/role_hooks.py` 已把最小 hook registry、结构化 gate result、`REQUIRED_HOOK_GATE_BLOCKED` incident 和 `REPLAY_REQUIRED_HOOKS` recovery 收进单点协议；`TicketGraph / workflow_auto_advance / incident detail / resolve / IncidentDrawer` 已开始消费这条新主链
- [x] `P2-S3` 已完成：`structured_document_delivery` 现已接入正式 `RoleHook` gate；治理文档与 closeout 会写 `artifact-capture.json`，closeout 还会额外写 `documentation-sync.json`，`REPLAY_REQUIRED_HOOKS` 也已能按持久化 terminal truth 幂等重放这两类 receipt
- [x] `P2-S4` 已完成：`review_evidence` 票现在也已接入正式 `artifact_capture` gate；`delivery_check_report / ui_milestone_review / maker_checker_verdict` 缺 receipt 时会显式阻断下游，`REPLAY_REQUIRED_HOOKS` 也已支持按 terminal truth 幂等补回或 fail-closed reject
- [x] `P2-S5` 已完成：provider unavailable 现在会先写 `TICKET_EXECUTION_PRECONDITION_BLOCKED`、把 ticket/node 固定阻断到 `BLOCKING_REASON_PROVIDER_REQUIRED`，不再误走 `TICKET_FAILED -> TICKET_RETRY_SCHEDULED -> REPEATED_FAILURE_ESCALATION`；provider 恢复后会幂等写 `TICKET_EXECUTION_PRECONDITION_CLEARED`，同一阻断不会重复落事件
- [x] `P2-S6` 已完成：`scheduler_runner` 的 provider incident / recovery 历史测试现在已切到 provider center + explicit target binding 真相；auth / bad response / rate limit 断言不再把失败包装成 `COMPLETED`，mainline recovery 也不再假设 `project-init` 直接打开旧 scope approval
- [x] `P2-S7` 已完成：`run_ceo_shadow_for_trigger` 现在已经改成严格路径；显式 deterministic mode 继续保留，但 live provider 坏响应、非法 action batch 和执行失败不再隐式 fallback，而是落 `CEO_SHADOW_PIPELINE_FAILED` incident
- [x] `P2-S8` 已完成：`command / approval / ticket / idle maintenance` 直调入口现在统一走 `trigger_ceo_shadow_with_recovery()`；`incident-resolve` 新增 `RERUN_CEO_SHADOW`，API 稳定验证桶也已改成 `test_p2_ceo_shadow_incident_*`
- [x] `P3-S1` 已完成：`GovernanceProfile` 现在已补 `auto_approval_scope / expert_review_targets / audit_materialization_policy`，`project-init` 会稳定落默认治理档位；`CompileRequest / CompiledExecutionPackage` 已带 `governance_profile_ref`、`governance_mode_slice`、`task_frame`、`required_doc_surfaces` 与 `context_layer_summary`
- [x] `P3-S2` 已完成：`build_ceo_shadow_snapshot()` 现在会稳定产出 `projection_snapshot / replan_focus`；`ceo_prompts / proposer / validator / scheduler / workflow_controller` 已切到新读面，缺少新结构时直接显式失败，不再从旧顶层隐式兜底
- [x] `P3-S3` 已完成：新增最小 `skill_runtime`，当前已稳定解析 `implementation / review / debugging / planning_governance` 四类技能；未知 `forced_skill_ids` 或冲突组合会直接拒绝组包，执行包与执行卡片都会带 `skill_binding`
- [x] `P4-S1` 已完成：新增正式 `BoardAdvisorySession` 合同、schema 和 repository helper；凡是 `requires_constraint_patch_on_modify=true` 的 review pack，当前都会自动绑定单条 advisory session，并在 review-room 读面暴露 `advisory_context`
- [x] `P4-S2` 已完成：`MODIFY_CONSTRAINTS` 现在会显式写 advisory decision truth、`DECISION_SUMMARY` 过程资产和可选 `GovernanceProfile` supersede；非法 `governance_patch` 不再隐式忽略，而是直接 reject
- [x] `P4-S3` 已完成：`build_ceo_shadow_snapshot()` 现在会输出 `projection_snapshot.board_advisory_sessions[] / replan_focus.latest_advisory_decision`；`ceo_prompts` 已显式提示先读顾问决策，现有 `ReviewRoomDrawer` 也已补最小 governance patch 控件
- [x] `P4-S4` 已完成：`FAILURE_FINGERPRINT / PROJECT_MAP_SLICE` 已进入正式 `ProcessAsset` 合同和 resolver；`Context Compiler / CEO Snapshot / CEO prompt` 都已接入 workflow 地图切片和最近失败指纹
- [x] `P4-S4` 已完成：新增最小 `GraphHealthReport` 首版，只覆盖 `FANOUT_TOO_WIDE / CRITICAL_PATH_TOO_DEEP / PERSISTENT_FAILURE_ZONE` 三类规则；`workflow_auto_advance` 命中 `CRITICAL` 时会显式打开 `GRAPH_HEALTH_CRITICAL`
- [x] `P4-S4` 已完成第二批：`modify-constraints` 对 advisory review pack 现在只会显式进入 change flow，不再直接 resolve approval；`Review Room` 已切成 `进入变更流程 -> 草拟 / 发分析 -> 确认导入` 三段最小闭环
- [x] `P4-S4` 已完成第二批：新增正式 `GRAPH_PATCH_PROPOSAL / GRAPH_PATCH` 过程资产、`board-advisory-append-turn / board-advisory-request-analysis / board-advisory-apply-patch` 命令和 `EVENT_GRAPH_PATCH_APPLIED`；`approved_patch_ref` 现在只会指向真实 graph patch
- [x] `P4-S4` 已完成第二批：`TicketGraph` 现在会叠加 applied advisory patch 的 `freeze / unfreeze / focus`，`ceo_shadow_snapshot / Review Room` 也已暴露 `change_flow_status / latest_patch_proposal_ref / patched_graph_version / focus_node_ids`
- [x] `P4-S4` 已完成第三批：`audit_mode = FULL_TIMELINE` 的 advisory change flow 现在会把 transcript archive 物化到 `90-archive/transcripts/board-advisory/<session>/v<N>.json`，并同步写正式 `TIMELINE_INDEX` 资产；archive 版本只增不改
- [x] `P4-S4` 已完成第三批：`BoardAdvisorySession / Review Room / build_ceo_shadow_snapshot() / latest_advisory_decision` 现已补 `latest_timeline_index_ref / latest_transcript_archive_artifact_ref / timeline_archive_version_int`
- [x] `P4-S4` 已完成第三批：`FULL_TIMELINE` archive 写失败时，相关 advisory 命令现在会显式 `REJECTED` 并回滚事务，不再留下半写 session 状态
- [x] `P4-S4` 已完成第四批：`board-advisory-request-analysis` 现在会先创建独立 `BoardAdvisoryAnalysisRun`，把 `BoardAdvisorySession` 切到 `PENDING_ANALYSIS`，再在事务外跑 analysis harness；不再在 board command 事务里同步直算 proposal
- [x] `P4-S4` 已完成第四批：advisory analysis harness 现已朝 `CompiledExecutionPackage` 收口，固定只读 `DECISION_SUMMARY / PROJECT_MAP_SLICE / FAILURE_FINGERPRINT / TIMELINE_INDEX`，并显式区分 `DETERMINISTIC / LIVE_PROVIDER`；live 失败不再隐式回退 deterministic
- [x] `P4-S4` 已完成第四批：新增正式 `BOARD_ADVISORY_ANALYSIS_FAILED` incident 和 `RERUN_BOARD_ADVISORY_ANALYSIS` recovery；`Review Room / Incident Detail / IncidentDrawer` 现已暴露 pending / failed / rerun 主链，analysis trace 也会落正式 artifact
- [x] `P4-S4` 已完成第五批：`SOURCE_CODE_DELIVERY` 过程资产现已补 `source_paths / written_paths / module_paths / document_surfaces`；`ProjectMapSlice` 会逐票优先消费这层结构化真相，legacy / 非 workspace-managed 代码票只有在本票缺稳定路径时才回退到本票自己的 `allowed_write_set`
- [x] `P4-S4` 已完成第五批：`ProjectMapSlice` 已删除按 `artifact_index.logical_path` 扫全票路径的旧兼容，不再把 runtime JSON、日志或证据路径混成模块地图
- [x] `P4-S4` 已完成第五批：`GraphHealthReport` 已补第二批规则 `BOTTLENECK_DETECTED / ORPHAN_SUBGRAPH / FREEZE_SPREAD_TOO_WIDE`；`CRITICAL_PATH_TOO_DEEP` 现在也已改成正式 `PARENT_OF + DEPENDS_ON` DAG 口径
- [x] `P4-S4` 已完成第六批：`GraphHealthReport` 现已补第三批时间线规则 `GRAPH_THRASHING / READY_NODE_STALE`；前者只认真实 `GRAPH_PATCH_APPLIED` 事件，后者只认 ready ticket 的 `updated_at / timeout_sla_sec`
- [x] `P4-S4` 已完成第六批：`graph_health.py` 新增正式 `GraphHealthUnavailableError`；graph patch payload 非对象、patch node list 非 `list[str]`、ready ticket 缺 `updated_at / timeout_sla_sec` 时现在都会显式失败，不再静默跳过
- [x] `P4-S4` 已完成第六批：`resolve_workflow_graph_version()` 已删掉对完整事件 payload 转换的旧兼容依赖，改成只按 `workflow_id + event_type + sequence_no` 取最新 graph mutation，避免坏 payload 污染 graph version 真相
- [x] `P4-S4` 已完成第六批：`is_ticket_graph_unavailable_error()` 现已显式识别 `GraphHealthUnavailableError`；`workflow_auto_advance / trigger_ceo_shadow_with_recovery` 命中这类 graph health 坏时间线时会继续复用 `TICKET_GRAPH_UNAVAILABLE -> REBUILD_TICKET_GRAPH / RESTORE_ONLY`
- [x] `P4-S4` 已完成第七批：advisory analysis live gate 已从“只认员工 `provider_id`”的旧兼容推导，收口到“真实 board-approved architect + 正式 runtime provider 选路”；`role_binding / ceo_binding_inheritance / default_provider` 命中时都可进入 `LIVE_PROVIDER`
- [x] `P4-S4` 已完成第七批：`board_advisory_analysis.py` 现已补单点 `execution plan` helper；run 创建、compile worker binding 和 live 执行现在共用同一套 executor / provider selection 真相，不再各自二次猜测
- [x] `P4-S4` 已完成第七批：advisory analysis live mode 命中 `no real architect / no live provider selection / provider paused` 时现在都会显式失败，并继续走现有 `BOARD_ADVISORY_ANALYSIS_FAILED -> RERUN_BOARD_ADVISORY_ANALYSIS / RESTORE_ONLY` 幂等恢复链，不再隐式降回 deterministic
- [x] `P4-S4` 已完成第八批：`GraphPatchProposal / GraphPatch` 现已正式支持 `replacements / remove_node_ids / edge_additions / edge_removals`；`add_node` 没有再用旧兼容偷渡，当前会显式 reject
- [x] `P4-S4` 已完成第八批：新增单点 `graph_patch_reducer.py`；`TicketGraph / GraphHealth / apply-patch` 现在都只消费正式 `GRAPH_PATCH_APPLIED` 事件和不可变 artifact，不再从 session 内嵌 patch JSON 反推真相
- [x] `P4-S4` 已完成第八批：advisory patch v2 现已支持 `REPLACES / remove_node / add-remove edge` 的 reducer overlay、显式校验和失败拒绝；`GraphHealthReport` 的 `GRAPH_THRASHING` 也已纳入 replacement / edge delta 目标集
- [x] `P4-S4` 已完成第九批：`graph_health.py` 现已补第四批规则 `QUEUE_STARVATION / READY_BLOCKED_THRASHING / CROSS_VERSION_SLA_BREACH`；三条规则都只读现有 `events + graph_version + ticket/node projection.version/updated_at`
- [x] `P4-S4` 已完成第九批：`QUEUE_STARVATION` 与 `CROSS_VERSION_SLA_BREACH` 现在都会以正式 `CRITICAL` finding 进入现有 `GRAPH_HEALTH_CRITICAL -> RERUN_CEO_SHADOW / RESTORE_ONLY` incident 主链；`READY_BLOCKED_THRASHING` 当前只保留 `WARNING` 读面，不新开 incident
- [x] `P4-S4` 已完成第九批：这轮没有新增 graph health history 表、projection 或 process asset；旧的“从模糊 blocker 或当前快照猜历史”的兼容推导也没有回流，缺 `updated_at / timeout_sla_sec / version / 合法事件 payload` 时继续显式抛 `GraphHealthUnavailableError`
- [x] `P4-S4` 已完成第十批：新增单点 `graph_identity.py`，graph lane 身份现在有正式真相；普通执行票固定走 execution lane，`MAKER_CHECKER_REVIEW` 固定走 `runtime_node_id::review`，`MAKER_REWORK_FIX` 会回 execution lane 替换当前绑定 ticket
- [x] `P4-S4` 已完成第十批：`TicketGraph` 已删掉 ticket-derived `graph_node_id=ticket:<ticket_id>` 旧兼容；shared runtime `node_id` 的 maker/checker/rework 现在会显式拆成 execution / review 两条 graph lane，不再靠 inherited self-loop 跳过污染图真相
- [x] `P4-S4` 已完成第十批：`graph_patch_reducer / graph_health / GRAPH_HEALTH_CRITICAL incident / CEO snapshot` 已统一切到 graph identity；graph health finding 和 incident payload 现在都会额外带 `affected_graph_node_ids`，旧兼容读面 `affected_nodes` 继续只保留 runtime node id
- [x] `P4-S4` 已完成第十批：advisory patch 如果指到 synthetic review lane，现在会显式 `REJECTED`；`GraphIdentityResolutionError` 也已接进现有 `TICKET_GRAPH_UNAVAILABLE` 恢复链，不做隐式 fallback
- [x] `P4-S4` 已完成第十一批：`GraphPatchProposal / GraphPatch` 现已正式支持 `add_nodes[]`；`GraphPatchAddedNode` 已固定 `node_id / node_kind / deliverable_kind / role_hint / parent_node_id / dependency_node_ids[]`，`graph_patch_proposal` output schema 也已升到 `v2`
- [x] `P4-S4` 已完成第十一批：`graph_patch_reducer.py` 现已支持 graph-only placeholder node overlay；`add_node` 必须显式声明 parent/dependency，same-patch `edge_additions / edge_removals` 不能再拿来偷接 placeholder，坏 patch 继续显式失败并复用既有幂等恢复链
- [x] `P4-S4` 已完成第十一批：`TicketGraph` 现在会物化 `is_placeholder=true / node_status=PLANNED / ticket_id=null / runtime_node_id=null` 的 placeholder node；`ready / blocked / in_flight` 继续只统计 ticket-backed node，placeholder 不再伪造 ticket 绑定
- [x] `P4-S4` 已完成第十一批：历史 `add_node` 在真实 ticket 创建后现在会被 graph replay 显式吸收，不再把图重算炸成 `graph unavailable`；`GraphHealthReport` 的结构类规则也已纳入 placeholder，`affected_nodes` 不再回退到 placeholder `node_id` 伪装成 runtime node
- [x] `P4-S4` 已完成第十二批：`board_advisory_analysis.py` 现已改成 advisory execution contract 驱动；新增独立 `execution_target:board_advisory_analysis`，真人 executor 改按 capability tags 选，旧的 `architect_primary + architect_governance_document` 直绑已退出核心判断
- [x] `P4-S4` 已完成第十二批：advisory analysis 现在只在 advisory target 真正可解析时进入 `LIVE_PROVIDER`；命中 contract mismatch / selection missing / provider paused 时都会显式失败，并继续复用现有 `BOARD_ADVISORY_ANALYSIS_FAILED -> RERUN_BOARD_ADVISORY_ANALYSIS / RESTORE_ONLY`
- [x] `P4-S4` 已完成第十二批：`graph_identity.py` 现已改成 `graph_contract.lane_kind` 优先；maker-checker review / rework 建票路径会显式写入 `graph_contract`，旧 taxonomy 只保留在单点 legacy adapter，不再散落到图内核判断
- [x] `P4-S4` 已完成第十二批：新增 `backend/app/core/graph_health_policy.py`，`GraphHealth` 的 threshold / multiplier / timeline window / event whitelist / severity 现已集中配置；`build_graph_health_report()` 也已支持显式 `policy` 注入，graph health 内核回到“只读图、产出 finding”
- [x] `P4-S4` 已完成第十三批：`board_advisory_analysis` 主线现已改成 live-only success path；没有真实 board-approved contract-matching executor、没有 advisory target provider selection、或 provider paused 时都会显式失败，不再让 synthetic executor / deterministic proposal 从 command 主链伪成功
- [x] `P4-S4` 已完成第十三批：graph core 现已改成 contract-only lane resolution；`resolve_graph_lane_kind()` 只认 `graph_contract.lane_kind`，legacy maker-checker / rework taxonomy 已移到单点 compat adapter；新票会在建票路径补正式 execution lane contract
- [x] `P4-S4` 已完成第十三批：新增 `backend/app/core/runtime_liveness.py` 与 `RuntimeLivenessReport`；`QUEUE_STARVATION / READY_BLOCKED_THRASHING / READY_NODE_STALE / CROSS_VERSION_SLA_BREACH` 已从 `GraphHealthReport` 主读面后移到独立 liveness monitor，`ProjectionSnapshot / CEO prompt / workflow_auto_advance` 现在会同时读 `graph_health_report + runtime_liveness_report`
- [x] `P4-S4` 已完成第十三批：liveness incident 主链已拆开；结构类 critical 继续走 `GRAPH_HEALTH_CRITICAL`，liveness critical 改走 `RUNTIME_LIVENESS_CRITICAL`，liveness 构建失败改走 `RUNTIME_LIVENESS_UNAVAILABLE`，不再把 runtime timeline 坏数据伪装成 `GraphHealthUnavailableError -> TICKET_GRAPH_UNAVAILABLE`
- [x] `P4-S4` 已完成第十四批：新增单点 `backend/app/core/runtime_node_views.py`，把 execution-lane graph node、graph-only placeholder 和持久化 `node_projection` 收成显式 `materialized / planned_placeholder / missing` 三态读面；同一 `node_id` 命中 placeholder/materialized 冲突、或 graph/runtime 真相不一致时现在会显式抛 `RuntimeNodeViewResolutionError`
- [x] `P4-S4` 已完成第十四批：`Dependency Inspector` 现在会显式展示 graph-only placeholder；新字段固定补 `is_placeholder / materialization_state`，依赖链继续按 graph truth 读取 `PARENT_OF + DEPENDS_ON`，不再因为缺 `node_projection` 就把 placeholder 当成缺失节点或把 `None` 混进 ticket 依赖链
- [x] `P4-S4` 已完成第十四批：`ticket-create / CEO create-ticket` 的节点存在性判断现已切到 runtime node view；placeholder `node_id` 允许进入正式建票并由现有 `EVENT_TICKET_CREATED -> node_projection` 主链物化，已 materialized 节点继续显式 reject，执行态 `context_compiler / ticket-start / runtime / ticket-result-submit` 则继续只认真实 `node_projection`
- [x] `P4-S5` 已完成：新增单点 `backend/app/core/runtime_node_lifecycle.py`，把 placeholder lifecycle 收成正式 gate 和 typed reason code；命中 graph/runtime 真相冲突时不再静默猜状态
- [x] `P4-S5` 已完成：`context_compiler / ticket-start / ticket-result-submit` 现已显式拒绝 planned placeholder，稳定暴露 `PLANNED_PLACEHOLDER_NOT_MATERIALIZED`；本轮触达路径里原先直接拿 `node_projection` 缺失猜状态的旧兼容已经退出
- [x] `P4-S5` 已完成：`ticket-create / CEO create-ticket` 继续允许 absorb placeholder，但 scheduler tick 仍不会隐式 materialize graph-only placeholder；本轮最小回归已覆盖 create / compile / start / result-submit / scheduler 边界
- [x] `P4-S6` 已完成：新增 `backend/app/core/planned_placeholder_gate.py` 和正式 `PLANNED_PLACEHOLDER_GATE_BLOCKED` incident；autopilot 命中 focused planned placeholder 且本轮无推进时，现已显式开 incident，不再静默停住
- [x] `P4-S6` 已完成：`incident detail / incident-resolve / IncidentDrawer` 已接到这条新主链；新 incident 固定暴露 `RERUN_CEO_SHADOW + RESTORE_ONLY`，resolve 继续复用现有 CEO rerun，不新增 placeholder 专用恢复动作
- [x] `P4-S6` 已完成：autopilot 对 `PLANNED_PLACEHOLDER_GATE_BLOCKED` 不再做隐式 auto-resolve；graph-only placeholder 仍只存在于 graph truth，`ticket-create` 继续是唯一合法 materialization 入口
- [x] `P4-S6` 已完成第二批：新增独立 `planned_placeholder_projection` 持久化真相层；execution-lane graph-only placeholder 现在会稳定落库 `workflow_id / node_id / graph_node_id / graph_version / status / reason_code / open_incident_id / materialization_hint / updated_at / version`
- [x] `P4-S6` 已完成第二批：`runtime_node_views` 现在只认 `node_projection + planned_placeholder_projection`；graph 有 placeholder 但缺持久化 placeholder projection、或 placeholder projection 脱离 execution graph lane 时，会显式抛 `RuntimeNodeViewResolutionError`，不再靠缺 `node_projection` 猜 planned
- [x] `P4-S6` 已完成第二批：`Dependency Inspector / context compiler / ticket-start / ticket-result-submit / workflow_auto_advance` 已切到这层新真相；planned placeholder 命中 open incident 时会稳定变成 `BLOCKED`，真实 `ticket-create` 成功后 placeholder row 会被吸收删除
- [x] `P4-S6` 已完成第二批：本轮同时删掉了污染新架构真相的旧兼容推导：placeholder 不再从 `node_projection` 缺失、incident detail 或读面空值反向猜状态；graph/runtime/placeholder 真相不一致时统一 fail-closed
- [x] `P4-S6` 已完成第三批：placeholder materialization 边界现已正式钉死；`workflow_auto_advance` 开 placeholder gate incident、`incident-resolve` 走 `RERUN_CEO_SHADOW`、以及现有 scheduler/runtime 入口都不会偷偷创建 ticket 或把 planned placeholder 改写成 materialized，`ticket-create` 继续是唯一合法 materialization 入口
- [x] `P4-S6` 已完成第三批：`workflow_auto_advance` 现已新增 preflight blocker recover；autopilot 会先处理 open approval / open incident，再 build snapshot 和 health probe，generic board approval 的 `ceo_delegate` 自动收口、provider incident 的 `RESTORE_ONLY / RETRY` 恢复链现在不会再被旧 blocker 顺序卡死
- [x] `P4-S6` 已完成第三批：`TicketGraph` 已删掉 same-lane retry / replacement lineage 的 self `PARENT_OF` 边；同一 execution lane 的 retry 历史不再把 `GraphHealthReport` 打成 cyclic path
- [x] `P4-S6` 已完成第三批：测试时钟基座现已补齐到 `runtime_liveness / graph_health`；provider recovery 和 autopilot orchestration 的时间窗口回归现在按显式会话时间跑，不再夹带宿主机当前时间
- [x] `P4-S7` 已完成第一批：新增正式 `runtime_node_projection` 真相层和 reducer；execution lane 的 materialized runtime node 现在按 `workflow_id / graph_node_id / node_id / runtime_node_id / latest_ticket_id / status / blocking_reason_code / updated_at / version` 幂等重建
- [x] `P4-S7` 已完成第一批：`runtime_node_views / context_compiler / ticket-start / ticket-result-submit / runtime runner / Dependency Inspector / TicketGraph` 已切到 execution-lane runtime truth；旧的 execution-lane `node_projection` 缺失猜状态路径已移除
- [x] `P4-S7` 已完成第一批：`CompileRequestMeta / CompiledExecutionPackageMeta` 现已补 `runtime_node_projection_version`；`ticket-start` 和 `ticket-result-submit` 现在会显式拒绝 stale runtime node projection，不再从 legacy `node_projection` 缺失或 shared `node_id` 反推执行态真相
- [x] `P4-S7` 已完成第二批：`runtime_node_projection` 已扩到所有 materialized graph lane；maker-checker review 现在会稳定落 `graph_node_id=<runtime_node_id>::review` 的 runtime truth，不再让 review lane 借 shared `node_id` 混进 execution row
- [x] `P4-S7` 已完成第二批：`context_compiler / ticket-start / ticket-result-submit / ticket-complete / runtime runner` 已改成先解 `graph_identity` 再读 `runtime_node_projection`；review lane 现在也会显式校验 `runtime_node_projection_version`，缺 graph-lane runtime row 时统一 fail-closed
- [x] `P4-S7` 已完成第二批：review pack subject 已补正式 `source_graph_node_id`；`approval target` 和 `RuntimeLivenessReport` 已切到 graph-first runtime truth，旧的 `source_node_id + node_projection` 审批校验和 lane-backed liveness 猜测已退出主链
- [x] `P4-S7` 已完成第三批：`scan_and_open_required_hook_gate_incidents()` 已从 shared `node_projection.latest_ticket_id` 改成 graph-first `runtime_graph_node_views`；review lane 的 required hook gate 现在会按 `graph_node_id` 判断当前票，不再被 stale shared `node_id` 污染
- [x] `P4-S7` 已完成第三批：`graph_health_policy.py` 已删掉 runtime-liveness 阈值；新增正式 `backend/app/core/runtime_liveness_policy.py`，`build_runtime_liveness_report()` 现已只消费自己的 policy contract
- [x] `P4-S7` 已完成第三批：`graph_health.py` 已删掉会污染边界的 runtime-specific 死代码；图健康只保留结构类规则，运行态健康只留在 `runtime_liveness.py`
- [x] `P4-S7` 已完成第四批：`workflow_relationships.py` 已拆成展示快照和运行态关系解析两层；`resolve_runtime_org_context_relations()` 只读 `TicketGraphSnapshot + graph_identity + ticket_projection`，缺 graph truth 或 parent edge 不唯一时显式失败
- [x] `P4-S7` 已完成第四批：`context_compiler._build_org_context()` 已切到 graph-first relation resolver；upstream / sibling / downstream reviewer 不再按 `parent_ticket_id + shared node_id` 拼关系，open review pack 也改成只按 `source_graph_node_id / source_ticket_id` 主判
- [x] `P4-S7` 已完成第四批：`backend/tests/test_role_hooks.py` 旧 helper 已收成显式 harness；create / lease / start / submit 都断言 `ACCEPTED`，删 receipt 前先确认 receipt 真落盘，整桶 `test_role_hooks.py -q` 已恢复全绿
- [x] `P4-S7` 已完成第五批：新增 `backend/app/core/review_subjects.py`，把 review / meeting / advisory 读面 subject 解析收成 graph-first 主判；`source_graph_node_id` 优先，旧 `source_node_id` 只保留为受控兼容展示字段，不再驱动 dependency inspector 的 open approval 命中
- [x] `P4-S7` 已完成第五批：`MeetingDetailProjectionData` 和前端 `MeetingDetailData` 现已显式暴露 `source_graph_node_id`，`MeetingRoomDrawer` 优先展示 graph node；meeting detail 不再把 `source_node_id` 当唯一来源真相
- [x] `P4-S7` 已完成第五批：`approval_handlers` 的 board review projection guard 和 advisory artifact subject 解析已优先走 graph-first subject resolver；事件和 artifact 写入仍保留 `source_node_id` 兼容字段，不在本轮改写 command / event 合同
- [x] `P4-S7` 已完成第六批：`meeting-request` 现在会显式给 meeting ticket 写入 `graph_contract={"lane_kind":"execution"}`；`MEETING_REQUESTED / MEETING_STARTED` 事件和 `meeting_projection` 也已同步持久化 `source_graph_node_id`，meeting 主链不再因缺 lane contract 在 reducer 阶段崩溃
- [x] `P4-S7` 已完成第六批：`build_meeting_projection()`、CEO recent closed meeting reuse candidate 和 meeting 相关读面现在会优先消费持久化 `source_graph_node_id`；`resolve_review_subject_identity()` 已删掉“source_ticket_id 解不出 graph identity 就回退 source_node_id”的旧兼容推导，缺 graph truth 时统一显式失败
- [x] `P4-S7` 已完成第六批：meeting-backed `consensus_document` 票现在会显式跳过 provider precondition gate，继续走本地 deterministic meeting runtime；`approval_handlers` 里的 board-approved scope/meeting follow-up 建票入口也已补正式 `graph_contract`，不再留旧 router 漏口
- [x] `P4-S7` 已完成第七批：`workflow_relationships.list_workflow_ticket_snapshots()` 现已改成 graph-first 展示快照；只读 `TicketGraphSnapshot + ticket_projection + ticket-create payload`，不再从 legacy `node_projection` 缺口反向猜 `phase / parent / node_status`
- [x] `P4-S7` 已完成第七批：dashboard `pipeline_summary` 和 dependency inspector 节点展示已改成 graph/runtime truth 主判；phase 汇总现在只读 `ticket_projection` 运行态真相，blocked / critical-path 继续复用 `TicketGraph` 索引，不再让 stale `node_projection` 改写展示状态
- [x] `P4-S7` 已完成第七批：`resolve_review_subject_identity()` 已删掉 `source_node_id` 单独成真相的旧兼容；dependency inspector 的 open approval 命中现在只按 `source_graph_node_id`，缺 graph truth 时显式失败；CEO recent closed meeting reuse candidate 也不再回退 `source_node_id`
- [x] `P4-S7` 已完成第八批：`ceo_snapshot` 的 recent completed reuse candidate 现已改成 graph-first；`consensus_document` 的复用 gate 不再依赖 legacy `node_projection.status`，stale 或缺失的 compat row 不再误伤复用候选
- [x] `P4-S7` 已完成第八批：`ceo_meeting_policy / ceo_validator / CEORequestMeetingPayload` 现已补正式 `source_graph_node_id`；meeting candidate、shadow/live `REQUEST_MEETING` 校验和 graph truth 存在性判断都已改成 `source_ticket_id + source_graph_node_id` 主判，`source_node_id` 只保留展示兼容
- [x] `P4-S7` 已完成第八批：`workflow_autopilot._workflow_closeout_state()` 和 `workflow_controller` 的 closeout completion 判定已切到 `TicketGraphSnapshot.node_status`；workflow chain report / controller closeout gate 不再因 stale `node_projection` 误判未完成
- [x] `P4-S7` 已完成第九批：`workflow_controller` 的 governance progression / architect gate / backlog followup existing-ticket 判断现已优先读 `ticket_projection` 当前真相；`required_governance_ticket_plan.existing_ticket_id` 不再依赖 legacy `workflow_nodes.latest_ticket_id`
- [x] `P4-S7` 已完成第九批：`ceo_proposer._build_backlog_followup_batch()` 现已直接复用 `capability_plan.followup_ticket_plans[].existing_ticket_id` 作为 fanout 依赖真相；上游 followup 的 legacy `node_projection` 缺失时，不再把下游依赖错判成“尚未存在”
- [x] `P4-S7` 已完成第九批：autopilot closeout deterministic fallback 已删掉对 `node_ceo_delivery_closeout` 的 legacy `node_projection` existence guard；没有真实 closeout ticket 时，stale compat row 不再误挡 closeout batch
- [x] `P4-S7` 已完成第九批：controller 生成的 implementation-boundary meeting candidate 现已补正式 `source_graph_node_id`，deterministic `REQUEST_MEETING` 不再因为 command-side candidate 缺 graph subject 而在 proposer 阶段崩掉
- [x] `P4-S7` 已完成第十批：新增单点 execution-target resolver，`review_subjects` 现在会把 review lane `source_graph_node_id` 显式映射到 execution lane target；board advisory session 不再把 stale `source_node_id` 当 affected node 真相
- [x] `P4-S7` 已完成第十批：`approval_handlers / board_advisory_analysis` 现已统一复用这条 graph-first execution target；advisory change flow、analysis trace/archive、incident 和 patch artifact 不再靠 legacy `source_node_id` 反向猜 execution branch
- [x] `P4-S7` 已完成第十批：advisory analysis synthetic compile spec 已补正式 `graph_contract={"lane_kind":"execution"}`，`org_context` 现在按 source execution ticket 组包；缺 graph truth 时继续显式失败，不新增 fallback

### 未完成
- [ ] `P4-S6` 已把 placeholder 收成独立持久化 `planned_placeholder_projection` 真相，但仍没有进入持久化 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] review pack / advisory / meeting 写入载荷现在仍同时带 `source_node_id + source_graph_node_id`；读面主判已切到 graph-first，但彻底把 command / event payload 改成 graph-only 需要单独切片
- [ ] dashboard phase 汇总这轮已收成 graph/runtime truth；如果后续产品还想显示“更高层的阶段完成感”，必须单独定义正式 stage projection，不能再把旧 `node_projection` 推断逻辑塞回 dashboard

### 明确放弃
- [ ] 暂无

### 新发现但不在本轮做
- [ ] `backend/tests/test_api.py -k "system_initialized or startup or project_init"` 仍会命中一组依赖 live provider 的旧 `project-init` 自动推进用例；当前环境未配 provider 时会落 `PROVIDER_REQUIRED_UNAVAILABLE`，不阻断 `P0-S1` 收口
- [ ] `compiled_context_bundle / compile_manifest` 的版本 ref 这轮已落库并进入 persisted payload，但 dashboard / review 读面还没显式消费；后续按 `P0-S4 / P1` 再接正式读面
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "delivery_check_report or ui_milestone_review or maker_checker_verdict" -q` 本轮按计划原样补跑时命中 `286 deselected`；当前仓库没有直接按 schema 名命名的 API 用例，本轮已改用精确链路用例 `test_review_evidence_missing_required_hook_keeps_dependency_gate_blocked` 做同口径验证
- [ ] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "ceo_shadow" -q` 当前会返回 `51 deselected`；本轮已改用显式 `idle_ceo_maintenance_*` 桶做非空跑验证，后续如果要恢复聚合桶，需要单独整理命名
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_role_hooks.py -q` 的旧 helper 假设已在 `P4-S7` 第四批清理：测试现在显式补 provider 前置、断言命令 `ACCEPTED`、确认 receipt 真存在后再删，整桶已通过
- [ ] synthetic manual `scope review -> build/check/review -> closeout` 链当前不会自动产出 dashboard `completion_summary`；这类 summary 继续由 autopilot / closeout 专项测试覆盖，不把这条手工链写成已完成 workflow 真相
- [ ] placeholder node 当前已进入 runtime read/create path，但仍只支持 execution lane；同一 patch 里的 placeholder-to-placeholder 接线、review lane placeholder、scheduler 自动 materialization 和持久化 `node_projection` 真相仍未支持，后续若要补必须单独开切片
- [ ] `GraphHealthReport` 第四批现已锁成“只读 `events + graph_version + ticket/node projection.version/updated_at`”；如果后续要补 dedicated history 或 workflow 级 SLA，必须单独开切片，不能在现有规则里偷偷落新真相层
- [ ] `READY_BLOCKED_THRASHING` 这轮只按最近 `24` 条显式事件窗口做 `WARNING` 检测；如果后续要做更细的 blocker-source 分层、跨窗口趋势分析或自动升级 incident，必须单独扩正式规则，不回退到当前快照猜历史
- [ ] advisory analysis live gate 现已锁成“真实 board-approved architect + 正式 runtime provider 选路”；synthetic architect 即使存在 binding / default provider 也保持 `DETERMINISTIC`，后续不要再回退到 `employee.provider_id` 兼容口径
- [ ] graph layer 这轮已完成 execution / review 双 lane identity；如果后续要继续拆 runtime `node_projection`、approval target 和 worker runtime 到 graph-first 双层真相，必须单独开切片，不能在现有 `P4-S4` 图层收口里偷渡
- [ ] `graph_health_policy.py` 这轮虽然已经把策略常量抽离出内核，但 `QUEUE_STARVATION / READY_NODE_STALE / CROSS_VERSION_SLA_BREACH` 仍继续读取 runtime ticket/node projection 的时间与 SLA 字段；如果下一轮还要继续瘦 graph 内核，应优先决定这批 runtime-liveness 规则是否拆到独立监视层
- [ ] `CEORequestMeetingPayload` 这轮已补正式 `source_graph_node_id`；如果后续还要把 board/advisory/meeting 全链统一成 graph-only subject，必须单独清 `meeting-request` 命令、event payload 和 artifact subject 里的 `source_node_id` 双写兼容，不能在现有切片里偷渡删除字段
- [ ] `RuntimeLivenessReport` 这轮已经从 `GraphHealthReport` 主读面拆出，但 `graph_health_policy.py` 仍同时承载 graph + liveness 两类阈值；如果下一轮继续瘦监视层，应先决定 policy contract 是否也跟着拆层，避免新 monitor 再长回 policy bucket
- [ ] `P4-S5` 这轮只把 lifecycle gate 收硬，没有给 planned placeholder 新增 incident / recovery 动作；后续如果自动路径还要显式暴露“先建票再继续”，必须单独决定是复用现有 command reject，还是新增正式恢复动作
- [ ] `planned_placeholder_projection` 当前故意只读 `graph patch events + node_projection + open placeholder incident`；还没有把 review-lane placeholder、patch edge delta 结构真相或 dedicated placeholder history 拉进持久化层，后续若要补必须单独开切片，不回退到 runtime/node 缺失猜状态
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "provider_incident_resolve or placeholder_gate_incident_resolve" -q` 这轮按计划补跑时，`test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure` 会先撞到老的 `wf_seed` 建链缺口：helper 在 workflow 真相未建好前直接 create ticket；当前改动没有去扩这条旧测试入口，本轮已改用精确用例和 scheduler/autopilot 回归验证 provider restore 主链
- [ ] `backend/tests/test_meeting_room.py::test_meeting_projection_backfills_review_pack_after_checker_approval` 这轮为了只验证 meeting review-pack 回填主链，补了最小 fake live provider 配置来满足 checker 票租约前置；当前没有把“无 provider 时人工 checker API 是否仍应被 provider gate 阻断”纳入产品决策，后续若要改要单独开切片
- [ ] dashboard phase 汇总这轮按 graph/runtime truth 收口后，`scope approval` 场景会显式看到后续 `build/check/review` 票仍处于 `PENDING`；如果后续要给 dashboard 单独展示“阶段完成感”或“业务里程碑感”，必须新建立法，不回退到 `node_projection` 或 checker verdict 的隐式推断
- [ ] `py -m pytest backend/tests/test_ceo_scheduler.py -q` 在本轮相关用例已转绿后，仍会有 3 条 advisory analysis 历史用例卡在旧口子：`board-advisory-request-analysis` 当前会把 session 落成 `ANALYSIS_REJECTED`，导致 `latest_patch_proposal_ref=None`，后续 `board-advisory-apply-patch` 直接 422；这条链当前看起来不属于本轮 `P4-S7` command-side helper 收口，先记到后续单独切片
- [ ] `py -m pytest backend/tests/test_api.py -k "board_advisory_request_analysis or board_advisory_apply_patch or advisory_context" -q` 这轮补跑后仍有 5 条 advisory analysis 历史测试失败：其中 4 条 success-path 用例还停在旧的 analysis harness 假设，没有按当前 live-only advisory execution contract 补 worker/provider/mocked provider；另有 1 条 `test_board_advisory_apply_patch_rejects_synthetic_review_lane_targets` 缺失 `monkeypatch` fixture 参数。这组失败不属于本轮 `P4-S7` graph-first subject 主链

---

## 9. 偏差与待决策

这里只记录两类东西：

1. 架构文档和代码现实不一致
2. 实施中发现必须补一个新决策，否则不能继续

### D-001
**现象：**  
`SYSTEM_INITIALIZED` 原先只在 `project-init` 命令里写入；应用冷启动只建表和回填，不写独立的系统初始化真相。`

**影响：**  
`系统启动和首个 workflow 创建被绑死；空态 dashboard / 事件流无法表达“系统已完成 bootstrap”，legacy 初始化顺序也会和 workflow 事件混在一起。`

**当前处理：**  
`已保守收口到 repository 级幂等 bootstrap：repository.initialize() 统一写单条 SYSTEM_INITIALIZED，project-init 回到纯 workflow 启动。`

### D-004
**现象：**  
`runtime truth` 原先只覆盖 execution lane，maker-checker review、approval target 和 worker runtime 一度继续依赖 legacy `node_projection`。

**影响：**  
如果 review lane、approval target 和 worker runtime 继续混用 shared `node_id`，图身份和运行时身份就会重新糊回一层，后面会逼出更多隐式 fallback。

**当前处理：**  
`已在 2026-04-17 收口：review lane runtime truth、approval target、runtime runner 和 runtime liveness 现已统一切到 graph-first runtime_node_projection；保留下来的 legacy node_projection 只剩部分兼容读面，不再承担 review/runtime 主校验。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-005
**现象：**
`BoardAdvisorySession.affected_nodes` 和 advisory analysis subject 之前仍直接吃 review pack 里的 legacy \`source_node_id\`；当 review pack subject 已经带正式 \`source_graph_node_id=node::<review>\` 时，这条旧兼容会把 runtime node 当成 graph patch target 真相。`

**影响：**
`advisory change flow / analysis / patch artifact / incident` 会混用 review lane graph id、execution lane graph id 和 stale runtime node，既污染新架构真相，也会把 graph patch 校验误打成 `ANALYSIS_REJECTED`。`

**当前处理：**
`已在 2026-04-18 收口：review/advisory 单点 resolver 现在会把 review lane \`source_graph_node_id\` 显式映射到 execution lane target；board advisory session affected_nodes、artifact subject 和 advisory analysis 主链都已切到这条 graph-first execution target。`

**是否需要改架构文档：**
`no`

**状态：** `closed`

### D-006
**现象：**
`board_advisory_analysis` 的 synthetic compile request 之前没有正式 `graph_contract.lane_kind`，而且 `org_context` 直接拿 synthetic advisory-analysis ticket 组包。`

**影响：**
`CompiledExecutionPackage` 主链会命中新架构的显式 graph/runtime 门禁，把 advisory analysis 打成 `ANALYSIS_REJECTED`；这不是 provider fallback 问题，而是 synthetic compile contract 不完整。`

**当前处理：**
`已在 2026-04-18 先按最小口径补齐：synthetic compile spec 现在显式写 `graph_contract={"lane_kind":"execution"}`，`org_context` 改按 source execution ticket 组包，不新增 fallback。`

**是否需要改架构文档：**
`no`

**状态：** `closed`

### D-002
**现象：**  
`当前 external command 调用仍允许省略 expected version / compiled execution package ref；本轮只把这组字段强接进主线 runtime 自发命令和显式新测试入口。`

**影响：**  
`主线已经开始沿统一协议收口，但对外命令面暂时还保留兼容入口；后续如果要把 stale guard 升成全量硬约束，还要单独清一轮旧调用方。`

**当前处理：**  
`repository / handler / runtime 主链已经统一到 optimistic guard；兼容入口暂时保留，避免这一轮把历史测试和冻结兼容面一起炸开。`

**是否需要改架构文档：**  
`no`

**状态：** `open`

### D-003
**现象：**  
`当前 legacy maker-checker 流里，maker 和 checker 仍可能共用同一个 node_id；为了先把 REVIEWS 边正规化，这轮 TicketGraph 先用 ticket 级 graph_node_id 承载边，再把原 node_id 作为显式字段保留。`

**影响：**  
`P1-S1 已经能稳定归约 REVIEWS，但 P1-S2 往后如果要把 controller / dashboard 全面改成消费图索引，还要继续决定“逻辑 node”和“ticket graph node”各自的长期边界。`

**当前处理：**  
`本轮先锁 ticket 级 graph_node_id + 原 node_id 双字段合同；上层只允许读 TicketGraph 协议，不允许继续直拼 legacy node/ticket 语义。`

**是否需要改架构文档：**  
`no`

**状态：** `open`

### D-004
**现象：**  
`dashboard` 的 `blocked_node_ids / blocked_nodes` 这轮已经优先读取 active workflow 的 `TicketGraph` 索引；但为了不把现有 workspace 级 blocked 读面直接打断，当 active graph 没给出 blocked node 时，dashboard 仍保留了一层 legacy blocked-node 兼容回退。`

**影响：**  
`P1-S2` 已经把 controller 和 dashboard 主读面拉到正式图索引上，但 dashboard 还没完全达到“只认图真相”的纯口径；后续 `P1-S3` 需要先决定 active workflow / blocked scope 的正式边界，再移除这层兼容逻辑。`

**当前处理：**  
`已在 P2-S1 收口：dashboard 继续保持只读显式状态 \`blocked_node_source=graph_unavailable\`；真正的 incident / recovery 主链改由 \`workflow_auto_advance -> TICKET_GRAPH_UNAVAILABLE -> REBUILD_TICKET_GRAPH\` 接管，不再补第二套 projection fallback。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-005
**现象：**  
`P1 已完成，但主计划正文里还没有展开 \`P2-S1\` 及后续切片；按本轮文档限制，不能顺手重排结构或新开大段正文。`

**影响：**  
`本轮可以把顶部当前阶段切到 \`P2\`，但下一轮正式进入恢复与 Hook 收口前，还要先把 P2 首个切片正文补进主计划，否则续跑入口不完整。`

**当前处理：**  
`P2-S1 正文、本轮验证和运行文档同步已补齐；后续继续从 \`P2-S2\` 起手。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-006
**现象：**  
`project-init` workflow 仍会在部分历史 API 回归里额外带出旧的 governance/provider auto-advance incident，导致 incident / blocked_reason 宽口径测试桶会多出一条和当前源码票无关的 `node_ceo_architecture_brief` 噪音。`

**影响：**  
`P2-S2` 的 required hook gate 主链本身已可验证，但当回归桶直接按“当前 workflow 的 open incident 数量 / fused 节点数”做强断言时，会被这条旧噪音打断。`

**当前处理：**  
`已在 P2-S5 收口：provider unavailable 现在会先写 `TICKET_EXECUTION_PRECONDITION_BLOCKED`、把 ticket/node 固定阻断到 `BLOCKING_REASON_PROVIDER_REQUIRED`，不再误走 `TICKET_FAILED / TICKET_RETRY_SCHEDULED / REPEATED_FAILURE_ESCALATION`；对应 3 条 API 历史噪音用例本轮已转绿。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-008
**现象：**  
`P2-S4` 计划里沿用了 \`./backend/.venv/bin/pytest backend/tests/test_api.py -k "delivery_check_report or ui_milestone_review or maker_checker_verdict" -q\` 这条宽匹配命令，但当前 `backend/tests/test_api.py` 里没有直接按 schema 名命名的 API 用例，原样补跑只会返回 \`286 deselected\`。`

**影响：**  
`如果后续会话照抄这条命令，会误以为“API 桶通过”，但其实没有真正执行到任何断言；这会让 review_evidence hook gate 的验证口径失真。`

**当前处理：**  
`本轮保持 fail-closed，不把 0 selected 当通过；已改用精确链路用例 \`test_review_evidence_missing_required_hook_keeps_dependency_gate_blocked\` 补齐 API 验证，后续如果要恢复宽桶，需要单独整理命名或补聚合用例。`

**是否需要改架构文档：**  
`no`

**状态：** `open`

### D-011
**现象：**  
`synthetic manual scope-followup 链在显式跑完 build/check/review/closeout maker-checker 后，closeout ticket 与 checker 都能完成，但 dashboard \`completion_summary\` 仍不会自动物化。`

**影响：**  
`closeout / approval 历史测试如果继续把这条手工链写成“workflow 已完成 + dashboard completion summary 必有”，就会逼实现去补隐式 fallback，和当前 fail-visible 主线冲突。`

**当前处理：**  
`本轮已把相关历史测试改成显式断言 ticket/node/artifact/process-asset 真相；dashboard completion summary 继续只在 autopilot / closeout 专项测试里覆盖，不把这条 synthetic chain 写成 workflow 完成真相。`

**是否需要改架构文档：**  
`no`

**状态：** `open`

### D-007
**现象：**  
`P2-S3` 已把治理文档和 closeout 接进正式 hook gate，但当前计划正文还没有单列 `P2-S4`；如果下一轮直接继续扩 review evidence 或 runtime/provider 恢复路径，续跑入口会只剩“当前快照”里的短说明。`

**影响：**  
`P2` 阶段还没结束，但主计划正文里当前只展开到 `P2-S3`；下一轮如果不先锁定 `P2-S4` 的边界，容易把 review evidence 收口和旧 runtime/provider 噪音清理混成同一轮。`

**当前处理：**  
`本轮先把顶部当前切片切到 \`P2-S4\`，并在“未完成”“当前快照”里明确下一轮先收 \`review_evidence\` gate，继续把 runtime/provider 老 incident 噪音留在独立未完成项。`

**是否需要改架构文档：**  
`no`

**状态：** `open`

### D-009
**现象：**  
`scheduler_runner` 的 provider recovery 历史测试此前沿用旧 env-config / deterministic fallback 口径，没有切到当前 provider center + target binding 真相。`

**影响：**  
`如果继续保留旧断言，这组测试会把“显式失败 + incident + recovery”误报成回归，反过来驱动代码去兼容旧假成功语义。`

**当前处理：**  
`已在 P2-S6 收口：helper 现在会补最小 provider center + target binding；5 条 provider incident / recovery 历史测试已转绿，并且断言口径已经改成显式失败与幂等恢复真相。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-010
**现象：**  
`如果把 \`EVENT_INCIDENT_RECOVERY_STARTED\` 的 CEO 审计触发也强接到新的 incident helper，provider recovery 的 autopilot 主链会在恢复中途再打开一条 \`CEO_SHADOW_PIPELINE_FAILED\`，把原本已经进入 RECOVERING 的 incident 主链二次打断。`

**影响：**  
`本轮要收的是 command / approval / ticket / idle maintenance 这些直调入口；如果连 recovery-start 审计也一起 incident 化，会把“审计附加动作”和“主恢复动作”重新耦合，反而破坏当前 runtime/provider 恢复闭环。`

**当前处理：**  
`本轮只把四类直调入口统一到 \`trigger_ceo_shadow_with_recovery()\`；\`EVENT_INCIDENT_RECOVERY_STARTED\` 继续保留 audit-only 的 best-effort shadow append，不再额外开第二层 incident。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-012
**现象：**  
`架构文档里的 \`approved_patch_ref\` 指向最终 graph patch；但这轮最小闭环里，\`BoardAdvisorySession.approved_patch_ref\` 先指向了 \`DECISION_SUMMARY\` 过程资产，由 CEO rerun 消费结构化决策，而不是独立 graph patch engine。`

**影响：**  
`P4` 第一批已经有了可审计的顾问决策真相，也能 fail-closed 地影响下一次 CEO 运行；但它还没有把“Board 决策 -> 正式 graph patch -> 新 graph_version”这段补齐。后续如果直接把这层写成“graph patch 已上线”，会误导下一轮实现判断。`

**当前处理：**  
`已在 2026-04-16 收口：advisory flow 现已补正式 \`GRAPH_PATCH_PROPOSAL / GRAPH_PATCH\` 资产、显式评估 / 导入路由和 \`EVENT_GRAPH_PATCH_APPLIED\`；\`approved_patch_ref\` 不再指向 \`DECISION_SUMMARY\`。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-014
**现象：**  
`advisory change flow 这轮已经有显式 drafting / analysis / apply 主链，但 \`audit_mode = FULL_TIMELINE\` 时要求的内部 transcript archive 还没物化到 \`90-archive/transcripts\`。`

**影响：**  
`如果不补 archive，\`FULL_TIMELINE\` 会只剩“声明支持”，达不到不可变时间线归档和 audit replay 的口径。`

**当前处理：**  
`已补正式 transcript archive / TIMELINE_INDEX 闭环：archive 会按 advisory change flow 的状态点物化到 \`90-archive/transcripts\`，session / review room / ceo snapshot 也已暴露最新 archive refs；archive 写失败时命令显式 reject 并回滚。`

**是否需要改架构文档：**  
`no`

**状态：** `closed`

### D-013
**现象：**
`legacy / 非 workspace-managed source_code_delivery` 的 terminal truth 对 `module_paths / documentation_updates` 还没有 workspace-managed 路径那样稳定；同一份结构化信息当前会分散在 ticket payload、source delivery asset 和 allowed write set。`

**影响：**
`P4-S4` 第一批虽然已经把 `ProjectMapSlice` 收成正式资产，但 legacy 代码票的地图切片精度仍弱于 workspace-managed 主链；如果后续直接把这层写成“所有代码票都已有同精度地图”，会误导实现判断。`

**当前处理：**
`已按 fail-closed 收口：`SOURCE_CODE_DELIVERY` 过程资产现在会稳定写 `source_paths / written_paths / module_paths / document_surfaces`，`ProjectMapSlice` 逐票优先消费这层真相；只有本票完全缺稳定路径时，才退回本票自己的 `allowed_write_set`，且已删除 `artifact_index.logical_path` 扫描这条污染地图的旧兼容。`

**是否需要改架构文档：**
`no`

**状态：** `closed`

### D-015
**现象：**
`advisory analysis` 的 live mode 之前只认 board-approved architect 员工卡上的显式 `provider_id`；即使 runtime provider center 已经给 `architect` target、CEO 继承链或 default provider 配好了 live provider，这条分析链也会被硬压回 deterministic。`

**影响：**
`P4-S4` 的 advisory analysis 虽然已经有正式 `CompiledExecutionPackage` 和 incident / recovery 主链，但 live provider 入口被旧兼容字段绑死；这会让 provider center 真相和 advisory analysis 真相分叉，也会把 “provider paused / selection missing” 这类运行时问题继续伪装成 deterministic 成功。`

**当前处理：**
`已在 2026-04-16 收口：advisory analysis live gate 现已改成“真实 board-approved architect + 正式 runtime provider 选路”；run 创建、compile worker binding 和 live 执行共用单点 execution plan helper；synthetic architect 不再解锁 live，live 命中 no real architect / no selection / provider paused 时也会显式失败并继续走现有幂等 incident / recovery。`

**是否需要改架构文档：**
`no`

**状态：** `closed`

### D-017
**现象：**
`graph_health.py` 这轮虽然已把 policy 常量外提到 `graph_health_policy.py`，但 `QUEUE_STARVATION / READY_NODE_STALE / CROSS_VERSION_SLA_BREACH` 仍直接读取 runtime ticket/node projection 的 `updated_at / timeout_sla_sec / version`。`

**影响：**
`GraphHealth` 当前已经比之前更薄，但还没有完全退回“纯图结构读面”；如果后续继续把更多 scheduler / SLA 语义塞回这里，会再次把 graph 内核拉成 policy + runtime 混合层。`

**当前处理：**
`已在 2026-04-16 收口：这批 runtime-liveness 规则现已后移到新的 `RuntimeLivenessReport`，`GraphHealthReport` 主读面回到结构类 finding；liveness critical / unavailable 也已拆成独立 incident 类型。当前仍复用 `graph_health_policy.py` 承载两类阈值，是否继续拆 policy 合同留到后续单独决策。`

**是否需要改架构文档：**
`no`

**状态：** `closed`

### D-018
**现象：**
`doc/new-architecture/14-graph-health-monitor.md` 仍把 queue / stale / cross-version 这类 runtime-liveness 规则写在 `GraphHealthMonitor` 名下；但当前代码现实已经把它们后移到独立 `RuntimeLivenessReport`。`

**影响：**
`如果后续会话继续照架构稿把 scheduler / SLA 语义塞回 `graph_health.py`，会把这轮刚拆开的监视层边界重新混回去。`

**当前处理：**
`这轮只改实现和运行文档，不改 `doc/new-architecture/**`；已把这个偏差显式记到主计划，后续若要改架构稿，单独走决策流程。`

**是否需要改架构文档：**
`yes`

**状态：** `open`

### D-016
**现象：**
`maker / checker` 当前仍会把多张 ticket 收到同一个 `node_id`，所以把图按 node 视角归约时，会出现 inherited `DEPENDS_ON self-loop`。`

**影响：**
`graph patch reducer` 和 `GraphHealthReport` 不能把这类 inherited self-loop 误判成新 patch 引入的 cycle；否则 advisory freeze-only patch 和 CEO advisory snapshot 都会被旧图形状反向打断。`

**当前处理：**
`已在 2026-04-16 完成图层收口：新增单点 graph identity resolver，shared runtime node 的 maker/checker/rework 现在会显式拆成 execution / review 两条 graph lane；graph patch validation 与 graph health 已删除 inherited self-loop 跳过兼容，不再回退到旧 session JSON 或 runtime latest-ticket 半猜推导。运行时 node_projection 主键保持不动，后续如果要继续拆 runtime identity，单独开切片。`

**是否需要改架构文档：**
`no`

**状态：** `closed`

---

## 10. 本轮会话记录

每次新会话追加一段，不覆盖历史。

### Session `2026-04-14 / 01`
**开始前判断：**
- 当前阶段：`P0`
- 当前切片：`P0-S1`
- 是否继续上轮：`no`

**本轮做了什么：**
- [x] 创建重构计划模板
- [x] 创建主计划文档
- [x] 创建新会话提示词文档
- [x] 更新文档索引入口

**验证结果：**
- [ ] 尚未进行代码重构验证
- [x] 计划资产文件已落盘

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新
- [ ] `doc/history/memory-log.md` 未更新

**留下的未完成项：**
- [ ] 进入首次代码实施前，先核对当前代码现实和 `P0-S1` 验证方式

**下一轮起手动作：**
`读取固定输入文档，然后从 P0-S1 开始锁定 bootstrap 相关代码入口和最小验证命令。`

### Session `2026-04-14 / 02`
**开始前判断：**
- 当前阶段：`P0`
- 当前切片：`P0-S1`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `SYSTEM_INITIALIZED` 收到 `repository.initialize()` 的仓库级幂等入口
- [x] 删掉 `project-init` 里的系统初始化写入，保留纯 workflow 启动职责
- [x] 补了冷启动空态 dashboard、初始化幂等和 legacy 初始化顺序回归
- [x] 同步本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "system_initialized or startup or invalid_project_init" -q` 通过
- [x] `./backend/.venv/bin/pytest backend/tests/test_repository.py -k "initialize" -q` 通过
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "system_initialized or startup or project_init" -q` 当前未全绿；命中一组依赖 live provider 的旧 `project-init` 自动推进用例，当前环境未配 provider 时会报 `PROVIDER_REQUIRED_UNAVAILABLE`

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P0-S2` 还没开始
- [ ] `project-init` 自动推进那批 provider 依赖老测试，后续要单独和 runtime/provider 收口一起处理

**下一轮起手动作：**
`继续 P0-S2，先锁 graph / asset / governance profile / execution package 这几类对象的最小版本标识入口。`

### Session `2026-04-14 / 03`
**开始前判断：**
- 当前阶段：`P0`
- 当前切片：`P0-S2`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/versioning.py`，统一 process asset canonical ref、compiled artifact version ref、`GovernanceProfile` id 和 workflow graph version helper
- [x] 给 process asset、compiled context bundle / manifest / execution package 接上显式版本字段和 supersede 链，旧短 ref 只保留 resolver 入口兼容
- [x] 新增最小 `GovernanceProfile` contract + repository append-only 存储与只读查询
- [x] 补齐 process asset / context compiler / repository / API 相关回归，并同步本计划、`doc/TODO.md`、`doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_process_assets.py backend/tests/test_versioning.py backend/tests/test_context_compiler.py -k "version or governance_profile or graph_version or process_asset" -q` 通过（`11 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_process_assets.py backend/tests/test_context_compiler.py backend/tests/test_repository.py backend/tests/test_project_workspace_hooks.py -k "version or governance or compile or process_asset" -q` 通过（`40 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "governance_document or compile or process_asset" -q` 通过（`5 passed`）
- [x] `python -m py_compile backend/app/contracts/governance.py backend/app/core/versioning.py backend/app/core/process_assets.py backend/app/core/context_compiler.py backend/app/db/repository.py backend/tests/test_process_assets.py backend/tests/test_versioning.py backend/tests/test_context_compiler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P0-S3` 还没开始
- [ ] graph version 当前还是 repository helper 推导值，后续 `P1` 需要决定是否升级成正式图真相字段

**下一轮起手动作：**
`进入 P0-S3，先给关键写路径补显式版本检查，再把冲突失败保护接进 repository / compiler / ticket handler。`

### Session `2026-04-14 / 04`
**开始前判断：**
- 当前阶段：`P0`
- 当前切片：`P0-S3`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `CompileRequestMeta / CompiledExecutionPackageMeta` 补上 `ticket_projection_version / node_projection_version / source_projection_version`
- [x] 给 `TicketStartCommand / TicketResultSubmitCommand` 补上最小 optimistic guard 字段，并把 runtime 主线的 `ticket-start / ticket-result-submit` 一起接上新字段
- [x] 在 repository / ticket handler 里新增主线 stale guard：`ticket-start` 会拒绝 stale projection version，`ticket-result-submit` 会拒绝 stale `compiled_execution_package` ref
- [x] 把审批版本检查抽成共享 helper，并给 `ticket_context_archives` 补上 `compile_request_id / version_ref / source_projection_version / stale_against_latest`
- [x] 同步本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k "version or stale or compile" -q` 通过（`33 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "stale_board_command or board_command_is_rejected_when_projection_is_not_currently_blocked or stale_projection_version_guard or stale_compiled_execution_package_version_ref" -q` 通过（`4 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_context_archive.py -q` 通过（`3 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "runtime_uses_openai_compat_provider_when_configured" -q` 通过（`1 passed`）
- [x] `python -m py_compile backend/app/contracts/runtime.py backend/app/contracts/commands.py backend/app/db/repository.py backend/app/core/context_compiler.py backend/app/core/ticket_handlers.py backend/app/core/approval_handlers.py backend/app/core/ticket_context_archive.py backend/app/core/runtime.py` 通过
- [ ] 宽口径 `./backend/.venv/bin/pytest backend/tests/test_api.py -k "board_approve or stale_board_command or projection_guard or stale_projection_version_guard or stale_compiled_execution_package_version_ref" -q` 当前未全绿；命中一组旧的 governance/provider auto-advance 用例，会在 `node_ceo_architecture_brief` 打开 `PROVIDER_REQUIRED_UNAVAILABLE -> REPEATED_FAILURE_ESCALATION`

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P0-S4` 当前只完成 `ticket_context_archives` 这一类视图文档的版本标记和 stale 检查；是否把一致性检查扩到更多物化面，下一轮再锁
- [ ] external command 调用仍允许省略 expected version / execution package ref；如果下一轮要把它升成全量硬约束，需要先清旧调用方

**下一轮起手动作：**
`继续 P0-S4 或直接转 P1；先决定 ticket graph / controller 的首个正式切片，再把版本护栏扩到下一类物化视图。`

### Session `2026-04-14 / 05`
**开始前判断：**
- 当前阶段：`P0`
- 当前切片：`P0-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/boardroom_document_materializer.py`，给 `Boardroom` 运行时视图补上共享 contract、纯 renderer 和原子 writer
- [x] 把 `active-worktree-index.md`、`brief.md`、`required-reads.md`、`doc-impact.md`、`git-closeout.md` 改成从 projection + receipt 重算，不再靠 bootstrap 模板或点状手写正文
- [x] 给 `ticket-create / ticket-start / ticket-result-submit` 以及 review/closeout 的 git 状态变更补视图刷新触点
- [x] 补齐 `backend/tests/test_boardroom_document_materializer.py`，并扩 `test_project_workspaces.py / test_project_workspace_hooks.py`
- [x] 同步本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_boardroom_document_materializer.py -q` 通过（`2 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_project_workspaces.py backend/tests/test_project_workspace_hooks.py -k "boardroom or dossier or worktree or doc_impact or git_closeout" -q` 通过（`6 passed, 19 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_context_archive.py -q` 通过（`3 passed`）
- [x] `python3 -m py_compile backend/app/core/boardroom_document_materializer.py backend/app/core/project_workspaces.py backend/app/core/ticket_handlers.py backend/app/core/approval_handlers.py backend/tests/test_boardroom_document_materializer.py backend/tests/test_project_workspaces.py backend/tests/test_project_workspace_hooks.py` 通过
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "closeout_internal_checker_approved_returns_completion_summary" -q` 未通过；已在原工作区同提交复验，同样失败，确认为历史旧问题，不是本轮回归

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P1` 的首个 ticket graph / controller 正式切片还没建立
- [ ] 更广的 closeout / approval 历史测试还没和新物化面一起重收

**下一轮起手动作：**
`从 P1-S1 开始，先把 ticket graph / edge / ready-node 选路收成正式协议，再决定哪些 Boardroom 视图继续复用这轮 materializer。`

### Session `2026-04-14 / 06`
**开始前判断：**
- 当前阶段：`P1`
- 当前切片：`P1-S1`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/contracts/ticket_graph.py` 和 `backend/app/core/ticket_graph.py`，把 legacy ticket/node/projection 归约成正式 `TicketGraph`
- [x] 给最小图合同接上 `PARENT_OF / DEPENDS_ON / REVIEWS` 三类边，并把缺失 legacy dependency 显式收成 `reduction_issues + blocked_node_ids`
- [x] 把 `ceo_snapshot / workflow_controller` 接到图摘要，ready/blocked 读口开始优先走 `TicketGraph`
- [x] 同步本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q` 通过（`3 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py backend/tests/test_versioning.py -q` 通过（`7 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "snapshot_exposes_capability_plan_for_backlog_followups or snapshot_requires_next_governance_document_before_backlog_fanout or snapshot_builds_full_dependency_chain_for_next_governance_document or snapshot_treats_any_approved_architect_governance_document_as_gate_satisfied" -q` 通过（`7 passed, 60 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "test_scheduler_runner_idle_ceo_maintenance_hires_architect_for_controller_gate or test_scheduler_runner_idle_ceo_maintenance_creates_architect_governance_ticket_for_controller_gate or test_scheduler_runner_idle_ceo_maintenance_creates_next_governance_document_ticket" -q` 通过（`3 passed, 48 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/ticket_graph.py backend/app/core/ticket_graph.py backend/app/core/versioning.py backend/app/core/workflow_controller.py backend/app/core/ceo_snapshot.py backend/tests/test_ticket_graph.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P1-S2` 还没开始；controller 的 ready-node / blocked 判定目前只是开始读图摘要，还没全面切到图索引
- [ ] dashboard / dependency inspector 还没消费 `TicketGraph`

**下一轮起手动作：**
`继续 P1-S2，把 controller 的 ready-node / blocked 判定改成正式消费 TicketGraph 索引，并决定 dependency inspector / dashboard 哪个先接图摘要。`

### Session `2026-04-14 / 07`
**开始前判断：**
- 当前阶段：`P1`
- 当前切片：`P1-S2`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 扩 `backend/app/contracts/ticket_graph.py` 和 `backend/app/core/ticket_graph.py`，给正式图索引补上 `in_flight_* / critical_path_node_ids / blocked_reasons`
- [x] 把 `workflow_controller` 的 runtime gate 改成正式读 `TicketGraph` 索引，`ceo_snapshot.ticket_summary.ready_count` 继续和图索引共口径
- [x] 把 dashboard 的 `blocked_node_ids / critical_path_node_ids / ops_strip.blocked_nodes` 接到同一套图索引，并保留最小兼容回退
- [x] 同步本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q` 通过（`6 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py backend/tests/test_ceo_scheduler.py -k "in_flight or blocker or summary_without_changing_controller_state or snapshot_exposes_capability_plan_for_backlog_followups or snapshot_requires_next_governance_document_before_backlog_fanout or snapshot_builds_full_dependency_chain_for_next_governance_document or snapshot_treats_any_approved_architect_governance_document_as_gate_satisfied" -q` 通过（`11 passed, 62 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "inbox_and_dashboard_reflect_open_approval or dashboard_projection_reuses_ticket_graph_indexes_for_blocked_and_critical_path or board_approve_command_resolves_open_approval or board_reject_command_resolves_open_approval" -q` 通过（`4 passed, 275 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/ticket_graph.py backend/app/core/ticket_graph.py backend/app/core/workflow_controller.py backend/app/core/projections.py backend/tests/test_ticket_graph.py backend/tests/test_api.py` 通过
- [ ] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "employee_freeze_containment_opens_staffing_incident_for_executing_ticket" -q` 额外复验时仍会命中一条旧的 provider / auto-advance incident；当前先记为历史问题，不算本轮回归

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P1-S3` 还没开始；`Dependency Inspector` 仍未正式消费 `TicketGraph`
- [ ] dashboard blocked 读面的兼容回退还没退出

**下一轮起手动作：**
`继续 P1-S3，先把 Dependency Inspector 切到 TicketGraph，再决定 dashboard blocked 兼容层的退出条件。`

### Session `2026-04-14 / 08`
**开始前判断：**
- 当前阶段：`P1`
- 当前切片：`P1-S3`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 重写 `Dependency Inspector` 投影，让它正式消费 `TicketGraph` 边和索引，不再按 legacy parent-only 语义解释依赖
- [x] 给依赖读面补上 `dependency_ticket_ids[] / graph_summary`，并把 dashboard 的 `blocked_node_ids` silent legacy fallback 改成显式 `blocked_node_source`
- [x] 同步后端 API 回归、前端类型和 `DependencyInspectorDrawer` 最小展示
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "dependency_inspector or dashboard_projection_reuses_ticket_graph_indexes_for_blocked_and_critical_path" -q` 通过（`6 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q` 通过（`6 passed`）
- [x] `cd frontend && npm run test:run -- src/App.test.tsx` 通过（`29 passed`）
- [x] `cd frontend && npm run build` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P2-S1` 正文还没写进主计划
- [ ] `TicketGraph` 不可用时的显式状态当前还没升级成正式 incident / recovery 主链

**下一轮起手动作：**
`切到 P2-S1，先把恢复与 Hook 收口的首个切片正文补进主计划，再继续实现 fail-visible 到 incident / recovery 的正式接线。`

### Session `2026-04-14 / 09`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S1`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把主计划的 `## 6` 和 `P2-S1` 正文补齐到真实 `P2 / P2-S1` 续跑状态
- [x] 新增 `TICKET_GRAPH_UNAVAILABLE` incident 与 `REBUILD_TICKET_GRAPH` 恢复动作，`workflow_auto_advance` 命中图不可用时会正式开单并停止静默推进
- [x] 给 incident detail / resolve 和前端 `IncidentDrawer` 补齐图故障说明、恢复动作和 fail-closed 恢复校验
- [x] 同步本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_unavailable or rebuild_ticket_graph" -q` 通过（`4 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_workflow_autopilot.py -k "graph_unavailable" -q` 通过（`1 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q` 通过（`6 passed`）
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx` 通过（`2 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/commands.py backend/app/core/constants.py backend/app/core/ticket_handlers.py backend/app/core/workflow_auto_advance.py backend/app/core/projections.py backend/tests/test_api.py backend/tests/test_workflow_autopilot.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P2-S2` 还没开始；Hook 仍是散点 receipt / validation，尚未收成正式 `RoleHook` registry 和 required hook gate
- [ ] `TICKET_GRAPH_UNAVAILABLE` 这轮只接到 `workflow_auto_advance`；其他直接调用 `run_ceo_shadow_for_trigger` 的路径还没统一 incident 化

**下一轮起手动作：**
`继续 P2-S2，先把现有 worker receipts 和 validation 收成最小 RoleHook registry，再把 required hook gate 接进节点放行条件。`

### Session `2026-04-15 / 10`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S2`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/role_hooks.py`，把最小 hook registry、结构化 gate result、required hook replay 和缺 hook incident 扫描收成单点协议
- [x] 给 `TicketGraph / workflow_auto_advance / ticket_handlers` 接上 `REQUIRED_HOOK_GATE_BLOCKED`、`REPLAY_REQUIRED_HOOKS` 和 `REQUIRED_HOOK_PENDING:*`
- [x] 给 incident detail / 前端 `IncidentDrawer` 补 required hook gate 说明和默认恢复动作
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q` 通过（`7 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_project_workspace_hooks.py -q` 通过（`19 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "incident or hook or graph" -q` 通过（`3 passed, 8 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q` 通过（`6 passed`）
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx` 通过（`3 passed`）
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "hook or blocked_reason or incident" -q` 当前未全绿；仍有 3 条旧的 `project-init` governance/provider incident 历史用例失败，已记到“新发现但不在本轮做”和 `D-006`

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P2-S3` 还没开始；当前 `REPLAY_REQUIRED_HOOKS` 只覆盖 workspace-managed 源码票
- [ ] `run_ceo_shadow_for_trigger` 的其他直调路径和 project-init governance/provider 老 incident 噪音还没统一收口

**下一轮起手动作：**
`从 P2-S3 继续，把 required hook gate 从 workspace-managed 源码票扩到下一类真实主线票型，并决定 runtime/provider 老 incident 噪音和 hook replay 的边界谁先收。`

### Session `2026-04-15 / 11`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S3`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `structured_document_delivery` 接进正式 `RoleHook` gate：治理文档和 closeout 现在会写 `artifact-capture.json`
- [x] 给 closeout 额外补 `documentation-sync.json`，并把 `REPLAY_REQUIRED_HOOKS` 扩到 `artifact_capture / documentation_sync`
- [x] 给 `TICKET_COMPLETED` payload 补 `written_artifacts`，让文档票 replay 只读持久化 terminal truth，不从正文反推
- [x] 把前端 `IncidentDrawer` 文案收正成票型无关口径，并同步后端 / 前端回归
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q` 通过（`10 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_project_workspace_hooks.py -q` 通过（`29 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "incident or hook or graph" -q` 通过（`3 passed, 8 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q` 通过（`6 passed`）
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx` 通过（`3 passed`）
- [x] `python3 -m py_compile backend/app/core/project_workspaces.py backend/app/core/role_hooks.py backend/app/core/ticket_handlers.py backend/tests/test_role_hooks.py backend/tests/test_project_workspace_hooks.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P2-S4` 还没开始；`review_evidence` 票型仍未接进正式 hook gate / replay
- [ ] project-init governance/provider 老 incident 噪音仍未收口

**下一轮起手动作：**
`从 P2-S4 起手，先把 review evidence 票型按独立语义接进 hook gate / replay，再决定 runtime/provider 老 incident 噪音是否单列一个恢复切片。`

### Session `2026-04-15 / 12`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `review_evidence` 接进正式 `RoleHook` gate：`delivery_check_report / ui_milestone_review / maker_checker_verdict` 现在都会按独立票型语义走 `artifact_capture`
- [x] 在 `ticket-result-submit` 成功路径里给 `review_evidence` 票补写 `artifact-capture.json`，并保持只用持久化 terminal truth 做 replay
- [x] 把 `artifact_capture` replay 收正成“缺字段才 reject，空数组可幂等回放”的 fail-closed 口径
- [x] 补齐 `backend/tests/test_role_hooks.py` 和 `backend/tests/test_api.py` 的 review evidence gate / replay / dependency gate 回归
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q` 通过（`13 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "hook or incident or graph" -q` 通过（`3 passed, 8 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "review_evidence_missing_required_hook_keeps_dependency_gate_blocked" -q` 通过（`1 passed`）
- [x] `python3 -m py_compile backend/app/core/role_hooks.py backend/app/core/ticket_handlers.py backend/tests/test_role_hooks.py backend/tests/test_api.py` 通过
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "delivery_check_report or ui_milestone_review or maker_checker_verdict" -q` 原样补跑仅返回 `286 deselected`；已记入 `D-008`，本轮不把它当通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] project-init governance/provider 老 incident 噪音仍未收口
- [ ] `run_ceo_shadow_for_trigger` 其他直调路径还没统一进恢复主链
- [ ] API 宽匹配验证命令还没有一个稳定、非空跑的聚合桶

**下一轮起手动作：**
`从旧的 project-init governance/provider incident 噪音收口切片继续，优先把 runtime/provider 恢复主链和相关历史回归统一到正式 incident / recovery 口径。`

### Session `2026-04-15 / 13`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S5`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 scheduler dispatch、`ticket-lease` 和 `ticket-start` 接上统一 provider precondition gate
- [x] 新增 `TICKET_EXECUTION_PRECONDITION_BLOCKED / TICKET_EXECUTION_PRECONDITION_CLEARED` 和 `BLOCKING_REASON_PROVIDER_REQUIRED`
- [x] 把 `project-init -> node_ceo_architecture_brief` 的“无 live provider”从普通失败链剥离，改成显式阻断 + 幂等解阻
- [x] 同步 API 测试夹具，让直接造执行票的测试默认补最小 provider binding，不靠旧的隐式 deterministic 口径混过去
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_check_internal_checker_escalated_opens_incident_and_marks_dependency_stop or test_dashboard_pipeline_summary_shows_fused_build_stage_for_open_incident_breaker or test_employee_freeze_containment_opens_staffing_incident_for_executing_ticket or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q` 通过（`6 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q` 通过（`3 passed, 8 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q` 通过（`6 passed`）
- [x] `python3 -m py_compile backend/app/core/constants.py backend/app/core/reducer.py backend/app/core/ticket_handlers.py backend/tests/test_api.py` 通过
- [ ] `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "provider_incident or provider_recovery" -q` 额外复验仍有 5 条旧测试失败；当前判断是 legacy env-config / deterministic fallback 口径未迁到 provider center + target binding，不作为本轮 blocker，已记到 `D-009`

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `run_ceo_shadow_for_trigger` 其他直调路径还没统一进恢复主链
- [ ] scheduler_runner 的 provider recovery 历史测试还没迁到 provider center + target binding 口径
- [ ] API 宽匹配验证命令仍没有稳定、非空跑的聚合桶

**下一轮起手动作：**
`继续 runtime/provider 历史测试收口，先把 scheduler_runner 的 provider recovery 夹具和直调恢复路径统一到当前 provider center 真相。`

### Session `2026-04-15 / 14`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S5`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `backend/tests/test_scheduler_runner.py` 补最小 provider center + target binding helper
- [x] 把 provider auth / bad response / rate limit 相关 runner 断言改成显式失败与 incident 真相
- [x] 把 mainline recovery 测试改成“先补 governance-first 前置，再测 provider 恢复”，不再把 `project-init` 和旧 scope approval 首跳绑死
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "provider_incident or provider_recovery" -q` 通过（`5 passed, 46 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q` 通过（`3 passed, 8 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q` 通过（`3 passed, 284 deselected`）
- [x] `python3 -m py_compile backend/tests/test_scheduler_runner.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `run_ceo_shadow_for_trigger` 其他直调恢复路径还没统一进正式 incident / recovery 主链
- [ ] API 宽匹配验证桶仍没有稳定、非空跑的聚合口径
- [ ] 更宽的 closeout / approval 历史测试桶还没收口

**下一轮起手动作：**
`继续 runtime/provider 恢复主链收口，优先把 run_ceo_shadow_for_trigger 的直调路径和 API 宽匹配验证桶统一到当前显式错误 / 幂等恢复真相。`

### Session `2026-04-15 / 15`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `run_ceo_shadow_for_trigger` 改成严格路径：live provider 坏响应、非法 action batch 和执行失败现在都会抛 `CeoShadowPipelineError`，不再隐式 fallback
- [x] 新增 `CEO_SHADOW_PIPELINE_FAILED` incident，并把 `command / approval / ticket / idle maintenance` 四类直调入口统一接到 `trigger_ceo_shadow_with_recovery()`
- [x] 给 `incident-resolve` 补 `RERUN_CEO_SHADOW`，incident detail / autopilot 推荐动作也已接上同一条恢复合同
- [x] 把 API 恢复验证桶收正成稳定、非空跑的 `test_p2_ceo_shadow_incident_*`，并把 `workflow_autopilot` 回归补到新口径
- [x] 更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "ceo_shadow_pipeline_failed or rerun_ceo_shadow" -q` 通过（`2 passed, 67 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "p2_ceo_shadow_incident" -q` 通过（`5 passed, 287 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_workflow_autopilot.py -k "ceo_shadow or incident" -q` 通过（`4 passed, 8 deselected`）
- [x] `python -m py_compile backend/app/core/ceo_scheduler.py backend/app/core/ticket_handlers.py backend/app/core/projections.py backend/tests/test_ceo_scheduler.py backend/tests/test_api.py backend/tests/test_workflow_autopilot.py` 通过
- [ ] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -q` 额外补跑仍有一批旧 helper 失败；当前判断是旧 deliverable contract 夹具没有迁到现状，不算本轮 blocker，已记到“新发现但不在本轮做”

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] 更宽的 closeout / approval 历史测试桶还没收口
- [ ] `backend/tests/test_ceo_scheduler.py` 里仍有一批旧 helper 夹具没有迁到当前 deliverable contract

**下一轮起手动作：**
`继续 closeout / approval 历史测试桶收口，优先把旧的 ceo_scheduler helper 夹具迁到当前 deliverable contract，再决定是否把 recovery-start 审计进一步协议化。`

### Session `2026-04-15 / 16`
**开始前判断：**
- 当前阶段：`P2`
- 当前切片：`P2-S8`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `backend/tests/test_ceo_scheduler.py` 里的旧 helper 收成显式步骤：provider 前置、lease/start、源码票、治理文档票、共识票、checker verdict 都已对齐当前 deliverable contract，并统一检查 `status_code + json.status`
- [x] 把 `backend/tests/test_api.py` 的 closeout / approval 历史桶改成显式 manual chain：`scope approval -> build maker/checker -> check maker/checker -> review maker/checker -> final review -> closeout maker/checker`
- [x] 把 synthetic manual chain 和 dashboard `completion_summary` 的边界收正到测试真相：不再把这条手工链误写成“workflow 已完成”，summary 继续只在 autopilot / closeout 专项测试里覆盖
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -q` 通过（`69 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "test_board_approve_scope_review_creates_followup_ticket_and_advances_to_visual_review or test_final_review_approval_creates_closeout_ticket_and_completion_summary_uses_closeout_fields or test_closeout_internal_checker_approved_returns_completion_summary" -q` 通过（`3 passed, 289 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "test_final_review_approval_rejects_when_review_gate_merge_conflicts or test_completion_summary_handles_missing_closeout_documentation_updates or test_closeout_internal_checker_changes_required_creates_fix_ticket_and_blocks_completion or test_completion_summary_returns_null_source_delivery_summary_when_closeout_lacks_source_delivery_asset" -q` 通过（`4 passed, 288 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/tests/test_api.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P3` 正文切片还没展开；下一轮先补 `P3` 首个切片入口，再继续执行包与 CEO 收口

**下一轮起手动作：**
`从 P3 起手，先补执行包 / CEO 收口的首个切片正文，再决定执行包合同、快照分层和技能绑定谁先落。`

### Session `2026-04-15 / 17`
**开始前判断：**
- 当前阶段：`P3`
- 当前切片：`P3-S1`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `GovernanceProfile` 补齐运行时合同字段，`project-init` 现在会稳定写默认治理档位；`CompileRequest / CompiledExecutionPackage` 已显式带 `governance_profile_ref / governance_mode_slice / task_frame / required_doc_surfaces / context_layer_summary`
- [x] 把 `build_ceo_shadow_snapshot()` 收成 `projection_snapshot / replan_focus` 两层，`ceo_prompts / proposer / validator / scheduler / workflow_controller` 已切到新快照协议；缺结构时走显式失败，不再隐式读旧顶层
- [x] 新增最小 `skill_runtime`，把 `SkillBinding` 接进执行包和执行卡片；当前已覆盖 `implementation / review / debugging / planning_governance` 四类技能，并对未知 `forced_skill_ids` fail-closed
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "snapshot or governance or prompt" -q` 通过（`35 passed, 36 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "ceo_shadow_snapshot" -q` 通过（`2 passed, 4 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "idle_ceo_maintenance_creates_architect or idle_ceo_maintenance_creates_next_governance_document_ticket" -q` 通过（`2 passed, 49 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_skill_runtime.py -q` 通过（`3 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_context_compiler.py -q` 通过（`34 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "worker_runtime" -q` 通过（`34 passed, 259 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_context_archive.py -q` 通过（`3 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_versioning.py -q` 通过（`5 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/commands.py backend/app/contracts/governance.py backend/app/contracts/runtime.py backend/app/contracts/ceo.py backend/app/core/governance_profiles.py backend/app/core/context_compiler.py backend/app/core/skill_runtime.py backend/app/core/ceo_snapshot_contracts.py backend/app/core/ceo_snapshot.py backend/app/core/ceo_prompts.py backend/app/core/ceo_proposer.py backend/app/core/ceo_validator.py backend/app/core/ceo_scheduler.py backend/app/core/workflow_controller.py backend/app/core/ticket_context_archive.py backend/app/core/command_handlers.py backend/app/db/repository.py backend/app/core/versioning.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py backend/tests/test_context_compiler.py backend/tests/test_ticket_context_archive.py backend/tests/test_versioning.py backend/tests/test_skill_runtime.py backend/tests/test_scheduler_runner.py backend/tests/test_ticket_graph.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P4` 正文切片还没展开；下一轮先补顾问环 / ProjectMap 接入的首个切片入口

**下一轮起手动作：**
`从 P4 起手，先补顾问环 / ProjectMap 接入的首个切片正文，再决定 BoardAdvisorySession 和 ProjectMap 谁先落。`

### Session `2026-04-15 / 18`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S1`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `BoardAdvisorySession` 合同、schema、repository helper 和只读查询；`requires_constraint_patch_on_modify=true` 的 review pack 现在会自动绑定单条 advisory session
- [x] 把 `MODIFY_CONSTRAINTS` 收成显式顾问决策链：会写 advisory decision truth、`DECISION_SUMMARY` 过程资产，并在需要时 append-only supersede `GovernanceProfile`
- [x] 把 `build_ceo_shadow_snapshot()` 和现有 `Review Room / ReviewRoomDrawer` 接到 advisory 摘要；CEO prompt 现在会显式提示先读 `board_advisory_sessions / latest_advisory_decision`
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `python -m py_compile backend/app/contracts/advisory.py backend/app/contracts/commands.py backend/app/contracts/ceo.py backend/app/contracts/process_assets.py backend/app/core/board_advisory.py backend/app/core/approval_handlers.py backend/app/core/ceo_snapshot.py backend/app/core/ceo_prompts.py backend/app/core/process_assets.py backend/app/core/projections.py backend/app/core/constants.py backend/app/db/repository.py backend/app/db/schema.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py` 通过
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "review_room_route_returns_existing_projection or review_room_route_includes_board_advisory_context or modify_constraints or board_approve_dismisses_linked_board_advisory_session" -q` 通过（`7 passed, 290 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "latest_board_advisory_decision or prompt_mentions_latest_board_advisory_decision" -q` 通过（`2 passed, 71 deselected`）
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/ReviewRoomDrawer.test.tsx src/test/__tests__/components/ReviewRoomDrawer.persistence.test.tsx` 通过（`5 passed`）
- [x] `cd frontend && npm run build` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `P4-S4` 还没开始；`ProjectMap / FailureFingerprint / GraphHealthReport` 仍未进入正式合同和 CEO 可消费读面
- [ ] `approved_patch_ref -> graph patch engine` 这层当前仍是 open deviation，后续要单独收口

**下一轮起手动作：**
`从 P4-S4 继续，先补 ProjectMap 最小合同和 process asset / advisory 的血缘接线，再决定 graph patch engine 和 GraphHealthMonitor 谁先落。`

### Session `2026-04-15 / 19`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `FAILURE_FINGERPRINT / PROJECT_MAP_SLICE` 正式 `ProcessAsset` 合同、ref builder 和 resolver，不新增独立存储，也不从文档正文反推真相
- [x] 把 workflow 级 `ProjectMapSlice`、最近失败指纹和 `GraphHealthReport` 接进 `Context Compiler / CEO Snapshot / CEO prompt`
- [x] 新增最小 `graph_health.py`，只做 `FANOUT_TOO_WIDE / CRITICAL_PATH_TOO_DEEP / PERSISTENT_FAILURE_ZONE` 三条规则
- [x] 把 `GRAPH_HEALTH_CRITICAL` 接进 `workflow_auto_advance / incident detail / IncidentDrawer`，恢复动作继续复用 `RERUN_CEO_SHADOW`
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_process_assets.py -q` 通过（`3 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k "project_map or failure_fingerprint" -q` 通过（`1 passed, 34 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "project_map or failure_fingerprint or graph_health" -q` 通过（`1 passed, 73 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "graph_health" -q` 通过（`2 passed, 6 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "graph_health_critical or incident_detail" -q` 通过（`3 passed, 295 deselected`）
- [x] `python3 -m py_compile backend/app/contracts/ceo.py backend/app/contracts/process_assets.py backend/app/core/process_assets.py backend/app/core/context_compiler.py backend/app/core/ceo_snapshot.py backend/app/core/ceo_prompts.py backend/app/core/graph_health.py backend/app/core/constants.py backend/app/core/projections.py backend/app/core/ticket_handlers.py backend/app/core/workflow_auto_advance.py backend/tests/test_process_assets.py backend/tests/test_context_compiler.py backend/tests/test_ceo_scheduler.py backend/tests/test_ticket_graph.py backend/tests/test_api.py` 通过
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx` 通过（`4 passed`）
- [x] `cd frontend && npm run build` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `BoardAdvisorySession.approved_patch_ref -> graph patch engine` 仍未落地
- [ ] `ProjectMapSlice` 对 legacy 非 workspace-managed 代码票仍是保守精度，不等于 workspace-managed 主链的正式地图精度

**下一轮起手动作：**
`如果继续推进新架构重构，优先从 advisory graph patch engine 的独立切片起手，再决定是否扩第二批 GraphHealth 规则和更细的 ProjectMap 切片。`

### Session `2026-04-16 / 20`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 advisory review pack 的 `modify-constraints` 收正成显式 change flow 入口，不再一步式 resolve approval
- [x] 给 advisory session 补 `working_turns / latest_patch_proposal_ref / approved_patch_ref / patched_graph_version / focus_node_ids`，并新增 `board-advisory-append-turn / board-advisory-request-analysis / board-advisory-apply-patch`
- [x] 新增正式 `GRAPH_PATCH_PROPOSAL / GRAPH_PATCH` 过程资产和 resolver，让 `approved_patch_ref` 只指向真实 graph patch
- [x] 把 applied advisory patch 的 `freeze / unfreeze / focus` 接进 `TicketGraph`，同时更新 `ceo_shadow_snapshot / Review Room / ReviewRoomDrawer`
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py::test_review_room_route_includes_board_advisory_context backend/tests/test_api.py::test_modify_constraints_enters_board_advisory_change_flow_without_resolving_open_approval backend/tests/test_api.py::test_board_advisory_append_turn_persists_working_context_without_changing_graph backend/tests/test_api.py::test_board_advisory_request_analysis_creates_patch_proposal_without_resolving_approval backend/tests/test_api.py::test_board_advisory_apply_patch_resolves_approval_and_advances_graph_version backend/tests/test_api.py::test_board_advisory_apply_patch_rejects_stale_proposal backend/tests/test_api.py::test_board_approve_dismisses_linked_board_advisory_session backend/tests/test_process_assets.py::test_resolve_board_advisory_graph_patch_assets backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_exposes_latest_board_advisory_decision backend/tests/test_ceo_scheduler.py::test_ceo_shadow_prompt_mentions_latest_board_advisory_decision backend/tests/test_api_surface.py -q` 通过（`12 passed`）
- [x] `python3 -m py_compile backend/app/contracts/advisory.py backend/app/contracts/commands.py backend/app/contracts/ceo.py backend/app/contracts/process_assets.py backend/app/core/board_advisory.py backend/app/core/approval_handlers.py backend/app/core/process_assets.py backend/app/core/ticket_graph.py backend/app/core/ceo_snapshot.py backend/app/core/versioning.py backend/app/api/commands.py backend/app/db/repository.py` 通过
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/ReviewRoomDrawer.test.tsx src/App.test.tsx && npm run build` 通过（`35 passed`，build passed）

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `FULL_TIMELINE` 的 advisory transcript archive 还没物化
- [ ] advisory analysis 还没把 CEO / 架构侧内部讨论收成独立运行链和 recovery 动作

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先补 FULL_TIMELINE 的 advisory transcript archive 和更完整的 advisory recovery / architect discussion 链。`

### Session `2026-04-16 / 21`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `BoardAdvisorySession` 补 `latest_timeline_index_ref / latest_transcript_archive_artifact_ref / timeline_archive_version_int`，并把 `TIMELINE_INDEX` 收进正式 `ProcessAsset` 合同和 resolver
- [x] 给 advisory change flow 补 `FULL_TIMELINE` transcript archive helper；`modify-constraints / append-turn / request-analysis / apply-patch / dismiss` 命中 `FULL_TIMELINE` 时现在都会写 archive + timeline index
- [x] 把 archive refs 接进 `Review Room / ReviewRoomDrawer / build_ceo_shadow_snapshot() / latest_advisory_decision`
- [x] 把 archive 失败路径收正成显式 `REJECTED + rollback`，不再留下半写 session 状态
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "board_advisory or timeline_index" -q` 通过（`9 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_process_assets.py -k "timeline_index or board_advisory" -q` 通过（`2 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "advisory or timeline" -q` 通过（`3 passed`）
- [x] `python3 -m py_compile backend/app/contracts/advisory.py backend/app/contracts/ceo.py backend/app/contracts/process_assets.py backend/app/core/board_advisory.py backend/app/core/approval_handlers.py backend/app/core/process_assets.py backend/app/db/repository.py backend/app/db/schema.py backend/tests/test_api.py backend/tests/test_process_assets.py backend/tests/test_ceo_scheduler.py` 通过
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/ReviewRoomDrawer.test.tsx && npm run build` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] advisory analysis 还没把 CEO / 架构侧内部讨论收成独立运行链和 recovery 动作
- [ ] legacy / 非 workspace-managed 代码票的 `ProjectMapSlice` 仍是保守精度

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先补 advisory analysis 的独立运行链和 recovery 动作，再决定是否扩第二批 GraphHealth 规则。`

### Session `2026-04-16 / 22`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `BoardAdvisoryAnalysisRun` 合同、schema 和 repository helper，把 advisory analysis 收成独立运行链，不再让 `board-advisory-request-analysis` 直接在 command 事务里同步算 proposal
- [x] 新增 `backend/app/core/board_advisory_analysis.py`，把 advisory analysis 的 compile request / compiled execution package / explicit deterministic-vs-live execution / proposal 校验 / trace artifact / FULL_TIMELINE archive 收到单点 harness
- [x] 新增 `BOARD_ADVISORY_ANALYSIS_FAILED` incident 和 `RERUN_BOARD_ADVISORY_ANALYSIS` recovery；`incident-resolve` 现在能基于最新 session 真相幂等补一轮 analysis rerun
- [x] 把 `Review Room / Incident Detail / IncidentDrawer / CEO snapshot` 接到 analysis run 新读面；pending analysis、failed analysis 和 rerun recovery 现在都能从正式只读投影里看见
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "board_advisory and (analysis or incident)" -q` 通过（`3 passed, 302 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_process_assets.py -k "board_advisory or timeline_index" -q` 通过（`2 passed, 3 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "advisory or timeline" -q` 通过（`3 passed, 72 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "graph_health" -q` 通过（`2 passed, 6 deselected`）
- [x] `python3 -m py_compile backend/app/contracts/advisory.py backend/app/contracts/commands.py backend/app/contracts/ceo.py backend/app/core/board_advisory.py backend/app/core/board_advisory_analysis.py backend/app/core/output_schemas.py backend/app/core/approval_handlers.py backend/app/core/projections.py backend/app/core/ticket_handlers.py backend/app/core/constants.py backend/app/db/repository.py backend/app/db/schema.py backend/tests/test_api.py backend/tests/test_process_assets.py backend/tests/test_ceo_scheduler.py backend/tests/test_ticket_graph.py` 通过
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/ReviewRoomDrawer.test.tsx src/test/__tests__/components/IncidentDrawer.test.tsx` 通过（`14 passed`）
- [x] `cd frontend && npm run build` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `legacy / 非 workspace-managed source_code_delivery` 的 `ProjectMapSlice` 仍是保守精度
- [ ] advisory analysis 的 live 选路当前仍收得很窄，只在存在 board-approved architect 且该员工显式绑定 `provider_id` 时启用

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先处理 legacy 非 workspace-managed 代码票的 ProjectMapSlice 精度，再决定是否扩第二批 GraphHealth 规则。`

### Session `2026-04-16 / 23`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `SOURCE_CODE_DELIVERY` 过程资产补成稳定地图输入，现已显式带 `source_paths / written_paths / module_paths / document_surfaces`
- [x] 把 `ProjectMapSlice` 收正到逐票消费 `SOURCE_CODE_DELIVERY` 资产；legacy / 非 workspace-managed 代码票只有在本票完全缺稳定路径时，才回退到本票自己的 `allowed_write_set`
- [x] 删掉 `ProjectMapSlice` 里按 `artifact_index.logical_path` 扫路径的旧兼容，不再把 runtime JSON、日志或证据路径混进模块地图
- [x] 把 `GraphHealthReport` 补到第二批：新增 `BOTTLENECK_DETECTED / ORPHAN_SUBGRAPH / FREEZE_SPREAD_TOO_WIDE`，并把 `CRITICAL_PATH_TOO_DEEP` 改成正式 `PARENT_OF + DEPENDS_ON` DAG 口径
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_assets.py -q` 通过（`7 passed`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_context_compiler.py -k "project_map or failure_fingerprint" -q` 通过（`1 passed, 34 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_health" -q` 通过（`6 passed, 6 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "project_map or graph_health" -q` 通过（`1 passed, 74 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_health_critical or incident_detail" -q` 通过（`3 passed, 302 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/core/process_assets.py backend/app/core/graph_health.py backend/tests/test_process_assets.py backend/tests/test_ticket_graph.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] `GraphHealthReport` 仍未补 `GRAPH_THRASHING / READY_NODE_STALE` 这类依赖额外时间序列或调度 SLA 真相的规则
- [ ] advisory analysis 的 live 选路当前仍收得很窄，只在存在 board-approved architect 且该员工显式绑定 `provider_id` 时启用

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先决定第三批 GraphHealth 是否补版本时间线规则，或单独收 advisory analysis 的 live provider 选路边界。`

### Session `2026-04-16 / 24`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `GraphHealthReport` 补第三批时间线规则：新增 `GRAPH_THRASHING / READY_NODE_STALE`；前者只读真实 `GRAPH_PATCH_APPLIED`，后者只读 ready ticket `updated_at / timeout_sla_sec`
- [x] 给 `graph_health.py` 新增正式 `GraphHealthUnavailableError`，把 graph patch payload 非对象、patch node list 非 `list[str]`、ready ticket 缺 `updated_at / timeout_sla_sec` 收成显式异常，不再静默 fallback
- [x] 删掉 `resolve_workflow_graph_version()` 对完整事件 payload 转换的旧依赖，改成按 graph mutation event 的 `sequence_no` 直接解 graph version，避免坏 payload 污染 graph version 真相
- [x] 把 `GraphHealthUnavailableError` 接进 `is_ticket_graph_unavailable_error()`；`workflow_auto_advance / trigger_ceo_shadow_with_recovery` 现在会继续复用 `TICKET_GRAPH_UNAVAILABLE` 恢复链
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_health" -q` 通过（`13 passed, 6 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_health_critical or incident_detail or ticket_graph_unavailable" -q` 通过（`5 passed, 303 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "graph_health or ticket_graph_unavailable" -q` 通过（`2 passed, 75 deselected`）
- [x] `python -m py_compile backend/app/core/graph_health.py backend/app/core/ceo_scheduler.py backend/app/core/versioning.py backend/tests/test_ticket_graph.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] advisory analysis 的 live provider 选路当前仍只在 board-approved architect 显式绑定 `provider_id` 时启用
- [ ] advisory graph patch engine 仍只支持 `freeze / unfreeze / focus`；`REPLACES`、增删节点和增删边还没进主链

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先单独收 advisory analysis 的 live provider 选路边界，再决定是否继续扩更细的 GraphHealth 调度时间线规则。`

### Session `2026-04-16 / 25`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 删除 advisory analysis live gate 对员工 `provider_id` 的旧兼容依赖，收口到“真实 board-approved architect + 正式 runtime provider 选路”
- [x] 给 `board_advisory_analysis.py` 补单点 `execution plan` helper；run 创建、compile worker binding 和 live 执行现在共用同一套 executor / selection 真相
- [x] 把 advisory analysis live mode 的失败口径收正到显式错误：`no real architect / no live provider selection / provider paused` 都会直接失败并继续走既有幂等 incident / recovery
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "advisory_analysis_run_uses_live_mode or advisory_analysis_run_stays_deterministic_without_real_architect or advisory_analysis_live_provider_pause_opens_incident_without_deterministic_fallback" -q` 通过（`4 passed, 308 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory and analysis" -q` 通过（`7 passed, 305 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/core/board_advisory_analysis.py backend/tests/test_api.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] advisory graph patch engine 仍只支持 `freeze / unfreeze / focus`
- [ ] `GraphHealthReport` 更细的 queue starvation、多次 ready/blocked 往返和跨版本调度 SLA 还没进入主链

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先补 advisory graph patch engine 第二版，把 REPLACES / 增删节点 / 增删边收成正式 patch 合同。`

### Session `2026-04-16 / 26`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `GraphPatchProposal / GraphPatch` 扩成正式 patch v2 合同，新增 `replacements / remove_node_ids / edge_additions / edge_removals`，并显式拒绝 `add_node`
- [x] 新增单点 `graph_patch_reducer.py`，把 patch 校验、overlay 归约和 touched-node 统计收成单一真相层；`TicketGraph / GraphHealth / apply-patch` 现已共用
- [x] 删掉 `TicketGraph` 直接读 `session.approved_patch` 的旧推导；`GRAPH_PATCH_PROPOSAL / GRAPH_PATCH` resolver 也已改成读不可变 artifact，不再从 session JSON 回填正文
- [x] 把 advisory patch v2 接进 `TicketGraph`：`REPLACES` 会物化正式图边，`remove_node` 会把旧节点转成 `CANCELLED`，`replacement` 会把旧节点转成 `SUPERSEDED`，`edge_additions / edge_removals` 会真实影响 blocked / critical-path
- [x] 把 graph patch 失败口径收正到显式拒绝：未知 node、重复边、缺失边、orphan、cycle、执行中/已完成节点 remove/replace 都会 fail-closed；旧 maker/checker inherited self-loop 只做显式跳过，不再污染 patch 校验和 graph health depth
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_patch or graph_health" -q` 通过（`16 passed, 7 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_assets.py -k "graph_patch or board_advisory" -q` 通过（`2 passed, 5 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory and patch" -q` 通过（`4 passed, 309 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "advisory or graph_health or ticket_graph_unavailable" -q` 通过（`5 passed, 72 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/advisory.py backend/app/core/board_advisory.py backend/app/core/board_advisory_analysis.py backend/app/core/approval_handlers.py backend/app/core/ceo_scheduler.py backend/app/core/constants.py backend/app/core/graph_health.py backend/app/core/graph_patch_reducer.py backend/app/core/output_schemas.py backend/app/core/process_assets.py backend/app/core/ticket_graph.py backend/tests/test_api.py backend/tests/test_process_assets.py backend/tests/test_ticket_graph.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] 真 `add_node` / placeholder node 仍未进入主链；当前 patch v2 只允许 existing-node rewiring
- [ ] maker/checker 的 inherited self-loop 只做了显式跳过，还没有推进到 graph-first node identity 真相
- [ ] `GraphHealthReport` 的 queue starvation、多次 ready/blocked 往返和跨版本调度 SLA 还没进入主链

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先补 GraphHealthReport 的 queue starvation / ready-blocked thrash / cross-version SLA 规则；true add_node 继续保持 graph-first 后置，不在现有 patch v2 里偷渡。`

### Session `2026-04-16 / 27`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `graph_health.py` 新增事件时间线 helper，并把 projection 读取收成单点；新规则只读 `events + graph_version + ticket/node projection.version/updated_at`
- [x] 新增 `QUEUE_STARVATION`：当前有 ready、没有 in-flight，且 ready 票停滞超过 `timeout_sla_sec * 3` 时现在会显式报 `CRITICAL`
- [x] 新增 `READY_BLOCKED_THRASHING / CROSS_VERSION_SLA_BREACH`：前者只认显式 blocker/unblocker 事件窗口并保留 `WARNING` 读面；后者只认当前 blocked 节点的 projection version 与当前 `graph_version` 差值，再叠加 `timeout_sla_sec * 2` 的停滞阈值，命中时显式报 `CRITICAL`
- [x] 这轮没有加新表、新 projection 或新 process asset；同时保持 fail-closed：缺 `updated_at / timeout_sla_sec / version` 或事件 payload 非法时继续抛 `GraphHealthUnavailableError`
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "queue_starvation or ready_blocked_thrashing or cross_version_sla or missing_version" -q` 通过（`7 passed`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "queue_starvation" -q` 通过（`1 passed, 313 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "queue_starvation" -q` 通过（`1 passed, 77 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_health" -q` 通过（`20 passed, 10 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_health" -q` 通过（`5 passed, 309 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "graph_health" -q` 通过（`2 passed, 76 deselected`）
- [x] `python -m py_compile backend/app/core/graph_health.py backend/tests/test_ticket_graph.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新

**留下的未完成项：**
- [ ] 真 `add_node` / placeholder node 仍未进入主链
- [ ] maker/checker inherited self-loop 仍只做显式跳过，还没有推进到 graph-first node identity 真相
- [ ] dedicated graph health history / workflow 级 SLA 配置 / 更细的 blocker-source attribution 仍未进入主链

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先处理 maker/checker 的 graph-first node identity，再决定 true add_node / placeholder node 是否拆成下一独立切片。`

### Session `2026-04-16 / 28`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/graph_identity.py`，把 graph lane 身份收成单点真相；普通执行票固定走 execution lane，`MAKER_CHECKER_REVIEW` 固定走 `runtime_node_id::review`，`MAKER_REWORK_FIX` 固定回 execution lane
- [x] 重写 `TicketGraph` 的 graph node 语义：删除 ticket-derived `graph_node_id=ticket:<ticket_id>` 旧兼容，shared runtime `node_id` 的 maker/checker/rework 现在会显式拆成 execution / review 两条 graph lane，并按当前 lane 聚合最新 ticket
- [x] 把 `graph_patch_reducer / graph_health / GRAPH_HEALTH_CRITICAL incident / CEO snapshot` 全切到新 graph identity；graph health finding 和 incident payload 现在会额外带 `affected_graph_node_ids`，旧兼容读面 `affected_nodes` 继续只保留 runtime node id
- [x] 删掉污染新架构真相的旧兼容：path self-loop 跳过、advisory patch 对 review lane 的“unknown node”模糊拒绝、以及 graph 层按 runtime latest-ticket 半猜 graph node 的旧推导都已移除；命中这类问题时现在会显式抛 `GraphIdentityResolutionError` 或显式 `REJECTED`
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_identity or graph_patch or graph_health" -q` 通过（`25 passed, 8 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_health or incident_detail or advisory_patch" -q` 通过（`7 passed, 308 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "graph_health or advisory" -q` 通过（`5 passed, 73 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/core/graph_identity.py backend/app/core/ticket_graph.py backend/app/core/graph_patch_reducer.py backend/app/core/graph_health.py backend/app/core/ceo_scheduler.py backend/app/core/approval_handlers.py backend/app/core/board_advisory_analysis.py backend/app/core/ticket_handlers.py backend/app/contracts/ticket_graph.py backend/app/contracts/ceo.py backend/tests/test_ticket_graph.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收口 graph layer identity 和 graph health/incident 合同，没有改变仓库级入口叙事或运行方式

**留下的未完成项：**
- [ ] 真 `add_node` / placeholder node 仍未进入主链
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；这轮只完成 graph layer identity 收口，没有继续拆运行时身份
- [ ] dedicated graph health history / workflow 级 SLA 配置 / 更细的 blocker-source attribution 仍未进入主链

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先决定 true add_node / placeholder node 是否拆成独立切片；runtime node_projection 是否继续拆成 graph-first 双层真相保持后置单独决策。`

### Session `2026-04-16 / 29`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `GraphPatchProposal / GraphPatch` 新增正式 `add_nodes[]`，补最小 `GraphPatchAddedNode` 合同；`graph_patch_proposal` output schema 已升到 `v2`
- [x] 把 `board_advisory_analysis.py` 的 analysis output 校验收正到新合同：旧的“只认 existing node rewiring”提示已删掉，`add_node` 现在要显式带 parent/dependency，重复 node_id 也会显式 reject
- [x] 把 `graph_patch_reducer.py` 扩成 graph-only placeholder overlay：`add_node` 现在会物化 parent/dependency 边并参与 DAG / orphan 校验；same-patch edge delta 指向 placeholder 会 fail-closed；历史 add-node 遇到后续真实 ticket 时会显式吸收，不再把 replay 打成 graph unavailable
- [x] 把 `TicketGraph / GraphHealth` 接到 placeholder 真相：placeholder node 现在会以 `is_placeholder=true / node_status=PLANNED / ticket_id=null / runtime_node_id=null` 出现在 graph snapshot；结构类 graph health 已纳入 placeholder，`affected_nodes` 不再把 placeholder `node_id` 冒充成 runtime node
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q` 通过（`37 passed`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory and patch" -q` 通过（`7 passed, 310 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_assets.py -k "graph_patch or board_advisory" -q` 通过（`2 passed, 5 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "advisory or graph_health" -q` 通过（`5 passed, 73 deselected`）
- [x] `python -m py_compile backend/app/contracts/advisory.py backend/app/contracts/ticket_graph.py backend/app/core/output_schemas.py backend/app/core/board_advisory.py backend/app/core/board_advisory_analysis.py backend/app/core/process_assets.py backend/app/core/graph_patch_reducer.py backend/app/core/ticket_graph.py backend/app/core/graph_health.py backend/app/core/approval_handlers.py backend/tests/test_ticket_graph.py backend/tests/test_api.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收口 graph patch / ticket graph / graph health 的内部合同，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder node 仍是 graph-only 真相，还没进入 runtime `node_projection` 或自动建票 materialization
- [ ] same-patch placeholder-to-placeholder 接线、review lane placeholder 仍未支持
- [ ] dedicated graph health history / workflow 级 SLA 配置 / 更细的 blocker-source attribution 仍未进入主链

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先决定 placeholder node 的 runtime materialization 是否拆成独立切片；runtime node_projection 的 graph-first 双层真相继续保持后置单独决策。`

### Session `2026-04-16 / 30`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 给 `execution_targets.py` 新增正式 `execution_target:board_advisory_analysis`，把 advisory analysis 从 `architect_governance_document` 旧 target 里拆出来
- [x] 把 `board_advisory_analysis.py` 收成 contract 驱动：真人 executor 改按 capability tags 选，compile worker binding / live provider selection / deterministic guard 现在共用同一套 execution plan
- [x] 把 advisory analysis 的错误口径收正到 fail-closed：命中 contract mismatch / missing provider selection / provider paused 时现在都会显式失败，并复用现有幂等 incident / recovery
- [x] 给 ticket create 合同新增最小 `graph_contract.lane_kind`；`graph_identity.py` 现已改成 contract 优先，maker-checker review / rework 建票路径也已显式写入 lane contract
- [x] 新增 `backend/app/core/graph_health_policy.py`，把 `GraphHealth` 的 threshold / multiplier / window / event whitelist / severity 从内核文件抽离；`build_graph_health_report()` 现已支持显式 `policy` 注入
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory_analysis" -q` 通过（`8 passed, 312 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_identity or graph_health" -q` 通过（`24 passed, 16 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "graph_health or advisory" -q` 通过（`5 passed, 73 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/core/board_advisory_analysis.py backend/app/core/graph_identity.py backend/app/core/graph_health.py backend/app/core/graph_health_policy.py backend/app/core/execution_targets.py backend/tests/test_api.py backend/tests/test_ticket_graph.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收口 advisory execution contract、graph lane contract 和 graph health policy，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder node 仍只停在 graph-only 真相，还没进入 runtime `node_projection` 或自动建票 materialization
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] `GraphHealth` 虽然已把 policy 常量外提，但 queue / stale / cross-version 这批 runtime-liveness finding 仍继续依赖 ticket/node projection 的时间与 SLA 字段

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先决定 GraphHealth 的 runtime-liveness 规则是否后移出 graph 内核；placeholder runtime materialization 和 runtime node_projection 双层真相继续保持后置单独决策。`

### Session `2026-04-16 / 31`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `board_advisory_analysis.py` 收到主线 live-only success path：没有真实 board-approved contract-matching executor、没有 advisory target provider selection、或 provider paused 时都会显式失败；synthetic executor 已退出 command 主链成功路径
- [x] 把 graph lane 核心判断收成 contract-only：`resolve_graph_lane_kind()` 现在只认 `graph_contract.lane_kind`；legacy maker-checker / rework taxonomy 已移到单点 compat adapter，新票路径会补正式 execution lane contract
- [x] 新增 `backend/app/core/runtime_liveness.py` 与 `RuntimeLivenessReport`，把 `QUEUE_STARVATION / READY_BLOCKED_THRASHING / READY_NODE_STALE / CROSS_VERSION_SLA_BREACH` 从 `GraphHealthReport` 主读面拆出；`ProjectionSnapshot / CEO prompt / workflow_auto_advance` 现在会同时读 `graph_health_report + runtime_liveness_report`
- [x] 把 incident 主链按边界拆开：结构类 critical 保持 `GRAPH_HEALTH_CRITICAL`；liveness critical 改成 `RUNTIME_LIVENESS_CRITICAL`；liveness 构建失败改成 `RUNTIME_LIVENESS_UNAVAILABLE`
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q` 通过（`42 passed`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "graph_health or runtime_liveness or advisory" -q` 通过（`5 passed, 73 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory_analysis or graph_health or runtime_liveness" -q` 通过（`14 passed, 307 deselected`）
- [x] `D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/ceo.py backend/app/core/board_advisory_analysis.py backend/app/core/graph_identity.py backend/app/core/graph_health.py backend/app/core/runtime_liveness.py backend/app/core/ceo_snapshot.py backend/app/core/ceo_prompts.py backend/app/core/workflow_auto_advance.py backend/app/core/ticket_handlers.py backend/app/core/ticket_graph.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py backend/tests/test_ticket_graph.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收口 advisory 主链、graph contract 和 graph/runtime monitor 边界，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder node 仍只停在 graph-only 真相，还没进入 runtime `node_projection` 或自动建票 materialization
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] `RuntimeLivenessReport` 虽已独立，但 policy 仍复用 `graph_health_policy.py`；是否继续拆成双 policy contract 仍待后续单独决策

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先决定 placeholder runtime materialization 是否拆独立切片；runtime node_projection 双层真相继续保持后置，RuntimeLiveness/GraphHealth 的 policy contract 是否继续拆层单独决策。`

### Session `2026-04-16 / 32`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S4`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/runtime_node_views.py`，把 execution-lane graph node、graph-only placeholder 和持久化 `node_projection` 收成单点三态读面；同一 `node_id` 命中 placeholder/materialized 冲突、或 graph/runtime 不一致时现在会显式抛 `RuntimeNodeViewResolutionError`
- [x] 把 `Dependency Inspector` 接到这条新读面：graph-only placeholder 现在会直接显示在节点列表里，并新增 `is_placeholder / materialization_state`；依赖链继续按 graph truth 读取 `PARENT_OF + DEPENDS_ON`，不再因为缺 `node_projection` 就把 placeholder 当缺失节点
- [x] 把 `ticket-create / CEO create-ticket` 的节点存在性判断切到 runtime node view；placeholder `node_id` 现在允许进入正式建票并由现有 `EVENT_TICKET_CREATED -> node_projection` 主链物化，已 materialized 节点继续显式 reject
- [x] 同步更新前端 dependency inspector 类型和抽屉文案，让 placeholder 状态能直接显示给治理壳
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "placeholder or graph_patch" -q` 通过（`8 passed, 34 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "dependency_inspector or placeholder or create_ticket" -q` 通过（`8 passed, 315 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "placeholder or advisory" -q` 通过（`3 passed, 75 deselected`）
- [x] `python3 -m py_compile backend/app/core/runtime_node_views.py backend/app/core/projections.py backend/app/core/ticket_handlers.py backend/app/core/ceo_validator.py backend/app/core/ceo_proposer.py backend/tests/test_api.py` 通过
- [x] `cd frontend && npm run build` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只补 placeholder runtime 挂载读面和建票吸收，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder node 已进入 runtime read/create path，但仍没有进入持久化 `node_projection` 真相、scheduler 自动 materialization 或 graph-first placeholder lifecycle
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] `RuntimeLivenessReport` 虽已独立，但 policy 仍复用 `graph_health_policy.py`；是否继续拆成双 policy contract 仍待后续单独决策

**下一轮起手动作：**
`继续从 P4-S4 续跑，优先决定 placeholder runtime materialization 是否单独升格为下一切片；runtime node_projection 双层真相继续保持后置，RuntimeLiveness/GraphHealth 的 policy contract 是否继续拆层单独决策。`

### Session `2026-04-16 / 33`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S5`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/runtime_node_lifecycle.py`，把 runtime node lifecycle 收成单点 gate、稳定 reason code 和 typed error
- [x] 把 `ticket-create / CEO create-ticket` 改成统一走 lifecycle gate 判断 placeholder absorb / materialized reject，不再在本轮触达路径里从 `node_projection` 缺失反向猜状态
- [x] 把 `context_compiler / ticket-start / ticket-result-submit` 接到同一 lifecycle gate；命中 planned placeholder 时现在会显式 fail-closed，并稳定暴露 `PLANNED_PLACEHOLDER_NOT_MATERIALIZED`
- [x] 补了 placeholder 相关最小回归：compile、create-ticket、ticket-start、ticket-result-submit 和 scheduler tick 边界
- [x] 同步更新本计划和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k planned_placeholder -q` 通过（`1 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "ticket_start_rejects_planned_placeholder_before_materialization or ticket_result_submit_rejects_planned_placeholder_before_materialization or ticket_create_accepts_placeholder_node_and_materializes_runtime_truth" -q` 通过（`3 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k graph_only_placeholder -q` 通过（`1 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "placeholder or advisory" -q` 通过（`3 passed, 75 deselected`）
- [x] `python3 -m py_compile backend/app/core/runtime_node_lifecycle.py backend/app/core/runtime_node_views.py backend/app/core/ticket_handlers.py backend/app/core/context_compiler.py backend/app/core/ceo_validator.py backend/app/core/ceo_proposer.py` 通过

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只收口 placeholder lifecycle 协议，没有改变当前批次入口或 TODO 主线优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只补 runtime lifecycle gate，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder node 仍没有进入持久化 `node_projection` 真相、scheduler 自动 materialization 或 graph-first placeholder lifecycle
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] `RuntimeLivenessReport` 仍复用 `graph_health_policy.py`；是否继续拆成 graph/liveness 双 policy contract 仍待后续单独决策

**下一轮起手动作：**
`从 P4-S6 续跑，优先决定 placeholder 持久化 node_projection / 自动 materialization 是否要进入正式恢复链；RuntimeLiveness/GraphHealth 的 policy contract 拆层继续保持后置单独决策。`

### Session `2026-04-17 / 34`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S6`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/planned_placeholder_gate.py`，把 focused planned placeholder 的 autopilot 停滞检测收成单点 helper；当前最小口径只认 snapshot 已暴露的 `replan_focus.focus_node_ids`
- [x] 新增正式 `PLANNED_PLACEHOLDER_GATE_BLOCKED` incident，并把 `workflow_auto_advance` 的“version 没变化就直接 return”旧静默停滞改成显式 incident；这条主链不会补 projection、不会偷偷建票、不会隐式 fallback
- [x] 把 `incident detail / incident-resolve / IncidentDrawer` 接到现有 `RERUN_CEO_SHADOW` 恢复链；新 incident 现在固定暴露 `RERUN_CEO_SHADOW + RESTORE_ONLY`，缺 `trigger_type` 时 resolve 会显式 reject
- [x] 保持 graph/runtime 边界不变：graph-only placeholder 继续只存在于 graph truth，autopilot 对这类 incident 不再 auto-resolve，`ticket-create` 继续是唯一合法 materialization 入口
- [x] 同步更新本计划和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder_gate" -q` 通过（`2 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "placeholder_gate" -q` 通过（`3 passed, 325 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "placeholder or incident" -q` 通过（`2 passed, 76 deselected`）
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx` 通过（`6 passed`）
- [x] `python3 -m py_compile backend/app/core/planned_placeholder_gate.py backend/app/core/ticket_handlers.py backend/app/core/workflow_auto_advance.py backend/app/core/projections.py backend/app/core/constants.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py` 通过
- [ ] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder or incident or ceo_delegate" -q` 未全绿；当前会额外暴露 3 条旧 autopilot 宽桶问题，已记到“新发现但不在本轮做”

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只把 placeholder 自动停滞收成显式 incident/recovery，没有改变当前批次入口或 TODO 主线优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只补 autopilot placeholder incident 和恢复主链，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍没有进入持久化 `node_projection` 真相、scheduler 自动 materialization 或 graph-first placeholder lifecycle
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] `graph_health_policy.py` / `RuntimeLivenessReport` 的 policy contract 仍未继续拆层
- [ ] autopilot 宽桶里仍有 3 条旧回归待单独收口：generic approval auto-resolve、provider incident 恢复和 graph health cyclic path

**下一轮起手动作：**
`继续从 P4-S6 后续未完成项续跑；先判断 placeholder 是否需要进入正式 materialization/recovery 之外的真相层，再单独收口 autopilot 宽桶里那 3 条旧回归。`

### Session `2026-04-17 / 35`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S6`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/planned_placeholder_projection.py` 和 `backend/app/core/planned_placeholder_constants.py`，把 execution-lane graph-only placeholder 的持久化真相收成单点协议；当前最小状态只保留 `PLANNED / BLOCKED`
- [x] 在 `backend/app/db/schema.py`、`backend/app/db/repository.py` 新增 `planned_placeholder_projection` 表、仓库读写 helper 和投影刷新接线；placeholder 真相现在会随现有 projection rebuild 幂等重建
- [x] 把 `runtime_node_views.py` 从“graph + node_projection 现场猜 placeholder”改成“materialized 只认 node_projection、planned 只认 planned_placeholder_projection”；缺持久化 placeholder truth 或 graph/runtime 冲突时现在显式抛 `RuntimeNodeViewResolutionError`
- [x] 保持 `ticket-create` 仍是唯一合法 materialization 入口；真实建票成功后，placeholder row 会在下一次 refresh 中被吸收删除，incident resolve 不会偷偷把 placeholder 改成 materialized
- [x] 删除一批会污染新架构真相的旧兼容：placeholder 不再从 `node_projection` 缺失、incident/detail 读面或空值回退反向猜状态；命中这类不一致时统一 fail-closed
- [x] 顺手修了一条旧事务内快照 bug：`build_ticket_graph_snapshot(..., connection=...)` 现在会显式复用同一连接读取 workflow projection，不再在事务里悄悄读旧连接状态
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "placeholder" -q` 通过（`6 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k planned_placeholder -q` 通过（`1 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder_gate" -q` 通过（`2 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "placeholder or dependency_inspector or create_ticket" -q` 通过（`13 passed`）
- [x] `python3 -m py_compile backend/app/core/planned_placeholder_constants.py backend/app/core/planned_placeholder_projection.py backend/app/core/runtime_node_views.py backend/app/core/ticket_graph.py backend/app/db/repository.py backend/tests/test_ticket_graph.py backend/tests/test_context_compiler.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只补 placeholder 持久化真相和 fail-closed 读面，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 现在已有独立持久化 `planned_placeholder_projection`，但仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] autopilot 宽桶里仍有 3 条旧回归待单独收口：generic approval auto-resolve、provider incident 恢复和 graph health cyclic path

**下一轮起手动作：**
`继续从 P4-S6 续跑，优先决定 placeholder 持久化真相是否要继续升格到 scheduler/recovery 之外的正式 materialization 协议；autopilot 宽桶里的 3 条旧回归继续后置单独收口。`

### Session `2026-04-17 / 36`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S6`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 用新增回归把 placeholder materialization 边界钉死：`workflow_auto_advance` 开 gate incident 和 `incident-resolve` 走 `RERUN_CEO_SHADOW` 时都不会偷偷建票或把 planned placeholder 改成 materialized
- [x] 把 `workflow_auto_advance` 改成先处理 open approval / open incident，再 build snapshot；autopilot 的 `ceo_delegate` 审批和 provider incident 恢复不再先被旧 blocker 顺序卡住
- [x] 把 `TicketGraph` 的 same-lane retry lineage self `PARENT_OF` 边删掉，收掉 provider 单节点失败流触发的 graph health cyclic path
- [x] 补齐测试时钟基座到 `runtime_liveness / graph_health`，让 provider recovery 的时间窗回归按显式测试时间跑，不再夹带宿主机当前时间
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "autopilot_auto_advance_resolves_generic_open_approval_via_ceo_delegate or autopilot_auto_advance_resolves_provider_incident_and_retries_latest_failure or autopilot_auto_advance_restores_provider_incident_when_source_ticket_already_completed" -q` 通过
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder or incident or ceo_delegate" -q` 通过
- [x] `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "test_scheduler_runner_auto_recovers_open_provider_incident_for_autopilot_workflow" -q` 通过
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "graph_health or same_lane_retry_parent_self_edge" -q` 通过
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "placeholder_gate_incident_resolve_reruns_shadow_and_closes_incident" -q` 通过
- [x] `python3 -m py_compile backend/app/core/workflow_auto_advance.py backend/app/core/ticket_graph.py backend/tests/conftest.py backend/tests/test_workflow_autopilot.py backend/tests/test_ticket_graph.py backend/tests/test_api.py` 通过
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "provider_incident_resolve or placeholder_gate_incident_resolve" -q` 未全绿；命中一条旧 `wf_seed` 测试 helper 建链缺口，已记录到“新发现但不在本轮做”

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收口 autopilot orchestration、graph self-edge 和测试时钟基座，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] runtime `node_projection` 仍沿用共享 runtime `node_id` 主键；graph-first 双层身份还没拆
- [ ] `RuntimeLivenessReport` / `graph_health_policy.py` 仍未继续拆成 graph/liveness 双 policy contract
- [ ] `test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure` 这条旧 API helper 仍依赖 `wf_seed` 预建 workflow，后续若要恢复宽桶验证，需要单独清这条老测试入口

**下一轮起手动作：**
`继续从 P4-S6 后续未完成项续跑；保持 placeholder materialization 边界冻结，优先决定 runtime node_projection 双层真相和 graph/liveness policy contract 是否要单独开下一切片。`

### Session `2026-04-17 / 37`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 在 `backend/app/db/schema.py`、`backend/app/core/reducer.py`、`backend/app/db/repository.py` 新增正式 `runtime_node_projection` 表、幂等 reducer 和仓库 helper；当前只让 execution lane 的 materialized runtime node 进入这层真相
- [x] 把 `runtime_node_views.py` 收正到 “materialized 只认 `runtime_node_projection`、planned 只认 `planned_placeholder_projection`”；execution graph node 缺 runtime row、runtime row 脱离 graph、graph/runtime identity 对不上时现在都会显式 `RuntimeNodeViewResolutionError`
- [x] 把 `CompileRequestMeta / CompiledExecutionPackageMeta` 接到 `runtime_node_projection_version`；`context_compiler / ticket-start / ticket-result-submit / runtime runner` 现在会对 execution lane 显式校验 runtime node version，不再从 legacy `node_projection` 缺失反推执行态
- [x] 保持 review lane 的兼容边界显式不变：`ticket-lease / ticket-start / ticket-result-submit / ticket-complete` 对 review lane 继续读 legacy `node_projection`，只把 execution lane 切到新 runtime truth，避免 review 票污染 execution runtime 真相
- [x] 把 `Dependency Inspector` 和 `TicketGraph` 补齐 `graph_node_id / runtime_node_id` 读面；当前读面已经能把 graph identity 和 runtime identity 分开看
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "runtime_node or placeholder or graph_health" -q` 通过（`19 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k "runtime_node or planned_placeholder or captures_projection_versions" -q` 通过（`2 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "create_ticket or dependency_inspector or ticket_start or ticket_result_submit" -q` 通过（`32 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder or incident" -q` 通过（`6 passed`）
- [x] `python3 -m py_compile backend/app/core/context_compiler.py backend/app/core/ticket_handlers.py backend/app/core/ticket_graph.py backend/app/core/runtime_node_views.py backend/app/core/runtime.py backend/app/core/reducer.py backend/app/db/repository.py backend/app/core/planned_placeholder_projection.py backend/app/contracts/runtime.py backend/app/contracts/commands.py backend/app/contracts/projections.py backend/app/core/projections.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收 execution-lane runtime truth 和版本门禁，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] review lane / approval target / worker runtime 仍未继续拆成 graph-first 双层真相
- [ ] `graph_health_policy.py` / `RuntimeLivenessReport` 仍未继续拆成 graph/liveness 双 policy contract

**下一轮起手动作：**
`继续从 P4-S7 后续未完成项续跑；先决定 review lane / approval target / worker runtime 是否继续拆成 graph-first 双层真相，再决定 graph/liveness policy contract 是否单独开下一切片。`

---

### Session `2026-04-17 / 38`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `backend/app/core/reducer.py` 的 `runtime_node_projection` 重建从 execution-only 扩到所有 materialized graph lane；maker-checker review 现在也会稳定落 `graph_node_id=<runtime_node_id>::review` 的 runtime truth
- [x] 把 `backend/app/core/runtime_node_views.py` 收成 graph-lane 真相入口；materialized lane 现在统一只认 `runtime_node_projection`，execution placeholder 继续只认 `planned_placeholder_projection`
- [x] 把 `context_compiler / ticket-start / ticket-result-submit / ticket-complete / runtime runner` 全部改成“先解 graph identity，再读 graph-lane runtime truth”；review lane 现在也会显式校验 `runtime_node_projection_version`
- [x] 给 review pack subject 补正式 `source_graph_node_id`，并把 `approval target` 切到 `source_graph_node_id + runtime_node_projection`；旧的 `source_node_id + node_projection` 主校验已退出
- [x] 把 `RuntimeLivenessReport` 改成先校验所有 materialized graph lane 的 runtime truth，再读 lane-scoped `runtime_node_projection.updated_at / version / latest_ticket_id`；lane-backed graph/runtime 不一致时现在会显式 `RuntimeLivenessUnavailableError`
- [x] 删掉一批会污染新架构真相的旧兼容：review lane runtime 不再借 legacy `node_projection` 主校验，runtime runner 不再直接拿 `ticket.node_id` 查 runtime row，approval target 不再按 shared `node_id` 猜当前 graph lane
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "runtime_node or placeholder or graph_health" -q` 通过（`20 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_context_compiler.py -k "runtime_node or captures_projection_versions" -q` 通过（`2 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "runtime_node_projection_version or maker_checker or projection_is_not_currently_blocked" -q` 通过（`7 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "runtime_governance_gate or maker_checker or runtime_runner_executes_leased_review_lane_ticket" -q` 通过（`1 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "runtime_liveness or QUEUE_STARVATION" -q` 通过（`1 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/core/reducer.py backend/app/core/runtime_node_views.py backend/app/core/context_compiler.py backend/app/core/ticket_handlers.py backend/app/core/runtime.py backend/app/core/runtime_liveness.py backend/app/core/approval_handlers.py backend/tests/test_ticket_graph.py backend/tests/test_context_compiler.py backend/tests/test_api.py backend/tests/test_scheduler_runner.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收 review lane / approval target / runtime liveness 的 graph-first runtime truth，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] legacy `node_projection` 仍保留在部分读面和历史 helper 兼容壳里，后续若要继续收缩需要单独清点消费面
- [ ] `graph_health_policy.py` / `RuntimeLivenessReport` 仍未继续拆成 graph/liveness 双 policy contract

**下一轮起手动作：**
`继续从 P4-S7 后续未完成项续跑；优先决定 legacy node_projection 兼容壳是否还能继续收缩，再判断 graph/liveness policy contract 是否单独开下一切片。`

---

### Session `2026-04-17 / 39`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 `backend/app/core/runtime_liveness_policy.py`，把 `QUEUE_STARVATION / READY_BLOCKED_THRASHING / READY_NODE_STALE / CROSS_VERSION_SLA_BREACH` 的阈值、事件窗口和 severity 从 `graph_health_policy.py` 正式拆出去
- [x] 把 `backend/app/core/runtime_liveness.py` 改成只消费 `RuntimeLivenessPolicy`；`GraphHealthReportDigest / RuntimeLivenessReportDigest / CEO snapshot` 的外部字段保持不变
- [x] 删掉 `backend/app/core/graph_health.py` 里会污染新架构真相的 runtime-specific 死代码；图健康内核现在只保留结构类规则，不再夹 runtime stale/queue 推导
- [x] 把 `scan_and_open_required_hook_gate_incidents()` 改成按 `resolve_ticket_graph_identity() + build_runtime_graph_node_views()` 判断当前 graph lane；review lane required hook gate 不再受 stale shared `node_projection.latest_ticket_id` 污染
- [x] 同步补了回归：新增 review lane stale `node_projection` 的 required hook gate 用例，policy contract 断言也已切到 `runtime_liveness_policy`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_role_hooks.py -k "review_lane_runtime_truth_even_when_node_projection_is_stale" -q` 通过（`1 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "policy_override_for_ready_node_stale_threshold or graph_health_policy_contract_excludes_runtime_liveness_thresholds" -q` 通过（`2 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_health or runtime_liveness or runtime_node" -q` 通过（`30 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "runtime_node_projection_version or graph_health or runtime_liveness" -q` 通过（`9 passed, 323 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_workflow_autopilot.py -k "runtime_liveness or incident or placeholder" -q` 通过（`6 passed, 8 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "runtime_liveness or graph_health" -q` 通过（`2 passed, 76 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/core/role_hooks.py backend/app/core/graph_health.py backend/app/core/graph_health_policy.py backend/app/core/runtime_liveness.py backend/app/core/runtime_liveness_policy.py backend/tests/test_role_hooks.py backend/tests/test_ticket_graph.py` 通过
- [ ] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_role_hooks.py -q` 未全绿；当前会命中一组旧 helper/receipt 假设，已记到“新发现但不在本轮做”

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只继续收口 graph-first runtime truth 和 policy contract，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] `workflow_relationships / context_compiler` 等混合读面仍保留 legacy `node_projection` 兼容壳
- [ ] review pack / advisory 的 `source_node_id` 仍只收成展示兼容字段，还没继续清点所有消费面
- [ ] `backend/tests/test_role_hooks.py -q` 仍有一组旧 helper 假设需要单独清理

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先清点 workflow_relationships / context_compiler 里的 legacy node_projection 兼容壳，再单独处理 role_hooks 全桶里的旧 helper 假设。`

---

### Session `2026-04-17 / 40`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 在 `backend/app/core/workflow_relationships.py` 新增 graph-first `resolve_runtime_org_context_relations()`；运行态 org context 现在只读 `TicketGraphSnapshot + graph_identity + ticket_projection`，不再把 `node_projection` 当运行态真相
- [x] 把 `backend/app/core/context_compiler.py` 的 `_build_org_context()` 改成只吃这条新入口；upstream / collaborators / downstream reviewer 不再按 `parent_ticket_id + shared node_id` 猜关系，open review pack 也改成 `source_graph_node_id -> source_ticket_id` 主判
- [x] 删掉一批会污染新架构真相的旧兼容推导：compiler 不再按 `source_node_id` 匹配 open review pack，不再按 incident `node_id` 猜 lane，也不再从展示快照反推运行态 org context
- [x] 把 `backend/tests/test_role_hooks.py` 和 `backend/tests/test_context_compiler.py` 的旧 helper 收正成显式 harness：补 scoped workflow / provider 前置、create/lease/start/submit 全部断言 `ACCEPTED`、删 receipt 前先确认 receipt 已落盘；原先整桶红灯现已收绿

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_role_hooks.py -q` 通过（`14 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_context_compiler.py -q` 通过（`38 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "dependency_inspector or runtime_node_projection_version or maker_checker" -q` 通过（`11 passed, 321 deselected`）
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/core/workflow_relationships.py backend/app/core/context_compiler.py backend/app/core/projections.py backend/tests/test_role_hooks.py backend/tests/test_context_compiler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只继续收缩 graph-first runtime truth 和测试 harness，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] `workflow_relationships` 展示快照仍直接读 legacy `node_projection`；运行态 org context 已切出，但展示层兼容壳还没单独清
- [ ] review pack / advisory 的 `source_node_id` 仍只保留为展示兼容字段，相关消费面还没全量清点

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先清点 projection / dashboard 这类展示层对 legacy node_projection 与 source_node_id 的剩余消费面，再判断是否继续收缩 shared node 兼容字段。`

---

### Session `2026-04-17 / 41`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增 graph-first 读面 subject resolver：`source_graph_node_id` 优先，稳定兼容入口只负责解析旧 payload，不再从 stale `node_projection` 反向猜当前 lane
- [x] 把 `Dependency Inspector` 的 open approval 关联改成按 `graph_node_id` 命中；`source_node_id` 被改坏时仍能通过 `source_graph_node_id` 绑定正确 review lane
- [x] 把 `Meeting Detail` 合同和前端类型补上 `source_graph_node_id`，`MeetingRoomDrawer` 也改为优先展示 graph node
- [x] 把 `approval_handlers` 的 board review projection guard 和 advisory artifact subject 解析接到同一套 graph-first subject resolver；写入事件和 artifact 仍保留 `source_node_id` 兼容字段，不在本轮改 command/event 合同
- [x] 同步更新本计划、`doc/TODO.md` 和 `doc/history/memory-log.md`

**验证结果：**
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "test_dependency_inspector_prefers_source_graph_node_id_for_open_review_pack_match" -q` 先红后绿
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_meeting_room.py -k "test_meeting_projection_exposes_source_graph_node_id" -q` 先红后绿
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/MeetingRoomDrawer.test.tsx` 先红后绿
- [x] `./backend/.venv/Scripts/python.exe -m py_compile backend/app/core/review_subjects.py backend/app/core/projections.py backend/app/core/approval_handlers.py backend/app/contracts/projections.py` 通过
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "dependency_inspector or review_room or meeting_detail or runtime_node_projection_version" -q` 通过（`21 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_meeting_room.py -k "meeting_projection_exposes_source_graph_node_id" -q` 通过（`1 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_context_compiler.py -k "review_pack or source_graph_node_id" -q` 通过（`1 passed`）
- [x] `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_role_hooks.py -q` 通过（`14 passed`）
- [x] `cd frontend && npm run test:run -- src/test/__tests__/components/MeetingRoomDrawer.test.tsx src/test/__tests__/components/ReviewRoomDrawer.test.tsx src/test/__tests__/pages/dashboard-page-detail-state.test.tsx` 通过（`11 passed`）
- [x] `cd frontend && npm run build` 通过
- [ ] `backend/tests/test_meeting_room.py::test_meeting_request_creates_open_meeting_projection_and_ticket` 仍会命中现有 `meeting-request` 缺 `graph_contract.lane_kind` 的旧入口问题；本轮没有把它纳入修复，避免越界改 meeting command 主链

**文档更新：**
- [x] 本计划已更新
- [x] `doc/TODO.md` 已更新
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收口 graph-first 读面主判和展示字段，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] review pack / advisory / meeting 的写入载荷仍保留 `source_node_id` 兼容字段，彻底 graph-only 化需要单独切片
- [ ] `workflow_relationships` 展示快照仍直接读 legacy `node_projection`；运行态 org context 和本轮读面主判已经不再受它驱动
- [ ] meeting command 主链缺 `graph_contract.lane_kind` 的旧入口问题仍未收口

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先决定是否单独处理 meeting command 的 graph_contract.lane_kind 缺口，或继续清 workflow_relationships / dashboard 展示层的 legacy node_projection 兼容壳。`

---

### Session `2026-04-17 / 42`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `backend/app/core/meeting_handlers.py` 的 meeting 建票入口补成正式 graph contract：meeting ticket 现在显式写 `graph_contract={"lane_kind":"execution"}`，`MEETING_REQUESTED / MEETING_STARTED` 事件和 `meeting_projection` 也会同步写 `source_graph_node_id`
- [x] 把 meeting graph-first 读写链继续收口：`build_meeting_projection()` 和 `ceo_snapshot` 的 recent closed meeting reuse candidate 现在都优先读持久化 `source_graph_node_id`；meeting projection 的 graph id 不再依赖 legacy `source_node_id` 反推
- [x] 删掉一条会污染新架构真相的旧兼容：`resolve_review_subject_identity()` 不再允许“有 `source_ticket_id` 但解不出 graph identity 时退回 `source_node_id`”；现在缺 graph truth 会直接显式失败
- [x] 顺手补平一条同类旧入口：meeting-backed `consensus_document` 票现在会显式跳过 provider precondition gate，继续走本地 deterministic meeting runtime；`approval_handlers` 的 board-approved follow-up 直建票路径也已补正式 `graph_contract`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_meeting_room.py -q` 通过（`7 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "meeting or dependency_inspector or review_room" -q` 通过（`25 passed, 308 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k "review_pack or source_graph_node_id" -q` 通过（`1 passed, 37 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "graph_contract or runtime_node" -q` 通过（`9 passed, 40 deselected`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "reuse_candidates" -q` 通过（`5 passed, 73 deselected`）
- [x] `python3 -m py_compile backend/app/core/meeting_handlers.py backend/app/core/review_subjects.py backend/app/core/projections.py backend/app/core/ceo_snapshot.py backend/app/core/ticket_handlers.py backend/app/core/approval_handlers.py backend/app/db/repository.py backend/app/db/schema.py backend/tests/test_meeting_room.py backend/tests/test_api.py backend/tests/test_ticket_graph.py backend/tests/test_ceo_scheduler.py` 通过

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只补 `P4-S7` 已锁定的 meeting graph-first 子缺口，没有改变当前批次入口、阶段目标或优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只修 meeting 主链合同和 graph-first 读写链，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] `workflow_relationships` 展示快照仍直接读 legacy `node_projection`；展示层兼容壳还没单独清
- [ ] review pack / advisory / meeting 的写入载荷仍保留 `source_node_id` 兼容字段，彻底 graph-only 化需要单独切片

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先清点 projection / dashboard / workflow_relationships 这类展示层对 legacy node_projection 的剩余消费面，再决定是否继续收缩 source_node_id 双写兼容字段。`

---

### Session `2026-04-17 / 43`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `workflow_relationships.list_workflow_ticket_snapshots()` 改成 graph-first 展示快照：现在只读 `TicketGraphSnapshot + ticket_projection + created_spec`，不再从 `node_projection` 猜 `phase / parent / node_status`
- [x] 把 dashboard `pipeline_summary` 收到 graph/runtime truth：phase 计数改读 `ticket_projection`，blocked / critical-path 继续复用 `TicketGraph` 索引；stale `node_projection` 不再改写 dashboard 阶段状态
- [x] 把 dependency inspector 接到这层新读面：节点展示继续保留 `parent / dependency / artifact scope / blocking reason`，但主判已经不再依赖 legacy `node_projection`
- [x] 删掉一条会污染新架构真相的旧兼容：`resolve_review_subject_identity()` 不再接受只有 `source_node_id` 的 legacy subject；open approval 命中现在只认 `source_graph_node_id`
- [x] 顺手把 CEO recent closed meeting reuse candidate 的旧 fallback 收紧：已有持久化 `source_graph_node_id` 时，不再回退 `source_node_id`

**验证结果：**
- [x] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "dashboard_pipeline_summary or dependency_inspector" -q` 通过（`13 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_meeting_room.py -q` 通过（`7 passed`）
- [x] `./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "reuse_candidates" -q` 通过（`5 passed, 73 deselected`）
- [x] `python3 -m py_compile backend/app/core/workflow_relationships.py backend/app/core/projections.py backend/app/core/ceo_snapshot.py backend/app/core/review_subjects.py backend/tests/test_api.py` 通过

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只续跑 `P4-S7` 已锁定的展示层 graph-first 收口，没有改变当前批次入口、阶段目标或优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只收展示层和读面真相，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] recent completed consensus gate 和少数历史 helper 仍直接读 legacy `node_projection`
- [ ] review pack / advisory / meeting 写入载荷仍保留 `source_node_id` 兼容字段；彻底 graph-only 化要单独开切片

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先清剩余 history/read helper 对 legacy node_projection 的消费面，再决定是否单独推进 source_node_id 双写兼容字段的进一步收缩。`

---

### Session `2026-04-17 / 44`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `backend/app/core/ceo_snapshot.py` 的 recent completed reuse candidate 改成 graph-first；`consensus_document` 现在按当前 graph lane 的 completed truth 判定可复用，不再被 stale / 缺失的 legacy `node_projection` 误伤
- [x] 把 `backend/app/core/ceo_meeting_policy.py`、`backend/app/core/ceo_validator.py`、`backend/app/contracts/ceo_actions.py` 和 `backend/app/core/ceo_proposer.py` 一起收口到 `source_graph_node_id` 主判；缺 graph truth 时显式失败，不再回退 `source_node_id` 或 shared `node_projection`
- [x] 把 `backend/app/core/workflow_autopilot.py` 的 closeout report helper、以及 `backend/app/core/workflow_controller.py` 的 closeout completion 判定改成只吃 `TicketGraphSnapshot.node_status`；stale `node_projection` 不再把 closeout 判定打回未完成
- [x] 顺手删掉一条会污染新架构真相的旧兼容：`REQUEST_MEETING` 的 snapshot candidate 匹配和 graph truth 存在性校验不再让 `source_node_id` 单独成真

**验证结果：**
- [x] `py -m pytest backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_reuse_candidates_ignore_stale_node_projection_for_approved_consensus backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_includes_failed_ticket_meeting_candidate backend/tests/test_ceo_scheduler.py::test_ceo_validator_rejects_request_meeting_when_source_graph_node_id_mismatches_snapshot_candidate backend/tests/test_workflow_autopilot.py::test_autopilot_closeout_chain_report_ignores_stale_node_projection -q` 先红后绿，最终通过（`4 passed`）
- [x] `py -m pytest backend/tests/test_ceo_scheduler.py -k "reuse_candidates or consensus or meeting_candidates or request_meeting" -q` 通过（`9 passed, 71 deselected`）
- [x] `py -m pytest backend/tests/test_api.py -k "dashboard_pipeline_summary or dependency_inspector or review_room" -q` 通过（`24 passed, 312 deselected`）
- [x] `py -m pytest backend/tests/test_workflow_autopilot.py -k "graph or placeholder or incident" -q` 通过（`6 passed, 9 deselected`）
- [x] `py -m py_compile backend/app/core/ceo_snapshot.py backend/app/core/workflow_autopilot.py backend/app/core/workflow_controller.py backend/app/core/ceo_meeting_policy.py backend/app/core/ceo_validator.py backend/app/core/ceo_proposer.py backend/app/contracts/ceo_actions.py backend/tests/test_ceo_scheduler.py backend/tests/test_workflow_autopilot.py` 通过

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只续跑 `P4-S7` 已锁定的 history/read helper graph-first 收口，没有改变当前批次入口、阶段目标或优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只继续收缩 graph-first 真相来源和 closeout/read helper，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] `ceo_proposer` 的部分 create-ticket/closeout existence guard 和 controller 的少数治理推进输入仍直接读 legacy `node_projection`
- [ ] review pack / advisory / meeting 写入载荷仍保留 `source_node_id` 兼容字段；彻底 graph-only 化要单独开切片

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先清 ceo_proposer / controller 这类 command-side helper 对 legacy node_projection 的剩余消费面，再决定 source_node_id 双写兼容是否单独继续收缩。`

---

### Session `2026-04-18 / 45`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 把 `backend/app/core/workflow_controller.py` 的 command-side existing-ticket 判定收回 `ticket_projection` 当前真相：governance progression、architect gate 和 backlog followup 不再依赖 stale `workflow_nodes.latest_ticket_id`
- [x] 把 `backend/app/core/ceo_proposer.py` 的 backlog followup existence guard 收到 `capability_plan.followup_ticket_plans[].existing_ticket_id`；上游 followup 的 legacy `node_projection` 被删掉时，下游依赖票仍能继续 fanout
- [x] 删掉 `ceo_proposer` 里会误挡 closeout 的旧 compat guard：没有真实 closeout ticket 时，stale `node_ceo_delivery_closeout` row 不再阻断 deterministic closeout batch
- [x] 顺手补齐一条同链 graph subject：controller 生成的 meeting candidate 现在会显式带 `source_graph_node_id`，`REQUEST_MEETING` 不再因为 command-side candidate 缺 graph subject 而在 proposer 阶段报错

**验证结果：**
- [x] `py -m pytest backend/tests/test_ceo_scheduler.py::test_backlog_followup_batch_uses_existing_ticket_ids_from_capability_plan_when_node_projection_is_stale backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_keeps_existing_governance_ticket_plan_when_node_projection_is_stale backend/tests/test_ceo_scheduler.py::test_autopilot_closeout_batch_ignores_stale_closeout_node_projection_without_closeout_ticket -q` 先红后绿，最终通过（`3 passed`）
- [x] `py -m pytest backend/tests/test_ceo_scheduler.py::test_autopilot_completed_atomic_task_does_not_auto_create_closeout_ticket_before_full_delivery_chain backend/tests/test_ceo_scheduler.py::test_autopilot_governance_only_workflow_does_not_auto_create_closeout_ticket backend/tests/test_ceo_scheduler.py::test_autopilot_closeout_batch_ignores_stale_closeout_node_projection_without_closeout_ticket backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_exposes_capability_plan_for_backlog_followups backend/tests/test_ceo_scheduler.py::test_backlog_followup_batch_uses_existing_ticket_ids_from_capability_plan_when_node_projection_is_stale backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_requires_next_governance_document_before_backlog_fanout backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_keeps_existing_governance_ticket_plan_when_node_projection_is_stale backend/tests/test_ceo_scheduler.py::test_ceo_shadow_run_creates_architect_governance_ticket_before_backlog_followup_when_doc_is_missing backend/tests/test_ceo_scheduler.py::test_ceo_shadow_run_requests_meeting_before_backlog_followup_when_required -q` 通过（`10 passed`）
- [x] `py -m py_compile backend/app/core/workflow_controller.py backend/app/core/ceo_proposer.py backend/tests/test_ceo_scheduler.py` 通过
- [ ] `py -m pytest backend/tests/test_ceo_scheduler.py -q` 未全绿；剩余 3 条 advisory analysis 历史用例会把 session 落成 `ANALYSIS_REJECTED`，后续 `board-advisory-apply-patch` 因 `latest_patch_proposal_ref=None` 返回 `422`

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只续跑 `P4-S7` 已锁定的 command-side helper graph-first 收口，没有改变当前批次入口、阶段目标或优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只继续收缩 `workflow_controller / ceo_proposer` 的 graph-first 真相来源，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] review pack / advisory / meeting 写入载荷仍保留 `source_node_id + source_graph_node_id` 双写兼容字段；彻底 graph-only 化需要单独切片
- [ ] advisory analysis 这条历史链当前会把 session 落成 `ANALYSIS_REJECTED`；是否纳入下一轮，需要先判断它是不是 `P4-S7` 的同链缺口

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先决定 review/advisory/meeting 的 source_node_id 双写兼容是否继续收缩，或把 advisory analysis 的 ANALYSIS_REJECTED 历史口子单独拆成下一条切片。`

---

### Session `2026-04-18 / 46`
**开始前判断：**
- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 是否继续上轮：`yes`

**本轮做了什么：**
- [x] 新增单点 graph-first execution target resolver：`backend/app/core/review_subjects.py` 现在会把 review lane `source_graph_node_id` 显式映射到 execution lane target，不再让 stale `source_node_id` 反向主导 advisory branch
- [x] 把 `backend/app/core/board_advisory.py` 的 `affected_nodes` 收口到这条新 resolver；BoardAdvisorySession 不再把 legacy `source_node_id` 写成 graph patch target 真相
- [x] 把 `backend/app/core/approval_handlers.py` 和 `backend/app/core/board_advisory_analysis.py` 接到同一套 execution target：advisory change flow、analysis trace/archive、incident 和 patch artifact 现在统一按 graph-first execution branch 落点
- [x] 给 advisory analysis synthetic compile spec 补正式 `graph_contract={"lane_kind":"execution"}`，并把 `org_context` 改成按 source execution ticket 组包；缺 graph truth 时继续显式失败，不新增 fallback
- [x] 新增回归 `backend/tests/test_board_advisory_subjects.py`，锁定“review pack subject 已带 `source_graph_node_id` 时，advisory analysis 要忽略 stale legacy `source_node_id`”

**验证结果：**
- [x] `py -m pytest backend/tests/test_board_advisory_subjects.py -q` 先红后绿，最终通过（`1 passed`）
- [x] `py -m pytest backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_exposes_latest_board_advisory_decision backend/tests/test_ceo_scheduler.py::test_ceo_shadow_prompt_mentions_latest_board_advisory_decision backend/tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_exposes_full_timeline_archive_refs_for_applied_advisory_session -q` 通过（`3 passed`）
- [x] `py -m pytest backend/tests/test_api.py::test_dependency_inspector_prefers_source_graph_node_id_for_open_review_pack_match backend/tests/test_api.py::test_review_subject_identity_rejects_source_node_id_only_legacy_fallback -q` 通过（`2 passed`）
- [x] `py -m pytest backend/tests/test_ceo_scheduler.py -k "advisory or request_meeting or reuse_candidates" -q` 通过（`11 passed, 72 deselected`）
- [x] `py -m py_compile backend/app/core/review_subjects.py backend/app/core/board_advisory.py backend/app/core/board_advisory_analysis.py backend/app/core/approval_handlers.py backend/tests/test_board_advisory_subjects.py` 通过
- [ ] `py -m pytest backend/tests/test_api.py -k "board_advisory_request_analysis or board_advisory_apply_patch or advisory_context" -q` 未全绿；当前仍有 5 条 advisory 历史测试停在旧 analysis harness 假设或测试本身缺 `monkeypatch` fixture，不属于本轮 `P4-S7` graph-first subject 主链

**文档更新：**
- [x] 本计划已更新
- [ ] `doc/TODO.md` 未更新；原因：本轮只续跑 `P4-S7` 已锁定的 graph-first subject / advisory analysis compile contract 收口，没有改变当前批次入口、阶段目标或优先级
- [x] `doc/history/memory-log.md` 已更新
- [x] `README.md` 未更新；原因：本轮只继续收 advisory/meeting graph-first subject 真相和 advisory analysis compile contract，没有改变仓库入口叙事或运行方式

**留下的未完成项：**
- [ ] placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle
- [ ] review pack / advisory / meeting 写入载荷仍保留 `source_node_id + source_graph_node_id` 双写兼容字段；彻底 graph-only 化需要单独切片
- [ ] advisory analysis 宽口径 `test_api` 历史测试仍停在旧 harness 假设；如果下一轮要清，应该单独按 advisory execution contract / 测试基座收口，不应再混进 `P4-S7` subject 主链

**下一轮起手动作：**
`继续从 P4-S7 续跑；优先决定是否继续收缩 review/advisory/meeting 的 source_node_id 双写兼容，或把 advisory analysis 宽口径历史测试和 harness 假设单独拆成下一条切片。`

---

## 11. 新会话续跑指令

每次新会话先做这 6 步：

1. 读“固定输入文档”
2. 读本计划的“当前阶段”“任务清单核对区”“最近一条会话记录”
3. 确认当前切片状态
4. 先处理 `blocked` 和“未完成”
5. 再继续当前切片，不要重开新方向
6. 收尾前必须更新本计划和相关运行文档

---

## 12. 收尾检查

每次本轮实施结束前，必须手动核对：

- [x] 代码已落地
- [x] 有最小验证证据
- [x] 本计划状态已更新
- [x] 已完成项已勾选
- [x] 未完成项已保留
- [x] 新问题已记录到“偏差与待决策”
- [x] `doc/TODO.md` 已同步或明确说明为何没改
- [x] `doc/history/memory-log.md` 已补记
- [x] 没有修改 `doc/new-architecture/**`

---

## 13. 当前快照

这一段保持短，方便下次打开 10 秒内看懂。

- 当前阶段：`P4`
- 当前切片：`P4-S7`
- 当前状态：`P4-S7` 已完成第十批；review/advisory execution target 现在会从 graph-first subject 单点解析，BoardAdvisorySession affected_nodes、advisory analysis trace/archive/incident 和 synthetic compile contract 已退出 legacy source_node 主判`
- 最近完成：`review_subjects` 新增 execution target resolver；`board_advisory / approval_handlers / board_advisory_analysis` 已统一切到这条 graph-first execution branch，advisory analysis synthetic compile spec 也已补正式 `graph_contract`
- 当前阻塞：placeholder 仍未进入 `node_projection`、自动 scheduler materialization 或 graph-first placeholder lifecycle；review/advisory/meeting 写入载荷仍保留 `source_node_id` 双写兼容；`backend/tests/test_api.py -k "board_advisory_request_analysis or board_advisory_apply_patch or advisory_context" -q` 仍有 5 条 advisory 历史测试停在旧 harness 假设或测试基座缺口
- 下一步：`继续从 P4-S7 后续未完成项续跑；优先决定 source_node_id 双写兼容是否继续收缩，或把 advisory analysis 宽口径历史测试和 harness 假设单独拆成下一条切片`
