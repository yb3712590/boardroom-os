# Boardroom OS — CTO 全面评估报告

> 评估日期：2026-04-03
> 评估人：CTO（技术审查角色）
> 评估范围：架构、设计、代码、规划文档、与 feature-spec 的对齐度

---

## 一、综述

### 1.1 项目定位

Boardroom OS 是一个**本地优先、事件溯源驱动的 Agent Team 自动化交付控制面**。用户扮演董事会，只负责提出目标、约束和验收标准；系统通过结构化事件、结构化工单和结构化审批门来推进工作，而不是依赖多 Agent 长对话。

### 1.2 总体评价

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构与 feature-spec 对齐度 | ★★★★☆ (4/5) | 核心架构高度对齐，但 CEO Agent 调度器和人格模型尚未实现 |
| 后端工程质量 | ★★★★☆ (4/5) | 事件溯源、Reducer、投影、Ticket 生命周期扎实，但存在代码膨胀 |
| 前端工程质量 | ★★★☆☆ (3/5) | 功能完整但全部堆在少数大文件中，无组件库、无类型抽象 |
| 测试覆盖 | ★★★★☆ (4/5) | 后端 ~21,000 行测试，覆盖核心链路；前端几乎无测试 |
| 文档质量 | ★★★★★ (5/5) | 设计文档、路线决议、记忆日志、运行指南齐全且真实 |
| MVP 闭环完成度 | ★★★★☆ (4/5) | 本地链路已跑通，但缺少真实 LLM 驱动的自主执行 |
| 与 feature-spec 的偏离程度 | 中等 | 基础设施过度建设 vs 核心 Agent 智能缺失 |

### 1.3 核心结论

**项目在「控制面基础设施」维度做得远超预期，但在「Agent 智能」维度严重滞后。**

feature-spec 描述的是一个「像公司一样自动运转的交付系统」，其核心是 CEO Agent 自主拆解任务、招聘员工、推进交付。当前项目已经建好了公司的办公楼（事件总线、工单系统、审批门、投影读面），但公司里还没有真正的 CEO 和员工——所有「执行」都是确定性 mock 或需要人工触发。

同时，项目在 worker-admin、多租户、对象存储、远程 handoff 等方向上投入了大量代码（后端 87,000+ 行），这些能力虽然保留在仓库中并已被路线纠偏决议降级，但它们的存在显著增加了认知负担和维护成本。

---

## 二、详细分析

### 2.1 项目结构概览

```
boardroom-os/
├── backend/                    # Python 后端 (FastAPI + SQLite)
│   ├── app/
│   │   ├── api/                # HTTP 路由层 (commands, projections, events, worker_*)
│   │   ├── contracts/          # Pydantic 契约 (commands, events, projections, runtime, artifacts, worker_*)
│   │   ├── core/               # 业务逻辑核心
│   │   │   ├── reducer.py      # 事件溯源 Reducer（纯函数）
│   │   │   ├── command_handlers.py
│   │   │   ├── ticket_handlers.py
│   │   │   ├── approval_handlers.py
│   │   │   ├── employee_handlers.py
│   │   │   ├── workflow_auto_advance.py
│   │   │   ├── context_compiler.py
│   │   │   ├── runtime.py
│   │   │   ├── projections.py
│   │   │   ├── output_schemas.py
│   │   │   ├── staffing_catalog.py
│   │   │   ├── staffing_containment.py
│   │   │   ├── artifacts.py / artifact_*.py
│   │   │   ├── worker_*.py     # Worker 运维（已降级）
│   │   │   └── provider_openai_compat.py
│   │   ├── db/
│   │   │   ├── schema.py       # SQLite DDL
│   │   │   └── repository.py   # 数据访问层
│   │   ├── config.py
│   │   ├── main.py
│   │   └── scheduler_runner.py
│   ├── tests/                  # 11 个测试文件，~21,000 行
│   └── pyproject.toml
├── frontend/                   # React 前端 (Vite + TypeScript)
│   ├── src/
│   │   ├── App.tsx             # ~995 行，主壳
│   │   ├── App.css             # ~5,000+ 行样式
│   │   ├── api.ts              # ~580 行 API 客户端
│   │   └── components/         # 6 个组件文件
│   └── package.json
└── doc/                        # 文档
    ├── feature-spec.md         # 董事会愿景（57 条）
    ├── roadmap-reset.md        # 路线纠偏决议
    ├── TODO.md                 # 当前主线待办
    ├── design/                 # 7 份设计文档
    └── history/                # 记忆日志 + 归档
```

