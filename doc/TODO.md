# TODO

> 最后更新：2026-04-17
> 本文件仍是项目唯一的待办真相源，但正文只保留当前批次与条件批次。已完成能力改看 `todo/completed-capabilities.md`，远期储备改看 `todo/postponed.md` 与 `milestone-timeline.md`。

## 当前阶段目标

先把项目从“文档式 artifact 交付闭环”收正成一个本地单机可运行、可验证、可演示，而且真正产出源码的 Agent Delivery OS MVP：

- canonical 协议是真相源，CEO action、provider config、runtime result、ticket deliverable 不再多口径并存
- 单一 workflow controller 推进工作，scheduler / CEO / fallback 不再各自维护主线语义
- BUILD / CHECK / CLOSEOUT 必须交真实源码、测试和构建证据，不再只交 artifact JSON
- architect / meeting / source-code deliverable 是主线硬约束，不再只是“允许发生”
- React 只做最薄治理壳，不接管工作流真相

## 当前基线（最后一次静态验证：2026-04-09；2026-04-10 live 长测新增主线偏差）

- backend：`./backend/.venv/bin/pytest tests/ -q` -> `555 passed`
- frontend：`npm run build` -> passed，`npm run test:run` -> `84 passed`
- CEO 当前真实执行集：`CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / REQUEST_MEETING`；`ESCALATE_TO_BOARD` 仍是 `DEFERRED_SHADOW_ONLY`
- 2026-04-10 live 集成测试新增确认：当时主线虽然能跑到 closeout，但 BUILD 还在交占位式文档产物，不是真实源码交付；这也是 `P0-COR` 被提升为最高优先级的直接原因
- 2026-04-11 第二段纠偏已落地：`BUILD` 主结果已经硬切到 `source_code_delivery`，workspace-managed staged follow-up build 也已改成 `10-project / 20-evidence` write set；runtime 会落源码写入、测试证据、git 留痕和 `SOURCE_CODE_DELIVERY` 过程资产
- 2026-04-11 第三段纠偏已落地：`10-project/` 现在会初始化成真实 git repo；workspace-managed 代码票在 `ticket-start` 时会分配真实 worktree，在 `ticket-result-submit` 时会真实写盘并生成服务端 git commit 记录；final review approve 会先做真实 merge，成功后才继续 closeout
- 2026-04-11 第四段纠偏已落地：CEO shadow snapshot 现已补上 `task_sensemaking / capability_plan / controller_state`，`ceo_scheduler` comparison、deterministic fallback、validator 和 `workflow_auto_advance` 的 idle gate 已开始共用这套 controller truth；当前先覆盖 `CEO_AUTOPILOT_FINE_GRAINED + backlog_recommendation` 的实现 fanout
- 2026-04-11 第五段纠偏已落地：`delivery_closeout_package` 已收回 current `structured_document_delivery` 主线，closeout 票默认写入 `20-evidence/closeout/<ticket>/`，并会继承 canonical docs、doc update 要求与上游交付证据；`ticket-result-submit` 现在会额外硬校验 `payload.final_artifact_refs` 必须对齐已知 delivery evidence
- 2026-04-11 第六段纠偏已落地：live runner 已抽成共享 harness，当前主线保留 3 条真实入口：`library_management_autopilot_live`、`requirement_elicitation_autopilot_live`、`architecture_governance_autopilot_live`；这轮已补齐脚本和最小单测，但当前环境还没重跑真实 provider 长测
- 2026-04-12 本轮先补了一条 Windows 本机真相：`project_workspaces.py` 的 Git 子进程现已统一带 `stdin=DEVNULL`，这台 Windows + Python 3.14 机器上 `project-init / ticket-start / ticket-result-submit` 不再因为 `git init / worktree / rev-parse` 直接报 `WinError 6`
- 2026-04-12 本轮还补了一条 `P0-COR-006` 最小 live 验证口径：shared harness 新增 `architecture_governance_autopilot_smoke` checkpoint smoke，`run_report.json` 会写 `completion_mode=checkpoint_smoke`；当前只验“招聘架构师 + 技术决策会议 + 架构治理文档批准”，不把它冒充成 full closeout 长测
- 2026-04-12 同机实跑 smoke 时，provider 仍反复报 `UPSTREAM_UNAVAILABLE / timed out`；当前 smoke 入口已就位，但还没在这台机器上拿到成功的 checkpoint `run_report.json`
- 2026-04-13 本轮已按 `doc/tests/integration-audit-remediation-master-plan-20260413.md` 落第一批执行切片：`source_code_delivery@1` 现在必须带 `source_files[] / verification_runs[]`，workspace-managed 代码票会拦截占位源码和极简测试自报结果，`20-evidence/tests|git` 也已改成按 `ticket_id/attempt-1` 分路径；对应专项记录见 `doc/tests/source-delivery-evidence-remediation-20260413.md`
- 2026-04-13 本轮已继续落第二批执行切片：live harness 现在会自动生成正式版 `audit-summary.md` 和去重后的 `integration-monitor-report.md`，治理文档会旁挂同名 `.audit.md`，`ticket_context_archives/*.md` 也已重写成执行卡片；对应专项记录见 `doc/tests/audit-readability-remediation-20260413.md`
- 2026-04-14 本轮已落 `P0-S1` 最小启动协议：`repository.initialize()` 现在会幂等写入单条 `SYSTEM_INITIALIZED`，系统冷启动和 `project-init` 已拆开；空态 dashboard / 事件流现在也能直接看到初始化真相
- 2026-04-14 本轮已落 `P0-S2` 最小版本协议骨架：`process asset` canonical ref 现已改成显式 versioned ref，旧短 ref 只在 resolver 入口兼容；`compiled_context_bundle / compile_manifest / compiled_execution_package` 也已接上版本与 supersede 链，最小 `GovernanceProfile` 与 workflow graph version helper 已落仓库级查询
- 2026-04-14 本轮已落 `P0-S3` 主线写保护：`CompileRequestMeta / CompiledExecutionPackageMeta` 现在会带 `ticket_projection_version / node_projection_version / source_projection_version`；`ticket-start` 可拒绝 stale projection version，`ticket-result-submit` 可拒绝 stale `compiled_execution_package` ref；runtime 主线自发的 `ticket-start / ticket-result-submit` 也已开始携带这组新 guard 字段
- 2026-04-14 本轮已给 `P0-S4` 先落最小预接线：`ticket_context_archives` 现在会展示 `compile_request_id / compiled execution package version / source projection version / stale_against_latest`，最小 stale 检查 helper 也已落地
- 2026-04-14 本轮已完成 `P0-S4` 第一批正式物化面：新增共享 `Boardroom` runtime view materializer，`active-worktree-index.md` 与 ticket dossier 的 `brief.md / required-reads.md / doc-impact.md / git-closeout.md` 现在都会从 projection + receipt 重算，文档头固定带 `view_kind / generated_at / source_projection_version / source_refs / stale_check_key`
- 2026-04-14 本轮还把 `doc-impact.md` 收正到只读 `worker-postrun` receipt：未上报时明确展示 `not_reported`，已上报时展示真实 `documentation_updates`；手工改坏正文后，再次 sync 会整份覆盖，不会从文档正文反推真相
- 2026-04-14 本轮已落 `P1-S1` 第一段：新增正式 `TicketGraphSnapshot / TicketGraphNode / TicketGraphEdge / TicketGraphIndexSummary`，legacy ticket/node/projection 现在可归约出 `PARENT_OF / DEPENDS_ON / REVIEWS` 三类最小图边
- 2026-04-14 本轮已把 `ceo_snapshot / workflow_controller` 接到图摘要：ready/blocked 读口开始优先走 `TicketGraph`，invalid legacy dependency 会显式收成 `reduction_issues + blocked_node_ids`，不再静默当成 ready
- 2026-04-14 `graph_version` 这轮也已继续往正式图真相靠：`WORKFLOW_CREATED` 现已纳入 graph mutation event 序列，空图 workflow 也能拿到稳定 `gv_<int>` 版本
- 2026-04-14 本轮已完成 `P1-S2`：`TicketGraphIndexSummary` 现已补齐 `in_flight_ticket_ids / in_flight_node_ids / critical_path_node_ids / blocked_reasons`，controller 的 runtime gate 与 `ceo_snapshot.ticket_summary.ready_count` 继续共用同一套图索引
- 2026-04-14 本轮已完成 `P1-S3`：`Dependency Inspector` 现已正式消费 `TicketGraph` 边和索引，依赖读面补上 `dependency_ticket_ids[] / graph_summary`；dashboard 的 `pipeline_summary.blocked_node_ids` 不再回退 legacy blocked-node，图不可用时会显式返回 `blocked_node_source=graph_unavailable`
- 2026-04-14 本轮已完成 `P2-S1`：`graph_unavailable` 不再只停在 dashboard 的只读状态；`workflow_auto_advance` 命中 `build_ceo_shadow_snapshot()` 的图快照异常时，现在会打开正式 `TICKET_GRAPH_UNAVAILABLE` incident，并按 `workflow_id + incident_type + source_component` 去重
- 2026-04-14 本轮还把图故障恢复入口接到现有 incident 主链：incident detail 现已暴露 `REBUILD_TICKET_GRAPH / RESTORE_ONLY`，`incident-resolve` 会先同步重建 `TicketGraph`，成功后才关 breaker 并进入 `RECOVERING`，失败时直接 reject，不做静默恢复
- 2026-04-14 前端 `IncidentDrawer` 这轮也已补图故障说明和默认恢复动作；本轮实跑通过 `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_unavailable or rebuild_ticket_graph" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_workflow_autopilot.py -k "graph_unavailable" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q`、`cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx`
- 2026-04-15 本轮已完成 `P2-S2`：新增 `backend/app/core/role_hooks.py`，把最小 `RoleHook` registry、结构化 gate result、缺 hook 稳定指纹和 `REPLAY_REQUIRED_HOOKS` replay 收成单点协议；当前先只覆盖 `workspace-managed source_code_delivery`
- 2026-04-15 本轮已把 `TicketGraph / workflow_auto_advance / incident detail / incident-resolve / IncidentDrawer` 接到这条新主链：源码票缺 `worker_postrun / evidence_capture / git_closeout` 任一 required hook 时，会显式落 `REQUIRED_HOOK_PENDING:*`、正式打开 `REQUIRED_HOOK_GATE_BLOCKED`，并按 persisted terminal truth 幂等补写缺失 receipt
- 2026-04-15 本轮已完成 `P2-S3`：`structured_document_delivery` 现已接进正式 hook gate；治理文档和 closeout 会写 `artifact-capture.json`，closeout 还会额外写 `documentation-sync.json`，`REPLAY_REQUIRED_HOOKS` 也已能基于 `TICKET_COMPLETED.payload.artifact_refs / written_artifacts / documentation_updates` 幂等补回缺失 receipt
- 2026-04-15 本轮还把 required hook 文案收正到票型无关口径：`IncidentDrawer` 现在不再把 `REQUIRED_HOOK_GATE_BLOCKED` 写死成源码票；本轮实跑通过 `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_project_workspace_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "incident or hook or graph" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q`、`cd frontend && npm run test:run -- src/test/__tests__/components/IncidentDrawer.test.tsx`
- 2026-04-15 本轮已完成 `P2-S5`：provider unavailable 现在会在 dispatch/start 前先写 `TICKET_EXECUTION_PRECONDITION_BLOCKED`，把 ticket/node 固定阻断到 `BLOCKING_REASON_PROVIDER_REQUIRED`，不再误走 `TICKET_FAILED / TICKET_RETRY_SCHEDULED / REPEATED_FAILURE_ESCALATION`
- 2026-04-15 本轮还补了幂等解阻：同一票同一 provider 阻断不会重复记事件；provider 恢复后会先写 `TICKET_EXECUTION_PRECONDITION_CLEARED`，再恢复正常派发。本轮实跑通过 `./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_check_internal_checker_escalated_opens_incident_and_marks_dependency_stop or test_dashboard_pipeline_summary_shows_fused_build_stage_for_open_incident_breaker or test_employee_freeze_containment_opens_staffing_incident_for_executing_ticket or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -q`
- 2026-04-15 本轮已完成 `P2-S6`：`scheduler_runner` 的 provider incident / recovery 历史测试现在已切到 provider center + explicit target binding 真相；auth / bad response / rate limit 断言不再把失败包装成 `COMPLETED`
- 2026-04-15 本轮还把 mainline recovery 的测试入口收正成“先补 governance-first 前置，再测 provider 恢复”，并实跑通过 `./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "provider_incident or provider_recovery" -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "provider or incident" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore or test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident or test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure" -q`、`python3 -m py_compile backend/tests/test_scheduler_runner.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py`
- 2026-04-15 本轮已完成 `P2-S7`：`run_ceo_shadow_for_trigger` 现在已经收成严格路径；显式 deterministic mode 继续保留，但 live provider 坏响应、非法 action batch 和执行失败不再隐式 fallback，而是抛 `CeoShadowPipelineError` 并打开 `CEO_SHADOW_PIPELINE_FAILED`
- 2026-04-15 本轮已完成 `P2-S8`：`command / approval / ticket / idle maintenance` 四类直调入口现在统一走 `trigger_ceo_shadow_with_recovery()`；`incident-resolve` 新增 `RERUN_CEO_SHADOW`，API 验证桶也已收正成稳定、非空跑的 `test_p2_ceo_shadow_incident_*`
- 2026-04-15 本轮新增并实跑通过 `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "ceo_shadow_pipeline_failed or rerun_ceo_shadow" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "p2_ceo_shadow_incident" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_workflow_autopilot.py -k "ceo_shadow or incident" -q`、`python -m py_compile backend/app/core/ceo_scheduler.py backend/app/core/ticket_handlers.py backend/app/core/projections.py backend/tests/test_ceo_scheduler.py backend/tests/test_api.py backend/tests/test_workflow_autopilot.py`
- `EVENT_INCIDENT_RECOVERY_STARTED` 的 CEO 审计这轮保持 audit-only best-effort；本轮只把直调入口 incident 化，避免 provider recovery 的 autopilot 主链在恢复中途再递归打开第二条 CEO shadow incident
- 2026-04-15 本轮已把 `backend/tests/test_ceo_scheduler.py` 的旧 helper 收成显式步骤：provider 前置、lease/start、源码票、治理文档票、共识票、checker verdict 现在都会显式检查 `status_code + json.status`，不再把 `REJECTED` 当成成功继续往后跑
- 2026-04-14 本轮宽口径 `board_approve` 回归桶仍会命中一组旧的 governance/provider auto-advance 用例：scope review 批准后会在 `node_ceo_architecture_brief` 打开 `PROVIDER_REQUIRED_UNAVAILABLE -> REPEATED_FAILURE_ESCALATION`；本轮 stale-guard 主链子集已通过，这组继续留给 runtime/provider 历史测试收口
- 2026-04-15 本轮已把 `closeout / approval` 历史 API 桶改成显式 manual chain：`scope approval -> build maker/checker -> check maker/checker -> review maker/checker -> final review -> closeout maker/checker`，不再把旧的 `VISUAL_MILESTONE` 快捷链写成当前真相
- synthetic manual `scope review -> closeout` 链当前不会自动产出 dashboard `completion_summary`；这条链现在只验证 ticket/node/artifact/process-asset 真相，dashboard completion summary 继续由 autopilot / closeout 专项测试覆盖
- 2026-04-14 额外复验 `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "employee_freeze_containment_opens_staffing_incident_for_executing_ticket" -q` 时，`project-init` workflow 仍会多带一条旧的 provider / auto-advance incident；当前先继续留给 runtime/provider 历史测试收口
- 2026-04-16 本轮已落 `P4-S4` 第六批：`GraphHealthReport` 现已补第三批时间线规则 `GRAPH_THRASHING / READY_NODE_STALE`；前者只读真实 `GRAPH_PATCH_APPLIED`，后者只读 ready ticket `updated_at / timeout_sla_sec`，不再靠 advisory session 时间或其他文档侧信号猜时间线
- 2026-04-16 本轮还补了显式 `GraphHealthUnavailableError`：graph patch payload 非对象、patch node list 非 `list[str]`、ready ticket 缺 `updated_at / timeout_sla_sec` 时现在会显式失败；`workflow_auto_advance / trigger_ceo_shadow_with_recovery` 继续复用 `TICKET_GRAPH_UNAVAILABLE`
- 2026-04-16 本轮顺手删掉了 `resolve_workflow_graph_version()` 对完整事件 payload 转换的旧依赖，改成只按 graph mutation event 的 `sequence_no` 取最新 graph version，避免坏 payload 污染 graph version 真相
- 2026-04-17 本轮已继续落 `P4-S7` 第三批：required hook gate scan 现已改成按 `graph_identity + runtime_graph_node_views` 判断当前 graph lane；review lane 不再受 stale shared `node_projection.latest_ticket_id` 污染。`graph_health_policy.py` 也已只保留结构类规则，runtime stale/queue 阈值现已拆到新文件 `backend/app/core/runtime_liveness_policy.py`

