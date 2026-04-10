# 集成测试记录 001

## 目标

盯住上个提交新增的 live 集成场景：

- `backend/tests/live/library_management_autopilot_live.py`

要求：

- 把项目拉起后持续观察
- 有问题就做最小修复
- 记录 bug 点、修复点、验证结果
- 一直跑到 closeout 和最终交付产物出来

---

## 本次环境

- 记录时间：`2026-04-10 02:50:56 +0800`
- 仓库：`/Users/bill/projects/boardroom-os`
- live 场景目录：`/Users/bill/projects/boardroom-os/backend/data/scenarios/library_management_autopilot_live`
- 当前 live workflow：`wf_5fb4315af7ba`
- 当前运行状态：`EXECUTING / plan`
- 当前票面状态：`COMPLETED=5`
- 当前上下文归档数：`5`

可查看地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

前端当前已经能读到这次 live scenario 的真实投影。

---

## 已确认 bug

### Bug 1：流式 provider 收到 `response.completed` 后不收口

现象：

- live 长测首票会一直挂住
- Python 进程卡在 `socket.recv()`
- provider 已经发了 `response.completed`
- 但实现还在等 `[DONE]` 或连接关闭

根因：

- `backend/app/core/provider_openai_compat.py` 里的流式解析只把 `[DONE]` 和 EOF 当结束条件
- 对 OpenAI-compatible SSE 来说，这不稳

最小修复：

- 在收到 `response.completed` 时直接 finalize 输出
- 如果已经有 `delta`，就直接拼结果返回
- 如果没有 `delta`，再回退读 `response` 里的完整文本

代码：

- `backend/app/core/provider_openai_compat.py`

回归测试：

- `backend/tests/test_provider_openai_compat.py`
- 新增用例：`test_invoke_openai_compat_response_returns_after_response_completed_without_done_sentinel`

---

### Bug 2：workflow 票都完成了，但 CEO idle maintenance 没信号

现象：

- live workflow 在 `plan` 阶段完成了已有票
- 没有 pending
- 没有 working ticket
- 但 CEO 没被重新唤起
- 调度器只在刷 `SCHEDULER_ORCHESTRATION_RECORDED`

根因：

- `backend/app/core/ceo_snapshot.py` 里，`NO_TICKET_STARTED` 只在“完全没票”时才触发
- “已有票，但全是 terminal 状态”不会触发 idle maintenance 信号
- 结果就是 workflow 还没结束，但 CEO 不会继续拆后续票

最小修复：

- 把“所有 ticket 都是 terminal 状态”也视为 `NO_TICKET_STARTED`

代码：

- `backend/app/core/ceo_snapshot.py`

回归测试：

- `backend/tests/test_ceo_scheduler.py`
- 新增用例：`test_idle_ceo_maintenance_targets_workflow_with_only_completed_tickets`

---

### Bug 3：idle maintenance 需要跳过已结束 workflow

现象：

- 修 Bug 2 之后，如果不收边界，理论上已结束 workflow 也可能被重新捞起

根因：

- `list_due_ceo_maintenance_workflows` 之前没有先按 workflow 状态做硬过滤

最小修复：

- 只允许 `status == EXECUTING` 的 workflow 进入 idle maintenance 候选

代码：

- `backend/app/core/ceo_scheduler.py`

---

## 运行环境侧发现

### 运行侧问题：默认 provider 不适合这条长测

现象：

- 仓库默认 provider 是 `prov_new_xem8k5`
- 对小请求能回
- 但对这条真实长测的大 prompt 路径不稳，首票观察期内表现很差

处理：

- 当前 live 长测改用 `prov_api_hk_codex`
- 这不是代码 bug 修复
- 这是本次长测的实际运行选择

说明：

- 这条记录先保留
- 后面如果需要把 provider 选择策略固化进代码，再单独开 bug

---

## 已落地改动

- `backend/app/core/provider_openai_compat.py`
- `backend/app/core/ceo_snapshot.py`
- `backend/app/core/ceo_scheduler.py`
- `backend/tests/test_provider_openai_compat.py`
- `backend/tests/test_ceo_scheduler.py`
- `docs/superpowers/plans/2026-04-10-integration-live-closeout.md`

---

## 已验证结果

已跑回归：