### 2.2 代码规模统计

| 区域 | 行数 | 说明 |
|------|------|------|
| 后端 Python (app/) | ~87,000 | 包含大量已降级的 worker-admin 代码 |
| 后端测试 (tests/) | ~21,000 | 覆盖核心链路 |
| 前端 TypeScript (src/) | ~7,900 | 含 CSS |
| 设计文档 | ~3,000+ | 7 份设计文档 |
| 运行文档 | ~1,500+ | README + 运行指南 + TODO + 路线决议 |

---

### 2.3 与 feature-spec 逐条对齐分析

以下按 feature-spec 的 57 条逐一评估当前实现状态。

#### 第一组：治理模型与自治执行（条目 1-10）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 1 | 用户扮演董事会，CEO Agent 自主拆解推进 | ⚠️ 部分实现 | 董事会角色已实现（Inbox → Review Room），但 CEO Agent 不存在——当前是 `workflow_auto_advance.py` 里的确定性状态机在推进，不是 LLM 驱动的 CEO |
| 2 | 自治执行，少量审查门 | ✅ 已实现 | 审查门模型完整：视觉审批、核心员工审批、预算异常、范围变更。非阻塞时自动推进 |
| 3 | 视觉质量作为一级治理对象 | ✅ 已实现 | `ui_milestone_review@1` 有独立的 Maker-Checker 闭环 |
| 4 | 视觉交付物必须提交董事会审核 | ✅ 已实现 | 视觉里程碑通过 `BOARD_REVIEW_REQUIRED` 进入 Inbox → Review Room |
| 5 | 其他阶段团队自主闭环 | ✅ 已实现 | BUILD/CHECK 有内部 Maker-Checker，不进董事会 |
| 6 | CEO 必须持续推进 | ❌ 未实现 | 没有 CEO Agent。`workflow_auto_advance.py` 是硬编码的状态转换，不是 LLM 驱动的调度器 |
| 7 | 明确的升级规则 | ✅ 已实现 | `escalation_policy` 在每张工单上，incident/breaker 机制完整 |
| 8 | 「继续推进」是制度 | ✅ 已实现 | 每个阶段有明确输出格式，非阻塞时自动推进 |
| 9 | 视觉审查采用可比较形式 | ✅ 已实现 | Review Pack 包含选项、证据、推荐、风险 |
| 10 | 只在关键审查门升级 | ✅ 已实现 | 当前只有 5 种 ReviewType 会进入董事会 |

#### 第二组：组织与人才模型（条目 11-20）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 11 | CEO 自主招聘 | ⚠️ 部分实现 | 招聘命令存在（`employee-hire-request`），但由人工触发，不是 CEO 自主决策 |
| 12 | 技能+性格+审美三维人才模型 | ⚠️ 结构存在 | 契约中有 `skill_profile`、`personality_profile`、`aesthetic_profile` 字段，但全部是空 dict，没有实际使用 |
| 13 | 同岗异质性 | ❌ 未实现 | 没有相似度计算，没有多样性约束 |
| 14 | 结构化人格画像 | ❌ 未实现 | 字段存在但无内容，无维度定义 |
| 15 | 互补而非最强 | ❌ 未实现 | 没有互补性计算逻辑 |
| 16 | 核心员工人格需董事会批准 | ✅ 已实现 | `CORE_HIRE_APPROVAL` 会进入 Inbox → Review Room |
| 17 | 普通员工 CEO 自主招聘 | ⚠️ 部分实现 | 命令存在但无自主触发 |
| 18 | 结构化招聘提案 | ⚠️ 部分实现 | `EmployeeHireRequestCommand` 有结构，但 profile 字段为空 |
| 19 | 动态扩编与替换 | ✅ 已实现 | hire/replace/freeze/restore 完整 |
| 20 | 真实组织韧性 | ❌ 未实现 | 缺少人格互补、制衡、分层的实际逻辑 |

