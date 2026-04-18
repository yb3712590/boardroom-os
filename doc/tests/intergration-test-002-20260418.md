# intergration-test-002-20260418

这份记录只做两件事：

- 把 `library_management_autopilot_live` 两轮真实长测里遇到的问题收清楚
- 把“卡死时缺少什么审计证据”讲明白

这份文档是留档，不代表这些问题已经在当前会话里正式修好。

---

## 0. 测试背景

这轮长测目标是：

- 使用图结构 ticket runtime
- 重新开启 `library_management_autopilot_live`
- provider 固定为 `https://api-hk.codex-for.me/v1`
- 每 60 秒观察一次
- 重点看图是否收敛、scope 是否命中、graph health 是否健康

业务范围收缩为 9 个 capability：

- `reader_search`
- `reader_reservation`
- `reader_loan_history`
- `reader_profile`
- `admin_procurement`
- `admin_cataloging`
- `admin_inventory`
- `admin_user_management`
- `admin_system_config`

旧场景在重跑前已备份：

- `backend/data/scenarios/library_management_autopilot_live_backup_20260418-123418`

---

## 1. 第一轮长测

### 1.1 现场

第一轮 workflow：

- `wf_21c2ca2b0dab`

关键轨迹：

- `13:00:56 +08:00` workflow 创建
- `13:01:52 +08:00` maker 票 `tkt_wf_21c2ca2b0dab_ceo_architecture_brief` 创建、lease、start
- `13:07:40 +08:00` maker 票完成
- 同时创建 checker review 票 `tkt_93087ad9f0ed`
- `13:09:24 +08:00` review 票被 `emp_checker_1` lease 并 start
- `13:10:19 +08:00` 第一条 `integration-monitor-report.md` 落盘
- `13:13:39 +08:00` 落出 `failure_snapshots/max_ticks.json`

最终状态：

- workflow 仍是 `EXECUTING / project_init`
- ticket 状态是 `1 completed + 1 executing`
- active ticket 是 `tkt_93087ad9f0ed`
- node 是 `node_ceo_architecture_brief`
- role 是 `checker_primary`
- output schema 是 `maker_checker_verdict`
- `run_report.json` 不存在

### 1.2 第一轮问题

#### 问题 A：in-process runtime 不会恢复 `EXECUTING` 票

review 票 `tkt_93087ad9f0ed` 已经有：

- `TICKET_LEASED`
- `TICKET_STARTED`

但后续 scheduler trace 里，`runtime_execution.count` 一直是 `0`。

说明：

- 票进入 `EXECUTING`
- 但后续 tick 没再接管它

根因是 in-process runtime 只扫 `LEASED`，不扫 `EXECUTING`。

这会导致：

- 对外部 worker 模式没问题
- 对 in-process 模式有问题

因为 in-process 本来应该自己完成：

- `lease -> start -> execute -> result-submit`

当前实现允许 `start` 后掉在半空，没有 `EXECUTING -> resume` 路径。

#### 问题 B：review lane 的 compiled package guard 查错 graph node

补测试时抓到，review 票结果提交会被拒。

拒绝原因是：

`Compiled execution package is outdated. Reload runtime state before retrying (runtime node version 8 != expected 13).`

根因是：

- guard 校验 runtime node version 时直接用 `meta.node_id`
- 但 review lane 的真正 graph node id 是 `node_id::review`

结果：

- guard 查到了 execution lane
- 版本比对错位
- 合法的 review 结果被当成 stale package

#### 问题 C：当场卡住时，证据虽然比旧版多，但还不够完整

第一轮至少已经有这些证据：

- `ticket_context_archives/*.md`
- `integration-monitor-report.md`
- `failure_snapshots/max_ticks.json`
- SQLite 事件流

但它仍缺一类关键证据：

- 如果 review 票进入 `EXECUTING` 后不再推进
- 系统没有显式写出“为什么这张 active ticket 后续没再进入 runtime_execution”

也就是说，现有审计更像“看结果能推断出卡住”，还不是“系统主动声明卡住原因”。

---

## 2. 第二轮长测

### 2.1 现场

第二轮 workflow：

- `wf_1c159db8f596`

关键轨迹：

- `13:54:10 +08:00` workflow 创建
- `13:56:48 +08:00` maker 票 `tkt_wf_1c159db8f596_ceo_architecture_brief` 创建、lease、start

