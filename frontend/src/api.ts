export type ProjectionEnvelope<T> = {
  schema_version: string
  generated_at: string
  projection_version: number
  cursor: string | null
  data: T
}

export type WorkflowSummary = {
  workflow_id: string
  title: string
  north_star_goal: string
  status: string
  current_stage: string
  started_at: string
  deadline_at: string | null
}

export type NodeCounts = {
  pending: number
  executing: number
  under_review: number
  blocked_for_board: number
  fused: number
  completed: number
}

export type PhaseSummary = {
  phase_id: string
  label: string
  status: string
  node_counts: NodeCounts
}

export type DashboardData = {
  workspace: {
    workspace_id: string
    workspace_name: string
  }
  active_workflow: WorkflowSummary | null
  ops_strip: {
    budget_total: number
    budget_used: number
    budget_remaining: number
    token_burn_rate_5m: number
    active_tickets: number
    blocked_nodes: number
    open_incidents: number
    open_circuit_breakers: number
    provider_health_summary: string
  }
  runtime_status: {
    effective_mode: string
    provider_label: string
    model: string | null
    configured_worker_count: number
    provider_health_summary: string
    reason: string
  }
  pipeline_summary: {
    phases: PhaseSummary[]
    critical_path_node_ids: string[]
    blocked_node_ids: string[]
  }
  inbox_counts: {
    approvals_pending: number
    incidents_pending: number
    budget_alerts: number
    provider_alerts: number
  }
  artifact_maintenance: {
    auto_cleanup_enabled: boolean
    cleanup_interval_sec: number
    pending_expired_count: number
    pending_storage_cleanup_count: number
    delete_failed_count: number
  }
  workforce_summary: {
    active_workers: number
    idle_workers: number
    overloaded_workers: number
    active_checkers: number
    workers_in_rework_loop: number
    workers_in_staffing_containment: number
  }
  completion_summary: {
    workflow_id: string
    final_review_pack_id: string
    approved_at: string
    final_review_approved_at: string
    closeout_completed_at: string
    closeout_ticket_id: string
    title: string
    summary: string
    selected_option_id: string | null
    board_comment: string | null
    artifact_refs: string[]
    closeout_artifact_refs: string[]
  } | null
  event_stream_preview: Array<{
    event_id: string
    occurred_at: string
    category: string
    severity: string
    message: string
    related_ref?: string | null
  }>
}

export type InboxItem = {
  inbox_item_id: string
  workflow_id: string
  item_type: string
  priority: string
  status: string
  created_at: string
  sla_due_at?: string | null
  title: string
  summary: string
  source_ref: string
  route_target: {
    view: string
    review_pack_id?: string | null
    incident_id?: string | null
  }
  badges: string[]
}

export type InboxData = {
  items: InboxItem[]
}

export type WorkforceWorker = {
  employee_id: string
  role_type: string
  employment_state: string
  activity_state: string
  current_ticket_id: string | null
  current_node_id: string | null
  provider_id: string | null
  last_update_at?: string | null
  available_actions: WorkforceWorkerAction[]
}

export type WorkforceRoleLane = {
  role_type: string
  active_count: number
  idle_count: number
  workers: WorkforceWorker[]
}

export type WorkforceWorkerAction = {
  action_type: string
  enabled: boolean
  disabled_reason: string | null
  template_id: string | null
}

export type StaffingHireTemplate = {
  template_id: string
  label: string
  role_type: string
  role_profile_refs: string[]
  employee_id_hint: string
  provider_id: string | null
  request_summary: string
  skill_profile: Record<string, string>
  personality_profile: Record<string, string>
  aesthetic_profile: Record<string, string>
}

export type WorkforceData = {
  summary: {
    active_workers: number
    idle_workers: number
    overloaded_workers: number
    active_checkers: number
    workers_in_rework_loop: number
    workers_in_staffing_containment: number
  }
  hire_templates: StaffingHireTemplate[]
  role_lanes: WorkforceRoleLane[]
}

