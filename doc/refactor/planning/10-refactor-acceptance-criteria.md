# 重构验收标准

## 总验收

- [ ] 无人工 DB/projection/event 注入完成 replay/resume。
- [ ] 无 placeholder source/evidence 能通过 deliverable closeout。
- [ ] Provider streaming smoke 在同一 API 配置下达到外部 AI 编程框架同级稳定性。
- [ ] Runtime kernel 不硬编码 CEO、员工、角色模板或业务 milestone。
- [ ] Closeout 证明 PRD acceptance，而不是只证明 graph terminal。
- [ ] 文档视图可从 event/process asset 重新物化。

## Phase 0：文档与边界冻结

- [x] 12 份重构规划文档已写入 `doc/refactor/planning/`。
- [x] 新规划索引 `INDEX.md` 已建立。
- [x] `doc/README.md` 已加入新规划入口。
- [x] 一次性 handoff 文档已安全归档。
- [x] 旧 `frontend/` 源码树已删除。
- [x] 旧设计、路线、任务 backlog、历史记忆和 001-014 integration logs 已集中归档。
- [x] `doc/` active 入口只保留当前真相、重构控制面、后端参考和必要 015 证据。
- [x] Phase 0 未修改 provider、scheduler、ticket handler、workflow controller 或 `backend/app/core` runtime 行为。
- [x] Round 4 backend cleanup 已删除无生产/测试引用的旧 project-init architecture helper，并同步 frozen boundary truth。
- [x] Round 4 未拆 provider、progression、actor 或核心 runtime 大模块。

## Phase 1：目录 / 产物 / 写权限 contract

- [x] 仓库根目录已清理为 backend-only runtime rebuild 基线。

- [x] 每种 Phase 1 covered artifact ref 都有合法路径映射或显式非法分类。
- [x] write-set policy 以 capability 为主键。
- [x] 角色模板不直接决定 write root；Phase 1 未新增 role-name-to-root 分支。
- [x] closeout final refs 只接受合法 delivery/check/verification/git/closeout evidence。
- [x] placeholder source/test fallback 被阻断。
- [x] 目录契约有单测或 contract test。

## Phase 2：Provider adapter 与 streaming soak

- [x] Provider adapter 输出标准 `ProviderEvent`，OpenAI Responses streaming 已通过 `ProviderRequest -> ProviderEvent -> ProviderResult/ProviderFailure` 聚合并接入 ticket provider 调用层。
- [x] first-token timeout、stream-idle timeout、request-total timeout、ticket lease timeout 被区分。
- [x] malformed SSE 有 raw archive 和 retryable 分类；provider 保存 raw event archive，runtime 保留 `MALFORMED_STREAM_EVENT`，raw archive 只作为 operational diagnostics，不可作为 closeout final evidence。
- [x] empty assistant text 被分类为 provider bad response。
- [x] schema validation failure 不被归为 upstream unavailable。
- [x] 同一 API 配置连续 20 次 streaming smoke 成功率 >= 95% 的独立 smoke 已建立。
- [x] late provider event 不覆盖 current graph pointer；timed-out attempt 后到达的 heartbeat/completed/output 只保留旧 attempt lineage，不改写 current ticket projection、runtime node pointer 或 final evidence。

## Phase 3：Actor / Role lifecycle

