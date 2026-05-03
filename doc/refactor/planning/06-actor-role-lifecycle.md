# Actor / Role 生命周期

## 目标

当前项目中“员工”“角色模板”“执行能力”“模型绑定”“租约”“排除列表”容易混在一起。重构后，runtime kernel 只认识 actor、capability、assignment 和 lease；CEO、architect、checker、frontend engineer 等只是治理模板或产品语义。

## 概念分层

```text
Actor / Employee
  -> RoleTemplate
  -> CapabilitySet
  -> Assignment
  -> Lease
  -> ExecutionAttempt
```

## 核心对象

### Actor

运行时可被派工的实体。

字段：

- `actor_id`
- `status`
- `capability_set`
- `provider_binding_refs`
- `availability`
- `created_from_policy`
- `deactivated_reason`

### Employee

产品层对 actor 的公司化表示。Employee 可以映射到 actor，但 runtime 不以 employee title 做判断。

### RoleTemplate

组织模板，表达默认职责、默认 capability、默认 provider 偏好、协作边界。

### Capability

runtime 可理解的能力原语，例如：

- `source.modify.backend`
- `source.modify.frontend`
- `evidence.check.delivery`
- `closeout.write`
- `policy.propose.graph_patch`

### Assignment

某 actor 被选为某 ticket 的候选执行者。

### Lease

某 actor 在有限时间内领取某 ticket 的执行权。

## 状态机

```text
CANDIDATE
  -> ACTIVE
  -> SUSPENDED
  -> DEACTIVATED
  -> REPLACED
```

| 状态 | 含义 |
|---|---|
| `CANDIDATE` | 已注册但未启用 |
| `ACTIVE` | 可派工 |
| `SUSPENDED` | 暂停派工，可恢复 |
| `DEACTIVATED` | 不再派工 |
| `REPLACED` | 被新 actor 替代，保留 lineage |

## Lease 状态机

```text
AVAILABLE -> ASSIGNED -> LEASED -> EXECUTING -> RELEASED
                                      -> TIMED_OUT
                                      -> FAILED
```

规则：

- `ASSIGNED` 不等于 `LEASED`。
- `LEASED` 不等于 `EXECUTING`。
- lease 必须有 timeout。
- provider attempt late completion 不能自动恢复过期 lease。
- replacement ticket 必须有新 idempotency key。

## RoleTemplate 示例

```yaml
role_templates:
  backend_engineer_primary:
    default_capabilities:
      - source.modify.backend
      - test.run.backend
      - evidence.write.test
      - evidence.write.git
      - docs.update.delivery
    provider_preferences:
      purpose: implementation

  checker_primary:
    default_capabilities:
      - evidence.check.delivery
      - verdict.write.maker_checker
    provider_preferences:
      purpose: review
```

## 派工规则

派工必须基于：

1. ticket required capabilities；
2. actor active status；
3. provider health；
4. current leases；
5. exclusion policy；
6. failure heat；
7. graph locality。

派工不得只基于：

- role name；
- ticket summary 文本；
- hardcoded employee id；
- 上一次谁做过类似 ticket。

## Exclusion Policy

`excluded_employee_ids` 必须有作用域：

| Scope | 含义 |
|---|---|
| `attempt` | 只排除当前 attempt |
| `ticket` | 排除当前 ticket 的后续 retry |
| `node` | 排除当前 graph node |
| `capability` | 暂停某 actor 对某 capability 的派工 |
| `workflow` | 整个 workflow 排除，必须有 incident 支撑 |

禁止无作用域地复制旧 ticket 的 excluded list。015 中 checker 票排除所有可用 checker 的问题，必须由该策略阻断。

## 员工池为空

当 required capability 无可用 actor 时，policy engine 只能输出：

- `CREATE_ACTOR`；
- `REASSIGN_EXECUTOR`；
- `REQUEST_HUMAN_DECISION`；
- `BLOCK_NODE_NO_CAPABLE_ACTOR`。

不能：

- silent stall；
- 让不具备 capability 的 actor 执行；
- 靠 role name fallback；
- 自动取消业务节点。

## 启用与注销

启用 actor 必须记录：

- source policy；
- capabilities；
- provider bindings；
- effective graph version；
- audit reason。

注销 actor 必须记录：

- deactivation reason；
- active leases；
- affected nodes；
- replacement plan；
- audit event。

## Provider 绑定

Actor 可以有 provider preference，但 provider 实际选择必须记录：

- preferred provider/model；
- actual provider/model；
- fallback reason；
- provider health snapshot；
- cost/latency class。

