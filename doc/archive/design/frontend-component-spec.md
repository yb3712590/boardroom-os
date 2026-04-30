# Boardroom OS 前端组件规格说明书

## TL;DR

- 定位：当前前端壳各个页面、布局、卡片、抽屉和共享组件的职责与接口说明。
- 什么时候读：要改组件 props、结构、职责分工、测试覆盖边界时。
- 关键接口：`DashboardPage`、布局组件、仪表盘组件、员工面板、事件流、覆盖层、共享组件、工具函数。
- 当前边界：这份文档管组件职责和结构，不展开事件总线或后端业务规则；视觉细节看视觉规范。
- 关联文档：`frontend-architecture-guide.md`、`boardroom-ui-visual-spec.md`、`boardroom-data-contracts.md`。

> 版本：1.0
> 日期：2026-04-03
> 作者：CTO
> 适用范围：前端开发人员

---

## 一、组件层级总览

```
App (路由配置)
└── DashboardPage
    ├── ErrorBoundary (全局)
    ├── AppShell
    │   ├── TopChrome
    │   │   ├── 产品标识 + 工作流标题
    │   │   ├── RuntimeStatusCard
    │   │   ├── BoardGateIndicator
    │   │   └── OpsStrip
    │   └── ThreeColumnLayout
    │       ├── [左栏] InboxWell
    │       ├── [中栏] BoardroomCenter
    │       │   ├── ProjectInitForm (无 active workflow 时)
    │       │   ├── WorkflowRiver (有 active workflow 时)
    │       │   ├── CenterDetailGrid
    │       │   └── CompletionCard (有 completion 时)
    │       └── [右栏] BoardroomSupport
    │           ├── WorkforcePanel
    │           │   └── StaffingActions
    │           └── EventTicker
    ├── ReviewRoomDrawer (路由参数驱动)
    ├── IncidentDrawer (路由参数驱动)
    ├── DependencyInspectorDrawer (状态驱动)
    └── ProviderSettingsDrawer (状态驱动)
```

---

## 二、页面组件

### 2.1 DashboardPage

**文件**：`src/pages/DashboardPage.tsx`

**职责**：
- 初始化数据加载（调用 `boardroomStore.loadSnapshot()`）
- 建立 SSE 连接（通过 `useSSE` hook）
- 根据路由参数控制 ReviewRoomDrawer 和 IncidentDrawer 的开关
- 组装 AppShell 和所有抽屉

**Props**：无（从 stores 和路由参数获取所有数据）

**内部逻辑**：
```typescript
function DashboardPage() {
  const { reviewPackId, incidentId } = useParams()
  const navigate = useNavigate()
  const loadSnapshot = useBoardroomStore(s => s.loadSnapshot)
  const dashboard = useBoardroomStore(s => s.dashboard)
  const dependencyInspectorOpen = useUIStore(s => s.dependencyInspectorOpen)

  // 初始加载
  useEffect(() => { void loadSnapshot() }, [])

  // SSE 失效通知
  useSSE(() => {
    void loadSnapshot()
    // 如果有打开的抽屉，也刷新对应数据
  })

  // 路由参数变化时加载审查/事件数据
  useEffect(() => {
    if (reviewPackId) reviewStore.loadReviewRoom(reviewPackId)
    else reviewStore.clearReview()
  }, [reviewPackId])

  return (
    <ErrorBoundary>
      <AppShell>
        {/* 主内容 */}
      </AppShell>
      <ReviewRoomDrawer isOpen={!!reviewPackId} onClose={() => navigate('/')} />
      <IncidentDrawer isOpen={!!incidentId} onClose={() => navigate('/')} />
      <DependencyInspectorDrawer isOpen={dependencyInspectorOpen} />
      <ProviderSettingsDrawer />
    </ErrorBoundary>
  )
}
```

**行数目标**：< 120 行

---

## 三、布局组件

### 3.1 AppShell

**文件**：`src/components/layout/AppShell.tsx`

**职责**：提供应用外壳的玻璃面板效果

**Props**：
```typescript
type AppShellProps = {
  children: ReactNode
}
```

