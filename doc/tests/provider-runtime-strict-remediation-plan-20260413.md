# Provider Runtime Strict Remediation - 2026-04-13

> 这是专项 P0 记录。
> 覆盖两份审计报告全部问题的总计划，见 `doc/tests/integration-audit-remediation-master-plan-20260413.md`。

## 目标

这轮整改只收一个核心问题：

- provider 失败后，不再把结果改写成本地成功
- provider 选择链、超时、重试和审计信息，统一按远端真实执行结果记录

## 已落地变更

### 1. Runtime fail-closed

- runtime 主链不再走 `LOCAL_DETERMINISTIC` 补成功
- 无可用 provider 时，统一返回 `PROVIDER_REQUIRED_UNAVAILABLE`
- provider paused / config incomplete / auth failed / upstream unavailable 都会保留真实失败
- `provider_candidate_chain`、`provider_attempt_log`、`fallback_blocked=true` 会写进 failure detail

### 2. Provider 选择与切换

- `provider_model_entry_refs[]` 现在按顺序参与候选链
- 绑定链上的后续 provider 会先于 `fallback_provider_ids[]` 被尝试
- `runtime_preference` 指向不可用 provider 时直接失败，不再静默降级
- `fallback_provider_ids[]` 仍保留，但只作为主 provider 的链尾兼容补充

### 3. OpenAI-compatible 请求与超时

- system 消息改成顶层 `instructions`
- user / assistant 消息改成可读文本，不再双重 JSON 包裹
- 新增阶段化超时字段：
  - `connect_timeout_sec`
  - `write_timeout_sec`
  - `first_token_timeout_sec`
  - `stream_idle_timeout_sec`
  - `request_total_timeout_sec`
  - `retry_backoff_schedule_sec`
- 新增 failure kind：
  - `FIRST_TOKEN_TIMEOUT`
  - `STREAM_IDLE_TIMEOUT`
- provider 级默认重试间隔改成 `[2, 8, 20]`

### 4. Projection / UI / 审计

- runtime provider projection 新增：
  - `fallback_blocked`
  - `provider_candidate_chain`
- dashboard 和前端读面已改成 `PROVIDER_REQUIRED_UNAVAILABLE / UNAVAILABLE`
- live harness 新增场景根目录 `audit-summary.md`
- failure snapshot 额外写出：
  - `provider_candidate_chain`
  - `provider_attempt_log`
  - `fallback_blocked`
  - `final_failure_kind`

## 这轮重点验证

后端：

- `backend/tests/test_provider_openai_compat.py`
- `backend/tests/test_runtime_provider_center.py`
- `backend/tests/test_runtime_provider_api_center.py`
- `backend/tests/test_live_library_management_runner.py`
- `backend/tests/test_scheduler_runner.py`
- `backend/tests/test_api.py`

前端：

- `frontend/src/test/__tests__/components/RuntimeStatusCard.test.tsx`
- `frontend/src/test/__tests__/stores/boardroom-store.test.ts`
- `frontend/src/App.test.tsx`

## 当前已验证的行为

- 绑定链里的第二、第三个 provider 会进入 failover 候选
- provider auth failure 不会再切本地，也不会偷跑 backup provider
- provider paused 时不会执行 live path，也不会补 deterministic completed
- 无 provider 配置时 ticket 会失败，不会本地收口
- streaming 请求体已经切成 `instructions + input`
- 首 token 超时和流式静默超时会分开上报
- scenario 根目录会产出 `audit-summary.md`

## 仍需在真实环境继续盯的点

- 真实远端流式连接下，`stream_idle_timeout_sec` 的体感是否还要再收紧
- 多个真实备用 API 接入后，`provider_model_entry_refs[] + fallback_provider_ids[]` 的组合是否还需要进一步简化
- 现有 `test_scheduler_runner.py` 里那批与本轮无关的历史失败，仍需单独清