#### 第三组：消息传递与状态总线（条目 21-40）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 21 | 事件溯源状态总线 + Ticket 驱动 | ✅ 已实现 | 这是项目最强的部分 |
| 22 | CEO 计算无状态调度器 | ⚠️ 部分实现 | 架构正确（每次读快照输出动作），但 CEO 是硬编码而非 LLM |
| 23 | CEO 由显式事件触发 | ✅ 已实现 | `scheduler_tick` + `workflow_auto_advance` |
| 24 | CEO 输出受控动作 | ⚠️ 部分实现 | 动作类型存在（CREATE_TICKET 等），但由确定性代码生成，不是 LLM 提出后 Reducer 校验 |
| 25 | Agent 间通过总线交接 | ✅ 已实现 | 所有交互都是事件/工单/产物引用 |
| 26 | 员工为无状态 Ticket 执行器 | ✅ 已实现 | Worker 只处理单一工单，不继承历史 |
| 27 | 标准工单字段 | ✅ 已实现 | `TicketCreateCommand` 包含 spec 要求的所有字段 |
| 28 | Context Compiler 独立负责上下文 | ✅ 已实现 | `context_compiler.py` 完整实现 |
| 29 | SQLite 作为嵌入式状态总线 | ✅ 已实现 | SQLite + WAL 模式 |
| 30 | SQLite 并发控制 | ✅ 已实现 | WAL + busy_timeout + 幂等键 + 租约 |
| 31 | 事件日志 + 状态投影双层模型 | ✅ 已实现 | `repository.py` 中事件追加 + 投影重建 |
| 32 | 轻量检索层 | ⚠️ 部分实现 | 本地历史摘要检索已有，FTS5/LanceDB 未实现 |
| 33 | 降低幻觉概率 | ✅ 已实现 | Schema 校验、写集验证、Reducer 守卫 |
| 34 | 熔断机制 | ✅ 已实现 | Circuit breaker + incident + 升级 |
| 35 | 董事会审批门纳入消息机制 | ✅ 已实现 | `BOARD_REVIEW_REQUIRED/APPROVED/REJECTED` 事件 |
| 36 | 完整事件类型集 | ✅ 已实现 | 所有 spec 要求的事件类型都存在 |
| 37 | Reducer 纯净 | ✅ 已实现 | Reducer 是纯函数，不产生副作用 |
| 38 | TICKET_COMPLETED 双重校验 | ✅ 已实现 | schema validation + write-set validation |
| 39 | 编译后的执行包 | ✅ 已实现 | Context Compiler 产出完整执行包 |
| 40 | 视觉审批状态机 | ✅ 已实现 | PENDING → EXECUTING → BLOCKED_FOR_BOARD_REVIEW → REWORK_REQUIRED → COMPLETED |

#### 第四组：会议室协议（条目 41-45）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 41 | 会议室协议作为受控例外 | ⚠️ 设计存在 | `meeting-room-protocol.md` 设计完整，但代码中只有 `MEETING_ESCALATION` 审批类型，无真实会议执行 |
| 42 | 不退化为自由群聊 | ✅ 设计正确 | 设计文档明确了约束 |
| 43 | 显式会议事件 | ❌ 未实现 | 事件类型未在代码中定义 |
| 44 | 结构化共识输出 | ⚠️ 部分实现 | `consensus_document@1` 有 schema，但无真实会议过程 |
| 45 | 结构化轮次 | ❌ 未实现 | 无立场轮/质疑轮/方案轮/收敛轮逻辑 |