## 当前批次

### `P0-COR`：主线纠偏、能力驱动决策与真实交付重构

状态：`进行中（2026-04-10，新纳入；与主线关系：live 集成测试已经证明当前默认主线会退化成文档式 artifact 交付，必须先重写协议、控制器和硬门禁，再继续新角色、新 provider 和后续治理增强）`

#### `P0-COR` 总框架补记（2026-04-10）

- 这批任务先收正 CEO 的决策起点：从 `role-first` 改成 `task-first / capability-first / resource-binding-last`。CEO 先判断任务现实，再决定能力缺口、协作方式和交付物，不再先找某个角色。
- CEO 的第一层真相要变成结构化 `task sensemaking + capability plan`：最小要能说明 `task_kind / deliverable_kind / uncertainty_level / required_capabilities / optional_capabilities / recommended_team_shape / staffing_gaps / need_meeting`。
- 角色、招聘、会议、ticket 派发都只能是 capability plan 的结果。不能再因为员工池里刚好有谁在线，就静默把任务改派给这个角色；也不能把 `architect_primary` 写成所有项目的默认前置。
- `architect_primary`、系统分析师、开发测试团队都只是特定任务下的可能结果。需求调研类任务可以落到分析/调研能力，模块化实施任务可以直接落到开发/测试能力，复杂架构拆解任务才需要架构设计能力。
- multi-agent 协作也要跟着任务边界走：先由主控 agent 做任务分解，再决定是否启用 focused subagent 或 parallel agent team。只有互相独立的 domain 才允许并行，且每个 subagent / worktree 只负责清晰边界内的一段任务。
- 代码实施只是 `deliverable_kind=source_code_delivery` 的一个分支。需求调研、系统分析、治理设计、代码实施要按各自 deliverable contract 收口，不能把“真实代码交付”误写成所有项目的默认完成定义。

#### `P0-COR` 优先整改顺序（2026-04-10）

1. 先补 `task sensemaking`：让 CEO 在任何建票、招聘、开会之前，先判断任务类型、交付物类型、不确定性和风险。
2. 再补 `capability plan`：把所需能力、可选能力、建议 team shape、staffing gap 和是否需要 meeting 固化成显式中间真相。
3. 把 controller 收成单一主线：`workflow_auto_advance / scheduler_runner / ceo_scheduler / deterministic fallback` 都只消费同一套 `task sensemaking + capability plan`，禁止静默改写 role 或 assignee。
4. 把招聘和会议改成缺口驱动：现有员工能覆盖就派单，覆盖不全就显式招聘，分歧高或不确定性高就显式开会，三者都不再靠隐式 fallback。
5. 按 `deliverable_kind` 重写交付 contract：代码型任务走真实源码交付包，调研/分析/治理型任务走各自证据包，不再只认旧的占位式 JSON 交付。
6. 按 `deliverable_kind` 重写 review gate：代码型任务校验源码、测试、构建和文档同步；调研/分析型任务校验事实来源、结论链、风险边界和决策记录。
7. 重建 live 回归矩阵：至少覆盖需求调研、系统/架构拆解、模块化实施三类任务，确保 CEO 是按任务现实决策，而不是按现有角色池静默派单。

