# Boardroom OS 前端架构指南

> 版本：1.0
> 日期：2026-04-03
> 作者：CTO
> 适用范围：前端开发人员

---

## 一、概述

本文档是 Boardroom OS 前端的完整架构指南。前端是一个**最薄治理控制壳**，它消费后端投影、提交治理命令、展示系统状态，但**不拥有工作流真相**。

### 1.1 核心原则

1. **Projection-first**：前端只消费后端投影 API，不在浏览器中重建工作流状态
2. **Command-submit**：所有写操作通过命令 API 提交，前端不直接修改状态
3. **SSE-invalidate**：通过 SSE 事件流做失效通知，触发重新拉取，不作为第二真相源
4. **视觉克制**：premium near-future operating surface，不是 BI 仪表盘
5. **最小复杂度**：只做治理壳需要的事，不做工作流引擎

### 1.2 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19.2 | UI 框架 |
| TypeScript | 5.9 | 类型安全 |
| Vite | 8.0 | 构建工具 |
| Zustand | 5.x (新增) | 状态管理 |
| React Router | 7.x | 路由 |
| framer-motion | 12.x | 动画 |
| vitest | 4.x | 测试 |
| @testing-library/react | 16.x | 组件测试 |

---

## 二、目标目录结构

```
frontend/src/
├── main.tsx                          # 应用入口
├── App.tsx                           # 路由配置（<50行）
├── types/                            # 共享类型定义
│   ├── domain.ts                     # 领域模型类型
│   ├── api.ts                        # API 响应/请求类型
│   └── ui.ts                         # UI 专用类型
├── api/                              # API 客户端层
│   ├── client.ts                     # 基础 fetch 封装
│   ├── projections.ts                # 投影 API
│   ├── commands.ts                   # 命令 API
│   └── sse.ts                        # SSE 事件流管理
├── stores/                           # Zustand 状态管理
│   ├── boardroom-store.ts            # 主状态 store
│   ├── review-store.ts               # Review Room 状态
│   └── ui-store.ts                   # UI 临时状态（抽屉开关等）
├── pages/                            # 页面组件
│   ├── DashboardPage.tsx             # 主控面板页
│   ├── ReviewRoomPage.tsx            # 审查室页（路由参数驱动）
│   └── IncidentPage.tsx              # 事件详情页（路由参数驱动）
├── components/                       # 功能组件
│   ├── layout/                       # 布局组件
│   │   ├── AppShell.tsx              # 应用外壳
│   │   ├── TopChrome.tsx             # 顶栏
│   │   └── ThreeColumnLayout.tsx     # 三栏布局
│   ├── dashboard/                    # 仪表盘组件
│   │   ├── InboxWell.tsx             # 收件箱
│   │   ├── WorkflowRiver.tsx         # 工作流河道
│   │   ├── OpsStrip.tsx              # 运维指标条
│   │   ├── RuntimeStatusCard.tsx     # 运行时状态卡
│   │   ├── BoardGateIndicator.tsx    # 董事会门指示器
│   │   ├── CompletionCard.tsx        # 完成卡片
│   │   └── ProjectInitForm.tsx       # 项目初始化表单
│   ├── workforce/                    # 员工面板
│   │   ├── WorkforcePanel.tsx        # 员工面板主体
│   │   └── StaffingActions.tsx       # 员工操作按钮组
│   ├── events/                       # 事件流
│   │   └── EventTicker.tsx           # 事件滚动条
│   ├── overlays/                     # 抽屉/覆盖层
│   │   ├── ReviewRoomDrawer.tsx      # 审查室抽屉
│   │   ├── IncidentDrawer.tsx        # 事件详情抽屉
│   │   ├── DependencyInspectorDrawer.tsx  # 依赖检查器
│   │   └── ProviderSettingsDrawer.tsx    # Provider 设置
│   └── shared/                       # 共享基础组件
│       ├── Button.tsx                # 按钮
│       ├── Badge.tsx                 # 徽章
│       ├── Drawer.tsx                # 通用抽屉
│       ├── LoadingSkeleton.tsx       # 加载骨架屏
│       ├── ErrorBoundary.tsx         # 错误边界
│       └── Toast.tsx                 # 提示消息
├── styles/                           # 样式
│   ├── tokens.css                    # 设计令牌（颜色、间距、字体）
│   ├── global.css                    # 全局样式
│   ├── layout.css                    # 布局样式
│   ├── components.css                # 组件样式
│   └── overlays.css                  # 覆盖层样式
├── hooks/                            # 自定义 Hooks
│   ├── useSSE.ts                     # SSE 连接管理
│   ├── useProjection.ts             # 投影数据获取
│   └── useCommand.ts                # 命令提交
└── test/                             # 测试
    ├── setup.ts                      # 测试配置
    ├── mocks/                        # Mock 数据
    │   └── projections.ts            # 投影 Mock
    └── __tests__/                    # 测试文件
        ├── stores/
        ├── components/
        └── api/
```

