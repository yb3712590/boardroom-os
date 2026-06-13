# 领域模型

## 文档职责

本文件定义 Boardroom OS V2 的核心领域对象及其关系。

## 对象关系总览

```text
BoardDirective
  -> ProjectCharter
  -> MethodologyProfile
  -> AcceptanceContract
  -> PackageContract
  -> TicketGraph
  -> TicketNode
      -> SeatDemand
      -> AgentSeatAssignment
          -> AgentSeat
              -> RoleProfile
              -> ModelExecutionProfile
  -> ExecutionPackage
  -> WorkProduct
  -> EvidenceClaim
  -> VerificationRun
  -> ReworkCycle
      -> ReworkRequest
      -> ReworkPlan
      -> ReworkAttempt
      -> ReworkOutcome
  -> SourceInventory
  -> CloseoutPackage
  -> ReplayBundle
  -> ProcessAuditReport
```

`SeatDemand`（席位需求）属于 ticket 创建事实，用于声明任务需要的 `RoleCategory`（角色类别）和 capability tags（能力标签）。因此 graph 层会引用 agents 层的 seat demand value object（席位需求值对象）；这是 demand-first assignment（需求优先派工）的显式依赖方向，不表示 runtime 可以绕过治理投影直接选 seat。

## BoardDirective

用户输入的原始需求或 PRD 引用。

最小字段：

```yaml
board_directive_id:
source_type: natural_language | prd_file | human_review_update
content_ref:
received_at:
requester_ref:
```

## ProjectCharter

项目章程，描述目标、范围、非目标、交付类型和风险。

```yaml
project_charter_id:
board_directive_ref:
project_goal:
delivery_type:
non_goals:
constraints:
risks:
success_summary:
```

## AcceptanceContract

动态验收合同。它必须来自当前需求和治理产物，不能使用固定静态 AC 列表覆盖所有项目。

```yaml
acceptance_contract_id:
project_charter_ref:
criteria:
  - acceptance_ref:
    statement:
    evidence_required:
    blocking: true
    source_surface_refs:
```

## PackageContract

生成项目包合同，定义最终项目的目录、运行方式、测试方式和集成边界。

```yaml
package_contract_id:
package_root:
project_type:
source_surfaces:
run_commands:
test_commands:
integration_boundaries:
documentation_obligations:
```

## TicketGraph

流程状态源。所有项目推进都由 ticket graph 表达。

```yaml
ticket_graph_id:
graph_version:
nodes:
edges:
blocked_by:
ready_queue:
completed_nodes:
```

## TicketNode

可执行工作单元。

```yaml
ticket_id:
purpose:
seat_demand:
depends_on:
acceptance_refs:
source_surface_refs:
evidence_obligations:
allowed_read_refs:
allowed_write_set:
status:
attempt_count:
```

## ReworkCycle

返工循环。它把 evidence/checker/closeout（证据/检查/收尾）发现的阻塞项提升为 CEO-governed（项目经理治理）的跨角色流程，而不是让 runtime（运行时）或 atomic-agent（原子智能体）内部循环直接决定完成。

```yaml
rework_cycle_id:
project_ref:
origin_ticket_ref:
trigger_ref:
trigger_kind: checker_verdict | final_evidence_table | closeout_gate
round_index:
status: requested | planned | executing | reviewing | accepted | escalated | exhausted
budget_policy_ref:
termination_policy:
```

## ReworkRequest

返工请求。它只能来自 verified blocker（已验证阻塞项），例如 FinalEvidenceTable（最终证据表）中的 missing/failed row（缺失/失败行）、CheckerVerdict（检查结论）的 blocking issue（阻塞问题）或 CloseoutGate（收尾门禁）失败。

```yaml
rework_request_id:
rework_cycle_ref:
requested_by_ref:
blocker_refs:
acceptance_refs:
source_surface_refs:
required_artifact_types:
evidence_refs:
summary:
```

## ReworkPlan

返工计划。CEO（项目经理/治理角色）或 Architect（架构师）读取 ReworkRequest（返工请求）后，决定修原 ticket（工单）、拆新 ticket、重排依赖、要求合同修订或升级人工复核。

```yaml
rework_plan_id:
rework_cycle_ref:
planner_attempt_ref:
decision:
ticket_graph_patch_ref:
target_ticket_refs:
contract_change_refs:
rationale:
```

## ReworkAttempt

返工尝试。每次尝试必须绑定新的 ExecutionPackage（执行包）和真实执行事实；atomic-agent completed（原子智能体运行完成）只表示执行事实完成，不表示返工已被接受。

```yaml
rework_attempt_id:
rework_cycle_ref:
ticket_ref:
execution_package_ref:
agent_run_ref:
provider_attempt_refs:
tool_attempt_refs:
command_evidence_refs:
workspace_mutation_refs:
source_lineage_refs:
```

## ReworkOutcome

返工结果。只有 EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、Checker（检查者）和必要的 CloseoutGate（收尾门禁）重新通过后，返工才能 accepted（接受）。

```yaml
rework_outcome_id:
rework_cycle_ref:
reviewer_attempt_ref:
status: accepted | still_blocked | escalated | exhausted
remaining_blocker_refs:
accepted_ticket_refs:
next_rework_request_ref:
```

## AgentSeat

本项目中实际启用的 agent seat。

```yaml
seat_ref:
actor_ref:
project_ref:
role_profile_ref:
role_category:
capability_tags:
model_execution_profile_ref:
skill_refs:
context_budget_tokens:
lifecycle_status:
```

## ExecutionPackage

worker 或 checker 的结构化执行包。

```yaml
execution_package_id:
ticket_ref:
graph_version:
seat_ref:
objective:
context_refs:
constraints:
acceptance_refs:
source_surface_refs:
allowed_write_set:
required_outputs:
commands:
fallback_policy:
```

## WorkProduct

agent 或工具产出的工作结果。

```yaml
work_product_id:
execution_package_ref:
producer_attempt_ref:
artifact_refs:
summary:
claim_refs:
```

## EvidenceClaim

关于 source/test/run/integration/closeout 的证据声明。

```yaml
evidence_claim_id:
claim_type:
acceptance_refs:
source_surface_refs:
producer_ref:
artifact_refs:
verification_run_refs:
```

## VerificationRun

真实 runner 或 tool 执行结果。

```yaml
verification_run_id:
command:
workspace_ref:
exit_code:
stdout_ref:
stderr_ref:
started_at:
finished_at:
runner_ref:
```

## SourceInventory

最终源码清单。必须绑定文件 hash、producer、acceptance refs、git state。

```yaml
source_inventory_id:
package_commit_ref:
files:
  - path:
    sha256:
    source_surface_ref:
    producer_ticket_ref:
    acceptance_refs:
    evidence_refs:
```

## CloseoutPackage

最终收口包。

```yaml
closeout_package_id:
graph_version:
package_commit_ref:
acceptance_summary_ref:
source_inventory_ref:
replay_bundle_ref:
process_audit_ref:
verdict: passed | failed
```

## ReplayBundle

审计和恢复所需的可重放材料。

```yaml
replay_bundle_id:
event_range:
projection_versions:
artifact_manifest_ref:
hash_manifest_ref:
replay_report_ref:
```

## ProcessAuditReport

人类可读流程审计资料。

```yaml
process_audit_report_id:
timeline_ref:
decision_log_ref:
agent_context_index_ref:
ticket_graph_ref:
evidence_map_ref:
git_audit_ref:
closeout_summary_ref:
```