#### 第五组：Maker-Checker（条目 46-50）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 46 | Maker-Checker 同行评审 | ✅ 已实现 | 5 种产物已覆盖 |
| 47 | Checker 证据导向 | ✅ 设计正确 | `maker_checker_verdict` schema 要求结构化 findings |
| 48 | 自动创建 REVIEW_TICKET | ✅ 已实现 | Maker 完成后自动生成 Checker ticket |
| 49 | 结构化内审裁决 | ✅ 已实现 | APPROVED/APPROVED_WITH_NOTES/CHANGES_REQUIRED/ESCALATED |
| 50 | 返工闭环 | ✅ 已实现 | fix ticket + 重复指纹升级 + 换人 |

#### 第六组：Boardroom UI（条目 51-55）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 51 | 极简黑客控制台气质 | ⚠️ 部分实现 | 功能完整但视觉偏朴素，缺少 spec 要求的「黑客控制台气质」 |
| 52 | Projection-first | ✅ 已实现 | 前端只消费后端投影 |
| 53 | 审批收件箱 + 流水线主视图 + 执行器 + 健康条 | ✅ 已实现 | Dashboard/Inbox/WorkflowRiver/OpsStrip 都存在 |
| 54 | Review Room 专门审查界面 | ✅ 已实现 | ReviewRoomDrawer 完整 |
| 55 | snapshot + stream + command 通信模式 | ✅ 已实现 | Projection API + SSE + Command API |

#### 第七组：Provider 与 BYOK（条目 56-57）

| 条目 | 要求 | 状态 | 评估 |
|------|------|------|------|
| 56 | 模型与 Provider 配置中心 | ⚠️ 部分实现 | 基础配置存在，但缺少能力标签、fallback 路由、健康检查等 |
| 57 | BYOK 方案 | ✅ 已实现 | UI 中可直接配置 API Key，本地保存，遮罩展示 |

### 2.4 对齐度总结

| 类别 | 总条目 | 已实现 | 部分实现 | 未实现 |
|------|--------|--------|----------|--------|
| 治理模型 (1-10) | 10 | 7 | 2 | 1 |
| 组织人才 (11-20) | 10 | 2 | 4 | 4 |
| 消息总线 (21-40) | 20 | 17 | 3 | 0 |
| 会议室 (41-45) | 5 | 1 | 2 | 2 |
| Maker-Checker (46-50) | 5 | 5 | 0 | 0 |
| UI (51-55) | 5 | 4 | 1 | 0 |
| Provider (56-57) | 2 | 1 | 1 | 0 |
| **合计** | **57** | **37 (65%)** | **13 (23%)** | **7 (12%)** |

---

### 2.5 架构分析

#### 2.5.1 优势

1. **事件溯源架构扎实**：事件日志 → 状态投影 → 命令处理的三层分离清晰。Reducer 是纯函数，不产生副作用。事件类型覆盖完整。

2. **Ticket 生命周期完整**：PENDING → LEASED → EXECUTING → COMPLETED/FAILED/TIMED_OUT，加上 RETRY、CANCEL、BOARD_REVIEW 等分支，状态机设计严谨。

3. **Maker-Checker 是真实闭环**：不是装饰性的代码审查，而是有 schema 校验、写集验证、结构化 findings、返工票、重复指纹升级的完整质量门。

4. **Context Compiler 设计精良**：预算控制、片段编译、降级策略、媒体引用、审计产物，这是整个系统中最有技术深度的模块之一。

5. **文档体系优秀**：feature-spec、设计文档、路线决议、记忆日志形成了完整的决策链。roadmap-reset.md 的纠偏决议尤其有价值。

#### 2.5.2 问题

1. **核心缺失：没有真正的 CEO Agent**
   - feature-spec 条目 1、6、11、22、24 都要求 CEO 是 LLM 驱动的自主调度器
   - 当前 `workflow_auto_advance.py` 是硬编码的 if-else 状态转换
   - 这意味着系统无法自主拆解任务、无法根据项目复杂度调整策略、无法在成员停滞时重新分派
   - **这是与 feature-spec 最大的偏离**