---

## 三、类型系统设计

### 3.1 领域类型 (types/domain.ts)

```typescript
// ===== 工作流 =====
export type WorkflowStatus = 'PENDING' | 'EXECUTING' | 'COMPLETED' | 'CANCELLED'

export type WorkflowSummary = {
  workflow_id: string
  title: string
  north_star_goal: string
  status: WorkflowStatus
  current_stage: string
  started_at: string
  deadline_at: string | null
}

// ===== 流水线 =====
export type PhaseStatus =
  | 'PENDING'
  | 'EXECUTING'
  | 'UNDER_REVIEW'
  | 'BLOCKED_FOR_BOARD'
  | 'COMPLETED'

export type NodeCounts = {
  pending: number
  executing: number
  under_review: number
  blocked_for_board: number
  fused: number
  completed: number
}

export type PipelinePhase = {
  phase_id: string
  label: string
  status: PhaseStatus
  node_counts: NodeCounts
}

// ===== 收件箱 =====
export type InboxPriority = 'low' | 'medium' | 'high' | 'critical'

export type InboxRouteTarget = {
  view: string
  review_pack_id?: string
  incident_id?: string
}

export type InboxItem = {
  inbox_item_id: string
  title: string
  summary: string
  priority: InboxPriority
  badges: string[]
  route_target: InboxRouteTarget
  created_at: string
}

// ===== 员工 =====
export type EmployeeState = 'ACTIVE' | 'FROZEN' | 'REPLACED'

export type EmployeeSummary = {
  employee_id: string
  role_type: string
  state: EmployeeState
  current_ticket_id: string | null
  current_node_id: string | null
  provider_id: string | null
}

export type RoleLane = {
  role_type: string
  employees: EmployeeSummary[]
}

// ===== 审查 =====
export type ReviewAction = 'APPROVE' | 'REJECT' | 'MODIFY_CONSTRAINTS'

export type ReviewOption = {
  option_id: string
  label: string
  summary: string
  artifact_refs: string[]
  pros: string[]
  cons: string[]
  risks: string[]
}

export type ReviewPackMeta = {
  review_pack_id: string
  review_pack_version: number
  approval_id: string
  review_type: string
  priority: InboxPriority
  title: string
  subtitle: string | null
}

// ===== 事件 =====
export type EventSeverity = 'debug' | 'info' | 'warning' | 'critical'
export type EventCategory = 'workflow' | 'ticket' | 'system' | 'approval'

export type EventStreamItem = {
  event_id: string
  occurred_at: string
  category: EventCategory
  severity: EventSeverity
  event_type: string
  workflow_id: string | null
  node_id: string | null
  ticket_id: string | null
}

// ===== Staffing =====
export type StaffingHireTemplate = {
  template_id: string
  label: string
  role_type: string
  role_profile_refs: string[]
  skill_profile: Record<string, unknown>
  personality_profile: Record<string, unknown>
  aesthetic_profile: Record<string, unknown>
  provider_id: string | null
  request_summary: string
}

export type StaffingAction = {
  action_type: 'freeze' | 'restore' | 'hire_request' | 'replace_request'
  label: string
  enabled: boolean
  hire_template?: StaffingHireTemplate
}
```

### 3.2 API 类型 (types/api.ts)