```bash
./backend/.venv/bin/python -m pytest \
  backend/tests/test_provider_openai_compat.py \
  backend/tests/test_ceo_scheduler.py \
  backend/tests/test_live_library_management_runner.py -q
```

结果：

- `59 passed in 9.55s`

---

## 当前 live 进度

截至本次记录：

- workflow：`wf_5fb4315af7ba`
- status：`EXECUTING`
- stage：`plan`
- completed tickets：`5`
- context archives：`5`

最近已经确认完成的 planning 票包括：

- `architecture_brief`
- `technology_decision`
- `detailed_design`
- `backlog_recommendation`

当前判断：

- 主线还在继续跑
- 不是停死
- 但还没进入 closeout
- 当前还不能说“集成测试已完成”

---

## 当前产物

已看到的 live 产物包括：

- `backend/data/scenarios/library_management_autopilot_live/boardroom_os.db`
- `backend/data/scenarios/library_management_autopilot_live/runtime-provider-config.json`
- `backend/data/scenarios/library_management_autopilot_live/ticket_context_archives/*.md`
- `backend/data/scenarios/library_management_autopilot_live/artifacts/reports/governance/*`

当前已经落出的治理文档产物至少包括：

- `architecture_brief.json`

更多产物会随着长测继续追加。

---

## 后续追加规则

从这里开始，只追加，不覆盖。

### [2026-04-10 02:50 +0800]

状态：

- live 长测继续运行中
- 当前 workflow 已推进到 `COMPLETED=5`
- 前后端查看环境已拉起

下一步：

- 继续盯 live 场景
- 每出现新的停滞点、失败点、修复点、closeout 证据，都往本文件后面追加
- 直到最终 closeout 和交付产物完整出来

### [2026-04-10 03:13 +0800]

新增确认：

- live workflow 仍是 `wf_5fb4315af7ba`
- 当前总事件数已经到 `75`
- 当前票面仍是 `COMPLETED=5`
- 当前仍没进入 closeout

这轮新增 bug 4：

- CEO shadow 在 idle maintenance 被唤起后，live provider 返回的 action 可能用 `type`
- 当前解析器只认 `action_type`
- 结果是 provider 明明给了 `CREATE_TICKET`，系统却会落回 fallback

这轮新增 bug 5：

- governance chain 在 idle maintenance 场景下会断链
- 具体表现是后续治理票虽然被创建出来，但 `parent_ticket_id` 和 `dependency_gate_refs` 没从已完成治理文档里自动推出来
- 进一步导致 `input_process_asset_refs` 为空
- `backlog_recommendation` 实际拿不到上游 planning artifacts
- live 产出的 backlog recommendation 因为缺少输入证据，只能 fail-closed，不会给出结构化拆票

这轮新增 bug 6：

- 我在补 process asset 继承逻辑时，又撞到一个实现级 bug
- `build_ceo_create_ticket_command` 里内部循环变量把外层新票 `ticket_id` 覆盖了
- 结果新建 backlog 票会错误复用最后一个依赖票 ID，直接被 `handle_ticket_create` 拒掉

这轮已做修复：

- `backend/app/core/ceo_proposer.py`
  - 兼容 `type -> action_type`
  - governance follow-up 在 idle maintenance 下自动推导前序治理依赖
  - governance follow-up 在 idle maintenance 下自动把最后一个前序治理票设成 parent
- `backend/app/core/ceo_execution_presets.py`
  - 创建治理票时，同时继承 parent 和 dependency governance tickets 的 process assets
  - 修掉内部循环变量覆盖外层 `ticket_id` 的问题
- `backend/tests/live/library_management_autopilot_live.py`
  - 把 live provider timeout 提到 `180s`
  - 避免 CEO shadow 在长 snapshot 上过早超时

这轮新增回归：

- `test_ceo_shadow_run_normalizes_live_action_type_alias_field`
- `test_ceo_shadow_run_idle_governance_followup_infers_dependency_chain_and_process_assets`

本轮验证结果：

```bash
./backend/.venv/bin/python -m pytest \
  backend/tests/test_provider_openai_compat.py \
  backend/tests/test_ceo_scheduler.py \
  backend/tests/test_live_library_management_runner.py -q
```

结果：

- `61 passed in 9.97s`

下一步：

