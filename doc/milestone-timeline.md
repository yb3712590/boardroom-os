# Boardroom OS 里程碑时间线

> 版本：2.2
> 日期：2026-04-10
> 用法：这份文档现在只负责“当前状态 + 后续顺序 + 条件批次 + 远期储备”，不再代表实时代码真相，也不再保留过期周历。

## 零拷贝速览

- 当前代码真相仍以 `doc/mainline-truth.md` 和 `doc/TODO.md` 为准
- `M0` 到 `M5` 的核心主线能力大多已落地或已被现状吸收，但不代表每个原始交付物都按旧计划原样完成
- 旧口径下的 `M7` 已收口，但 2026-04-10 live 集成测试证明主线仍会退化成“文档式 artifact 交付”
- 新的最高优先级改为 `P0-COR` 主线纠偏批次，先收正 canonical 协议、单一 workflow controller、architect/meeting/source-code deliverable 硬约束
- 已归档的 [archive/specs/feature-spec.md](archive/specs/feature-spec.md) 第 `58–80` 条已经重新分层：已在规划内、条件纳入、远期储备、治理原则

## 一、里程碑状态总览

| 里程碑 | 名称 | 当前状态 | 现在怎么看 |
|--------|------|----------|------------|
| M0 | 基础重置 | 已吸收 | 主线与冻结边界已经收口，但 `P1-CLN-002/003` 仍因 blocker 未关闭 |
| M1 | 最小可行 CEO | 已吸收 | CEO 已真实执行首轮有限动作，自动会议也已进入窄主线 |
| M2 | 最小可行 Worker | 已吸收 | 当前主链 Worker、maker-checker、closeout 已真实运行，但 `BUILD` 主线仍是 artifact 交付，不是源码交付 |
| M3 | 人格模型与治理模板 | 部分吸收 | persona 已落地；治理模板与文档型角色仍未开启 |
| M4 | 前端重构 | 已吸收 | 前端壳、数据层、抽屉层和核心测试已完成重构收口 |
| M5 | 会议室协议 | 已吸收 | 最小会议室已落地；`P2-MTG-011` 已于 2026-04-07 收口 ADR 化决策视图，但 meeting 仍不是主线硬门禁 |
| M6 | 检索与 Provider | 未开启 | 继续作为后置增强，承接 `#58 #59 #62` 与既有 `P2-RET-* / P2-PRV-*` |
| M7 | 集成与交付口径收口 | 已完成（旧口径） | `P2-M7-001` 到 `P2-M7-005` 与手动纳入的 `P2-MTG-011` 已收口；但 closeout 仍偏文档交付，现由 `P0-COR` 继续纠偏 |
| M8 | 发布候选 | 未开启 | 只有在本地 MVP 已证明需要发布准备时才打开 |

## 二、已落地 / 已吸收里程碑

### M0：基础重置

- 当前已经吸收的部分：
  - `mainline-truth.md` 已成为主线与冻结边界的代码真相入口
  - `worker-admin` 与 `worker-runtime` 已完成 shim 迁移，真实实现进入 `_frozen/`
  - 冻结能力的真实入口、测试归属、阻塞摘要、路由组和共享表锚点都已有回归
- 当前未关闭的部分：
  - `P1-CLN-002`：多租户 shared scope shape 仍在，现已降为冻结后置
  - `P1-CLN-003`：upload 导入入口与 session 存储仍在，现已降为冻结后置

### M1：最小可行 CEO

- 已吸收为当前主线能力
- 当前真实执行动作是：
  - `CREATE_TICKET`
  - `RETRY_TICKET`
  - `HIRE_EMPLOYEE`
  - `REQUEST_MEETING`
- `ESCALATE_TO_BOARD` 当前仍是 `DEFERRED_SHADOW_ONLY`
- 这意味着后续任何和初始化澄清相关的设计，都必须按“受控 board review 路径”写，而不能假装 CEO 已有 live escalation

### M2：最小可行 Worker

- 已吸收为当前主线能力
- 当前主线已真实覆盖：
  - `consensus_document@1`
  - `implementation_bundle@1`
  - `delivery_check_report@1`
  - `ui_milestone_review@1`
  - `delivery_closeout_package@1`