```typescript
import type { InboxItem, PipelinePhase, WorkflowSummary, RoleLane, EventStreamItem, StaffingHireTemplate, StaffingAction } from './domain'

// ===== 通用信封 =====
export type ProjectionEnvelope<T> = {
  schema_version: string
  generated_at: string
  projection_version: number
  cursor: string | null
  data: T
}

// ===== Dashboard =====
export type DashboardData = {
  workspace: { workspace_id: string; workspace_name: string }
  active_workflow: WorkflowSummary | null
  ops_strip: {
    budget_total: number
    budget_used: number
    budget_remaining: number
    active_tickets: number
    blocked_nodes: number
    open_incidents: number
    open_circuit_breakers: number
    provider_health_summary: string
  }
  pipeline_summary: {
    phases: PipelinePhase[]
    critical_path_node_ids: string[]
    blocked_node_ids: string[]
  }
  inbox_counts: {
    approvals_pending: number
    incidents_pending: number
    budget_alerts: number
    provider_alerts: number
  }
  workforce_summary: {
    active_workers: number
    idle_workers: number
    rework_loops: unknown[]
  }
  runtime_status: {
    effective_mode: string
    provider_label: string
    model: string | null
    configured_worker_count: number
    reason: string
    provider_health_summary: string
  } | null
  completion_summary: {
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
  } | null
  event_stream_preview: EventStreamItem[]
}

// ===== Inbox =====
export type InboxData = {
  items: InboxItem[]
}

// ===== Workforce =====
export type WorkforceData = {
  role_lanes: RoleLane[]
  staffing_hire_templates: StaffingHireTemplate[]
  staffing_actions: Record<string, StaffingAction[]>
}

// ===== Runtime Provider =====
export type RuntimeProviderData = {
  effective_mode: string
  effective_reason: string
  mode: string
  base_url: string | null
  api_key_masked: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  configured_worker_count: number
}

// ===== Review Room =====
export type ReviewRoomData = {
  review_pack: {
    meta: ReviewPackMeta
    decision_form: {
      command_target_version: number
      available_actions: ReviewAction[]
      options: ReviewOption[]
      recommended_option_id: string | null
      recommended_action: ReviewAction
      recommendation_summary: string
      draft_selected_option_id: string | null
      comment_template: string
    }
    context: {
      trigger_reason: string
      why_now: string
      evidence_summary: unknown[]
      maker_checker_summary: unknown | null
      risk_summary: unknown | null
      budget_impact: unknown | null
      developer_inspector_refs: {
        compiled_context_bundle_ref: string | null
        compile_manifest_ref: string | null
        rendered_execution_payload_ref: string | null
      } | null
    }
  } | null
  state: {
    status: string
    decided_at: string | null
    decided_action: string | null
    board_comment: string | null
  }
}

// ===== 命令请求类型 =====
export type ProjectInitRequest = {
  north_star_goal: string
  hard_constraints: string[]
  budget_cap: number
  deadline_at: string | null
}

export type BoardApproveRequest = {
  review_pack_id: string
  review_pack_version: number
  command_target_version: number
  approval_id: string
  selected_option_id: string
  board_comment: string
  idempotency_key: string
}

export type BoardRejectRequest = {
  review_pack_id: string
  review_pack_version: number
  command_target_version: number
  approval_id: string
  board_comment: string
  rejection_reasons: string[]
  idempotency_key: string
}

export type ModifyConstraintsRequest = {
  review_pack_id: string
  review_pack_version: number
  command_target_version: number
  approval_id: string
  constraint_patch: {
    add_rules: string[]
    remove_rules: string[]
    replace_rules: string[]
  }
  board_comment: string
  idempotency_key: string
}

export type IncidentResolveRequest = {
  incident_id: string
  resolved_by: string
  resolution_summary: string
  followup_action: string
  idempotency_key: string
}

export type EmployeeFreezeRequest = {
  workflow_id: string
  employee_id: string
  frozen_by: string
  reason: string
  idempotency_key: string
}

export type EmployeeRestoreRequest = {
  workflow_id: string
  employee_id: string
  restored_by: string
  reason: string
  idempotency_key: string
}

export type EmployeeHireRequestPayload = {
  workflow_id: string
  employee_id: string
  role_type: string
  role_profile_refs: string[]
  skill_profile: Record<string, unknown>
  personality_profile: Record<string, unknown>
  aesthetic_profile: Record<string, unknown>
  provider_id: string | null
  request_summary: string
  idempotency_key: string
}

export type EmployeeReplaceRequestPayload = {
  workflow_id: string
  replaced_employee_id: string
  replacement_employee_id: string
  replacement_role_type: string
  replacement_role_profile_refs: string[]
  replacement_skill_profile: Record<string, unknown>
  replacement_personality_profile: Record<string, unknown>
  replacement_aesthetic_profile: Record<string, unknown>
  replacement_provider_id: string | null
  request_summary: string
  idempotency_key: string
}

export type RuntimeProviderUpsertRequest = {
  mode: string
  base_url: string | null
  api_key: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  idempotency_key: string
}

export type CommandAck = {
  command_id: string
  idempotency_key: string
  status: 'ACCEPTED' | 'REJECTED' | 'DUPLICATE'
  received_at: string
  reason: string | null
}
```