Provider binding 不应写死在 role template 中作为不可变事实。

## Round 7A 实现状态

Round 7A 已按强迁移建立独立 Actor registry，`actor_projection` 只由 `ACTOR_ENABLED`、`ACTOR_SUSPENDED`、`ACTOR_DEACTIVATED`、`ACTOR_REPLACED` 事件重放生成；`EMPLOYEE_*` 事件不会桥接或回填 runtime actor。

已落地的数据结构：

- `backend/app/core/constants.py` 定义 actor lifecycle 事件与 `CANDIDATE` / `ACTIVE` / `SUSPENDED` / `DEACTIVATED` / `REPLACED` 状态常量。
- `backend/app/core/reducer.py` 提供 `rebuild_actor_projections(events)`，覆盖 enable、suspend、deactivate、replace，并保留 replacement lineage。
- `backend/app/db/schema.py` 新增持久化 `actor_projection` 表。
- `backend/app/db/repository.py` 初始化和 `refresh_projections()` 会重放 actor projection，并提供 `replace_actor_projections()`、`list_actor_projections()`、`get_actor_projection()`。
- `backend/app/core/execution_targets.py` 新增 `build_role_template_capability_contract()`；RoleTemplate 只输出 `capability_set` 与 `provider_preferences`，不输出 `execution_target_ref` 或 runtime execution key。

7A 明确边界：

- `employee_projection` 仍保留为产品/公司化表示和历史输入来源，但不再作为后续 runtime eligibility 的目标路径。
- 旧 `role_profile_ref -> execution_target_ref`、scheduler eligibility、assignment、lease、provider selection 调用点本批不全链路迁移；7B–7E 必须继续删除这些 runtime 决策路径，而不是把 role template 包装成新的执行键。
- 7B 的入口应直接消费 `actor_projection`、ticket required capabilities 和 scoped exclusion，不能从 `EMPLOYEE_*` lifecycle 恢复 runtime actor。

测试证据：

- `backend/tests/test_reducer.py::test_reducer_rebuilds_actor_projection_from_independent_actor_events`
- `backend/tests/test_api.py::test_repository_persists_actor_projection_from_independent_actor_events`
- `backend/tests/test_execution_targets.py::test_role_template_capability_contract_does_not_emit_runtime_execution_key`

## Round 7B 实现状态

Round 7B 已把 scheduler runtime eligibility 迁移到 actor capability assignment resolver。Scheduler 现在消费 `actor_projection`、ticket required capabilities、actor status、provider pause state、active leases 和 scoped exclusions；`employee_projection` 与 `role_profile_ref` 不再作为派工兜底路径。

已落地的运行时边界：

- `backend/app/core/assignment_resolver.py` 负责基于 capability 的 actor eligibility、候选诊断和 no-eligible payload。
- `backend/app/core/execution_targets.py` 只把 legacy ticket / RoleTemplate 输入编译成 `required_capabilities`，RoleTemplate 仍不是 runtime execution key。
- `backend/app/core/ticket_handlers.py` 的 scheduler tick 从 `actor_projection` 读取候选 actor；7C 已把 resolver 选出的 actor 写入独立 `TICKET_ASSIGNED` / `TICKET_LEASE_GRANTED` identity。
- legacy `excluded_employee_ids` 只被适配为 scoped exclusion，支持 `attempt`、`ticket`、`node`、`capability`、`workflow`，retry/rework 不再复制无作用域旧列表。
- required capability 无可用 actor 时继续写 `EVENT_SCHEDULER_LEASE_DIAGNOSTIC_RECORDED`，payload 使用 `reason_code = "NO_ELIGIBLE_ACTOR"`，并包含 `required_capabilities`、`candidate_summary`、`candidate_details` 和建议动作 `CREATE_ACTOR` / `REASSIGN_EXECUTOR` / `REQUEST_HUMAN_DECISION` / `BLOCK_NODE_NO_CAPABLE_ACTOR`。

测试证据：

- `backend/tests/test_assignment_resolver.py`
- `backend/tests/test_scheduler_runner.py::test_scheduler_does_not_lease_without_enabled_actor_registry_entry`
- `backend/tests/test_scheduler_runner.py::test_scheduler_leases_actor_by_required_capabilities_not_employee_role`
- `backend/tests/test_scheduler_runner.py::test_scheduler_blocks_rework_fix_when_only_capable_actor_is_scoped_excluded`
- `backend/tests/test_api.py` 中 retry/rework scoped exclusion 回归用例

## Round 7C 实现状态

