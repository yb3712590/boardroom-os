# Boardroom OS V2 PRD

## 文档职责

本 PRD 定义 Boardroom OS V2 要解决的产品问题和成功标准。不定义具体代码结构；代码结构见技术架构和代码约束文档。

## 产品愿景

Boardroom OS V2 是一个可信的 agent team framework：用户输入一句自然语言需求或 PRD，系统由 CEO / Architect / Worker / Checker 等 agent seat 在显式合同、ticket graph 和证据门禁下协作，最终产出一个一致、可运行、可验证、可审计的 generated project package。

## 用户

主要用户：

1. 想用 LLM agent team 生成软件项目的项目 owner；
2. 需要可审计 AI 交付流程的技术负责人；
3. 需要复盘 agent 决策和产物证据的 reviewer；
4. 希望扩展角色、skills、provider 和交付模板的 framework developer。

## 核心问题

传统 LLM 编程 agent 容易产出看似完成但不可运行、不可审计、不可追踪的结果。V2 要解决的问题是：

- 谁决定下一步？
- 决策基于什么状态？
- agent 收到了什么上下文？
- 生成了什么 source？
- source 是否真的可运行？
- 测试和证据是否真实？
- closeout 是否只是收束已证明事实？
- 人类如何审计整个过程？

## 产品目标

V2 必须具备：

1. 从自然语言需求或 PRD 启动项目；
2. CEO-governed 的 ticket graph；
3. architect 产出可施工 package contract；
4. worker 接收结构化 execution package；
5. checker 独立验证交付物和证据；
6. runtime 只执行、记录、校验、投影；
7. generated project workspace 承载源码、文档、测试和证据；
8. acceptance/evidence/source inventory/closeout 全链路可追踪；
9. provider attempt、model、effort、fallback 分类可审计；
10. human-readable process audit；
11. replay/resume 支撑审计和恢复。

## 非目标

V2 初期不做：

- 产品前端 UI；
- 多租户平台；
- 复杂权限系统；
- marketplace；
- 大规模并发调度；
- 兼容旧 runtime；
- 迁移旧历史文档；
- 直接追求复杂项目生成。

## 第一类支持交付物

V2 应能生成不同类型的软件项目包，包括但不限于：

- backend-only service；
- full-stack web app；
- CLI tool；
- script / automation；
- data pipeline；
- document-heavy compliance project。

第一阶段只证明 tiny full-stack package。

## 第一个 proving scenario

```text
Build a tiny anonymous book availability tracker.
```

最小功能：

- FastAPI 或等价 backend；
- SQLite 持久化；
- static HTML/JS frontend；
- add/list/checkout/return/delete；
- 状态：IN_LIBRARY / CHECKED_OUT；
- 前端必须真实调用后端 API；
- 本地可运行；
- 测试和 evidence 真实产生；
- closeout 生成 process audit。

详细验收见 `../04-implementation/proving-scenario-tiny-fullstack.md`。

## 成功标准

V2 的成功不是 workflow completed，而是：

1. active acceptance contract 从当前需求动态派生；
2. package contract 明确 source surfaces、run/test commands、integration boundary；
3. ticket graph 是唯一流程状态源；
4. provider-backed implementation attempt 存在；
5. command runner 真实执行 declared commands；
6. evidence verifier 只接受可追踪证据；
7. checker 对缺口发起 rework；
8. closeout 只在 evidence complete 时通过；
9. replay bundle 可重建 typed summary；
10. process audit 可供人类审计。

## 关键反目标

以下结果即使 workflow 显示 completed，也必须视为失败：

- runtime 生成 placeholder source；
- synthetic test output 被接受；
- provider attempt 为 0；
- acceptance map 为空；
- source inventory 只证明引用存在；
- generated project package 不可运行；
- checker notes 覆盖了 blocker；
- closeout 阶段才第一次发现 evidence 缺口。

