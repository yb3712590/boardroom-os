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

Round 9A 已完成最小 contract/evaluator skeleton，Round 9B 已完成 source surface / evidence pack 映射，Round 9C 已完成 checker/convergence gate，Round 9D 已完成 upstream rework target routing，Round 9E 已完成 closeout contract/final evidence table 收口：

- `backend/app/core/deliverable_contract.py` 定义版本化 `DeliverableContract`、`DeliverableEvaluation` 和 `ContractFinding`。
- `compile_deliverable_contract()` 可从结构化 PRD / charter / ticket acceptance 输入编译 contract。
- `compile_deliverable_contract()` 可从 locked scope、governance/design/backlog assets 和 allowed write set metadata 编译 required source surfaces。
- `EvidencePack` / `EvidenceItem` 映射 source/test/check/git/closeout evidence 到 acceptance criteria、source surface、producer ticket/node 和 artifact legality。
- `evaluate_deliverable_contract()` 是纯函数 evaluator；9A 覆盖 missing acceptance、missing required evidence、unknown evidence kind 和 empty final evidence，9B 覆盖 invalid evidence、placeholder/source-test fallback、acceptance 缺 required source/test/check/git/closeout evidence。
- Round 9C 已把 checker verdict gate 接到 `DeliverableEvaluation`，并要求 failed delivery report 只有结构化 `ConvergencePolicy` 才能放行。
- Round 9D 已把 blocking `ContractFinding` 编译成 Phase 4 recovery input，rework target 指向 source surface / producer ticket / producer node，缺 current producer 时输出 incident，不默认回 checker、graph terminal 或 closeout。
- Round 9E 已把 closeout package 放行改为消费 contract version/id、evaluation fingerprint 和 final evidence table；`final_artifact_refs` 仅保留为 input compiler / API display 兼容字段。

任务：

- [x] 将 PRD acceptance 编译为 deliverable contract（Round 9A skeleton）。
- [x] 建立稳定 contract id、finding id 和 evaluation fingerprint（Round 9A skeleton）。
- [x] 将 required source surfaces 映射到 capability write surfaces 和 required evidence kinds（Round 9B）。
- [x] 将 evidence pack 映射到 acceptance criteria，并拒绝 superseded/placeholder/archive/unknown/stale pointer evidence（Round 9B）。
- [x] checker verdict 与 deliverable contract 解耦（Round 9C）。
- [x] rework target 指向能修问题的 upstream node（Round 9D）。
- [x] `APPROVED_WITH_NOTES` 不得覆盖 blocking contract gap（Round 9C）。
- [x] closeout package 包含 contract version/id、evaluation fingerprint 和 final evidence table（Round 9E）。
- [x] final evidence set 只接受 current graph pointer 下的合法 final evidence，并拒绝 superseded/placeholder/archive/unknown/stale/governance/backlog refs（Round 9E）。

验收：

- [x] placeholder source/evidence 不能通过 contract evaluator。
- [x] failed delivery report 有结构化 convergence policy 才能放行。
- [x] final evidence set 不包含 superseded/old placeholder/governance/backlog/stale 资产。
- [x] checker verdict、failed delivery report、graph terminal 和 manual closeout recovery 不能绕过 deliverable contract satisfaction。

Round 9B/9C 证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py -q` -> `34 passed`。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_autopilot.py -q` -> `42 passed, 1 warning`。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework backend/tests/test_api.py::test_structured_convergence_policy_allows_failed_check_report -q` -> `3 passed`。

Round 9D 证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_progression.py -q` 覆盖 upstream source node、missing test evidence、checker-only defect、missing current producer incident、controller recovery input 和 BR-040/BR-041 placeholder 等价。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework -q` 覆盖 failed delivery checker rework upstream target。

Round 9E 证据：

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py backend/tests/test_output_schemas.py -q` 覆盖 PRD acceptance compiler、source surface path/capability/evidence mapping、evidence pack -> acceptance mapping、closeout package contract fields、final evidence table 行字段、superseded/placeholder/archive/unknown/stale/governance/backlog refs 排除。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_autopilot.py backend/tests/test_workflow_progression.py -q` 覆盖 closeout contract/table gate、stale old attempt 排除、governance/backlog 混入 final refs 拒绝、graph terminal 不能替代 contract satisfaction、closeout proposal 需要 contract satisfied 且 final table 非空。
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_closeout_internal_checker_approved_returns_completion_summary backend/tests/test_api.py::test_manual_closeout_recovery_cannot_bypass_contract_table backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework backend/tests/test_api.py::test_structured_convergence_policy_allows_failed_check_report -q` 覆盖 closeout package contract fields、manual closeout recovery、failed delivery checker rework、无结构化 convergence policy 不放行、结构化 convergence policy 放行。
- `rg -n "graph terminal|checker notes|freeform|final_artifact_refs.*satisf" backend/app/core` 用于确认旧 freeform / graph terminal / final refs satisfaction 路径未保留为放行依据。
- `rg -n "_delivery_closeout_final_artifact_refs|classify_closeout_final_artifact_ref|evaluate_deliverable_contract|final_evidence_table" backend/app/core` 用于确认保留 helper 的边界为 input compiler / evaluation helper / API display，并确认 contract evaluator / final table 为主路径。

