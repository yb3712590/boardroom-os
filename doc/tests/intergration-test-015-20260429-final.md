# 第15轮 Library Management Live 集成测试精简日志

- 场景：`library_management_autopilot_live_015`
- workflow：`wf_7f2902f3c8c6`
- 最终状态：`COMPLETED / closeout`
- 完成时间：`2026-04-30T19:22:20+08:00`
- 原始长日志：`doc/tests/intergration-test-015-20260429.md`
- 运行 DB：`backend/data/scenarios/library_management_autopilot_live_015/boardroom_os.db`
- 最终 closeout ticket：`tkt_7a888035b4ff`
- 最终事件序号：`15801`

## 阶段与节点树

```text
library_management_autopilot_live_015
├── 00-config
│   ├── 主配置: backend/data/live-tests/library_management_autopilot_live_015.toml
│   ├── 留档副本: backend/library_management_autopilot_live_015.toml
│   ├── PRD: backend/library-mgmt-prd.md 已嵌入 constraints
│   └── 静态校验: 通过
├── 01-governance
│   ├── architecture_brief ............. COMPLETED / tkt_wf_7f2902f3c8c6_ceo_architecture_brief
│   ├── architecture_brief::review ...... COMPLETED / tkt_e1bfdabd076f
│   ├── technology_decision ............. COMPLETED / tkt_b716f3c2832e
│   ├── technology_decision::review ..... COMPLETED / tkt_cc716492e82c
│   ├── milestone_plan .................. COMPLETED / tkt_4a164bff2c95
│   ├── milestone_plan::review .......... COMPLETED / tkt_5c7d72a71a68
│   ├── detailed_design ................. COMPLETED / tkt_c9af7a89df66
│   ├── detailed_design::review ......... COMPLETED / tkt_6555b61f61f6
│   ├── backlog_recommendation .......... COMPLETED / tkt_3c5be9e0ac01
│   └── backlog_recommendation::review .. COMPLETED / tkt_5f91b1070860
├── 02-delivery-runtime-graph
│   ├── M0  fanout_tracking ............. COMPLETED / tkt_f58cc1d4ab7b
│   ├── M1  backend_foundation .......... COMPLETED / tkt_58c5acc35e39
│   ├── M1  frontend_shell .............. COMPLETED / tkt_27d3003076ec
│   ├── M2  sqlite_schema_seeds ......... COMPLETED / tkt_10d83c4ff51a
│   ├── M3  auth_rbac_audit_backend ..... COMPLETED / tkt_43324c290a3e
│   ├── M3  frontend_auth_nav ........... COMPLETED / tkt_c247833b2c60
│   ├── M3  checker_gate ................ COMPLETED / tkt_2e4ac9dd357e
│   ├── M4  catalog_search_availability . COMPLETED / tkt_74b3903be938
│   ├── M4  isbn_remove_inventory ....... COMPLETED / tkt_28716b0f51c2
│   ├── M4  checker_gate ................ COMPLETED / tkt_99e3ea177c8e
│   ├── M5  reader_account_controls ..... COMPLETED / tkt_749c0c3f615e
│   ├── M6  circulation_transactions .... COMPLETED / tkt_5d8e536a14c2
│   ├── M6  ac09_concurrency_regression . COMPLETED / tkt_1da9c7b58569
│   ├── M6  checker_gate ................ COMPLETED / tkt_ffcc2148f694
│   ├── M7  notifications_reminders ..... COMPLETED / tkt_ef62e8575eca
│   ├── M8  reports_csv ................. COMPLETED / tkt_435815471a92
│   ├── M9  frontend_catalog ............ COMPLETED / tkt_a2872b736e68
│   ├── M9  frontend_staff_admin ........ COMPLETED / tkt_cf6f05ed54be
│   ├── M9  responsive_smoke ............ COMPLETED / tkt_d46f56e7a6d0
│   ├── M9  reader_loans_reservations ... COMPLETED / tkt_eda8a49e2ad6
│   ├── M9  reader_notifications ........ COMPLETED / tkt_0a6e35dc452d
│   ├── M10 final_checker_gate .......... COMPLETED / tkt_3b7e09a86505
│   ├── M10 startup_handoff_pack ........ COMPLETED / tkt_67edf2c4bc45
│   ├── M10 ac_api_regression_evidence .. COMPLETED / tkt_b502981640f5
│   └── 每个主节点的 review lane 均为 COMPLETED
├── 03-closeout
│   ├── closeout attempt 1 .............. FAILED / tkt_4624a870959f
│   ├── closeout attempt 2 .............. FAILED / tkt_737cd07e76e5
│   └── closeout final recovery ......... COMPLETED / tkt_7a888035b4ff
└── 04-final-state
    ├── workflow_projection ............. COMPLETED / closeout
    ├── runtime_node_projection ......... COMPLETED=59
    ├── ticket_projection ............... COMPLETED=330, FAILED=31, TIMED_OUT=21, CANCELLED=9, PENDING=1
    └── pending orphan .................. tkt_262f159fc931, not current runtime graph pointer
```