- 当前这套主线已经能闭环，但 2026-04-10 live 长测证明它闭的是“结构化 artifact 交付”，不是“真实源码交付”
- 后续 `P0-COR-004/005` 会重写 `BUILD / CHECK / CLOSEOUT` 的完成定义，把源码交付、测试证据和硬门禁升成主线约束

### M3：人格模型与治理模板

- 已吸收的部分：
  - persona 真相源、执行包 `persona_summary`、staffing 画像可视化
  - `P2-GOV-002` 已于 2026-04-07 收口：统一只读 `role_templates_catalog` 现在同时覆盖 live 执行角色、未来执行角色预留、治理角色预留、文档类型和模板片段
- 仍未开启的部分：
  - `P2-GOV-003`：文档/设计型角色产物契约与可编译输入
  - `P2-GOV-004` 到 `P2-GOV-006`：文档链触发、角色边界和文档真相收口
  - `P2-RLS-001` 到 `P2-RLS-003`：新增角色进入 staffing / CEO / runtime 真实工作链
- 仍未被旧规划覆盖的部分：
  - `architect_primary` 真实招聘、真实使用、closeout 前硬断言
  - 治理会议何时必须发生、缺失时如何阻断主线
- 当前顺序前置条件：
  - 上述任务现在都排在 `P0-COR` 之后；`P2-DEC` 只完成了第一层派单与运行时边界解耦，当前要先完成主线纠偏，再继续角色纳入
- 对应已归档的 `archive/specs/feature-spec.md`：
  - `#60`、`#61` 已在规划内，但不是当前主线

### M4：前端重构

- 已吸收为当前主线能力
- 当前已经完成：
  - 数据层与 store 拆分
  - `App.tsx` 收回纯路由入口
  - 抽屉、焦点管理、骨架屏、懒加载、首页信息架构收口
- 后续前端工作只保留治理壳最小打磨，不再开新的前端大重构

### M5：会议室协议

- 最小会议室已落地并进入主线
- 当前会议能力边界：
  - 会议类型只开放 `TECHNICAL_DECISION`
  - 会议结果仍落在 `consensus_document@1`
  - 自动会议只在窄触发条件下开启
- 这层边界还不等于“治理讨论必须发生”
- 后续 `P0-COR-003` 会把 architect/meeting 从“允许发生”提升成特定 profile 下的硬约束
- 已吸收的后续增强：
  - `P2-MTG-011`：会议 `consensus_document@1` 现在可选携带 ADR 化 `decision_record`，Meeting Room 默认先看决策视图，会议来源 follow-up ticket 会额外注入 ADR 摘要

## 三、后续顺序

### 前置批次：`P0-COR` 主线纠偏

定位：新的最高优先级。2026-04-10 live 集成测试已经证明，当前主线虽然能跑到 closeout，但本质仍是“文档式 artifact 交付模拟器”。这批任务先把协议、控制器和硬门禁收正，再继续任何新角色、新 provider 或新治理增强。

对应任务：

- `P0-COR-001` 到 `P0-COR-006`

核心目标：

- 收正 canonical 协议：CEO action、provider config、runtime result、ticket deliverable 都只保留一套主线真相，alias 和隐式补推只允许留在兼容入口
- 收正单一 workflow controller：`workflow_auto_advance / scheduler_runner / ceo_scheduler / deterministic fallback` 不再各自维护业务推进语义
- 收正硬约束：`architect_primary` 真实招聘、真实 runtime 执行、必要治理 meeting 证据进入 closeout 前硬断言
- 收正交付形态：`BUILD` 主线从 `implementation_bundle` 迁到“真实源码交付包”，closeout 只接受代码、测试、构建与文档同步证据

补充约束：

- 不再默认接受“只写 `artifacts/...` JSON”作为 build 完成
- 不再允许 deterministic fallback 用模板化 `implementation_bundle / checker verdict / closeout package` 伪成功推进主线
- 这批任务优先级高于 `M6`、`C1` 和所有新角色扩张
- 这批任务不属于旧 `archive/specs/feature-spec.md #58-80` 的完整覆盖范围，属于 2026-04-10 live 集成测试新增纠偏项

建议拆分：

