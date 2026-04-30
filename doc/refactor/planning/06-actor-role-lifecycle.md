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

## 验收标准

- runtime 不再以 `role_profile_ref` 作为唯一派工依据。
- `excluded_employee_ids` 有明确作用域，不能继承污染后续票。
- 员工池为空时产生显式 action/incident。
- late lease/provider event 不污染 current graph pointer。
- actor lifecycle 全部可从事件重放。