- `P0-COR-001` 进行中：收正 canonical 协议，把 `CEO action / provider config / runtime result / ticket deliverable` 统一到单一主线真相；当前已落第一段 project workspace 真相：`project-init` 现在会创建三分区项目工作区，`ticket-create` 会自动补 `project_workspace_ref / project_methodology_profile / deliverable_kind / canonical_doc_refs / required_read_refs / doc_update_requirements / git_policy`，workspace-managed ticket 也会生成 dossier
- `P0-COR-002` 进行中：收正单一 workflow controller。当前第四段已落：`STANDARD` 也已切到 governance-first，`project-init` kickoff、requirement elicitation 后续 kickoff、`workflow_controller / ceo_scheduler / deterministic fallback / validator / workflow_auto_advance` 现在都会共用同一条治理链真相；旧 approved-scope follow-up 只留给非 autopilot 的手工 `consensus_document` 兼容链
- `P0-COR-003` 进行中：收正 capability gap 驱动的招聘、协作和阻断逻辑。当前第四段已落：`STANDARD` 在 backlog recommendation 之前也会被治理链阻断，`required_governance_ticket_plan` 会直接暴露下一张治理文档票；backlog recommendation 之后，`STANDARD` 与 `CEO_AUTOPILOT_FINE_GRAINED` 一样会进入 `architect_primary / 技术决策会议 / staffing gap` 硬约束
- `P0-COR-004` 进行中：按 `deliverable_kind` 重写交付 contract。当前第七段已把 `delivery_closeout_package` 也并回 `structured_document_delivery` 主线：closeout 票默认写到 `20-evidence/closeout/<ticket>/`，继续复用 declared artifact / written artifact 对齐 gate，并把 closeout 需要的 canonical docs / doc update 要求一起补齐；这轮又补了 Windows Git 子进程兼容，workspace-managed 代码链在本机回归已恢复；更广义的 research / analysis deliverable kind 还没正式引入
- `P0-COR-005` 进行中：把 checker / closeout 改成按 `deliverable_kind` 生效的硬门禁。当前第七段已把 closeout 提交口径收正到“final_artifact_refs 必须对齐已知 delivery evidence”，并统一 board-approved closeout、autopilot closeout 与 dashboard completion 的真相链；`FOLLOW_UP_REQUIRED` 继续只作为 checker 可见风险，不自动升成 schema 级硬失败；本机 `project_workspace_hooks` 相关 closeout 回归现在已能重跑
- `P0-COR-006` 进行中：当前已把 live runner 抽成共享 harness，并补齐 3 条 full live 入口：`backend/tests/live/requirement_elicitation_autopilot_live.py`、`backend/tests/live/architecture_governance_autopilot_live.py`、`backend/tests/live/library_management_autopilot_live.py`。这轮新增了 `backend/tests/live/architecture_governance_autopilot_smoke.py` checkpoint smoke，用真实 provider 验“招聘架构师 + 技术决策会议 + 架构治理文档批准”；但这台机器上实跑仍被 provider timeout 卡住，`requirement_elicitation` 和 `library_management` 的 full real-provider 长测也仍待重跑
- `2026-04-13 审计第一批执行切片` 已完成：只覆盖 `P0-2 / P0-3 / P1-3`。这轮把 `source_code_delivery` 提交口径从“只交 ref”收紧成“必须同时交源码正文、原始测试运行详情和版本化证据路径”；workspace-managed 代码票不再接受 `source.ts/source.tsx`、`runtimeSourceDelivery = true`、`generated for <ticket>`、空 stdout/stderr、`pytest -q passed` 这类占位内容过关；live harness full closeout 现在也会把源码证据质量和 `artifact_index` 路径撞车一并纳入成功断言
- `2026-04-13 审计第二批执行切片` 已完成：覆盖 `P1-1 / P1-2 / P2-1 / P2-2`。这轮把场景根目录的审计入口收正成 `audit-summary.md + integration-monitor-report.md + governance *.audit.md + ticket_context_archives/*.md` 这组人工可读层；live harness 现在只记录状态变化点和静默恢复摘要，治理 JSON 会自动旁挂 `.audit.md`，ticket 上下文档案也会在 compile / terminal 两个阶段刷新成执行卡片
- 本轮额外补了一条测试运行真相：当仓库位于 Git linked worktree 下时，`backend/tests/conftest.py` 现在会自动把 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT` 改到系统临时目录，避免测试里再创建项目 worktree 时撞上 Git 的 `$GIT_DIR too big`；Windows 下 `pytest` 仍建议继续显式带 repo 内 `--basetemp`
- 本轮还补了一条 `P0-S1` 验证真相：`./backend/.venv/bin/pytest backend/tests/test_repository.py -k "initialize" -q` 当前已通过；`./backend/.venv/bin/pytest backend/tests/test_api.py -k "system_initialized or startup or project_init" -q` 仍会命中一组依赖 live provider 的旧 `project-init` 自动推进用例，当前环境未配 provider 时会报 `PROVIDER_REQUIRED_UNAVAILABLE`
- 当前 blocker 仍集中在真实 provider 长测；`ceo_scheduler` 旧 helper、`closeout / approval` 历史测试桶和 `run_ceo_shadow_for_trigger` 直调恢复历史桶这轮都已按当前真相收口
- 当前 `P2-S4` 已完成：`review_evidence` 票现在也已经走正式 `RoleHook` registry、`artifact_capture` required hook gate、`REQUIRED_HOOK_GATE_BLOCKED` incident 和 `REPLAY_REQUIRED_HOOKS` recovery；`delivery_check_report / ui_milestone_review / maker_checker_verdict` 缺 receipt 时会显式阻断下游，不再静默放行
- 本轮 `review_evidence` replay 已收正成 fail-closed：只要 `TICKET_COMPLETED` 里缺 `artifact_refs` 或 `written_artifacts` 字段就直接 `REJECTED`，incident 保持 `OPEN`；如果字段存在但为空数组，则允许幂等补回最小 `artifact-capture.json`，不从正文或磁盘目录反推
- 本轮新增并实跑通过 `./backend/.venv/bin/pytest backend/tests/test_role_hooks.py -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "hook or incident or graph" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "review_evidence_missing_required_hook_keeps_dependency_gate_blocked" -q`、`python3 -m py_compile backend/app/core/role_hooks.py backend/app/core/ticket_handlers.py backend/tests/test_role_hooks.py backend/tests/test_api.py`
- `./backend/.venv/bin/pytest backend/tests/test_api.py -k "delivery_check_report or ui_milestone_review or maker_checker_verdict" -q` 本轮原样补跑只返回 `286 deselected`；当前仓库没有直接按 schema 名命名的 API 聚合桶，这条不能再当有效验证口径，后续要单独整理
- 2026-04-15 本轮已完成 `P3-S1`：`GovernanceProfile` 现已补齐 `auto_approval_scope / expert_review_targets / audit_materialization_policy`，`project-init` 会稳定写默认治理档位；`CompileRequest / CompiledExecutionPackage` 也已显式带 `governance_profile_ref / governance_mode_slice / task_frame / required_doc_surfaces / context_layer_summary`
- 2026-04-15 本轮已完成 `P3-S2`：`build_ceo_shadow_snapshot()` 现在会稳定产出 `projection_snapshot / replan_focus`；`ceo_prompts / proposer / validator / scheduler / workflow_controller` 已切到新快照合同，缺结构时显式失败，不再从旧顶层隐式补读
- 2026-04-15 本轮已完成 `P3-S3`：新增最小 `skill_runtime`，当前已稳定解析 `implementation / review / debugging / planning_governance` 四类技能；未知 `forced_skill_ids` 或冲突组合会直接拒绝组包，执行包和执行卡片都会带 `skill_binding`
- 2026-04-15 本轮已完成 `P4-S1`：新增正式 `BoardAdvisorySession` 合同、schema 和 repository helper；`requires_constraint_patch_on_modify=true` 的 review pack 现在会自动绑定单条 advisory session，Review Room 也会暴露 `advisory_context`
- 2026-04-15 本轮已完成 `P4-S2`：`MODIFY_CONSTRAINTS` 现在会显式写 advisory decision truth、`DECISION_SUMMARY` 过程资产和可选 `GovernanceProfile` supersede；非法 `governance_patch` 会 fail-closed reject，不再静默忽略
- 2026-04-15 本轮已完成 `P4-S3`：`build_ceo_shadow_snapshot()` 已补 `board_advisory_sessions / latest_advisory_decision`，`ceo_prompts` 会显式提示先读顾问决策；现有 `ReviewRoomDrawer` 也已补最小 governance patch 控件，不新开页面
- 2026-04-15 本轮已完成 `P4-S4` 第一批：`FAILURE_FINGERPRINT / PROJECT_MAP_SLICE` 已进入正式 `ProcessAsset` 合同和 resolver；`Context Compiler` 会对源码票、`delivery_check_report` 和治理文档自动注入 workflow 地图切片与最近失败指纹，`build_ceo_shadow_snapshot()` 也已补 `project_map_slices / failure_fingerprints / graph_health_report`
- 2026-04-15 本轮还把 `GraphHealthReport` 首版接进 incident 主链：当前只覆盖 `FANOUT_TOO_WIDE / CRITICAL_PATH_TOO_DEEP / PERSISTENT_FAILURE_ZONE` 三条规则；`workflow_auto_advance` 命中 `CRITICAL` 时会显式打开 `GRAPH_HEALTH_CRITICAL`，Incident Drawer 和 incident detail 继续复用 `RERUN_CEO_SHADOW`
- 2026-04-16 本轮已完成 `P4-S4` 第二批：advisory review pack 现在会先显式进入 change flow，再走 drafting / analysis / apply；`modify-constraints` 不再一步式 resolve approval，`board-advisory-append-turn / board-advisory-request-analysis / board-advisory-apply-patch` 也已进正式命令面
- 2026-04-16 本轮已完成 `P4-S4` 第二批：新增正式 `GRAPH_PATCH_PROPOSAL / GRAPH_PATCH` 过程资产和 resolver，`approved_patch_ref` 现在只会指向真实 graph patch；applied patch 的 `freeze / unfreeze / focus` 也已接进 `TicketGraph`
- 2026-04-16 本轮已完成 `P4-S4` 第二批：`ReviewRoomDrawer` 已切成“进入变更流程 -> 草拟 / 发分析 -> 确认导入”三段最小闭环，`ceo_shadow_snapshot` 也已补 `change_flow_status / latest_patch_proposal_ref / patched_graph_version / focus_node_ids`
- 2026-04-16 本轮已完成 `P4-S4` 第三批：`audit_mode = FULL_TIMELINE` 的 advisory change flow 现在会把 transcript archive 物化到 `90-archive/transcripts/board-advisory/<session>/v<N>.json`，并同步写正式 `TIMELINE_INDEX` 资产；archive 版本只增不改
- 2026-04-16 本轮已完成 `P4-S4` 第三批：`BoardAdvisorySession / Review Room / build_ceo_shadow_snapshot() / latest_advisory_decision` 已补 `latest_timeline_index_ref / latest_transcript_archive_artifact_ref / timeline_archive_version_int`；`ReviewRoomDrawer` 也已能直接打开 transcript archive 和 timeline index
- 2026-04-16 本轮已完成 `P4-S4` 第三批：`FULL_TIMELINE` archive 写失败时，相关 advisory 命令现在会显式 `REJECTED` 并回滚事务，不再留下半写 session 状态
- 2026-04-16 本轮已完成 `P4-S4` 第四批：`board-advisory-request-analysis` 现在会先创建独立 `BoardAdvisoryAnalysisRun`，把 session 切到 `PENDING_ANALYSIS`，再在事务外跑 analysis harness；不再在 board command 事务里同步直算 proposal
- 2026-04-16 本轮已完成 `P4-S4` 第四批：advisory analysis harness 已朝 `CompiledExecutionPackage` 收口，固定只读 `DECISION_SUMMARY / PROJECT_MAP_SLICE / FAILURE_FINGERPRINT / TIMELINE_INDEX`，并显式区分 `DETERMINISTIC / LIVE_PROVIDER`；live 失败不会再隐式回退 deterministic
- 2026-04-16 本轮已完成 `P4-S4` 第四批：新增 `BOARD_ADVISORY_ANALYSIS_FAILED` incident 和 `RERUN_BOARD_ADVISORY_ANALYSIS` recovery；`Review Room / Incident Detail / IncidentDrawer` 也已补 pending / failed / rerun 主链
- 2026-04-16 本轮已完成 `P4-S4` 第五批：`SOURCE_CODE_DELIVERY` 过程资产现已显式带 `source_paths / written_paths / module_paths / document_surfaces`；`ProjectMapSlice` 会逐票优先消费这层结构化真相，legacy / 非 workspace-managed 代码票仅在本票缺稳定路径时才回退到自己的 `allowed_write_set`
- 2026-04-16 本轮还把 `ProjectMapSlice` 的旧兼容收掉：artifact `logical_path` 不再参与模块地图推导，runtime JSON、日志和证据路径不会再污染 `module_paths`
- 2026-04-16 本轮还把 `GraphHealthReport` 补到第二批：新增 `BOTTLENECK_DETECTED / ORPHAN_SUBGRAPH / FREEZE_SPREAD_TOO_WIDE`，并把 `CRITICAL_PATH_TOO_DEEP` 收正到正式 `PARENT_OF + DEPENDS_ON` DAG 口径
- 2026-04-16 本轮已完成 `P4-S4` 第七批：advisory analysis live gate 已从员工 `provider_id` 旧兼容收口到“真实 board-approved architect + 正式 runtime provider 选路”；`role_binding / ceo_binding_inheritance / default_provider` 命中时都可进入 `LIVE_PROVIDER`
- 2026-04-16 本轮还把 `board_advisory_analysis.py` 收成单点 `execution plan` helper；run 创建、compile worker binding 和 live 执行现在共用同一套 executor / provider selection 真相，synthetic architect 即使存在 binding / default provider 也保持 `DETERMINISTIC`
- 2026-04-16 本轮已补 fresh 验证：`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory and analysis" -q`、`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m py_compile backend/app/core/board_advisory_analysis.py backend/tests/test_api.py` 都已通过；paused provider 现在也会显式失败并继续走既有 `BOARD_ADVISORY_ANALYSIS_FAILED` recovery
- 2026-04-16 本轮已完成 `P4-S4` 第八批：`GraphPatchProposal / GraphPatch` 已扩成正式 patch v2 合同，新增 `replacements / remove_node_ids / edge_additions / edge_removals`；`add_node` 当前会显式 reject，不再借旧兼容偷渡
- 2026-04-16 本轮已新增单点 `graph_patch_reducer.py`：`TicketGraph / GraphHealth / board-advisory-apply-patch` 现在统一消费 `GRAPH_PATCH_APPLIED` 真相；`GRAPH_PATCH_PROPOSAL / GRAPH_PATCH` resolver 也已改成读不可变 artifact，不再从 session 内嵌 JSON 回填正文
- 2026-04-16 本轮还补了 graph patch v2 的 fail-closed 校验：未知 node、重复边、缺失边、orphan、cycle、执行中/已完成节点 remove/replace 都会显式 `REJECTED`；`GRAPH_THRASHING` 也已开始统计 replacement / edge delta 目标集
- 2026-04-16 本轮顺手补了一条实现判断真相：maker/checker 仍会把多张 ticket 收到同一 `node_id`，当前只是在 reducer / graph health 里显式跳过 inherited self-loop，没把 graph-first node identity 冒充成已完成
- 2026-04-16 本轮已完成 `P4-S4` 第九批：`graph_health.py` 现已补第四批规则 `QUEUE_STARVATION / READY_BLOCKED_THRASHING / CROSS_VERSION_SLA_BREACH`；三条规则都只读现有 `events + graph_version + ticket/node projection.version/updated_at`，没有新增 graph health history 表、projection 或 process asset
- 2026-04-16 本轮还把 fail-closed 口径继续收紧到新规则：ready / blocked 节点缺 `updated_at / timeout_sla_sec / version`、或参与时间线重建的事件 payload 非法时，现在会继续显式抛 `GraphHealthUnavailableError`，不回退到当前快照、session JSON 或 ticket-only 快捷推导
- 2026-04-16 本轮已完成 `P4-S4` 第十批：新增单点 `graph_identity.py`，把 graph lane 身份收成正式真相；普通执行票固定收口到 execution lane，`MAKER_CHECKER_REVIEW` 固定收口到 `runtime_node_id::review`，`MAKER_REWORK_FIX` 则回 execution lane 替换当前绑定 ticket
- 2026-04-16 本轮已把 `TicketGraph` 收正到 graph-first lane 口径：旧的 ticket-derived `graph_node_id=ticket:<ticket_id>` 已删除；shared runtime `node_id` 的 maker/checker/rework 现在会显式拆成 execution / review 两条 graph lane，不再靠 inherited self-loop 跳过兼容
- 2026-04-16 本轮已把 `graph_patch_reducer / graph_health / GRAPH_HEALTH_CRITICAL incident / CEO snapshot` 全切到新 graph identity；`affected_graph_node_ids` 已进入 graph health digest 和 incident payload，旧兼容读面 `affected_nodes` 继续只保留 runtime node id
- 2026-04-16 本轮还删掉了会污染新架构真相的旧兼容：path self-loop 跳过、advisory patch 对 review lane 的“未知 node”模糊拒绝、以及 graph 层按 runtime latest-ticket 半猜 graph node 的旧推导都已移除；命中这类问题时现在会显式抛 `GraphIdentityResolutionError` 或显式 `REJECTED`
- 2026-04-16 本轮已完成 `P4-S4` 第十一批：`GraphPatchProposal / GraphPatch` 现已正式支持 `add_nodes[]`；最小 `GraphPatchAddedNode` 已固定 `node_id / node_kind / deliverable_kind / role_hint / parent_node_id / dependency_node_ids[]`，`graph_patch_proposal` output schema 也已升到 `v2`
- 2026-04-16 本轮已把 `graph_patch_reducer.py` 扩成 graph-only placeholder overlay：`add_node` 现在必须显式声明 parent/dependency，same-patch `edge_additions / edge_removals` 不能再偷接 placeholder；坏 patch 会继续 fail-closed，历史 add-node 在真实 ticket 创建后会被显式吸收，不再把 graph replay 打成 unavailable
- 2026-04-16 本轮已把 `TicketGraph / GraphHealth` 接到 placeholder 真相：placeholder node 现在会以 `is_placeholder=true / node_status=PLANNED / ticket_id=null / runtime_node_id=null` 物化到 graph snapshot；结构类 graph health 已纳入 placeholder，`affected_nodes` 不再把 placeholder `node_id` 伪装成 runtime node
- 2026-04-16 本轮 fresh 验证已通过：`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -q`、`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "board_advisory and patch" -q`、`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_assets.py -k "graph_patch or board_advisory" -q`、`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "advisory or graph_health" -q`、`python -m py_compile backend/app/contracts/advisory.py backend/app/contracts/ticket_graph.py backend/app/core/output_schemas.py backend/app/core/board_advisory.py backend/app/core/board_advisory_analysis.py backend/app/core/process_assets.py backend/app/core/graph_patch_reducer.py backend/app/core/ticket_graph.py backend/app/core/graph_health.py backend/app/core/approval_handlers.py backend/tests/test_ticket_graph.py backend/tests/test_api.py`
- 2026-04-16 本轮已完成 `P4-S4` 第十二批：新增正式 `execution_target:board_advisory_analysis`，`board_advisory_analysis.py` 已改成 execution contract 驱动；真人 executor 改按 capability tags 选，旧的 `architect_primary + architect_governance_document` 直绑已退出核心判断
- 2026-04-16 本轮还把 advisory analysis 的错误口径收正到 fail-closed：命中 contract mismatch / missing provider selection / provider paused 时都会显式失败，并继续复用现有 `BOARD_ADVISORY_ANALYSIS_FAILED -> RERUN_BOARD_ADVISORY_ANALYSIS / RESTORE_ONLY`
- 2026-04-16 本轮已给 ticket create 合同补最小 `graph_contract.lane_kind`，`graph_identity.py` 现已改成 contract 优先；maker-checker review / rework 建票路径也已显式写入 lane contract，旧 taxonomy 只留单点 adapter
- 2026-04-16 本轮已新增 `backend/app/core/graph_health_policy.py`，把 `GraphHealth` 的 threshold / multiplier / timeline window / event whitelist / severity 收成集中配置；`build_graph_health_report()` 现已支持显式 `policy` 注入
- 2026-04-16 本轮已完成 `P4-S4` 第十三批：`board_advisory_analysis` 主链已改成 live-only success path；没有真实 board-approved contract-matching executor、没有 advisory target provider selection、或 provider paused 时都会显式失败，不再让 synthetic executor / deterministic proposal 从 command 主链伪成功
- 2026-04-16 本轮已完成 `P4-S4` 第十三批：graph core 现已改成 contract-only lane resolution；`resolve_graph_lane_kind()` 只认 `graph_contract.lane_kind`，legacy maker-checker / rework taxonomy 已移到单点 compat adapter；新票路径会补正式 execution lane contract
- 2026-04-16 本轮已完成 `P4-S4` 第十三批：新增 `backend/app/core/runtime_liveness.py` 与 `RuntimeLivenessReport`，把 `QUEUE_STARVATION / READY_BLOCKED_THRASHING / READY_NODE_STALE / CROSS_VERSION_SLA_BREACH` 从 `GraphHealthReport` 主读面拆出；`ProjectionSnapshot / CEO prompt / workflow_auto_advance` 现在会同时读 `graph_health_report + runtime_liveness_report`
- 2026-04-16 本轮已完成 `P4-S4` 第十三批：结构类 critical 保持 `GRAPH_HEALTH_CRITICAL`；liveness critical 改走 `RUNTIME_LIVENESS_CRITICAL`；liveness 构建失败改走 `RUNTIME_LIVENESS_UNAVAILABLE`
- 2026-04-16 本轮已完成 `P4-S4` 第十四批：新增 `backend/app/core/runtime_node_views.py`，把 execution-lane graph node、graph-only placeholder 和持久化 `node_projection` 收成单点三态读面；同一 `node_id` 命中 placeholder/materialized 冲突、或 graph/runtime 真相不一致时现在会显式抛 `RuntimeNodeViewResolutionError`
- 2026-04-16 本轮已把 `Dependency Inspector` 接到 placeholder runtime 挂载读面：graph-only placeholder 现在会直接显示在节点列表里，并新增 `is_placeholder / materialization_state`；依赖链继续按 graph truth 读取 `PARENT_OF + DEPENDS_ON`，不再因为缺 `node_projection` 就把 placeholder 当缺失节点
- 2026-04-16 本轮已把 `ticket-create / CEO create-ticket` 的节点存在性判断切到 runtime node view；placeholder `node_id` 现在允许进入正式建票并由现有 `EVENT_TICKET_CREATED -> node_projection` 主链物化，已 materialized 节点继续显式 reject，执行态 compile/runtime 内核保持不变
- 下一轮如果继续推进 `P4-S4` 收尾瘦身，优先决定 placeholder runtime materialization 是否拆独立切片；runtime `node_projection` 双层真相继续保持后置，`RuntimeLiveness/GraphHealth` 的 policy contract 是否继续拆层单独决策
- 2026-04-16 本轮 fresh 验证已通过：`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "placeholder or graph_patch" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "dependency_inspector or placeholder or create_ticket" -q`、`./backend/.venv/bin/pytest backend/tests/test_ceo_scheduler.py -k "placeholder or advisory" -q`、`python3 -m py_compile backend/app/core/runtime_node_views.py backend/app/core/projections.py backend/app/core/ticket_handlers.py backend/app/core/ceo_validator.py backend/app/core/ceo_proposer.py backend/tests/test_api.py`、`cd frontend && npm run build`
- 2026-04-17 本轮已把 `P4-S6` 正式推进到 placeholder 持久化真相：新增 `planned_placeholder_projection` 表和 `backend/app/core/planned_placeholder_projection.py`，execution-lane graph-only placeholder 现在会稳定落库 `workflow_id / node_id / graph_node_id / graph_version / status / reason_code / open_incident_id / materialization_hint / updated_at / version`
- 2026-04-17 本轮已把 `runtime_node_views` 收正到 “materialized 只认 `node_projection`、planned 只认 `planned_placeholder_projection`”；graph 有 placeholder 但缺持久化 placeholder truth、或 placeholder projection 脱离 execution graph lane 时，会显式抛 `RuntimeNodeViewResolutionError`，不再靠缺 `node_projection` 猜状态
- 2026-04-17 本轮已把 placeholder incident / recovery 和真实建票吸收接到同一真相：planned placeholder 命中 open incident 时会稳定变成 `BLOCKED`，真实 `ticket-create` 成功后 placeholder row 会被吸收删除；incident resolve 不会偷偷改成 materialized
- 2026-04-17 本轮还删掉了会污染新架构真相的旧兼容：placeholder 不再从 `node_projection` 缺失、incident/detail 读面或空值回退反向猜状态；graph/runtime/placeholder 真相不一致时统一 fail-closed
- 2026-04-17 本轮 fresh 验证已通过：`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "placeholder" -q`、`./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k planned_placeholder -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder_gate" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "placeholder or dependency_inspector or create_ticket" -q`、`python3 -m py_compile backend/app/core/planned_placeholder_constants.py backend/app/core/planned_placeholder_projection.py backend/app/core/runtime_node_views.py backend/app/core/ticket_graph.py backend/app/db/repository.py backend/tests/test_ticket_graph.py backend/tests/test_context_compiler.py backend/tests/test_workflow_autopilot.py backend/tests/test_api.py`
- 下一轮如果继续推进 `P4-S6`，优先决定 `planned_placeholder_projection` 是否继续升格到正式 materialization 协议；scheduler 自动建票和 graph-first placeholder lifecycle 继续后置单独决策
- 2026-04-17 本轮已把 `P4-S6` 第三批收口到 orchestration 边界：placeholder materialization 现已显式冻结在 `ticket-create` 单入口，`workflow_auto_advance` 开 gate incident 和 `incident-resolve` 走 `RERUN_CEO_SHADOW` 都不会偷偷建票或改写成 materialized
- 2026-04-17 本轮已把 `workflow_auto_advance` 改成先 recover open approval / open incident，再 build snapshot；generic `ceo_delegate` 自动审批、provider `RESTORE_ONLY / RETRY` 恢复链不再先被旧 blocker 顺序卡住
- 2026-04-17 本轮已收掉 provider 单节点失败流的 graph self-edge：same-lane retry lineage 不再生成 self `PARENT_OF` 边，`GraphHealthReport` 不会再因 execution-lane retry 历史触发 cyclic path
- 2026-04-17 本轮还补了测试时钟基座到 `runtime_liveness / graph_health`；provider recovery 和 autopilot orchestration 回归现在按显式会话时间跑，不再被宿主机当前时间误判成 stale queue
- 2026-04-17 本轮 fresh 验证已通过：`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "autopilot_auto_advance_resolves_generic_open_approval_via_ceo_delegate or autopilot_auto_advance_resolves_provider_incident_and_retries_latest_failure or autopilot_auto_advance_restores_provider_incident_when_source_ticket_already_completed" -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder or incident or ceo_delegate" -q`、`./backend/.venv/bin/pytest backend/tests/test_scheduler_runner.py -k "test_scheduler_runner_auto_recovers_open_provider_incident_for_autopilot_workflow" -q`、`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "graph_health or same_lane_retry_parent_self_edge" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "placeholder_gate_incident_resolve_reruns_shadow_and_closes_incident" -q`、`python3 -m py_compile backend/app/core/workflow_auto_advance.py backend/app/core/ticket_graph.py backend/tests/conftest.py backend/tests/test_workflow_autopilot.py backend/tests/test_ticket_graph.py backend/tests/test_api.py`
- 这一轮还确认了一条旧测试入口问题：`./backend/.venv/bin/pytest backend/tests/test_api.py -k "provider_incident_resolve or placeholder_gate_incident_resolve" -q` 会先撞到 `test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure` 的 `wf_seed` 预建 workflow 缺口；当前 provider restore 主链已由 autopilot / scheduler 精确回归覆盖，这条旧 API helper 入口后续单独清
- 2026-04-17 本轮已完成 `P4-S7` 第一批：新增正式 `runtime_node_projection` 真相层，execution lane 的 materialized runtime node 现在会按 `workflow_id / graph_node_id / node_id / runtime_node_id / latest_ticket_id / status / blocking_reason_code / updated_at / version` 幂等重建
- 2026-04-17 本轮已把 execution-lane runtime gate 切到新真相：`runtime_node_views / context_compiler / ticket-start / ticket-result-submit / runtime runner / TicketGraph / Dependency Inspector` 现在优先读 `runtime_node_projection`；review lane 明确继续留在 legacy `node_projection` 兼容壳，不再让 review 票污染 execution runtime truth
- 2026-04-17 本轮已把版本门禁收正到 execution runtime truth：`CompileRequestMeta / CompiledExecutionPackageMeta` 现已补 `runtime_node_projection_version`，`ticket-start / ticket-result-submit` 会显式拒绝 stale runtime node version，不再从 shared `node_id` 或 legacy `node_projection` 缺失反向猜状态
- 2026-04-17 本轮已完成 `P4-S7` 第二批：`runtime_node_projection` 已扩到所有 materialized graph lane；maker-checker review 现在会稳定落 `graph_node_id=<runtime_node_id>::review` 的 runtime truth，不再借 execution row 或 legacy `node_projection` 混状态
- 2026-04-17 本轮已把 review lane / approval target / worker runtime 继续收口到 graph-first runtime truth：`context_compiler / ticket-start / ticket-result-submit / ticket-complete / runtime runner` 现在都会先解 `graph_identity` 再读 graph-lane runtime row；review pack subject 已补正式 `source_graph_node_id`，board approval 也不再按 shared `node_id` 猜 target
- 2026-04-17 本轮已把 `RuntimeLivenessReport` 改成先校验 materialized graph lane 的 runtime truth，再读 `runtime_node_projection.updated_at / version / latest_ticket_id`；缺 review-lane runtime row、graph/runtime identity 漂移时现在会显式 `RuntimeLivenessUnavailableError`
- 2026-04-17 本轮 fresh 验证已通过：`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "runtime_node or placeholder or graph_health" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_context_compiler.py -k "runtime_node or captures_projection_versions" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "runtime_node_projection_version or maker_checker or projection_is_not_currently_blocked" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "runtime_governance_gate or maker_checker or runtime_runner_executes_leased_review_lane_ticket" -q`、`./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "runtime_liveness or QUEUE_STARVATION" -q`、`./backend/.venv/Scripts/python.exe -m py_compile backend/app/core/reducer.py backend/app/core/runtime_node_views.py backend/app/core/context_compiler.py backend/app/core/ticket_handlers.py backend/app/core/runtime.py backend/app/core/runtime_liveness.py backend/app/core/approval_handlers.py backend/tests/test_ticket_graph.py backend/tests/test_context_compiler.py backend/tests/test_api.py backend/tests/test_scheduler_runner.py`
- 2026-04-17 本轮 fresh 验证已通过：`./backend/.venv/bin/pytest backend/tests/test_ticket_graph.py -k "runtime_node or placeholder or graph_health" -q`、`./backend/.venv/bin/pytest backend/tests/test_context_compiler.py -k "runtime_node or planned_placeholder or captures_projection_versions" -q`、`./backend/.venv/bin/pytest backend/tests/test_api.py -k "create_ticket or dependency_inspector or ticket_start or ticket_result_submit" -q`、`./backend/.venv/bin/pytest backend/tests/test_workflow_autopilot.py -k "placeholder or incident" -q`、`python3 -m py_compile backend/app/core/context_compiler.py backend/app/core/ticket_handlers.py backend/app/core/ticket_graph.py backend/app/core/runtime_node_views.py backend/app/core/runtime.py backend/app/core/reducer.py backend/app/db/repository.py backend/app/core/planned_placeholder_projection.py backend/app/contracts/runtime.py backend/app/contracts/commands.py backend/app/contracts/projections.py backend/app/core/projections.py`
- 2026-04-16 本轮 fresh 验证已通过：`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ticket_graph.py -k "graph_health" -q`、`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api.py -k "graph_health" -q`、`D:/projects/boardroom-os/backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ceo_scheduler.py -k "graph_health" -q`、`python -m py_compile backend/app/core/graph_health.py backend/tests/test_ticket_graph.py backend/tests/test_api.py backend/tests/test_ceo_scheduler.py`
- `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scheduler_runner.py -k "ceo_shadow" -q` 当前会返回 `51 deselected`；本轮已改用精确的 `idle_ceo_maintenance_*` 桶做非空跑验证，这条聚合桶后续要单独整理
- 下一轮如果继续推进新架构重构，继续从 `P4-S7` 续跑，优先决定 legacy `node_projection` 兼容壳是否还能继续收缩；`RuntimeLiveness/GraphHealth` 的 policy contract 是否继续拆层单独决策；`doc/new-architecture/**` 仍保持只读
- 这批任务优先级高于 `M6`、`C1` 和所有新角色扩张；旧 `M7` 只按“旧口径完成”，不再作为当前主线完成定义