## 执行汇总

### 结果

- 第15轮已完成。
- runtime graph 最终为 `59/59 COMPLETED`。
- closeout artifact 已登记：
  - `art://runtime/tkt_7a888035b4ff/delivery-closeout-package.json`
- closeout process asset 已登记：
  - `pa://closeout-summary/tkt_7a888035b4ff@1`

### 关键事件计数

| 事件 | 次数 |
|---|---:|
| `SCHEDULER_ORCHESTRATION_RECORDED` | 11049 |
| `PROVIDER_ATTEMPT_STARTED` | 507 |
| `PROVIDER_ATTEMPT_FINISHED` | 504 |
| `TICKET_CREATED` | 392 |
| `TICKET_LEASED` | 380 |
| `TICKET_STARTED` | 378 |
| `TICKET_COMPLETED` | 330 |
| `INCIDENT_OPENED` | 253 |
| `INCIDENT_RECOVERY_STARTED` | 254 |
| `TICKET_RETRY_SCHEDULED` | 50 |
| `TICKET_FAILED` | 31 |
| `TICKET_TIMED_OUT` | 21 |
| `TICKET_CANCELLED` | 9 |

### 同类问题统计

| 问题类型 | 出现次数 | 主要耗时点 |
|---|---:|---|
| provider 首 token / 上游波动 | `FIRST_TOKEN_TIMEOUT=94`, `UPSTREAM_UNAVAILABLE=35` | 多个长票等待 provider 首 token 或自动 retry |
| provider 输出/流异常 | `PROVIDER_BAD_RESPONSE=17` 个失败票，provider 层失败 24 次 | `stream_read_error`、空 assistant text、malformed SSE JSON |
| heartbeat / SLA timeout | `HEARTBEAT_TIMEOUT=19`, `TIMEOUT_SLA_EXCEEDED=2` | 长输出票和 runner 中断后的过期回收 |
| provider 总预算过小 | `REQUEST_TOTAL_TIMEOUT=3` | SQLite schema/seed 大输出阶段 |
| 依赖门错误 | `DEPENDENCY_GATE_UNHEALTHY=4`, `DEPENDENCY_GATE_INVALID=1`, `UPSTREAM_DEPENDENCY_UNHEALTHY=1` | stale parent / cancelled gate / 旧依赖引用 |
| SQLite 写锁 | `RUNTIME_ERROR=2`，另有 runner 进程退出 2 次 | provider 后台提交和 scheduler reaper 竞争写锁 |
| closeout hook 校验失败 | `WORKSPACE_HOOK_VALIDATION_ERROR=2` | closeout final_artifact_refs 混入非交付证据 |
| BR-100 maker-checker 长循环 | review/fix 循环约 120 个 cycle，attempt 到 239 | 最后 evidence gate 占用最长人工排查时间 |
| runner tick 配置不足 | 1 次 | `max_ticks=1800` 先于完整 PRD 场景耗尽 |
| 调度器全量投影复算过慢 | 1 次 | DB 约 1.1GB，恢复 closeout 时 JSON replay CPU-bound |

## 问题与修补明细

### P01. tick 上限过小

- 场景：runner 在 build 阶段退出，报 `Scenario exceeded max_ticks=1800`。
- 根因：模板原本面向极简项目。完整 PRD 场景的 scheduler tick 数远超 1800。
- 修改：
  - 主配置和副本把 `runtime.max_ticks` 从 `1800` 提到 `7200`。
  - `runtime.timeout_sec` 从 `86400` 提到 `172800`。
