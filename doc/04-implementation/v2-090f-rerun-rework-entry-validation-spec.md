# V2-090F Rerun Rework Entry Validation Spec

## 状态

- Stage（阶段）：Phase 9 / V2-090F
- State（状态）：spec written / awaiting implementation plan（规格已写入 / 等待实施计划）
- 日期：2026-06-16
- 输入：原始 short PRD（简短产品需求）、V2-090F 专用配置基线、V2-090K fail-closed failure snapshot（失败关闭现场）、V2-100A~E rework loop（返工循环）能力
- 输出：一次真实 V2-090F rerun（重跑）的复判证据；若阻断，则必须形成 verified blocker（已验证阻塞项）和 ReworkRequest（返工请求），并展示 TicketGraph（工单图）更新前后差异

## 结论

V2-100E 完成后，下一步不是先补一大批 orchestration glue（编排胶水），也不是直接把 V2-090F 标记为可通过。正确顺序是先把 V2-090F 作为 rework-entry validation（返工入口验证）重跑：

```text
short PRD
  -> V2-090F real agent-team run
  -> CloseoutGate / Checker / EvidenceVerifier
  -> no blocker: 按原样 closeout candidate
  -> verified blocker: 进入 V2-100 ReworkCycle
  -> ReworkPlan + TicketGraphPatch
  -> rework attempt + evidence/checker/closeout recheck
  -> accepted / escalated / exhausted
```

该验证的首要问题不是“090F 能不能一次通过”，而是：

1. 不阻断时，是否能按现有 closeout path（收尾路径）正常候选通过；
2. 阻断时，是否能从现有 evidence/checker/closeout 输出自然形成 ReworkRequest；
3. 进入返工后，TicketGraph 是否真的发生治理图补丁更新，并可由 before/after graph（更新前后图）证明。

## 背景

V2-090F（Golden sample rebuild，黄金样例重建）仍保持 `REVIEW_REQUIRED / BLOCKED`，原因不是 worker implementation（实施者实现）不可运行，而是旧运行中存在 runner/prompt/validator/helper（运行器/提示词/校验器/辅助器）外部介入、静态验收引用、固定业务探针和 helper-written checker/closeout verdict（辅助器写检查/收尾结论）。

V2-090K 已移除这些外部介入，并保留了可审计的 fail-closed 现场：行为探针 response shape（响应形状）错配、env binding（环境绑定）未收敛、FinalEvidenceTable（最终证据表）旧验收引用、closeout/audit（收尾/审计）旧 run 引用。

V2-100A~E 已实现并证明：

- verified blocker 可以投影为 ReworkRequest；
- CEO（项目经理/治理角色）能生成 ReworkPlan（返工计划）和 TicketGraphPatch（工单图补丁）；
- graph patch 需要多角色 review（审查）并经 reducer（归约器）提交；
- 每次 ReworkAttempt（返工尝试）必须重新进入 SourceInventory / FinalEvidenceTable / Checker / CloseoutGate（源码清单 / 最终证据表 / 检查者 / 收尾门禁）；
- 多轮返工可 accepted（接受）或显式 escalated/exhausted（升级/耗尽）。

因此，V2-090F 的下一步应验证“真实 090F run 能否自然接入这些能力”，而不是先假设必须重写编排框架。

## 非目标

本 spec 不要求：

- 先实现新的 full orchestration framework（完整编排框架）；
- 在没有真实阻断证据前新增并行 runner、并行 TicketGraph builder（工单图构建器）或并行 closeout helper；
- 把 V2-100E 的 resettable fixture（可重置夹具）伪装成 V2-090F golden sample；
- 用 fake provider（模拟模型供应商）、provider artifact lock（模型产物锁）或 deterministic replay（确定性重放）证明 happy path；
- 因一次 CRUD 可用、一次 command success（命令成功）或 `AgentRunResult.status == completed`（智能体运行完成）直接判定 V2-090F DONE。

