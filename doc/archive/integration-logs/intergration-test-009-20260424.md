# intergration-test-009-20260424

本记录覆盖上一份失败的 009，只保留第九轮 `library_management_autopilot_live` 长测的有效信息。

## 1. 测试口径

- 场景：`library_management_autopilot_live`
- 启动入口：`python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live.toml --clean --max-ticks 180 --timeout-sec 7200`
- 场景目录：`backend/data/scenarios/library_management_autopilot_live/`
- 日志目录：`.tmp/integration-monitor/live-009-20260424/`
- Provider：`prov_openai_compat_truerealbill`
- Base URL：`http://codex.truerealbill.com:11234/v1`
- Model：`gpt-5.4`
- Role strategy：`architect_primary=xhigh`，其他执行角色 `high`
- Provider 限制：本轮只允许使用 `prov_openai_compat_truerealbill`，不允许 fallback provider。

## 2. 启动与最终状态

- 最终 workflow：`wf_b50260a690dd`
- 最终 stage：`plan`
- workflow projection：`EXECUTING`
- harness completion mode：`timeout`
- runner 最终退出：`RuntimeError: Scenario timed out. Snapshot: backend/data/scenarios/library_management_autopilot_live/failure_snapshots/timeout.json`
- `run_report.json`：已落盘，`success=false`
- `audit-summary.md`：已落盘
- `integration-monitor-report.md`：已落盘
- `failure_snapshots/timeout.json`：已落盘

票状态：

- Total：`4`
- Completed：`0`
- Failed：`3`
- Pending：`1`
- Pending ticket：`tkt_63e6e6710c7c` / `node_ceo_architecture_brief`

## 3. Provider 绑定修复

### 现象

启动阶段发现治理雇员 provider 绑定不一致：

- 默认 roster 员工 `emp_frontend_2`、`emp_checker_1` 使用 `prov_openai_compat_truerealbill`
- 首票 provider attempt 使用 `prov_openai_compat_truerealbill / gpt-5.4`
- 但 CEO 自动 hire 的 `emp_architect_governance` 一度使用旧默认 `prov_openai_compat`

这违反了“本轮只使用 truerealbill provider”的测试口径。

### 根因

`execute_ceo_action_batch()` 执行 `HIRE_EMPLOYEE` 时，provider 选择顺序原先偏向 action payload / staffing template。`backend/app/core/staffing_catalog.py` 的 hire template 仍包含旧默认 `prov_openai_compat`，导致 runtime config 的 `default_provider_id=prov_openai_compat_truerealbill` 被 template 截断。

### 修复

- `backend/app/core/ceo_executor.py`：CEO hire provider 解析顺序改为：
  - action payload `provider_id`
  - runtime provider config `default_provider_id`
  - staffing template `provider_id`
- `backend/tests/test_ceo_scheduler.py`：新增 `test_ceo_hire_execution_prefers_runtime_default_provider_over_template`
- `backend/tests/test_live_library_management_runner.py`：新增 live scenario environment provider override 测试

### 验证

执行：

```bash
cd backend && pytest -q \
  tests/test_ceo_scheduler.py::test_ceo_hire_execution_prefers_runtime_default_provider_over_template \
  tests/test_ceo_scheduler.py::test_project_init_can_use_live_provider_to_hire_architect_before_kickoff \
  tests/test_live_library_management_runner.py::test_live_scenario_environment_sets_configured_default_employee_provider \
  tests/test_persona_profiles.py::test_build_default_employee_roster_supports_provider_override
```

结果：

```text
4 passed in 0.75s
```

修复后确认：

- `emp_frontend_2.provider_id=prov_openai_compat_truerealbill`
- `emp_checker_1.provider_id=prov_openai_compat_truerealbill`
- `emp_architect_governance.provider_id=prov_openai_compat_truerealbill`
- 首票 `PROVIDER_ATTEMPT_STARTED`：`provider_id=prov_openai_compat_truerealbill`，`actual_model=gpt-5.4`

## 4. 长测失败原因

本轮没有进入 `PROVIDER_FIRST_TOKEN_RECEIVED`，也没有产出 `architecture_brief`。

provider attempt 结果：

- Observed attempts：`10`
- Attempts `1-9`：均以 `REQUEST_TOTAL_TIMEOUT` 失败并进入 retry
- Attempt `10`：timeout snapshot 时仍为 `IN_PROGRESS / awaiting_first_token`

关键结论：

- provider 绑定问题已修复。
- retry / failure snapshot / run report / audit summary 审计链完整。
- 但首 token 始终未返回，长测未推进出首张 architecture brief。

## 5. `REQUEST_TOTAL_TIMEOUT` 追查结论

`REQUEST_TOTAL_TIMEOUT` 不是本轮 provider 口径，而是代码里残留的 legacy total timeout 语义。

证据链：

- `backend/tests/live/_config.py` 的 `LiveProviderConfig.compat_timeout_sec` 返回 `max(first_token_timeout_sec, stream_idle_timeout_sec)`。
- `build_runtime_provider_payload()` 又把该值写入 `timeout_sec` 和 `request_total_timeout_sec`。
- `backend/app/core/runtime_provider_config.py` 的 `RuntimeProviderConfigEntry.normalize_legacy_fields()` 会把 `request_total_timeout_sec` 归一化为非空并写回 provider config。
- `backend/app/core/provider_openai_compat.py` 的 `_ResponsesStreamAccumulator.check_timeout()` 先检查 `request_total_timeout_sec`，再检查 first token / stream idle。

因此首 token 未返回且 300s 到达时，当前代码先命中 `REQUEST_TOTAL_TIMEOUT`，而不是期望的 `FIRST_TOKEN_TIMEOUT`。

后续应修正：

- streaming provider 不再使用 total request timeout 作为第三种终止条件。
- live runtime provider payload 不再生成 `request_total_timeout_sec`。
- runtime provider config 不再从 legacy `timeout_sec` 派生 `request_total_timeout_sec`。
- 测试期望从 `REQUEST_TOTAL_TIMEOUT` 改为 `FIRST_TOKEN_TIMEOUT` / `STREAM_IDLE_TIMEOUT`。

## 6. 本轮有效产物

- `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- `backend/data/scenarios/library_management_autopilot_live/audit-summary.md`
- `backend/data/scenarios/library_management_autopilot_live/integration-monitor-report.md`
- `backend/data/scenarios/library_management_autopilot_live/failure_snapshots/timeout.json`
- `backend/data/scenarios/library_management_autopilot_live/ticket_context_archives/tkt_wf_b50260a690dd_ceo_architecture_brief.md`
- `backend/data/scenarios/library_management_autopilot_live/ticket_context_archives/tkt_40f1a5be7208.md`
- `backend/data/scenarios/library_management_autopilot_live/ticket_context_archives/tkt_7d9cb207684c.md`

没有产出项目代码、测试 evidence 或 git evidence。
