# Intergration Test 012 审计日志

## 基本信息

- 日期：2026-04-26
- 测试轮次：012
- 场景 slug：`library_management_autopilot_live_012`
- 测试配置：`backend/data/live-tests/library_management_autopilot_live_012.toml`
- 配置来源：由 `integration-tests.template.toml` 复制生成
- base_url：`http://codex.truerealbill.com:11234/v1`
- API key：已按用户提供值写入测试配置；本文档不记录明文密钥
- 运行入口：`python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_012.toml --clean`

## 模型绑定

- CEO：`gpt-5.5` / `high`
- 架构或分析角色：`gpt-5.5` / `xhigh`
- 开发类角色：`gpt-5.3-codex-spark` / `xhigh`

## 最终结论

第 12 轮最终业务 workflow 达到 `COMPLETED / closeout`，最终 workflow 为 `wf_6695c18ddb6f`。

严格按原 runner 退出状态看，本轮自然执行的最后一次 runner 仍失败，失败点是最终结果收集阶段缺少 workflow chain report artifact。该问题不是业务产物未完成，而是测试 harness 在收集完成态时没有补齐已有生命周期中的 chain report 生成动作。

在修补 harness 后，使用同一个已完成数据库重放 `collect_common_outcome()` 通过，结果为 workflow `COMPLETED / closeout`，compiled / archived tickets 为 `34 / 34`。因此本轮应拆分判断：

- 业务 workflow：成功完成，并有可查看产物。
- 原始 runner 退出：失败，失败于最终收集门禁。
- 修补后重放收集：成功。

## 最终产物状态

- 最终 workflow：`wf_6695c18ddb6f`
- 最终阶段：`closeout`
- ticket 汇总：`COMPLETED=28 / FAILED=6`
- active ticket：无
- open incident：无
- 失败 ticket 主要类型：provider bad response、workspace hook validation、closeout artifact refs 合约不合格；均已由 replacement、retry 或后续 closeout 收敛覆盖
- 用户人工查看产物后确认：产物本身已经没有问题

## 验证摘要

本轮修补过程中执行过以下定向验证：

- 配置验证：`tests/test_scenario_config.py`、`tests/test_live_configured_runner.py`，结果 `14 passed`
- CEO fallback / scheduler 相关：`tests/test_ceo_scheduler.py` 定向用例，最终结果 `8 passed, 112 deselected`
- live harness 相关：`tests/test_live_library_management_runner.py` 定向用例，最终结果 `4 passed, 42 deselected`
- runtime source delivery normalization：`tests/test_runtime_fallback_payload.py`，结果 `3 passed`
- workspace hook 验证：`tests/test_project_workspace_hooks.py -k "source_code_delivery or verification"`，结果 `9 passed, 12 deselected`
- workflow chain report：`tests/test_workflow_autopilot.py -k "chain_report"`，结果 `2 passed, 15 deselected, 1 warning`
- 已完成 DB 重放：`collect_common_outcome()` 在 `wf_6695c18ddb6f` 上通过，compiled / archived tickets 为 `34 / 34`

## 问题审计

### P01. backlog follow-up plan 缺失 workflow_id

**场景**

首轮 live runner 推进到 backlog follow-up 阶段后，CEO shadow pipeline 触发 incident。错误集中在 deterministic fallback 生成 follow-up ticket plan 时，`ticket_payload.workflow_id` 为空。

**详细情况**

incident 报错为 `deterministic_fallback.backlog_followup[plan_missing_fields]`，随后重复出现 `Backlog follow-up plan ticket_payload does not match the canonical CREATE_TICKET contract.`。

定位到 `workflow_controller._build_followup_ticket_plans()` 试图从 backlog created spec 中推断 `workflow_id`，但当时的 backlog ticket created payload 不包含 `workflow_id` / `workflow_ref` 等字段。与此同时，构造 controller view 的调用链已经持有真实 workflow id，只是没有显式传入该函数。

**改动**

- 修改 `backend/app/core/workflow_controller.py`
- 让 `_build_followup_ticket_plans()` 显式接收当前 `workflow_id`
- follow-up `CREATE_TICKET` payload 使用该 workflow id 填充 canonical contract 字段
- 在 `backend/tests/test_ceo_scheduler.py` 增加断言，确保 follow-up ticket payload 带当前 workflow id