Round 7C 已把 Assignment 与 Lease 拆成一等 runtime identity。Assignment 表示 actor 被选中，Lease 表示有限时间执行窗口；`lease_owner` 只作为历史展示 / 迁移 alias，不再驱动 scheduler、runtime start 或 context compiler 的执行身份。

已落地的运行时边界：

- `EVENT_TICKET_ASSIGNED` 写入 `assignment_id`、`actor_id`、`required_capabilities` 和 assignment reason；`assignment_projection` 独立重放，不会因 lease timeout 被撤销。
- `EVENT_TICKET_LEASE_GRANTED` 写入 `lease_id`、`assignment_id`、`actor_id`、lease timeout 和 expiry；`lease_projection` 在 start / complete / fail / timeout / cancel 上更新状态。
- `ticket_projection` denormalize 当前 `actor_id`、`assignment_id`、`lease_id`；`lease_owner` 对新路径保持空。
- ticket lease / start / timeout payload 都携带 `actor_id`、`assignment_id`、`lease_id`。
- scheduler active lease 检查使用 `actor_id`，replace 后旧 actor `REPLACED` 不再 eligible，新 actor 必须获得新的 assignment 和 lease，不继承旧 lease。
- context compiler 和 compiled execution package meta 使用 actor / assignment / lease identity；RoleTemplate 仍只提供 capability/persona 输入，不作为 runtime execution identity。

测试证据：

- `backend/tests/test_reducer.py::test_reducer_keeps_assignment_history_separate_from_lease_timeout`
- `backend/tests/test_api.py::test_repository_persists_assignment_and_lease_projections`
- `backend/tests/test_scheduler_runner.py::test_scheduler_runner_once_external_mode_leaves_ticket_leased`
- `backend/tests/test_scheduler_runner.py::test_scheduler_replacement_actor_gets_new_assignment_without_old_lease`
- `backend/tests/test_api.py::test_ticket_lease_moves_ticket_to_leased_and_keeps_node_pending`
- `backend/tests/test_api.py::test_ticket_start_moves_ticket_and_node_to_executing`
- `backend/tests/test_api.py::test_scheduler_tick_times_out_executing_ticket_and_creates_retry`
- `backend/tests/test_context_compiler.py::test_build_compile_request_translates_runtime_inputs`
- `backend/tests/test_context_compiler.py::test_compile_execution_package_builds_minimal_worker_input`

## Round 7D 实现状态

Round 7D 已把 provider preferred/actual provenance 贯穿 assignment、execution attempt/provider audit 和 runtime result evidence。Provider selection 不再把旧 `role_bindings` / binding chain 当作 runtime execution key；role template 只能继续作为默认 capability/provider preference 的迁移来源。

已落地的运行时边界：

- `EVENT_TICKET_ASSIGNED` payload 记录 `preferred_provider_id`、`preferred_model`、`actual_provider_id`、`actual_model`、`selection_reason`、`policy_reason`、`provider_health_snapshot`、`cost_class` 和 `latency_class`；manual lease 使用 `policy_reason=manual_lease`，scheduler assignment 使用 `policy_reason=capability_match`。
- `assignment_projection` 持久化 `provider_selection`，replay 后可恢复同一套 provider provenance 字段。
- provider audit event payload 记录 preferred/actual provider/model、selection/policy/fallback reason、provider health snapshot、cost/latency class；字段命名与 provider-only smoke 报告一致。
- provider failover 只消费 provider config 的 `fallback_provider_ids`，并把 final execution 记录为 fallback provider 的 `actual_provider_id` / `actual_model`，不把 fallback 成功伪装成 primary provider 成功。
- runtime result assumptions 和 provider attempt log 保留同名 provenance 字段，便于 result evidence 与 provider audit 对齐。

测试证据：

- `backend/tests/test_runtime_provider_center.py`
- `backend/tests/test_scheduler_runner.py::test_scheduler_assignment_records_provider_provenance_from_actor_preference`
- `backend/tests/test_scheduler_runner.py::test_runtime_provider_rate_limit_failover_uses_fallback_provider_before_deterministic`

仍留给 Round 7E：

- 全仓库收口 remaining role/template/provider config legacy surface，确认 `role_profile_ref` 仅作为治理模板、产品展示、legacy input -> capability/preference 编译来源保留。
- 对 `runtime_provider_config.py` 中仍为历史配置 shape 保留的 `role_bindings` / provider model entry API 做最终边界标注或删除测试依赖。
- 用 grep + targeted tests 为 Phase 3 全部 checkbox 建立最终证据。