export type ReviewOption = {
  option_id: string
  label: string
  summary: string
  artifact_refs?: string[]
}

export type ReviewPack = {
  meta: {
    approval_id: string
    review_pack_id: string
    review_pack_version: number
    workflow_id: string
    review_type: string
    created_at: string
    priority: string
  }
  subject: {
    title: string
    subtitle?: string | null
    source_node_id?: string | null
    source_ticket_id?: string | null
    blocking_scope?: string | null
    change_kind?: string | null
    employee_id?: string | null
  }
  trigger: {
    trigger_event_id: string
    trigger_reason: string
    why_now: string
  }
  recommendation: {
    recommended_action: string
    recommended_option_id?: string | null
    summary: string
  }
  options: ReviewOption[]
  evidence_summary?: Array<{
    evidence_id: string
    label: string
    summary: string
  }>
  delta_summary?: string | null
  maker_checker_summary?: {
    review_status?: string
    summary?: string
    checker_employee_id?: string
  } | null
  risk_summary?: string[] | null
  budget_impact?: {
    budget_delta_tokens?: number
    summary?: string
  } | null
  decision_form: {
    allowed_actions: string[]
    command_target_version: number
    requires_comment_on_reject: boolean
    requires_constraint_patch_on_modify: boolean
  }
  developer_inspector_refs?: {
    compiled_context_bundle_ref?: string
    compile_manifest_ref?: string
    rendered_execution_payload_ref?: string
  } | null
}

export type ReviewRoomData = {
  review_pack: ReviewPack | null
  available_actions: string[]
  draft_defaults: {
    selected_option_id?: string | null
    comment_template: string
  }
}

export type DeveloperInspectorData = {
  review_pack_id: string
  compile_summary?: {
    source_count: number
    inline_full_count: number
    degraded_source_count: number
    total_budget_tokens: number
    used_budget_tokens: number
    remaining_budget_tokens: number
  } | null
  render_summary?: {
    control_message_count: number
    data_message_count: number
  } | null
  availability: string
}

export type DependencyInspectorNode = {
  node_id: string
  ticket_id: string | null
  parent_ticket_id: string | null
  phase: string
  delivery_stage: string | null
  node_status: string
  ticket_status: string | null
  role_profile_ref: string | null
  output_schema_ref: string | null
  lease_owner: string | null
  depends_on_ticket_id: string | null
  dependent_ticket_ids: string[]
  block_reason: string
  is_critical_path: boolean
  is_blocked: boolean
  expected_artifact_scope: string[]
  open_review_pack_id: string | null
  open_incident_id: string | null
}

export type DependencyInspectorData = {
  workflow: {
    workflow_id: string
    title: string
    current_stage: string
    status: string
  }
  summary: {
    total_nodes: number
    critical_path_nodes: number
    blocked_nodes: number
    open_approvals: number
    open_incidents: number
    current_stop: {
      reason: string
      node_id: string | null
      ticket_id: string | null
      review_pack_id: string | null
      incident_id: string | null
    } | null
  }
  nodes: DependencyInspectorNode[]
}

export type RuntimeProviderData = {
  mode: string
  effective_mode: string
  provider_id: string
  base_url: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  api_key_configured: boolean
  api_key_masked: string | null
  configured_worker_count: number
  effective_reason: string
}

export type IncidentDetailData = {
  incident: {
    incident_id: string
    workflow_id: string
    node_id: string | null
    ticket_id: string | null
    provider_id: string | null
    incident_type: string
    status: string
    severity: string | null
    fingerprint: string
    circuit_breaker_state: string | null
    opened_at: string
    closed_at: string | null
    payload: Record<string, unknown>
  }
  available_followup_actions: string[]
  recommended_followup_action: string | null
}