**验证**

CEO scheduler 定向测试通过，覆盖 capability plan、deterministic backlog follow-up、fallback closeout 等相关路径。

**架构与幂等性评估**

这是实际的 controller contract 构造错误，不是为了跑测试的临时绕过。改动方向符合当前架构：workflow id 是 controller view 的上下文事实，应显式传递，而不是从不稳定 payload 里反向猜测。

幂等性良好。同一个 workflow 重复构造 follow-up plan 时，得到相同 workflow id，不引入随机状态，也不改变 ticket 去重策略。

**是否建议回退**

不建议回退。建议在新会话中保留，并审计是否还有类似“从派生 payload 猜顶层上下文”的模式。

### P02. 所有 follow-up ticket 已存在时 fallback 报 no_actions_built

**场景**

第二轮推进到 check / closeout 前后，所有 backlog follow-up plan 对应 ticket 都已经创建或完成。provider 在这种稳态下给出 `NO_ACTION`，但 deterministic fallback 仍报 `no_actions_built`。

**详细情况**

当所有 follow-up plans 都已有 existing ticket 且没有可创建 / 可 retry 动作时，系统实际处于“等待图归约或 closeout 条件成熟”的状态，不应把它视为 fatal contract error。

原逻辑里 `_build_backlog_followup_batch()` 在无 action 时抛出或导致 fallback error；同时 validator 仍按 controller state 期望 `CREATE_TICKET`，导致 provider 的 `NO_ACTION` 被拒绝，fallback 自己也无法给出合法动作，形成 incident 循环。

**改动**

- 修改 `backend/app/core/ceo_proposer.py`
- `_build_backlog_followup_batch()` 在无动作可构造时返回 `None`
- `build_deterministic_fallback_batch()` 在 backlog 无动作时优先尝试 closeout
- closeout 尚不可用时返回 `NO_ACTION`，等待现有 ticket / graph 状态自然归约
- 新增测试覆盖“所有 planned tickets 已存在时 batch 返回 none”

**验证**

CEO scheduler 定向测试通过，覆盖 backlog follow-up batch 与 closeout fallback。

**架构与幂等性评估**

这是状态机稳态处理问题。改动符合当前架构：没有新 work item 时应允许 CEO 层表达无动作，而不是强制制造无效 `CREATE_TICKET`。

幂等性良好。重复进入同一状态时都返回 `NO_ACTION` 或 closeout，不会重复创建 ticket。

**是否建议回退**

不建议回退。建议新会话继续审计 provider validator 与 deterministic fallback 的动作期望是否能统一表达“可创建、可 closeout、可等待”三种状态。

### P03. 最新 existing ticket 失败但同 node 已有较早完成票据

**场景**

M6 节点已经有较早完成票据，但同 node 后续又出现失败重试票据。capability plan 的 `existing_ticket_id` 指向较新的失败票据，导致 M7 依赖判断无法继续。

**详细情况**

deterministic fallback 只看 plan 中的 latest existing ticket。若该 ticket 处于 `FAILED` 或 `TIMED_OUT`，fallback 会判定需要 restore，并阻塞下游 follow-up 创建。但同 workflow / node 已经存在完成票据，足以满足依赖 gate。

这导致系统在恢复路径上被“最新失败”遮蔽了“已有完成产物”。

**改动**

- 修改 `backend/app/core/ceo_proposer.py`
- 当 planned existing ticket 是 terminal failure 时，查询同 workflow / node 的最新 completed ticket
- 若存在 completed ticket，则将其作为依赖 gate 的满足依据
- 新增回归测试覆盖“同节点先完成、后续失败重试仍可继续下游 follow-up”

**验证**

CEO scheduler 定向测试通过，覆盖该恢复分支。

**架构与幂等性评估**

这是实际的 dependency resolution 边界问题。修补方向总体合理：依赖应关心 node 是否已有可用完成产物，而不是只关心最新票据是否失败。