## 范围

本 spec 覆盖一次受控重跑和复判流程：

1. 使用原始 short PRD 作为唯一业务输入。
2. 使用 V2-090F 专用 runtime/providers/roles config（运行时 / 供应商 / 角色配置）。
3. 运行现有 V2-090F PRD-to-delivery agent team entrypoint（从 PRD 到交付的智能体团队入口）。
4. 对 runner 输出执行 existing gates（现有门禁）：EvidenceVerifier、FinalEvidenceTableBuilder、Checker、CloseoutGate、Replay/Process/Git audit。
5. 若阻断，要求阻断先被投影成 typed BlockerReport（类型化阻塞报告）和 ReworkRequest。
6. 使用现有 V2-100 rework loop API（返工循环接口）处理 ReworkRequest，不预先改写 V2-090F 任务图。
7. 导出 TicketGraph before/after（更新前/后）示意图和 JSON snapshot（JSON 快照）。
8. 根据结果给出 V2-090F 复判建议：candidate passed、needs minimal rework-entry glue、needs human review、或仍 blocked。

## 输入约束

### PRD

业务输入必须仍是单份用户 PRD 或其仓库内 short PRD 文件，例如：

```text
examples/directives/tiny-fullstack-prd.md
```

不得向 runner 额外注入固定 ticket refs（工单引用）、固定源码布局、固定 HTTP path（HTTP 路径）、固定 env names（环境变量名）或预制 ReworkPlan。

### Config Baseline

必须使用 V2-090F 专用配置：

```text
config/boardroom-runtime.v2-090f.yaml
config/boardroom-providers.v2-090f.yaml
config/boardroom-roles.v2-090f.yaml
```

`.env` 只允许提供 config paths（配置路径）、secret（密钥）和本地 bootstrap path（启动路径）。model（模型）、timeout（超时）、reasoning effort（推理强度）、budget（预算）和 retry policy（重试策略）必须来自 YAML 并进入 baseline hash（基线哈希）。

### Provider

真实复判必须显式 opt-in：

```bash
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. \
python scripts/run_v2_090f_prd_agent_team.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --reset \
  --stage full
```

缺真实 provider secret（供应商密钥）时必须 fail closed，不得转入 fake success（模拟成功）。

## 输出要求

重跑输出必须保留在 generated workspace（生成工作区）或受控 evidence root（证据根）下，至少包含：

- `00-boardroom/v2-090f-baseline.json`：PRD sha256、config hashes、角色上下文、预算和 provider profile refs（供应商配置引用）。
- `00-boardroom/agent-team-role-context.json`：每个 required seat（必需席位）的 RolePromptHook（角色提示词钩子）ref/version/sha256 和 skill refs（技能引用）。
- `00-boardroom/ticket-graph.before-rework.json`：返工判定前工单图。
- `00-boardroom/ticket-graph.before-rework.md`：返工判定前 Mermaid graph（Mermaid 图）。
- `00-boardroom/ticket-graph.after-rework.json`：若进入返工，则记录 graph patch 提交后的工单图。
- `00-boardroom/ticket-graph.after-rework.md`：若进入返工，则记录更新后的 Mermaid graph。
- `20-evidence/rework-entry/blocker-report.json`：阻断投影结果；无阻断时记录空 blocker summary。
- `20-evidence/rework-entry/rework-request.json`：进入返工时的 ReworkRequest。
- `20-evidence/rework-entry/rework-plan.json`：进入返工时的 CEO ReworkPlan。
- `20-evidence/rework-entry/ticket-graph-patch.json`：进入返工时的 TicketGraphPatch。
- `20-evidence/rework-entry/rework-terminal.json`：accepted / escalated / exhausted / blocked_by_missing_entry 的终态。
- `30-audit/rework-entry-validation.md`：人类可读复判报告。