---

## 四、状态管理设计

### 4.1 为什么选 Zustand

- 极简 API，无 boilerplate
- 支持 TypeScript 开箱即用
- 不需要 Provider 包裹
- 支持中间件（devtools、persist）
- 与 React 19 兼容

### 4.2 Store 设计

#### boardroom-store.ts（主 Store）

```typescript
import { create } from 'zustand'
import type { DashboardData, InboxData, WorkforceData, RuntimeProviderData } from '../types/api'

type SnapshotState = {
  // 数据
  dashboard: DashboardData | null
  inbox: InboxData | null
  workforce: WorkforceData | null
  runtimeProvider: RuntimeProviderData | null

  // 加载状态
  snapshotLoading: boolean
  snapshotError: string | null
  runtimeProviderLoading: boolean
  runtimeProviderError: string | null

  // 操作
  loadSnapshot: () => Promise<void>
  setSnapshotError: (error: string | null) => void
}

export const useBoardroomStore = create<SnapshotState>((set, get) => ({
  dashboard: null,
  inbox: null,
  workforce: null,
  runtimeProvider: null,
  snapshotLoading: true,
  snapshotError: null,
  runtimeProviderLoading: true,
  runtimeProviderError: null,

  loadSnapshot: async () => {
    set({ snapshotLoading: true, snapshotError: null, runtimeProviderLoading: true })
    try {
      const [snapshotResult, providerResult] = await Promise.allSettled([
        Promise.all([
          api.getDashboard(),
          api.getInbox(),
          api.getWorkforce(),
        ]),
        api.getRuntimeProvider(),
      ])

      if (snapshotResult.status === 'fulfilled') {
        const [dashboard, inbox, workforce] = snapshotResult.value
        set({ dashboard, inbox, workforce })
      } else {
        set({ snapshotError: snapshotResult.reason?.message ?? 'Failed to load snapshot' })
      }

      if (providerResult.status === 'fulfilled') {
        set({ runtimeProvider: providerResult.value, runtimeProviderError: null })
      } else {
        set({ runtimeProvider: null, runtimeProviderError: providerResult.reason?.message })
      }
    } finally {
      set({ snapshotLoading: false, runtimeProviderLoading: false })
    }
  },

  setSnapshotError: (error) => set({ snapshotError: error }),
}))
```

#### review-store.ts（审查 Store）

```typescript
import { create } from 'zustand'
import type { ReviewRoomData, DeveloperInspectorData } from '../types/api'

type ReviewState = {
  reviewRoom: ReviewRoomData | null
  developerInspector: DeveloperInspectorData | null
  loading: boolean
  inspectorLoading: boolean
  error: string | null
  submittingAction: string | null

  loadReviewRoom: (reviewPackId: string) => Promise<void>
  loadDeveloperInspector: (reviewPackId: string) => Promise<void>
  clearReview: () => void
  setSubmittingAction: (action: string | null) => void
  setError: (error: string | null) => void
}

export const useReviewStore = create<ReviewState>((set) => ({
  reviewRoom: null,
  developerInspector: null,
  loading: false,
  inspectorLoading: false,
  error: null,
  submittingAction: null,

  loadReviewRoom: async (reviewPackId) => {
    set({ loading: true, error: null, developerInspector: null })
    try {
      const data = await api.getReviewRoom(reviewPackId)
      set({ reviewRoom: data })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load review room', reviewRoom: null })
    } finally {
      set({ loading: false })
    }
  },

  loadDeveloperInspector: async (reviewPackId) => {
    set({ inspectorLoading: true })
    try {
      const data = await api.getDeveloperInspector(reviewPackId)
      set({ developerInspector: data })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load inspector' })
    } finally {
      set({ inspectorLoading: false })
    }
  },

  clearReview: () => set({
    reviewRoom: null,
    developerInspector: null,
    loading: false,
    error: null,
    submittingAction: null,
  }),

  setSubmittingAction: (action) => set({ submittingAction: action }),
  setError: (error) => set({ error }),
}))
```