需要新会话重点审计一点：该逻辑可能掩盖“较早完成票据已过期或被后续失败证明不可用”的场景。当前代码按同 workflow / node 的 completed ticket 兜底，适合本轮阻塞，但架构上最好明确 completed artifact 的有效性规则，例如 attempt lineage、superseded 标记或 artifact freshness。

**是否建议回退**

不建议立即回退，否则会恢复本轮阻塞。建议保留并在新会话审计依赖 gate 的“completed ticket 可用性”定义，必要时改成更显式的 lineage / supersession 判断。

### P04. failure snapshot 审计复用最终质量门禁，掩盖原始失败

**场景**

runner 在失败退出时尝试写 failure snapshot，但 snapshot 构建过程本身因为 source delivery payload 质量审计抛错而终止。

**详细情况**

stderr 显示退出点为 `compact source delivery payload is missing raw verification output`。这不是当时业务阻塞的原始错误，而是 `_build_audit_snapshot()` 在失败快照路径复用了最终 `collect_common_outcome()` 级别的严格 source delivery 审计。

结果是 failure snapshot 没能稳定记录现场，反而用二次审计错误覆盖了原始 live incident。

**改动**

- 修改 `backend/tests/live/_autopilot_live_harness.py`
- 为 failure snapshot 增加专用审计包装
- snapshot 写入阶段捕获 source delivery payload audit error
- 将错误记录到 `source_delivery_payload_audit.audit_error`
- 不放宽最终 `collect_common_outcome()` 的质量门禁
- 新增测试覆盖 snapshot 审计异常只记录、不抛出

**验证**

live harness 定向测试通过。

**架构与幂等性评估**

这是测试 harness 的健壮性问题，不是业务 runtime 架构错误。修补符合审计系统设计：失败快照应尽最大努力保存现场，不能因为附加质量审计失败而丢失原始诊断信息。

幂等性良好。重复生成 snapshot 时，同样的 audit error 会被结构化记录，不改变 workflow 状态。

**是否建议回退**

不建议回退。建议保留。

### P05. final source delivery audit 不接受 compact payload

**场景**

workflow 已完成，但最终 `collect_common_outcome()` 失败，报 `compact source delivery payload is missing raw verification output`。

**详细情况**

相关 ticket 的 terminal event 采用 compact source delivery payload，没有顶层 `verification_runs`。但 raw verification output 并未丢失，而是存在于 `written_artifacts[*].content_json` 中，并且这些 artifact 被 `verification_evidence_refs` 引用。

初始考虑过把 `verification_runs` 写回生产完成事件，但这会扩大 runtime 事件 payload 的影响面，并触发现有 API snapshot incident。因此撤回该方向，改为只在 live harness 终态审计中按 evidence refs 还原验证输出。

**改动**

- 修改 `backend/tests/live/_autopilot_live_harness.py`
- source delivery 终态审计中，如果 payload 无顶层 `verification_runs`
- 则从 `verification_evidence_refs` 指向的 `written_artifacts.content_json` 读取 verification run
- 继续校验 raw stdout，而不是简单放过
- 新增测试覆盖 compact evidence artifact 中 raw output 可被接受

**验证**

live harness 定向测试通过。随后在已完成 DB 上重放 `collect_common_outcome()` 通过。

**架构与幂等性评估**

这是 harness 对 compact terminal payload 的假设错误，不是 production runtime 必须修改的错误。修补没有降低质量门禁，只是让门禁理解当前 artifact 存储格式。

幂等性良好。审计过程只读 evidence artifacts，不写业务事件，不改变 runtime 状态。

**是否建议回退**

不建议回退。建议保留，并在新会话确认 source delivery payload 的 canonical compact/full 两种格式是否应写入文档化 contract。

### P06. provider 反复输出未按 attempt 版本化的 verification evidence path

**场景**

M4 anonymous actions 等节点多次触发 `WORKSPACE_HOOK_VALIDATION_ERROR`，错误为 code delivery ticket 的 verification evidence path 必须按 attempt versioning。

**详细情况**

workspace hook 要求 verification evidence path 包含 attempt 版本，类似 `20-evidence/tests/<ticket_id>/attempt-<attempt_no>/<filename>`。provider 多次输出未包含 `/attempt-.../` 的路径，导致同类失败反复出现，自动恢复无法稳定收敛。