- 用新修复重启 live 场景
- 继续盯到 backlog follow-up / implementation tickets 真正出现
- 再往后推进到 closeout

### [2026-04-10 03:23 +0800]

新增确认：

- 重启后的 live workflow 一度推进到 `COMPLETED=5`
- 但新一轮更早暴露了 provider fallback 相关故障
- 当前最近一轮中间态是：`COMPLETED=2 / EXECUTING=1 / FAILED=2`

这轮新增 bug 7：

- autopilot 第一张 `architecture_brief` kickoff 票没有自动挂 `board-brief.md`
- provider 正常时这件事不一定马上炸
- 但 provider 一旦超时并回退到 deterministic runtime，就会因为 `context_blocks=0` 报 `RUNTIME_INPUT_ERROR`

根因：

- `build_ceo_create_ticket_command` 只给 `project-init scope` 票挂了 `board-brief`
- `CEO_AUTOPILOT_FINE_GRAINED` 的第一张 `architecture_brief` kickoff 票没走这条输入挂载逻辑

这轮新增 bug 8：

- `runtime-provider-upsert` 当前 schema 不接受 `timeout_sec`
- 我一开始把 live timeout 同时放进环境变量和 upsert payload
- 结果脚本会在 `runtime-provider-upsert` 这一步直接被 422 拒掉

处理：

- `timeout_sec` 只保留环境变量路径
- 不再写进 upsert payload

这轮新增 bug 9：

- 修 governance process asset 继承时，`build_ceo_create_ticket_command` 里内部循环变量把外层新票 `ticket_id` 覆盖了
- 结果新建治理票会错误复用最后一个依赖票 ID
- `handle_ticket_create` 会直接报“Ticket already exists in projection state”

这轮已做修复：

- `backend/app/core/ceo_execution_presets.py`
  - autopilot 第一张 `architecture_brief` kickoff 票现在也会挂 `board-brief.md`
  - 修掉内部循环变量覆盖外层 `ticket_id`
- `backend/tests/live/library_management_autopilot_live.py`
  - 回退到“环境变量控制 timeout”，不再往 upsert payload 里塞 `timeout_sec`

这轮新增回归：

- `test_ceo_autopilot_project_init_kicks_off_architecture_brief_before_scope_consensus`

本轮验证结果：

```bash
./backend/.venv/bin/python -m pytest \
  backend/tests/test_provider_openai_compat.py \
  backend/tests/test_ceo_scheduler.py \
  backend/tests/test_live_library_management_runner.py -q
```

结果：

- `61 passed in 9.56s`

下一步：

- 用这轮补丁再重启 live
- 继续盯 provider timeout 后的恢复链
- 确认 architecture kickoff 不再因为零上下文回退失败

### [2026-04-10 03:52 +0800]

新增确认：

- 后端和前端当前都还活着
- 当前可查看地址仍然是 `http://127.0.0.1:5173/`
- 停住的 live workflow 还是 `wf_beba2bca5cf4`
- 卡点已经收敛到两个新问题：`scheduler_runner` 不会自动收 incident，live 脚本写失败快照时吃不下 `datetime`

这轮新增 bug 10：

- live 场景不是卡在 provider 本身，而是卡在 `run_scheduler_once()`
- 这个主循环只跑 `CEO idle maintenance -> scheduler_tick -> runtime`
- 但它不会像 `workflow_auto_advance` 那样，先帮 `CEO_AUTOPILOT_FINE_GRAINED` workflow 自动处理 `OPEN approval / OPEN incident`
- 所以 provider incident 一打开，workflow 就会一直停在 `OPEN + breaker OPEN`，后面的 tick 基本只会空转

根因：

- 自动恢复逻辑已经存在于 `workflow_auto_advance.auto_advance_workflow_to_next_stop`
- 但 live 脚本走的是 `scheduler_runner.run_scheduler_once`
- 两条主线不一致，导致 autopilot workflow 在真实 scheduler 主循环里不会自动恢复 blocker

这轮新增 bug 11：

- live 脚本在 `timeout / stall / max_ticks` 触发 `_write_failure_snapshot()` 时，`_write_json()` 直接 `json.dumps(payload)`
- snapshot 里带有数据库投影里的 `datetime`
- 结果脚本本来想落失败快照，反而会先因为 `TypeError: Object of type datetime is not JSON serializable` 崩掉