**渲染结构**：
```html
<div class="boardroom-app">
  <div class="boardroom-shell">
    {children}
  </div>
</div>
```

**样式要点**：
- 外层 `boardroom-app`：`min-height: 100vh; padding: 28px`
- 内层 `boardroom-shell`：圆角 34px，深蓝黑玻璃背景，1px 半透明描边
- 使用 `radial-gradient` 模拟内部光晕
- `::before` 伪元素添加额外光泽层

**行数目标**：< 30 行

---

### 3.2 TopChrome

**文件**：`src/components/layout/TopChrome.tsx`

**职责**：顶栏，展示产品标识、工作流标题、运行时状态、董事会门状态、运维指标

**Props**：
```typescript
type TopChromeProps = {
  title: string
  subtitle: string
  onOpenProviderSettings: () => void
}
```

**内部数据来源**：从 `useBoardroomStore` 读取 dashboard、runtimeProvider

**渲染结构**：
```html
<header class="top-chrome">
  <div>
    <p class="eyebrow">Boardroom OS</p>
    <h1>{title}</h1>
    <p class="top-chrome-copy">{subtitle}</p>
  </div>
  <div class="top-chrome-meta">
    <RuntimeStatusCard onOpenSettings={onOpenProviderSettings} />
    <BoardGateIndicator />
    <OpsStrip />
  </div>
</header>
```

**样式要点**：
- `display: flex; justify-content: space-between`
- 底部 1px 半透明分割线
- 标题使用 `clamp(2rem, 2.6vw, 3.4rem)`
- 右侧 meta 区域垂直排列

**行数目标**：< 60 行

---

### 3.3 ThreeColumnLayout

**文件**：`src/components/layout/ThreeColumnLayout.tsx`

**职责**：三栏布局容器

**Props**：
```typescript
type ThreeColumnLayoutProps = {
  left: ReactNode    // InboxWell
  center: ReactNode  // 主内容区
  right: ReactNode   // WorkforcePanel + EventTicker
}
```

**渲染结构**：
```html
<div class="boardroom-main">
  {left}
  <section class="boardroom-center">{center}</section>
  <aside class="boardroom-support">{right}</aside>
</div>
```

**样式要点**：
- `display: grid; grid-template-columns: minmax(260px, 22%) 1fr minmax(280px, 24%)`
- `gap: 24px`
- 响应式：< 1200px 时右栏折叠到底部
- 最小高度：`calc(100vh - 200px)`

**行数目标**：< 25 行

---

## 四、仪表盘组件

### 4.1 InboxWell

**文件**：`src/components/dashboard/InboxWell.tsx`

**职责**：左栏收件箱，展示需要董事会操作的项目

**Props**：
```typescript
type InboxWellProps = {
  items: InboxItem[]
  loading: boolean
  onOpenReview: (reviewPackId: string) => void
  onOpenIncident: (incidentId: string) => void
}
```

**渲染结构**：
```html
<aside class="inbox-well" aria-labelledby="inbox-title">
  <div class="section-heading">
    <p class="eyebrow">Inbox</p>
    <h2 id="inbox-title">Board actions and governance pressure</h2>
  </div>
  {loading && <p class="muted-copy">Loading current inbox…</p>}
  {!loading && items.length === 0 && <p class="muted-copy">No board escalations are waiting right now.</p>}
  <div class="inbox-item-list">
    {items.map(item => <InboxItemCard key={item.inbox_item_id} item={item} ... />)}
  </div>
</aside>
```

**每个 InboxItem 的渲染**：
- 左侧色条（ribbon）：根据 priority 变色
  - `low`/`medium`：冷蓝灰
  - `high`：香槟金
  - `critical`：暗红
- 标题 + 摘要 + 徽章
- 可点击项（review/incident）渲染为 `<button>`
- 不可点击项渲染为 `<div>`

**可访问性**：
- `aria-labelledby` 关联标题
- 可点击项有 `role="button"` 或使用原生 `<button>`
- 焦点可见样式

**行数目标**：< 80 行

---

### 4.2 WorkflowRiver

**文件**：`src/components/dashboard/WorkflowRiver.tsx`

