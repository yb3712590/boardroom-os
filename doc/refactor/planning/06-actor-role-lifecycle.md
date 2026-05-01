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


- `excluded_employee_ids` 有明确作用域，不能继承污染后续票。
- 员工池为空时产生显式 action/incident。
- late lease/provider event 不污染 current graph pointer。
- actor lifecycle 全部可从事件重放。
