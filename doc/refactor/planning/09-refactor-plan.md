# 重构实施计划

## 总体策略

本次重构采用“先立 contract，再拆 runtime”的顺序。

不直接从代码清理开始。先将目录、写入面、provider、actor lifecycle、progression policy、deliverable contract 和 replay/resume 的验收口径写清，再按阶段把现有 runtime 的隐式逻辑迁移到显式 policy 和 contract 中。

## Phase 0：文档与边界冻结（已完成）

目标：建立重构控制面，冻结主线取舍，并把项目目录重置为后端自治 runtime 重建基线。

已完成：

- 写入 12 份规划文档。
- 更新文档入口。
- 归档一次性 handoff 文档。
- 明确本轮不承载的愿景。
- 标记 015 为压力审计，不作为自治验收通过。
- 删除旧 `frontend/` 源码树。
- 完成 Round 4 backend cleanup：删除无引用旧 `project_init_architecture_tickets.py`，并把 worker-admin / worker-runtime frozen boundary 同步为未挂载的冻结材料。
- 将旧设计、旧路线、旧任务流水、旧历史记忆、001-014 integration logs 和旧 refactor 实施资料集中归档到 `doc/archive/`。

验收：

- `doc/refactor/planning/INDEX.md` 可导航全部文档。
- `doc/README.md` 指向新规划入口。
- `doc/` active 入口只保留当前真相、重构控制面、后端参考和必要 015 证据。
- Phase 0 提交不包含 runtime 行为修改。

## Phase 1：目录 / 产物 / 写权限 contract

目标：把目录和写入面变成 runtime contract。

任务：

- [x] 将 `03-directory-contract.md` 映射到现有 workspace 代码：`backend/app/core/workspace_path_contracts.py` now resolves workspace source/test/git refs, runtime delivery/check/closeout refs, governance refs, upload-import refs, archive refs, and unknown refs into explicit contract kinds and logical paths.
- [x] 将 `04-write-surface-policy.md` 编译为可测试 policy：`CAPABILITY_WRITE_SURFACES`, `build_allowed_write_set_for_capabilities()`, and `match_contract_write_set()` codify capability-keyed write surfaces without new role-name-to-write-root branches.
- [x] closeout final refs 统一走 artifact type allowlist：ticket closeout hooks and workflow completion gates classify final refs with `classify_closeout_final_artifact_ref()`.
- [x] 阻断 placeholder source/test fallback 进入 final evidence：placeholder, legacy fallback, superseded, archive, governance, and unknown refs are rejected before closeout completion.

验收：

- [x] 任意 Phase 1 covered artifact ref 可追溯到合法目录或 explicit illegal/unknown kind.
- [x] checker/source-delivery/closeout paths share the same artifact legality vocabulary for evidence refs.
- [x] 015-style placeholder delivery refs cannot pass closeout final evidence checks.

## Phase 2：Provider adapter 重建与 streaming soak test

目标：证明 provider 层稳定性，隔离上游故障与本项目实现问题。

任务：

- 定义标准 `ProviderEvent`。
- 抽离厂商 SSE/parser。
- 明确 timeout 语义。
- 建立 provider smoke/soak test。
- 记录 preferred vs actual provider/model。

验收：

- 同一 API 配置连续 streaming smoke 成功率达到阈值。
- malformed SSE、empty assistant、schema failure、first token timeout 都有分类测试。
- late provider event 不污染 current ticket projection。

## Phase 3：Actor / Role lifecycle 重建

目标：把 role template 从 runtime 执行键降级为 governance template。

任务：