**职责**：工作流河道可视化，展示 5 个固定阶段的状态

**Props**：
```typescript
type WorkflowRiverProps = {
  phases: PipelinePhase[]
  approvalsPending: number
}
```

**渲染结构**：
```html
<section class="workflow-river" aria-label="Workflow pipeline">
  <div class="river-track">
    {phases.map((phase, i) => (
      <div key={phase.phase_id} class="river-stage river-stage--{status}">
        <span class="river-stage-label">{phase.label}</span>
        <div class="river-stage-body">
          <span class="river-stage-count">{totalActive(phase)}</span>
        </div>
        {i < phases.length - 1 && <div class="river-connector" />}
      </div>
    ))}
  </div>
  {approvalsPending > 0 && (
    <div class="river-board-branch">
      <div class="river-board-gate">
        <span class="river-board-gate-light" />
        <span>{approvalsPending} pending</span>
      </div>
    </div>
  )}
</section>
```

**视觉规范**：
- 河道横向穿过中央视图
- 阶段状态颜色：
  - `PENDING`：低亮蓝灰 `rgba(199, 225, 255, 0.2)`
  - `EXECUTING`：冰蓝 `var(--color-active-ice)`
  - `UNDER_REVIEW`：稍收敛蓝
  - `BLOCKED_FOR_BOARD`：香槟金 `var(--color-board-gold)`
  - `COMPLETED`：低对比退场
- Board Branch：从主河道偏出的金色支路
- Board Gate 节点边缘慢速呼吸动画（CSS `boardPulse`）

**动画**：
- 阶段切换时使用 CSS transition（`background-color 400ms ease`）
- Board Gate 呼吸使用 CSS `@keyframes boardPulse`
- 不使用 framer-motion（保持轻量）

**行数目标**：< 120 行

---

### 4.3 OpsStrip

**文件**：`src/components/dashboard/OpsStrip.tsx`

**职责**：运维指标条，展示预算、活跃工单、阻塞节点、截止日期

**Props**：
```typescript
type OpsStripProps = {
  budgetRemaining: number
  activeTickets: number
  blockedNodes: number
  deadlineAt: string | null
}
```

**渲染结构**：
```html
<dl class="ops-strip">
  <div><dt>Budget</dt><dd>{formatNumber(budgetRemaining)}</dd></div>
  <div><dt>Live tickets</dt><dd>{activeTickets}</dd></div>
  <div><dt>Blocked</dt><dd>{blockedNodes}</dd></div>
  <div><dt>Deadline</dt><dd>{formatTimestamp(deadlineAt)}</dd></div>
</dl>
```

**样式要点**：
- `grid-template-columns: repeat(4, minmax(0, 1fr))`
- 每个指标卡：圆角 16px，深玻璃背景，半透明描边
- 标签：0.74rem 大写，`var(--color-muted-label)`
- 数值：`var(--color-text-strong)`

**行数目标**：< 40 行

---

### 4.4 RuntimeStatusCard

**文件**：`src/components/dashboard/RuntimeStatusCard.tsx`

**职责**：运行时状态卡片，展示当前执行模式、模型、Worker 数量、健康状态

**Props**：
```typescript
type RuntimeStatusCardProps = {
  effectiveMode: string
  providerLabel: string
  model: string | null
  workerCount: number
  healthSummary: string
  reason: string
  onOpenSettings: () => void
}
```

**渲染结构**：
```html
<section class="runtime-status-card runtime-status-{tone}">
  <div class="runtime-status-head">
    <div>
      <p class="eyebrow">Execution mode</p>
      <strong>{providerLabel}</strong>
    </div>
    <button class="ghost-button" onClick={onOpenSettings}>Runtime settings</button>
  </div>
  <p class="runtime-status-copy">{reason}</p>
  <dl class="runtime-status-grid">
    <div><dt>Model</dt><dd>{model ?? 'Deterministic local runtime'}</dd></div>
    <div><dt>Workers</dt><dd>{workerCount}</dd></div>
    <div><dt>Health</dt><dd>{healthSummary}</dd></div>
  </dl>
</section>
```