export type CommandAck = {
  command_id: string
  idempotency_key: string
  status: string
  received_at: string
  reason?: string | null
  causation_hint?: string | null
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function getDashboard(): Promise<DashboardData> {
  const payload = await requestJson<ProjectionEnvelope<DashboardData>>('/api/v1/projections/dashboard')
  return payload.data
}

export async function getInbox(): Promise<InboxData> {
  const payload = await requestJson<ProjectionEnvelope<InboxData>>('/api/v1/projections/inbox')
  return payload.data
}

export async function getRuntimeProvider(): Promise<RuntimeProviderData> {
  const payload = await requestJson<ProjectionEnvelope<RuntimeProviderData>>(
    '/api/v1/projections/runtime-provider',
  )
  return payload.data
}

export async function getWorkforce(): Promise<WorkforceData> {
  const payload = await requestJson<ProjectionEnvelope<WorkforceData>>('/api/v1/projections/workforce')
  return payload.data
}

export async function getReviewRoom(reviewPackId: string): Promise<ReviewRoomData> {
  const payload = await requestJson<ProjectionEnvelope<ReviewRoomData>>(
    `/api/v1/projections/review-room/${reviewPackId}`,
  )
  return payload.data
}

export async function getDependencyInspector(workflowId: string): Promise<DependencyInspectorData> {
  const payload = await requestJson<ProjectionEnvelope<DependencyInspectorData>>(
    `/api/v1/projections/workflows/${workflowId}/dependency-inspector`,
  )
  return payload.data
}

export async function getIncidentDetail(incidentId: string): Promise<IncidentDetailData> {
  const payload = await requestJson<ProjectionEnvelope<IncidentDetailData>>(
    `/api/v1/projections/incidents/${incidentId}`,
  )
  return payload.data
}

export async function getDeveloperInspector(reviewPackId: string): Promise<DeveloperInspectorData> {
  const payload = await requestJson<ProjectionEnvelope<DeveloperInspectorData>>(
    `/api/v1/projections/review-room/${reviewPackId}/developer-inspector`,
  )
  return payload.data
}

export async function projectInit(payload: {
  north_star_goal: string
  hard_constraints: string[]
  budget_cap: number
  deadline_at: string | null
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/project-init', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function runtimeProviderUpsert(payload: {
  mode: string
  base_url: string | null
  api_key: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/runtime-provider-upsert', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function boardApprove(payload: {
  review_pack_id: string
  review_pack_version: number
  command_target_version: number
  approval_id: string
  selected_option_id: string
  board_comment: string
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/board-approve', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function boardReject(payload: {
  review_pack_id: string
  review_pack_version: number
  command_target_version: number
  approval_id: string
  board_comment: string
  rejection_reasons: string[]
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/board-reject', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function modifyConstraints(payload: {
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
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/modify-constraints', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function incidentResolve(payload: {
  incident_id: string
  resolved_by: string
  resolution_summary: string
  followup_action: string
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/incident-resolve', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function employeeFreeze(payload: {
  workflow_id: string
  employee_id: string
  frozen_by: string
  reason: string
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/employee-freeze', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function employeeRestore(payload: {
  workflow_id: string
  employee_id: string
  restored_by: string
  reason: string
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/employee-restore', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function employeeHireRequest(payload: {
  workflow_id: string
  employee_id: string
  role_type: string
  role_profile_refs: string[]
  skill_profile: Record<string, string>
  personality_profile: Record<string, string>
  aesthetic_profile: Record<string, string>
  provider_id: string | null
  request_summary: string
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/employee-hire-request', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function employeeReplaceRequest(payload: {
  workflow_id: string
  replaced_employee_id: string
  replacement_employee_id: string
  replacement_role_type: string
  replacement_role_profile_refs: string[]
  replacement_skill_profile: Record<string, string>
  replacement_personality_profile: Record<string, string>
  replacement_aesthetic_profile: Record<string, string>
  replacement_provider_id: string | null
  request_summary: string
  idempotency_key: string
}): Promise<CommandAck> {
  return requestJson<CommandAck>('/api/v1/commands/employee-replace-request', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