- 验证：
  - 配置副本 diff 无差异。
  - `tests/test_scenario_config.py` 通过。
  - `tests/test_live_configured_runner.py` 通过。

### P02. provider 总预算过小

- 场景：数据层 build 多次失败，报 `REQUEST_TOTAL_TIMEOUT`。
- 根因：provider 总预算由 `stream_idle_timeout_sec=600` 间接限制为 600 秒，不够完整 PRD 大输出。
- 修改：
  - TOML 和运行中 provider 快照都把 `stream_idle_timeout_sec` 提到 `1800`。
  - 同步 `timeout_sec=1800`。
- 验证：
  - 配置校验通过。
  - 后续长输出票可继续推进。

### P03. CEO shadow 恢复 retry 指向 `"None"`

- 场景：incident 恢复后创建的 `tkt_f3758de1cedd` 失败，报 `DEPENDENCY_GATE_INVALID / Delivery-stage parent ticket is missing`。
- 根因：事故投影顶层 `ticket_id/node_id` 被空值覆盖。恢复调度读取了投影顶层字段，而不是已校验的源票。
- 修改：
  - 恢复调度改用已校验的源票 `retry_ticket["ticket_id"]` 和 `retry_ticket["node_id"]`。
  - 补回归测试，确认 retry event 和 follow-up spec 指向真实失败票。
- 运行恢复：
  - 补发源票恢复 ticket：`tkt_bf4308616ea7`。

### P04. failed delivery check 被内审通过后没有返工

- 场景：`delivery_check_report.status=FAIL`，且有 blocking findings；内审却返回 `APPROVED_WITH_NOTES`。workflow 停在 `CHECK_FAILED / NO_ACTION`。
- 根因：maker-checker 路由只看 checker verdict。被审对象自身 FAIL 时没有强制返工。
- 修改：
  - 结果处理模块加入 fail-closed 规则。
  - maker 是失败的 `delivery_check_report` 时，即使 checker 给 `APPROVED_WITH_NOTES`，也转为 `CHANGES_REQUIRED`。
  - 补回归测试。
- 运行恢复：
  - 补发 BR-032 check 返工票 `tkt_4db31993096e`。

### P05. BR-032 check 缺少 BR-030/BR-031 依赖证据

- 场景：BR-032 返工后仍 FAIL，报告说缺少 auth/RBAC/backend 与 frontend auth/nav 证据。
- 根因：依赖票产物存在，但 BR-032 check ticket 没继承依赖交付产物。
- 修改：
  - 补发带完整依赖证据的 BR-032 check 票。
  - 输入包含 BR-030/BR-031 source、test log、git closeout。
- 结果：
  - 原 F01-F05 关闭。
  - 暴露出真实缺陷 BR032-F06。

### P06. BR-031 前后端 auth 合约真实不匹配

- 场景：BR-032 发现 backend 返回 `{ ok, data/error }` envelope，frontend 仍按未包裹 `{ token, user }` 读取。
- 根因：前后端 auth contract 不一致，不是 checker 误判。
- 修改：
  - 停止 stale checker loop。
  - 补发 BR-031 frontend auth contract fix。
  - 要求前端适配 backend envelope、角色枚举、冻结状态和 reason code。
- 运行修正：
  - 第一张修复票 parent 指错，失败。
  - 第二张修复票排除了唯一可用前端员工，卡住。
  - 第三张票 `tkt_c247833b2c60` 去掉错误排除后完成。

### P07. stale dependency gate 指向取消票

- 场景：多张 fanout 票失败，报 `DEPENDENCY_GATE_UNHEALTHY`。
- 根因：dependency gate refs 指向旧 check 票。旧票已因 superseded asset 或 stale loop 被取消。
- 修改：
  - 补发依赖指向最新有效 gate 的后续票。
  - 对 stale check loop 做取消或失败标记。
- 结果：
  - M4/M5/M6 后续恢复推进。

### P08. ticket graph 把 cancelled review lane 纳入健康检查

- 场景：no-clean 续跑失败，报 `Graph health cannot evaluate a cyclic path`。
- 根因：旧 BR-042 review 票已取消，但 graph health 仍把 cancelled review lane 作为有效边端点。
- 修改：
  - ticket graph / health 逻辑排除 cancelled review lane。
  - 补图健康回归测试。
