# Provider 契约

## 目标

Provider 层必须能够证明：同一 API 配置在本项目中的高失败率到底来自上游，还是来自本项目的 adapter、stream parser、timeout、retry、schema validation 或 ticket lease 逻辑。

第 15 轮中出现了大量 `FIRST_TOKEN_TIMEOUT`、`UPSTREAM_UNAVAILABLE`、`stream_read_error`、empty assistant text、malformed SSE JSON 和 schema validation retry。用户观察到同一 API 在其他 AI 编程框架里 streaming 表现正常。因此重构默认假设是：在独立 soak test 排除前，本项目 provider 层不可信。

## Provider Adapter 最小接口

Provider adapter 只负责厂商协议适配，输出标准事件流：

```text
ProviderRequest -> Iterator[ProviderEvent]
```

Provider adapter 不负责：

- ticket retry；
- graph recovery；
- worker lease；
- closeout 判断；
- delivery fallback；
- 默认生成 source/test evidence。

## ProviderEvent

OpenAI-compatible streaming provider 已切到标准事件协议。Provider 模块内部边界是：

```text
ProviderRequest -> Iterator[ProviderEvent] -> ProviderResult | ProviderFailure
```

当前实现只覆盖 OpenAI Responses streaming；暂不抽象 Anthropic/Gemini。ticket runtime 调 provider 时必须消费这个协议聚合出的 `ProviderResult` / `ProviderFailure`，而不是直接依赖 provider-specific audit dict。

| Event | 含义 |
|---|---|
| `request_started` | provider 内部一次请求 attempt 已发出 |
| `connected` | HTTP/SSE 连接已建立 |
| `first_token` | 收到第一段 assistant 内容或等价事件 |
| `content_delta` | assistant 文本增量 |
| `heartbeat` | provider 或 adapter 心跳 |
| `schema_candidate` | 可解析的结构化候选 |
| `completed` | 正常完成 |
| `failed_retryable` | provider 内部可重试失败 |
| `failed_terminal` | provider 内部最终失败或不可重试失败 |

所有 event 必须包含：

- provider name；
- model；
- request id；
- attempt id；
- monotonic timestamp；
- raw byte count / text char count；
- error category if failed。

## Timeout 语义

| Timeout | 含义 | 触发后 |
|---|---|---|
| `connect_timeout` | 建立连接超时 | retryable provider failure |
| `first_token_timeout` | 已发请求但未收到 first token | retryable provider failure |
| `stream_idle_timeout` | first token 后长时间无 delta/heartbeat | retryable or terminal by policy |
| `request_total_timeout` | 单次请求最大墙钟预算 | terminal for attempt, recovery by ticket policy |
| `ticket_lease_timeout` | 执行票租约过期 | runtime timeout，不等同 provider timeout |

实现备注（2026-05-01）：provider smoke 将 `ticket_lease_timeout` 标记为 `not_applicable_provider_smoke`，以证明 provider 层测试不依赖 ticket lease。`request_total_timeout` 只作为单次 provider request 墙钟预算，不复用 `first_token_timeout` 或 `stream_idle_timeout`。

禁止把 `stream_idle_timeout` 隐式当作总预算，除非配置显式声明。

## 错误分类

| 分类 | 示例 | 默认处理 |
|---|---|---|
| `connect_error` | DNS/TCP/TLS/HTTP connect failure | retryable |
| `upstream_unavailable` | 429/5xx/网关错误 | retryable with backoff |
| `first_token_timeout` | 无 first token | retryable |
| `stream_read_error` | SSE 读取中断 | retryable if partial invalid, terminal if repeated |
| `malformed_stream_event` | SSE JSON malformed | retryable + raw archive |
| `empty_assistant_text` | 完成但没有 assistant text | terminal provider_bad_response |
| `schema_validation_failed` | 文本存在但 schema 不符 | retryable by schema budget，不归入上游不可用 |
| `write_set_violation` | 输出要求越权写 | terminal contract violation |
| `placeholder_delivery` | 输出只有占位 source/evidence | terminal deliverable violation |

## Retry 契约

Retry 分两层：

1. Provider 内部 retry：OpenAI Responses streaming provider 采用 Codex-like 体验，最多 5 次标准内部 attempt，同一 execution input 下只为拿到正确 request/response；每次内部 attempt 都产生标准 `ProviderEvent`。
2. Runtime / ticket recovery retry：provider 5 次内部 attempt 全部失败后只返回最终 `ProviderFailure`；runtime 之后才按既有异常处理、incident、failover 或 recovery 机制处理。

Provider adapter 不能创建 ticket。Ticket recovery 不能伪造 provider success。Provider 内部 retry 不额外写 projection，不创建 workflow/ticket，不做多余审计动作。

## Late Event 规则

如果旧 ticket 已 timed out 或被 replacement supersede：

- late provider heartbeat 可以归档；
- late provider completed 不能覆盖 current graph pointer；
- late output 不能生成 completed ticket；
- 如需利用 late output，必须创建显式 recovery action 并记录 lineage。

## Streaming Soak Test

当前实现状态（2026-05-01）：

- [x] `backend/tests/live/openai_compat_reliability_suite.py` 可独立运行 provider-only streaming smoke，不创建 workflow、ticket、lease 或 progression event。
- [x] 默认 20 次短 streaming 请求，覆盖 small / medium / schema prompt，并按 `success rate >= 95%` 判定。
- [x] 可选 `--include-long-request` 覆盖预计可能超过 300s 的长请求，只放宽 `request_total_timeout_sec`。
- [x] 报告 `preferred_provider_id/preferred_model` 与 `actual_provider_id/actual_model`。
- [x] 报告 first token p95、stream idle gap p95、failure counts、response/request id、stream byte/text counters、failure category、provider attempt count、标准 ProviderEvent 列表和 JSON/schema resolver 信息。
- [ ] late provider event 不污染 current ticket projection 属于 runtime/ticket recovery 边界，仍在后续 Phase 2/Phase 4 验收。

每个 provider 配置必须有独立 smoke:

```text
20 consecutive streaming requests
same base_url/api_key/model
small prompt + medium prompt + schema prompt
success rate >= 95%
first token p95 recorded
stream idle gap p95 recorded
malformed event count = 0
empty assistant count = 0
```

如果其他 AI 编程框架在同一配置下稳定，而本项目 smoke 失败，则默认判定本项目 adapter/parser/timeout 有问题。

## 观测指标

Provider 层必须记录：

- requests started；
- connected；
- first token latency；
- total duration；
- input/output token estimate；
- stream byte count；
- retry count；
- schema retry count；
- provider error category；
- fallback provider/model；
- preferred vs actual provider/model。

## 禁止事项

1. 禁止 provider fallback 静默伪装成原 provider 成功。
2. 禁止 provider adapter 直接写 ticket projection。
3. 禁止用默认 fake source/test evidence 填补 provider 空输出。
4. 禁止把 schema validation failure 简化为 upstream unavailable。
5. 禁止 request total timeout 和 ticket lease timeout 混用。
6. 禁止 old attempt 的 late heartbeat 改写 active ticket。

## 验收标准

- Provider adapter 可在无 workflow 的独立测试中运行。
- Streaming parser 有 malformed SSE、partial chunk、empty text、slow first token、slow idle 的测试。
- Provider retry 和 ticket recovery 的事件边界清晰。
- 015 中的 provider 失败类型能被重新分类并解释。