015 映射：

- BR-040、BR-041 placeholder delivery：Round 9D/9E 结构化等价覆盖在 `backend/tests/test_deliverable_contract.py`、`backend/tests/test_workflow_progression.py` 和 `backend/tests/test_workflow_autopilot.py::test_closeout_gate_rejects_placeholder_final_artifact_ref`；完整 015 replay 归 Phase 7。
- BR-100 final checker 长循环：Phase 4 结构化 threshold 等价已由 `backend/tests/test_workflow_progression.py` 覆盖；完整 015 replay 归 Phase 7。
- closeout final refs 混入治理文档 / backlog recommendation：Round 9E 覆盖 `test_closeout_gate_rejects_illegal_final_artifact_ref_kind`、`test_closeout_gate_rejects_backlog_recommendation_final_artifact_ref_kind` 和 deliverable final table governance/backlog exclusion。
- manual closeout recovery：Round 9E 覆盖 `backend/tests/test_api.py::test_manual_closeout_recovery_cannot_bypass_contract_table`；真实 015 replay 仍归 Phase 7。

下一入口：Round 11A 015 replay import harness。Round 10A 已建立 Replay resume contract 与 event cursor；Round 10B 已实现 graph version resume，并证明 graph version resume 与同一事件集 full replay 的 effective graph pointer / projection summary 等价；Round 10C 已实现 ticket / incident resume；Round 10D 已建立 projection checkpoint 和 invalidation；Round 10E 已建立 artifact hash manifest 与 replay bundle report，可验证 artifact index / materialized storage 的 content hash；Round 10F 已把 document materialized view hash 接入同一 replay bundle/report，并从 event/process asset/artifact metadata/content 重新物化 document view。Phase 7 的 015 full replay import 和 case 验证从 Round 11A 开始。

## Phase 6：Replay / resume / checkpoint 重建

目标：replay/resume 成为一等操作。

任务：

- Round 10A：已建立 `ReplayResumeRequest` / `ReplayWatermark` / `ReplayResumeResult`、event id cursor 恢复入口、稳定 watermark hash 和 fail-closed diagnostic。
- Round 10B：已在同一 contract 上增加 `graph_version` resume kind；`gv_<event sequence_no>` 映射到明确 event range / projection version / replay watermark，并从 event log 重放后重算 effective graph pointer、ready/blocked/complete index。
- Round 10C：已在同一 contract 上增加 `ticket_id` / `incident_id` resume kind；两者默认恢复到最新 event 或显式 event cursor，并复用 replay watermark / projection version / event range / diagnostic 语义。
- Round 10C：ticket resume 从 event log 重建 projection 后保留 terminal/in-flight 状态、runtime node view、assignment/lease context、current graph pointer 和 related artifact/evidence/process asset refs。
- Round 10C：incident resume 保留 incident status、source ticket context、followup action、incident/recovery action lineage 和 Phase 4 `recovery.actions` 形状的 rework/restore policy input。
- Round 10C：缺 ticket、缺 incident、source ticket 不一致、source ticket 缺失、runtime node view 断裂都会 fail-closed。
- Round 10D：已定义 `ReplayCheckpoint`，字段覆盖 checkpoint id/version、event watermark、projection version、schema version、contract version、invalidated_by、created_at、hash、covered projections、compatibility 和 projection payloads。
- Round 10D：checkpoint 存储边界为 `replay_checkpoint` 表，保存 checkpoint JSON；正常 resume 不手写 projection/index row，也不调用 projection repair。
- Round 10D：`resume_replay_with_checkpoint()` 复用 10A–10C 四类 resume contract。有效 checkpoint 从 checkpoint watermark 后增量 replay；无效 checkpoint 默认 fail-closed，只有显式 `allow_full_replay_fallback=True` 才 full replay fallback 并写 diagnostic。
- Round 10D：schema version、contract version、projection version、event watermark、checkpoint hash、covered projection set 和 compatibility mismatch 都会输出 checkpoint invalidation diagnostic。
- Round 10E：已定义 `ReplayHashManifest` / `ReplayBundleReport`，字段覆盖 source event range、checkpoint refs/watermark、resume source、projection version、artifact refs、storage refs、content hash、materialization status、diagnostics 和 replay compatibility。
- Round 10E：artifact hash verifier 只读取 `artifact_index` 与已登记 storage bytes 重算 sha256；缺 artifact、缺 content hash、缺 storage ref、storage read failed 或 hash mismatch 都 fail-closed，不人工补写 materialized files。
- Round 10F：已定义 `boardroom-document-view.v1`，document materialized view section 列出 source event range、process asset refs、artifact refs、document refs、content hash 和 diagnostics。
- Round 10F：document view 只从 replay 后的 `process_asset_index`、artifact metadata 和已登记 artifact storage content hash 重新物化；不读取手工补写 markdown 或 workspace receipt 作为恢复输入。
- Round 10F：缺 artifact、非法 process asset、非 CONSUMABLE lineage、linked process asset 缺失、artifact storage/hash mismatch 都 fail-closed。
- replay bundle materializer 已覆盖 artifact hash manifest 与 document materialized view hash。
- 禁止人工投影补写作为正常路径。

