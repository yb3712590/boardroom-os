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
    meeting_id?: string | null
  }
  badges: string[]
}

export type WorkforceWorkerAction = {
  action_type: string
  enabled: boolean
  disabled_reason: string | null
  template_id: string | null
}

export type EmployeeProfileBundle = {
  skill_profile: Record<string, string>
  personality_profile: Record<string, string>
  aesthetic_profile: Record<string, string>
}

export type WorkforceWorker = {
  employee_id: string
  role_type: string
  employment_state: string
  activity_state: string
  current_ticket_id: string | null
  current_node_id: string | null
  provider_id: string | null
  skill_profile: Record<string, string>
  personality_profile: Record<string, string>
  aesthetic_profile: Record<string, string>
  profile_summary: string
  source_template_id?: string | null
  source_fragment_refs?: string[]
  last_update_at?: string | null
  available_actions: WorkforceWorkerAction[]
}

export type WorkforceRoleLane = {
  role_type: string
  active_count: number
  idle_count: number
  workers: WorkforceWorker[]
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

export type RoleTemplateDocumentKind = {
  kind_ref: string
  label: string
  summary: string
}

export type RoleTemplateFragment = {
  fragment_id: string
  fragment_kind: string
  label: string
  summary: string
  payload: Record<string, string>
}

export type RoleTemplateMainlineBoundary = {
  boundary_status: string
  active_path_refs: string[]
  blocked_path_refs: string[]
}

export type RoleTemplate = {
  template_id: string
  template_kind: string
  label: string
  role_family: string
  role_type: string
  canonical_role_ref: string
  alias_role_profile_refs: string[]
  provider_target_ref: string
  participation_mode: string
  execution_boundary: string
  status: string
  default_document_kind_refs: string[]
  responsibility_summary: string
  summary: string
  composition: {
    fragment_refs: string[]
  }
  mainline_boundary: RoleTemplateMainlineBoundary
}

export type RoleTemplatesCatalog = {
  role_templates: RoleTemplate[]
  document_kinds: RoleTemplateDocumentKind[]
  fragments: RoleTemplateFragment[]
}

export type ReviewPackEmployeeChange = {
  change_kind: string
  employee_id?: string | null
  replacement_employee_id?: string | null
  role_type?: string | null
  role_profile_refs?: string[]
  skill_profile?: Record<string, string>
  personality_profile?: Record<string, string>
  aesthetic_profile?: Record<string, string>
  replacement_role_type?: string | null
  replacement_role_profile_refs?: string[]
  replacement_skill_profile?: Record<string, string>
  replacement_personality_profile?: Record<string, string>
  replacement_aesthetic_profile?: Record<string, string>
  provider_id?: string | null
  replacement_provider_id?: string | null
}

export type ReviewOption = {
  option_id: string
  label: string
  summary: string
  artifact_refs?: string[]
}

export type ElicitationQuestion = {
  question_id: string
  prompt: string
  response_kind: 'SINGLE_SELECT' | 'MULTI_SELECT' | 'TEXT'
  required: boolean
  options: Array<{
    option_id: string
    label: string
    summary?: string | null
  }>
}

export type ElicitationAnswer = {
  question_id: string
  selected_option_ids: string[]
  text: string
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
    source_ref?: string | null
  }>
  delta_summary?: string | Record<string, unknown> | null
  maker_checker_summary?: {
    review_status?: string
    summary?: string
    checker_employee_id?: string
  } | null
  risk_summary?: string[] | string | Record<string, unknown> | null
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
  employee_change?: ReviewPackEmployeeChange | null
  elicitation_questionnaire?: ElicitationQuestion[] | null
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