如果没有 verified blocker，`after-rework` graph 可以不存在，但报告必须说明 closeout 是在无阻断条件下产生的 candidate result（候选结果），不是跳过返工。

## Ticket Graph 示意图要求

为满足人工判断“确实对图进行了更新”的要求，进入返工时必须输出 before/after 两份 Mermaid graph。节点标签至少包含：

- ticket id（工单 ID）；
- owner seat（负责席位）；
- status（状态）；
- acceptance refs count（验收引用数量）；
- evidence obligations count（证据义务数量）。

返工新增或修改的节点必须可见，例如：

```mermaid
graph TD
  "ticket.architect.plan\nseat.architect.delivery\ncompleted" --> "ticket.worker.implementation\nseat.worker.implementation\nblocked"
  "ticket.worker.implementation\nblocked" --> "ticket.checker.acceptance\nblocked"
```

```mermaid
graph TD
  "ticket.architect.plan\nseat.architect.delivery\ncompleted" --> "ticket.worker.implementation\nseat.worker.implementation\nblocked"
  "ticket.worker.implementation\nblocked" --> "ticket.rework.response-shape\nseat.worker.implementation\nready"
  "ticket.rework.response-shape\nready" --> "ticket.checker.acceptance\nwaiting_recheck"
```

JSON graph snapshot 必须包含 graph_version（图版本）。after graph 的 graph_version 必须大于 before graph，且必须能追踪到同一 TicketGraphPatch。

## 结果判定

### `passed_without_rework_candidate`

条件：

- CloseoutGate passed；
- FinalEvidenceTable 覆盖 active AcceptanceContract 的所有 blocking criteria；
- 每个 declared run/test command 均有 final evidence；
- SourceInventory 绑定 provider attempt、source lineage 和 active PackageContract.source_surfaces；
- Checker/Closeout 均有 provider-backed attempt；
- 没有 verified blocker。

该结果只能进入 V2-090F DONE 候选，仍需专家评审；不能由脚本自动改 backlog checkbox。

### `rework_accepted_candidate`

条件：

- 首轮产生 verified blocker；
- blocker 投影为 ReworkRequest；
- CEO 产生 ReworkPlan 和 TicketGraphPatch；
- graph patch 经必需 review domains（审查域）批准；
- reducer 提交后 graph_version 增加；
- ReworkAttempt 重新进入证据、检查和收尾门禁；
- CloseoutGate passed；
- before/after graph 和 rework audit 可审计。

该结果是 V2-090F 最合理的解阻候选，因为它证明了 `V2-090K + V2-100` 后黄金样例可从阻断进入治理返工并收敛。

### `rework_escalated_or_exhausted`

条件：

- verified blocker 已形成；
- ReworkRequest / ReworkPlan / TicketGraphPatch 链路成立；
- 返工仍无法通过；
- 产生 explicit ReworkTerminationDecision（显式返工终止决策）。

该结果不通过 V2-090F，但证明返工框架没有残缺到静默失败。后续应由人工评审 termination reason（终止原因）决定是否改 PRD、预算、provider capability（模型能力）或框架能力。

### `blocked_by_missing_rework_entry`

条件：

- 090F runner 或 closeout 输出只留下 raw exception（原始异常）、free text（自由文本）或未结构化错误；
- EvidenceVerifier / Checker / CloseoutGate 没有把失败投影为 verified blocker；
- 因缺 BlockerReport / ReworkRequest 无法进入 V2-100。

该结果说明原有框架能力仍有 rework-entry gap（返工入口缺口）。后续只允许补最小入口适配：把现有 gate failure（门禁失败）结构化为 BlockerReport / ReworkRequest；不得写第二套 evidence/checker/closeout 实现。

## Fail-Closed Matrix