这里 hook 的要求是合理的：验证证据如果不按 attempt 隔离，会造成不同重试之间的证据覆盖和审计歧义。

**改动**

- 修改 `backend/app/core/runtime.py`
- 在 source delivery 提交前规范化 `verification_runs[*].path`
- 若路径已包含 attempt 版本，则保持不变
- 若路径未版本化，则改写为 `20-evidence/tests/<ticket_id>/attempt-<attempt_no>/<filename>`
- 不放宽 workspace hook
- 新增 `test_source_code_delivery_normalization_versions_verification_paths_by_attempt`

**验证**

- runtime fallback payload 测试通过，结果 `3 passed`
- workspace hook 定向测试通过，结果 `9 passed, 12 deselected`
- live harness 定向测试通过
- CEO scheduler 定向测试通过

**架构与幂等性评估**

这是 runtime-level normalization 缺口，属于真实架构健壮性问题。provider 输出是外部、不稳定输入；runtime 在进入 workspace hook 前做 canonicalization，符合边界防御设计。

幂等性良好。已版本化路径不重复改写；未版本化路径按 ticket id 与 attempt no 生成确定路径；同一 ticket / attempt 重复处理结果一致。

**是否建议回退**

不建议回退。这是本轮最应保留的 runtime 修补之一。新会话建议审计 normalization 是否覆盖所有 delivery payload 入口，而不只是当前 source delivery 分支。

### P07. workflow 完成后 final collection 缺少 chain report artifact

**场景**

最终 workflow `wf_6695c18ddb6f` 已达到 `COMPLETED / closeout`，无 active ticket、无 open incident，但 runner stderr 显示最终收集失败：`Workflow chain report artifact is missing.`。

**详细情况**

chain report 生成在当前系统中属于收尾 artifact 生成动作，已有 `ensure_workflow_atomic_chain_report()` 能补齐该 artifact。问题出在 live harness 的 `collect_common_outcome()` 直接断言 chain report 已存在，没有先执行与 auto-advance 收尾一致的 ensure 动作。

因此原 runner 自然退出失败，但失败点是测试收集层面的完成态 artifact 竞态，不是业务 workflow 未完成。

**改动**

- 修改 `backend/tests/live/_autopilot_live_harness.py`
- 在 `collect_common_outcome()` 检查 chain report 前显式调用 `ensure_workflow_atomic_chain_report()`
- 与已有 auto-advance 收尾逻辑保持一致

**验证**

- 用 `wf_6695c18ddb6f` 已完成 DB 重放 `collect_common_outcome()` 通过
- workflow chain report 定向测试通过，结果 `2 passed, 15 deselected, 1 warning`
- live harness 定向测试通过

**架构与幂等性评估**

这是 harness / lifecycle 边界问题。作为测试 harness 修补是稳健的，因为 ensure 操作本身应是幂等的：存在则复用，不存在则补齐。

但从架构角度看，完成态 workflow 是否应由 production completion path 保证 chain report 已物化，需要新会话审计。如果 chain report 是 completion contract 的一部分，最好把 ensure 前移到生产 closeout / auto-advance 生命周期，而不只是在测试收集时补。

**是否建议回退**

不建议回退 harness 修补。建议新会话评估是否还需要 production-side remediation。

### P08. provider bad response、invalid JSON 与 closeout artifact_refs 不合规

**场景**

最终 workflow 中仍存在 6 个 failed ticket。失败类型包括 provider bad response、JSON parse error、无效内容，以及 closeout package 曾把 `10-project/ARCHITECTURE.md` 这类非 delivery evidence artifact 放入 `payload.final_artifact_refs`。

**详细情况**

这些问题多发生在 provider 输出质量和 schema compliance 层。系统通过 retry、replacement、incident recovery 和后续 closeout 重新生成，最终业务 workflow 收敛完成。

本轮没有为这些 provider 输出质量问题做专门代码修补。它们被现有恢复机制或前述 runtime / harness 修补间接跨过。

**改动**

无直接代码改动。

