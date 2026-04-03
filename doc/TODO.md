# TODO

> 最后更新：2026-04-04
> 本文件是项目唯一的待办真相源。合并了原 `doc/TODO.md`、根目录 `codex-followup-todo.md` 和 `detailed-todo.md`（现 `doc/task-backlog.md`）三份文档。

---

## 当前阶段目标

把项目收敛成一个本地单机可运行的 Agent Delivery OS MVP：

- 事件溯源状态总线是真相源
- Ticket 驱动无状态执行器推进工作
- Maker-Checker 和 Review 闭环真实可用
- 最后以最薄的 React Web 壳呈现 `dashboard / inbox / review room`

## 当前基线（2026-04-04 实测）

- backend：`py -m pytest tests -q` → 378 passed
- frontend：当前环境缺少 Node.js / npm，`npm run build` 与 `npm run test:run` 本轮无法复核

---

## 已完成能力概要

下面这些能力已经在代码中真实运行，不是 stub：

- **Employee lifecycle**：hire / replace / freeze / restore 全部进入真实治理链；冻结/替换时自动回收已 lease 票、围堵执行中票；restore 自动恢复被冻结回收的旧票
- **Maker-Checker 五条真实链路**：
  1. `MEETING_ESCALATION + consensus_document@1`
  2. `BUILD + implementation_bundle@1`（内部 maker → checker → fix / incident）
  3. `CHECK + delivery_check_report@1`（内部 maker → checker → fix / incident）
  4. `REVIEW + ui_milestone_review@1`（→ Inbox → Review Room）
  5. `delivery_closeout_package@1`（review 通过后自动补收口票）
