# 已完成能力与收口批次

> 说明：这里保留当前代码已经真实落地的主线能力，以及已收口批次的结果。默认行动判断仍以 `../TODO.md` 为准。

## 已完成能力概要

下面这些能力已经在代码中真实运行，不是 stub：

- **Employee lifecycle**：`hire / replace / freeze / restore` 全部进入真实治理链；冻结/替换时自动回收已 lease 票、围堵执行中票；`restore` 自动恢复被冻结回收的旧票
- **Maker-Checker 五条真实链路**：
  1. `MEETING_ESCALATION + consensus_document@1`
  2. `BUILD + implementation_bundle@1`
  3. `CHECK + delivery_check_report@1`
  4. `REVIEW + ui_milestone_review@1`
  5. `delivery_closeout_package@1`
- **返工治理**：重复问题指纹升级、fix 票默认排除原 maker/checker、incident 升级不误开审批
- **Context Compiler**：`TEXT / MARKDOWN / JSON` 内联、超预算降级、媒体/二进制引用、跨 workflow 历史摘要、`json_messages_v1` 渲染、`OpenAI Compat` 最小真实调用路径
- **完整主链**：`project-init -> scope review -> BUILD -> CHECK -> REVIEW -> closeout` 已端到端打通
- **CEO 最小接管闭环**：动作契约、快照、提示词、提议器、校验器、执行器、影子审计日志和只读 projection 已落地；当前可真实执行 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE`
- **Live 长测入口**：后端现已把图书馆场景收口到配置驱动 runner：`python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live.toml`；它会把 DB、provider 配置、artifact、developer inspector、失败快照和每票 markdown 上下文留档统一收进 `backend/data/scenarios/library_management_autopilot_live/`
- **Runtime 审阅留痕**：runtime 在持久化 compile 产物后，除了原有 `developer_inspector` JSON，还能额外写每票一份 markdown 上下文审阅档；provider assumptions 也会记录 `effective_reasoning_effort`
- **Seeded staffing variants**：CEO 招聘在配置 `BOARDROOM_OS_CEO_STAFFING_VARIANT_SEED` 后，会基于现有人格模板生成可复现但不完全同质的画像变体，降低同岗扩招时撞上高重合拒绝的概率
- **React Boardroom UI**：`dashboard / inbox / review room / meeting room / incident detail / workforce / events / workflow river / board gate / project-init form / dependency inspector / runtime provider settings / completion card`

## 已收口批次

### P0-A：现状校准与单一真相源

- 新增 `mainline-truth.md`，把主链现实、runtime 支持矩阵和冻结边界收成单独入口
- 入口文档已经统一指向这份真相表，后续先以这里和代码现实为准

### P0-B：真实 Worker 执行扩到当前主链

- OpenAI Compat live path 已补齐超时、限流、认证失败、坏响应的分类和回退
- 主链所需 5 类输出已进入真实执行与统一审计形态
- provider 故障会打开现有 incident + breaker，但当前票会回退到 deterministic，不再把 workflow 卡死
- Dashboard / runtime provider 读面统一使用 `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`
- `frontend_engineer` 已拆成独立 `frontend_engineer_primary` runtime worker

### P0-C / P1-A：CEO 从影子到有限接管首轮

- `ceo_actions.py / ceo_snapshot.py / ceo_prompts.py / ceo_proposer.py / ceo_validator.py / ceo_scheduler.py / ceo_executor.py` 已落地
- 工单完成、工单失败、审批完成、incident 恢复后都会追加 CEO 审计
- `ceo-shadow` 读面现在会返回 `executed_actions / execution_summary / deterministic_fallback_*`
- `project-init` 后首个 scope kickoff 票已改由 CEO 发起，`scheduler_runner` 也会在空转时补打一轮 idle maintenance

### P1-B：前端拆壳

- 数据层已拆到 `types/ + api/ + stores/ + hooks/`
- 页面壳、布局壳、共享组件壳、覆盖层壳都已拆出；`App.tsx` 已缩到路由入口
- `DashboardPage.tsx` 已从 903 行压到 298 行
- 样式已拆成 `tokens / global / layout / components / overlays`
- 前端 build 与测试均已完成真实复核

### P1-C：人格模型接入真实决策

- 后端新增 `persona_profiles.py` 作为真相源，统一 `skill / personality / aesthetic`
- 默认 roster、`staffing_catalog`、CEO snapshot / prompt、Context Compiler、runtime 编译包已统一用标准化画像与 `persona_summary`
- 同岗高重合招聘约束已进主线
- `Workforce` 与 staffing `Review Room` 已能直接看到画像摘要

### P0-D：P0 集成收口首批

- deterministic 主线、provider happy path / fallback、staffing containment 恢复、incident 恢复、前端主线烟囱都已补成明确回归
- `P0-INT-001` 到 `P0-INT-008` 当前都能从验收矩阵里直接看到覆盖范围

### P2-A：会议室协议最小版

- 后端已支持 `meeting-request` 命令、会议事件类型、会议投影表和 `TECHNICAL_DECISION` 最小状态机
- 会议固定执行 `POSITION -> CHALLENGE -> PROPOSAL -> CONVERGENCE` 四轮，成功时会生成真实 `consensus_document` 与 `meeting-digest.json`
- React 壳已新增 `/meeting/:meetingId` 与只读 `MeetingRoomDrawer`

### P2-B：真实图书馆管理系统长测入口

- 后端新增 `tests.live.run_configured` 配置驱动 live runner，图书馆场景通过 `data/live-tests/library_management_autopilot_live.toml` 启动，不进入默认 `pytest`
- 这条场景固定走 `CEO_AUTOPILOT_FINE_GRAINED`，目标是把“图书馆管理系统毕业设计”一路推进到 closeout
- runner 会先用 `runtime-provider-upsert` 把 live provider 绑定到 `gpt-5.4`，并固定 `architect_primary -> xhigh`、其他 live 角色 -> `high`
- 场景结束时会断言：workflow 完成、closeout 产物存在、workflow chain report 存在、ticket 总数至少 30、架构师真实参与且招聘成功、每个 runtime ticket 都有 markdown 上下文审阅档

## 详细追溯

- 想看完整任务卡片、工时、依赖、验收标准、完成补记，统一去 `../task-backlog/done.md`
- 想看最近几轮的事实进展，而不是任务库，统一去 `../history/memory-log.md`