2. **核心缺失：没有真正的 Worker 执行**
   - 所有 Worker 执行都是确定性 mock（`runtime.py` 中的 `_build_deterministic_*` 函数）
   - 虽然有 `provider_openai_compat.py` 适配层，但只覆盖 2 种 schema
   - 系统建好了工厂但没有工人

3. **核心缺失：人格模型是空壳**
   - `skill_profile`、`personality_profile`、`aesthetic_profile` 在契约中定义但全部为空 dict
   - 没有维度定义、没有相似度计算、没有多样性约束
   - feature-spec 条目 12-15、20 的要求完全未实现

4. **代码膨胀：已降级能力占比过高**
   - 后端 87,000 行中，worker-admin、多租户、对象存储、远程 handoff 相关代码估计占 30-40%
   - 这些代码已被路线决议降级，但仍在仓库中增加认知负担
   - 新开发者需要花大量时间区分「主线」和「冻结」代码

5. **前端工程化不足**
   - `App.tsx` 995 行，`App.css` 5000+ 行，`api.ts` 580 行
   - 没有状态管理库、没有组件库、没有类型抽象层
   - 所有状态都用 `useState` 平铺在 `ShellRoute` 中
   - 对于 MVP 可以接受，但继续扩展会迅速失控

6. **会议室协议只有设计没有实现**
   - `meeting-room-protocol.md` 设计完整，但代码中只有审批类型定义
   - 没有真实的多角色协作执行

---

### 2.6 后端代码质量详评

#### 2.6.1 契约层 (contracts/)

**评价：优秀**

- 使用 Pydantic v2 的 `StrictModel`（`extra="forbid"`），防止字段泄漏
- 命令、事件、投影契约分离清晰
- `TicketCreateCommand` 包含 feature-spec 条目 27 要求的所有字段
- `TicketBoardReviewRequest` 包含选项、证据、推荐、风险、开发者检查器引用
- 枚举类型使用 `StrEnum`，序列化友好

**问题：**
- `contracts/` 目录中混入了 `worker_runtime.py`、`worker_admin.py` 等已降级模块的契约
- 部分契约文件超过 500 行

#### 2.6.2 Reducer (core/reducer.py)

**评价：优秀**

- 纯函数设计，无副作用
- 覆盖 workflow、employee、ticket、node、incident、circuit breaker 六类投影重建
- 事件类型处理完整
- 有专门的测试文件 `test_reducer.py`（1,448 行）

#### 2.6.3 命令处理器 (core/*_handlers.py)

**评价：良好，但过于庞大**

- `ticket_handlers.py` 是最大的单文件，估计 1,500+ 行
- 包含 ticket 创建、租约、启动、心跳、完成、失败、取消、结果提交、调度、incident 恢复
- 逻辑正确但可读性因文件大小而下降
- `approval_handlers.py` 中的 `handle_board_approve` 包含 scope follow-up 消费逻辑，复杂度较高

#### 2.6.4 Context Compiler (core/context_compiler.py)

**评价：优秀**

- 预算控制策略完整：完整内联 → 片段编译 → 预览降级 → 引用
- 支持文本、JSON、Markdown、图片、PDF、二进制
- 产出可审计的 compile manifest
- 本地历史摘要检索已实现
- `display_hint` 系统让 Worker 不需要猜测内容类型

#### 2.6.5 数据库层 (db/)

**评价：良好**

- `schema.py` 定义了完整的 DDL，包含迁移逻辑
- `repository.py` 是最大的文件之一，包含所有数据访问
- 使用 WAL 模式和 busy_timeout
- 有幂等键去重
- 有 legacy 数据迁移和回填逻辑

**问题：**
- `repository.py` 过于庞大，应该按领域拆分
- 部分查询使用字符串拼接而非参数化（需要确认）

#### 2.6.6 已降级代码

以下模块已被路线决议降级但仍在仓库中：