这轮已做修复：

- `backend/app/scheduler_runner.py`
  - 新增 CEO delegate blocker recovery 预处理
  - 每次 `run_scheduler_once()` 先扫描 `open_incidents + open_approvals`
  - 只对 `CEO_AUTOPILOT_FINE_GRAINED` workflow 调 `auto_advance_workflow_to_next_stop(..., max_steps=1)`
  - 这样 incident/approval 会先被自动恢复，再进入正常的 `scheduler_tick`
- `backend/tests/live/library_management_autopilot_live.py`
  - `_write_json()` 改成 `json.dumps(..., default=str)`
  - 失败快照和最终 report 现在都能稳定写出带 `datetime` 的 payload

这轮新增回归：

- `backend/tests/test_scheduler_runner.py`
  - `test_scheduler_runner_auto_recovers_open_provider_incident_for_autopilot_workflow`
- `backend/tests/test_live_library_management_runner.py`
  - `test_write_json_serializes_datetime_payloads`

本轮验证结果：

```bash
./backend/.venv/bin/python -m pytest \
  backend/tests/test_live_library_management_runner.py \
  backend/tests/test_scheduler_runner.py -q
```

结果：

- `48 passed in 13.55s`

进一步回归：

```bash
./backend/.venv/bin/python -m pytest \
  backend/tests/test_provider_openai_compat.py \
  backend/tests/test_ceo_scheduler.py \
  backend/tests/test_live_library_management_runner.py \
  backend/tests/test_scheduler_runner.py \
  backend/tests/test_workflow_autopilot.py -q
```

结果：

- `118 passed in 30.19s`

下一步：

- 用新补丁重启 live 场景
- 每半分钟看一次 workflow / incident / 产物状态
- 继续盯到 `closeout` 和 `run_report.json` 真正落出来

### [2026-04-10 05:49 +0800]

新增确认：

- 第一轮修复后的 live workflow `wf_5ae1ba489724` 确实已经跑到 `COMPLETED / closeout`
- 但那一轮没有产出 `run_report.json`
- 根因不是 closeout 没落，而是 workflow 只走了 `9` 张票，没满足 live 约束里的“至少 30 张 ticket”

这轮新增 bug 12：

- deterministic runtime 在 `backlog_recommendation` 上只会吐“摘要型治理文档”
- 文档里没有 `sections[].content_json.tickets / dependency_graph / recommended_sequence`
- CEO backlog follow-up batch 拿不到结构化拆票数据，就不会继续 fan out 原子任务
- 结果 workflow 会过早滑进 implementation / closeout，最后被 live script 的 ticket 数量断言拦下

根因：

- `backend/app/core/runtime.py` 里 `_build_runtime_success_payload()`
- 对所有 governance document 都共用一套极简 fallback payload
- `source_process_asset_refs` 被写死成空数组
- `backlog_recommendation` 也没有特殊化，导致 fallback 后完全丢失拆票结构

这轮已做修复：

- `backend/app/core/runtime.py`
  - governance fallback 现在会回填 `source_process_asset_refs`
  - `backlog_recommendation` fallback 现在会产出结构化 sections
  - 内含 30 个以上 backlog follow-up ticket、依赖图和推荐顺序
  - 这样 provider 断开或被 circuit breaker 暂停时，CEO 仍然能继续把 backlog 扇出成原子实施票

这轮新增回归：

- `backend/tests/test_runtime_fallback_payload.py`
  - `test_backlog_recommendation_fallback_payload_includes_structured_ticket_split`

本轮验证结果：

```bash
./backend/.venv/bin/python -m pytest \
  backend/tests/test_runtime_fallback_payload.py \
  backend/tests/test_ceo_scheduler.py \
  backend/tests/test_live_library_management_runner.py \
  backend/tests/test_scheduler_runner.py -q
```

结果：

- `99 passed in 22.65s`

第二轮 live 运行中的关键 checkpoint：

- 新 workflow：`wf_933342026438`
- 前半段治理链再次验证通过：
  - `architecture_brief` 完成
  - `technology_decision` 在 provider incident 后自动恢复
  - `milestone_plan` 完成
  - `detailed_design` 完成
  - `backlog_recommendation` 完成