- [x] 建立 actor registry：Round 7A added independent `ACTOR_*` lifecycle events, replayable `actor_projection`, repository read APIs, and tests proving no `EMPLOYEE_*` bridge.
- [x] 建立 capability mapping：Round 7A added `build_role_template_capability_contract()` so RoleTemplate emits capability/provider preference only, not runtime execution keys.
- [x] 定义 actor enable/suspend/deactivate/replace 事件：Round 7A reducer tests cover the actor lifecycle state transitions and replacement lineage.
- [x] 修复 excluded employee 继承污染：Round 7B adapts legacy `excluded_employee_ids` into scoped exclusions and clears unscoped legacy lists on retry/rework.
- [x] actor pool empty 时生成显式 action/diagnostic：Round 7B records `EVENT_SCHEDULER_LEASE_DIAGNOSTIC_RECORDED` with `NO_ELIGIBLE_ACTOR`, candidate diagnostics, and suggested actions.

Round 7C 已把 Assignment 与 Lease 拆为独立 runtime identity；`TICKET_ASSIGNED` / `TICKET_LEASE_GRANTED` 及 assignment/lease projections 已落地，ticket lease/start/timeout、scheduler dispatch、context compiler 和 execution package meta 均携带 `actor_id` / `assignment_id` / `lease_id`。`lease_owner` 只保留为 legacy display/migration alias，不再驱动新 runtime execution identity。

Round 7D–7E 已完成 provider provenance 与 Phase 3 集成收口：assignment payload/projection、provider audit event 和 runtime result evidence 统一记录 preferred/actual provider/model、selection/policy/fallback reason、provider health snapshot、cost/latency class；provider selection 不再使用 `role_bindings` 或 binding chain 作为 runtime execution key，provider failover 只使用 provider config `fallback_provider_ids` 并把 final execution 的 actual provider/model 记录为 fallback provider。Round 7E 删除未知 legacy `role_profile_ref -> role_profile:*` runtime execution key fallback 和未引用 legacy binding helper；`role_bindings` / `provider_model_entries` 仅作为配置导入、sharded routing snapshot、API 展示和 RoleTemplate 默认 preference 来源保留。

验收：

- [x] 派工由 required capabilities 驱动：Round 7B scheduler consumes `actor_projection` plus compiled `required_capabilities` through `assignment_resolver`.
- [x] 角色名不再决定 write root 或 runtime execution key：Round 7E grep/test evidence covers runtime, scheduler, provider selection and context compiler paths; unknown legacy `role_profile_ref` no longer becomes `role_profile:*` execution target.
- [x] no eligible worker 不会 silent stall：Round 7B emits explicit no-eligible actor scheduler diagnostic with suggested actions.
- [x] Assignment 与 Lease 分离：Round 7C introduced `TICKET_ASSIGNED` and `TICKET_LEASE_GRANTED`, assignment/lease projections, ticket `actor_id` / `assignment_id` / `lease_id`, and runtime/context compiler identity propagation.

## Phase 4：Progression policy engine 抽离

目标：把推进规则从 controller/runtime/ticket handlers 中抽到显式 policy。

任务：

- [x] Round 8A：建立 `ProgressionSnapshot` / `ProgressionPolicy` / `ActionProposal` contract，并实现可独立测试的 `decide_next_actions(snapshot, policy)` 最小骨架。
- [x] Round 8B：建立 effective graph pointer 规则；`REPLACES` 新票为 current，`CANCELLED` / `SUPERSEDED` 不参与 effective edges/readiness/complete，orphan pending 不阻断 graph complete，缺 explicit pointer 不用 `updated_at` 猜测。
- [x] Round 8A：统一 CREATE_TICKET / REWORK / CLOSEOUT / INCIDENT / WAIT / NO_ACTION 的 metadata helper。
- [x] Round 8C：governance chain、required architect governance gate、meeting requirement、backlog handoff fanout 和 fanout graph patch plan 由结构化 policy input 驱动。
- [x] Round 8C：移除 freeform `hard_constraints` substring gate 和 hardcoded backlog milestone fanout 作为推进依据；`hard_constraints` 只保留为 snapshot/display 字段。
- [x] Round 8D：closeout readiness、duplicate closeout、closeout blocker、rework、retry/restore、completed-ticket reuse gate、superseded/invalidated lineage、incident followup action 和 BR-100 loop threshold 由结构化 policy input / proposal 驱动。
- [x] Round 8E：迁移 controller/runtime/scheduler/CEO proposer 主路径业务判断；旧路径只保留 input compiler、policy call、proposal execution shell、API display 或显式 no-op/incident。