验收：

- resume from event id 已由 `backend/tests/test_replay_resume.py` 覆盖；正常路径不调用 projection repair。
- 从中间 graph version 恢复不需要人工 DB/projection 注入；`backend/tests/test_replay_resume.py` 覆盖 graph version watermark、full replay equivalence、orphan pending/effective edge、late old attempt / late old cancellation 不改 current pointer 语义，以及缺失/断层/event range mismatch/hash missing/hash mismatch/projection rebuild failed fail-closed。
- 从 ticket id / incident id 恢复不需要人工 DB/projection 注入；`backend/tests/test_replay_resume.py` 覆盖 ticket terminal/in-flight、runtime node view、assignment/lease、related refs、incident source ticket、followup/recovery lineage 和缺上下文 fail-closed。
- Projection checkpoint 避免每次全量 JSON replay；`backend/tests/test_replay_resume.py` 覆盖 checkpoint write/read、增量 replay event count/starting cursor、schema/version/hash/watermark/projection set/compatibility invalidation、stale checkpoint fail-closed 和显式 full replay fallback；`backend/tests/test_reducer.py` 覆盖 checkpoint payload 与 reducer full replay projection 等价；`backend/tests/test_scheduler_runner.py` 覆盖 scheduler/resume checkpoint 正常路径不调用 projection repair。
- replay 后 artifact hash 可验证；`backend/tests/test_replay_resume.py::test_replay_hash_manifest_verifies_materialized_artifact_storage` 覆盖 materialized storage hash，`test_replay_hash_manifest_fails_closed_when_artifact_missing`、`test_replay_hash_manifest_fails_closed_when_storage_hash_mismatches`、`test_replay_hash_manifest_fails_closed_when_materialized_storage_ref_unregistered` 覆盖 fail-closed，`test_replay_bundle_report_includes_resume_checkpoint_artifacts_and_diagnostics` 覆盖 replay bundle report。
- replay 后 document/materialized view hash 可验证；`backend/tests/test_boardroom_document_materializer.py` 覆盖正常、缺 artifact、非法 process asset 和非法 evidence lineage fail-closed；`backend/tests/test_replay_resume.py::test_replay_hash_manifest_includes_materialized_document_view_hash`、`test_replay_document_view_hash_matches_full_rematerialization`、`test_replay_bundle_report_includes_resume_checkpoint_artifacts_and_diagnostics` 覆盖 hash manifest/report 接入和 full rematerialization hash 稳定。

## Phase 7：015 replay 包验证

目标：用 `boardroom-os-replay` 作为回归靶场。

任务：