- `P0-COR-001`：canonical 协议收口
- `P0-COR-002`：单一 workflow controller
- `P0-COR-003`：architect / meeting 硬约束
- `P0-COR-004`：源码交付 contract 与 write set 重构
- `P0-COR-005`：checker / closeout 硬门禁
- `P0-COR-006`：live 场景回归与退出标准重建

### 前置批次：`P2-DEC` 派单边界与 role/runtime 解耦

定位：上一轮前置批次，已完成。但它只完成了第一层解耦，没有解决“主线仍按文档 artifact 交付”和“多控制器并存”的核心问题；后续由 `P0-COR` 接管。

对应任务：

- `P2-DEC-001` 到 `P2-DEC-004`

直接承接的 `archive/specs/feature-spec.md` 条目：

- `#76`：role template 不再充当 runtime 执行键
- `#77`：原子任务输入输出经由过程资产闭环，正式派单始终来自 CEO
- `#78`：scheduler 只做 readiness / lease / wakeup
- `#79`：CEO 不进入状态机，只读快照后输出动作
- `#80`：定时 + 事件双路径唤醒 CEO，避免调度停滞

补充约束：

- 不在这批任务里直接纳入 `backend_engineer / database_engineer / platform_sre / architect / cto`
- 不把 scheduler 扩成业务决策器，也不让 CEO 变成持久状态节点
- 不把过程资产闭环顺势扩成新的平台级子系统；只收正当前主链所需的输入、输出和唤醒边界

### M6：检索与 Provider

定位：后置增强，只在当前主链已经证明需要时打开。

对应任务：

- `P2-RET-001` 到 `P2-RET-006`
- `P2-PRV-001` 到 `P2-PRV-008`

直接承接的 `archive/specs/feature-spec.md` 条目：

- `#58`：角色级默认模型绑定
- `#59`：成本等级与参与频率路由
- `#62`：CEO / 文档角色 / 实施 Worker 模型解耦

补充约束：

- `M6` 相关改动如果继续碰运行时执行键或派单边界，应以后续 `P2-DEC-001/002` 的结果为前置
- `#63` 的最小组织上下文不默认塞进 M6 主体，只在 `P2-RET-006` 条件成立时打开
- `#69` 当前只允许吸收 `L1` 纪律；`L2` 仍由既有检索任务承接；`L3` 不进入当前阶段

### M7：集成、文档与交付口径收口

定位：不再承担“把全部愿景条目顺手落地”的职责，只收口当前主线和必要的软规则。

当前状态：

- `P2-M7-001` 到 `P2-M7-005` 已完成：当前主线、任务索引和里程碑状态已切到 `M7`，Review Room / completion 的最小证据可见性已经接到现有只读查看入口
- 手动纳入的 `P2-MTG-011` 也已完成：会议 `consensus_document@1` 现在可选携带 ADR 化 `decision_record`，Meeting Room 默认先看决策视图
- 当前这部分已收口；新的默认主线已经切到 `P0-COR` 主线纠偏批次，`P2-DEC` 保留为已完成的前置层

默认承接：

- 当前文档一致性与入口收口
- 当前主线的集成验证与 closeout 口径收口
- completion / review 证据默认消费面清理

可吸收但不默认开启的内容：

- `#68`：ADR 化共识文档与决策视图
- `#71`：closeout 证据软约束
- `#75`：文档同步软约束

明确不在 M7 默认打开的内容：

- `#65 SPIKE_TICKET`
- `#70` 项目地图
- `#72` 过程资产体系
- `#73` 组织学习闭环
- `#74` 文档治理引擎
- `#75` 硬状态机门禁

### M8：发布候选

定位：只有在本地 MVP 已证明需要发布准备时才打开。

当前仍后置的原因：

- 现阶段优先级仍是本地单机 MVP 主线稳定，而不是发布包装
- `P0-REL-*` 仍作为后续顺序的一部分，不进入当前活跃任务统计

## 四、`C1` 条件批次

`C1` 不是新里程碑，而是只有在触发条件成立时才打开的近程批次。

