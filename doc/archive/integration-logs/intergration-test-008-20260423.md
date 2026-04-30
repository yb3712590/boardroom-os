# intergration-test-008-20260423

这份记录只保留这轮长测真正有价值的内容：

- 这轮要验证什么
- 开跑前改了什么
- 真实运行过程里发生了什么
- 遇到的问题、修法和验证结果
- 最后为什么停在 stall

不再保留按分钟刷新的探针流水。

---

## 0. 这轮要验证什么

这轮测试的目标只有一件事：

- 把 `library_management_autopilot_live` 从旧 Python 入口改成单 TOML 配置驱动的 full live runner，然后用真实 provider 再跑一轮

固定口径：

- 场景：`library_management_autopilot_live`
- 命令：
  - `/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m tests.live.run_configured --config /Users/bill/projects/boardroom-os/backend/data/live-tests/library_management_autopilot_live.toml --clean --max-ticks 180 --timeout-sec 7200`
- provider id：`prov_openai_compat_truerealbill`
- base url：`http://codex.truerealbill.com:11234/v1`
- model：`gpt-5.4`
- fallback：`[]`

本轮要验证四件事：

- 图书馆 full live 是否已经彻底切到 `tests.live.run_configured`
- live 配置是否已经从旧入口里抽出来，变成单独 TOML
- 运行时是否真的只使用这一个 provider
- 真实长测里遇到卡点时，系统和代码能不能继续往前收口

本轮真相源以这些为准：