#### ui-store.ts（UI 状态 Store）

```typescript
import { create } from 'zustand'

type UIState = {
  // 抽屉状态
  dependencyInspectorOpen: boolean
  providerSettingsOpen: boolean

  // 操作中状态
  projectInitPending: boolean
  submittingStaffingAction: string | null
  submittingIncidentAction: boolean

  // 操作
  setDependencyInspectorOpen: (open: boolean) => void
  setProviderSettingsOpen: (open: boolean) => void
  setProjectInitPending: (pending: boolean) => void
  setSubmittingStaffingAction: (action: string | null) => void
  setSubmittingIncidentAction: (submitting: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  dependencyInspectorOpen: false,
  providerSettingsOpen: false,
  projectInitPending: false,
  submittingStaffingAction: null,
  submittingIncidentAction: false,

  setDependencyInspectorOpen: (open) => set({ dependencyInspectorOpen: open }),
  setProviderSettingsOpen: (open) => set({ providerSettingsOpen: open }),
  setProjectInitPending: (pending) => set({ projectInitPending: pending }),
  setSubmittingStaffingAction: (action) => set({ submittingStaffingAction: action }),
  setSubmittingIncidentAction: (submitting) => set({ submittingIncidentAction: submitting }),
}))
```

---

## 五、API 客户端设计

### 5.1 基础客户端 (api/client.ts)

```typescript
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    let detail: unknown
    try {
      detail = await response.json()
    } catch {
      // ignore
    }
    throw new ApiError(
      `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      detail,
    )
  }

  return response.json() as Promise<T>
}

export function get<T>(url: string): Promise<T> {
  return request<T>(url)
}

export function post<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
```

### 5.2 投影 API (api/projections.ts)

```typescript
import { get } from './client'
import type { ProjectionEnvelope, DashboardData, InboxData, WorkforceData, RuntimeProviderData, ReviewRoomData } from '../types/api'

export async function getDashboard(): Promise<DashboardData> {
  const envelope = await get<ProjectionEnvelope<DashboardData>>('/api/v1/projections/dashboard')
  return envelope.data
}

export async function getInbox(): Promise<InboxData> {
  const envelope = await get<ProjectionEnvelope<InboxData>>('/api/v1/projections/inbox')
  return envelope.data
}

export async function getWorkforce(): Promise<WorkforceData> {
  const envelope = await get<ProjectionEnvelope<WorkforceData>>('/api/v1/projections/workforce')
  return envelope.data
}

export async function getRuntimeProvider(): Promise<RuntimeProviderData> {
  const envelope = await get<ProjectionEnvelope<RuntimeProviderData>>('/api/v1/projections/runtime-provider')
  return envelope.data
}

export async function getReviewRoom(reviewPackId: string): Promise<ReviewRoomData> {
  const envelope = await get<ProjectionEnvelope<ReviewRoomData>>(`/api/v1/projections/review-room/${reviewPackId}`)
  return envelope.data
}

export async function getDeveloperInspector(reviewPackId: string): Promise<unknown> {
  const envelope = await get<ProjectionEnvelope<unknown>>(
    `/api/v1/projections/review-room/${reviewPackId}/developer-inspector`
  )
  return envelope.data
}

export async function getIncidentDetail(incidentId: string): Promise<unknown> {
  const envelope = await get<ProjectionEnvelope<unknown>>(`/api/v1/projections/incidents/${incidentId}`)
  return envelope.data
}

export async function getDependencyInspector(workflowId: string): Promise<unknown> {
  const envelope = await get<ProjectionEnvelope<unknown>>(
    `/api/v1/projections/workflows/${workflowId}/dependency-inspector`
  )
  return envelope.data
}
```

### 5.3 SSE 管理 (api/sse.ts)

```typescript
type SSEOptions = {
  url: string
  onEvent: () => void
  reconnectDelay?: number
  maxReconnectDelay?: number
}

export class SSEManager {
  private eventSource: EventSource | null = null
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  constructor(private options: SSEOptions) {}