- [x] Actor registry 有 enable/suspend/deactivate/replace 状态机（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_reducer.py::test_reducer_rebuilds_actor_projection_from_independent_actor_events -q`）。
- [x] RoleTemplate 只映射 capability，不作为 runtime 执行键（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_execution_targets.py::test_role_template_capability_contract_does_not_emit_runtime_execution_key backend/tests/test_execution_targets.py::test_unknown_role_profile_ref_is_not_runtime_execution_key -q`）。
- [x] Assignment 与 Lease 分离（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_reducer.py::test_reducer_keeps_assignment_history_separate_from_lease_timeout backend/tests/test_api.py::test_repository_persists_assignment_and_lease_projections backend/tests/test_scheduler_runner.py::test_scheduler_replacement_actor_gets_new_assignment_without_old_lease -q`）。
- [x] `excluded_employee_ids` 有作用域，不会继承污染（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_assignment_resolver.py backend/tests/test_scheduler_runner.py::test_scheduler_blocks_rework_fix_when_only_capable_actor_is_scoped_excluded -q`）。
- [x] no eligible actor 产生显式 action 或 incident（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_assignment_resolver.py::test_resolver_returns_complete_suggested_actions_in_required_order backend/tests/test_scheduler_runner.py::test_scheduler_does_not_lease_without_enabled_actor_registry_entry -q`）。
- [x] provider preferred/actual 记录完整（`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_scheduler_runner.py::test_scheduler_assignment_records_provider_provenance_from_actor_preference backend/tests/test_scheduler_runner.py::test_runtime_provider_rate_limit_failover_uses_fallback_provider_before_deterministic backend/tests/test_runtime_provider_center.py::test_resolve_provider_failover_uses_provider_fallbacks_not_binding_chain -q`）。
- [x] role/profile/provider legacy surface 已收口（grep runtime/scheduler/provider/context compiler 确认无未知 `role_profile_ref -> role_profile:*` execution key、无 `role_bindings` selection/failover branch；`role_bindings` / `provider_model_entries` 仅为导入、routing snapshot、API 展示和 RoleTemplate 默认 preference 来源）。

## Phase 4：Progression policy engine

- [x] `decide_next_actions(snapshot, policy)` 可独立测试（Round 8A/8B/8C：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_progression.py -q`）。
- [x] CREATE_TICKET / WAIT / REWORK / CLOSEOUT / INCIDENT / NO_ACTION 都有 reason code（Round 8A metadata helper + Round 8B approval/incident/in-flight/blocked/graph reduction/stale-orphan/graph-complete reason code + Round 8C governance/fanout reason code + Round 8D closeout/recovery/incident reason code 测试覆盖）。
- [x] Effective graph pointer 不受 orphan pending 干扰（Round 8B policy 单测覆盖 orphan pending 不阻断 graph complete，015 replay 仍归 Phase 7）。
- [x] CANCELLED/SUPERSEDED 节点不参与 effective edges（Round 8B policy 单测覆盖；ticket graph facade 保留 `REPLACES` lineage 展示但不进入 policy effective edges）。
- [x] substring hint 不再驱动会议/架构 gate（Round 8C policy/scheduler 回归覆盖 legacy hard constraint hint ignored；grep controller/proposer 无 `hard_constraints` substring gate）。
- [x] hardcoded backlog milestone fanout 被 policy/graph patch 替代（Round 8C policy 单测覆盖 handoff fanout、graph patch fanout、milestone-only no fanout；controller fanout 只由 validated backlog handoff 或 structured graph patch plan 编译为 policy input）。
- [x] closeout readiness 和 duplicate closeout 由 policy proposal 决定（Round 8D policy 单测覆盖 `CLOSEOUT` stable metadata、duplicate closeout `NO_ACTION`、open incident/approval/gate issue/illegal evidence blockers；controller 只编译 readiness input）。
- [x] retry/restore/rework/incident followup 有结构化 policy 回归（Round 8D policy 单测覆盖 checker blocking finding、retry budget exhausted、restore-needed missing ticket id、completed-ticket reuse gate、superseded/invalidated lineage、retryable terminal target、unrecoverable failure kind 和 BR-100 loop threshold）。
- [x] CREATE_TICKET / WAIT / REWORK / CLOSEOUT / INCIDENT / NO_ACTION 六类 action 都有 reason code、idempotency key、source graph version、affected node refs 和 expected state transition 验收测试（`backend/tests/test_workflow_progression.py::test_phase4_action_proposals_expose_required_acceptance_metadata`）。
- [x] scheduler/controller/proposer 不再直接做 closeout/fanout/rework 业务判断；旧路径只保留 policy input compiler、policy call、proposal execution shell、API display 或 explicit no-op/incident（Round 8E 五组 pytest + grep 无旧 helper/substr gate 命中）。

