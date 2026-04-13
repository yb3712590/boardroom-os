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
