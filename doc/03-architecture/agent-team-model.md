# Agent Team 模型

## 文档职责

本文件定义 CEO、角色、seat、skill、model effort、delegation、rework 和 closeout 的关系。

## 核心观点

Role 是职责模板，Seat 是本项目中被 CEO 激活的具体 agent 席位，Skill 是可组合能力包，ModelExecutionProfile 是 provider/model/effort 的执行配置。

```text
RoleProfile + SkillBinding + ModelExecutionProfile -> AgentSeat
AgentSeat + TicketNode + ExecutionPackage -> Attempt
```

## CEO

CEO 是项目治理核心，不是代码生成 worker。

CEO 负责：

- 解释用户目标；
- 选择 methodology；
- 创建或调整 ticket graph；
- 启用或派生 agent seat；
- 发起 clarification；
- 发起 rework；
- 判断是否请求 closeout；
- 记录关键治理决策。

CEO 禁止：

- 绕过 contract 直接完成项目；
- 接受缺 evidence 的 implementation；
- 用 workflow completed 替代 closeout；
- 把 runtime fallback 当作 worker 产出。

## Architect

Architect 负责把项目目标转成可施工合同。

Architect 必须产出：

- architecture decision；
- package layout；
- source surfaces；
- integration boundary；
- run/test commands；
- evidence obligations；
- implementation decomposition；
- risk constraints。

如果 architect 输出只是散文，不能进入 BUILD。

## Worker

Worker 负责在 execution package 边界内实施。

Worker 必须接收：

- objective；
- context refs；
- constraints；
- allowed write set；
- required outputs；
- acceptance refs；
- evidence obligations；
- command requirements。

Worker 禁止：

- 写入未授权路径；
- 省略 command evidence；
- 用 placeholder source 伪装实现；
- 修改 acceptance contract。

## Checker

Checker 是独立验证角色。

Checker 输入：

- work product；
- source diff；
- verification runs；
- evidence claims；
- acceptance contract；
- package contract；
- source inventory draft。

Checker 输出：

```text
APPROVED
APPROVED_WITH_NON_BLOCKING_NOTES
REWORK_REQUIRED
ESCALATE
```

任何 blocking evidence gap 都必须导致 `REWORK_REQUIRED`。

## Reviewer / Human Board

Human board 可以：

- 澄清需求；
- 修改约束；
- 批准 scope change；
- 审核 process audit；
- 触发 forensic lookup。

所有 human interaction 必须进入 event log 和 process audit。

## Runtime

Runtime 不是 agent team 的治理者。它是执行和记录层。

职责见 `execution-and-runtime-boundary.md`。

## RoleProfile

角色模板。

```yaml
role_profile_id:
role_name:
responsibilities:
capability_tags:
input_contracts:
output_contracts:
forbidden_actions:
```

## AgentSeat

项目中被启用的具体席位。

```yaml
seat_id:
role_profile_ref:
project_ref:
model_execution_profile_ref:
skill_refs:
context_budget:
status:
```

## SkillBinding

Skill 不绑定特定 role，由 CEO 或 policy 根据任务选择。

```yaml
skill_ref:
purpose:
required_for_ticket_types:
allowed_roles:
input_requirements:
output_effects:
```

## ModelExecutionProfile

```yaml
profile_id:
provider:
model:
reasoning_effort:
context_window:
temperature:
tool_permissions:
fallback_policy_ref:
```

## Delegation Loop

```text
CEO observes graph
-> proposes governance action
-> reducer validates action
-> ticket becomes ready
-> seat receives execution package
-> provider attempt recorded
-> work product submitted
-> evidence verified
-> checker verdict recorded
-> reducer completes or creates rework ticket
```