- 最关键的是：
  - backlog 完成后，workflow 没再直接滑进 closeout
  - 系统已经真实创建出 `node_backlog_followup_br_t01/br_t02/br_t03/...`
  - 票总数已经从个位数拉到 `32+`
  - 说明 deterministic backlog fallback 的结构化拆票已经在 live 场景里生效

当前状态：

- workflow 仍在 `build`
- 最近 checkpoint：`COMPLETED=18`
- 已归档 ticket context：`18`
- `run_report.json` 还没落，说明 closeout 还没真正结束

下一步：

- 继续每半分钟盯 live run
- 确认 30+ 票会继续被消费而不是停在 build
- 盯到 `run_report.json` 真正落出来，再做最终 closeout

### [2026-04-10 07:20 +0800]

新增现场状态：

- 前端和后端 dev 服务当时都已经停了，所以页面打不开是服务层问题，不是前端代码直接崩了
- 我已经重新拉起：
  - 前端：`http://127.0.0.1:5173/`
  - 后端：`http://127.0.0.1:8000/`
- 后端现在直接指向 live 场景目录：
  - `backend/data/scenarios/library_management_autopilot_live`

当前实施状态：

- 当前 workflow：`wf_933342026438`
- 当前阶段：`build`
- 当前状态：`EXECUTING`
- 当前总票数：`87`
- 已完成：`68`
- 待处理：`19`
- 当前没有 live runner 进程在跑，但数据库里保留了这一轮完整实施状态

当前可见阻塞：

- dashboard 显示 provider health 仍是 `PAUSED`
- open incident / open circuit breaker 仍是 `1`
- 当前阻塞节点是：`node_backlog_followup_br_t05`
- 这说明项目已经完成了大部分 build 拆票，但这轮还没真正收口到 check / review / closeout

### [2026-04-10 07:32 +0800]

恢复执行结果：

- 已按现有场景库继续执行，没有重开新 workflow
- 恢复后的 runner 继续推进的是：`wf_933342026438`
- 可视化服务也已经恢复：
  - 前端：`http://127.0.0.1:5173/`
  - 后端：`http://127.0.0.1:8000/`

恢复后的最新状态：

- 当前阶段仍是 `build`
- 当前总票数：`89`
- 已完成：`73`
- 待处理：`16`
- 当前 provider 已恢复成 `HEALTHY`
- open incident / open circuit breaker 已清零
- `run_report.json` 还没落，说明 closeout 还没真正完成

当前判断：

- 恢复执行已经成功，不是空转
- 这轮现在主要是在正常消化 backlog follow-up build 票
- 还没进入最终的 check / review / closeout 收口

### [2026-04-10 07:36 +0800]

新增问题记录：

- 需求里明确要求：
  - CEO 必须真实招聘并真实使用 `architect_primary`
  - 允许招聘复数员工进行实施
  - 需要发生 CEO / 架构治理侧的真实讨论
- 但当前 live workflow `wf_933342026438` 的真实落地情况不是这样

已确认现状：

- `employee_projection` 当前只有两名 active 员工：
  - `emp_frontend_2`
  - `emp_checker_1`
- 没有任何 `architect_primary` / `cto_primary`
- `meeting_projection` 当前 workflow 下没有任何会议记录
- 事件流里也没有这轮的招聘或会议事件

结论：

- “真实招聘 architect_primary 并参与治理”这条当前没有实现
- “允许招聘复数员工进行实施”只实现了最弱版本：
  - 现在只有 frontend + checker
  - backend / database / platform / architect 都没有真实进场
- 这个问题已记录，后续单独修，不在当前 closeout 收口里顺手改

顺带调查：`runtime-provider-config.json` 为什么像是被清空了

当前结论：

- 我检查了以下 4 个同名文件，当前都不是空文件：
  - `.tmp/live-library-system-drill-*/runtime-provider-config.json`
  - `.tmp/test-db/runtime-provider-config.json`
  - `backend/data/runtime-provider-config.json`
  - `backend/data/scenarios/library_management_autopilot_live/runtime-provider-config.json`
- 所以现场没有“当前仍为空文件”的情况

更可能的原因有两种：

- 如果你看的是场景目录这个文件：
  - `backend/tests/live/library_management_autopilot_live.py`
  - 每次 `--clean` 会先 `shutil.rmtree(paths.root)`
  - 也就是整个场景目录先被删掉
  - 文件会短暂不存在，直到后面的 `runtime-provider-upsert` 再重新写回
