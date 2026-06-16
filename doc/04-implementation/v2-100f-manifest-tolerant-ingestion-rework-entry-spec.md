# V2-100F RunManifest Tolerant Ingestion And Agent-owned Blackbox Verification Spec

## Status

- Stage: V2-100F
- State: REVIEW_REQUIRED
- Input: V2-090F real provider rerun result `blocked_by_missing_rework_entry`
- Output: revised spec for expert review; no implementation plan yet

## Reviewer Scenario Brief

V2-090F 的真实 provider rerun（模型供应商重跑）已经生成了可运行的 tiny-fullstack sample（微型全栈样例）：backend CRUD（后端增删改查）、checkout / return / delete（借出 / 归还 / 删除）和本地测试都能工作。但流程没有进入 V2-100 ReworkCycle（返工循环），而是在 RunManifest（运行清单）摄取阶段因 `json_array_contains_field` 这类 LLM（大模型）自然生成的 assertion type（断言类型）未被硬编码枚举支持而 raw crash（原始崩溃），最终状态为 `blocked_by_missing_rework_entry`。这说明当前问题不是“返工循环不会工作”，而是“真实失败还没被转换成可返工上下文”。

建议专家按以下顺序阅读：先读本文件，评审 V2-100F 是否应该把 RunManifest assertion（运行清单断言）改为 tolerant semantic ingestion（宽容语义摄取），并把黑盒验证升级为 Tester / Release DevOps（测试 / 发布运维）自主计划；再读 `doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md` 和 `doc/04-implementation/v2-090f-rerun-rework-entry-validation-implementation-plan.md`，理解当前 rework-entry（返工入口）验证目标；随后读 `examples/generated-workspaces/tiny-fullstack/30-audit/rework-entry-validation.md`、`examples/generated-workspaces/tiny-fullstack/30-audit/raw-run-error.txt` 和 `examples/generated-workspaces/tiny-fullstack/00-boardroom/generated-run-manifest.json`，确认真实失败现场；最后读 `doc/04-implementation/v2-100-agent-team-rework-loop-spec.md`，检查 V2-100F 是否与既有 ReworkRequest（返工请求）、TicketGraph（工单图）和 evidence/closeout（证据/收尾）边界一致。

## Problem

V2-090F real provider rerun reached `blocked_by_missing_rework_entry` before it could enter V2-100 ReworkCycle（返工循环）.

The immediate raw error was:

```text
ValueError: unsupported RunManifest behavior assertion type: json_array_contains_field
```

The generated sample project contains real implementation work: backend CRUD（后端增删改查）、checkout（借出）、return（归还）、delete（删除） and local tests can run. It also contains real contract drift（合同漂移） between generated implementation and generated RunManifest（运行清单）, such as readiness path（就绪路径） and response shape（响应结构） differences. Those drifts are valid rework input.

The failure is that the framework treats model-produced assertion type strings as a closed protocol enum during RunManifest ingestion（运行清单摄取）. Because LLM output can vary in wording, adding one alias at a time will trap the system in an endless adapter patch loop. A fully autonomous agent team framework must not raw-crash before it can collect facts and form rework context.

## Decision

Introduce V2-100F as a rework-entry hardening batch.

V2-100F must move RunManifest assertion handling from closed enum ingestion（封闭枚举摄取） to tolerant semantic ingestion（宽容语义摄取） and move blackbox verification（黑盒验证） from framework-driven manifest step execution（框架驱动运行清单步骤执行） to agent-owned verification planning（智能体拥有的验证规划）.

The governing rule is:

```text
Framework constrains what the system may claim.
Tester / Release DevOps decide what to verify.
Runner executes approved agent plans and records facts.
Checker / Closeout decide whether evidence proves the claim.
```

Therefore:

- Unknown or variant assertion language must not raw-crash manifest ingestion.
- Unknown or variant assertion language must not be silently skipped.
- Unknown or variant assertion language must not count as passed evidence.
- RunManifest（运行清单） is context and a run commitment（运行承诺）, not the complete blackbox test script（黑盒测试脚本）.
- Tester / Release DevOps must receive RunManifest, PackageContract（包合同）, AcceptanceContract（验收合同）, project docs, source refs（源码引用） and observed failures, then produce a provider-backed BlackboxVerificationPlan（模型支撑黑盒验证计划）.
- The runner executes that plan as tool / command / HTTP / browser facts（工具 / 命令 / HTTP / 浏览器事实）. It must not invent business probes, default endpoints, commands or assertions.
- ReworkRequest（返工请求） should receive raw RunManifest fragments（原始运行清单片段）、agent verification plan（智能体验证计划）、observed execution facts（观察执行事实） and advisory context（参考上下文） so CEO / Architect / Tester / Release DevOps（项目经理 / 架构师 / 测试 / 发布运维） can decide whether to fix implementation（实现）、RunManifest（运行清单）、contract（合同） or ticket graph（工单图）.

## Non-goals

V2-100F must not:

- Make unknown assertions pass by default.
- Drop assertions from the audit trail.
- Create a second EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、Checker（检查者） or CloseoutGate（收尾门禁）.
- Hardcode provider-specific alias lists as the primary design.
- Patch the generated sample project directly to satisfy the current manifest.
- Restore runner/helper（运行器/辅助器） business-domain probes as a success path.
- Treat RunManifest behavioral steps as the only allowed blackbox verification path.
- Add a standalone ManifestInterpreter（运行清单解释器） role or provider call owned by the framework.
- Let Tester / Release DevOps mark evidence passed without real execution facts.
- Let runtime（运行时） create ReworkPlan（返工计划） or mutate TicketGraph（工单图）.

## Required Architecture

### 1. Raw Manifest Assertion As First-class Context

RunManifest ingestion must preserve every provider-produced assertion as raw semantic payload（原始语义载荷） with at least:

- `probe_id`
- `step_id`
- `assertion_index`
- `raw_type`
- `raw_payload`
- `source_ref`

The ingestion gate may validate manifest skeleton（清单骨架） such as service refs（服务引用）、commands（命令）、service topology（服务拓扑）、steps（步骤）、method（方法）、path（路径）、expected status（期望状态） and capture declaration（捕获声明）. It must not require raw assertion type strings to belong to a closed enum before the run can proceed to agent-owned verification planning.

Ingestion output must be context, not evidence. It may include deterministic structural summaries（确定性结构摘要）, but those summaries must not become gate-only reason enums or passed behavior claims.

### 2. Agent-owned BlackboxVerificationPlan

V2-100F must introduce or extend a provider-backed BlackboxVerificationPlan（黑盒验证计划） owned by Tester / Release DevOps（测试 / 发布运维）.

The plan input must include:

- AcceptanceContract（验收合同） and blocking acceptance refs（阻塞验收引用）.
- PackageContract（包合同）.
- RunManifest raw and skeleton-normalized context（原始和骨架归一化运行清单上下文）.
- Project docs such as README, RUNBOOK, API docs or generated docs（项目文档）.
- Relevant source surface refs（源码面引用）.
- Previous observed failures and raw errors（已观察失败和原始错误）.
- Runtime permissions, network policy and allowed tool set（运行权限、网络策略和允许工具集）.

The plan output must include:

- plan id（计划 ID） and producer ProviderAttempt（模型调用尝试记录）.
- verification objective（验证目标）.
- selected commands / services / HTTP calls / browser actions / file reads（命令 / 服务 / HTTP 调用 / 浏览器动作 / 文件读取）.
- why each action is relevant to active acceptance refs（每个动作为何关联活跃验收引用）.
- required tool permissions（所需工具权限）.
- expected observations（预期观察） in open structured form, not closed assertion enums.
- evidence obligations to produce（应产生的证据义务）.

RunManifest is one input to this plan. Tester / Release DevOps may follow RunManifest steps, challenge them, add checks from API docs, compare manifest against RUNBOOK, or probe multiple documented endpoints when doing so is justified by the package context. The framework must not precompute those decisions.

### 3. Runner Executes Agent Plans And Records Facts

The runner must execute only approved BlackboxVerificationPlan actions. It may enforce sandbox, network, cwd, command, timeout and artifact recording policy（沙箱 / 网络 / 工作目录 / 命令 / 超时 / 制品记录策略）, but it must not generate business-domain verification actions itself.

For each executed action, it must record:

- command/tool/browser/HTTP action identity（命令 / 工具 / 浏览器 / HTTP 动作标识）.
- input refs and hashes（输入引用和哈希）.
- stdout/stderr/status/body/screenshot/artifact refs（输出引用） where applicable.
- exit code / HTTP status / browser result（退出码 / HTTP 状态 / 浏览器结果）.
- started/finished timestamps（开始/结束时间）.
- producing plan ref（产生该动作的计划引用）.
- acceptance refs and package refs claimed by the plan（计划声明的验收和包引用）.

Execution facts do not pass closeout by themselves. They are evidence inputs for EvidenceVerifier / Checker / CloseoutGate（证据验证器 / 检查者 / 收尾门禁）.

### 4. Rework Routing

V2-100F must route outcomes into three coarse states:

- `passed`: evidence is sufficient for closeout candidate（收尾候选）.
- `rework_required`: there is trustworthy problem context and the issue can be returned to CEO-governed ReworkCycle（项目经理治理返工循环）.
- `blocked_or_escalated`: the framework cannot form trustworthy rework context, execution is unsafe, required provider/config is missing, or termination policy is hit.

Most manifest, implementation, API, response-shape, readiness and assertion vocabulary problems should be `rework_required`, not terminal failure.

Implementation must rename `ReworkIssueCode.RUN_MANIFEST_MISMATCH`（运行清单不匹配） to `RUN_MANIFEST_ERROR`（运行清单错误）. `MISMATCH` is too narrow because the category includes ambiguous assertions, incomplete manifest semantics, unsafe execution context, bad service readiness, and implementation/manifest drift.

`RUN_MANIFEST_ERROR` is a coarse routing code. Fine details must live in raw/advisory context（原始/参考上下文）, not gate enums. Advisory context may include:

- raw assertion or manifest fragment（原始断言或清单片段）.
- agent interpretation summary（智能体解释摘要）.
- advisory labels（参考标签）.
- observed HTTP / command / browser facts（观察到的 HTTP / 命令 / 浏览器事实）.
- execution safety status（执行安全状态）.
- probe / step / capture context（探针 / 步骤 / 捕获上下文）.

Reducers, closeout and rework gates must not depend on advisory labels matching a fixed vocabulary.

### 5. No Standalone Model-mediated Interpretation

V2-100F must not add a standalone model-mediated manifest interpretation stage.

Semantic interpretation of ambiguous RunManifest assertions belongs inside Tester / Release DevOps verification planning. Their ProviderAttempt lineage attaches to BlackboxVerificationPlan, not to a framework-owned ManifestInterpreter（运行清单解释器）.

The framework may compute deterministic structural summaries and preserve raw payloads, but it must not ask a separate model to convert unknown assertions into canonical assertions that the framework then executes as if they were authoritative.

### 6. Completion And Escalation

Closeout failure should normally become rework, not terminal crash. Closeout may only pass when real evidence proves active acceptance claims. Failure should be `blocked_or_escalated` rather than `rework_required` only when the framework cannot build trustworthy rework context or cannot safely proceed.

Examples:

- missing RunManifest raw artifact（缺原始运行清单）;
- missing run / ticket / graph / provider attempt linkage（缺运行 / 工单 / 图 / 模型调用链路）;
- unsafe execution request outside policy（越权执行请求）;
- missing required provider/config for agent-owned verification planning（缺必需模型/配置）;
- forged or stale evidence（伪造或陈旧证据）;
- runtime attempts to create ReworkPlan or mutate graph（运行时试图创建返工计划或改图）;
- rework budget or termination policy is hit（预算或终止策略触发）.

## Required Negative Cases

V2-100F implementation plan must include negative tests proving:

- Unknown assertion type does not raw-crash ingestion.
- Unknown assertion type is not ignored.
- Unknown assertion type cannot become closeout success without agent-owned verification evidence.
- Raw RunManifest payload is preserved for Tester / Release DevOps planning.
- Runner cannot invent verification actions when BlackboxVerificationPlan is absent.
- Runner cannot execute actions outside the approved agent plan.
- Tester / Release DevOps BlackboxVerificationPlan without ProviderAttempt lineage fails.
- Tester / Release DevOps cannot mark behavior evidence passed without real execution facts.
- ReworkRequest cannot be created from raw exception alone; it requires trustworthy context such as raw manifest refs, agent plan refs, execution facts, active contract refs or an explicit blocked/escalated reason.
- Runtime cannot convert advisory labels, interpretation summaries, or agent prose into `passed`.
- Missing RunManifest raw artifact, missing graph linkage, unsafe execution request, or missing required provider/config routes to `blocked_or_escalated`, not silent fallback.
- New code and new artifacts must use `RUN_MANIFEST_ERROR`; `RUN_MANIFEST_MISMATCH` must not remain as an active routing code.

## Required Happy Path

V2-100F implementation plan must include happy path tests proving:

- A provider-produced RunManifest with novel assertion vocabulary is ingested without raw crash.
- Raw assertion payloads and manifest skeleton summaries are included in Tester / Release DevOps ExecutionPackage（执行包）.
- Tester / Release DevOps produces a provider-backed BlackboxVerificationPlan that may use RunManifest, project docs, API docs, source refs and previous failure context.
- Runner executes the approved plan and records command / HTTP / browser / tool facts with plan lineage.
- Checker / Closeout consumes those facts and either forms a closeout candidate or returns `rework_required`.
- Manifest / implementation / API / response-shape drift is projected into ReworkIssue（返工问题） using coarse `RUN_MANIFEST_ERROR` plus raw/advisory context.
- V2-090F rework-entry can proceed from `blocked_by_missing_rework_entry` to `rework_required` or a typed `blocked_or_escalated` reason, not raw exception.

## Expert Review Questions

Expert review should answer:

1. Is the ingestion boundary permissive enough to avoid endless alias patching?
2. Does the routing distinguish `passed`, `rework_required`, and `blocked_or_escalated` without using raw crash as control flow?
3. Does blackbox verification belong to Tester / Release DevOps rather than framework-generated manifest step execution?
4. Does the design avoid a standalone model-mediated manifest interpreter?
5. Are there any hidden second sources of truth for acceptance, source surfaces, run commands or closeout?

## Completion Criteria For This Spec

This spec is complete when:

- It is linked from `doc/04-implementation/INDEX.md`.
- `doc/04-implementation/backlog.md` lists V2-100F as REVIEW_REQUIRED.
- `doc/04-implementation/acceptance-criteria.md` records the new Phase 10 gap without marking it complete.
- `doc/05-project-log/decisions.md` records the architectural decision.
- `doc/05-project-log/2026-06.md` records that this is a spec-only expert review batch.

Implementation must wait for expert review and a separate implementation plan.