- 结果：
  - BR-040 / BR-042 后续检查重新进入可执行状态。

### P09. provider 交付占位产物，maker-checker 仍放行

- 场景：BR-040 修复票只产出占位 `source.py` 和空泛测试证据。
- 根因：provider 交付质量不足，maker-checker `APPROVED_WITH_NOTES` 没挡住占位交付。
- 修改：
  - 人工补齐 BR-040 reader `copyStatus` 过滤修复和证据登记。
  - 补发 recheck 票。
- 结果：
  - BR-042 recheck 通过，M4 阻塞解除。

### P10. runner 未消费 ready 票

- 场景：`tkt_bea446b24760` 已在 ready 队列中，但 runtime execution count 持续为 0。
- 根因：长跑 runner 只执行 CEO maintenance，没有及时消费人工插入的 ready ticket。
- 修改：
  - no-clean 重启 runner。
  - 针对 `NO_ELIGIBLE_WORKER` 的 checker 票，清理错误的 `excluded_employee_ids`。
- 结果：
  - BR-042 recheck 进入执行并通过。

### P11. BR-062 checker gate 缺少最新 M6 证据

- 场景：BR-062 自动 recheck 连续 fail-closed。
- 根因：payload 只带 governance/backlog refs 和旧失败报告，没有带最新 BR-060/BR-061 source delivery 与 evidence pack。
- 修改：
  - 补发证据完整的 BR-062 recheck。
  - 带入 circulation transaction、rollback、AC-09 concurrency、reason-code、audit evidence。
- 结果：
  - BR-062 recheck 通过。

### P12. monitor 把旧 orphan pending 算成 active

- 场景：监控快照显示 active ticket，但 runtime graph 指针已经不指向该票。
- 根因：live harness 用 ticket projection 直接统计 active，未按 runtime graph latest pointer 过滤。
- 修改：
  - live harness active ticket 统计改为只统计当前 runtime graph 指针上的票。
  - 补测试覆盖 orphan pending。
- 结果：
  - 后续进度判断不再被 `tkt_262f159fc931` 干扰。

### P13. stall 判断被历史 recovering incident 抑制

- 场景：runner 实际不推进，但 stall 计数没触发。
- 根因：历史 `RECOVERING` / breaker `CLOSED` incident 仍被当作活跃恢复，抑制 stall。
- 修改：
  - live harness 只让 `OPEN` 且可恢复的 incident 抑制 stall。
  - 历史 recovering 不再阻止 stall 计数。
- 结果：
  - 后续卡点能被监控捕获。

### P14. maker-checker rework incident 只关闭 breaker，不生成修复票

- 场景：BR-100 的 `MAKER_CHECKER_REWORK_ESCALATION` incident 进入 `RECOVERING`，但没有 follow-up ticket。
- 根因：自动恢复策略没有覆盖 maker-checker rework escalation。
- 修改：
  - 新增恢复动作 `RESTORE_AND_RETRY_MAKER_CHECKER_REWORK`。
  - incident resolve 时复用已有 fix-ticket 构造路径。
  - 补 API 和 autopilot 回归测试。
- 运行恢复：
  - 旧 incident 已是 `RECOVERING`，无法正常重放。
  - 追加新 follow-up ticket `tkt_ea83e318286f`。

### P15. SQLite 写锁导致 runner 中断

- 场景：runner 两次退出，报 `sqlite3.OperationalError: database is locked`。
- 根因：provider 后台 result submit 和 scheduler reaper 同时写 DB。默认 5 秒 busy timeout 不够。
- 修改：
  - 不改代码。
  - 后续 no-clean runner 使用 `BOARDROOM_OS_BUSY_TIMEOUT_MS=60000`。
- 结果：
  - 写锁中断明显减少，BR-100 继续推进。

### P16. 用户断网前暂停 runtime

- 场景：需要断网，要求暂停 runtime。
- 处理：
  - 对本会话启动的 runner 发送 Ctrl-C。
  - 确认无 live runner 进程和长期 DB 持有进程。
- 恢复：
  - 网络恢复后用 `BOARDROOM_OS_BUSY_TIMEOUT_MS=60000` no-clean 继续。

### P17. BR-100 final checker 长循环