- [x] Round 11A：导入 015 replay 包。已新增 `ReplayImportManifest`、read-only source DB import harness 和 CLI；source DB 用 SQLite `mode=ro` 打开，目标 DB 从 events reducer 重建 projection，只复制 `artifact_index` metadata，不复制 source projection rows。
- [x] Round 11B：定位并重放 015 provider failure。已新增 `ReplayCaseResult`、只读 provider replay harness 和 CLI；case `provider-failure-015-malformed-sse` 继承 11A manifest，读取导入 DB，不修改 replay source DB、projection、event 或 artifact。
- [x] Round 11C：重放 BR-032 auth contract mismatch 和 BR-040/BR-041 placeholder delivery。已新增只读 contract gap replay harness 和 CLI；三条 case 均继承 11A manifest 与 11B provider 边界，只消费 `events`、`artifact_index`、`process_asset_index`，不读取 raw transcript / late output / artifact 正文，不修改 replay DB/projection/event。
- [x] Round 11D：重放 graph/progression orphan pending、CANCELLED/SUPERSEDED effective edge、late provider current pointer 和 missing explicit pointer。已新增只读 graph/progression replay harness 和 CLI；四条 case 继承 11A manifest、11B provider late guard 和 11C contract gap boundary，只消费 `events`，不读取 source projection，不修改 replay DB/projection/event。
- 重放关键 incident/rework/closeout 路径。
- 验证 placeholder、orphan pending、provider late event、manual closeout recovery 都被新规则处理。

验收：

- [x] Round 11A import harness 无人工 DB/projection/event 注入。证据：`python -m app.replay_import_cli ... --manifest-out D:/Projects/boardroom-os/.pytest-tmp/replay-import-015/replay-import-manifest.json` 输出 `READY`；重复导入使用 `--expected-manifest` 仍输出同一 `manifest_hash=8438fb6aed8e2daa32e90fd19ed171cb1691f06ebe5f0194e20f9e33ccda9d53` 和 `idempotency_key=replay-import:3a209b15acc022ff85a35f27efa4f5857f3151d51aaaf391dd7408cf866332b8`。
- closeout 不能绕过 deliverable contract。
- 输出 replay audit report。

Round 11A 证据边界：

- 已导入 event range `1..15801`、`artifact_index=362`、`process_asset_index=393`；目标 DB event count 为 `15801`。
- 输入 hash：DB `4094836432b17030d21f0d0b1fbf7c19c935940f9912e288fc9079a748610fcf`，artifact tree `336d1ab44e01e1ae77a516b577bb3072a30660bb41441d7607d8b0aca7358061`，registered artifact tree `ea5cbd11ab7aa49e4bf6f155ba882d2f5edddf59b42a217844a4ed7a8296410f`，event log `56a621cc7f57e5879cc76d89eb5e74eff44d9522306a57292d7ac83804fe7320`，artifact index `d220f1d58db2623c268a1116fee63c08b1414b044c462ba4617b807f6fc8908f`。
- Import diagnostics 只归类为 `replay/import issue`：AppleDouble / `PaxHeader` archive metadata、未登记 artifact root 文件、mutable workspace storage path、`INLINE_DB` artifact、source projection mismatch。
- Round 11A 没有验证 provider failure、BR-032、BR-040/BR-041、orphan pending、graph/progression 或 closeout；这些从 Round 11B 开始依赖 11A manifest 的 event range、hash、artifact refs 和 diagnostics。

Round 11B provider replay 证据边界：

- Case result path：`D:/Projects/boardroom-os/.pytest-tmp/replay-provider-015/replay-case-result.json`。
- Case id：`provider-failure-015-malformed-sse`；event range `9969..10016`；失败票 `tkt_0c616378c9ac`；核心事件 `9995 PROVIDER_ATTEMPT_FINISHED` / `9996 TICKET_FAILED`。
- Attempt ref：`attempt:wf_7f2902f3c8c6:tkt_0c616378c9ac:prov_openai_compat_truerealbill:1`，事件 `9973` / `9995`，provider policy ref `provider-policy:prov_openai_compat_truerealbill:gpt-5.5:xhigh:openai_compat`。
- Observed failure kind：`PROVIDER_BAD_RESPONSE`；expected malformed taxonomy：`MALFORMED_STREAM_EVENT`。真实旧数据缺 `raw_archive_ref`，`raw_archive_refs=[]`，diagnostics 为 `provider_raw_archive_ref_missing` 和 `provider_failure_taxonomy_legacy_bad_response`，classification 为 `replay/import issue`。
- Provider provenance：preferred/actual provider 均为 `prov_openai_compat_truerealbill`，preferred/actual model 均为 `gpt-5.5`。
- Retry/recovery：只用结构化 failure detail、ticket terminal、retry 和 incident recovery 事件得出 `retried_and_completed`；`10007 TICKET_RETRY_SCHEDULED` -> `tkt_2b58304dccb9`，`10009 INCIDENT_RECOVERY_STARTED` 使用 `RESTORE_AND_RETRY_LATEST_FAILURE`，`10016 TICKET_COMPLETED` 完成恢复票。
- Late guard：旧票 `tkt_30c7a10979ae` 在 `9967 TICKET_FAILED` 后的 late provider events 只保留 lineage；case range 内 current pointer source 为 `case_range_terminal_events`，current ticket 为 `tkt_2b58304dccb9`。Harness 明确记录 `raw_transcript_used=false`、`late_output_body_used=false`、`timestamp_pointer_guess_used=false`。
- Phase 7 provider checkbox 仍保持未勾：11B 证明关键 provider failure 可定位和重放，也证明真实 015 旧数据不能提供 raw archive contract 成功证据。11C 从 Contract gap replay 开始，不得用 provider raw transcript 或 late output 正文弥补 BR contract gap。