- `worker_admin.py` + `worker_admin_tokens.py` + `worker_admin_auth.py`：多租户 worker 运维面
- `worker_bootstrap_tokens.py` + `worker_delivery_tokens.py`：远程 worker handoff
- `worker_runtime.py`（API 层）：外部 worker 接入
- `artifact_uploads.py`：分段上传
- `artifact_store.py`（对象存储部分）：S3 兼容后端

这些代码质量本身不差，但它们不在当前主线上，增加了维护负担。

---

### 2.7 前端代码质量详评

#### 2.7.1 架构

- React + Vite + TypeScript
- 路由使用 React Router
- 状态管理：纯 `useState`，无 Redux/Zustand/Context
- API 层：手写 fetch 封装
- 样式：纯 CSS，无 CSS-in-JS 或 Tailwind

#### 2.7.2 组件结构

| 文件 | 行数 | 职责 |
|------|------|------|
| App.tsx | ~995 | 主壳、所有状态、所有事件处理 |
| api.ts | ~580 | API 客户端 + 类型定义 |
| App.css | ~5,000+ | 全部样式 |
| WorkflowRiver.tsx | ~200 | 流水线可视化 |
| ReviewRoomDrawer.tsx | ~400 | 审查室抽屉 |
| WorkforcePanel.tsx | ~260 | 员工面板 |
| IncidentDrawer.tsx | ~150 | 事件详情 |
| EventTicker.tsx | ~80 | 事件流 |
| DependencyInspectorDrawer.tsx | ~150 | 依赖检查器 |
| ProviderSettingsDrawer.tsx | ~200 | Provider 设置 |

#### 2.7.3 问题

1. **App.tsx 是上帝组件**：995 行，包含 20+ 个 useState、10+ 个事件处理函数、所有路由逻辑
2. **无类型抽象**：API 响应类型直接在 `api.ts` 中定义，没有共享的领域模型
3. **无错误边界**：任何组件崩溃都会白屏
4. **无加载骨架屏**：加载时只显示文字
5. **SSE 重连逻辑简陋**：`EventSource` 断开后没有重连策略
6. **无国际化**：硬编码英文
7. **无可访问性测试**
8. **测试几乎为零**：只有一个 `App.test.tsx`

---

### 2.8 测试覆盖分析

| 测试文件 | 行数 | 覆盖范围 |
|----------|------|----------|
| test_api.py | 2,598+ | API 集成测试，覆盖核心链路 |
| test_scheduler_runner.py | 1,813 | 调度器 + 运行时 |
| test_reducer.py | 1,448 | 事件溯源 Reducer |
| test_repository.py | 1,597 | 数据库层 |
| test_context_compiler.py | ~800 | Context Compiler |
| test_output_schemas.py | 178 | 输出 schema |
| test_provider_openai_compat.py | ~500 | OpenAI 适配 |
| test_inprocess_scheduler.py | ~500 | 进程内调度 |
| test_worker_auth_cli.py | 913 | Worker 认证 CLI |
| test_worker_admin_auth_cli.py | 161 | Worker Admin CLI |
| conftest.py | ~100 | 测试配置 |

**优势：** 后端核心链路测试覆盖良好，Reducer 有纯单元测试。
**问题：** 前端几乎无测试；后端测试中约 1/3 覆盖的是已降级的 worker-admin 功能。

---

### 2.9 文档质量分析

| 文档 | 评价 |
|------|------|
| feature-spec.md | ★★★★★ 极其详尽的产品愿景，57 条覆盖治理、人才、架构、UI、Provider |
| roadmap-reset.md | ★★★★★ 关键纠偏决议，明确了主线边界和判断规则 |
| TODO.md | ★★★★☆ 当前待办清晰，但缺少里程碑时间线 |
| message-bus-design.md | ★★★★★ 1,028 行的详细设计，覆盖事件、状态机、Ticket、审批 |
| context-compiler-design.md | ★★★★☆ 设计完整 |
| meeting-room-protocol.md | ★★★★☆ 设计完整但未实现 |
| boardroom-ui-design.md | ★★★★☆ UI 信息架构清晰 |
| boardroom-ui-visual-spec.md | ★★★★☆ 视觉规范详细 |
| memory-log.md | ★★★★★ 压缩后的长期记忆，真实反映进展 |