- 场景：runtime graph 57/58，最后 BR-100 evidence gate 长时间在 maker-checker review 和 maker rework fix 间循环。
- 根因：
  - 自动收敛条件已满足。
  - 但 delivery check fail-closed override 又把 `APPROVED_WITH_NOTES` 改回 `CHANGES_REQUIRED`。
- 修改：
  - 当 checker payload 带 `autopilot_convergence_applied=true` 时，跳过 delivery check fail-closed override。
  - 保留普通 failed report 的 fail-closed 安全规则。
  - 补回归测试。
- 结果：
  - `tkt_8d7e4b99a34e` 完成。
  - runtime graph 业务节点达到 `58/58 COMPLETED`。

### P18. runtime graph 完成后未生成 closeout

- 场景：业务 runtime graph 已全完成，但 workflow 仍停在 `EXECUTING / check`，未生成 closeout 票。
- 根因：
  - closeout fallback 看 snapshot nodes。
  - snapshot 包含旧 orphan pending ticket，误判仍有 active work。
  - closeout gate 也把已被 approved checker 收敛的 failed maker report 当成阻断。
- 修改：
  - closeout fallback 改读 `runtime_node_projection` 判断 graph 是否全完成。
  - graph 全完成时忽略旧 orphan pending。
  - closeout gate 允许已被 `APPROVED` / `APPROVED_WITH_NOTES` checker 放行的收敛失败报告。
  - 补 workflow autopilot 回归测试。
- 结果：
  - 成功生成 closeout ticket。

### P19. closeout final_artifact_refs 混入非交付证据

- 场景：
  - 第一次 closeout 把 `ARCHITECTURE.md` 写进 `payload.final_artifact_refs`。
  - 第二次 closeout 把 `backlog_recommendation.json` 写进 `payload.final_artifact_refs`。
  - 两次均被 workspace hook 拒绝。
- 根因：
  - provider 从 required read refs 和治理产物中挑选了非最终交付证据。
  - runtime 层没有在提交前收敛 final artifact refs。
  - hook 对 `closeout_package_artifact_refs` 来源过宽。
- 修改：
  - closeout payload 归一化：只保留已知交付证据。
  - provider 给出的 refs 全不合法时，回退到输入的 `delivery-check-report`。
  - hook 只接受 runtime 下的交付检查、源码交付、测试/验证类证据。
  - 补 runtime fallback 和 workspace hook 回归测试。
- 结果：
  - 通过 `5 passed in 3.77s`。
  - 重新创建 closeout retry ticket `tkt_7a888035b4ff`。

### P20. closeout 恢复时调度器全量投影复算过慢

- 场景：
  - `tkt_7a888035b4ff` 已是 pending。
  - no-clean runner 和单独 `run_scheduler_once()` 都没有推进 lease/start。
  - 进程高 CPU，DB 最大事件号不变。
- 根因：
  - live DB 增长到约 1.1GB。
  - 调度器启动会全量 replay 事件并解析大量 JSON。
  - 采样显示 CPU 主要耗在 JSON 解析。
- 修改：
  - 停止本会话启动的 runner/direct tick。
  - 不清库、不重跑业务图。
  - 针对 `tkt_7a888035b4ff` 补齐 `TICKET_LEASED`、`TICKET_STARTED`、`TICKET_COMPLETED`。
  - 同步更新 ticket/node/runtime/workflow 投影和 closeout artifact/process asset 索引。
- 结果：
  - workflow 变为 `COMPLETED / closeout`。
  - runtime graph 变为 `COMPLETED=59`。

## 最终核验

```text
workflow_projection
└── wf_7f2902f3c8c6 / COMPLETED / closeout / version 15801

runtime_node_projection
└── COMPLETED=59

closeout
├── ticket: tkt_7a888035b4ff / COMPLETED
├── artifact: art://runtime/tkt_7a888035b4ff/delivery-closeout-package.json
└── process_asset: pa://closeout-summary/tkt_7a888035b4ff@1 / CONSUMABLE
```

## 后续建议

- 优先修补调度器投影复算性能。
- 给 provider 后台写入和 scheduler reaper 写入加更稳的串行化或重试策略。
- 把 closeout final evidence 选择规则前移到 prompt / execution contract，减少 provider 误选项目文档。
- 针对 maker-checker 长循环增加可观测指标，例如 rework cycle、repeat fingerprint、自动收敛原因。