Round 8E 证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_progression.py backend/tests/test_ticket_graph.py backend/tests/test_workflow_autopilot.py backend/tests/test_ceo_scheduler.py backend/tests/test_scheduler_runner.py -q` -> `333 passed, 1 warning`。
- `rg -n "pause.*fanout|fanout.*pause|hard_constraints.*architect|hard_constraints.*meeting|_build_autopilot_closeout_batch|_workflow_is_closeout_candidate|_workflow_has_existing_closeout_ticket|_workflow_runtime_graph_is_complete" backend/app/core backend/app/scheduler_runner.py` -> 无命中。
- `rg -n "_build_backlog_followup_batch|_build_required_governance_ticket_batch|_resolve_required_governance_ticket_payload|_resolve_followup_ticket_payload" backend/app/core backend/tests` -> 无 runtime/helper 命中。

015 映射：stale gate 由 `test_policy_runtime_pointer_selects_current_and_missing_pointer_blocks_reduction` 覆盖结构化 current pointer 等价；orphan pending 由 `test_policy_orphan_pending_does_not_block_graph_complete` 覆盖；restore-needed missing ticket id 由 `test_policy_restore_needed_missing_ticket_id_opens_incident` 覆盖；BR-100 loop 由 `test_policy_br100_loop_threshold_opens_incident` / `test_policy_br100_loop_below_threshold_requests_rework` 覆盖结构化 threshold 等价。BR-100 full replay 需要 Phase 7 replay DB/event import，Phase 4 不勾 Phase 7 项。

## Phase 5：Deliverable contract

- [x] PRD acceptance criteria 可编译成 `DeliverableContract`（Round 9A：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py -q`）。
- [x] Required source surfaces 有路径、capability、evidence 映射（Round 9B：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py -q`）。
- [x] Evidence pack 能映射到 acceptance criteria（Round 9B：同上）。
- [x] `APPROVED_WITH_NOTES` 不放行 blocking contract gap（Round 9C：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_autopilot.py -q`）。
- [x] blocking contract gap 产生 upstream rework target（Round 9D：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_progression.py -q`；覆盖 source surface / producer node、missing test evidence、checker-only defect、missing current producer incident、controller recovery input、BR-040/BR-041 placeholder 等价）。
- [x] closeout package 包含 contract version/id、evaluation fingerprint 和 final evidence table（Round 9E：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_output_schemas.py backend/tests/test_api.py::test_closeout_internal_checker_approved_returns_completion_summary -q`；完整批量命令见下方 9E 证据）。
- [x] superseded/placeholder/archive/unknown/stale/governance/backlog evidence 不满足 required evidence，也不会进入 closeout final evidence table（Round 9E：`pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_autopilot.py -q` 覆盖 evaluator/table/gate）。

Round 9A 证据：contract/evaluator skeleton 已覆盖 missing acceptance、missing required evidence、unknown evidence kind、empty final evidence 和重复 evaluation 稳定输出。

Round 9B 证据：source surface path/capability/evidence mapping、evidence -> acceptance mapping、关键 acceptance 缺 evidence、placeholder source/test fallback、superseded/archive/unknown/stale evidence 拒绝均有单测。

Round 9C 证据：checker gate 先消费 `DeliverableEvaluation`，failed delivery report 无结构化 `ConvergencePolicy` 不放行，结构化 policy 只放行声明 gap/scope/expiry；目标测试 `backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework backend/tests/test_api.py::test_structured_convergence_policy_allows_failed_check_report` -> `3 passed`。

Round 9D 证据：contract finding 编译为 upstream recovery action；missing current producer 输出 incident；closeout gate issue 编译进 recovery input；failed delivery checker rework fix ticket 指向 producer ticket/node。