验收：

- [x] Round 8A：相同 snapshot + policy 输出稳定 action proposals（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_progression.py -q`）。
- [x] Round 8A：六类 action metadata helper 覆盖 reason code、idempotency key、source graph version、affected node refs、expected state transition 和 policy ref。
- [x] Round 8B：effective graph pointer、orphan pending、CANCELLED/SUPERSEDED effective edge 排除、approval/incident/in-flight/blocked/graph reduction/stale-orphan reason code 有 policy 单测；ticket graph facade 通过 policy 回填 ready/blocked/in-flight indexes。
- [x] Round 8C：structured governance/fanout policy 单测覆盖 legacy hint ignored、architect gate、meeting wait、backlog handoff fanout、graph patch fanout 和 milestone-only no fanout；scheduler/controller governance/fanout 关键词回归通过。
- [x] Round 8D：structured closeout/recovery policy 单测覆盖 closeout metadata、duplicate closeout `NO_ACTION`、closeout blockers、checker blocking rework、retry budget exhausted、restore-needed missing ticket id、completed-ticket reuse gate、superseded/invalidated lineage、retryable terminal target、unrecoverable failure kind 和 BR-100 loop threshold。
- [x] Round 8E：015 的 stale gate、orphan pending、restore-needed missing ticket id 有 policy 回归；BR-100 loop 有结构化 threshold 等价 policy 回归，完整 replay DB 验证仍归 Phase 7。
- [x] Round 8E：Scheduler 不再做 closeout/fanout/rework 业务判断；只看 policy/controller explicit state 或输出显式 action/incident。

8E 收口证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_progression.py backend/tests/test_ticket_graph.py backend/tests/test_workflow_autopilot.py backend/tests/test_ceo_scheduler.py backend/tests/test_scheduler_runner.py -q` -> `333 passed, 1 warning`。
- `rg -n "pause.*fanout|fanout.*pause|hard_constraints.*architect|hard_constraints.*meeting|_build_autopilot_closeout_batch|_workflow_is_closeout_candidate|_workflow_has_existing_closeout_ticket|_workflow_runtime_graph_is_complete" backend/app/core backend/app/scheduler_runner.py` -> 无命中。
- `rg -n "_build_backlog_followup_batch|_build_required_governance_ticket_batch|_resolve_required_governance_ticket_payload|_resolve_followup_ticket_payload" backend/app/core backend/tests` -> 无 runtime/helper 命中。

Phase 4 边界：governance chain、architect/meeting gate、backlog fanout、closeout、rework、retry/restore、incident followup 和 BR-100 loop threshold 已由 policy proposal / helper 驱动。Controller 负责读取 DB/artifact index 并编译 structured input；CEO proposer/validator/auto-advance/projection 只作为 proposal execution shell、policy helper caller 或 API display。Phase 5 deliverable contract、Phase 6 replay/resume/checkpoint 和 Phase 7 015 full replay 未在本阶段完成。

## Phase 5：Deliverable contract + checker/rework 重建

目标：closeout 证明 PRD 满足，而不是 graph terminal。

Round 9A 已完成最小 contract/evaluator skeleton，Round 9B 已完成 source surface / evidence pack 映射：

