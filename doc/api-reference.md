# Boardroom OS API Reference

> 最后更新：2026-04-20  
> 这份文档按当前代码真实暴露的路由写，不按设计草案写。接口分组来自 `backend/app/api/*.py`，并由 `backend/tests/test_api_surface.py` 固定。

## 1. 怎么看这份文档

如果你要判断接口是不是当前主线，先看这三个标签：

- `当前主线`：现在推荐直接使用，属于本地 MVP 的真实控制面
- `已下线`：旧兼容面已经从当前应用入口移除，不再暴露路由
- `默认是否建议使用`：站在今天的主线角度，是否建议作为第一选择

完整字段约束以 `backend/app/contracts/` 为准。这里主要回答三件事：

- 接口在哪一组
- 它现在属于主线还是已下线兼容面
- 关键用途和关键输入是什么

## 2. 共通约定

投影接口一般返回：

- `schema_version`
- `generated_at`
- `projection_version`
- `cursor`
- `data`

命令接口一般返回 `CommandAckEnvelope`，用于表示：

- 命令是否已被接受
- 命令 ID / 事件游标
- 当前命令写入后的最小确认信息

## 3. 路由分组总览

| 分组 | 代码入口 | 当前边界 | 默认是否建议使用 |
|------|----------|----------|------------------|
| `commands` | `backend/app/api/commands.py` | 当前主线 | 是 |
| `projections` | `backend/app/api/projections.py` | 当前主线 | 是 |
| `artifacts` | `backend/app/api/artifacts.py` | 当前主线 | 是 |
| `artifact-uploads` | `backend/app/api/artifact_uploads.py` | 当前主线中的受限大文件链路 | 是 |
| `events` | `backend/app/api/events.py` | 当前主线 | 是 |

## 4. Commands

这组接口都在 `/api/v1/commands/*`，统一返回 `CommandAckEnvelope`。

| 接口 | 边界标签 | 默认是否建议使用 | 用途 | 关键请求字段 |
|------|----------|------------------|------|--------------|
| `POST /api/v1/commands/project-init` | 当前主线 | 是 | 初始化 workflow；默认继续触发首个 scope review 链路，必要时先打开初始化需求澄清板审，并创建受管项目工作区 | `north_star_goal`、`hard_constraints`、`budget_cap`、`deadline_at`、`force_requirement_elicitation`、`project_methodology_profile?`、`idempotency_key` |
| `POST /api/v1/commands/runtime-provider-upsert` | 当前主线 | 是 | 保存本地 runtime provider registry | `default_provider_id`、`providers[]`、`role_bindings[]` |
| `POST /api/v1/commands/employee-hire-request` | 当前主线 | 是 | 发起员工招聘审批 | `workflow_id`、`employee_id`、`role_type`、`role_profile_refs`、人格画像、`provider_id` |
| `POST /api/v1/commands/employee-replace-request` | 当前主线 | 是 | 发起换人审批 | `workflow_id`、`replaced_employee_id`、`replacement_employee_id`、替代员工画像 |
| `POST /api/v1/commands/employee-freeze` | 当前主线 | 是 | 立即冻结员工，阻止新 dispatch / lease / start | `workflow_id`、`employee_id`、`frozen_by`、`reason` |
| `POST /api/v1/commands/employee-restore` | 当前主线 | 是 | 立即恢复 `FROZEN -> ACTIVE` | `workflow_id`、`employee_id`、`restored_by`、`reason` |
| `POST /api/v1/commands/meeting-request` | 当前主线 | 是 | 手动创建 `TECHNICAL_DECISION` 会议请求 | `workflow_id`、`ticket_id`、`meeting_type`、`topic`、`participant_ids` |
| `POST /api/v1/commands/ticket-create` | 当前主线 | 是 | 创建普通 ticket | `workflow_id`、`node_id`、`role_profile_ref`、`output_schema_ref`、`allowed_write_set`、`runtime_preference?`、`deliverable_kind?`、`required_read_refs?`、`doc_update_requirements?`、`git_policy?` |
| `POST /api/v1/commands/ticket-lease` | 当前主线 | 是 | 显式 lease 一个待执行 ticket | `workflow_id`、`ticket_id`、`node_id`、`leased_by` |
| `POST /api/v1/commands/ticket-start` | 当前主线 | 是 | 把 `LEASED` ticket 切到执行中 | `workflow_id`、`ticket_id`、`node_id`、`started_by` |
| `POST /api/v1/commands/ticket-heartbeat` | 当前主线 | 是 | 给执行中 ticket 续活 | `workflow_id`、`ticket_id`、`node_id`、`reported_by` |
| `POST /api/v1/commands/ticket-fail` | 当前主线 | 是 | 显式记录失败并触发既有恢复链 | `workflow_id`、`ticket_id`、`node_id`、`failure_kind`、`failure_message` |
| `POST /api/v1/commands/ticket-complete` | 当前主线 | 保守使用 | 旧完成接口，仍保留兼容 | `workflow_id`、`ticket_id`、`node_id`、结果摘要 |
| `POST /api/v1/commands/ticket-result-submit` | 当前主线 | 是 | 当前统一的结构化结果写回入口；代码票和结构化文档票都会在这里走各自 hard gate | `workflow_id`、`ticket_id`、`node_id`、`result_status`、`schema_version`、`payload`、`artifact_refs`、`written_artifacts`、`verification_evidence_refs?`、`git_commit_record?` |
| `POST /api/v1/commands/scheduler-tick` | 当前主线 | 是 | 显式推动一次调度 tick | `workers`、`max_dispatches`、`idempotency_key` |
| `POST /api/v1/commands/incident-resolve` | 当前主线 | 是 | 关闭 incident 并按策略恢复 | `incident_id`、`resolved_by`、`resolution_type`、`resolution_summary` |
| `POST /api/v1/commands/artifact-delete` | 当前主线 | 按需 | 逻辑删除 artifact | `artifact_ref`、`deleted_by`、`delete_reason` |
| `POST /api/v1/commands/artifact-cleanup` | 当前主线 | 按需 | 触发一次 artifact cleanup | `cleaned_by`、`idempotency_key` |
| `POST /api/v1/commands/ticket-artifact-import-upload` | 当前主线 | 是 | 把已完成的 upload session 导入为普通 artifact | `workflow_id`、`ticket_id`、`node_id`、`artifact_ref`、`path`、`upload_session_id` |
| `POST /api/v1/commands/ticket-cancel` | 当前主线 | 按需 | 取消 ticket | `workflow_id`、`ticket_id`、`node_id`、`cancelled_by` |
| `POST /api/v1/commands/board-approve` | 当前主线 | 是 | 董事会通过 review | `review_pack_id`、`approval_id`、`selected_option_id`、`board_comment`、`elicitation_answers?` |
| `POST /api/v1/commands/board-reject` | 当前主线 | 是 | 董事会驳回 review | `review_pack_id`、`approval_id`、`board_comment`、`rejection_reasons` |
| `POST /api/v1/commands/modify-constraints` | 当前主线 | 是 | 董事会改约束并要求重做 | `review_pack_id`、`approval_id`、`constraint_patch`、`board_comment`、`elicitation_answers?` |