以下批次保留作已完成基线，但当前执行优先级统一让位给 `P0-COR`。

### `P2-UI`：前端英文恢复与 runtime UI 回归收口

状态：`已完成（2026-04-09，2 项已全部收口；与主线关系：在当前主线任务空窗时，先把前端主线壳恢复到与 README / 测试 / runtime-provider 真相一致的英文口径，并补齐 runtime UI 回归，避免 UI 壳继续偏离当前 MVP 真相）`

- `P2-UI-009` 已完成（2026-04-09）：`frontend/src` 当前主线可见文案已恢复英文，覆盖 `Dashboard / Inbox / Workflow River / Workforce / Review Room / Meeting Room / Incident / Dependency Inspector / Provider Settings / Project Init / Completion` 等主线读面；`frontend/src/utils/format.ts` 也已恢复英文 locale 与英文 fallback，`rg -n "[\\p{Han}]" frontend/src` 当前无命中
- `P2-UI-010` 已完成（2026-04-09）：前端继续沿用当前真实 runtime/provider 契约，不回退后端字段；`CompletionCard` 已收正 `final_review_pack_id` 空值分支，`frontend/src/types/api.ts` 已把 `RuntimeProviderData.providers / role_bindings / future_binding_slots` 与 `IncidentDetailData.available_followup_actions` 等数组口径对齐到 `readonly`，前端回归测试与 `App.test.tsx` 也已同步到英文文案与当前真实字段
- 本轮额外收口了一条后端测试真相差异：`test_idle_ceo_maintenance_targets_pending_workflow_once_per_interval` 现已按当前“最近状态变化冷却窗口”语义改成超过间隔后再断言 due，不再用 workflow 刚更新的同一时刻误判 idle maintenance 应立即触发