**验证**

最终 workflow 完成，open incident 为 0；但 failed ticket 仍保留在历史中，说明这些不是“消失的问题”，只是被恢复路径覆盖。

**架构与幂等性评估**

这不是单一 runtime bug，但暴露了 prompt / schema / validator 压力。系统当前能恢复，但仍会消耗重试次数并污染失败历史。

幂等性取决于 provider 输出，不能视为已修复。

**是否建议回退**

无可回退修补。建议新会话单独审计 provider prompt、closeout schema validator 和 artifact_refs 白名单，避免靠重试碰运气。

### P09. 产物预览服务不支持页面所需 API

**场景**

用户要求把测试产物拉起网页查看。页面可以打开，但没有内置 30 本馆藏，也无法添加书籍和取走书籍，错误显示在页面底部。

**详细情况**

产物页面 `index.html` 依赖 `/api/books` 以及添加 / 借阅 / 归还等 mutation endpoints。最初使用的简单静态服务只能返回文件，对 POST / mutation API 返回 501 或等价错误。

这不是产物本身缺少业务能力，而是本地预览方式没有提供页面期望的 API。

**改动**

- 创建临时本地预览服务 `.tmp/library_preview_server.py`
- 该服务同时提供静态页面和 SQLite-backed preview API
- 初始化使用产物内的 `books_schema.sql` 与 `books_seed.sql`
- 验证 30 本馆藏可加载，添加书籍与取走书籍动作可执行
- 用户确认产物已经没有问题后，预览进程已关闭

**验证**

人工查看通过。预览进程已按用户要求关闭。

**架构与幂等性评估**

这是预览 harness 缺口，不是 production artifact 修补。`.tmp/library_preview_server.py` 是为了查看产物而创建的临时工具，不应被视为业务代码修复。

它对当前工作区是低风险的临时文件，但不属于最终产品架构。

**是否建议回退**

无需回退业务代码。建议新会话决定是否删除该 `.tmp` 临时预览脚本，或将“artifact preview server”正式产品化为测试工具。

## 本轮代码修补归类

### 建议保留

- `backend/app/core/workflow_controller.py`：follow-up plan 显式使用当前 workflow id
- `backend/app/core/ceo_proposer.py`：backlog 无动作时允许 closeout / NO_ACTION
- `backend/app/core/runtime.py`：source delivery verification path attempt 版本化 normalization
- `backend/tests/live/_autopilot_live_harness.py`：failure snapshot 审计容错、compact evidence 审计、chain report ensure
- 相关定向回归测试

### 建议保留但需新会话重点审计

- `backend/app/core/ceo_proposer.py`：当 latest existing ticket 失败时，回退使用同 node 已完成 ticket 满足依赖 gate
- `backend/tests/live/_autopilot_live_harness.py`：在测试收集阶段 ensure chain report；需判断 production completion path 是否也应保证该 contract

### 临时动作，不应视为架构修复

- 多次停止旧 live runner 并 clean 重启：原因是进程已加载旧代码，属于测试推进操作
- `.tmp/library_preview_server.py`：仅用于本地查看产物的临时预览服务

### 未修复，仅被恢复机制覆盖

- provider bad JSON / invalid content
- closeout `final_artifact_refs` 曾引用非 delivery evidence artifact
- provider schema compliance 不稳定

## 新会话审计重点

1. 审计 `ceo_proposer` 中 completed ticket 兜底逻辑是否需要 artifact freshness / superseded / lineage 约束，避免旧完成票据掩盖新失败。
2. 审计 chain report 是否属于 production completion contract；如果是，应把 ensure 前移到 workflow closeout 生命周期。
3. 审计 source delivery verification path normalization 是否覆盖所有 runtime delivery 入口。
4. 审计 compact source delivery payload 与 full source delivery payload 的正式 contract，并将 harness 审计规则与 contract 对齐。
5. 审计 provider prompt 与 closeout schema validator，减少 bad JSON、invalid content、artifact_refs 不合规依赖 retry 恢复的情况。
6. 决定 `.tmp/library_preview_server.py` 是删除、保留为临时工具，还是提升为正式 artifact preview harness。
