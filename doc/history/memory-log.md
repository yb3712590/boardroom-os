# Memory Log

> This file is intentionally compact. Stable baseline context lives in `doc/history/context-baseline.md`.
> Detailed recent logs now live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`
> - `doc/history/archive/memory-log-detailed-2026-04-03_to_2026-04-06.md`

## How To Use This File

- Read `doc/history/context-baseline.md` first for stable rules and architecture.
- Read `doc/TODO.md` next for the current action list.
- Use this file only for recent changes that still affect implementation decisions.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Current Mainline Truth

- Current executable truth lives in `doc/mainline-truth.md`.
- This file is recent memory, not a second truth source.

## Recent Memory

### 2026-04-03

- `delivery_check_report@1` 获得独立 checker gate，final review 通过后会自动补 `delivery_closeout_package@1`，workflow 完成口径因此改成 closeout 真正收口
- `doc/mainline-truth.md` 成为当前代码真相入口，provider 健康标签也收口成 `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`
- `frontend_engineer` 已有独立 runtime profile，scope kickoff 只保留兼容 alias

### 2026-04-04

- CEO 从影子进入有限执行首轮：当前真实执行 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / REQUEST_MEETING`，`ESCALATE_TO_BOARD` 仍保持 `DEFERRED_SHADOW_ONLY`
- `project-init` 的首个 scope kickoff 票改由 CEO 发起，`scheduler_runner.py` 也会在空转时做受控 idle maintenance
- 前端数据层拆分和 persona 真相源收口完成，执行包当前会携带 `persona_summary`

### 2026-04-05

- `P0-INT-*` 收口为八条明确集成验收任务，主线 deterministic、provider、incident、frontend 烟囱覆盖矩阵已明确
- 最小会议室主线落地：`meeting-request`、`TECHNICAL_DECISION` 状态机、会议投影和只读 `MeetingRoomDrawer` 已进入真实闭环
- 自动会议仍只覆盖窄触发条件，不递归 reopen `MEETING_ESCALATION`
- `P1-CLN-005`、`P1-CLN-006` 已关闭，冻结边界、测试归属和迁移前置条件已写进 `mainline_truth.py`

### 2026-04-06

- `P1-CLN-001` 与 `P1-CLN-004` 已完成 shim 迁移：真实实现分别进入 `backend/app/_frozen/worker_admin/` 和 `backend/app/_frozen/worker_runtime/`
- `P1-CLN-002` 与 `P1-CLN-003` 的 blocker 已进一步收口：共享 scope data shape 仍保留，upload 导入入口与 session 存储仍保留
- `FrozenCapabilityBoundary` 现在还会记录 `api_surface_groups` 与 `storage_table_refs`，接口分组也有 `api_surface.py` 回归保护
- 高频文档入口这轮已按新愿景重整：`README`、`TODO`、`task-backlog`、`milestone-timeline` 和 `postponed` 已重新分层，不再把当前批次、已完成补记和远期储备混写
- `P2-GOV-007` 已按 soft rule 收口：`delivery_closeout_package@1` 可选携带 `documentation_updates`，closeout checker / runtime review 会显式总结文档同步状态，但不会把 `FOLLOW_UP_REQUIRED` 自动升级成硬门禁
- runtime 生成 structured artifact 的写回顺序已收正：`implementation_bundle`、`delivery_check_report`、`delivery_closeout_package` 的默认 artifact 现在会持久化最终 payload，而不是先写空壳再补内存结果
- `P2-RET-001` 到 `P2-RET-005` 已完成：SQLite 现在有 `review / incident / artifact` 三通道 FTS5 检索索引，repository 检索改成“查询前懒刷新 + FTS 命中 + 稳定排序去重”
- `P2-RET-006` 已完成：execution package 与 rendered `SYSTEM_CONTROLS` 现在都会携带结构化 `org_context`，最小暴露上游提供者、下游 reviewer、活跃 sibling 协作者、升级路径和职责边界；缺 direct dependent 时会回退到预期 reviewer，不新建持久化或 retrieval 通道
- artifact 检索继续保留原有粗匹配边界：只有路径 / `kind` / `media_type` 先命中关键词时，正文命中才会进入历史 retrieval summary，避免把当前输入附件正文误回灌进执行包
- 当前主线已从 `P2-B` 切到 `M7`：`P1-CLN-002/003` 降级为冻结后置，`P2-M7-001` 到 `P2-M7-005` 已全部完成；当前没有新的可直接开启主线任务
- 前端现在有统一 `ArtifactPreviewDrawer`：Review Room 的 artifact 型 evidence `source_ref`、option `artifact_refs` 和 completion card 的 final / closeout artifact refs 都会接到现有本地 artifact metadata / preview / content 只读接口，不新建 artifact 浏览器
- completion 投影现在会汇总 closeout 文档同步摘要、更新数和 follow-up 数；Review Room 也会展示 evidence `source_ref`，当前验证基线更新为 backend `437 passed`、frontend build passed、frontend `70 passed`
- `P2-CEO-001` 已完成：`project-init` 现在支持显式 `force_requirement_elicitation`，也会在保守启发式命中明显弱输入时先打开 `REQUIREMENT_ELICITATION`
- 初始化澄清继续复用现有 `Inbox -> Review Room -> board-*` 审批流；董事会在 Review Room 提交结构化 `elicitation_answers` 后，`APPROVE` 会生成 `requirements-elicitation` / enriched board brief artifact 并继续进入 scope kickoff，`MODIFY_CONSTRAINTS` 会重新打开一版澄清板审
- `P2-MTG-011` 已完成：会议 `consensus_document@1` 现在可选携带 ADR 化 `decision_record`，固定暴露 `format / context / decision / rationale / consequences / archived_context_refs`
- `build_meeting_projection` 现在会从会议主 artifact 读出 `decision_record`，Meeting Room 默认先展示 ADR 决策视图，再把 round timeline 留作 audit trail；会议 follow-up ticket 只在 `MEETING_ESCALATION` 路径额外注入 ADR `decision + consequences`
- 当前验证基线更新为 backend `444 passed`、frontend build passed、frontend `72 passed`

