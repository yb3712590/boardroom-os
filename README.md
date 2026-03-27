# Boardroom OS

> Event-sourced Agent Governance.

中文版首页说明。English version: [README.en.md](README.en.md)

Boardroom OS 是一个基于事件溯源的 Agent 治理框架。

它不是聊天机器人外壳，不是“AI 办公室动画”产品，也不是把一堆 Agent 扔进群聊后听天由命的自动化脚本。它的目标是把 Agent 开发流程做成一个可审计、可治理、可审批、可持续推进的控制面系统：

- 用户扮演董事会
- CEO Agent 负责调度与推进
- Worker 以工单方式无状态执行
- Checker 负责内部审查
- 关键里程碑通过 Board Gate 审批
- 全流程通过事件日志和状态投影保留可追溯性

## 这个项目想解决什么

多数 Agent 开发框架最后都会掉进两个坑：

1. 过度依赖长对话上下文，成本高、易漂移、难审计。
2. 动不动停下来等人确认，无法像真正的团队一样持续推进。

Boardroom OS 试图用一套更工程化的方式处理这个问题：

- 用 `Event Log + Projection` 管理状态，而不是用聊天记录管理状态
- 用 `Ticket` 驱动执行，而不是让 Agent 自由漫游
- 用 `Context Compiler` 组装上下文，而不是让 CEO 手工喂 prompt
- 用 `Maker-Checker` 和 `Board Gate` 保证质量与治理
- 用 `Boardroom UI` 提供高密度、极简的人机控制面

一句话概括：

**少一点群聊，多一点治理。**

## 核心机制

### 1. Event-sourced Workflow Bus
- 事件日志是唯一真实来源
- CEO 读取状态投影，不读取长对话
- 状态流转由 Reducer 和 Transition Guard 约束

### 2. Ticket-driven Stateless Workers
- Worker 只处理当前原子任务
- 正式信息交接通过工单、事件和产物引用完成
- 禁止平级 Agent 黑箱式自由对话

### 3. Context Compiler
- 将 Ticket、约束、Artifact、检索结果编译为执行包
- 通过 `CompileRequest -> CompiledContextBundle` 管理上下文
- 支持基于任务类型的差异化压缩策略

### 4. Maker-Checker Review
- 重要产物不能由 Maker 直接进入主干
- Checker 负责对抗性、证据导向的结构化审查
- 反复打回达到阈值时触发熔断或升级

### 5. Board Gate
- 视觉里程碑、预算异常、关键升级事项进入董事会审批
- 董事会面向的是 `Board Review Pack`
- 原始编译上下文只作为高级调试信息存在

### 6. Boardroom UI
- 不是聊天窗口
- 不是桌宠/办公室动画
- 是 projection-first 的治理控制台

## 当前状态

当前仓库处于 **设计定稿 + 项目启动前** 阶段。

已完成：

- 总体 feature 约束整理
- 消息总线设计
- Context Compiler 设计
- Meeting Room 协议设计
- Boardroom UI 设计
- Boardroom 数据契约设计

当前尚未承诺：

- 生产可用
- 完整模型路由编排
- 完整向量检索
- 完整可视化前端实现

更准确地说，这个仓库目前是 **Boardroom OS 的 RFC / PRD / API 契约集合**，用于启动后续实现。

## 文档导航

- [feature.txt](feature.txt)
  - 全局 feature 规则与设计约束总表
- [message-bus-design.md](message-bus-design.md)
  - 事件总线、Ticket、Projection、Board Gate 的总体机制
- [context-compiler-design.md](context-compiler-design.md)
  - Context Compiler、CompileRequest、CompiledContextBundle、压缩策略
- [meeting-room-protocol.md](meeting-room-protocol.md)
  - 受控会议室协作协议
- [boardroom-ui-design.md](boardroom-ui-design.md)
  - Boardroom 控制面的产品与交互边界
- [boardroom-data-contracts.md](boardroom-data-contracts.md)
  - Dashboard / Inbox / Review Room 等 UI 数据契约
- [memory.txt](memory.txt)
  - 会话连续性记录，非正式规范源

## 计划技术栈

- 后端：Python 3.12 + FastAPI + Pydantic v2
- 数据层：SQLite + WAL + 手写 SQL / 拼装 SQL
- 前端：React + Vite + TypeScript + TailwindCSS
- 同步：REST + SSE
- 存储：控制面元数据进 SQLite，产物与预览走文件系统引用

## MVP 范围

首个可运行版本优先打通一条最小闭环：

- `project-init`
- event store
- projection API
- SSE 事件流
- Context Compiler 骨架
- Worker 执行链骨架
- Maker-Checker 一次闭环
- Board Review Pack 一次审批链路
- Boardroom UI 最小控制面

## 明确不做

至少在 MVP 阶段，不做以下内容：

- 聊天主界面
- 动画桌宠 / 办公室可视化表演
- 复杂首页 DAG 画布
- Meeting Room 专用 UI
- 重型 ORM 驱动的数据层
- 为了“看起来聪明”而超出文档约束的功能发散

## 开源协作

Boardroom OS 计划作为 GitHub 开源项目推进。

希望它具备以下特征：

- clone 后容易理解
- 文档和代码边界清晰
- 架构约束明确
- 适合人类与 AI 协作开发

后续实现阶段将补充：

- `CONTRIBUTING.md`
- `CHANGELOG.md`
- CI 骨架
- 统一版本入口

## 版本状态

计划起始版本：

- `0.1.0`

当前建议阶段标记：

- `pre-alpha`

## License

许可证尚未最终确认。

## 项目哲学

Boardroom OS 默认相信：

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠
- 用户应只在关键节点介入，而不是为系统兜底日常执行

最终目标不是做一个“会聊天的 Agent 项目”，而是做一个：

**可推进、可治理、可交付的 Agent Operating System。**