- **返工治理**：重复问题指纹升级、fix 票默认排除原 maker/checker、incident 升级不误开审批
- **Context Compiler**：TEXT/MARKDOWN/JSON 内联、超预算降级（片段→预览）、媒体/二进制引用、跨 workflow 历史摘要、`json_messages_v1` 渲染、`prov_openai_compat` 最小真实调用路径
- **完整主链**：`project-init → scope review → BUILD → CHECK → REVIEW → closeout` 端到端打通
- **CEO 有限接管首轮**：CEO 动作契约、快照、提示词、提议器、校验器、执行器、影子审计日志和只读 projection 已落地；当前已能真实执行 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE`，`ESCALATE_TO_BOARD` 仍只做影子建议与对照记录
- **React Boardroom UI**：dashboard / inbox / review room / incident detail / workforce / events / workflow river / Board Gate / project-init form / dependency inspector / runtime provider settings / completion card

---

## P0：把主链上的智能补齐

### P0-A：现状校准与单一真相源

主线关系：**直接服务主链入口判断**，避免把冻结能力、旧设计目标和当前代码现实混在一起。

> 结果：之后任何开发都能明确知道"哪些已经真实存在，哪些只是文档目标"。

- [x] 做一份"代码 vs 文档"能力对照表，确认主链上每个阶段到底是真实运行、半真实、还是仅文档存在
- [x] 明确 Runtime 支持矩阵：按角色、输出类型、执行模式列清楚当前支持范围和缺口
- [x] 把冻结模块列成清单和边界说明，先在文档上隔离，不做物理搬迁
- [x] 修正文档里的明显漂移项（路径写法、过时规模估计、验证命令入口）

验收门槛：新人只看入口文档就能判断当前主线和冻结边界；不再出现"文档说已经有，代码里其实还没有"的关键误判。

对应任务库：借用 `P1-CLN-*` 的边界整理思路，但不执行 `_frozen/` 迁移。

本轮产物：

- 新增 [mainline-truth.md](mainline-truth.md)，单独收口主链阶段对照、runtime 支持矩阵和冻结边界
- 入口文档已统一指向这份真相表，后续批次先以这里和代码现实为准

### P0-B：把真实 Worker 执行扩到当前主链

主线关系：**直接决定主链能否从确定性演示走到真实模型执行**，是 `project-init -> ... -> closeout` 真正变“活”的关键一段。

> 结果：现有 `project-init → scope → build → check → review → closeout` 这条链，在配置 Provider 后能真实跑模型，而不是只靠确定性结果。

- [x] 先把当前已接好的 OpenAI Compat 路径补成稳定能力：超时、限流、认证失败、坏响应都要有清晰分类和回退
- [x] 把真实执行覆盖扩到主链需要的 5 类输出：`consensus_document`、`implementation_bundle`、`delivery_check_report`、`ui_milestone_review`、`delivery_closeout_package`，以及对应的 `maker_checker_verdict`
- [x] 统一 live path 和 deterministic path 的结果校验、审计产物、incident 记录方式
- [x] 给 Dashboard / Incident / Review 读面补足 provider 健康和回退信号
- [x] 用 mock provider 补完整端到端测试，覆盖 build / check / review / closeout 四段

验收门槛：配好 Provider 后，一条完整 workflow 能在真实模型输出下跑到 closeout；Provider 出错时不会把工作流打坏，能自动降回确定性路径并留下证据。

对应任务库：`P0-WRK-001` 到 `P0-WRK-012`。

本轮产物：

- OpenAI Compat live path 现在会对 `timeout / 429 / 5xx` 做固定重试，对 `401/403 / 坏响应 / schema 不符` 直接归类为非重试错误
- pause-worthy 的 provider 故障会继续打开现有 provider incident + breaker，但当前票会立即回落到 deterministic，不再把 workflow 卡死在 live path
- Dashboard / runtime provider 读面现在统一使用 `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`，paused / incomplete 文案会明确说明当前会回落到 deterministic
- 已 lease 的 OpenAI Compat 票在 provider 已 paused 时可以继续走本地 fallback 完成，不再只停在 `LEASED`
- live path 成功产出 `consensus_document / implementation_bundle / delivery_check_report / ui_milestone_review / delivery_closeout_package` 时，现在也会补齐和 deterministic path 一致的默认 artifact refs 与写入记录，scope 审批和 closeout 收口不再因为缺证据引用被拒
- 后端新增了两条 mock provider 主链验证：一条覆盖 provider-backed happy path 到 closeout completion，另一条覆盖 final review 上的 `PROVIDER_BAD_RESPONSE` fallback 后仍能完成主链
- 后端补了 provider 重试、pause、fallback、健康读面的最小测试；前端 mock / 类型也已对齐新契约
- `frontend_engineer` 现在已经拆成独立 `frontend_engineer_primary` runtime worker；`BUILD / REVIEW / closeout` 改走独立 profile，scope 共识链仍保留 `ui_designer_primary` 并由调度兼容承接

- [ ] 当前开发环境缺少 Node.js / npm，前端 `build` 与 `test:run` 还需要在可用环境里补一次真实复核

主线关系：**只服务验证闭环**，不改变主链能力，但影响这条主线的前端交付是否完成最终验收。

### P0-C：让 CEO 先进入影子模式

主线关系：**直接服务后续主调度器接管**，但必须建立在现有主链成功率不被影响的前提上。

> 结果：系统开始出现真正的"CEO 判断"，但先不直接改状态，先拿真实数据比对质量。

- [x] 定义 CEO 动作契约、状态快照、系统提示和输出校验
- [x] 在工单完成、失败、审批完成、incident 恢复这些节点上，让 CEO 读当前快照并产出建议动作
- [x] 影子模式下只记录建议、校验结果和与现有确定性调度器的差异，不执行动作
- [x] 为 CEO 决策加审计日志和回放测试
- [x] 跑一轮代表性场景回放，确认 CEO 建议质量够稳定，再决定哪些动作进入有限接管

验收门槛：至少覆盖"创建首票、失败重试、升级 incident、招聘建议、等待董事会"五类场景；影子模式不影响现有主链成功率。

对应任务库：`P0-CEO-001` 到 `P0-CEO-015`，但新增"影子模式"阶段，不直接一步切换主调度器。

本轮产物：

- 后端新增 `ceo_actions.py / ceo_snapshot.py / ceo_prompts.py / ceo_proposer.py / ceo_validator.py / ceo_scheduler.py / ceo_executor.py`，先从影子判断器起步，再接入有限执行首轮
- 当前影子模式只开放 5 类受控动作：`CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / ESCALATE_TO_BOARD / NO_ACTION`
- `ticket_handlers` 与 `approval_handlers` 现在会在工单完成、工单失败、审批完成、incident 恢复后追加 CEO 影子审计，不影响现有 `workflow_auto_advance`
- 后端新增 `ceo_shadow_run` 审计表和 `/api/v1/projections/workflows/{workflow_id}/ceo-shadow` 只读投影，后续前端可以直接接入，不需要翻库
- 新增 `backend/tests/test_ceo_scheduler.py`，覆盖 fallback、live provider 提议、有限执行建票 / 重试 / 招聘、deferred escalation、失败触发、审批触发、incident 恢复触发；本轮后端全量验证为 `378 passed`
- 2026-04-04 收尾修正：移除了 `ticket-create` 上误插的 `TICKET_FAILED` 影子触发，并把 `ticket-fail` 的真实影子触发补回成功出口，避免 CEO 审计把“建票成功”误记成“失败后决策”
- 2026-04-04 增量推进：`ceo_executor.py` 已接入有限执行首轮，当前会真实落地 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE`，并把 `executed_actions / execution_summary / deterministic_fallback_*` 一起写入 `ceo-shadow` 审计与投影；`ESCALATE_TO_BOARD` 仍明确保留为 `DEFERRED_SHADOW_ONLY`

