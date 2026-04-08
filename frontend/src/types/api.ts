import type {
  DependencyInspectorNode,
  InboxItem,
  PhaseSummary,
  ReviewPack,
  RoleTemplatesCatalog,
  StaffingHireTemplate,
  WorkforceRoleLane,
  WorkflowSummary,
} from './domain'

export type ProjectionEnvelope<T> = {
  schema_version: string
  generated_at: string
  projection_version: number
  cursor: string | null
  data: T
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
    documentation_sync_summary: string | null
    documentation_update_count: number
    documentation_follow_up_count: number
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

export type InboxData = {
  items: InboxItem[]
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
  role_templates_catalog: RoleTemplatesCatalog
  role_lanes: WorkforceRoleLane[]
}

export type ReviewRoomData = {
  review_pack: ReviewPack | null
  available_actions: string[]
  draft_defaults: {
    selected_option_id?: string | null
    comment_template: string
    elicitation_answers?: Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
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

export type RuntimeProviderEntry = {
  provider_id: string
  adapter_kind: string
  label: string
  enabled: boolean
  base_url: string | null
  api_key_configured: boolean
  api_key_masked: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  command_path: string | null
  capability_tags: string[]
  cost_tier: string
  participation_policy: string
  fallback_provider_ids: string[]
  health_status: string
  health_reason: string
  configured_worker_count: number
  is_default: boolean
}

export type RuntimeProviderRoleBinding = {
  target_ref: string
  target_label: string
  provider_id: string
  model: string | null
}

export type RuntimeProviderFutureBindingSlot = {
  target_ref: string
  label: string
  status: string
  reason: string
  blocked_path_refs: string[]
}

export type RuntimeProviderData = {
  mode: string
  effective_mode: string
  provider_health_summary: string
  provider_id: string | null
  base_url: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  api_key_configured: boolean
  api_key_masked: string | null
  configured_worker_count: number
  effective_reason: string
  default_provider_id: string | null
  providers: RuntimeProviderEntry[]
  role_bindings: RuntimeProviderRoleBinding[]
  future_binding_slots: RuntimeProviderFutureBindingSlot[]
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

export type MeetingParticipantData = {
  employee_id: string
  role_type: string
  meeting_responsibility: string
  is_recorder: boolean
}

export type MeetingRoundData = {
  round_type: string
  round_index: number
  summary: string
  notes: string[]
  completed_at: string
}

export type MeetingDecisionRecordData = {
  format: string
  context: string
  decision: string
  rationale: string[]
  consequences: string[]
  archived_context_refs: string[]
}

export type MeetingDetailData = {
  meeting_id: string
  workflow_id: string
  meeting_type: string
  topic: string
  status: string
  review_status: string | null
  source_ticket_id: string
  source_node_id: string
  review_pack_id: string | null
  opened_at: string
  updated_at: string
  closed_at: string | null
  current_round: string | null
  recorder_employee_id: string
  participants: MeetingParticipantData[]
  rounds: MeetingRoundData[]
  consensus_summary: string | null
  no_consensus_reason: string | null
  decision_record: MeetingDecisionRecordData | null
}

export type CommandAck = {
  command_id: string
  idempotency_key: string
  status: 'ACCEPTED' | 'REJECTED' | 'DUPLICATE'
  received_at: string
  reason?: string | null
  causation_hint?: string | null
}

export type ProjectInitRequest = {
  north_star_goal: string
  hard_constraints: string[]
  budget_cap: number
  deadline_at: string | null
  force_requirement_elicitation?: boolean
}

export type ElicitationAnswerRequest = {
  question_id: string
  selected_option_ids: string[]
  text: string
}

export type RuntimeProviderConfigRequest = {
  provider_id: string
  adapter_kind: string
  label: string
  enabled: boolean
  base_url: string | null
  api_key: string | null
  model: string | null
  timeout_sec: number
  reasoning_effort: string | null
  command_path: string | null
  capability_tags: string[]
  cost_tier: string
  participation_policy: string
  fallback_provider_ids: string[]
}

export type RuntimeProviderRoleBindingRequest = {
  target_ref: string
  provider_id: string
  model: string | null
}

export type RuntimeProviderUpsertRequest = {
  default_provider_id: string | null
  providers: RuntimeProviderConfigRequest[]
  role_bindings: RuntimeProviderRoleBindingRequest[]
  idempotency_key: string
}

export type BoardApproveRequest = {
  review_pack_id: string
  review_pack_version: number
  command_target_version: number
  approval_id: string
  selected_option_id: string
  board_comment: string
  elicitation_answers?: ElicitationAnswerRequest[]
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
  elicitation_answers?: ElicitationAnswerRequest[]
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

export type EmployeeHireRequest = {
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
}

export type EmployeeReplaceRequest = {
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
}