**tone 映射**：
- `OPENAI_COMPAT_LIVE` → `live`（蓝色高亮边框）
- `OPENAI_COMPAT_INCOMPLETE` / `OPENAI_COMPAT_PAUSED` → `warning`（金色边框）
- `LOCAL_DETERMINISTIC` → `local`（默认边框）

**行数目标**：< 60 行

---

### 4.5 BoardGateIndicator

**文件**：`src/components/dashboard/BoardGateIndicator.tsx`

**职责**：董事会门状态指示器

**Props**：
```typescript
type BoardGateIndicatorProps = {
  approvalsPending: number
}
```

**渲染结构**：
```html
<div class="board-chip {approvalsPending > 0 ? 'is-armed' : 'is-clear'}">
  <span class="board-chip-light" aria-hidden="true" />
  <strong>{approvalsPending > 0 ? 'Board Gate armed' : 'Board Gate clear'}</strong>
  <span>{approvalsPending > 0 ? `${approvalsPending} approvals pending` : 'No approvals pending'}</span>
</div>
```

**视觉规范**：
- `is-armed` 状态：金色指示灯 + 慢速呼吸动画
- `is-clear` 状态：低亮蓝灰指示灯
- 呼吸动画：`animation: boardPulse 2.8s ease-in-out infinite`

**行数目标**：< 25 行

---

### 4.6 CompletionCard

**文件**：`src/components/dashboard/CompletionCard.tsx`

**职责**：工作流完成卡片，展示最终审查结果和证据入口

**Props**：
```typescript
type CompletionCardProps = {
  summary: {
    workflow_id: string
    title: string
    summary: string
    final_review_pack_id: string
    final_review_approved_at: string | null
    approved_at: string | null
    closeout_completed_at: string | null
    selected_option_id: string | null
    board_comment: string | null
    artifact_refs: string[]
    closeout_artifact_refs: string[]
  }
  onOpenReview: (reviewPackId: string) => void
}
```

**渲染结构**：
- 标题区："Delivery completed"
- 时间信息：审批时间 + 收口完成时间
- 指标网格：标题、审批时间、收口时间、选项、评论、证据数、收口证据数
- 摘要文本
- 操作按钮："Open final review evidence"

**行数目标**：< 80 行

---

### 4.7 ProjectInitForm

**文件**：`src/components/dashboard/ProjectInitForm.tsx`

**职责**：项目初始化表单，在无 active workflow 时显示

**Props**：
```typescript
type ProjectInitFormProps = {
  submitting: boolean
  onSubmit: (payload: {
    northStarGoal: string
    hardConstraints: string[]
    budgetCap: number
  }) => Promise<void>
}
```

**表单字段**：
1. **North star goal**：`<textarea>` 4 行，默认值 "Ship the thinnest governance shell from dashboard to review room."
2. **Hard constraints**：`<textarea>` 5 行，每行一条约束
3. **Budget cap**：`<input type="number">`

**验证规则**：
- goal 不能为空
- budget 必须 >= 0

**提交行为**：
- 将 constraints 按换行分割、trim、过滤空行
- 调用 `onSubmit`
- 提交中禁用按钮，显示 "Advancing to first review…"

**行数目标**：< 70 行

---

## 五、员工面板组件

### 5.1 WorkforcePanel

**文件**：`src/components/workforce/WorkforcePanel.tsx`

**职责**：右栏员工面板，按角色分泳道展示员工状态和操作

**Props**：
```typescript
type WorkforcePanelProps = {
  workforce: WorkforceData | null
  loading: boolean
  submittingAction: string | null
  onFreeze: (employeeId: string) => Promise<void>
  onRestore: (employeeId: string) => Promise<void>
  onRequestHire: (template: StaffingHireTemplate, employeeId: string) => Promise<void>
  onRequestReplacement: (employeeId: string, template: StaffingHireTemplate, replacementId: string) => Promise<void>
}
```

