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
  -> AgentSeatAssignment
  -> ExecutionPackage
  -> WorkProduct
  -> EvidenceClaim
  -> VerificationRun
  -> SourceInventory
  -> CloseoutPackage
  -> ReplayBundle
  -> ProcessAuditReport
```

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
owner_seat_ref:
depends_on:
acceptance_refs:
source_surface_refs:
evidence_obligations:
allowed_read_refs:
allowed_write_set:
status:
attempt_count:
```

## AgentSeat

本项目中实际启用的 agent seat。

```yaml
seat_id:
role_profile_ref:
capability_tags:
responsibility_boundary:
model_execution_profile_ref:
skill_refs:
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