- `backend/app/core/deliverable_contract.py` 定义版本化 `DeliverableContract`、`DeliverableEvaluation` 和 `ContractFinding`。
- `compile_deliverable_contract()` 可从结构化 PRD / charter / ticket acceptance 输入编译 contract。
- `compile_deliverable_contract()` 可从 locked scope、governance/design/backlog assets 和 allowed write set metadata 编译 required source surfaces。
- `EvidencePack` / `EvidenceItem` 映射 source/test/check/git/closeout evidence 到 acceptance criteria、source surface、producer ticket/node 和 artifact legality。
- `evaluate_deliverable_contract()` 是纯函数 evaluator；9A 覆盖 missing acceptance、missing required evidence、unknown evidence kind 和 empty final evidence，9B 覆盖 invalid evidence、placeholder/source-test fallback、acceptance 缺 required source/test/check/git/closeout evidence。
- `workflow_completion.py` 和 `ticket_handlers.py` 只新增 closeout preview helper，没有迁移 checker verdict、rework target 或 closeout final evidence 主路径。

任务：

- [x] 将 PRD acceptance 编译为 deliverable contract（Round 9A skeleton）。
- [x] 建立稳定 contract id、finding id 和 evaluation fingerprint（Round 9A skeleton）。
- [x] 将 required source surfaces 映射到 capability write surfaces 和 required evidence kinds（Round 9B）。
- [x] 将 evidence pack 映射到 acceptance criteria，并拒绝 superseded/placeholder/archive/unknown/stale pointer evidence（Round 9B）。
- checker verdict 与 deliverable contract 解耦。
- rework target 指向能修问题的 upstream node。
- `APPROVED_WITH_NOTES` 不得覆盖 blocking contract gap。

验收：

- placeholder source/evidence 不能通过 contract evaluator。
- failed delivery report 有结构化 convergence policy 才能放行。
- final evidence set 不包含 superseded/old placeholder 资产；Round 9B 已覆盖 evaluator 层拒绝，closeout table 主路径留给 9E。

Round 9B 证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py -q` -> `34 passed`。

下一入口：Round 9C Checker verdict / convergence policy gate。不得用 checker notes、graph terminal 或 failed delivery report freeform 文本覆盖 blocking contract gap。

## Phase 6：Replay / resume / checkpoint 重建

目标：replay/resume 成为一等操作。

任务：

- 增量 projection checkpoint。
- event replay 性能预算。
- resume from event/version/ticket/incident。
- replay bundle materializer。
- 禁止人工投影补写作为正常路径。

验收：

- 从中间 graph version 恢复不需要人工 DB/projection 注入。
- 1GB 级 DB 不需要每次全量 JSON replay。
- replay 后 artifact/doc view hash 一致。

## Phase 7：015 replay 包验证

目标：用 `boardroom-os-replay` 作为回归靶场。

任务：

- 导入 015 replay 包。
- 重放关键 incident/rework/closeout 路径。
- 验证 placeholder、orphan pending、provider late event、manual closeout recovery 都被新规则处理。

验收：

- 无人工 DB/projection 注入。
- closeout 不能绕过 deliverable contract。
- 输出 replay audit report。

## Phase 8：新 live scenario clean run

目标：证明新 runtime 能 clean run。

任务：

- 设计小而完整的 PRD scenario。
- 固定 provider soak 前置条件。
- 运行无人工 DB/projection 介入的 live。
- 产出 closeout、evidence、replay bundle。

验收：

- zero manual intervention。
- final deliverable contract pass。
- provider failure attribution clear。
- replay from checkpoint pass。

## Cleanup audit guardrail

Round 4 backend cleanup 只允许删除满足“无生产引用、无当前测试引用、非审计证据、非未来目标架构必要入口”的废弃 surface。`ticket_handlers.py`、`runtime.py`、`workflow_controller.py` 仍按后续 policy/contract phase 拆分；cleanup 轮只记录这些大模块的拆分建议，不直接改行为。

## 提交策略

- Phase 0 已完成目录清理和文档归档，作为合回 `main` 的重新开始基线。
- Phase 1 以后每个 phase 单独提交。
- 行为代码重构和文档移动不要混在同一提交。
- 每个提交必须更新对应 acceptance。