**渲染结构**：
```html
<section class="workforce-panel" aria-labelledby="workforce-title">
  <div class="section-heading">
    <p class="eyebrow">Workforce</p>
    <h2 id="workforce-title">Active team and staffing controls</h2>
  </div>
  {loading && <LoadingSkeleton lines={4} />}
  {workforce?.role_lanes.map(lane => (
    <div key={lane.role_type} class="workforce-lane">
      <h3 class="workforce-lane-title">{lane.role_type}</h3>
      {lane.employees.map(emp => (
        <EmployeeCard
          key={emp.employee_id}
          employee={emp}
          actions={workforce.staffing_actions[emp.employee_id]}
          submittingAction={submittingAction}
          onFreeze={onFreeze}
          onRestore={onRestore}
          ...
        />
      ))}
    </div>
  ))}
  <StaffingActions
    templates={workforce?.staffing_hire_templates ?? []}
    submittingAction={submittingAction}
    onRequestHire={onRequestHire}
  />
</section>
```

**每个 EmployeeCard**：
- 员工 ID + 角色类型
- 状态徽章：ACTIVE（蓝）/ FROZEN（灰）/ REPLACED（暗红）
- 当前工单 ID（如果有）
- 操作按钮：freeze / restore（根据 staffing_actions 决定可用性）

**行数目标**：< 150 行

---

### 5.2 StaffingActions

**文件**：`src/components/workforce/StaffingActions.tsx`

**职责**：招聘/替换操作区域

**Props**：
```typescript
type StaffingActionsProps = {
  templates: StaffingHireTemplate[]
  submittingAction: string | null
  onRequestHire: (template: StaffingHireTemplate, employeeId: string) => Promise<void>
}
```

**行为**：
- 展示可用的招聘模板
- 点击模板后生成新的 employee_id（前端生成 `emp_` 前缀 + 随机 hex）
- 调用 `onRequestHire`

**行数目标**：< 60 行

---

## 六、事件流组件

### 6.1 EventTicker

**文件**：`src/components/events/EventTicker.tsx`

**职责**：事件滚动条，展示最近的系统事件

**Props**：
```typescript
type EventTickerProps = {
  events: EventStreamItem[]
}
```

**渲染结构**：
```html
<section class="event-ticker" aria-labelledby="event-ticker-title">
  <div class="section-heading">
    <p class="eyebrow">Events</p>
    <h3 id="event-ticker-title">Recent activity</h3>
  </div>
  <div class="event-ticker-list">
    {events.map(event => (
      <div key={event.event_id} class="event-ticker-item event-ticker-item--{event.severity}">
        <span class="event-ticker-dot" />
        <span class="event-ticker-type">{event.event_type}</span>
        <span class="event-ticker-time">{formatRelativeTime(event.occurred_at)}</span>
      </div>
    ))}
  </div>
</section>
```

**severity 颜色**：
- `debug`：`var(--color-muted-label)` 最低对比
- `info`：`var(--color-line-blue)` 默认蓝
- `warning`：`var(--color-board-gold)` 金色
- `critical`：`var(--color-incident-rose)` 红色

**行数目标**：< 60 行

---

## 七、覆盖层组件

### 7.1 通用 Drawer 组件

**文件**：`src/components/shared/Drawer.tsx`

**职责**：通用右侧抽屉容器

**Props**：
```typescript
type DrawerProps = {
  isOpen: boolean
  onClose: () => void
  title: string
  subtitle?: string
  width?: string  // 默认 '680px'
  children: ReactNode
}
```

**渲染结构**：
```html
<AnimatePresence>
  {isOpen && (
    <>
      <motion.div class="drawer-backdrop" onClick={onClose} ... />
      <motion.aside
        class="drawer-panel"
        style={{ width }}
        variants={drawerVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        <header class="drawer-header">
          <div>
            <p class="eyebrow">{subtitle}</p>
            <h2>{title}</h2>
          </div>
          <button class="drawer-close" onClick={onClose} aria-label="Close">&times;</button>
        </header>
        <div class="drawer-body">
          {children}
        </div>
      </motion.aside>
    </>
  )}
</AnimatePresence>
```

**动画变体**：
```typescript
const drawerVariants = {
  hidden: { x: '100%', opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: { type: 'spring', damping: 25, stiffness: 200 },
  },
  exit: { x: '100%', opacity: 0, transition: { duration: 0.2 } },
}
```