| 场景 | 结果 |
|---|---|
| 未设置 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` | fail closed |
| 缺 V2-090F 专用配置或 baseline hash 漂移 | fail closed |
| runner 注入固定 ticket graph 或固定 ReworkPlan | fail closed |
| ProviderAttempt 为 0 的 implementation ticket 被完成 | fail closed |
| `AgentRunResult.status == completed` 被直接映射为 `TICKET_COMPLETED` | fail closed |
| command success 但 FinalEvidenceTable 证明命题错误 | closeout blocked |
| Checker notes 覆盖 blocker | fail closed |
| Closeout helper 写 passed verdict 替代 CloseoutGate | fail closed |
| 阻断无法投影为 BlockerReport / ReworkRequest | `blocked_by_missing_rework_entry` |
| 返工后复用旧 FinalEvidenceTable / CheckerVerdict / CloseoutPackage | fail closed |
| 返工耗尽预算但无 ReworkTerminationDecision | fail closed |
| after graph 没有 graph_version 增加或缺 TicketGraphPatch ref | rework audit blocked |

## 实施入口建议

后续实施计划应按最小增量分三段：

1. **Observation run（观察重跑）**：不改编排，只重跑 V2-090F full stage，收集 closeout/gate 失败形态和 ticket graph before snapshot。
2. **Entry projection（入口投影）**：若失败已经结构化，直接复用现有 blocker projection；若失败缺结构化入口，仅补从现有 gate failure 到 BlockerReport / ReworkRequest 的 adapter（适配器）。
3. **Rework continuation（返工继续）**：调用 V2-100 rework loop，提交 TicketGraphPatch，执行返工重验，并导出 before/after graph。

不得在第 1 段之前预先实现大规模编排重构。只有真实重跑证明缺入口时，才允许第 2 段补最小 adapter。

## 验收

本 spec 对应的实施完成后，至少需要以下验证：

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_prd_agent_team_script.py \
  tests/proving/test_v2_100_rework_loop.py \
  tests/negative/test_v2_100_rework_loop_fail_closed.py \
  -q
```

真实 provider opt-in 验证必须单独执行并记录耗时、run id（运行编号）和 audit export path（审计导出路径）：

```bash
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. \
python scripts/run_v2_090f_prd_agent_team.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --reset \
  --stage full
```

如果进入返工，还必须运行或等价调用 V2-100 rework loop，并验证：

- `ticket-graph.before-rework.json` 与 `ticket-graph.after-rework.json` 均存在；
- after graph_version 大于 before graph_version；
- after graph 包含由 TicketGraphPatch 引入或修改的 rework ticket；
- ReworkAttempt 的 evidence namespace（证据命名空间）不同于首轮；
- CloseoutGate passed 或 ReworkTerminationDecision 存在。

## 自审

- Placeholder scan（占位扫描）：本 spec 不含占位标记或未定义成功条件。
- Scope check（范围检查）：本 spec 只定义 V2-090F 重跑与返工入口验证，不要求重写编排框架或实现新 evidence/checker/closeout 平行链路。
- Contract first（合同优先）：业务输入仍是 PRD；implementation / rework 均必须绑定 active AcceptanceContract 和 PackageContract。
- Reducer first（归约器优先）：TicketGraphPatch 只能经 reducer / validator 提交，graph_version 变化必须可审计。
- Evidence first（证据优先）：CloseoutGate passed 只消费真实 evidence；命令通过、模型完成或一次探针不能单独通过。
- Fail closed（失败关闭）：缺 provider、缺 baseline、缺 blocker 投影、缺 graph before/after 或缺 termination decision 均有明确失败结果。
- Runtime bounded（运行时有界）：runtime / atomic-agent 只记录执行事实，不创建 ReworkPlan、不接受返工、不写 closeout passed verdict。
- No second source of truth（无第二权威源）：若需要 adapter，只允许把现有 gate failure 结构化为 BlockerReport / ReworkRequest，不允许复制 FinalEvidenceTableBuilder、SourceInventory 或 CloseoutGate 规则。