Round 11C contract gap replay 证据边界：

- Case result paths：`D:/Projects/boardroom-os/.pytest-tmp/replay-contract-gap-015/br032.json`、`br040.json`、`br041.json`。
- BR-032：`contract-gap-015-br032-auth-mismatch`，event range `5855..6299`，checker report `art://runtime/tkt_bc0404503ec8/delivery-check-report.json` 保留 blocking `BR032-F06`；`APPROVED_WITH_NOTES` 不能覆盖 blocker，policy proposal 为 `progression.rework.deliverable_contract_gap`，target 为 `tkt_c247833b2c60` / `node_backlog_followup_br_031_m3_frontend_auth_nav`。
- BR-040：`contract-gap-015-br040-placeholder-delivery`，event range `11400..11464`，placeholder refs 为 `art://workspace/tkt_2252a7a1f92e/source.py`、`art://workspace/tkt_2252a7a1f92e/test-report.json`、`pa://source-code-delivery/tkt_2252a7a1f92e@1`、`pa://evidence-pack/tkt_2252a7a1f92e@1`；被 `invalid_evidence_for_contract` / `acceptance_missing_required_evidence` 阻断，target 为 `tkt_2252a7a1f92e`。
- BR-041：`contract-gap-015-br041-placeholder-delivery`，event range `9933..10016`，placeholder refs 为 `art://workspace/tkt_5707c310bc6d/source.py`、`art://workspace/tkt_5707c310bc6d/test-report.json`、`pa://source-code-delivery/tkt_5707c310bc6d@1`、`pa://evidence-pack/tkt_5707c310bc6d@1`；被 `invalid_evidence_for_contract` / `acceptance_missing_required_evidence` 阻断，target 为 `tkt_5707c310bc6d`。
- 三条 case 均记录 `graph_terminal_override_used=false`、`raw_transcript_used=false`、`late_output_body_used=false`、`timestamp_pointer_guess_used=false`。下一入口为 Round 11D Graph / progression replay，不开始 closeout 或 audit 收口。

Round 11D graph/progression replay 证据边界：

- Case result paths：`D:/Projects/boardroom-os/.pytest-tmp/replay-graph-progression-015/orphan-pending.json`、`cancelled-superseded.json`、`late-provider-pointer.json`、`missing-explicit-pointer.json`。
- Orphan pending：`graph-progression-015-orphan-pending-br060`，event range `11791..11903`；`tkt_262f159fc931` 不进入 ready/current/effective complete，current pointer 为 `tkt_5d8e536a14c2` 和 review `tkt_665d647e556a`；policy reason code `progression.stale_orphan_pending_ignored`，source graph version `gv_11903`，affected refs `["tkt_262f159fc931"]`。
- CANCELLED/SUPERSEDED：`graph-progression-015-superseded-cancelled-br032`，event range `5960..6299`；`tkt_ade5951f10ec`、`tkt_2262491ff9ae`、`tkt_e2b36aef19e9` 不进入 effective edges/readiness/current/completed refs；current pointer 保持 `tkt_c247833b2c60`、`tkt_f00a95436db3`、`tkt_2e4ac9dd357e`、`tkt_1b2b27220047`。
- Late provider pointer：`graph-progression-015-late-provider-current-pointer-br041`，event range `9969..10016`；late provider output 不改 current pointer，current 为 `tkt_2b58304dccb9`，`timestamp_pointer_guess_used=false`。
- Missing explicit pointer：`graph-progression-015-missing-explicit-pointer`，event range `11791..11903`；缺 explicit runtime pointer 时生成 `graph.current_pointer.missing_explicit` 和 `progression.incident.graph_reduction_issue`，不按 ticket `updated_at` 猜 current。
- 四条 case 均为 `READY`，issue classification 为 `graph progression replay evidence`。下一入口为 Round 11E Closeout replay 与 audit report。

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