**可访问性**：
- 打开时 focus trap（Tab 键不会跳出抽屉）
- Escape 键关闭
- `aria-modal="true"`
- 背景遮罩 `aria-hidden="true"`

**行数目标**：< 70 行

---

### 7.2 ReviewRoomDrawer

**文件**：`src/components/overlays/ReviewRoomDrawer.tsx`

**职责**：审查室抽屉，展示 Review Pack 并支持 Approve/Reject/ModifyConstraints

**Props**：
```typescript
type ReviewRoomDrawerProps = {
  isOpen: boolean
  loading: boolean
  reviewData: ReviewRoomData | null
  inspectorData: DeveloperInspectorData | null
  inspectorLoading: boolean
  error: string | null
  submittingAction: string | null
  onClose: () => void
  onOpenInspector: () => Promise<void>
  onApprove: (input: { selectedOptionId: string; boardComment: string }) => Promise<void>
  onReject: (input: { boardComment: string; rejectionReasons: string[] }) => Promise<void>
  onModifyConstraints: (input: {
    boardComment: string
    addRules: string[]
    removeRules: string[]
    replaceRules: string[]
  }) => Promise<void>
}
```

**内部结构**：

1. **状态区**：展示当前审查状态（PENDING_REVIEW / APPROVED / REJECTED）
2. **上下文区**：
   - 触发原因
   - 为什么现在
   - 证据摘要列表
   - Maker-Checker 摘要（如果有）
   - 风险摘要
   - 预算影响
3. **选项区**：
   - 每个选项卡片：标题、摘要、优缺点、风险、产物引用
   - 推荐选项高亮
   - 单选选择
4. **决策区**：
   - 评论输入框
   - Approve / Reject / Modify Constraints 按钮
   - 拒绝时需要填写拒绝原因
   - 修改约束时需要填写 add/remove/replace rules
5. **开发者检查器**：
   - 按钮打开
   - 展示编译上下文、编译清单、渲染执行包

**表单状态管理**：使用组件内部 `useState`（不需要放入全局 store）

**行数目标**：< 350 行

---

### 7.3 IncidentDrawer

**文件**：`src/components/overlays/IncidentDrawer.tsx`

**职责**：事件详情抽屉，展示 incident 信息并支持恢复操作

**Props**：
```typescript
type IncidentDrawerProps = {
  isOpen: boolean
  loading: boolean
  incidentData: IncidentDetailData | null
  error: string | null
  submitting: boolean
  onClose: () => void
  onResolve: (input: {
    resolutionSummary: string
    followupAction: string
  }) => Promise<void>
}
```

**内部结构**：
1. Incident 基本信息（ID、类型、严重度、创建时间）
2. 描述和上下文
3. 推荐后续操作
4. 恢复表单：摘要 + 后续操作选择
5. 提交按钮

**行数目标**：< 120 行

---

### 7.4 DependencyInspectorDrawer

**文件**：`src/components/overlays/DependencyInspectorDrawer.tsx`

**职责**：依赖检查器抽屉，展示当前工作流的依赖链、停点和入口

**Props**：
```typescript
type DependencyInspectorDrawerProps = {
  isOpen: boolean
  loading: boolean
  inspectorData: DependencyInspectorData | null
  error: string | null
  onClose: () => void
  onOpenReview: (reviewPackId: string) => void
  onOpenIncident: (incidentId: string) => void
}
```

**内部结构**：
1. 工作流概览
2. 节点依赖列表（按阶段分组）
3. 每个节点：状态、依赖、阻塞原因
4. 可点击的 review/incident 链接

**行数目标**：< 120 行

---

### 7.5 ProviderSettingsDrawer

**文件**：`src/components/overlays/ProviderSettingsDrawer.tsx`

**职责**：运行时 Provider 设置抽屉

**Props**：
```typescript
type ProviderSettingsDrawerProps = {
  isOpen: boolean
  providerData: RuntimeProviderData | null
  loading: boolean
  error: string | null
  submitting: boolean
  onClose: () => void
  onSave: (input: {
    mode: string
    baseUrl: string | null
    apiKey: string | null
    model: string | null
    timeoutSec: number
    reasoningEffort: string | null
  }) => Promise<void>
}
```