---

## P1：在 P0 稳住后推进

### P1-A：CEO 有限接管

主线关系：**主链增强**，建立在 `P0-B / P0-C` 已稳定的前提上。

- [x] 先放开有限动作中的 3 类真实执行：创建工单、重试工单、发起招聘建议；`ESCALATE_TO_BOARD` 继续保持 shadow-only
- [x] 所有动作仍经过 Reducer 级校验；校验失败不会改主状态，并会在 `ceo-shadow` 中留下 rejected / fallback 记录
- [x] 保留现有 `workflow_auto_advance` 作为总回退；provider fallback 和执行失败现在会显式写入 `deterministic_fallback_*`
- [x] 增加"影子建议 vs 实际执行"对照审计与读面：`ceo-shadow` 投影现在会返回 `executed_actions / execution_summary`

验收门槛：P1-A 首轮当前已满足“失败重试、无 worker 时招聘、受限主线 preset 建票”三类动作；“project-init 后首票自主拆解”和“通用董事会升级执行”仍留在后续批次。

### P1-B：前端拆壳，只拆会继续长的部分

主线关系：**间接服务主链**，目标是降低后续 UI 继续演进和验证的成本，不改变当前工作流真相。

- [x] 先拆数据层：类型、API 客户端、SSE 管理器、主 store、review store、UI store
- [x] 再拆页面壳和抽屉壳：`DashboardPage`、各类 Drawer、错误边界
- [x] 保持视觉和交互基本不变，不在这一阶段重新设计品牌风格
- [x] 测试重点放在 store、API、关键交互和错误状态
- [x] 把 `App.tsx` 缩到只剩路由和组装职责

本轮产物：

- 前端已完成 `P0-FE-001` 到 `P0-FE-010`：`zustand` 已接入，`src/api.ts` 已拆成 `types/ + api/ + stores/ + hooks/`，`App.tsx` 改为通过独立 API 模块、SSE hook 和 store 取数/提交
- `frontend/src/pages/DashboardPage.tsx` 现在承接原 `App.tsx` 的页面组装、SSE 失效刷新、路由驱动的 review / incident 读取，以及 `incident detail / dependency inspector` 的本地读状态
- `frontend/src/components/shared/ErrorBoundary.tsx` 与 `frontend/src/components/shared/Drawer.tsx` 已落地；`ReviewRoomDrawer / IncidentDrawer / DependencyInspectorDrawer / ProviderSettingsDrawer` 已统一迁到 `components/overlays/` 并复用同一套抽屉壳
- `frontend/src/App.tsx` 已缩到纯路由入口；旧的四个重复抽屉壳文件已移除，避免仓库里同时留两套实现
- 前端补了 shared 组件最小测试：新增 `Drawer` 的 backdrop / Escape 关闭验证，以及 `ErrorBoundary` 的渲染兜底与重试恢复验证
- 本轮前端真实命令级验证仍受环境限制：当前 shell 没有 Node.js / npm，`npm run build` 与 `npm run test:run` 无法复跑
- `frontend/src/api.ts` 目前保留为兼容出口，现有组件还没整体迁到新目录，这一层兼容先保留到页面壳和组件壳拆分完成

新发现任务：

- [ ] 把 `DashboardPage` 里仍偏多的命令回调、格式化 helper 和本地拉取细节继续下沉，尽量逼近设计文档里的轻页壳目标
- [ ] 共享基础组件、CSS 拆分和工具函数模块（`P0-FE-013 / P0-FE-020 / P0-FE-021`）仍未做，留在前端拆壳下一批处理