然后就没有然后了。

现场长期停在：

- workflow: `EXECUTING / plan`
- ticket: `tkt_wf_1c159db8f596_ceo_architecture_brief`
- role: `frontend_engineer_primary`
- output schema: `architecture_brief`
- 状态: `EXECUTING`

同时缺少：

- `integration-monitor-report.md`
- `run_report.json`
- failure snapshot

### 2.2 第二轮问题

#### 问题 D：maker 票 start 之后，provider 执行阶段卡住

这次不是 review lane 卡住。

证据链说明它卡在更早的位置：

- `TICKET_STARTED` 已存在
- ticket context archive 已经生成
- compile request / execution package / rendered payload 都已就位

这说明：

- `start` 已完成
- `compile` 已完成
- `archive` 已完成

但后面没有：

- terminal event
- result-submit
- downstream checker ticket
- orchestration trace
- failure snapshot

所以卡点范围已经很窄：

- 大概率卡在 live provider 调用本身
- 或 provider 调用返回前后的极窄窗口

就现场形态看，更像是 provider 调用卡住，没有返回。

#### 问题 E：第二轮缺少“卡死审计”

这是这份文档最重要的一条。

第二轮现场已经满足“明显卡死”的特征：

- 进程还活着
- workflow 不再推进
- ticket 停在 `EXECUTING`
- 没有新的事件
- 没有新的 artifacts

但系统没有留下任何能解释这个卡死的正式证据：

- 没有 `integration-monitor-report.md`
- 没有 `run_report.json`
- 没有 failure snapshot
- 没有 `provider_attempt_log`
- 没有 `retry_backoff_schedule_sec`
- 没有 `provider_attempt_count`
- 没有 `elapsed_sec`
- 没有“当前是第几次 attempt”

这意味着：

- 现场可以推断“卡在 provider”
- 但审计上不能证明“卡了多久、重试了几次、单次 300s 是否命中、是否已经耗尽 10 次”

换句话说：

**第二轮不是只卡在 provider，还是卡在“provider 卡住时没有留下足够审计证据”。**

---

## 3. 关于“10 次重试 + 300s”这件事

代码层现状：

- 最大 attempt 数是 `10`
- 单次 provider request 的 total timeout 是 `300s`
- `first_token_timeout_sec` / `stream_idle_timeout_sec` / `request_total_timeout_sec` 默认都是 `300s`
- backoff schedule 是 `[1, 2, 4, 8, 16, 32, 60, 60, 60]`

但这里要说清：

- 当前 `300s` 是**单次请求超时**
- 不是整张票从第一次 attempt 到最后失败的**全过程总时长上限**

更关键的是：

**第二轮现场里没有任何审计证据能证明这套 10 次 / 300s 真的发生了。**

也就是说：

- 代码里有这个策略
- 现场里没有这个证据

这是一个独立审计缺口。

---

## 4. 两轮问题总表

### 第一轮

- review 票进入 `EXECUTING` 后，in-process runtime 不恢复执行
- review lane package guard 查错 graph node，导致结果提交可能被误判 stale
- 卡住时虽然有 probe 和 max_ticks snapshot，但没有系统级“主动声明卡住原因”的证据

### 第二轮

- maker 票在 provider 执行阶段卡住
- start / compile / archive 都完成了，但 provider 调用后没有返回
- 更严重的是，没有形成 probe、run_report、failure snapshot
- 所以“卡死审计”缺失，无法正式证明：
  - 卡在第几次 attempt
  - 单次 300s 是否命中
  - 总共重试了几次
  - 从开始卡住到结束一共耗时多久

---

## 5. 这轮会话的处理结论

本会话里，这些问题已经被重新整理并留档。

按当前要求，长测相关的临时补丁不保留，留待下一次新会话中正式修复。

下一次修复建议至少覆盖这 3 个点：

- in-process runtime 对 `EXECUTING` 票的 resume/接管闭环
- review lane runtime node guard 的 graph node 对齐
- provider 卡死时的强制审计落盘：
  - attempt start
  - attempt end
  - provider_attempt_log
  - retry_backoff_schedule_sec
  - elapsed_sec
  - 单次 timeout / 总耗时
  - 无论成功失败都要写 failure snapshot / run_report