### 2026-04-07

- `P2-CEO-002` 已完成：CEO shadow snapshot 现在会暴露当前 workflow 内 `reuse_candidates.recent_completed_tickets / recent_closed_meetings`，OpenAI Compat live prompt 会先检查这些复用候选，再决定是否 `NO_ACTION`、`RETRY_TICKET`、`REQUEST_MEETING` 或 `HIRE_EMPLOYEE`
- 这轮保持保守边界：deterministic fallback 完全不变，不新增 `CEOAction` 字段，也不把 artifact/ADR refs 直接注入新建 ticket；当前 completed ticket 摘要因普通 `TICKET_CREATED` payload 无 `summary`，回退到完成态 `completion_summary`
- `P2-PRV-001 / P2-PRV-005 / P2-PRV-006` 已完成：runtime provider 配置已从单一 OpenAI 开关切到最小 registry，首版真实支持 `OpenAI Compat` 与 `Claude Code CLI` 两个 adapter，并开放 `ceo_shadow / ui_designer_primary / frontend_engineer_primary / checker_primary` 的角色绑定
- 这轮保持保守边界：Gemini 原生 adapter、任务级模型 override、复杂 fallback 路由、成本分层和后台健康探测都未开启；现有员工投影里的 `provider_id` 仍保留为兼容字段和展示字段
- `runtime-provider` 投影与前端设置抽屉现在都会暴露 `default_provider_id / providers / role_bindings / future_binding_slots`；未来治理角色只做只读占位，不写成已启用能力
- `P2-PRV-002 / P2-PRV-003 / P2-PRV-004` 已完成：provider registry 现在会暴露结构化 `capability_tags[]`、每个 provider 的 `health_status / health_reason` 和最小 `fallback_provider_ids[]`
- provider 能力底线当前固定按运行目标收口：`ceo_shadow / ui_designer_primary` 需要 `structured_output + planning`，`frontend_engineer_primary` 需要 `structured_output + implementation`，`checker_primary` 需要 `structured_output + review`
- provider-to-provider failover 现在只覆盖 `PROVIDER_RATE_LIMITED / UPSTREAM_UNAVAILABLE`；鉴权错误、坏响应和配置不完整仍直接回退现有 deterministic 路径，board-facing evidence 也继续只突出 deterministic fallback
- `P2-GOV-001` 已完成：后端新增单点 `governance_templates` catalog，固定暴露 `cto_governance / architect_governance` 两组只读 role template 和五类文档 metadata ref；`workforce` 投影与 `runtime-provider.future_binding_slots` 现在都从同一 catalog 派生
- 这轮保持保守边界：治理模板当前只做只读数据结构与前端可见性，不启用 `cto_primary / architect_primary` runtime 执行、不扩 staffing 动作，也不提前定义文档型输出 schema
- `P2-GOV-002` 已完成：统一只读 `role_templates_catalog` 现在覆盖 `3` 个 live 执行模板、`3` 个未来执行模板、`2` 个治理模板、`5` 类文档 metadata ref 和 `9` 个模板片段；`workforce` worker 还会额外暴露 `source_template_id / source_fragment_refs`
- `runtime-provider.future_binding_slots` 现在改从统一目录筛出未启用模板，最小覆盖 `backend_engineer / database_engineer / platform_sre / architect / cto`；这轮仍不把这些角色接进 staffing、CEO 建票、runtime 或执行包
- 后续真实纳入链已拆成两段：`P2-GOV-003` 到 `P2-GOV-006` 负责文档/设计链与边界，新增 `P2-RLS-001` 到 `P2-RLS-003` 专门承接 staffing / CEO / runtime 纳入
- 董事会愿景本轮追加了 `#76` 到 `#80`：role 模板不再充当 runtime 执行键，原子任务输入输出经由过程资产闭环，scheduler 只做确定性 readiness / lease / wakeup，CEO 不进入状态机，并继续保留事件 + 定时双路径唤醒防停滞
- 新的最高优先级任务包已改为 `P2-DEC-001` 到 `P2-DEC-004`；`P2-GOV-003` 到 `P2-GOV-006` 和 `P2-RLS-001` 到 `P2-RLS-003` 继续保留，但顺序统一排在这组前置解耦任务之后
- `P2-DEC-001` 已完成：ticket create spec 现在会补 `execution_contract / dispatch_intent`，CEO create-ticket 校验会拒绝不存在、非激活或能力不匹配的 assignee；runtime/provider 现在优先按 `execution_contract.execution_target_ref` 选路，并兼容旧 `role_profile:*` binding
- 当前 execution target catalog 先按主线收口为 5 类：`scope_consensus / frontend_build / checker_delivery_check / frontend_review / frontend_closeout`
- `P2-DEC-002` 已完成：scheduler 现在会在 `dispatch_intent.assignee_employee_id` 存在时只租约给该 assignee，但仍要求 assignee 出现在当前可用 worker 候选里；`dispatch_intent` 也已补入 `dependency_gate_refs / selected_by / wakeup_policy`
- `ticket-create` 现在会拒绝显式 dependency gate 的自依赖、缺失依赖和简单 cycle；scheduler 遇到显式 dependency gate 指向 `FAILED / TIMED_OUT / CANCELLED` ticket 时，会直接记结构化 `TICKET_FAILED` 并触发 CEO 重决策
- 对现有 `delivery_stage + parent_ticket_id` staged follow-up 主链，这轮按最保守口径只把 `missing / cancelled` 视为硬坏依赖；`FAILED / TIMED_OUT` 仍继续等待同节点 retry / recovery，避免在 build/check/review staged 票链上提前打死下游票
- `P2-DEC-003` 已完成：ticket create spec、compile request 和 maker-checker / approval follow-up 现在都补入 `input_process_asset_refs[]`；旧 `input_artifact_refs[]` 会兼容映射到同一套过程资产入口
- 当前新增统一 `process asset resolver`，已纳入 `artifact / compiled_context_bundle / compile_manifest / compiled_execution_package / meeting_decision_record / closeout_summary / governance_document` 七类来源；Context Compiler 现在只消费 resolver 输出的规范化文本块或 JSON 块
- runtime 完成事件现在会写回结构化 `produced_process_assets[]`；meeting ADR、closeout summary、治理文档和 runtime 默认 artifact 会自动回灌到 follow-up ticket 与 internal checker 输入链
- `P2-DEC-004` 已完成：runner 现在固定按 `CEO idle maintenance -> scheduler tick -> leased runtime -> orchestration trace` 编排，artifact cleanup 保持为 sidecar；每轮会额外写一条 `SCHEDULER_ORCHESTRATION_RECORDED` 审计事件
- idle wakeup 现在会基于 `NO_TICKET_STARTED / READY_TICKET / INVALID_DEPENDENCY_OR_DISPATCH / FAILED_TICKET` 信号和最近 ticket / node / approval / incident 变化的冷却窗口决定是否触发，不再把 workflow 行本身的旧时间戳当作防停滞依据
- `P2-GOV-003` 已完成：治理文档合同现已按最小统一骨架收口为 `architecture_brief / technology_decision / milestone_plan / detailed_design / backlog_recommendation` 五类 schema，并统一保留 `linked_document_refs / linked_artifact_refs / source_process_asset_refs / decisions / constraints / sections / followup_recommendations`
- 过程资产入口现已新增 `GOVERNANCE_DOCUMENT`：`ticket-result-submit` 会为治理文档结果额外写回该类过程资产，`Context Compiler` 也能直接把它当作一等显式输入消费；runtime 支持矩阵、staffing 和 CEO live 建票边界仍保持不变
- 文档入口规则这轮补成“混合版分层”：继续保留现有高频真相栈命名，`doc/design/*` 继续承担详细设计层，文档关系要求用索引或相关文档段落显式回链
- `P2-GOV-004` 已完成：CEO 现在可在 `ui_designer_primary / frontend_engineer_primary` 两个 live 规划角色上创建五类治理文档票；`default_document_kind_refs` 继续只表示建议默认文档，不再作为硬白名单
- execution target catalog 现在扩到 `7` 类：在原有 `scope_consensus / frontend_build / checker_delivery_check / frontend_review / frontend_closeout` 之外，新增 `scope_governance_document / frontend_governance_document` 两类 planning 文档目标；五类治理文档也已进入 runtime 支持矩阵，但 `architect / cto / backend / database / platform` 仍未纳入 live 路径
- 当 CEO 创建的后续票显式挂在治理文档父票下时，建票路径会自动继承父票输出的 `GOVERNANCE_DOCUMENT` 过程资产，避免下游票继续手工补这类引用
- `P2-DEC-*` 与 `P2-GOV-004` 已全部收口，当前下一步转入 `P2-GOV-005`；本轮全量验证结果更新为 backend `493 passed`、frontend build passed、frontend `73 passed`

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, `doc/TODO.md`, `doc/history/context-baseline.md`, and then this file before touching the archive.
- Keep only facts that still change implementation decisions here; move raw logs and exhaustive verification into archive files.