主线关系：**间接服务主链验证**，降低前端后续演进和回归成本，不改变工作流真相。

对应任务库：选择性吸收 `P0-FE-001` 到 `P0-FE-022`。

### P1-C：人格模型接入真实决策

主线关系：**主链增强但不阻塞当前闭环**，晚于真实执行和调度稳定化。

- [ ] 定义最小可用的 `skill / personality / aesthetic` 三组维度
- [ ] 先做 4 到 6 个模板，接进 staffing catalog、CEO 提示词和 worker 提示词
- [ ] 在招聘决策里加入最小多样性约束
- [ ] 在 Review Pack 或 Workforce 里可见当前员工画像

对应任务库：`P1-PER-001` 到 `P1-PER-008`。

---

## P2：功能收口与后置能力

### P2-A：会议室协议最小版

主线关系：**后置增强**，不影响当前本地 MVP 主闭环成立。

- [ ] 只实现 1 个会议类型（建议先做 `TECHNICAL_DECISION`）
- [ ] 只支持最小轮次：立场、质疑、方案、收敛
- [ ] 输出必须还是结构化文档，并能回到现有审查/审批链

对应任务库：`P1-MTG-001` 到 `P1-MTG-010`。

### P2-B：代码瘦身与冻结能力隔离

主线关系：**后置收口**；当前阶段只做文档隔离和边界说明，不做物理迁移。

- [ ] 先做 import 依赖图和调用清单，再决定是否物理迁移冻结模块
- [ ] 如果迁移，以"不影响主线测试"为绝对前提
- [ ] 如果不迁移，也至少把入口、文档和目录注释补齐

对应任务库：`P1-CLN-001` 到 `P1-CLN-006`。

### P2-C：检索、Provider 路由、发布准备

主线关系：**后置增强**，只有在真实 Worker 与 CEO 稳定后才值得继续投入。

- [ ] 检索只在真实证明本地历史摘要不够后再做
- [ ] Provider registry / routing / fallback 策略放在真实 Worker 和 CEO 稳定之后
- [ ] 发布准备以"本地单机演示可复现"为目标

对应任务库：`P2-RET-*`、`P2-PRV-*`、`P0-REL-*`。

### P2-D：UI 打磨与文档

主线关系：**后置打磨**，不阻塞当前本地单机 MVP 闭环。

- [ ] Workflow River 粒子动画、Board Gate 呼吸动画、加载骨架屏、响应式布局
- [ ] 键盘可访问性、暗色主题微调、性能优化
- [ ] 更新 README、运维指南、API 文档

对应任务库：`P2-UI-*`、`P2-DOC-*`。

---

## 已实现但暂停扩张

下面这些能力保留现状，但默认不继续扩张，除非它们直接服务当前 MVP：

- 多租户 worker 运维面与 `worker-admin` HTTP 控制面
- 操作人令牌、可信代理断言、独立 auth rejection 读面
- multipart artifact upload
- 本地默认 + 可选对象存储双后端
- 更强的远程 worker handoff 与公网暴露边界

## 明确后置的能力

在本地 MVP 闭环完成前，不主动推进下面这些方向：

- 新的 `worker-admin` 读写接口
- 更细的多租户 scope 治理与租户级运维工具
- 面向公网的身份层、外网暴露策略、零信任边界
- 浏览器直传、云厂商预签名直传、远程对象存储交付链路增强
- 为远程多节点部署设计的新控制面复杂度

## 执行约束

- 新工作如果不能直接缩短本地 MVP 路径，就默认延后
- 文档、任务拆分和代码审查都应以"本地无状态 agent team + web 壳"作为判断基准
- 对已有基础设施代码优先采取"冻结、收口、少动"的策略

## 建议首轮执行批次

- 批次 1：现状校准 + 支持矩阵 + 文档入口纠偏
- 批次 2：OpenAI Compat live path 稳定化 + provider 观测信号
- 批次 3：把 live Worker 覆盖扩到 build / check / review / closeout 主链
- 批次 4：CEO 影子模式 + 审计日志 + 回放测试

---

## 参考

- 完整 112 项任务清单（含工时估算、依赖图、验收标准）：[task-backlog.md](task-backlog.md)
- CTO 评审报告（诊断与差距分析）：[cto-assessment-report.md](cto-assessment-report.md)
- 里程碑时间线（13 周 9 里程碑）：[milestone-timeline.md](milestone-timeline.md)