### `P2-DEC`：派单边界与 role/runtime 解耦前置

状态：`已完成（2026-04-07，新纳入后已于同日完成四个实现切片；与主线关系：这批只完成第一层解耦，先把 role 模板、runtime 执行键、CEO 派单、过程资产闭环与 scheduler 的确定性执行边界收正到原子 Ticket 模型；但 canonical 协议分裂、多 workflow controller 并存、BUILD 仍是 artifact 交付这些主线问题没有在这里解决，现已由 P0-COR 接管）`

- `P2-DEC-001` 已完成（2026-04-07）：执行 target contract 与 role/runtime 解耦；ticket create spec 现已补入 `execution_contract / dispatch_intent`，CEO create-ticket 校验会拒绝不存在、非激活或能力不匹配的 assignee，runtime/provider 会优先按 `execution_contract.execution_target_ref` 选路，同时保留 legacy `role_profile:*` binding 兼容
- `P2-DEC-002` 已完成（2026-04-07）：scheduler 现在会在 `dispatch_intent.assignee_employee_id` 存在时只租约给该 assignee，并把 `dependency_gate_refs / selected_by / wakeup_policy` 收进 `dispatch_intent`；ticket-create 会拒绝自依赖、缺失依赖和简单 dependency cycle；scheduler 会把显式 dependency gate 的坏依赖直接转成结构化失败并触发 CEO 重决策。对现有 `delivery_stage + parent_ticket_id` 主链，这轮按最保守口径只把 `missing / cancelled` 视为硬坏依赖，`FAILED / TIMED_OUT` 仍继续等待节点级 retry / recovery，避免打断 staged follow-up 主链
- `P2-DEC-003` 已完成（2026-04-07）：ticket create spec 现已补入 `input_process_asset_refs[]`，`Context Compiler` 会先把 `input_artifact_refs[]` 兼容转换到过程资产，再统一经 `process asset resolver` 解析；当前已纳入 `artifact / compiled_context_bundle / compile_manifest / compiled_execution_package / meeting_decision_record / closeout_summary / governance_document` 七类过程资产，并把 meeting ADR、closeout summary、治理文档和 runtime 默认 artifact 的输出映射补到 follow-up / maker-checker 输入链
- `P2-DEC-004` 已完成（2026-04-07）：runner 现在固定按 `CEO idle maintenance -> scheduler tick -> leased runtime -> orchestration trace` 编排，artifact cleanup 保持 sidecar；idle wakeup 只会在没有 open approval / incident、没有 active runtime、存在明确重决策信号且最近 ticket / node / approval / incident 变化已经过冷却窗口时触发；每轮 runner 也会写一条 `SCHEDULER_ORCHESTRATION_RECORDED` 审计事件