补充说明：

- `project-init` 和 `ticket-create` 不再接受弃用兼容输入 `tenant_id / workspace_id`
- `project-init` 当前新增可选 `force_requirement_elicitation`；开启后会先进入一次 `REQUIREMENT_ELICITATION` 板审，而不是直接 kickoff scope review
- `project-init` 当前还会在 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT/<workflow_id>/` 下创建受管项目工作区；`project_methodology_profile` 第一版支持 `AGILE / HYBRID / COMPLIANCE`
- `runtime-provider-upsert` 当前已从单一表单切到 registry 快照；`providers[]` 首版只开放 `prov_openai_compat` 与 `prov_claude_code`，并额外支持 `capability_tags[]`、`fallback_provider_ids[]`、`cost_tier` 与 `participation_policy`；`role_bindings[]` 当前只建议写现有真实角色
- `runtime-provider-upsert` 当前会拒绝未知能力标签、重复标签、未知 fallback provider、自引用和重复 fallback 项
- `ticket-create` 当前可选支持 `runtime_preference.preferred_provider_id / preferred_model`；它只表达任务级 runtime 偏好，不提供绕过能力底线、provider 启停状态、参与策略或现有 failover 约束的硬覆盖
- `ticket-create` 对由当前 `project-init` 建出来的 workflow，会自动补 project workspace / methodology / deliverable / 文档 / git 相关真相，并创建 ticket dossier；legacy / seeded workflow 没有 workspace manifest 时只会补最小默认值
- `ticket-result-submit` 对 workspace-managed `source_code_delivery` 票，当前会硬要求 `payload.documentation_updates`、`verification_evidence_refs` 和 `git_commit_record`；旧 artifact-path 代码票继续兼容
- `ticket-result-submit` 对 `deliverable_kind=structured_document_delivery` 的票，当前会硬要求至少一条 `artifact_ref`、至少一条 `written_artifact`，以及至少一条 declared `artifact_ref` 和本次写盘对齐
- `ticket-result-submit` 对五类治理文档票，除了上面的统一 gate，还会继续硬校验 `payload.document_kind_ref == output_schema_ref`
- `ticket-result-submit` 对 `consensus_document` 票，当前不再接受 legacy `payload.followup_tickets`；runtime 默认生成的 consensus payload 也不再产出这个字段
- `ticket-result-submit` 现在不再直接消费 `upload_session_id`；中大文件必须先走 `ticket-artifact-import-upload`
- `board-approve` 在 scope review 主链里，当前不再依赖也不再物化 legacy consensus `followup_tickets` contract；不要再把它当成 build/check/review 链的来源

## 5. Projections

这组接口都在 `/api/v1/projections/*`，统一返回投影 envelope。

| 接口 | 边界标签 | 默认是否建议使用 | 用途 | 关键查询参数 |
|------|----------|------------------|------|--------------|
| `GET /api/v1/projections/dashboard` | 当前主线 | 是 | 首页聚合快照 | 无 |
| `GET /api/v1/projections/runtime-provider` | 当前主线 | 是 | 读取当前 provider registry、默认 provider、角色绑定、每个 provider 的能力标签、fallback 链、成本层级、参与策略与健康明细 | 无 |
| `GET /api/v1/projections/workflows/{workflow_id}/dependency-inspector` | 当前主线 | 是 | 查看当前 workflow 链路依赖和停点原因 | `workflow_id` |
| `GET /api/v1/projections/workflows/{workflow_id}/ceo-shadow` | 当前主线 | 按需 | 查看 CEO 审计提议与执行摘要，包括 `preferred_* / actual_* / selection_reason / policy_reason`，以及当前 `reuse_candidates` | `workflow_id`、`limit` |
| `GET /api/v1/projections/artifact-cleanup-candidates` | 当前主线 | 按需 | 查看 cleanup 候选明细 | `ticket_id`、`retention_class`、`limit` |
| `GET /api/v1/projections/inbox` | 当前主线 | 是 | 读取董事会 inbox | 无 |
| `GET /api/v1/projections/meetings/{meeting_id}` | 当前主线 | 是 | 读取会议详情 | `meeting_id` |
| `GET /api/v1/projections/workforce` | 当前主线 | 是 | 读取当前员工泳道、状态和 staffing 模板 | 无 |
| `GET /api/v1/projections/tickets/{ticket_id}/artifacts` | 当前主线 | 按需 | 读取单 ticket 的 artifact 索引 | `ticket_id` |
| `GET /api/v1/projections/incidents/{incident_id}` | 当前主线 | 是 | 读取 incident 详情 | `incident_id` |
| `GET /api/v1/projections/review-room/{review_pack_id}` | 当前主线 | 是 | 读取 review room 主体 | `review_pack_id` |
| `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` | 当前主线 | 按需 | 读取编译包、manifest 和 compile summary | `review_pack_id` |

## 6. Artifacts

这组接口都在 `/api/v1/artifacts/*`，用于控制面读取 artifact。

| 接口 | 边界标签 | 默认是否建议使用 | 用途 | 关键查询参数 |
|------|----------|------------------|------|--------------|
| `GET /api/v1/artifacts/by-ref` | 当前主线 | 是 | 读取 artifact 元数据和本地读取 URL | `artifact_ref` |
| `GET /api/v1/artifacts/content` | 当前主线 | 是 | 读取原始内容或下载 | `artifact_ref`、`disposition=inline|attachment` |
| `GET /api/v1/artifacts/preview` | 当前主线 | 是 | 读取 JSON / 文本 / 媒体预览 | `artifact_ref` |

## 7. Artifact Uploads

这组接口都在 `/api/v1/artifact-uploads/*`，属于当前主线里受限的大文件导入链。

| 接口 | 边界标签 | 默认是否建议使用 | 用途 | 关键输入 |
|------|----------|------------------|------|----------|
| `POST /api/v1/artifact-uploads/sessions` | 当前主线 | 是 | 创建上传会话 | 上传目标路径、kind、媒体类型等 |
| `PUT /api/v1/artifact-uploads/sessions/{session_id}/parts/{part_number}` | 当前主线 | 是 | 上传单个分片 | `session_id`、`part_number`、二进制 body |
| `POST /api/v1/artifact-uploads/sessions/{session_id}/complete` | 当前主线 | 是 | 完成会话并合并 staging 内容 | `session_id` |
| `POST /api/v1/artifact-uploads/sessions/{session_id}/abort` | 当前主线 | 是 | 终止会话并清理 staging | `session_id` |

## 8. Events

| 接口 | 边界标签 | 默认是否建议使用 | 用途 | 关键查询参数 |
|------|----------|------------------|------|--------------|
| `GET /api/v1/events/stream` | 当前主线 | 是 | SSE 失效通知流 | `after` |

说明：

- 这条流只用于前端刷新提示，不是浏览器第二真相源

## 9. 已下线兼容面

- `/api/v1/worker-runtime/*` 已从当前应用入口移除
- `/api/v1/worker-admin/*` 已从当前应用入口移除
- `worker-admin` / `worker-runtime` projections 已从当前应用入口移除

## 10. 已知边界

- 这份文档按今天的代码现实写，不保证和旧设计稿完全一致
- `worker-admin / worker-runtime` 不再属于当前 API 暴露面
- 多租户 shape 和对象存储相关遗留代码仍在仓库里，但不属于当前主线接口承诺
- 如果接口定义、设计文档和代码冲突，以代码和 [mainline-truth.md](mainline-truth.md) 为准
