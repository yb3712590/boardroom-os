# V2 总验收标准

## 文档职责

本文件定义 Boardroom OS V2 自身的验收标准。它不是某个 generated project 的 acceptance contract。

## AC-V2-FOUNDATION

### AC-V2-FOUNDATION-001: clean branch foundation

V2 必须能在干净分支中独立表达目标、架构、约束和路线，不依赖旧实现主链。

### AC-V2-FOUNDATION-002: legacy boundary

旧实现默认 abandoned by default。除 forensic lookup 外，AI 不应读取旧实现作为 V2 实施依据。

## AC-V2-CONTRACT

### AC-V2-CONTRACT-001: dynamic acceptance contract

Acceptance criteria 必须从当前用户需求、PRD 和治理产物动态派生。

### AC-V2-CONTRACT-002: package contract required

任何 implementation ticket 创建前，必须存在 package contract，定义 source surfaces、run/test commands、integration boundary 和 evidence obligations。

### AC-V2-CONTRACT-003: no static universal AC

禁止使用固定 AC 列表覆盖所有项目类型。

## AC-V2-GRAPH

### AC-V2-GRAPH-001: ticket graph as state source

Ticket graph 是流程状态源。runtime 不得直接推进 project completed。

### AC-V2-GRAPH-002: reducer-protected transitions

所有关键状态变更必须通过 reducer 或 validator。

## AC-V2-EXECUTION

### AC-V2-EXECUTION-001: execution package required

Worker 执行前必须收到结构化 execution package。

### AC-V2-EXECUTION-002: provider attempt required

Provider-required implementation ticket 必须有 provider attempt。attempt count 为 0 必须失败。

### AC-V2-EXECUTION-003: fallback cannot satisfy implementation evidence

Fallback 默认不能满足 source、integration、acceptance 或 closeout evidence。

## AC-V2-EVIDENCE

### AC-V2-EVIDENCE-001: command evidence from runner

Verification run 必须来自 command runner 的真实执行记录。

### AC-V2-EVIDENCE-002: source inventory proves implementation lineage

Source inventory 必须证明文件路径、hash、producer ticket、provider attempt、source surface、acceptance refs 和 evidence refs。

### AC-V2-EVIDENCE-003: evidence map complete

Final evidence table 必须覆盖 active acceptance contract 的所有 blocking criteria。

## AC-V2-CHECKER

### AC-V2-CHECKER-001: checker blocks evidence gaps

Checker 必须对缺失 source、test、integration、acceptance 或 closeout evidence 发起 rework。

### AC-V2-CHECKER-002: notes do not clear blockers

Checker notes 不能覆盖 blocker。

## AC-V2-PACKAGE

### AC-V2-PACKAGE-001: generated project package is final output

最终输出必须是 generated project package，而不是离散 source artifact。

### AC-V2-PACKAGE-002: package must be runnable when required

对于声明为可运行的软件项目，必须验证 run/test commands。

## AC-V2-CLOSEOUT

### AC-V2-CLOSEOUT-001: closeout only after verified evidence

Closeout 只能在 evidence、source inventory、git audit、replay bundle 全部 ready 后通过。

### AC-V2-CLOSEOUT-002: replay bundle required

缺 replay bundle 不允许 terminal success。

### AC-V2-CLOSEOUT-003: human-readable process audit required

必须产出人类可读 process audit。

## Negative acceptance

以下情况必须失败：

- runtime 生成 placeholder source；
- runtime 合成 verification success；
- provider attempt count 为 0；
- acceptance map 为空；
- source inventory 只证明 ref 存在；
- checker notes 覆盖 blocker；
- generated project package 缺 run manifest；
- final package 不可运行却 closeout passed；
- replay bundle 缺失；
- closeout 阶段才首次发现 implementation 缺口。