### `P2-GOV`：文档/设计型角色链纳入与边界收口

状态：`已完成（2026-04-08，6 项已收口；与主线关系：在派单/runtime/过程资产边界收正后，把文档/设计型角色的产物契约、CEO 触发边界和文档真相收进现有 Ticket 主链，不提前打开新增执行角色；当前主线已转入 P2-RLS 角色纳入链）`

- `P2-GOV-003` 已完成（2026-04-07）：治理文档合同现已按最小统一骨架收口为 `architecture_brief / technology_decision / milestone_plan / detailed_design / backlog_recommendation` 五类 schema；`ticket-result-submit` 会把这类结果额外写成 `GOVERNANCE_DOCUMENT` 过程资产，`Context Compiler` 也已能把它们当作一等显式输入消费，同时保留 `linked_document_refs / linked_artifact_refs / source_process_asset_refs / sections / followup_recommendations` 这组结构化关联，不改 runtime 支持矩阵，也不提前启用治理角色 live 执行
- `P2-GOV-004` 已完成（2026-04-08）：CEO 现在可在当前 live 规划角色上创建五类治理文档票；`default_document_kind_refs` 继续只表示建议默认文档，不是硬白名单；后续 `P2-RLS-002` 又把 `architect_primary / cto_primary` 纳入 CEO 治理文档建票入口。`backend / database / platform` 原先只停在 blocked surface，后续 `P0-COR-002/003` 又把 capability-approved backlog follow-up 这条 direct create-ticket 打开
- `P2-GOV-005` 已完成（2026-04-08）：`role_templates_catalog.role_templates[]` 现在会暴露结构化 `mainline_boundary`；这层边界在 `P2-RLS-003` 后已进一步收口为全部 8 个模板都标成 `LIVE_ON_MAINLINE`。`backend / database / platform` 的 blocked surface 现已缩到“一般代码票仍关闭，但 capability-approved backlog follow-up 可直达”，`architect / cto` 继续只走治理文档 live path
- `P2-GOV-006` 已完成（2026-04-08）：`workforce` 目录卡片和 `runtime-provider` 设置抽屉现在都会直接展示这套边界；`P2-RLS-003` 后五类新增角色已从 `Reserved bindings` 移到当前可编辑绑定区，`future_binding_slots` 当前为空
- 当前主线已完成 `P2-RLS`