| 任务 | 对应条目 | 触发条件 | 文档落点 |
|------|----------|----------|----------|
| `P2-CEO-001` 初始化需求澄清板审协议 | `#64` | 初始化输入反复低于最小可执行阈值 | `TODO.md`、`active.md` |
| `P2-RET-006` 执行包最小组织上下文与 L1 收口 | `#63`、`#69-L1` | Worker 输出反复暴露缺少最小组织上下文，或执行包需要进一步收紧 | `TODO.md`、`active.md` |
| `P2-MTG-011` ADR 化共识文档与决策视图 | `#68` | 已于 2026-04-07 手动纳入并收口 | `TODO.md`、`done.md` |
| `P2-GOV-007` closeout 证据与文档同步软约束 | `#71-soft`、`#75-soft` | closeout / review 反复出现“代码已改但证据或文档没同步” | `TODO.md`、`active.md` |

默认规则：

- `C1` 任务进入执行前，先把触发原因写回 `doc/TODO.md`
- `C1` 任务只做最小软增强，不顺势扩成平台级系统

## 五、`R1` 远期储备

`R1` 不是排期，只是已经明确判定为当前不进入关键路径的远期方向。

| 条目 / 方向 | 当前判断 | 后置原因 |
|-------------|----------|----------|
| `#65 SPIKE_TICKET` | 重大影响项，远期储备 | 会同时碰 ticket 类型、调度、投影和前端识别 |
| `#69` 完整三层上下文 | 远期储备 | 当前只吸收 `L1` 纪律，不承诺 `L3 -> L2` 提升协议 |
| `#70` 项目地图 | 重大影响项，远期储备 | 当前不能新增新的项目真相源 |
| `#72` 组织过程资产体系 | 远期储备 | 依赖更重，不直接缩短本地 MVP 路径 |
| `#73` 组织学习闭环 | 重大影响项，远期储备 | 属于元治理能力，当前验证成本过高 |
| `#74` 系统化文档治理引擎 | 远期储备 | 当前阶段只按治理规则和文档约束处理 |
| `#67` 的系统化并行调度能力 | 远期储备 | 当前只作为治理原则记录，不做调度器改造 |
| `#71-hard` / `#75-hard` | 远期储备 | 当前只接受 soft rule，不做硬 gate |

## 六、58–80 映射总表

说明：

- 下表只覆盖旧 `archive/specs/feature-spec.md #58-80`
- `P0-COR` 主线纠偏不在这组旧条目里，单独按本次 live 集成纠偏跟踪

| 条目 | 当前分层 | 主要落点 |
|------|----------|----------|
| `#58` | 已在规划内 | `M6`、`P2-PRV-006` |
| `#59` | 已在规划内 | `M6`、`P2-PRV-008` |
| `#60` | 已在规划内 | `M3`、`P2-GOV-002` |
| `#61` | 已在规划内 | `M3`、`P2-GOV-003` |
| `#62` | 已在规划内 | `M6`、`P2-PRV-001/006/008` |
| `#63` | 条件纳入 | `C1`、`P2-RET-006` |
| `#64` | 条件纳入 | `C1`、`P2-CEO-001` |
| `#65` | 远期储备 + 重大影响项 | `R1`、`todo/postponed.md` |
| `#66` | 后置增强 | `P2-CEO-002` |
| `#67` | 治理原则 | `roadmap-reset.md`、`context-baseline.md` |
| `#68` | 已吸收 | `M5`、`P2-MTG-011` |
| `#69` | 重大影响项 | `P2-RET-006` 只承接 `L1`；完整版进 `R1` |
| `#70` | 远期储备 + 重大影响项 | `R1`、`todo/postponed.md` |
| `#71` | 条件纳入（软）/远期储备（硬） | `P2-GOV-007`、`R1` |
| `#72` | 远期储备 | `R1`、`todo/postponed.md` |
| `#73` | 远期储备 + 重大影响项 | `R1`、`todo/postponed.md` |
| `#74` | 治理原则 | `roadmap-reset.md`、`context-baseline.md`、`todo/postponed.md` |
| `#75` | 治理原则（软）/远期储备（硬） | `P2-GOV-007`、`R1` |
| `#76` | 已在规划内 | `P2-DEC-001` |
| `#77` | 已在规划内 | `P2-DEC-002`、`P2-DEC-003` |
| `#78` | 已在规划内 | `P2-DEC-002` |
| `#79` | 已在规划内 | `P2-DEC-002` |
| `#80` | 已在规划内 | `P2-DEC-004` |
