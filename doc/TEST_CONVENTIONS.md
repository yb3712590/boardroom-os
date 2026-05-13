# 测试约束

V2 测试的首要目标不是证明 happy path 能跑，而是证明旧失败模式不能再次通过。

## 测试优先级

1. Negative tests：伪交付必须失败。
2. Contract tests：对象和 reducer 行为稳定。
3. Evidence tests：证据必须来自真实来源。
4. Integration tests：workspace / provider / runner / checker / closeout 链路。
5. Proving scenario：tiny full-stack generated project package。

## 必须覆盖的负例

- fallback source delivery 不能满足 implementation evidence。
- provider zero-attempt 不能完成 implementation ticket。
- synthetic verification run 不能进入 final evidence。
- static acceptance criteria 不能覆盖动态用户需求。
- source inventory 只含 ref/hash 但无行为证据不能 closeout。
- checker notes 不能覆盖 blocker。
- missing acceptance map 不能 closeout。
- generated project 不可运行不能 closeout。
- replay bundle 缺失不能 terminal success。

## 命名建议

负例测试命名应直观：

```text
test_fallback_source_delivery_must_not_satisfy_implementation_evidence
test_provider_zero_attempt_must_block_ticket_completion
test_checker_notes_must_not_clear_blockers
test_missing_acceptance_map_must_block_closeout
```

## 禁止 synthetic success

测试中可以使用 fake provider，但 fake provider 必须产生可追踪 attempt record。不能直接构造 completed source delivery payload 绕过 executor。

允许 mock 的内容：

- provider API transport；
- clock；
- filesystem sandbox；
- command runner process wrapper。

禁止 mock 的内容：

- evidence verifier 的最终结论；
- acceptance map completeness；
- source inventory hash；
- provider attempt count；
- closeout gate。

## Proving scenario 成功口径

Tiny full-stack proving scenario 必须证明：

1. workspace 被创建；
2. package contract 存在；
3. provider-backed worker attempt 存在；
4. source files 写入 package root；
5. declared commands 被 runner 真实执行；
6. frontend 调用 backend API 的 evidence 存在；
7. SQLite schema / persistence evidence 存在；
8. source inventory 覆盖 frontend/backend/db/test；
9. acceptance map 完整；
10. closeout/replay/process audit READY。