- `backend/data/scenarios/library_management_autopilot_live/boardroom_os.db`
- `backend/data/scenarios/library_management_autopilot_live/runtime-provider-config.json`
- `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- `backend/data/scenarios/library_management_autopilot_live/audit-summary.md`
- `backend/data/scenarios/library_management_autopilot_live/integration-monitor-report.md`
- `backend/data/scenarios/library_management_autopilot_live/failure_snapshots/stall.json`

---

## 1. 开跑前做了什么

这轮不是直接启动旧命令，而是先把 live 入口重写。

核心改动：

- 新增 `backend/tests/live/_config.py`
- 新增 `backend/tests/live/_scenario_profiles.py`
- 新增 `backend/tests/live/_configured_runner.py`
- 新增 `backend/tests/live/run_configured.py`
- 删除旧入口 `backend/tests/live/library_management_autopilot_live.py`
- `library_management_autopilot_smoke` 改成直接吃新 profile 常量
- 新增本机 live 配置：
  - `backend/data/live-tests/library_management_autopilot_live.toml`
- 文档入口同步切到新命令：
  - `doc/backend-runtime-guide.md`
  - `doc/mainline-truth.md`
  - `doc/todo/completed-capabilities.md`
  - `doc/TODO.md`

这轮图书馆场景的约束也一起收口了：

- 匿名、单机、单租户
- 唯一数据模型只允许 `books`
- 状态只允许 `IN_LIBRARY / CHECKED_OUT`
- 动作只允许 `Add / Check Out / Return / Remove`
- 禁止 auth、RBAC、分类体系、借阅历史、时间轴逻辑
- UI 强制是高密度 terminal / console 风格

开跑前回归：

- `/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m pytest backend/tests/test_provider_openai_compat.py backend/tests/test_live_configured_runner.py backend/tests/test_live_library_management_runner.py -q`
- 结果：
  - `66 passed`

---

## 2. 运行过程摘要

### 第一段：新入口和新 provider 配置正常启动

新命令启动后，场景目录正常重建。

启动早期已经确认：

- `WORKFLOW_CREATED`
- `EMPLOYEE_HIRED`
- `TICKET_CREATED`
- `TICKET_LEASED`
- `TICKET_STARTED`
- `PROVIDER_ATTEMPT_STARTED`

说明：

- 新 runner 已经接回共享 harness
- provider payload 已正确写入 `runtime-provider-config.json`
- 现场只看到 `prov_openai_compat_truerealbill`

### 第二段：最开始卡在首张治理票的首 token

第一张票是：

- `tkt_wf_e26f97c1faaf_ceo_architecture_brief`

早期现场不是“直接失败”，而是长时间等不到真正正文。

这段运行里最重要的现象是：

- 之前配置里 `first_token_timeout_sec=300`
- 但 live 现场一度出现超过 300 秒才写 `PROVIDER_FIRST_TOKEN_RECEIVED`

这暴露出一个真实 bug：

- 首 token 超时口径被 provider 元事件偷偷续命了

### 第三段：修掉 timeout 口径后，现场进入稳定重试

修补 timeout 逻辑后，live 现场开始按设计收口：

- 每轮大约在 `300s` 处触发 `FIRST_TOKEN_TIMEOUT`
- 会写出：
  - `PROVIDER_ATTEMPT_FINISHED`
  - `PROVIDER_RETRY_SCHEDULED`

这说明：

- timeout 修正已经真进了 live 路径
- 失败不再是“挂死不收口”

### 第四段：旧首票跑满 attempt 上限，打开 incident 和 breaker

原始首票最后跑满 provider attempt 上限。

关键收口点：

- 旧首票：`tkt_wf_e26f97c1faaf_ceo_architecture_brief`
- 第 `10` 次 provider attempt 仍然 `FIRST_TOKEN_TIMEOUT`
- 随后打开：
  - `INCIDENT_OPENED`
  - `CIRCUIT_BREAKER_OPENED`
- incident 类型：
  - `PROVIDER_EXECUTION_PAUSED`

这一步很关键。

它说明 provider pause / breaker 主链不是摆设，真的进了现场。

### 第五段：系统自动恢复，切出 retry 票继续跑

旧首票没有把 workflow 直接打死。

系统自动走了恢复链：

- `INCIDENT_RECOVERY_STARTED`
- `CIRCUIT_BREAKER_CLOSED`
- `TICKET_RETRY_SCHEDULED`
- 新 retry 票：`tkt_d4dfaf0bcf5e`

新 retry 票前几轮还是继续 `FIRST_TOKEN_TIMEOUT`。

但后面终于出现了突破：

- 第 `8` 次 attempt 拿到 `PROVIDER_FIRST_TOKEN_RECEIVED`
- 随后 `PROVIDER_ATTEMPT_FINISHED`
- `TICKET_COMPLETED`

同时：

- `PROVIDER_EXECUTION_PAUSED` incident 被自动关闭

这说明恢复链不只是“能开票”，而是真的能把卡住的治理票救回来。

### 第六段：治理链继续推进，但 workflow 没进实现链

恢复后的主线不是立刻结束，而是继续往前。

后续真实完成过的票包括：

- `tkt_d4dfaf0bcf5e`
  - `architecture_brief`
- `tkt_c6d02845c867`
  - maker-checker 票
- `tkt_003050a16496`
  - `technology_decision`
- `tkt_98ef0876fcbe`
  - 新一张 maker-checker 票

也就是说，这轮后半段已经不再是“provider 全挂”：

- 多张治理票拿到了首 token
- 多张治理票完成了 structured output
- 对应 artifact 也落到了 runtime 路径

但是最终 workflow 没有进入实现链。

最终状态是：

- `status=EXECUTING`
- `current_stage=project_init`
- active ticket 已清空
- 没有新的 open approval
- 没有新的 open incident
- runner 最终按 `stall` 收尾

---

## 3. 这轮遇到的关键问题

### 问题 A：旧测试把本机忽略文件当成仓库固定资产

场景：

- 新 worktree 里先跑基线回归
- `backend/data/` 本来就是 gitignore
- 但旧测试默认要求 `backend/data/integration-test-provider-config.json` 一定存在

影响：

- 不是主线逻辑坏了
- 是测试口径把“本机 live 配置”误当成“仓库内资产”

改动：

- 把旧断言改成只验证默认路径规则
- 图书馆场景改成单独吃：
  - `backend/data/live-tests/library_management_autopilot_live.toml`

结果：

- 这块已经收口

### 问题 B：`first_token_timeout_sec` 被 provider 元事件续命

场景：

- 明明配置了 `first_token_timeout_sec=300`
- 但 live 现场出现了超过 300 秒才收到首 token 的情况

根因：

- `backend/app/core/provider_openai_compat.py`
- 旧实现按“下一条事件”计算超时
- 只要 provider 在正文前持续吐 `response.created` 之类的元事件，就会不断刷新等待窗口

改动：

- 把流式等待改成 absolute deadline 语义
- 首 token 前只看“请求开始时间 -> 首个输出 token”
- 首 token 后只看“最后一个输出 token -> 下一个输出 token”
- 元事件不再续命

新增回归：

- `test_invoke_openai_compat_response_enforces_first_token_timeout_across_non_output_events`
- `test_invoke_openai_compat_response_enforces_stream_idle_timeout_across_non_output_events`

结果：

- 这块已经在真实长测里验证成功
- 后续多轮 timeout 都稳定落在约 `300s`

### 问题 C：治理链能恢复，但 workflow 没 fanout 到实现链

这是这轮最后真正没收掉的问题。

现场表现：

- `architecture_brief` 被救回并完成
- `technology_decision` 也完成了
- maker-checker 票也在继续跑
- 但 workflow 一直停在 `project_init`
- 没有继续进入实现链
- 最终 active ticket 清空，runner 判定 `stall`

这说明问题已经不在 provider 首 token 口径，而在 workflow 推进本身：

- 治理票可以继续生成
- 治理票也可以继续完成
- 但 workflow stage 没正常推进到后续实施链

---

## 4. 最终结果

这轮最终已经正常收口到场景文件，不是后台还在跑。

最终落盘文件：

- `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- `backend/data/scenarios/library_management_autopilot_live/audit-summary.md`
- `backend/data/scenarios/library_management_autopilot_live/integration-monitor-report.md`
- `backend/data/scenarios/library_management_autopilot_live/failure_snapshots/stall.json`

`run_report.json` 最终口径：

- `completion_mode=stall`
- `failure_mode=stall`
- `success=false`
- `workflow_id=wf_e26f97c1faaf`
- `finished_at=2026-04-23T04:08:12+08:00`

最终票据汇总：

- `5` 张票
- `4` 张 `COMPLETED`
- `1` 张 `FAILED`

---

## 5. 这轮得出的结论

这轮已经验证通过的东西：

- 图书馆 full live 已经切到配置驱动 runner
- 单 TOML live 配置已经能驱动真实场景
- provider 现场只使用 `prov_openai_compat_truerealbill`
- `first_token_timeout_sec` / `stream_idle_timeout_sec` 的修正已经真进 live
- provider pause incident / breaker / recovery / retry ticket 这条恢复链是真在工作的
- 恢复后，治理票能继续完成，不会卡死在第一次 timeout

这轮最后没通过的点：

- workflow 没有从治理链顺利推进到实现链
- 当前异常形态不是 provider 挂死，而是：
  - 治理链继续生成和完成
  - 但 workflow stage 仍停在 `project_init`
  - active ticket 清空后没有新推进
  - 最终被 runner 判定为 `stall`

讲白了：

- provider timeout 这条线，这轮已经基本查清并修正了
- 下一轮该盯的主问题，不再是 provider 首 token，而是 workflow 从治理输出切到实现 fanout 的推进逻辑
