# intergration-test-004-20260419

这份记录只保留第四轮长测里最后确认下来的两个核心问题，以及本轮临时补丁的回滚说明。

这份文档的用途不是继续追探针细节。

它只做三件事：

- 记清楚这轮 live 长测最后停在哪
- 记清楚真正的问题是什么
- 记清楚本轮为排障加过哪些临时补丁，且这些补丁已经回滚

---

## 0. 当前结论

第四轮 live 长测最后稳定停在：

- workflow：`wf_5d6b8c3590ef`
- 主线完成到：`backlog_recommendation`
- 没有自动进入 implementation fanout

已经连续完成的治理链：

- `architecture_brief`
- `technology_decision`
- `milestone_plan`
- `detailed_design`
- `backlog_recommendation`

这说明：

- 治理文档主线本身可以连续收敛
- 当前真正卡住的不是 provider 基础可用性
- 当前真正卡住的是“治理文档怎么进入 implementation fanout”

---

## 1. 核心问题 A

### `CEO_SHADOW_PIPELINE_FAILED` 会被旧版 action payload 结构反复打爆

这轮长测里，`CEO shadow` 至少暴露过两类旧结构兼容问题：

- 旧版 `NO_ACTION.reason`
- 旧版 `HIRE_EMPLOYEE` payload

其中 `HIRE_EMPLOYEE` 还出现过多个变体：

- 只有 `role_profile_ref`
- 带 `justification`
- 带 `selection_guidance`
- 带 `reason`

现场表现：

- `source_stage=proposal`
- `error_class=ValidationError`
- 事件类型是：
  - `INCIDENT_OPENED`
  - `CIRCUIT_BREAKER_OPENED`
  - 之后又被 `ceo_delegate` 自动恢复

这说明：

- 当前 `CEOActionBatch` 的 schema 已经变严
- 但 live provider / 旧 fallback 仍可能返回旧 payload 结构
- CEO shadow 在 proposal 阶段没有完全兼容这些旧格式

这轮会话里我一度加过临时兼容补丁：

- `backend/app/core/ceo_proposer.py`
  - 兼容旧版 `NO_ACTION.reason`
  - 兼容旧版 `HIRE_EMPLOYEE.role_profile_ref / justification / selection_guidance / reason`
- `backend/tests/test_ceo_scheduler.py`
  - 增加了对应回归测试

这些补丁现在**已经全部回滚**。

原因很简单：

- 它们是为了当前长测止血的临时补丁
- 不该在没有重新设计 contract 的情况下直接留在主线

---

## 2. 核心问题 B

### `backlog_recommendation` 退化成自然语言治理文档，状态机无法消费

这是这轮最关键的问题。

现象：

- `backlog_recommendation` 文档已经产出
- 文档里也写了很多后续建议
- 但 controller 没有生成 `followup_ticket_plans`
- 结果是：
  - `controller_state=NO_IMMEDIATE_FOLLOWUP`
  - `recommended_action=NO_ACTION`
  - workflow 不会自动 fanout 到 implementation

根因判断：

- 当前 controller 只会消费结构化字段：
  - `sections[*].content_json.tickets`
  - `sections[*].content_json.dependency_graph`
  - `sections[*].content_json.recommended_sequence`
- 但这轮 live 产出的 `backlog_recommendation.json` 基本只是一份自然语言治理说明
- 它没有真正写出 machine-readable backlog split

所以现在的实际状态是：

- 人能看懂这份 backlog recommendation
- 状态机接不住这份 backlog recommendation

这会导致：

- CEO 即使被 scheduler 调起来
- 也只能基于 `controller_state=NO_IMMEDIATE_FOLLOWUP` 给出 `NO_ACTION`
- 而不是继续往下创建 implementation tickets

这不是“CEO 不会判断”。

这是：

- producer 没输出 machine-readable fanout plan
- controller 又不会自己把自然语言重新切成 machine-readable plan

---

## 3. 责任链判断

按当前 runtime 架构的意图：

- `backlog_recommendation` 本来就不该只是自然语言治理文档
- 它本来应该是“治理文档 + 机器可消费 backlog split”的二合一产物

也就是说：

- 这一步原本应该由接了 provider 的治理角色产出
- 不应该再由 Python 程序去理解自然语言并二次切分

当前漏掉的不是控制器逻辑。

当前漏掉的是：

- `backlog_recommendation` 的输出 contract 没有被强制成 machine-readable

---

## 4. CEO 当前能力边界

这轮也顺便确认了 CEO 当前的自主招聘边界。

当前 limited CEO staffing path 支持：

- `frontend_engineer`
- `backend_engineer`
- `database_engineer`
- `platform_sre`
- `checker`
- `governance_architect`
- `governance_cto`

这意味着：

- 编码人员可以招
- 测试/审查人员里的 `checker` 可以招

但这次没触发招聘，不是因为 CEO 没这个能力。

真正原因是：

- implementation fanout 没生成
- `followup_ticket_plans` 是空的
- 所以也不会进入 `STAFFING_REQUIRED`
- 自然不会走 `HIRE_EMPLOYEE`

---

## 5. 本轮回滚说明

本轮已经回滚的临时补丁：

- `backend/app/core/ceo_proposer.py`
  - 回滚 CEO shadow 对旧版 `NO_ACTION.reason` 的兼容修补
  - 回滚 CEO shadow 对旧版 `HIRE_EMPLOYEE` payload 的兼容修补
- `backend/tests/test_ceo_scheduler.py`
  - 回滚上述临时兼容补丁对应的回归测试

本轮**没有**回滚的内容：

- `library_management_autopilot_live` 的场景重写
- `test_live_library_management_runner.py` 对新场景口径的测试

原因：

- 这些属于第四轮长测本身的场景定义变更
- 不属于为了当前排障临时加的止血补丁

---

## 6. 留给新会话的处理方向

新会话里更值得直接解决的是这两件事：

1. 给 `backlog_recommendation` 单独加严格 schema

目标：

- 强制要求 machine-readable 的
  - `tickets`
  - `dependency_graph`
  - `recommended_sequence`

2. 明确 CEO shadow / provider 输出 contract 的兼容策略

目标：

- 要么彻底禁止旧 action payload 结构
- 要么集中、稳定地做兼容
- 不再在 live 长测里靠临时补丁止血

---

## 7. 最后状态

这轮第四次集成测试的最终结论可以收成一句话：

- 治理链已经能稳定推进到 `backlog_recommendation`
- 但 `backlog_recommendation` 还没有真正成为状态机可消费的 implementation handoff
- 同时 CEO shadow 对旧 action payload 结构仍存在真实兼容缺口
