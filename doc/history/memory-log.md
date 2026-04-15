# Memory Log

> This file is intentionally compact and no longer part of the default first-read stack. Stable baseline context lives in `doc/history/context-baseline.md`.
> Detailed recent logs now live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`
> - `doc/history/archive/memory-log-detailed-2026-04-03_to_2026-04-06.md`
> - `doc/history/archive/memory-log-detailed-2026-04-07_to_2026-04-10.md`

## How To Use This File

- Read `doc/mainline-truth.md` and `doc/TODO.md` first.
- Open this file only when recent changes still affect implementation decisions.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Current Mainline Truth

- Current executable truth lives in `doc/mainline-truth.md`.
- This file is recent memory, not a second truth source.

## Recent Memory

### 2026-04-15

- `P3-S1` 这轮已完成：`GovernanceProfile` 现已补齐 `auto_approval_scope / expert_review_targets / audit_materialization_policy`，`project-init` 会稳定写默认治理档位；`CompileRequest / CompiledExecutionPackage` 也已显式带 `governance_profile_ref / governance_mode_slice / task_frame / required_doc_surfaces / context_layer_summary`
- `P3-S2` 这轮已完成：`build_ceo_shadow_snapshot()` 现在会稳定产出 `projection_snapshot / replan_focus`；`ceo_prompts / proposer / validator / scheduler / workflow_controller` 已切到新快照合同，缺结构时直接显式失败，不再从旧顶层隐式补读
- `P3-S3` 这轮已完成：新增最小 `skill_runtime`，当前已稳定解析 `implementation / review / debugging / planning_governance` 四类技能；未知 `forced_skill_ids` 或冲突组合会直接拒绝组包，执行包和执行卡片都会带 `skill_binding`
- 当前 `worker_runtime` 和 `context_compiler` 测试夹具也已补齐主线前置：正常执行测试会先显式补 provider binding 和 governance profile，不再靠“未配置 provider / 未写治理档位也能 lease 或 compile”这种旧假设混过
- 本轮 fresh 验证已通过：`backend/tests/test_ceo_scheduler.py -k "snapshot or governance or prompt" -q`、`backend/tests/test_ticket_graph.py -k "ceo_shadow_snapshot" -q`、`backend/tests/test_scheduler_runner.py -k "idle_ceo_maintenance_creates_architect or idle_ceo_maintenance_creates_next_governance_document_ticket" -q`、`backend/tests/test_skill_runtime.py -q`、`backend/tests/test_context_compiler.py -q`、`backend/tests/test_api.py -k "worker_runtime" -q`、`backend/tests/test_ticket_context_archive.py -q`、`backend/tests/test_versioning.py -q`
- `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "ceo_shadow" -q` 当前仍会返回 `51 deselected`；这条不是失败，但也不是有效验证，本轮已改用精确的 `idle_ceo_maintenance_*` 桶替代
- `P2-S5` 这轮已完成：provider unavailable 现在会先写 `TICKET_EXECUTION_PRECONDITION_BLOCKED`，把 ticket/node 固定阻断到 `BLOCKING_REASON_PROVIDER_REQUIRED`；`project-init -> node_ceo_architecture_brief` 不再误走 `TICKET_FAILED -> TICKET_RETRY_SCHEDULED -> REPEATED_FAILURE_ESCALATION`
- `P2-S7` 这轮已完成：`run_ceo_shadow_for_trigger` 现在已经收成严格路径；显式 deterministic mode 继续保留，但 live provider 坏响应、非法 action batch 和执行失败不再隐式 fallback，而是抛 `CeoShadowPipelineError` 并打开 `CEO_SHADOW_PIPELINE_FAILED`
- `P2-S8` 这轮已完成：`command / approval / ticket / idle maintenance` 四类直调入口现在统一走 `trigger_ceo_shadow_with_recovery()`；`incident-resolve` 也新增了 `RERUN_CEO_SHADOW`，恢复时会按 incident 固化的原始 trigger 幂等重跑 shadow
- incident detail / autopilot 推荐动作这轮都已接上 `RERUN_CEO_SHADOW`；当前 `test_p2_ceo_shadow_incident_*` API 桶、`test_ceo_shadow_pipeline_failed*` scheduler 子桶，以及 `workflow_autopilot -k "ceo_shadow or incident"` 都已实跑通过
- `EVENT_INCIDENT_RECOVERY_STARTED` 的 CEO 审计这轮没有继续 incident 化；当前先保持 audit-only best-effort，避免 provider recovery 的 autopilot 主链在恢复中途再递归打开第二条 CEO shadow incident
- `backend/tests/test_ceo_scheduler.py` 这轮已把旧 helper 收成显式步骤：provider 前置、lease/start、源码票、治理文档票、共识票、checker verdict 现在都会显式检查 `status_code + json.status`，不再把 `REJECTED` 当成成功继续往后跑
- 这轮新增了 `TICKET_EXECUTION_PRECONDITION_CLEARED`；scheduler dispatch、`ticket-lease`、`ticket-start` 现在都会走同一套 provider precondition 检查。阻断仍存在时不重复记事件，provider 恢复后会先显式解阻，再恢复正常派发
- 这轮顺手把测试夹具收正到当前 provider center 真相：`backend/tests/test_api.py` 里直接造执行票的 helper 现在会先补最小 provider binding，避免再靠旧的“未配置 provider 也能直接 lease/start”假设混过测试
- 本轮实跑通过 `./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_check_internal_checker_escalated_opens_incident_and_marks_dependency_stop or test_dashboard_pipeline_summary_shows_fused_build_stage_for_open_incident_breaker or test_employee_freeze_containment_opens_staffing_incident_for_executing_ticket or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q`、`python3 -m py_compile backend/app/core/constants.py backend/app/core/reducer.py backend/app/core/ticket_handlers.py backend/tests/test_api.py`
- `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "provider_incident or provider_recovery" -q` 本轮额外复验仍有 5 条失败；当前判断是旧的 env-config / deterministic fallback 测试口径还没迁到 provider center + target binding 真相，这组后续要单列收口，不算本轮 P2-S5 blocker
- `P2-S6` 这轮已完成：`backend/tests/test_scheduler_runner.py` 里的 provider incident / recovery 历史测试现在已经切到 provider center + explicit target binding 真相；auth / bad response / rate limit 断言不再把显式失败包装成 `COMPLETED`
- mainline recovery 的测试入口这轮也已收正成“先补 governance-first 前置，再测 provider 恢复”；不再把 `project-init` 首跳硬写成旧的 `MEETING_ESCALATION` 假设，但仍保留最终要到 `VISUAL_MILESTONE` gate 的主线验收口径
- 本轮新增并实跑通过：`./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "provider_incident or provider_recovery" -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q`、`python3 -m py_compile backend/tests/test_scheduler_runner.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py`
- `P2-S4` 这轮已完成：`review_evidence` 票现在也进入正式 `RoleHook` gate；`delivery_check_report / ui_milestone_review / maker_checker_verdict` 会写最小 `artifact-capture.json`，缺 receipt 时会落 `REQUIRED_HOOK_PENDING:artifact_capture`，不再静默放行下游
- `ticket-result-submit` 这轮已把 review evidence receipt 写回接到成功路径，但不新加第二套 hook 框架；当前继续复用现有 `artifact_capture` receipt、`REQUIRED_HOOK_GATE_BLOCKED` incident 和 `REPLAY_REQUIRED_HOOKS` recovery
- `artifact_capture` replay 这轮已收正成“缺字段 reject、空数组可幂等回放”：`TICKET_COMPLETED.payload` 里只要缺 `artifact_refs` 或 `written_artifacts` 就会显式 `REJECTED` 并保持 incident `OPEN`；字段存在但为空数组时，允许补回最小 receipt，不从正文或目录反推业务状态
- review evidence 依赖 gate 这轮已补真实 API 链路回归：当上游 `delivery_check_report` 缺 `artifact-capture.json` 时，下游 follow-up 票不会被 scheduler 提前放行；本轮实跑通过 `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "hook or incident or graph" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "review_evidence_missing_required_hook_keeps_dependency_gate_blocked" -q`、`python3 -m py_compile backend/app/core/role_hooks.py backend/app/core/ticket_handlers.py backend/tests/test_role_hooks.py backend/tests/test_api.py`
- `./backend/.venv/bin/pytest backend/tests/test_api.py -k "delivery_check_report or ui_milestone_review or maker_checker_verdict" -q` 这轮原样补跑只返回 `286 deselected`；当前仓库没有直接按 schema 名命名的 API 聚合桶，后续如果还想保留这条命令，需要先整理命名或补新的聚合用例
- `P2-S3` 这轮已完成：`structured_document_delivery` 现在也进入正式 `RoleHook` gate；治理文档和 closeout 会写 `artifact-capture.json`，closeout 还会额外写 `documentation-sync.json`
- `REPLAY_REQUIRED_HOOKS` 这轮已从“只补源码票 receipt”扩到“也能补文档票 receipt”：replay 现在只读 `TICKET_COMPLETED.payload.artifact_refs / written_artifacts / documentation_updates`，缺字段会显式 `REJECTED`，incident 保持 `OPEN`
- `TICKET_COMPLETED` payload 这轮新增 `written_artifacts`，这是文档票幂等 replay 的唯一新增真相源；当前实现不会从 Markdown 正文或磁盘目录反推业务状态
- 前端 `IncidentDrawer` 这轮已把 required hook 说明收正成票型无关文案；本轮新增并实跑通过 `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_project_workspace_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "incident or hook or graph" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q`、`cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx`
- 下一轮从 `P2-S4` 起手：先把 `ui_milestone_review / delivery_check_report / maker_checker_verdict` 这些 `review_evidence` 票型按独立 hook 语义接进 gate / replay，再决定旧的 project-init governance/provider incident 噪音是否单列恢复切片
- `P2-S2` 这轮已完成：新增 `backend/app/core/role_hooks.py`，把最小 `RoleHook` registry、结构化 gate result、缺 hook 稳定指纹、`REQUIRED_HOOK_GATE_BLOCKED` incident 和 `REPLAY_REQUIRED_HOOKS` recovery 收成单点协议；当前先只覆盖 `workspace-managed source_code_delivery`
- `TicketGraph` 这轮已开始显式消费 hook gate：源码票缺 `worker_postrun / evidence_capture / git_closeout` 任一 required hook 时，会落 `REQUIRED_HOOK_PENDING:*`，不再把“票已提交”误当成“节点已对下游开放”
- `workflow_auto_advance` 这轮也已接上这条新主链：缺 hook 的源码票会被正式开成 `REQUIRED_HOOK_GATE_BLOCKED`，并按 `workflow_id + ticket_id + node_id + terminal_event_ref + sorted(missing_hook_ids)` 去重；恢复时 `incident-resolve` 会基于持久化 terminal truth 幂等补写缺失 receipt，不能补就 reject 并保持 incident OPEN
- 前端 `IncidentDrawer` 这轮已补 required hook gate 说明和默认 `REPLAY_REQUIRED_HOOKS` 动作；本轮实跑通过 `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_project_workspace_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "incident or hook or graph" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q`、`cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx`
- `./backend/.venv/bin/pytest backend/tests/test_api.py -k "hook or blocked_reason or incident" -q` 这轮仍有 3 条旧的 `project-init` governance/provider incident 历史用例失败；当前额外 incident 仍来自旧 `node_ceo_architecture_brief` provider / auto-advance 噪音，先继续留给 runtime/provider 历史测试收口，不算 `P2-S2` 新 gate 自己的回归
- 下一轮从 `P2-S3` 起手：优先把同一套 hook gate / replay 协议扩到下一类真实主线票型，再决定旧的 project-init governance/provider incident 噪音与其他直调 `run_ceo_shadow_for_trigger` 路径谁先收

### 2026-04-14

- `P2-S1` 这轮已完成：`graph_unavailable` 不再只停在 dashboard 读面；`workflow_auto_advance` 命中 `build_ceo_shadow_snapshot()` 的图快照异常时，会打开正式 `TICKET_GRAPH_UNAVAILABLE` incident，并按 `workflow_id + incident_type + source_component` 去重
- incident 恢复入口这轮已补 `REBUILD_TICKET_GRAPH`：incident detail 会优先推荐该动作，`incident-resolve` 会先同步重建 `TicketGraph`，成功后才关 breaker，失败时 reject 并保持 incident OPEN
- 前端 `IncidentDrawer` 这轮已补图故障说明和默认恢复动作；本轮新增并实跑通过的回归包括：`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_unavailable or rebuild_ticket_graph" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_workflow_autopilot.py -k "graph_unavailable" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q`、`cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx`
- 下一轮从 `P2-S2` 起手：先把 `worker-preflight / worker-postrun / evidence-capture / git-closeout` 这些散点 receipt / validation 收成最小 `RoleHook` registry 和 required hook gate
- `P1-S3` 这轮已完成：`Dependency Inspector` 现在直接消费 `TicketGraph` 边和索引，正式读面新增 `dependency_ticket_ids[] / graph_summary`，不再用 legacy `parent_ticket_id` 自己拼依赖解释
- dashboard 的 blocked 读面这轮已去掉 silent legacy fallback：active workflow 正常时只认 `TicketGraph.index_summary.blocked_node_ids`；图不可用时显式返回 `blocked_node_source=graph_unavailable` 和空 blocked 列表，后续 P2 再接 incident / recovery
- 本轮新增并实跑通过的回归包括：`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "dependency_inspector or dashboard_projection_reuses_ticket_graph_indexes_for_blocked_and_critical_path" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q`、`cd frontend && npm run test:run -- src/App.test.tsx`、`cd frontend && npm run build`
- 进入下一轮时，主计划顶部已切到 `P2 / P2-S1`，但 P2 切片正文还没展开；下一轮先补 P2-S1 正文，再继续实现恢复与 Hook 收口
- `P1-S2` 这轮已完成：`TicketGraphIndexSummary` 现已补齐 `in_flight_ticket_ids / in_flight_node_ids / critical_path_node_ids / blocked_reasons`，controller 和 dashboard 主读面开始共用这层正式图索引
- `workflow_controller` 的 `WAIT_FOR_RUNTIME` gate 现在已从“直扫 ticket status”改成读 `TicketGraph` 的 `in_flight_*` 索引；`ceo_snapshot.ticket_summary.ready_count` 继续沿同一套图索引，不再另算一遍 ready
- dashboard 的 `pipeline_summary.blocked_node_ids / critical_path_node_ids` 与 `ops_strip.blocked_nodes` 这轮已优先读取 active workflow 的 `TicketGraph` 索引；但当 active graph 没给出 blocked node 时，dashboard 仍会临时回退 legacy blocked-node 读面，这个兼容层会直接影响下一轮 `P1-S3`
- 本轮新增并实跑通过的回归包括：`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py backend/tests/test_ceo_scheduler.py -k "in_flight or blocker or summary_without_changing_controller_state or snapshot_exposes_capability_plan_for_backlog_followups or snapshot_requires_next_governance_document_before_backlog_fanout or snapshot_builds_full_dependency_chain_for_next_governance_document or snapshot_treats_any_approved_architect_governance_document_as_gate_satisfied" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "inbox_and_dashboard_reflect_open_approval or dashboard_projection_reuses_ticket_graph_indexes_for_blocked_and_critical_path or board_approve_command_resolves_open_approval or board_reject_command_resolves_open_approval" -q`
- `./backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/ticket_graph.py backend/app/core/ticket_graph.py backend/app/core/workflow_controller.py backend/app/core/projections.py backend/tests/test_ticket_graph.py backend/tests/test_api.py` 本轮已通过
- 额外复验 `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "employee_freeze_containment_opens_staffing_incident_for_executing_ticket" -q` 时，`project-init` workflow 仍会多带一条旧的 provider / auto-advance incident；当前还没证据表明是 `P1-S2` 新回归，先继续留给 runtime/provider 历史测试收口
- `P1-S1` 已落第一段正式 TicketGraph 合同：新增 `backend/app/contracts/ticket_graph.py` 和 `backend/app/core/ticket_graph.py`，当前会把 legacy `ticket_projection / node_projection / ticket create spec` 归约成 `TicketGraphSnapshot / TicketGraphNode / TicketGraphEdge / TicketGraphIndexSummary`
- 当前最小图边只覆盖 `PARENT_OF / DEPENDS_ON / REVIEWS`；`REPLACES / FREEZES / ESCALATES_TO` 还没进正式图合同，后续只能在这层接口上扩，不能再回去加新的旧 projection 直读逻辑
- `ceo_snapshot / workflow_controller` 这轮已开始读 `TicketGraph` 摘要：ready ticket 判定优先走 `index_summary.ready_ticket_ids`，invalid legacy dependency 会显式落 `reduction_issues + blocked_node_ids`，controller 在“有 blocked、没 ready”时会 fail-closed 停住
- `graph_version` 这轮已把 `WORKFLOW_CREATED` 算进 graph mutation event 序列；现在就算 workflow 还没创建 ticket，也能拿到稳定 graph version
- 当前 TicketGraph 为了兼容 legacy maker-checker，同一逻辑 node 下会先用 ticket 级 `graph_node_id` 承载 REVIEWS 边，同时保留原 `node_id` 字段；这会直接影响后续 `P1-S2 / P1-S3` 的图粒度收口
- 本轮新增并实跑通过的回归包括：`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py backend/tests/test_versioning.py -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "snapshot_exposes_capability_plan_for_backlog_followups or snapshot_requires_next_governance_document_before_backlog_fanout or snapshot_builds_full_dependency_chain_for_next_governance_document or snapshot_treats_any_approved_architect_governance_document_as_gate_satisfied" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "test_scheduler_runner_idle_ceo_maintenance_hires_architect_for_controller_gate or test_scheduler_runner_idle_ceo_maintenance_creates_architect_governance_ticket_for_controller_gate or test_scheduler_runner_idle_ceo_maintenance_creates_next_governance_document_ticket" -q`
- `./backend/.venv/Scripts/python.exe -m py_compile backend/app/contracts/ticket_graph.py backend/app/core/ticket_graph.py backend/app/core/versioning.py backend/app/core/workflow_controller.py backend/app/core/ceo_snapshot.py backend/tests/test_ticket_graph.py` 本轮已通过
- `P0-S3` 已落主线 optimistic guard：`CompileRequestMeta / CompiledExecutionPackageMeta` 现在会带 `ticket_projection_version / node_projection_version / source_projection_version`
- `ticket-start` 现在可显式拒绝 stale ticket/node projection version；`ticket-result-submit` 现在可显式拒绝 stale `compiled_execution_package` ref，主线继续保持 fail-closed，不做静默 fallback
- runtime 主线这轮也已开始自发携带新 guard：`run_leased_ticket_runtime` 发出的 `ticket-start / ticket-result-submit` 会带 expected projection version 与 `compile_request_id / compiled_execution_package_version_ref`
- `ticket_context_archives` 这轮已补最小 `P0-S4` 预接线：执行卡片头部现在会展示 `compile_request_id / package version / source projection version`，并支持最小 `stale_against_latest` 检查
- `P0-S4` 这轮已从“预接线”走到第一批正式物化面：新增 `backend/app/core/boardroom_document_materializer.py`，`active-worktree-index.md` 与 ticket dossier 的 `brief.md / required-reads.md / doc-impact.md / git-closeout.md` 现在都走共享 contract、纯 renderer 和原子 writer
- 上述 Boardroom 视图现在统一带 `view_kind / generated_at / source_projection_version / source_refs / stale_check_key`；harness 还没接这套协议，但后续如果要接，只能复用这层 contract，不能再写第二套正文格式
- `doc-impact.md` 这轮已收正到只读 `worker-postrun` receipt：没有 receipt 时明确展示 `not_reported`，有 receipt 时只展示真实 `documentation_updates`，手工改坏正文后再次 sync 会整份重算覆盖
- `git-closeout.md` 这轮不再由 `update_ticket_git_closeout_notes()` 直接手写 Markdown；该函数现在只更新结构化事实输入，ticket start / result submit / review gate merge / closeout rejection 这些触点都会再触发 Boardroom 视图重算
- 本轮新增并实跑通过的回归包括：`./backend/.venv/bin/pytest backend/tests/test_boardroom_document_materializer.py -q`、`./backend/.venv/bin/pytest backend/tests/test_project_workspaces.py backend/tests/test_project_workspace_hooks.py -k "boardroom or dossier or worktree or doc_impact or git_closeout" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_context_archive.py -q`
- `python3 -m py_compile backend/app/core/boardroom_document_materializer.py backend/app/core/project_workspaces.py backend/app/core/ticket_handlers.py backend/app/core/approval_handlers.py backend/tests/test_boardroom_document_materializer.py backend/tests/test_project_workspaces.py backend/tests/test_project_workspace_hooks.py` 本轮已通过
- `closeout / approval` 历史 API 桶这轮也已收口到显式 manual chain：`scope approval -> build maker/checker -> check maker/checker -> review maker/checker -> final review -> closeout maker/checker`
- synthetic manual `scope review -> closeout` 链当前不会自动产出 dashboard `completion_summary`；这条链继续只验证 ticket/node/artifact/process-asset 真相，dashboard summary 继续交给 autopilot / closeout 专项测试覆盖
- 本轮新增并实跑通过：`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "test_board_approve_scope_review_creates_followup_ticket_and_advances_to_visual_review or test_final_review_approval_creates_closeout_ticket_and_completion_summary_uses_closeout_fields or test_closeout_internal_checker_approved_returns_completion_summary" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "test_final_review_approval_rejects_when_review_gate_merge_conflicts or test_completion_summary_handles_missing_closeout_documentation_updates or test_closeout_internal_checker_changes_required_creates_fix_ticket_and_blocks_completion or test_completion_summary_returns_null_source_delivery_summary_when_closeout_lacks_source_delivery_asset" -q`、`./backend/.venv/Scripts/python.exe -m py_compile backend/tests/test_api.py backend/tests/test_ceo_scheduler.py`
- 本轮新增并实跑通过的回归包括：`./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k "version or stale or compile" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "stale_board_command or board_command_is_rejected_when_projection_is_not_currently_blocked or stale_projection_version_guard or stale_compiled_execution_package_version_ref" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_context_archive.py -q`、`./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "runtime_uses_openai_compat_provider_when_configured" -q`
- 宽口径 `./backend/.venv/bin/pytest backend/tests/test_api.py -k "board_approve or stale_board_command or projection_guard or stale_projection_version_guard or stale_compiled_execution_package_version_ref" -q` 当前仍会命中一组旧的 governance/provider auto-advance 用例；scope review 批准后会在 `node_ceo_architecture_brief` 打开 `PROVIDER_REQUIRED_UNAVAILABLE -> REPEATED_FAILURE_ESCALATION`，这块后续要和 runtime/provider 历史测试一起收口
- `P0-S2` 已落最小版本协议骨架：新增 `backend/app/core/versioning.py` 统一 process asset canonical ref、compiled artifact version ref、`GovernanceProfile` id 和 workflow graph version helper
- `ProcessAssetReference / ResolvedProcessAsset` 现在会带 `canonical_ref / version_int / supersedes_ref`；新写入结果统一落 versioned ref，旧短 ref 只保留 resolver 入口兼容
- `compiled_context_bundle / compile_manifest / compiled_execution_package` 这轮已改成 append-only 版本化持久化；repository 现在可按 `ticket_id + version_int` 查询，并在 persisted payload 里写入版本与 supersede 关系
- 最小 `GovernanceProfile` 现在已具备 append-only 存储、latest 查询和 supersede 链追溯；本轮只补骨架和只读入口，还没把 `approval_mode / audit_mode` 全面接进 runtime
- workflow graph version 当前已按最保守口径落成 repository helper：基于 graph mutation event 的最新 `sequence_no` 推导 `gv_<int>`，缺失时 fail-closed；后续 `P1` 再决定是否升级成正式图真相字段
- 本轮新增并实跑通过的回归包括：`./backend/.venv/bin/pytest backend/tests/test_process_assets.py backend/tests/test_versioning.py backend/tests/test_context_compiler.py -k "version or governance_profile or graph_version or process_asset" -q`、`./backend/.venv/bin/pytest backend/tests/test_process_assets.py backend/tests/test_context_compiler.py backend/tests/test_repository.py backend/tests/test_project_workspace_hooks.py -k "version or governance or compile or process_asset" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "governance_document or compile or process_asset" -q`
- `P0-S1` 已落最小启动协议：`repository.initialize()` 现在会幂等写入单条 `SYSTEM_INITIALIZED`，系统冷启动和 `project-init` 不再绑在一起
- `project-init` 这轮已删掉系统初始化写入，职责收回到纯 workflow 启动；空态 dashboard 和事件流现在就算没有 workflow，也能直接看到初始化真相
- 本轮新增并实跑通过的回归包括：`./backend/.venv/bin/pytest backend/tests/test_api.py -k "system_initialized or startup or invalid_project_init" -q`、`./backend/.venv/bin/pytest backend/tests/test_repository.py -k "initialize" -q`
- `./backend/.venv/bin/pytest backend/tests/test_api.py -k "system_initialized or startup or project_init" -q` 当前仍会命中一组依赖 live provider 的旧 `project-init` 自动推进用例；当前环境未配 provider 时会报 `PROVIDER_REQUIRED_UNAVAILABLE`，这块后续要和 runtime/provider 测试收口一起处理