### `P2-RLS`：新增角色真实纳入链

状态：`已完成（2026-04-08，3 项已全部收口；与主线关系：按最小闭环把五类新增角色从 staffing / CEO partial path 收正到 formal runtime live path；后续 `P0-COR-002/003` 又把 capability-approved backlog follow-up 的 direct CEO create-ticket 补进当前主线）`

- `P2-RLS-001` 已完成（2026-04-08）：`backend / database / platform / architect / cto` 五类模板现在已进入 Board/workforce staffing 主链；Board 可发起 hire / replace 审批，审批通过后这些角色会真实进入 workforce lane，并带上 `source_template_id / source_fragment_refs` 与一致的 `FREEZE / RESTORE / REPLACE` 动作；这轮同时把 board/workforce staffing 与 CEO limited hire 拆开，确保新增角色仍不会提前进入 CEO preset
- `P2-RLS-002` 已完成（2026-04-08）：CEO `HIRE_EMPLOYEE` 现在已放宽到 `backend / database / platform / architect / cto` 五类新增角色；`architect_primary / cto_primary` 已进入 CEO 治理文档建票入口，并通过最小 `execution_contract + legacy role_profile:*` 兼容路径执行；`backend / database / platform` 已进入 meeting participant 匹配与 `BUILD` follow-up owner_role；`CHECK` 仍只给 `checker`，`REVIEW` 仍只给 `frontend_engineer`
- `P2-RLS-003` 已完成（2026-04-08）：`backend / database / platform` 现在已进入正式代码交付 runtime live 路径，并新增 `backend_build / database_build / platform_build` 三类 execution target；`architect_primary / cto_primary` 现在也已进入正式治理文档 runtime 支持矩阵与 provider target label。`role_templates_catalog` 五类新增模板现已标成 `LIVE_ON_MAINLINE`，`runtime-provider.future_binding_slots` 当前为空，Provider 设置抽屉改为直接编辑这五类角色的当前绑定；当前边界已更新为：`backend / database / platform` 可进入 capability-approved backlog follow-up 的 direct CEO create-ticket，但一般代码票仍不开放，`architect / cto` 仍不进入 staged BUILD/CHECK/REVIEW follow-up owner_role

### `P2-PRV`：Provider 策略收口

状态：`已完成（2026-04-08，本轮手动提升并收口；与主线关系：在 provider registry、角色绑定和 runtime live path 已收口后，把任务级 runtime 偏好、静态成本层级和参与策略补进现有 CEO / runtime 审计闭环，同时保持“用户只通过 CEO / Board 施加影响”的边界）`

- `P2-PRV-007` 已完成（2026-04-08）：`ticket-create` 与 `CEO create-ticket` 现在都可选携带 `runtime_preference`，最小支持 `preferred_provider_id / preferred_model`；当前只作为 CEO / 内部兼容入口能力，不新增 Board 侧人工建票入口。运行时与 CEO shadow 审计现在都会稳定写出 `preferred_provider_id / preferred_model / actual_provider_id / actual_model / selection_reason / policy_reason`
- `P2-PRV-008` 已完成（2026-04-08）：provider registry、投影和前端设置抽屉现在都会暴露 `cost_tier / participation_policy`；当前静态策略固定支持 `standard / premium` 两档成本层级，以及 `always_allowed / low_frequency_only` 两档参与策略。provider 选路顺序现已收口为 `任务级偏好 -> 目标/角色绑定 -> 员工 provider -> 默认 provider`；命中高价低频限制时，会自动降级到下一层可用 provider，而不是硬失败
- 当前低频高杠杆路径按现有主线语义固定收口：`ceo_shadow`、scope/governance 文档链、`architect / cto` 治理文档属于低频高杠杆；`BUILD / CHECK / REVIEW / CLOSEOUT` 属于高频执行或高频审查；本轮不引入预算自适应、动态频率控制或新的策略引擎

### `P2-PRV-009 / P2-PRV-010`：路线外 provider center 重构补记

状态：`已完成（2026-04-09，路线外特性开发；与主线关系：当前主线任务空窗，且用户明确要求重构 provider 配置体验，所以按路线外补记收口，不回头改动冻结边界）`

- `P2-PRV-009` 已完成（2026-04-09）：Provider Settings 现在已改成多 provider 配置中心；`runtime-provider` 读面和保存命令都按 `providers[] / provider_model_entries[] / role_bindings[]` 工作。provider 落库时会自动补 alias 和默认 `max_context_window=1000000`；旧固定 provider 配置升级后按空配置处理，不做迁移保留
- `P2-PRV-010` 已完成（2026-04-09）：OpenAI-compatible provider 现在固定优先走 Responses 流式，连通性测试确认不支持时会回退到 Responses 非流式，并把返回的标准化 provider 结果用于保存；模型刷新接口会拉取远端模型列表，只保留仍存在的已勾选模型。CEO / role 绑定现在改成有序 `provider_model_entry_refs[]`，并支持 `max_context_window_override`；role 未配置时继承 CEO 的模型条目和上下文窗口
- 当前新体验只真实开放 OpenAI-compatible Responses provider；`claude/gemini` 只保留类型占位，`Claude Code CLI` 兼容执行路径不进入这轮配置主流程

### `P2-M7`：集成、文档与交付口径收口

状态：`已完成（2026-04-06，5 项已全部收口；后续默认主线已转入 P2-DEC 前置解耦批次）`

- `P2-M7-001` 已完成：`TODO`、任务库、里程碑和冻结后置文档已改成 `M7` 为当前主线，`P1-CLN-002/003` 明确降级为冻结后置而非已完成
- `P2-M7-002` 已完成：Review Room 现在会展示 evidence `source_ref`，前端契约已对齐后端现状
- `P2-M7-003` 已完成：dashboard completion 投影与完成卡片现在会显示 closeout 文档同步摘要、更新数和 follow-up 数
- `P2-M7-004` 已完成：M7 首批最小回归已补齐，当前验证基线更新为 backend `436 passed`、frontend build passed、frontend `66 passed`
- `P2-M7-005` 已完成：Review Room 和 dashboard completion 已把现有 `artifact_ref`、artifact 型 `source_ref` 接到统一只读查看入口，沿用本地 artifact metadata / preview / content 接口，不新建 artifact 浏览器

后续顺序统一看 [milestone-timeline.md](milestone-timeline.md)。

### `P2-RET-006`：执行包最小组织上下文与 L1 收口

状态：`已完成（2026-04-06，本轮显式纳入；与主线关系：继续收紧 worker 执行包，避免只靠 persona_summary 推进主链执行）`

- `P2-RET-006` 已完成：`compiled_execution_package` 与 rendered `SYSTEM_CONTROLS` 现在都会携带结构化 `org_context`，最小暴露 `upstream_provider / downstream_reviewer / collaborators / escalation_path / responsibility_boundary`
- 当前组织上下文按“动态关系版、角色优先”收口：优先复用现有 workflow `parent / dependent / sibling` 关系；缺失时才回退到当前 ticket 的预期下游 reviewer，不新建持久化或 retrieval 通道
- 当前回归已覆盖 root ticket、parent/dependent/sibling 关系和 worker-runtime execution package 读面；验证基线更新为 backend `437 passed`、frontend build passed、frontend `70 passed`

### `P2-MTG-011`：会议 ADR 化与会议来源后续票压缩上下文

状态：`已完成（2026-04-07，本轮手动纳入；与主线关系：把会议正式共识压成默认消费的决策视图，避免后续实施继续读会议流水）`

- `P2-MTG-011` 已完成：会议 `consensus_document@1` 现在可选携带结构化 `decision_record`，固定暴露 `format / context / decision / rationale / consequences / archived_context_refs`
- `MeetingRoom` 现在优先展示 ADR 化决策视图，再展示轮次审计轨迹；会议过程继续保留为审计材料，不再作为默认消费面
- 只有 `MEETING_ESCALATION` 批准后生成的 follow-up ticket 会额外注入 ADR `decision + consequences` 到 `semantic_queries` 与 `acceptance_criteria`；非会议来源的 `consensus_document` 路径保持不变
- 当前回归已覆盖 schema 校验、meeting projection 读 ADR、会议 follow-up 票 ADR 摘要注入和前端决策视图；验证基线更新为 backend `444 passed`、frontend build passed、frontend `72 passed`

### `P2-CEO-002`：CEO 复用优先决策策略