  connect(): void {
    if (this.disposed) return
    this.cleanup()

    const es = new EventSource(this.options.url)
    this.eventSource = es

    es.addEventListener('boardroom-event', () => {
      this.reconnectAttempts = 0
      this.options.onEvent()
    })

    es.addEventListener('heartbeat', () => {
      this.reconnectAttempts = 0
    })

    es.onerror = () => {
      this.cleanup()
      this.scheduleReconnect()
    }
  }

  dispose(): void {
    this.disposed = true
    this.cleanup()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private cleanup(): void {
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
  }

  private scheduleReconnect(): void {
    if (this.disposed) return
    const baseDelay = this.options.reconnectDelay ?? 2000
    const maxDelay = this.options.maxReconnectDelay ?? 30000
    const delay = Math.min(baseDelay * Math.pow(2, this.reconnectAttempts), maxDelay)
    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => this.connect(), delay)
  }
}
```

### 5.4 自定义 Hook: useSSE (hooks/useSSE.ts)

```typescript
import { useEffect, useRef } from 'react'
import { SSEManager } from '../api/sse'

export function useSSE(onInvalidate: () => void): void {
  const callbackRef = useRef(onInvalidate)
  callbackRef.current = onInvalidate

  useEffect(() => {
    if (typeof EventSource === 'undefined') return

    const manager = new SSEManager({
      url: '/api/v1/events/stream',
      onEvent: () => callbackRef.current(),
      reconnectDelay: 2000,
      maxReconnectDelay: 30000,
    })

    manager.connect()
    return () => manager.dispose()
  }, [])
}
```

---

## 六、路由设计

### 6.1 路由表

```typescript
// App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/review/:reviewPackId" element={<DashboardPage />} />
        <Route path="/incident/:incidentId" element={<DashboardPage />} />
      </Routes>
    </BrowserRouter>
  )
}
```

说明：所有路由共享 `DashboardPage`，通过 URL 参数控制抽屉开关。这保持了当前的行为模式——主面板始终可见，审查室和事件详情以抽屉形式覆盖。

---

## 七、样式策略

### 7.1 设计令牌 (styles/tokens.css)

```css
:root {
  /* 颜色 */
  --color-page-bg: #0A111B;
  --color-deep-glass: #101927;
  --color-mid-glass: #172334;
  --color-line-blue: #C7E1FF;
  --color-soft-blue: #DDEEFF;
  --color-active-ice: #ECF7FF;
  --color-muted-label: #9EB3CA;
  --color-board-gold: #E1C68B;
  --color-board-gold-deep: #C7A45E;
  --color-incident-rose: #A34F63;
  --color-incident-deep: #6E2433;
  --color-text-strong: #F0F4FA;
  --color-text-body: #C7D4E4;

  /* 间距 */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;

  /* 圆角 */
  --radius-sm: 8px;
  --radius-md: 16px;
  --radius-lg: 22px;
  --radius-xl: 34px;

  /* 字体 */
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-size-eyebrow: 0.72rem;
  --font-size-body: 0.92rem;
  --font-size-label: 0.86rem;
  --font-size-strong: 1.05rem;

  /* 玻璃效果 */
  --glass-border: 1px solid rgba(199, 225, 255, 0.16);
  --glass-border-subtle: 1px solid rgba(199, 225, 255, 0.08);
  --glass-bg: rgba(12, 21, 33, 0.72);
  --glass-bg-deep: rgba(16, 25, 39, 0.76);

  /* 动画 */
  --transition-fast: 150ms ease;
  --transition-normal: 250ms ease;
  --transition-slow: 400ms ease;
}
```

### 7.2 样式拆分规则

| 文件 | 内容 |
|------|------|
| tokens.css | CSS 变量定义 |
| global.css | body、html、通用 reset |
| layout.css | AppShell、TopChrome、ThreeColumnLayout |
| components.css | 所有功能组件样式 |
| overlays.css | 抽屉、模态框样式 |

每个样式文件使用 BEM-like 命名：`.component-name`、`.component-name__element`、`.component-name--modifier`。

---

## 八、错误处理策略

### 8.1 ErrorBoundary 组件

```typescript
import { Component, type ReactNode } from 'react'

