# 迁移图

## TL;DR

这套新架构不是推倒重来。  
它更像一次收编：把当前主线已经有的事件、投影、执行包、过程资产、回执链，收成单一协议；把多处散落的 fallback、follow-up、治理文档口径，收成正式状态机。

## 设计目标

- 把新架构和当前主线一一对上，不留“听起来很对，但不知道怎么落”的空话。
- 明确哪些能力已经有雏形，哪些需要补单点协议，哪些应该冻结。
- 给后续重构提供可拆任务的迁移顺序。

## 非目标

- 不在这份图里直接展开代码级实现细节。
- 不把所有远期愿景都抬回当前主线。
- 不借迁移之名重开多租户、远程 handoff、平台化对象存储这些支线。

## 核心 Contract

### 1. 迁移原则

1. 单一 controller 优先于新增能力。
2. 正式 contract 优先于提示词约定。
3. 幂等恢复优先于静默 fallback。
4. 现有可运行链不断，目标协议逐段替换。

### 2. 现状映射表

| 新架构领域 | 当前主线基础 | 主要缺口 | 迁移动作 |
|---|---|---|---|
| 文档宪法 | 三分区目录、文档同步回执 | 文档职责和更新模式不够硬 | 收口文档面和物化规则 |
| Ticket 图引擎 | ticket、follow-up、dependency gate | 没有正式 `graph_version` 和一等边类型 | 抽图层和索引层 |
| Worker 执行包 | `compiled_execution_package`、写集、工具集 | 技能绑定、组织边界、分层预算不够正式 | 扩执行包合同 |
| CEO 记忆模型 | `ceo_shadow`、`task_sensemaking`、`capability_plan` | 没有正式分层协议和预算 | 收口 `ProjectionSnapshot` |
| Incident / Recovery | incident、circuit breaker、provider fallback | 幂等面分散、恢复动作不统一 | 建立 `RecoveryAction` 协议 |
| Hook 系统 | preflight、postrun、git closeout、evidence capture | 没有正式 registry 和门禁 | 把回执链升级成 hook |
| 技能运行时 | 会话层技能、人工约定 | 没有 runtime 绑定协议 | 把技能写进执行包 |
| 顾问环 | Board review、modify constraints、meeting ADR | 没有 `BoardAdvisorySession` | 连接顾问包和图补丁 |
| 过程资产 / 项目地图 | `input_process_asset_refs[]`、资产写回 | 没有一等 `ProjectMap` | 增地图和血缘刷新 |

### 3. 冻结区

迁移期间继续冻结这些方向：

- `worker-admin`
- 多租户 scope / 远程 worker handoff
- 可选对象存储平台化扩张
- 为未来假想场景预铺的新 provider 策略引擎

## 状态机 / 流程

### 分阶段迁移顺序

| Phase | 目标 | 完成口径 |
|---|---|---|
| `P0` | 术语和文档立法 | 新规格和当前主线映射稳定 |
| `P1` | 图协议收口 | `graph_version`、边类型、索引层到位 |
| `P2` | 恢复和 hook 收口 | `IncidentRecord`、`RecoveryAction`、`RoleHook` 正式接管 |
| `P3` | 执行包和 CEO 记忆收口 | `ProjectionSnapshot`、`SkillBinding`、执行包扩容 |
| `P4` | 顾问环和项目地图接入 | `BoardAdvisorySession`、`ProjectMap` 上线 |

### 当前优先级

按 [../roadmap-reset.md](../roadmap-reset.md) 的边界，这几个顺序不能乱：

1. 先收 controller、contract、delivery evidence。
2. 再收图协议、恢复协议、hook。
3. 最后再把顾问环和项目地图接进来。

也就是说，`ProjectMap` 很重要，但不能抢在主链协议统一之前先做成新复杂度。

## 失败与恢复

迁移期最容易犯的错有 4 类：

| 错误 | 后果 | 纠偏 |
|---|---|---|
| 一边保旧 controller，一边补新图协议 | 双真相并存 | 强制单一 controller |
| 只补文档，不补状态机 | 又回到文档地狱 | 先落 contract，再补读面 |
| 先补项目地图，不补恢复协议 | 地图有了，但系统还是乱恢复 | 先补 incident / hook |
| 用 fallback 兼容一切 | 真问题继续被遮住 | fail-closed + 显式 incident |

## 统一示例

`library_management_autopilot` 可以作为迁移验收样例：

### 迁移前问题

- 有治理文档
- 有很多票
- 有 review 痕迹
- 长时间卡在 build
- 没有稳定收口成真实交付

### 迁移后的验收口径

- 图里能看见正式 fanout 和关键依赖
- `source_code_delivery` 失败会开 incident，不会被 artifact JSON 混过去
- hook 会自动补文档、证据、git closeout
- Board 改约束时会生成 `BoardAdvisorySession` 和新图版本
- `closeout` 只在真实证据和真实资产齐全时打开

## 和现有主线的关系

这份迁移图默认同时参考：

- [../mainline-truth.md](../mainline-truth.md)
- [../roadmap-reset.md](../roadmap-reset.md)
- [../history/context-baseline.md](../history/context-baseline.md)

说白了，这份图不是另起一套世界观。  
它是把当前主线已经摸到的方向，重新排成一个不会继续长歪的顺序。
