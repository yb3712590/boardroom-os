# Decisions

## DEC-0001: V2 采用 clean foundation 路线

- 状态：Accepted
- 日期：2026-05-13

### 决策

V2 不在旧实现主链上做瘦身重构。采用干净分支和新文档基座，旧 git 历史只作为归档教训。

### 理由

旧主链失败来自架构权力倒挂：runtime 可制造伪 source /伪 verification / workflow completion，治理、证据和 closeout 在事后才暴露问题。继续整理旧代码会污染上下文并降低性价比。

## DEC-0002: 旧实现 abandoned by default

- 状态：Accepted
- 日期：2026-05-13

### 决策

旧实现默认废弃。除用户明确要求 forensic lookup 外，不读取、不迁移、不整理旧实现。

### 理由

V2 需要避免从旧 runtime、旧 tests、旧 docs 中继承伪成功语义。

## DEC-0003: 新代码进入 `src/boardroom_os/`

- 状态：Accepted
- 日期：2026-05-13

### 决策

V2 后续实现进入新命名空间 `src/boardroom_os/`。

### 理由

需要从路径上切断与旧 `backend/app/core` 主链的耦合。

## DEC-0004: Contract-first and reducer-first

- 状态：Accepted
- 日期：2026-05-13

### 决策

没有 active contract 不写 implementation 主路径；关键状态变更必须通过 reducer。

### 理由

防止 runtime 或 executor 再次越权决定项目完成。

## DEC-0005: Negative tests first

- 状态：Accepted
- 日期：2026-05-13

### 决策

先写防伪成功负例测试，再写 happy path。

### 理由

旧系统的失败之一是测试保护了 fallback success。V2 必须反向设计测试激励。

## DEC-0006: Provider-backed implementation evidence is mandatory

- 状态：Accepted
- 日期：2026-05-13

### 决策

Provider-required implementation ticket 必须有 provider attempt。attempt count 为 0 必须失败。

### 理由

没有 provider attempt 的 implementation success 无法证明 agent team 真实实施。

## DEC-0007: Generated project package is final output

- 状态：Accepted
- 日期：2026-05-13

### 决策

最终交付物是 generated project package，而不是离散 source artifact。

### 理由

用户期望的是一个一致、可运行、可审计的目标项目包。