type Props = { children: ReactNode; fallback?: ReactNode }
type State = { hasError: boolean; error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="error-boundary">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
          <button onClick={() => this.setState({ hasError: false, error: null })}>
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
```

### 8.2 错误层级

1. **全局 ErrorBoundary**：包裹整个应用，捕获未处理的渲染错误
2. **页面级 ErrorBoundary**：包裹每个页面组件
3. **组件级错误状态**：通过 store 中的 error 字段展示内联错误
4. **API 错误**：通过 `ApiError` 类型化，在 store action 中 catch 并设置 error 状态

---

## 九、测试策略

### 9.1 测试层级

| 层级 | 工具 | 覆盖范围 |
|------|------|----------|
| Store 单元测试 | vitest | 每个 store 的 action 和状态变化 |
| 组件渲染测试 | vitest + @testing-library/react | 组件渲染、交互、状态 |
| API 客户端测试 | vitest + MSW | API 请求/响应/错误处理 |
| 集成测试 | vitest + @testing-library/react | 页面级用户流程 |

### 9.2 Mock 策略

- 使用 `test/mocks/projections.ts` 提供标准 mock 数据
- API 层使用 vi.mock 或 MSW 拦截
- Store 测试直接调用 action，不需要渲染组件

### 9.3 最低测试要求

- 每个 store 至少 3 个测试（加载成功、加载失败、操作提交）
- 每个页面组件至少 2 个测试（正常渲染、错误状态）
- API 客户端至少 5 个测试（成功、4xx、5xx、网络错误、超时）
- SSE 管理器至少 3 个测试（连接、断开重连、dispose）

---

## 十、动画规范

### 10.1 framer-motion 使用规则

只在以下场景使用 framer-motion：

1. **抽屉进出**：`AnimatePresence` + `motion.div` 滑入/滑出
2. **Board Gate 呼吸**：CSS animation（不用 framer-motion）
3. **Ticket 粒子漂移**：CSS animation（不用 framer-motion）
4. **列表项进入**：`motion.div` + `initial/animate` 淡入
5. **Toast 通知**：`AnimatePresence` + `motion.div`

### 10.2 抽屉动画变体

```typescript
export const drawerVariants = {
  hidden: { x: '100%', opacity: 0 },
  visible: { x: 0, opacity: 1, transition: { type: 'spring', damping: 25, stiffness: 200 } },
  exit: { x: '100%', opacity: 0, transition: { duration: 0.2 } },
}
```

### 10.3 Board Gate 呼吸动画

```css
@keyframes boardPulse {
  0%, 100% { box-shadow: 0 0 0 1px rgba(225, 198, 139, 0.2), 0 0 18px rgba(225, 198, 139, 0.48); }
  50% { box-shadow: 0 0 0 1px rgba(225, 198, 139, 0.3), 0 0 28px rgba(225, 198, 139, 0.64); }
}
```

---

## 十一、性能考虑

1. **投影缓存**：Store 中保持最新投影，SSE 触发增量刷新而非全量重载
2. **懒加载抽屉**：ReviewRoomDrawer、IncidentDrawer 等使用 `React.lazy` + `Suspense`
3. **事件节流**：SSE 事件触发的刷新使用 debounce（500ms）
4. **列表虚拟化**：如果 Inbox 或 EventTicker 超过 50 项，考虑虚拟滚动
5. **图片懒加载**：artifact 预览图使用 `loading="lazy"`

---

## 十二、迁移策略

从当前 monolithic App.tsx 迁移到新架构的步骤：

1. **安装 Zustand**：`npm install zustand`
2. **创建目录结构**：按照第二节创建所有目录
3. **提取类型**：从 `api.ts` 中提取类型到 `types/`
4. **创建 API 客户端**：从 `api.ts` 中提取 fetch 函数到 `api/`
5. **创建 Stores**：将 App.tsx 中的 useState 迁移到 Zustand stores
6. **提取共享组件**：Button、Badge、Drawer、ErrorBoundary
7. **提取功能组件**：逐个从 App.tsx 中提取
8. **创建页面组件**：DashboardPage 组装所有功能组件
9. **简化 App.tsx**：只保留路由配置
10. **拆分 CSS**：按组件拆分到对应样式文件
11. **添加测试**：为每个新模块添加测试
12. **删除旧代码**：确认所有功能正常后删除旧的 api.ts 和大 App.tsx

每一步都应该是可独立验证的——完成一步后运行 `npm run build` 和 `npm run test:run` 确认无回归。
