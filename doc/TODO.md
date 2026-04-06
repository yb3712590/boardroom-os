# TODO

> 最后更新：2026-04-07
> 本文件仍是项目唯一的待办真相源，但正文只保留当前批次与条件批次。已完成能力改看 `todo/completed-capabilities.md`，远期储备改看 `todo/postponed.md` 与 `milestone-timeline.md`。

## 当前阶段目标

把项目继续收敛成一个本地单机可运行、可验证、可演示的 Agent Delivery OS MVP：

- 事件溯源状态总线是真相源
- Ticket 驱动无状态执行器推进工作
- Maker-Checker 和 Review 闭环真实可用
- React 只做最薄治理壳，不接管工作流真相

## 当前基线（2026-04-07）

- backend：`./backend/.venv/bin/pytest tests/ -q` -> `463 passed`
- frontend：`npm run build` -> passed，`npm run test:run` -> `73 passed`
- CEO 当前真实执行集：`CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / REQUEST_MEETING`；`ESCALATE_TO_BOARD` 仍是 `DEFERRED_SHADOW_ONLY`

## 当前批次

### `P2-M7`：集成、文档与交付口径收口

状态：`已完成（2026-04-06，5 项已全部收口；当前没有新的可直接开启主线任务）`

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

- `P2-PRV-001` 已完成：`runtime-provider-config.json` 现在改成 registry 结构，固定暴露 `default_provider_id / providers[] / role_bindings[]`；旧版单 provider JSON 会自动迁移到新结构
- 当前 registry 首版真实支持两个 adapter：`prov_openai_compat` 和 `prov_claude_code`；Gemini 原生 adapter 仍未纳入，后续如果需要，先走 OpenAI-compatible 地址
- `P2-PRV-006` 已完成：运行时和 CEO shadow 都会先解析角色绑定，再回退员工 `provider_id` 兼容字段，最后才回退默认 provider 或本地 deterministic；当前真实 target 只开放 `ceo_shadow / ui_designer_primary / frontend_engineer_primary / checker_primary`
- `runtime-provider` 投影和前端 `ProviderSettingsDrawer` 现在都升级为最小 provider center：可编辑 OpenAI / Claude 配置、默认 provider 和当前真实角色绑定；未来治理角色只展示只读占位，不写成已启用能力
- 当前实现只补最小审计字段：runtime provider 执行与 fallback 现在会显式记录 `preferred_provider_id / preferred_model / actual_provider_id / actual_model / adapter_kind`；未开启任务级 override、复杂 fallback 路由、成本分层或独立健康探测器
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

- `P2-GOV-001` 已完成：后端新增共享 `governance_templates` catalog，最小固定两组只读 role template：`cto_governance`、`architect_governance`
- catalog 当前同时暴露五类文档型 metadata ref：`architecture_brief / technology_decision / milestone_plan / detailed_design / backlog_recommendation`；只做 metadata，不提前定义 `P2-GOV-003` 的完整输出契约
- `workforce` 投影现在会额外暴露只读 `governance_templates`，`runtime-provider` 的未来治理角色槽位也改成从同一 catalog 派生；前端 `WorkforcePanel` 与 `ProviderSettingsDrawer` 现在看到的是同一份后端真相，而不是各自硬编码
- 当前保持保守边界：`cto_primary / architect_primary` 仍未进入 runtime 支持矩阵、staffing 动作或 CEO 文档型建票链；本轮验证基线更新为 backend `463 passed`、frontend build passed、frontend `73 passed`

本轮完成后，当前剩余未关闭项仍都属于冻结后置或后置增强；当前再次回到“没有可直接开启的默认主线任务”状态。

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