Round 9E 证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py backend/tests/test_output_schemas.py -q`：覆盖 PRD acceptance compiler、source surface mapping、evidence pack mapping、closeout schema contract fields、final evidence table 行字段、superseded/placeholder/archive/unknown/stale/governance/backlog refs 排除。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_autopilot.py backend/tests/test_workflow_progression.py -q`：覆盖 closeout contract/table gate、stale old attempt 排除、governance/backlog final refs 拒绝、graph terminal 不替代 contract satisfaction、rework upstream target 和 closeout proposal contract readiness。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_closeout_internal_checker_approved_returns_completion_summary backend/tests/test_api.py::test_manual_closeout_recovery_cannot_bypass_contract_table backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework backend/tests/test_api.py::test_structured_convergence_policy_allows_failed_check_report -q`：覆盖 closeout package contract fields、manual closeout recovery 阻断、failed delivery checker rework、无结构化 convergence policy 不放行、结构化 convergence policy 放行。
- `rg -n "graph terminal|checker notes|freeform|final_artifact_refs.*satisf" backend/app/core`：确认旧 graph terminal、checker notes/freeform、final refs satisfaction 文本路径不作为 runtime 放行依据。
- `rg -n "_delivery_closeout_final_artifact_refs|classify_closeout_final_artifact_ref|evaluate_deliverable_contract|final_evidence_table" backend/app/core`：确认保留 helper 边界和主路径 evaluator/table 调用点。

015 结构化覆盖：

- BR-040、BR-041 placeholder delivery：Round 9D/9E 单测覆盖 placeholder source/evidence 和 closeout placeholder final ref 阻断；完整 015 replay 保持在 Phase 7。
- BR-100 final checker loop：Round 8D/8E policy 单测覆盖结构化 threshold 等价；完整 015 replay 保持在 Phase 7。
- closeout final refs 混入治理文档 / backlog recommendation：Round 9E 单测覆盖治理文档和 backlog final ref 拒绝，以及 final table exclusion。
- manual closeout recovery：Round 9E API 测试覆盖篡改 final table 后 checker approval 不能完成 workflow；真实 015 replay 保持在 Phase 7。

## Phase 6：Replay / resume / checkpoint

- [x] 支持 resume from event id。证据：`backend/tests/test_replay_resume.py::test_resume_from_event_id_returns_explicit_watermark_boundary`。
- [x] 支持 resume from graph version。证据：`backend/tests/test_replay_resume.py::test_resume_from_graph_version_returns_watermark_and_projection_summary`、`backend/tests/test_replay_resume.py::test_graph_version_resume_matches_full_replay_projection_summary`、`backend/tests/test_replay_resume.py::test_graph_version_resume_preserves_orphan_pending_and_effective_edge_semantics`、`backend/tests/test_replay_resume.py::test_graph_version_resume_keeps_late_old_attempt_out_of_current_pointer`、`backend/tests/test_replay_resume.py::test_graph_version_resume_keeps_late_old_cancelled_out_of_patch_legality`、`backend/tests/test_replay_resume.py::test_graph_version_resume_fails_closed_when_graph_version_missing`、`backend/tests/test_replay_resume.py::test_graph_version_resume_fails_closed_when_graph_version_is_gap`、`backend/tests/test_replay_resume.py::test_graph_version_resume_fails_closed_when_request_event_range_mismatches`、`backend/tests/test_replay_resume.py::test_graph_version_resume_fails_closed_when_graph_patch_hash_is_missing`、`backend/tests/test_replay_resume.py::test_graph_version_resume_fails_closed_when_graph_patch_hash_mismatches`、`backend/tests/test_replay_resume.py::test_graph_version_resume_fails_closed_when_projection_rebuild_rejects_patch`。
- [x] 支持 resume from ticket id。证据：`backend/tests/test_replay_resume.py::test_resume_from_ticket_id_returns_watermark_runtime_assignment_lease_and_refs`、`backend/tests/test_replay_resume.py::test_resume_from_ticket_id_preserves_terminal_state_and_related_refs`、`backend/tests/test_replay_resume.py::test_ticket_id_resume_fails_closed_when_ticket_is_missing`、`backend/tests/test_replay_resume.py::test_ticket_id_resume_fails_closed_when_runtime_node_view_is_broken`。
- [x] 支持 resume from incident id。证据：`backend/tests/test_replay_resume.py::test_resume_from_incident_id_preserves_source_ticket_followup_and_recovery_lineage`、`backend/tests/test_replay_resume.py::test_incident_id_resume_fails_closed_when_incident_is_missing`、`backend/tests/test_replay_resume.py::test_incident_id_resume_fails_closed_when_pinned_source_ticket_mismatches`、`backend/tests/test_replay_resume.py::test_incident_id_resume_fails_closed_when_source_ticket_context_is_missing`。
- [x] projection checkpoint 避免每次全量 JSON replay。证据：`backend/tests/test_replay_resume.py::test_replay_checkpoint_write_read_round_trip`、`backend/tests/test_replay_resume.py::test_resume_with_checkpoint_replays_only_events_after_watermark`、`backend/tests/test_replay_resume.py` checkpoint invalidation 测试、`backend/tests/test_reducer.py::test_replay_checkpoint_payload_matches_reducer_full_replay`、`backend/tests/test_scheduler_runner.py::test_scheduler_resume_checkpoint_path_does_not_repair_projection_rows`。
- [ ] replay 后 doc/materialized view hash 可验证。
- [x] event id resume 正常路径不需要人工补写 projection/index。证据：`backend/tests/test_replay_resume.py::test_resume_normal_path_does_not_touch_projection_repair`，以及 `rg -n "refresh_projections|INSERT INTO .*projection|UPDATE .*projection" backend/app/core/replay_resume.py backend/tests/test_replay_resume.py`。

## Phase 7：015 replay 包验证

- [ ] 能导入 015 replay DB/artifacts。
- [ ] 能定位并重放关键 provider failure。
- [ ] 能重放 BR-032 auth contract mismatch。
- [ ] 能阻断 BR-040/BR-041 placeholder delivery。
- [ ] 能处理 orphan pending 不阻断 graph complete。
- [ ] 能生成 closeout 但必须满足 deliverable contract。
- [ ] 输出新的 replay audit report。

## Phase 8：新 live scenario clean run

- [ ] provider soak 前置通过。
- [ ] 新 live scenario 不需要人工 DB/projection 介入。
- [ ] 所有 source delivery 有非 placeholder source inventory。
- [ ] 所有关键 acceptance 有 evidence refs。
- [ ] final closeout package 合法。
- [ ] 可从中间 checkpoint resume。
- [ ] 最终报告区分 provider noise、runtime bug、product defect。