### 2026-04-13

- 已按 `doc/tests/integration-audit-remediation-master-plan-20260413.md` 落第一批执行切片，只收 `P0-2 / P0-3 / P1-3`
- `source_code_delivery@1` 现在必须带 `source_files[] / verification_runs[]`；旧的“只交 `source_file_refs[]` + 占位源码 + 一句 `pytest -q passed`”已经被 schema 和 workspace hook 一起拦掉
- workspace-managed 代码票的测试证据和 git 证据现在会按 `20-evidence/tests/<ticket>/attempt-1/`、`20-evidence/git/<ticket>/attempt-1/` 分路径，不再继续写固定 `test-report.json / git-commit.json`
- live harness full success 现在也会把 `source_code_delivery` payload 质量和 `artifact_index` 证据路径撞车一起纳入断言
- 第二批执行切片也已落：shared harness 现在会自动生成正式版 `audit-summary.md` 和去重后的 `integration-monitor-report.md`，场景根目录不再依赖人工手记才看得懂
- governance JSON 现在会自动旁挂同名 `.audit.md`；`ticket_context_archives/*.md` 也已经从 preview dump 改成执行卡片，直接展示上下文来源、token 预算、降级告警、checkout / branch 和实际 artifact 路径
- 本轮已实跑通过的回归集中在 `test_output_schemas.py`、`test_project_workspace_hooks.py`、`test_runtime_fallback_payload.py`、`test_live_library_management_runner.py`、`test_workflow_autopilot.py`
- 本轮新增实跑通过的回归还包括：`test_ticket_context_archive.py`
- `test_api.py` 和 `test_scheduler_runner.py` 里那批依赖旧 deterministic 主线的历史测试，当前仍会被 provider fail-closed 链路打断；这批不是本轮第一批或第二批新引入，但后续继续推进前要单独收口