---

## 三、核心偏离总结

### 3.1 最严重的偏离

1. **没有 CEO Agent**：feature-spec 的核心是「CEO 自主拆解、委派、推进」，当前是硬编码状态机
2. **没有真实 Worker 执行**：所有执行都是确定性 mock
3. **人格模型是空壳**：三维人才模型只有字段定义，无实际内容
4. **会议室协议未实现**：只有设计文档

### 3.2 次要偏离

5. **基础设施过度建设**：worker-admin、多租户、对象存储、远程 handoff 占用了大量开发预算
6. **前端工程化不足**：上帝组件、无状态管理、无测试
7. **Provider 配置中心不完整**：缺少能力标签、fallback 路由、健康检查
8. **检索层未完成**：FTS5/LanceDB 未实现

### 3.3 偏离的根本原因

项目在「控制面基础设施」方向上投入过多，在「Agent 智能」方向上投入过少。这导致了一个悖论：

- 系统有完美的工单系统，但没有能自主创建工单的 CEO
- 系统有完美的执行包编译器，但没有能消费执行包的 Worker
- 系统有完美的人才管理命令，但没有真正有「人格」的员工

路线纠偏决议（roadmap-reset.md）已经识别到了基础设施过度建设的问题，并正确地将主线拉回本地 MVP。但纠偏后的重点仍然是补齐治理闭环（Maker-Checker 扩展、closeout 收口等），而不是补齐 Agent 智能。

---

## 四、风险评估

| 风险 | 严重度 | 说明 |
|------|--------|------|
| 无 CEO Agent 导致系统无法自主运转 | 🔴 高 | 这是 feature-spec 的核心要求 |
| 代码膨胀导致维护成本上升 | 🟡 中 | 87K 行后端代码中大量是已降级功能 |
| 前端扩展性差 | 🟡 中 | 上帝组件模式无法支撑更多功能 |
| 人格模型空壳导致团队无差异化 | 🟡 中 | 所有 Agent 本质相同 |
| 只有确定性执行导致无法验证真实场景 | 🔴 高 | 无法证明系统在真实 LLM 下能工作 |
| 会议室协议缺失导致跨角色协作无法处理 | 🟡 中 | 高耦合议题无法收敛 |

---

## 五、建议

### 5.1 立即行动（P0）

1. **实现最小 CEO Agent**：用 LLM 驱动的调度器替换 `workflow_auto_advance.py` 中的硬编码逻辑。CEO 读取当前状态快照，输出受控动作（CREATE_TICKET、RETRY_TICKET 等），由 Reducer 校验。

2. **实现最小 Worker 执行**：让至少一种 Worker（如 frontend_engineer）能通过 OpenAI Compat 路径真实执行工单，而不是返回确定性 mock。

3. **填充人格模型**：为 `skill_profile`、`personality_profile`、`aesthetic_profile` 定义具体维度和值，让不同角色有真实差异。

### 5.2 短期行动（P1）

4. **前端重构**：将 `App.tsx` 拆分为独立页面组件，引入轻量状态管理（Zustand），添加错误边界。

5. **代码瘦身**：将已降级的 worker-admin、多租户、对象存储代码移入独立目录或标记为 `_frozen`，降低主线认知负担。

6. **实现最小会议室协议**：至少支持一种结构化多角色协作场景。

### 5.3 中期行动（P2）

7. **完善 Provider 配置中心**：能力标签、fallback 路由、健康检查。
8. **实现检索层**：FTS5 关键词检索 + 可选向量检索。
9. **前端测试**：至少覆盖核心交互流程。
10. **性能基准**：建立事件写入、投影重建、Context 编译的性能基线。