**表单字段**：
1. **Mode 选择**：LOCAL_DETERMINISTIC / OPENAI_COMPAT（radio）
2. **Base URL**：文本输入（OPENAI_COMPAT 时必填）
3. **API Key**：密码输入（显示遮罩值，编辑时清空）
4. **Model**：文本输入
5. **Timeout**：数字输入（秒）
6. **Reasoning Effort**：下拉选择（low/medium/high/xhigh/null）

**行为**：
- 切换到 LOCAL_DETERMINISTIC 时，禁用所有 OpenAI 字段
- API Key 显示遮罩值（`sk-***xxxx`），编辑时清空
- 保存后关闭抽屉

**行数目标**：< 180 行

---

## 八、共享基础组件

### 8.1 Button

**文件**：`src/components/shared/Button.tsx`

**Props**：
```typescript
type ButtonProps = {
  variant: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
  children: ReactNode
  onClick?: () => void
  type?: 'button' | 'submit'
}
```

**样式变体**：
- `primary`：冰蓝背景，深色文字
- `secondary`：透明背景，蓝色描边
- `ghost`：无背景无描边，hover 时浅蓝底
- `danger`：暗红背景

**行数目标**：< 40 行

---

### 8.2 Badge

**文件**：`src/components/shared/Badge.tsx`

**Props**：
```typescript
type BadgeProps = {
  variant: 'info' | 'warning' | 'critical' | 'success' | 'muted'
  children: ReactNode
}
```

**行数目标**：< 20 行

---

### 8.3 LoadingSkeleton

**文件**：`src/components/shared/LoadingSkeleton.tsx`

**Props**：
```typescript
type LoadingSkeletonProps = {
  lines?: number  // 默认 3
  width?: string  // 默认 '100%'
}
```

**渲染**：多行脉冲动画条

**行数目标**：< 25 行

---

### 8.4 Toast

**文件**：`src/components/shared/Toast.tsx`

**Props**：
```typescript
type ToastProps = {
  message: string
  variant: 'success' | 'error' | 'info'
  onDismiss: () => void
}
```

**行为**：
- 从右上角滑入
- 5 秒后自动消失
- 可手动关闭
- 使用 `AnimatePresence`

**行数目标**：< 35 行

---

## 九、工具函数

### 9.1 格式化函数 (utils/format.ts)

```typescript
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'No deadline'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function formatRelativeTime(value: string): string {
  const diff = Date.now() - new Date(value).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return formatTimestamp(value)
}

export function normalizeConstraints(value: string): string[] {
  return value.split('\n').map(s => s.trim()).filter(Boolean)
}
```

### 9.2 ID 生成 (utils/ids.ts)

```typescript
export function newPrefixedId(prefix: string): string {
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(6)))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
  return `${prefix}_${hex}`
}
```

---

## 十、CSS 类命名规范

### 10.1 命名规则

使用 BEM-like 扁平命名：

```
.component-name              // 块
.component-name__element     // 元素（仅在必要时使用）
.component-name--modifier    // 修饰符
.component-name-child        // 子组件（优先使用连字符而非 __）
```

### 10.2 示例

```css
.inbox-well { }              /* InboxWell 容器 */
.inbox-item { }              /* 单个收件箱项 */
.inbox-item--high { }        /* 高优先级修饰 */
.inbox-item-ribbon { }       /* 色条子元素 */
.inbox-item-copy { }         /* 文案区域 */
.inbox-item-badges { }       /* 徽章区域 */

.workflow-river { }           /* WorkflowRiver 容器 */
.river-track { }              /* 河道轨道 */
.river-stage { }              /* 单个阶段 */
.river-stage--executing { }   /* 执行中修饰 */
.river-connector { }          /* 阶段连接线 */
.river-board-branch { }       /* 董事会支路 */
.river-board-gate { }         /* 董事会门 */
```

### 10.3 禁止事项

- 不使用 `#id` 选择器
- 不使用 `!important`（除非覆盖第三方库）
- 不使用超过 3 层的嵌套选择器
- 不使用 `style` 属性（除非动态计算值）