### 2026-04-11

- 当前已新增 `workflow_progression` shared abstraction：`AUTOPILOT_GOVERNANCE_CHAIN / STANDARD_LEGACY_SCOPE_CHAIN` 两个 adapter 现在开始承接 kickoff、requirement elicitation 后续 kickoff、controller 下一步判断，以及 standard scope follow-up 选路
- `CEO_AUTOPILOT_FINE_GRAINED` 当前已切 governance-first：治理链未走完时，snapshot 会暴露 `task_sensemaking=governance_followup`、`deliverable_kind=structured_document_delivery`、`coordination_mode=document_chain`，controller state 也会切到 `GOVERNANCE_REQUIRED`
- `required_governance_ticket_plan` 当前不再只补 architect `architecture_brief`；它现在也会表示下一张治理文档票，最小覆盖 `technology_decision / milestone_plan / detailed_design / backlog_recommendation`
- `STANDARD` 这轮也已切到 governance-first：project-init 会稳定创建 `node_ceo_architecture_brief / tkt_<workflow>_ceo_architecture_brief`，requirement elicitation 回流、controller、deterministic fallback 和 validator 现在都共用这条治理链真相
- legacy scope follow-up 这轮没有被硬删：它只退出了 `STANDARD project-init` 主线，继续保留给非 autopilot 的手工 `consensus_document` 兼容链
- 已完成真实 closeout 的 autopilot workflow，controller 不会再被 governance-first 补票重新拉起
- 当前测试环境如果跑在 Git linked worktree 里，`backend/tests/conftest.py` 会自动把 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT` 改到系统临时目录，避免测试里再建项目 worktree 时触发 Git 的 `$GIT_DIR too big`
- `project-init` 现在会在 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT/<workflow_id>/` 下创建受管项目工作区，固定三分区 `00-boardroom / 10-project / 20-evidence`；第一版支持 `AGILE / HYBRID / COMPLIANCE`
- `ticket-create` 现在会自动补 `project_workspace_ref / project_methodology_profile / deliverable_kind / canonical_doc_refs / required_read_refs / doc_update_requirements / git_policy`，并为 workspace-managed ticket 创建 dossier
- `Context Compiler` 现在会把 `required_read_refs` 并入 `input_process_asset_refs`，并给 workspace-managed ticket 写 `worker-preflight` 回执
- BUILD 主结果现在已经从占位式文档产物硬切到 `source_code_delivery`；deterministic / provider-backed runtime 都会直接落源码写入、测试证据、git 留痕和 `SOURCE_CODE_DELIVERY` 过程资产
- workspace-managed `source_code_delivery` 票现在会在 `ticket-result-submit` 时硬校验 `source_file_refs / documentation_updates / verification_evidence_refs / git_commit_record`，并写 `worker-postrun / evidence-capture / git-closeout` 回执
- architect gate 这轮已从“只阻断”推进到“可补票”：当 `architect_primary` 已在岗但还没有过 governance gate 的文档时，controller 现在会暴露 `required_governance_ticket_plan`，deterministic fallback 会优先创建一张稳定 node_id 的 `architect_primary + architecture_brief` 治理票
- architect gate 的满足口径这轮也已放宽：`architecture_brief / technology_decision / detailed_design` 任一已过 internal governance gate 的 `architect_primary` 文档都算满足，不再只认 `architecture_brief`
- 本轮已补 deterministic 回归和 live 脚本断言，要求最终结果里能看见已过 governance gate 的 architect 文档证据；但当前还没有在这台机器上重跑真实 live provider 长测
- 当前还没做完的点：Review Gate merge 自动化、closeout 统一 gate、非代码票硬 gate，以及 completion / projection 对源码文件数、测试证据数和 git 摘要的当前读面
- 后端当前全量回归基线已更新为 `555 passed`

### 2026-04-10

- `python -m tests.live.library_management_autopilot_live` 这条真实 LLM 长测已经证明：当前主线虽然能跑到 closeout，但 `BUILD` 仍会退化成“文档式 artifact 交付”，不是“真实源码交付”
- 当前最高优先级已切到 `P0-COR`：canonical 协议、单一 workflow controller、architect/meeting/source-code deliverable 硬约束，以及源码交付 contract / checker / closeout 硬门禁
- 这条 live 场景的留档仍在 `backend/data/scenarios/library_management_autopilot_live/`，需要复盘真实上下文时优先看这里，不要回看旧计划文档
- `doc/` 根目录的旧 spec、旧计划和旧分析已迁到 `doc/archive/`；高频入口现在只保留当前真相层
- `doc/task-backlog/active.md` 已重写为“只保留未关闭任务”，已完成流水统一留在 `doc/task-backlog/done.md`

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, and `doc/TODO.md` first.
- Open `doc/history/context-baseline.md` only when stable rules matter, and open this file only when recent changes matter.
- Keep only facts that still change implementation decisions here; move raw logs and exhaustive verification into archive files.
