# TODO

这份 TODO 只保留当前主线待办。已经实现但被降级为后置能力的基础设施，不再作为近期开发重点。

## 当前阶段目标

把项目收敛成一个本地单机可运行的 Agent Delivery OS MVP：

- 事件溯源状态总线是真相源
- Ticket 驱动无状态执行器推进工作
- Maker-Checker 和 Review 闭环真实可用
- 最后以最薄的 React Web 壳呈现 `dashboard / inbox / review room`

## P0：必须先完成的主链路

- 已完成核心 employee lifecycle：`employee hire / replace / freeze / restore` 现在都进入真实治理链
  - `employee-hire-request / employee-replace-request` 现在会走 `CORE_HIRE_APPROVAL -> Inbox -> Review Room -> board approve`
  - `employee-freeze` 会立即阻止 scheduler dispatch、手动 `ticket-lease / ticket-start` 和 `worker-runtime` bootstrap
  - `employee-restore` 会把 `FROZEN` 员工直接恢复回 `ACTIVE`，重新放开 scheduler dispatch、手动 `ticket-lease` 和 `worker-runtime` bootstrap
  - 冻结或替换员工时，已 lease 未开工票现在会自动回收到 `PENDING` 并把原员工写进 `excluded_employee_ids`；执行中票会进入 `staffing containment` 围堵，并通过 incident / circuit breaker 暴露到 `Inbox / Dashboard / Workforce`
  - `employee-restore` 现在会自动恢复因 freeze 被回收的旧票，只移除这次冻结临时加上的排除名单；`incident-resolve` 也新增了 `RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT`，可以把被 staffing containment 打断的执行票重新拉回待执行链
  - 默认 roster 现在由 employee 事件 bootstrap，再由 reducer 重建，不再把 `employee_projection` 当成静态真相源
  - 当前剩余缺口：更多票型上的 staffing policy 也还没补齐，replace / freeze 之外的恢复策略仍需要继续收口
- 直接推进主线：把已落地的视觉里程碑 Maker-Checker 闭环扩到更多关键产物，而不只停在这一条链上
  - 当前已新增第二条真实链路：`MEETING_ESCALATION + consensus_document@1` 现在也会先走 maker-checker，再进 `Inbox -> Review Room`
- 直接推进主线：把 Maker-Checker 返工治理继续补完到视觉链之外；当前已具备重复问题指纹升级、更明确的 fix 票约束，以及返工票默认排除原 maker 的最小换人链，剩余重点是把这套 staffing policy 推广到更多关键产物
- 把 `Context Compiler` 从“文本类 artifact 可内联”的当前版本继续推进，补完二进制 / 大文件 / 检索增强下的编译与降级策略
  - 当前已完成：`TEXT / MARKDOWN / JSON` 可完整内联；超预算文本 / JSON 会先退到确定性片段编译，片段仍放不下时再退到确定性预览；图片 / PDF 会作为结构化媒体引用进入执行包；其他二进制会作为结构化下载引用进入执行包；context block 和 worker execution package 现在都会显式带出 `display_hint`，不用再靠字段名猜是正文、预览还是下载；bundle / manifest / developer inspector 已暴露结构化降级原因、selector、片段/预览策略和媒体/下载型附件计数；编译时还能拉入同 workspace、跨 workflow 的本地 `review / incident / artifact` 历史摘要卡片；显式输入现在会为后续 mandatory source 预留最小 descriptor 预算，最终 bundle 不再允许悄悄超出 `max_context_tokens`；如果连 mandatory 输入 descriptor 都塞不进去，编译会按 `FAIL_CLOSED` 直接失败；编译产物现在还会稳定派生最小 `json_messages_v1` 渲染结果，并同步进入 worker execution package 与 `Review Room` developer inspector；in-process runtime 也已经接通最小真实 `prov_openai_compat` provider 路径，配置兼容 `responses` 站点后可直接跑真实调用
  - 当前仍缺：更强的预算压缩矩阵、更多 schema / role profile 的真实执行覆盖，以及向量/联网之外是否还需要更丰富的本地检索策略；`provider routing / recovery`、浏览器直传和云预签名 multipart 继续后置到 MVP 之后再评估
- 收敛 runtime 默认路径，优先保证本地单机执行稳定，而不是继续扩远程 handoff 面
- 明确 MVP 的最小 schema、role profile、ticket 路径，不再边做边膨胀
- 已完成直接推进主线：`project-init -> 首个 review` 现在已经打通
  - `project-init` 现在会先生成 board brief artifact，再自动创建首张 `consensus_document@1` 范围票，并在同一条后端链上同步跑完 `maker -> checker -> Inbox -> Review Room`
  - 如果本地没有 eligible worker，或途中出现 incident，这条入口会停在真实 pending / incident 状态，不会伪造首个 review 已经完成
- 直接推进主线：把首个 scope review 的通过结果继续接成后续执行票
  - 当前 board approve 仍只会关闭 review，本地主链还不会按 `consensus_document.followup_tickets` 自动继续生成下一段 build ticket
  - 这已经成为当前本地 `Board -> Review -> Build` 路径里最明显的新缺口

## P1：套上最薄 Web 壳

- 已完成直接推进主线：独立 React Boardroom UI 已落地在 `frontend/`
  - 当前已经接通 `dashboard / inbox / review room`
  - 首页采用 `workflow river` 主舞台，并以 `Board Gate` 高亮待审状态
  - 无 active workflow 时会显示最小 `project-init` 表单，并明确提示它会把 workflow 推进到首个 review
  - `approve / reject / modify constraints` 动作提交后会立即重新拉取，并用 SSE 做失效刷新
- 直接推进主线：继续补齐 UI 的剩余 MVP 读面
  - `provider / model` 设置页
  - `incident` 详情页
  - `workforce` 深入视图
  - dependency inspector
- 为主线解堵：继续保持 projection-first，前端不拥有工作流真相
  - 当前首页河道只消费 `dashboard.pipeline_summary.phases` 的固定五段高层摘要，不新造前端工作流引擎
  - `events/stream` 只用于失效通知，不作为浏览器里的第二真相源

## P2：在 MVP 之后补齐

- MVP 后补上 Meeting Room 专用界面
- MVP 后补上 dependency graph explorer
- MVP 后补上历史分析、多 workspace 管理和更深入的员工画像浏览
- 再评估是否需要在当前本地历史摘要检索之上继续扩更丰富的 Search / Retrieval
- 再评估是否需要更完整的 provider routing / recovery

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
- 文档、任务拆分和代码审查都应以“本地无状态 agent team + web 壳”作为判断基准
- 对已有基础设施代码优先采取“冻结、收口、少动”的策略，而不是继续加面