状态：`已完成（2026-04-07，本轮手动纳入；与主线关系：让 live CEO 在已有交付或会议已收敛时优先复用现状、恢复现有工作或保持不动作，减少平行新动作）`

- `P2-CEO-002` 已完成：CEO shadow snapshot 现在会暴露当前 workflow 内的 `reuse_candidates`，最小包含最近 `5` 个已完成 ticket 和最近 `3` 个已关闭会议的只读摘要
- OpenAI Compat live CEO prompt 现在会显式先检查 `reuse_candidates`，优先 `NO_ACTION`、`RETRY_TICKET` 或等待现有工作继续，而不是默认新建平行 ticket、额外开会或补招人
- 当前按最保守口径实现 completed ticket 摘要：继续从 `TICKET_CREATED` 取 `output_schema_ref`，但因普通 `TICKET_CREATED` payload 没有 `summary`，当前回退到完成态 `completion_summary`；会议复用候选只读 `meeting_projection`，不读 artifact 正文
- 当前回归已覆盖 snapshot `reuse_candidates`、live prompt 复用优先文案和 provider 渲染路径；验证基线更新为 backend `446 passed`、frontend build passed、frontend `72 passed`

### `P2-PRV-001 / P2-PRV-005 / P2-PRV-006`：多协议 provider registry 与角色路由首版

状态：`已完成（2026-04-07，本轮手动纳入；与主线关系：把 runtime provider 从单一 OpenAI 开关收口成最小可用的多协议配置中心，并让 CEO / Worker 都能按角色绑定选 provider）`

- `P2-PRV-001` 已完成：`runtime-provider-config.json` 现在已收口成 provider center 结构；当前真实读写主形状以 `providers[] / provider_model_entries[] / role_bindings[]` 为准，旧固定 provider 配置后续已被 `P2-PRV-009` 进一步收正为“升级后按空配置处理，不再迁移保留”
- 当前运行时兼容路径仍保留 `prov_openai_compat` 与 `prov_claude_code` 两类 adapter；但用户新配置主流程在 `P2-PRV-009 / P2-PRV-010` 后只真实开放 OpenAI-compatible Responses provider
- `P2-PRV-006` 已完成：运行时和 CEO shadow 都会先解析 CEO / role 的模型条目绑定，再回退员工 `provider_id` 兼容字段，最后才回退默认 provider 或本地 deterministic；当前角色绑定还支持 `max_context_window_override`
- `runtime-provider` 投影和前端 `ProviderSettingsDrawer` 现在都升级为 provider center：会暴露 `providers / provider_model_entries / role_bindings`、模型列表多选、连通性测试和模型刷新；未来治理角色只展示当前真实绑定，不写成新能力
- 当前实现只补最小审计字段：runtime provider 执行与 fallback 现在会显式记录 `provider_model_entry_ref / preferred_provider_id / preferred_model / actual_provider_id / actual_model / effective_max_context_window`；未开启新的预算引擎或后台主动探活
- `P2-PRV-005` 已完成：新增后端回归覆盖旧配置迁移、角色路由优先级、Claude CLI adapter、CEO/Worker 路由与 provider pause 兼容路径；前端回归补上 provider center 的未来治理角色只读占位；当前验证基线更新为 backend `453 passed`、frontend build passed、frontend `73 passed`

### `P2-PRV-002 / P2-PRV-003 / P2-PRV-004`：provider 能力标签、基础健康明细与简单 fallback 路由

状态：`已完成（2026-04-07，本轮手动纳入；与主线关系：把 provider center 从“能配置”收口到“能表达能力、能看清健康、能在窄失败场景下切到合格备选 provider”）`

- `P2-PRV-002` 已完成：`RuntimeProvider` 配置、投影和前端设置抽屉现在都会暴露结构化 `capability_tags[]`；当前只开放 `structured_output / planning / implementation / review` 四个封闭标签
- `P2-PRV-003` 已完成：`runtime-provider` 投影里的每个 provider 现在都会暴露 `health_status / health_reason`；当前健康明细只基于启停、配置完整度、provider incident pause 和 Claude 命令可解析性，不加主动探活
- `P2-PRV-004` 已完成：provider 现在支持最小 `fallback_provider_ids[]`；运行时与 CEO live proposal 只会在 `PROVIDER_RATE_LIMITED / UPSTREAM_UNAVAILABLE` 时按顺序尝试满足目标能力底线的备选 provider，鉴权错误、坏响应和配置不完整仍直接回退现有 deterministic 路径
- 当前能力底线固定按运行目标收口：`ceo_shadow / ui_designer_primary` 需要 `structured_output + planning`，`frontend_engineer_primary` 需要 `structured_output + implementation`，`checker_primary` 需要 `structured_output + review`
- `runtime-provider-upsert` 现在会拒绝未知能力标签、重复标签、未知 fallback provider、自引用和重复 fallback 项；当前验证基线更新为 backend `461 passed`、frontend build passed、frontend `73 passed`

### `P2-GOV-001`：治理模板数据结构收口

状态：`已完成（2026-04-07，本轮手动纳入；与主线关系：为后续治理角色和文档型任务链补单点数据结构与只读可见性，不提前启用执行路径）`

- `P2-GOV-001` 已完成：后端先补了治理模板基础目录，最小固定 `cto_governance / architect_governance` 两组只读模板和五类文档 metadata ref
- 这层基础目录当前已被 `P2-GOV-002` 扩成统一只读 `role_templates_catalog`；`P2-GOV-001` 现在只保留“打底”语义，不再单独作为前端当前真相字段暴露
- 当前保持保守边界：`cto_primary / architect_primary` 现在已进入 CEO 文档型建票链，但仍未进入 formal runtime 支持矩阵或 provider target label；`P2-GOV-001` 只为后续文档链和角色纳入链提供基础结构

### `P2-GOV-002`：统一角色/技能模板目录与组合元数据

状态：`已完成（2026-04-07，本轮手动纳入；与主线关系：先把未来角色纳入所需的角色真相、模板片段和前端只读展示收口成单点目录，不提前启用新工作链）`

- `P2-GOV-002` 已完成：后端新增统一只读 `role_templates_catalog`，固定暴露 `3` 个 live 执行模板、`3` 个未来执行模板、`2` 个治理模板、`5` 类文档 metadata ref 和 `9` 个模板片段
- `workforce` 投影现在改为暴露 `role_templates_catalog`；当前 live worker 还会额外返回 `source_template_id / source_fragment_refs`，把现有 `skill_profile / personality_profile / aesthetic_profile` 映射回高层模板来源
- `runtime-provider.future_binding_slots` 现在改从同一目录筛出未启用模板，最小覆盖 `backend_engineer / database_engineer / platform_sre / architect / cto`；当前保守边界已收窄为“不把这些角色写成 formal runtime live”；其中 `architect / cto` 已在 `P2-RLS-002` 打开 CEO 治理文档建票入口
- 本轮已同时重排后续任务包：`P2-GOV-003` 到 `P2-GOV-006` 现在只负责“文档/设计链纳入与边界”，新增 `P2-RLS-001` 到 `P2-RLS-003` 专门承接后续 staffing / CEO / runtime 真实纳入链
- 在本轮愿景重排后，这些后续任务都要排在 `P2-DEC-001` 到 `P2-DEC-004` 之后；当前先收正 role/runtime、CEO/scheduler 和过程资产的基础边界，再继续角色纳入
- 当前验证基线更新为 backend `464 passed`、frontend build passed、frontend `73 passed`

## 已降级出当前主线（冻结后置）

- `P1-CLN-002`：主线 command 侧已解耦，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留 `tenant_id/workspace_id` shape
- `P1-CLN-003`：`ticket-result-submit` 已与 upload session 解耦，但 upload 导入入口和 upload session 存储仍保留
- 这两项 blocker 没有消失，只是不再占用当前批次；详细约束统一看 [task-backlog/active.md](task-backlog/active.md) 和 [todo/postponed.md](todo/postponed.md)

## `C1` 条件批次

只有在触发条件成立时，下面这些任务才进入真实执行：

| 任务 | 状态 | 触发条件 | 说明 |
|---|---|---|---|
| `P2-CEO-001` | 已完成（2026-04-07，本轮手动纳入） | 已满足：本轮手动提升为当前批次，补上初始化阶段受控需求澄清板审 | `project-init` 现在支持显式 `force_requirement_elicitation`，也会在保守启发式命中明显弱输入时先打开 `REQUIREMENT_ELICITATION`；董事会在现有 Review Room 里提交结构化答卷后，再继续进入首个 scope review |
| `P2-RET-006` | 已完成（2026-04-06，本轮显式纳入） | 已满足：本轮手动提升为当前批次，收紧执行包最小组织上下文与 `L1` | 已在 execution package / rendered `SYSTEM_CONTROLS` 补入结构化 `org_context`，不新增 `L2/L3` 或新存储 |
| `P2-MTG-011` | 已完成（2026-04-07，本轮手动纳入） | 已满足：本轮手动提升为当前批次，压缩会议默认消费面 | 会议 `consensus_document@1` 现在可选携带 `decision_record`；Meeting Room 默认先看 ADR 决策视图；只有会议来源 follow-up ticket 会额外注入 ADR 摘要 |
| `P2-GOV-007` | 已完成（2026-04-06） | 已触发：closeout / review 反复出现“代码已改但证据或文档没同步” | 已在 `delivery_closeout_package@1`、closeout checker 文案和 runtime review 摘要补入结构化 `documentation_updates`，保持 soft rule，不加硬状态机门禁 |

## 当前入口

- 当前任务索引：[task-backlog.md](task-backlog.md)
- 当前活跃任务明细：[task-backlog/active.md](task-backlog/active.md)
- 已完成能力与收口批次：[todo/completed-capabilities.md](todo/completed-capabilities.md)
- 冻结范围与远期储备：[todo/postponed.md](todo/postponed.md)
- 后续顺序与条件批次：[milestone-timeline.md](milestone-timeline.md)
