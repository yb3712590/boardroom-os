# 新架构重构实施计划

> 状态：`active`
> 当前阶段：`P1`
> 当前切片：`P1-S1`
> 最后更新：`2026-04-14 13:30`
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
| `P1` | 图与控制面收口 | 收正图协议、controller、ready 节点选择 | `in_progress` | 图成为正式真相面 |
| `P2` | 恢复与 Hook 收口 | Incident、Recovery、Hook 门禁接管主链 | `todo` | 失败显式化、后置动作制度化 |
| `P3` | 执行包与 CEO 收口 | 执行包、CEO 快照、技能绑定接管运行时 | `todo` | CEO / Worker 不再靠长提示词兜底 |
| `P4` | 顾问环与地图接入 | Board 顾问环、ProjectMap、健康监视接入 | `todo` | 可重规划、可诊断、可复盘 |

状态只允许用：

- `todo`
- `in_progress`
- `blocked`
- `done`

---

## 6. 当前阶段

### 当前阶段编号
`P1`

### 当前阶段目标
先把 TicketGraph、legacy adapter 和 ready/blocked 读面收成正式协议，让 controller / snapshot 不再继续直拼旧 ticket/node 语义。

### 当前阶段入口条件
- [x] 当前代码现实已核对
- [x] 本阶段相关架构文档已重读
- [x] 上一阶段的未完成项已转移
- [x] 本阶段切片范围已锁定
- [x] 验证方式已明确

### 当前阶段出口条件
- [ ] 本阶段所有必做切片完成
- [ ] 每个切片都有最小验证证据
- [ ] 涉及的运行文档已同步
- [ ] 未完成项已明确转移到下阶段或阻塞区
- [ ] `doc/history/memory-log.md` 已补记

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

---

## 8. 任务清单核对区

每次阶段结束后，必须逐项核对，不允许跳过。

### 已完成
- [x] `P0-S1` 已完成：系统冷启动现在会在 `repository.initialize()` 幂等写入单条 `SYSTEM_INITIALIZED`，`project-init` 不再兼任系统初始化入口
- [x] `P0-S2` 已完成：最小版本协议骨架现已落地；process asset canonical ref 改成 versioned ref，compiled bundle / manifest / execution package 会追加版本与 supersede 链，`GovernanceProfile` 与 workflow graph version 也已有只读查询入口
- [x] `P0-S3` 已完成：主线写路径现在已有显式 optimistic guard；`ticket-start` 可拒绝 stale ticket/node projection version，`ticket-result-submit` 可拒绝 stale `compiled_execution_package` ref，compile meta 也会写入 `ticket_projection_version / node_projection_version / source_projection_version`
- [x] `P0-S4` 已完成：`active-worktree-index.md` 与 ticket dossier 核心视图现在会走共享 `Boardroom` materializer；文档头固定带 `view_kind / generated_at / source_projection_version / source_refs / stale_check_key`，`doc-impact.md` 只读 `worker-postrun` receipt，`git-closeout.md` 只读 checkout/git closeout 事实输入
- [x] `P1-S1` 已完成：`TicketGraph` 最小合同和 legacy adapter 已落地；`ceo_snapshot / workflow_controller` 现在会读正式图摘要，invalid legacy dependency 会显式 blocked，graph version 也已把 `WORKFLOW_CREATED` 算进正式事件序列

### 未完成
- [ ] `P1-S2` 还没开始；下一轮继续把 controller ready-node / blocked 判定收成正式消费 `TicketGraph` 索引

### 明确放弃
- [ ] 暂无

### 新发现但不在本轮做
- [ ] `backend/tests/test_api.py -k "system_initialized or startup or project_init"` 仍会命中一组依赖 live provider 的旧 `project-init` 自动推进用例；当前环境未配 provider 时会落 `PROVIDER_REQUIRED_UNAVAILABLE`，不阻断 `P0-S1` 收口
- [ ] `compiled_context_bundle / compile_manifest` 的版本 ref 这轮已落库并进入 persisted payload，但 dashboard / review 读面还没显式消费；后续按 `P0-S4 / P1` 再接正式读面
- [ ] 宽口径 `board_approve` 回归桶当前仍会被一组旧的 governance/provider auto-advance 用例打断：scope review 批准后会在 `node_ceo_architecture_brief` 打开 `PROVIDER_REQUIRED_UNAVAILABLE -> REPEATED_FAILURE_ESCALATION` incident；这组不是本轮 stale-guard 主链回归，但下一轮要和 runtime/provider 历史测试一起收口
- [ ] `./backend/.venv/bin/pytest backend/tests/test_api.py -k "closeout_internal_checker_approved_returns_completion_summary" -q` 当前在本 worktree 和原工作区同提交都会因拿不到 `VISUAL_MILESTONE` 开放审批而失败；已确认不是本轮 `P0-S4` 引入的回归，后续和 closeout / approval 历史测试一起收口
- [ ] `TicketGraph` 这轮还是投影化图：dashboard、dependency inspector 和 graph patch 写路径都还没切过来；后续只能在现有图合同上扩，不能再回去直接加旧 projection 直读逻辑

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

- 当前阶段：`P1`
- 当前切片：`P1-S1`
- 当前状态：`P1-S1 已完成，TicketGraph 最小合同和图摘要读面已落地`
- 最近完成：`legacy ticket/node/projection 现在可归约成正式 TicketGraph；ceo_snapshot / workflow_controller 已开始读 ready/blocked 图摘要`
- 当前阻塞：`dashboard / dependency inspector 还没切到 TicketGraph，宽口径 governance/provider 与 closeout/approval 历史回归仍是旧失败`
- 下一步：`继续 P1-S2，把 controller ready-node / blocked 判定正式切到 TicketGraph 索引`