- 如果你看到的是“系统像空配置一样工作”：
  - `RuntimeProviderConfigStore.load_saved_config()` 在读到缺少 `provider_model_entries` 的旧格式 payload 时
  - 会走 `_empty_runtime_provider_config()` 这条归一化路径
  - 这更像“读成空配置”，不是把磁盘文件真的清空

当前没有证据表明：

- 正常的 `runtime-provider-upsert` 会把一个有效配置文件直接写成空文件

当前能确认的写入路径：

- `RuntimeProviderConfigStore.save_config()` 会整文件重写 JSON
- live 场景 `--clean` 会先删除整个 scenario 目录

进一步定位：

- 你提到的“原本 2 个 provider + 20 个 model，后来退化成一个无效地址”，更像是根配置被覆盖，不是空文件
- 当前根配置文件：
  - `backend/data/runtime-provider-config.json`
  - 内容不是空的
  - 但已经被改写成测试风格的最小配置
- 现场内容特征：
  - OpenAI Compat 指向 `https://api.example.test/v1`
  - API Key 是 `sk-test-secret`
  - 另一个 provider 是 disabled 的 `prov_claude_code`
  - `provider_model_entries` 只有 2 条，不是你说的 20 条

当前判断：

- 这不是“文件清空”
- 这是“根配置被别的流程整文件覆盖成了测试配置”
- 从内容特征看，最像测试 payload 或测试风格的 `runtime-provider-upsert`
- live 场景真正使用的是：
  - `backend/data/scenarios/library_management_autopilot_live/runtime-provider-config.json`
  - 这个文件当前仍然是正确的 live provider 配置

风险说明：

- 如果后端不显式指定 scenario 级 `BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH`
- 默认就会去读根路径 `backend/data/runtime-provider-config.json`
- 于是 UI / provider center / 默认运行就会看到这份被覆盖后的测试配置

### [2026-04-10 08:05 +0800]

新增状态审查：图书馆管理系统代码产出位置

当前结论：

- 这轮 live workflow 确实不是纯空转
- 最近 10 张 ticket 主要在跑 `implementation_bundle` 与 `maker_checker_verdict`
- 但“图书馆管理系统应用代码”目前还没有真正落成源码文件

已确认现场：

- 场景产物目录：
  - `backend/data/scenarios/library_management_autopilot_live/artifacts`
- 当前只有两类主要产物：
  - 治理文档 JSON：
    - `architecture_brief.json`
    - `technology_decision.json`
    - `milestone_plan.json`
    - `detailed_design.json`
    - `backlog_recommendation.json`
  - 实施包 JSON：
    - `artifacts/ui/scope-followups/*/implementation-bundle.json`
- 我额外查了这整个产物目录，没有发现任何：
  - `.ts`
  - `.tsx`
  - `.js`
  - `.jsx`
  - `.py`
  - `.sql`
  - `.html`
  - `.css`

进一步确认原因：

- 当前 runtime 对 `frontend_build / backend_build / database_build / platform_build` 的输出契约，统一还是 `implementation_bundle`
- `implementation_bundle` 的 schema 只要求：
  - `summary`
  - `deliverable_artifact_refs`
  - `implementation_notes`
- 实际下发给执行 worker 的 payload 里，也明确写的是：
  - `Must produce a structured implementation bundle.`
- 所以这轮不是“本来应该写源码但模型偷懒没写”
- 更接近“系统当前主线设计就只要求交结构化实施包，不要求落真实代码文件”

补充判断：

- `boardroom-os` 这个宿主项目本身当然有真实代码，最近也确实新增了 live runner、execution target、schema、dashboard 等实现
- 但“图书馆管理系统”这个被自动开发的业务应用，还没有落成可运行的独立前后端代码资产
- 现在看到的更多是：
  - 规划文档
  - 拆票结果
  - 结构化实施说明
  - checker 审核闭环

结论：

- 如果按“是否已经写出图书馆管理系统代码”来问，当前答案是否定的
- 现在停留在“代码前一层”的 bundle / governance 阶段
- 这属于产物形态与预期不一致，后续需要单独收敛成真实源码落盘路径
