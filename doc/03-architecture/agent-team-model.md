# Agent Team 模型

## 文档职责

本文件定义 CEO、角色、seat、skill、model effort、delegation、rework 和 closeout 的关系。

## 核心观点

Role 是职责模板，Seat 是本项目中被 CEO 激活的具体 agent 席位，Skill 是可组合能力包，ModelExecutionProfile 是 provider/model/effort 的执行配置。CEO / Architect / Worker / Tester / Checker / Closeout 都是 provider-backed agent role（模型支撑的智能体角色）：它们必须通过 ExecutionPackage（执行包）接收上下文，通过 LLM（大模型）返回影响工作流的产物或判断。工具、validator（校验器）、reducer（归约器）和 gate（门禁）可以不接入 LLM，但它们不是 agent role。

RolePromptHook（角色提示词钩子）是受治理的基础提示词资产，定义 CEO / Architect / Worker / Tester / Checker / Closeout 的行为边界，但不替代程序化 contract / reducer / evidence / closeout gate（合同 / 归约器 / 证据 / 收尾门禁）。

```text
RolePromptHook + RoleProfile + SkillBinding + ModelExecutionProfile -> AgentSeat
AgentSeat + TicketNode + ExecutionPackage(role_prompt_hook snapshot) -> ProviderAttempt(role_prompt_hook audit fields)
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
role_prompt_hook_ref:
role_prompt_hook_version:
role_prompt_hook_sha256:
responsibilities:
capability_tags:
input_contracts:
output_contracts:
forbidden_actions:
```

RoleProfile 必须引用 active RolePromptHook（角色提示词钩子）。RoleProfileRegistry（角色模板注册表）负责校验 hook ref（钩子引用）存在、hook version（钩子版本）一致、content sha256（内容哈希）一致，以及 hook role category（角色类别）与 RoleProfile.role_category 匹配。缺字段、未知 hook、版本/hash/category mismatch（不匹配）均 fail closed。

## RolePromptHook

RolePromptHook 是 governed asset（治理资产），由 baseline registry builder（基准注册表构建器）读取源码配置路径中的 prompt template（提示词模板）并计算真实 sha256。active hook 必须非空、ref 唯一、hash 与内容一致、policy refs（策略引用）非空，并声明对应角色的 required responsibilities（必备职责）。

```yaml
hook_ref:
role_kind:
role_category:
hook_version:
template_path:
content_sha256:
prompt_text:
policy_refs:
required_responsibilities:
```

RolePromptHook 进入 ExecutionPackage（执行包）时是不可变 snapshot（快照），进入 ProviderAttempt（模型调用尝试记录）时是审计字段：`role_prompt_hook_ref`、`role_prompt_hook_version`、`role_prompt_hook_sha256`。ProviderExecutor（模型执行器）渲染 provider prompt（模型提示词）时必须包含 hook 内容和 ExecutionPackage facts（执行包事实），并校验 provider transport（模型传输）返回的 ProviderAttempt 绑定同一个 hook。

RolePromptHook 只能约束 agent behavior（智能体行为）和提示词边界；它不能声明 bypass / replace / supersede（绕过 / 替代 / 取代）AcceptanceContract（验收合同）、PackageContract（包合同）、reducer（归约器）、EvidenceVerifier（证据验证器）或 CloseoutGate（收尾门禁）。如果 hook 内容声称可绕过这些门禁，registry 必须拒绝。EvidenceVerifier（证据验证器）消费 provider-backed evidence（模型支撑证据）时必须通过 RolePromptHookRegistry（角色提示词钩子注册表）验真 ProviderAttempt（模型调用尝试记录）的 hook ref/version/hash，并按 `ProviderAttempt.input_package_ref`（模型调用输入包引用）解析对应 ExecutionPackage（执行包）；attempt（调用记录）的 hook 审计字段必须与该 ExecutionPackage 的 RolePromptHook snapshot 完全一致。EvidenceVerifier 不得按 RoleCategory（角色类别）推断证据权限；Tester（测试者）、Checker（检查者）等非 implementation category（非实施类别）角色只要绑定自身执行包快照，也必须能接收并留痕其预设提示词。

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
