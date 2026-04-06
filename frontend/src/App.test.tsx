import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

type JsonRecord = Record<string, unknown>

class FakeEventSource {
  static instances: FakeEventSource[] = []

  url: string
  listeners: Map<string, Set<() => void>>

  constructor(url: string) {
    this.url = url
    this.listeners = new Map()
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: () => void) {
    const listeners = this.listeners.get(type) ?? new Set()
    listeners.add(listener)
    this.listeners.set(type, listeners)
  }

  removeEventListener(type: string, listener: () => void) {
    this.listeners.get(type)?.delete(listener)
  }

  close() {}

  emit(type: string) {
    this.listeners.get(type)?.forEach((listener) => listener())
  }
}

function envelope<T>(data: T) {
  return {
    schema_version: '2026-03-28.boardroom.v1',
    generated_at: '2026-04-01T23:10:00+08:00',
    projection_version: 42,
    cursor: 'evt_000042',
    data,
  }
}

function phase(
  label: string,
  status: string,
  counts: Partial<{
    pending: number
    executing: number
    under_review: number
    blocked_for_board: number
    fused: number
    completed: number
  }> = {},
) {
  return {
    phase_id: `phase_${label.toLowerCase()}`,
    label,
    status,
    node_counts: {
      pending: 0,
      executing: 0,
      under_review: 0,
      blocked_for_board: 0,
      fused: 0,
      completed: 0,
      ...counts,
    },
  }
}

function reviewRoomData() {
  return {
    review_pack: {
      meta: {
        approval_id: 'apr_001',
        review_pack_id: 'brp_001',
        review_pack_version: 1,
        workflow_id: 'wf_001',
        review_type: 'VISUAL_MILESTONE',
        created_at: '2026-04-01T23:08:00+08:00',
        priority: 'high',
      },
      subject: {
        title: 'Review homepage visual milestone',
        subtitle: 'The latest maker-checker pass is ready for board review.',
        source_node_id: 'node_homepage_visual',
        source_ticket_id: 'tkt_visual_002',
        blocking_scope: 'NODE_ONLY',
      },
      trigger: {
        trigger_event_id: 'evt_000041',
        trigger_reason: 'Visual milestone is ready for board review.',
        why_now: 'Checker approved the current revision.',
      },
      recommendation: {
        recommended_action: 'APPROVE',
        recommended_option_id: 'option_a',
        summary: 'Approve option A to unblock the main build path.',
      },
      options: [
        {
          option_id: 'option_a',
          label: 'Option A',
          summary: 'Balanced visual direction with explicit review evidence.',
          artifact_refs: ['art://runtime/tkt_visual_002/option-a.png'],
        },
      ],
      evidence_summary: [
        {
          evidence_id: 'evidence_visual_consistency',
          label: 'Visual consistency',
          summary: 'The latest draft keeps the approved river layout and board cue hierarchy.',
          artifact_refs: [],
        },
      ],
      delta_summary: 'The board gate cue is now isolated in gold and the river motion is calmer.',
      maker_checker_summary: {
        review_status: 'APPROVED_WITH_NOTES',
        summary: 'Checker approved the deliverable with one downstream polish note.',
        checker_employee_id: 'emp_checker_1',
      },
      risk_summary: ['Further copy polish may still be needed after approval.'],
      budget_impact: {
        budget_delta_tokens: 4200,
        summary: 'No budget exception required for this approval.',
      },
      decision_form: {
        allowed_actions: ['APPROVE', 'REJECT', 'MODIFY_CONSTRAINTS'],
        command_target_version: 7,
        requires_comment_on_reject: true,
        requires_constraint_patch_on_modify: true,
      },
      developer_inspector_refs: {
        compiled_context_bundle_ref: 'ctx://homepage/visual-v1',
        compile_manifest_ref: 'manifest://homepage/visual-v1',
      },
    },
    available_actions: ['APPROVE', 'REJECT', 'MODIFY_CONSTRAINTS'],
    draft_defaults: {
      selected_option_id: 'option_a',
      comment_template: 'Board review note',
    },
  }
}

function meetingRoomData() {
  return {
    meeting_id: 'mtg_001',
    workflow_id: 'wf_001',
    meeting_type: 'TECHNICAL_DECISION',
    topic: 'Decide the homepage runtime contract',
    status: 'CLOSED',
    review_status: 'BOARD_REVIEW_PENDING',
    source_ticket_id: 'tkt_meeting_001',
    source_node_id: 'node_meeting_001',
    review_pack_id: 'brp_001',
    opened_at: '2026-04-05T10:00:00+08:00',
    updated_at: '2026-04-05T10:08:00+08:00',
    closed_at: '2026-04-05T10:08:00+08:00',
    current_round: 'CONVERGENCE',
    recorder_employee_id: 'emp_frontend_2',
    participants: [
      {
        employee_id: 'emp_frontend_2',
        role_type: 'frontend_engineer',
        meeting_responsibility: 'implementation feasibility',
        is_recorder: true,
      },
      {
        employee_id: 'emp_checker_1',
        role_type: 'checker',
        meeting_responsibility: 'validation pressure',
        is_recorder: false,
      },
    ],
    rounds: [
      {
        round_type: 'POSITION',
        round_index: 1,
        summary: 'Position round closed.',
        notes: ['emp_frontend_2 stated the main constraint.'],
        completed_at: '2026-04-05T10:02:00+08:00',
      },
      {
        round_type: 'CONVERGENCE',
        round_index: 4,
        summary: 'Convergence round closed.',
        notes: ['emp_checker_1 confirmed the final technical decision summary.'],
        completed_at: '2026-04-05T10:08:00+08:00',
      },
    ],
    consensus_summary: 'The meeting converged on one runtime contract.',
    no_consensus_reason: null,
    decision_record: null,
  }
}

function workforceAction(
  actionType: string,
  enabled: boolean,
  disabledReason: string | null = null,
  templateId: string | null = null,
) {
  return {
    action_type: actionType,
    enabled,
    disabled_reason: disabledReason,
    template_id: templateId,
  }
}

function hireTemplates() {
  return [
    {
      template_id: 'frontend_engineer_backup',
      label: 'Frontend backup maker',
      role_type: 'frontend_engineer',
      role_profile_refs: ['frontend_engineer_primary'],
      employee_id_hint: 'emp_frontend_backup',
      provider_id: 'prov_openai_compat',
      request_summary: 'Hire a backup frontend maker for rework rotation.',
      skill_profile: {
        primary_domain: 'frontend',
        system_scope: 'surface_polish',
        validation_bias: 'finish_first',
      },
      personality_profile: {
        risk_posture: 'cautious',
        challenge_style: 'probing',
        execution_pace: 'measured',
        detail_rigor: 'rigorous',
        communication_style: 'concise',
      },
      aesthetic_profile: {
        surface_preference: 'polished',
        information_density: 'layered',
        motion_tolerance: 'restrained',
      },
    },
    {
      template_id: 'checker_backup',
      label: 'Checker backup',
      role_type: 'checker',
      role_profile_refs: ['checker_primary'],
      employee_id_hint: 'emp_checker_backup',
      provider_id: 'prov_openai_compat',
      request_summary: 'Hire a backup checker to keep internal review moving.',
      skill_profile: {
        primary_domain: 'quality',
        system_scope: 'release_sweep',
        validation_bias: 'regression_first',
      },
      personality_profile: {
        risk_posture: 'cautious',
        challenge_style: 'constructive',
        execution_pace: 'deliberate',
        detail_rigor: 'sweeping',
        communication_style: 'concise',
      },
      aesthetic_profile: {
        surface_preference: 'clarifying',
        information_density: 'balanced',
        motion_tolerance: 'restrained',
      },
    },
  ]
}

function workforceData() {
  return {
    summary: {
      active_workers: 1,
      idle_workers: 1,
      overloaded_workers: 0,
      active_checkers: 1,
      workers_in_rework_loop: 0,
      workers_in_staffing_containment: 0,
    },
    hire_templates: hireTemplates(),
    governance_templates: {
      role_templates: [
        {
          template_id: 'cto_governance',
          label: 'CTO / 架构治理',
          role_type: 'governance_cto',
          role_profile_ref: 'cto_primary',
          provider_target_ref: 'role_profile:cto_primary',
          participation_mode: 'LOW_FREQUENCY_HIGH_LEVERAGE',
          execution_boundary: '默认不承担日常编码、测试或持续实施主力工作。',
          status: 'NOT_ENABLED',
          default_document_kind_refs: [
            'architecture_brief',
            'technology_decision',
            'milestone_plan',
            'backlog_recommendation',
          ],
          summary: 'Shape architecture, major decisions, and backlog direction.',
        },
        {
          template_id: 'architect_governance',
          label: '架构师 / 设计评审',
          role_type: 'governance_architect',
          role_profile_ref: 'architect_primary',
          provider_target_ref: 'role_profile:architect_primary',
          participation_mode: 'LOW_FREQUENCY_HIGH_LEVERAGE',
          execution_boundary: '默认不承担日常编码、测试或持续实施主力工作。',
          status: 'NOT_ENABLED',
          default_document_kind_refs: ['architecture_brief', 'technology_decision', 'detailed_design'],
          summary: 'Review design detail and keep implementation aligned to architecture.',
        },
      ],
      document_kinds: [
        {
          kind_ref: 'architecture_brief',
          label: '架构方案',
          summary: 'Frame the target architecture and major tradeoffs.',
        },
        {
          kind_ref: 'technology_decision',
          label: '技术选型',
          summary: 'Capture option comparisons and final decisions.',
        },
        {
          kind_ref: 'milestone_plan',
          label: '里程碑拆解',
          summary: 'Outline milestone sequence and delivery checkpoints.',
        },
        {
          kind_ref: 'detailed_design',
          label: '详细设计',
          summary: 'Explain implementation boundaries and interface decisions.',
        },
        {
          kind_ref: 'backlog_recommendation',
          label: 'TODO / Backlog 建议',
          summary: 'Recommend next execution slices without opening runtime support.',
        },
      ],
    },
    role_lanes: [
      {
        role_type: 'frontend_engineer',
        active_count: 1,
        idle_count: 1,
        workers: [
          {
            employee_id: 'emp_frontend_2',
            role_type: 'frontend_engineer',
            employment_state: 'ACTIVE',
            activity_state: 'EXECUTING',
            current_ticket_id: 'tkt_visual_002',
            current_node_id: 'node_homepage_visual',
            provider_id: 'prov_openai_compat',
            skill_profile: {
              primary_domain: 'frontend',
              system_scope: 'delivery_slice',
              validation_bias: 'balanced',
            },
            personality_profile: {
              risk_posture: 'assertive',
              challenge_style: 'constructive',
              execution_pace: 'fast',
              detail_rigor: 'focused',
              communication_style: 'direct',
            },
            aesthetic_profile: {
              surface_preference: 'functional',
              information_density: 'balanced',
              motion_tolerance: 'measured',
            },
            profile_summary:
              'Skill frontend, delivery slice, balanced. Personality assertive, constructive, fast, focused, direct. Aesthetic functional, balanced, measured.',
            last_update_at: '2026-04-01T23:08:00+08:00',
            available_actions: [
              workforceAction('FREEZE', true),
              workforceAction('RESTORE', false, 'Only frozen workers can be restored.'),
              workforceAction('REPLACE', true, null, 'frontend_engineer_backup'),
            ],
          },
          {
            employee_id: 'emp_frontend_backup',
            role_type: 'frontend_engineer',
            employment_state: 'ACTIVE',
            activity_state: 'IDLE',
            current_ticket_id: null,
            current_node_id: null,
            provider_id: null,
            skill_profile: {
              primary_domain: 'frontend',
              system_scope: 'surface_polish',
              validation_bias: 'finish_first',
            },
            personality_profile: {
              risk_posture: 'cautious',
              challenge_style: 'probing',
              execution_pace: 'measured',
              detail_rigor: 'rigorous',
              communication_style: 'concise',
            },
            aesthetic_profile: {
              surface_preference: 'polished',
              information_density: 'layered',
              motion_tolerance: 'restrained',
            },
            profile_summary:
              'Skill frontend, surface polish, finish first. Personality cautious, probing, measured, rigorous, concise. Aesthetic polished, layered, restrained.',
            last_update_at: '2026-04-01T23:07:00+08:00',
            available_actions: [
              workforceAction('FREEZE', true),
              workforceAction('RESTORE', false, 'Only frozen workers can be restored.'),
              workforceAction('REPLACE', true, null, 'frontend_engineer_backup'),
            ],
          },
        ],
      },
      {
        role_type: 'checker',
        active_count: 1,
        idle_count: 0,
        workers: [
          {
            employee_id: 'emp_checker_1',
            role_type: 'checker',
            employment_state: 'ACTIVE',
            activity_state: 'REVIEWING',
            current_ticket_id: 'tkt_checker_001',
            current_node_id: 'node_homepage_visual',
            provider_id: null,
            skill_profile: {
              primary_domain: 'quality',
              system_scope: 'release_guard',
              validation_bias: 'evidence_first',
            },
            personality_profile: {
              risk_posture: 'guarded',
              challenge_style: 'probing',
              execution_pace: 'measured',
              detail_rigor: 'rigorous',
              communication_style: 'forensic',
            },
            aesthetic_profile: {
              surface_preference: 'systematic',
              information_density: 'dense',
              motion_tolerance: 'minimal',
            },
            profile_summary:
              'Skill quality, release guard, evidence first. Personality guarded, probing, measured, rigorous, forensic. Aesthetic systematic, dense, minimal.',
            last_update_at: '2026-04-01T23:08:00+08:00',
            available_actions: [
              workforceAction('FREEZE', true),
              workforceAction('RESTORE', false, 'Only frozen workers can be restored.'),
              workforceAction('REPLACE', true, null, 'checker_backup'),
            ],
          },
        ],
      },
    ],
  }
}

function incidentDetailData(overrides: Partial<JsonRecord> = {}) {
  return {
    incident: {
      incident_id: 'inc_093',
      workflow_id: 'wf_001',
      node_id: 'node_homepage_visual',
      ticket_id: 'tkt_visual_002',
      provider_id: null,
      incident_type: 'RUNTIME_TIMEOUT_ESCALATION',
      status: 'OPEN',
      severity: 'high',
      fingerprint: 'wf_001:node_homepage_visual:runtime-timeout',
      circuit_breaker_state: 'OPEN',
      opened_at: '2026-04-01T23:09:00+08:00',
      closed_at: null,
      payload: {
        timeout_streak_count: 2,
        latest_failure_kind: 'TIMEOUT_SLA_EXCEEDED',
      },
    },
    available_followup_actions: ['RESTORE_ONLY', 'RESTORE_AND_RETRY_LATEST_TIMEOUT'],
    recommended_followup_action: 'RESTORE_AND_RETRY_LATEST_TIMEOUT',
    ...overrides,
  }
}

function inspectorData() {
  return {
    review_pack_id: 'brp_001',
    compiled_context_bundle_ref: 'ctx://homepage/visual-v1',
    compile_manifest_ref: 'manifest://homepage/visual-v1',
    rendered_execution_payload_ref: 'render://homepage/visual-v1',
    compiled_context_bundle: {
      context_blocks: [
        {
          title: 'Design brief',
          content_mode: 'INLINE_FULL',
        },
      ],
    },
    compile_manifest: {
      source_log: [],
    },
    rendered_execution_payload: {
      summary: {
        control_message_count: 3,
        data_message_count: 1,
      },
    },
    compile_summary: {
      source_count: 1,
      inline_full_count: 1,
      inline_fragment_count: 0,
      inline_partial_count: 0,
      reference_only_count: 0,
      degraded_source_count: 0,
      missing_critical_source_count: 0,
      reason_counts: {},
      retrieved_source_count: 0,
      retrieval_channel_counts: {},
      dropped_retrieval_count: 0,
      total_budget_tokens: 3000,
      used_budget_tokens: 1200,
      remaining_budget_tokens: 1800,
      truncated_tokens: 0,
      dropped_explicit_source_count: 0,
      media_reference_count: 0,
      download_attachment_count: 0,
      fragment_strategy_counts: {},
      preview_strategy_counts: {},
      preview_kind_counts: {},
    },
    render_summary: {
      control_message_count: 3,
      data_message_count: 1,
    },
    availability: 'ready',
  }
}

function dependencyInspectorData(overrides: Partial<JsonRecord> = {}) {
  return {
    workflow: {
      workflow_id: 'wf_001',
      title: 'Boardroom UI MVP',
      current_stage: 'project_init',
      status: 'EXECUTING',
    },
    summary: {
      total_nodes: 4,
      critical_path_nodes: 4,
      blocked_nodes: 1,
      open_approvals: 1,
      open_incidents: 0,
      current_stop: {
        reason: 'BOARD_REVIEW_OPEN',
        node_id: 'node_homepage_review',
        ticket_id: 'tkt_homepage_review',
        review_pack_id: 'brp_001',
        incident_id: null,
      },
    },
    nodes: [
      {
        node_id: 'node_scope_decision',
        ticket_id: 'tkt_scope_decision',
        parent_ticket_id: null,
        phase: 'Plan',
        delivery_stage: null,
        node_status: 'COMPLETED',
        ticket_status: 'COMPLETED',
        role_profile_ref: 'ui_designer_primary',
        output_schema_ref: 'consensus_document',
        lease_owner: null,
        depends_on_ticket_id: null,
        dependent_ticket_ids: ['tkt_homepage_build'],
        block_reason: 'COMPLETED',
        is_critical_path: true,
        is_blocked: false,
        expected_artifact_scope: ['reports/meeting/*'],
        open_review_pack_id: null,
        open_incident_id: null,
      },
      {
        node_id: 'node_homepage_build',
        ticket_id: 'tkt_homepage_build',
        parent_ticket_id: 'tkt_scope_decision',
        phase: 'Build',
        delivery_stage: 'BUILD',
        node_status: 'COMPLETED',
        ticket_status: 'COMPLETED',
        role_profile_ref: 'ui_designer_primary',
        output_schema_ref: 'implementation_bundle',
        lease_owner: null,
        depends_on_ticket_id: 'tkt_scope_decision',
        dependent_ticket_ids: ['tkt_homepage_check'],
        block_reason: 'COMPLETED',
        is_critical_path: true,
        is_blocked: false,
        expected_artifact_scope: ['artifacts/ui/scope-followups/tkt_homepage_build/*'],
        open_review_pack_id: null,
        open_incident_id: null,
      },
      {
        node_id: 'node_homepage_check',
        ticket_id: 'tkt_homepage_check',
        parent_ticket_id: 'tkt_homepage_build',
        phase: 'Check',
        delivery_stage: 'CHECK',
        node_status: 'COMPLETED',
        ticket_status: 'COMPLETED',
        role_profile_ref: 'checker_primary',
        output_schema_ref: 'delivery_check_report',
        lease_owner: null,
        depends_on_ticket_id: 'tkt_homepage_build',
        dependent_ticket_ids: ['tkt_homepage_review'],
        block_reason: 'COMPLETED',
        is_critical_path: true,
        is_blocked: false,
        expected_artifact_scope: ['reports/check/tkt_homepage_check/*'],
        open_review_pack_id: null,
        open_incident_id: null,
      },
      {
        node_id: 'node_homepage_review',
        ticket_id: 'tkt_homepage_review',
        parent_ticket_id: 'tkt_homepage_check',
        phase: 'Review',
        delivery_stage: 'REVIEW',
        node_status: 'BLOCKED_FOR_BOARD_REVIEW',
        ticket_status: 'BLOCKED_FOR_BOARD_REVIEW',
        role_profile_ref: 'ui_designer_primary',
        output_schema_ref: 'ui_milestone_review',
        lease_owner: null,
        depends_on_ticket_id: 'tkt_homepage_check',
        dependent_ticket_ids: [],
        block_reason: 'BOARD_REVIEW_OPEN',
        is_critical_path: true,
        is_blocked: true,
        expected_artifact_scope: [
          'artifacts/ui/scope-followups/tkt_homepage_review/*',
          'reports/review/tkt_homepage_review/*',
        ],
        open_review_pack_id: 'brp_001',
        open_incident_id: null,
      },
    ],
    ...overrides,
  }
}

function runtimeProviderData(overrides: Partial<JsonRecord> = {}) {
  return {
    mode: 'DETERMINISTIC',
    effective_mode: 'LOCAL_DETERMINISTIC',
    provider_health_summary: 'LOCAL_ONLY',
    provider_id: null,
    base_url: null,
    model: null,
    timeout_sec: 30,
    reasoning_effort: null,
    api_key_configured: false,
    api_key_masked: null,
    configured_worker_count: 1,
    effective_reason: 'Runtime is using the local deterministic path.',
    default_provider_id: null,
    providers: [
      {
        provider_id: 'prov_openai_compat',
        adapter_kind: 'openai_compat',
        label: 'OpenAI Compat',
        enabled: false,
        base_url: null,
        api_key_configured: false,
        api_key_masked: null,
        model: null,
        timeout_sec: 30,
        reasoning_effort: null,
        command_path: null,
        capability_tags: ['structured_output', 'planning', 'implementation'],
        fallback_provider_ids: [],
        health_status: 'DISABLED',
        health_reason: 'OpenAI-compatible provider is disabled.',
        configured_worker_count: 1,
        is_default: false,
      },
      {
        provider_id: 'prov_claude_code',
        adapter_kind: 'claude_code_cli',
        label: 'Claude Code CLI',
        enabled: false,
        base_url: null,
        api_key_configured: false,
        api_key_masked: null,
        model: null,
        timeout_sec: 30,
        reasoning_effort: null,
        command_path: null,
        capability_tags: ['structured_output', 'planning', 'implementation', 'review'],
        fallback_provider_ids: [],
        health_status: 'DISABLED',
        health_reason: 'Claude Code CLI provider is disabled.',
        configured_worker_count: 0,
        is_default: false,
      },
    ],
    role_bindings: [],
    future_binding_slots: [
      {
        target_ref: 'role_profile:cto_primary',
        label: 'CTO / 架构治理',
        status: 'NOT_ENABLED',
        reason: '治理模板角色尚未纳入当前主线。',
      },
      {
        target_ref: 'role_profile:architect_primary',
        label: '架构师 / 设计评审',
        status: 'NOT_ENABLED',
        reason: '治理模板角色尚未纳入当前主线。',
      },
    ],
    ...overrides,
  }
}

function dashboardData(overrides: Partial<JsonRecord> = {}) {
  return {
    workspace: {
      workspace_id: 'ws_default',
      workspace_name: 'Default Workspace',
    },
    active_workflow: {
      workflow_id: 'wf_001',
      title: 'Boardroom UI MVP',
      north_star_goal: 'Ship the thinnest governance shell from dashboard to review room.',
      status: 'EXECUTING',
      current_stage: 'project_init',
      started_at: '2026-04-01T22:30:00+08:00',
      deadline_at: null,
    },
    ops_strip: {
      budget_total: 500000,
      budget_used: 18200,
      budget_remaining: 481800,
      token_burn_rate_5m: 880,
      active_tickets: 1,
      blocked_nodes: 1,
      open_incidents: 0,
      open_circuit_breakers: 0,
      provider_health_summary: 'LOCAL_ONLY',
    },
    runtime_status: {
      effective_mode: 'LOCAL_DETERMINISTIC',
      provider_label: 'Local Deterministic',
      model: null,
      configured_worker_count: 1,
      provider_health_summary: 'LOCAL_ONLY',
      reason: 'Runtime is using the local deterministic path.',
    },
    pipeline_summary: {
      phases: [
        phase('Intake', 'COMPLETED', { completed: 1 }),
        phase('Plan', 'COMPLETED', { completed: 1 }),
        phase('Build', 'EXECUTING', { executing: 1 }),
        phase('Check', 'PENDING'),
        phase('Review', 'PENDING'),
      ],
      critical_path_node_ids: ['node_homepage_visual'],
      blocked_node_ids: [],
    },
    inbox_counts: {
      approvals_pending: 0,
      incidents_pending: 0,
      budget_alerts: 0,
      provider_alerts: 0,
    },
    artifact_maintenance: {
      auto_cleanup_enabled: true,
      cleanup_interval_sec: 300,
      ephemeral_default_ttl_sec: 3600,
      retention_defaults: {
        EPHEMERAL: 3600,
        REVIEW_EVIDENCE: 604800,
      },
      pending_expired_count: 0,
      pending_storage_cleanup_count: 0,
      delete_failed_count: 0,
      legacy_unknown_retention_count: 0,
      last_run_at: '2026-04-01T22:55:00+08:00',
      last_cleaned_by: 'system:artifact-cleanup',
      last_trigger: 'auto_scheduler',
      last_expired_count: 0,
      last_storage_deleted_count: 0,
    },
    workforce_summary: {
      active_workers: 1,
      idle_workers: 1,
      overloaded_workers: 0,
      active_checkers: 0,
      workers_in_rework_loop: 0,
      workers_in_staffing_containment: 0,
    },
    completion_summary: null,
    event_stream_preview: [
      {
        event_id: 'evt_000041',
        occurred_at: '2026-04-01T23:09:00+08:00',
        category: 'ticket',
        severity: 'info',
        message: 'TICKET_STARTED by emp_frontend_2',
        related_ref: 'tkt_visual_002',
      },
      {
        event_id: 'evt_000042',
        occurred_at: '2026-04-01T23:10:00+08:00',
        category: 'incident',
        severity: 'warning',
        message: 'INCIDENT_OPENED timeout escalation on node_homepage_visual',
        related_ref: 'inc_093',
      },
    ],
    ...overrides,
  }
}

function inboxData(items: JsonRecord[] = []) {
  return { items }
}

function jsonResponse(data: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function errorResponse(status: number, detail: string) {
  return Promise.resolve(
    new Response(JSON.stringify({ detail }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function artifactContentUrl(artifactRef: string, disposition: 'inline' | 'attachment' = 'inline') {
  const encodedRef = encodeURIComponent(artifactRef)
  return `/api/v1/artifacts/content?artifact_ref=${encodedRef}&disposition=${disposition}`
}

function artifactPreviewUrl(artifactRef: string) {
  return `/api/v1/artifacts/preview?artifact_ref=${encodeURIComponent(artifactRef)}`
}

function artifactMetadata(artifactRef: string, overrides: Partial<JsonRecord> = {}) {
  return {
    artifact_ref: artifactRef,
    workflow_id: 'wf_001',
    ticket_id: 'tkt_visual_002',
    node_id: 'node_homepage_visual',
    path: 'reports/review/homepage-option-a.json',
    kind: 'JSON',
    media_type: 'application/json',
    preview_kind: 'JSON',
    display_hint: 'INLINE',
    status: 'ACTIVE',
    materialization_status: 'MATERIALIZED',
    lifecycle_status: 'ACTIVE',
    retention_class: 'REVIEW_EVIDENCE',
    retention_class_source: 'PATH_DEFAULT',
    retention_ttl_sec: 604800,
    retention_policy_source: 'CLASS_DEFAULT',
    expires_at: null,
    deleted_at: null,
    deleted_by: null,
    delete_reason: null,
    storage_backend: 'LOCAL_DISK',
    storage_object_key: null,
    storage_delete_status: 'NOT_SCHEDULED',
    storage_delete_error: null,
    storage_deleted_at: null,
    size_bytes: 128,
    content_hash: 'sha256:test',
    created_at: '2026-04-01T23:08:00+08:00',
    content_url: artifactContentUrl(artifactRef),
    download_url: artifactContentUrl(artifactRef, 'attachment'),
    preview_url: artifactPreviewUrl(artifactRef),
    ...overrides,
  }
}

function artifactPreview(artifactRef: string, overrides: Partial<JsonRecord> = {}) {
  return {
    artifact_ref: artifactRef,
    preview_kind: 'JSON',
    media_type: 'application/json',
    lifecycle_status: 'ACTIVE',
    content_url: artifactContentUrl(artifactRef),
    download_url: artifactContentUrl(artifactRef, 'attachment'),
    json_content: {
      summary: 'Approve option A to unblock the main build path.',
      artifact_ref: artifactRef,
    },
    text_content: null,
    ...overrides,
  }
}

function setMockWorkerEmploymentState(workforce: JsonRecord, employeeId: string, nextState: 'ACTIVE' | 'FROZEN') {
  const roleLanes = ((workforce.role_lanes as JsonRecord[]) ?? [])
  for (const lane of roleLanes) {
    const workers = ((lane.workers as JsonRecord[]) ?? [])
    for (const worker of workers) {
      if (worker.employee_id !== employeeId) {
        continue
      }
      worker.employment_state = nextState
      worker.activity_state = nextState === 'FROZEN' ? 'OFFLINE' : 'IDLE'
      worker.current_ticket_id = nextState === 'FROZEN' ? worker.current_ticket_id : null
      worker.current_node_id = nextState === 'FROZEN' ? worker.current_node_id : null
      const currentActions = ((worker.available_actions as JsonRecord[]) ?? [])
      const templateId = (currentActions.find((action) => action.action_type === 'REPLACE')?.template_id ??
        null) as string | null
      worker.available_actions =
        nextState === 'FROZEN'
          ? [
              workforceAction('FREEZE', false, 'Only active workers can be frozen.'),
              workforceAction('RESTORE', true),
              workforceAction('REPLACE', false, 'Only active workers can be replaced.', templateId),
            ]
          : [
              workforceAction('FREEZE', true),
              workforceAction('RESTORE', false, 'Only frozen workers can be restored.'),
              workforceAction('REPLACE', true, null, templateId),
            ]
    }
  }
}

function pushMockStaffingInboxItem(
  state: {
    dashboard: JsonRecord
    inbox: JsonRecord
  },
  item: JsonRecord,
) {
  const currentItems = (((state.inbox.items as JsonRecord[]) ?? []).slice())
  currentItems.unshift(item)
  state.inbox = inboxData(currentItems)
  state.dashboard = {
    ...state.dashboard,
    inbox_counts: {
      ...((state.dashboard.inbox_counts as JsonRecord) ?? {}),
      approvals_pending: currentItems.length,
    },
  }
}

function installBoardroomMock(options?: {
  dashboard?: JsonRecord
  inbox?: JsonRecord
  workforce?: JsonRecord
  reviewRoom?: JsonRecord
  meetingRoom?: JsonRecord
  inspector?: JsonRecord
  dependencyInspector?: JsonRecord
  incidentDetail?: JsonRecord
  runtimeProvider?: JsonRecord
  boardActionDashboard?: JsonRecord
  artifactMetadataByRef?: Record<string, JsonRecord>
  artifactPreviewByRef?: Record<string, JsonRecord>
  artifactErrorsByRef?: Record<string, { status: number; detail: string }>
}) {
  const defaultArtifactMetadataByRef: Record<string, JsonRecord> = {
    'art://runtime/tkt_visual_002/option-a.png': artifactMetadata('art://runtime/tkt_visual_002/option-a.png', {
      path: 'reports/review/option-a.png',
      kind: 'IMAGE',
      media_type: 'image/png',
      preview_kind: 'INLINE_MEDIA',
      size_bytes: 2048,
    }),
    'art://runtime/tkt_closeout_001/delivery-closeout-package.json': artifactMetadata(
      'art://runtime/tkt_closeout_001/delivery-closeout-package.json',
      {
        path: 'reports/closeout/delivery-closeout-package.json',
      },
    ),
  }
  const defaultArtifactPreviewByRef: Record<string, JsonRecord> = {
    'art://runtime/tkt_visual_002/option-a.png': artifactPreview('art://runtime/tkt_visual_002/option-a.png', {
      preview_kind: 'INLINE_MEDIA',
      media_type: 'image/png',
      json_content: null,
    }),
    'art://runtime/tkt_closeout_001/delivery-closeout-package.json': artifactPreview(
      'art://runtime/tkt_closeout_001/delivery-closeout-package.json',
    ),
  }

  const state = {
    dashboard: options?.dashboard ?? dashboardData(),
    inbox: options?.inbox ?? inboxData(),
    workforce: options?.workforce ?? workforceData(),
    reviewRoom: options?.reviewRoom ?? reviewRoomData(),
    meetingRoom: options?.meetingRoom ?? meetingRoomData(),
    inspector: options?.inspector ?? inspectorData(),
    dependencyInspector: options?.dependencyInspector ?? dependencyInspectorData(),
    incidentDetail: options?.incidentDetail ?? incidentDetailData(),
    runtimeProvider: options?.runtimeProvider ?? runtimeProviderData(),
    artifactMetadataByRef: options?.artifactMetadataByRef ?? defaultArtifactMetadataByRef,
    artifactPreviewByRef: options?.artifactPreviewByRef ?? defaultArtifactPreviewByRef,
    artifactErrorsByRef: options?.artifactErrorsByRef ?? {},
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = (init?.method ?? 'GET').toUpperCase()
    const parsedUrl = new URL(url, 'http://test.local')
    const artifactRef = parsedUrl.searchParams.get('artifact_ref')

    if (method === 'GET' && url.endsWith('/api/v1/projections/dashboard')) {
      return jsonResponse(envelope(state.dashboard))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/inbox')) {
      return jsonResponse(envelope(state.inbox))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/runtime-provider')) {
      return jsonResponse(envelope(state.runtimeProvider))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/workforce')) {
      return jsonResponse(envelope(state.workforce))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/review-room/brp_001')) {
      return jsonResponse(envelope(state.reviewRoom))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/meetings/mtg_001')) {
      return jsonResponse(envelope(state.meetingRoom))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/workflows/wf_001/dependency-inspector')) {
      return jsonResponse(envelope(state.dependencyInspector))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/incidents/inc_093')) {
      return jsonResponse(envelope(state.incidentDetail))
    }
    if (
      method === 'GET' &&
      url.endsWith('/api/v1/projections/review-room/brp_001/developer-inspector')
    ) {
      return jsonResponse(envelope(state.inspector))
    }
    if (method === 'GET' && parsedUrl.pathname === '/api/v1/artifacts/by-ref' && artifactRef) {
      const error = state.artifactErrorsByRef[artifactRef]
      if (error) {
        return errorResponse(error.status, error.detail)
      }
      const metadata = state.artifactMetadataByRef[artifactRef]
      if (metadata) {
        return jsonResponse({ data: metadata })
      }
    }
    if (method === 'GET' && parsedUrl.pathname === '/api/v1/artifacts/preview' && artifactRef) {
      const error = state.artifactErrorsByRef[artifactRef]
      if (error) {
        return errorResponse(error.status, error.detail)
      }
      const preview = state.artifactPreviewByRef[artifactRef]
      if (preview) {
        return jsonResponse({ data: preview })
      }
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/project-init')) {
      state.dashboard = dashboardData({
        runtime_status: state.dashboard.runtime_status,
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'PENDING'),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'PENDING'),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_scope_decision'],
          blocked_node_ids: ['node_scope_decision'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      })
      state.inbox = inboxData([
        {
          inbox_item_id: 'inbox_apr_scope_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:12:00+08:00',
          title: 'Review scope decision consensus',
          summary: 'A consensus document is ready for board review.',
          source_ref: 'apr_scope_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['meeting', 'board_gate', 'scope'],
        },
      ])
      return jsonResponse({
        command_id: 'cmd_project_init',
        idempotency_key: 'project-init:mock',
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:11:00+08:00',
        reason: null,
        causation_hint: 'workflow:wf_001',
      })
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/employee-freeze')) {
      const payload = JSON.parse(String(init?.body ?? '{}')) as JsonRecord
      setMockWorkerEmploymentState(state.workforce, String(payload.employee_id), 'FROZEN')
      return jsonResponse({
        command_id: 'cmd_employee_freeze',
        idempotency_key: String(payload.idempotency_key ?? 'employee-freeze:mock'),
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:13:00+08:00',
        reason: null,
        causation_hint: `employee:${String(payload.employee_id)}`,
      })
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/employee-restore')) {
      const payload = JSON.parse(String(init?.body ?? '{}')) as JsonRecord
      setMockWorkerEmploymentState(state.workforce, String(payload.employee_id), 'ACTIVE')
      return jsonResponse({
        command_id: 'cmd_employee_restore',
        idempotency_key: String(payload.idempotency_key ?? 'employee-restore:mock'),
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:14:00+08:00',
        reason: null,
        causation_hint: `employee:${String(payload.employee_id)}`,
      })
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/employee-hire-request')) {
      const payload = JSON.parse(String(init?.body ?? '{}')) as JsonRecord
      pushMockStaffingInboxItem(state, {
        inbox_item_id: 'inbox_hire_001',
        workflow_id: String(payload.workflow_id ?? 'wf_001'),
        item_type: 'CORE_HIRE_APPROVAL',
        priority: 'high',
        status: 'OPEN',
        created_at: '2026-04-01T23:15:00+08:00',
        title: `Approve hire: ${String(payload.employee_id)}`,
        summary: String(payload.request_summary ?? 'Approve staffing hire.'),
        source_ref: 'apr_hire_001',
        route_target: {
          view: 'review_room',
          review_pack_id: 'brp_001',
        },
        badges: ['staffing', 'core_hire'],
      })
      return jsonResponse({
        command_id: 'cmd_employee_hire',
        idempotency_key: String(payload.idempotency_key ?? 'employee-hire-request:mock'),
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:15:00+08:00',
        reason: null,
        causation_hint: `approval:${String(payload.employee_id)}`,
      })
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/employee-replace-request')) {
      const payload = JSON.parse(String(init?.body ?? '{}')) as JsonRecord
      pushMockStaffingInboxItem(state, {
        inbox_item_id: 'inbox_replace_001',
        workflow_id: String(payload.workflow_id ?? 'wf_001'),
        item_type: 'CORE_HIRE_APPROVAL',
        priority: 'high',
        status: 'OPEN',
        created_at: '2026-04-01T23:16:00+08:00',
        title: `Approve replacement: ${String(payload.replaced_employee_id)}`,
        summary: String(payload.request_summary ?? 'Approve staffing replacement.'),
        source_ref: 'apr_replace_001',
        route_target: {
          view: 'review_room',
          review_pack_id: 'brp_001',
        },
        badges: ['staffing', 'core_hire', 'replacement'],
      })
      return jsonResponse({
        command_id: 'cmd_employee_replace',
        idempotency_key: String(payload.idempotency_key ?? 'employee-replace-request:mock'),
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:16:00+08:00',
        reason: null,
        causation_hint: `approval:${String(payload.replaced_employee_id)}`,
      })
    }
    if (
      method === 'POST' &&
      url.endsWith('/api/v1/commands/runtime-provider-upsert')
    ) {
      const payload = JSON.parse(String(init?.body ?? '{}')) as JsonRecord
      const defaultProviderId =
        typeof payload.default_provider_id === 'string' ? payload.default_provider_id : null
      const providers = Array.isArray(payload.providers) ? payload.providers : []
      const roleBindings = Array.isArray(payload.role_bindings) ? payload.role_bindings : []
      const openai = providers.find(
        (provider): provider is JsonRecord =>
          typeof provider === 'object' && provider !== null && provider.provider_id === 'prov_openai_compat',
      )
      const claude = providers.find(
        (provider): provider is JsonRecord =>
          typeof provider === 'object' && provider !== null && provider.provider_id === 'prov_claude_code',
      )
      const activeProvider = defaultProviderId === 'prov_claude_code' ? claude : openai
      const effectiveMode =
        defaultProviderId === 'prov_openai_compat'
          ? 'OPENAI_COMPAT_LIVE'
          : defaultProviderId === 'prov_claude_code'
            ? 'CLAUDE_CODE_CLI_LIVE'
            : 'LOCAL_DETERMINISTIC'
      state.runtimeProvider = runtimeProviderData({
        mode:
          defaultProviderId === 'prov_openai_compat'
            ? 'OPENAI_COMPAT'
            : defaultProviderId === 'prov_claude_code'
              ? 'CLAUDE_CODE_CLI'
              : 'DETERMINISTIC',
        effective_mode: effectiveMode,
        provider_health_summary: defaultProviderId ? 'HEALTHY' : 'LOCAL_ONLY',
        provider_id: defaultProviderId,
        default_provider_id: defaultProviderId,
        base_url: typeof activeProvider?.base_url === 'string' ? activeProvider.base_url : null,
        model: typeof activeProvider?.model === 'string' ? activeProvider.model : null,
        timeout_sec: typeof activeProvider?.timeout_sec === 'number' ? activeProvider.timeout_sec : 30,
        reasoning_effort:
          typeof activeProvider?.reasoning_effort === 'string' ? activeProvider.reasoning_effort : null,
        api_key_configured: Boolean(openai?.api_key),
        api_key_masked: typeof openai?.api_key === 'string' ? 'sk-***cret' : null,
        providers: providers.map((provider) => ({
          ...provider,
          api_key_configured: Boolean((provider as JsonRecord).api_key),
          api_key_masked: typeof (provider as JsonRecord).api_key === 'string' ? 'sk-***cret' : null,
          capability_tags: Array.isArray((provider as JsonRecord).capability_tags)
            ? (provider as JsonRecord).capability_tags
            : [],
          fallback_provider_ids: Array.isArray((provider as JsonRecord).fallback_provider_ids)
            ? (provider as JsonRecord).fallback_provider_ids
            : [],
          health_status:
            typeof (provider as JsonRecord).health_status === 'string'
              ? (provider as JsonRecord).health_status
              : defaultProviderId && (provider as JsonRecord).provider_id === defaultProviderId
                ? 'HEALTHY'
                : 'DISABLED',
          health_reason:
            typeof (provider as JsonRecord).health_reason === 'string'
              ? (provider as JsonRecord).health_reason
              : defaultProviderId && (provider as JsonRecord).provider_id === defaultProviderId
                ? 'Provider is ready for live execution.'
                : 'Provider is disabled.',
          is_default: (provider as JsonRecord).provider_id === defaultProviderId,
          configured_worker_count:
            typeof (provider as JsonRecord).configured_worker_count === 'number'
              ? (provider as JsonRecord).configured_worker_count
              : (provider as JsonRecord).provider_id === 'prov_openai_compat'
                ? 1
                : 0,
        })),
        role_bindings: roleBindings,
        effective_reason:
          defaultProviderId === 'prov_openai_compat'
            ? 'Runtime is using the saved OpenAI-compatible provider config.'
            : defaultProviderId === 'prov_claude_code'
              ? 'Runtime is using the saved Claude Code CLI provider config.'
            : 'Runtime is using the local deterministic path.',
      })
      state.dashboard = {
        ...state.dashboard,
        runtime_status: {
          effective_mode: state.runtimeProvider.effective_mode,
          provider_label:
            state.runtimeProvider.effective_mode === 'OPENAI_COMPAT_LIVE'
              ? 'OpenAI Compat'
              : state.runtimeProvider.effective_mode === 'CLAUDE_CODE_CLI_LIVE'
                ? 'Claude Code CLI'
              : 'Local Deterministic',
          model: state.runtimeProvider.model,
          configured_worker_count: Number(state.runtimeProvider.configured_worker_count),
          provider_health_summary: String(
            (state.dashboard as { ops_strip?: { provider_health_summary?: string } }).ops_strip
              ?.provider_health_summary ?? 'LOCAL_ONLY',
          ),
          reason: String(state.runtimeProvider.effective_reason),
        },
      }
      return jsonResponse({
        command_id: 'cmd_runtime_provider_upsert',
        idempotency_key: 'runtime-provider-upsert:mock',
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:10:30+08:00',
        reason: null,
        causation_hint: 'runtime-provider:prov_openai_compat',
      })
    }
    if (
      method === 'POST' &&
      ['/api/v1/commands/board-approve', '/api/v1/commands/board-reject', '/api/v1/commands/modify-constraints'].some(
        (path) => url.endsWith(path),
      )
    ) {
      state.dashboard = options?.boardActionDashboard ?? dashboardData({
        ops_strip: {
          ...dashboardData().ops_strip,
          blocked_nodes: 0,
          active_tickets: 0,
        },
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'COMPLETED', { completed: 1 }),
          ],
          critical_path_node_ids: [],
          blocked_node_ids: [],
        },
        inbox_counts: {
          approvals_pending: 0,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
        runtime_status: state.dashboard.runtime_status,
        completion_summary: {
          workflow_id: 'wf_001',
          final_review_pack_id: 'brp_001',
          approved_at: '2026-04-01T23:12:00+08:00',
          final_review_approved_at: '2026-04-01T23:12:00+08:00',
          closeout_completed_at: '2026-04-01T23:18:00+08:00',
          closeout_ticket_id: 'tkt_closeout_001',
          title: 'Review homepage visual milestone',
          summary: 'Approve option A to unblock the main build path.',
          selected_option_id: 'option_a',
          board_comment: 'Proceed with option A.',
          artifact_refs: ['art://runtime/tkt_visual_002/option-a.png'],
          closeout_artifact_refs: ['art://runtime/tkt_closeout_001/delivery-closeout-package.json'],
          documentation_sync_summary: '2 documentation updates recorded; 0 follow-up items.',
          documentation_update_count: 2,
          documentation_follow_up_count: 0,
        },
      })
      state.inbox = inboxData()
      return jsonResponse({
        command_id: 'cmd_board_action',
        idempotency_key: 'board-action:mock',
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:12:00+08:00',
        reason: null,
        causation_hint: 'approval:apr_001',
      })
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/incident-resolve')) {
      state.dashboard = dashboardData({
        ops_strip: {
          ...dashboardData().ops_strip,
          blocked_nodes: 0,
          active_tickets: 1,
          open_incidents: 0,
          open_circuit_breakers: 0,
        },
        inbox_counts: {
          approvals_pending: 0,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      })
      state.inbox = inboxData()
      state.incidentDetail = incidentDetailData({
        incident: {
          ...incidentDetailData().incident,
          status: 'RECOVERING',
          circuit_breaker_state: 'CLOSED',
          payload: {
            resolved_by: 'emp_ops_1',
            resolution_summary: 'Restore execution and retry the latest timeout attempt.',
            followup_action: 'RESTORE_AND_RETRY_LATEST_TIMEOUT',
            followup_ticket_id: 'tkt_visual_003',
          },
        },
        available_followup_actions: ['RESTORE_ONLY', 'RESTORE_AND_RETRY_LATEST_TIMEOUT'],
        recommended_followup_action: 'RESTORE_AND_RETRY_LATEST_TIMEOUT',
      })
      return jsonResponse({
        command_id: 'cmd_incident_resolve',
        idempotency_key: 'incident-resolve:mock',
        status: 'ACCEPTED',
        received_at: '2026-04-01T23:13:00+08:00',
        reason: null,
        causation_hint: 'incident:inc_093',
      })
    }

    throw new Error(`Unhandled mock request: ${method} ${url}`)
  })

  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('EventSource', FakeEventSource)

  return { fetchMock }
}

describe('Boardroom UI', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    FakeEventSource.instances = []
  })

  it('shows the project init entry when no active workflow exists', async () => {
    installBoardroomMock({
      dashboard: dashboardData({
        active_workflow: null,
        ops_strip: {
          ...dashboardData().ops_strip,
          budget_total: 0,
          budget_used: 0,
          budget_remaining: 0,
          active_tickets: 0,
          blocked_nodes: 0,
        },
        pipeline_summary: {
          phases: [
            phase('Intake', 'PENDING'),
            phase('Plan', 'PENDING'),
            phase('Build', 'PENDING'),
            phase('Check', 'PENDING'),
            phase('Review', 'PENDING'),
          ],
          critical_path_node_ids: [],
          blocked_node_ids: [],
        },
      }),
    })

    render(<App />)

    expect(await screen.findByRole('heading', { name: /launch workflow to first review/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /launch to first review/i })).toBeInTheDocument()
  })

  it('opens provider settings without an active workflow and saves runtime provider config', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        active_workflow: null,
        ops_strip: {
          ...dashboardData().ops_strip,
          budget_total: 0,
          budget_used: 0,
          budget_remaining: 0,
          active_tickets: 0,
          blocked_nodes: 0,
        },
      }),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /runtime settings/i }))
    expect(await screen.findByRole('heading', { name: /runtime provider/i })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText(/provider mode/i), 'OPENAI_COMPAT')
    await user.clear(screen.getByLabelText(/openai base url/i))
    await user.type(screen.getByLabelText(/openai base url/i), 'https://api.example.test/v1')
    await user.clear(screen.getByLabelText(/openai api key/i))
    await user.type(screen.getByLabelText(/openai api key/i), 'sk-test-secret')
    await user.clear(screen.getByLabelText(/openai model/i))
    await user.type(screen.getByLabelText(/openai model/i), 'gpt-5.3-codex')
    await user.click(screen.getByLabelText(/openai compat capability planning/i))
    await user.selectOptions(screen.getByLabelText(/openai compat fallback provider/i), 'prov_claude_code')
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/runtime-provider-upsert',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"default_provider_id":"prov_openai_compat"'),
        }),
      ),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/commands/runtime-provider-upsert',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"capability_tags":["structured_output","implementation"]'),
      }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/commands/runtime-provider-upsert',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"fallback_provider_ids":["prov_claude_code"]'),
      }),
    )
    expect(await screen.findByText(/openai compat/i)).toBeInTheDocument()
    expect(screen.getByText(/gpt-5.3-codex/i)).toBeInTheDocument()
  })

  it('shows future governance role slots as read-only in runtime provider settings', async () => {
    installBoardroomMock({
      runtimeProvider: runtimeProviderData(),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /runtime settings/i }))

    const futureSlots = await screen.findAllByDisplayValue(/not_enabled: 治理模板角色尚未纳入当前主线。/i)

    expect(futureSlots).toHaveLength(2)
    for (const slot of futureSlots) {
      expect(slot).toBeDisabled()
    }
  })

  it('launches project init and refreshes into the first review state', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        active_workflow: null,
        ops_strip: {
          ...dashboardData().ops_strip,
          budget_total: 0,
          budget_used: 0,
          budget_remaining: 0,
          active_tickets: 0,
          blocked_nodes: 0,
        },
        pipeline_summary: {
          phases: [
            phase('Intake', 'PENDING'),
            phase('Plan', 'PENDING'),
            phase('Build', 'PENDING'),
            phase('Check', 'PENDING'),
            phase('Review', 'PENDING'),
          ],
          critical_path_node_ids: [],
          blocked_node_ids: [],
        },
      }),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /launch to first review/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/project-init',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    expect((await screen.findAllByText(/board gate armed/i)).length).toBeGreaterThan(0)
    expect(screen.getByText(/review scope decision consensus/i)).toBeInTheDocument()
  })

  it('runs the mainline smoke from project init to review approval and completion evidence', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        active_workflow: null,
        ops_strip: {
          ...dashboardData().ops_strip,
          budget_total: 0,
          budget_used: 0,
          budget_remaining: 0,
          active_tickets: 0,
          blocked_nodes: 0,
        },
        pipeline_summary: {
          phases: [
            phase('Intake', 'PENDING'),
            phase('Plan', 'PENDING'),
            phase('Build', 'PENDING'),
            phase('Check', 'PENDING'),
            phase('Review', 'PENDING'),
          ],
          critical_path_node_ids: [],
          blocked_node_ids: [],
        },
      }),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /launch to first review/i }))
    await user.click(await screen.findByRole('button', { name: /review scope decision consensus/i }))

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /approve and continue/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/project-init',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/board-approve',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    expect(await screen.findByRole('heading', { name: /delivery completed/i })).toBeInTheDocument()
    expect(screen.getByText(/closeout refs/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /open final review evidence/i }))

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
  })

  it('lights board gate and lists the inbox approval when board review is pending', async () => {
    installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_homepage_visual'],
          blocked_node_ids: ['node_homepage_visual'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
        ops_strip: {
          ...dashboardData().ops_strip,
          blocked_nodes: 1,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })

    render(<App />)

    expect((await screen.findAllByText(/board gate armed/i)).length).toBeGreaterThan(0)
    expect(screen.getByText('Review homepage visual milestone')).toBeInTheDocument()
  })

  it('renders workforce lanes and recent event ticker on the homepage', async () => {
    installBoardroomMock()

    render(<App />)

    expect(await screen.findByText(/live workforce/i)).toBeInTheDocument()
    expect(screen.getByText('emp_frontend_2')).toBeInTheDocument()
    expect(screen.getAllByText('node_homepage_visual').length).toBeGreaterThan(0)
    expect(screen.getByText(/recent event pulse/i)).toBeInTheDocument()
    expect(screen.getByText(/incident_opened timeout escalation/i)).toBeInTheDocument()
  })

  it('shows rework loops in the workforce panel when build rework is open', async () => {
    installBoardroomMock({
      workforce: {
        ...workforceData(),
        summary: {
          ...workforceData().summary,
          workers_in_rework_loop: 7,
        },
      },
    })

    render(<App />)

    expect(await screen.findByText(/live workforce/i)).toBeInTheDocument()
    expect(screen.getByText('Rework loops')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('shows staffing templates, employment state, and worker actions in the workforce panel', async () => {
    installBoardroomMock()

    render(<App />)

    expect(await screen.findByText(/request staffing/i)).toBeInTheDocument()
    expect(screen.getByDisplayValue('emp_frontend_backup')).toBeInTheDocument()
    expect(screen.getAllByText(/employment active/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /freeze emp_frontend_2/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /request replacement for emp_frontend_2/i })).toBeInTheDocument()
  })

  it('freezes and restores a worker from the workforce panel with snapshot refresh', async () => {
    const { fetchMock } = installBoardroomMock()
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /freeze emp_frontend_2/i }))

    expect(await screen.findByText(/employment frozen/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /restore emp_frontend_2/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /restore emp_frontend_2/i }))

    expect((await screen.findAllByText(/employment active/i)).length).toBeGreaterThan(0)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/v1/commands/employee-freeze').length).toBe(1)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/v1/commands/employee-restore').length).toBe(1)
  })

  it('submits hire and replacement requests from the workforce panel and refreshes inbox', async () => {
    installBoardroomMock()
    const user = userEvent.setup()

    render(<App />)

    await user.clear(await screen.findByLabelText(/frontend backup maker employee id/i))
    await user.type(screen.getByLabelText(/frontend backup maker employee id/i), 'emp_frontend_new')
    await user.click(screen.getByRole('button', { name: /request hire for frontend backup maker/i }))

    expect(await screen.findByText('Approve hire: emp_frontend_new')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /request replacement for emp_frontend_2/i }))
    await user.type(await screen.findByLabelText(/replacement employee id for emp_frontend_2/i), 'emp_frontend_swap')
    await user.click(screen.getByRole('button', { name: /submit replacement for emp_frontend_2/i }))

    expect(await screen.findByText('Approve replacement: emp_frontend_2')).toBeInTheDocument()
  })

  it('shows the dependency inspector entry only when an active workflow exists', async () => {
    installBoardroomMock()

    render(<App />)

    expect(await screen.findByRole('button', { name: /inspect dependency chain/i })).toBeInTheDocument()
  })

  it('opens the dependency inspector and routes from the blocked node back to review room', async () => {
    installBoardroomMock()
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /inspect dependency chain/i }))

    expect(await screen.findByRole('heading', { name: /dependency chain/i })).toBeInTheDocument()
    expect(screen.getAllByText(/board review open/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText('tkt_homepage_review').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /open review room/i }))

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
  })

  it('refreshes the dependency inspector after an event-stream invalidation', async () => {
    const { fetchMock } = installBoardroomMock()
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /inspect dependency chain/i }))
    expect((await screen.findAllByText(/board review open/i)).length).toBeGreaterThan(0)

    const latestCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === '/api/v1/projections/workflows/wf_001/dependency-inspector' &&
        (!init || (init as RequestInit).method == null),
    )
    expect(latestCall).toBeTruthy()

    const source = FakeEventSource.instances.at(-1)
    expect(source).toBeTruthy()

    await act(async () => {
      ;(source as FakeEventSource).emit('boardroom-event')
    })

    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([url]) => url === '/api/v1/projections/workflows/wf_001/dependency-inspector').length).toBeGreaterThan(1),
    )
  })

  it('opens the review room and loads the review pack when an inbox review item is clicked', async () => {
    installBoardroomMock({
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /review homepage visual milestone/i }))

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
    expect(screen.getByText(/approve option a to unblock the main build path/i)).toBeInTheDocument()
  })

  it('opens the review room from keyboard navigation and lands focus on the close action', async () => {
    installBoardroomMock({
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    const reviewButton = await screen.findByRole('button', { name: /review homepage visual milestone/i })
    for (let index = 0; index < 8; index += 1) {
      if (reviewButton === document.activeElement) {
        break
      }
      await user.tab()
    }
    expect(reviewButton).toHaveFocus()
    await user.keyboard('{Enter}')

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /close review homepage visual milestone/i })).toHaveFocus()
  })

  it('keeps direct review routes keyboard-ready by focusing the drawer close action on load', async () => {
    window.history.replaceState({}, '', '/review/brp_001')
    installBoardroomMock()

    render(<App />)

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /close review homepage visual milestone/i })).toHaveFocus()
  })

  it('opens the meeting room route from inbox and can jump to the linked review room', async () => {
    installBoardroomMock({
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_mtg_001',
          workflow_id: 'wf_001',
          item_type: 'MEETING_ROOM',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-05T10:00:00+08:00',
          title: 'Technical decision meeting: Decide the homepage runtime contract',
          summary: 'Open the meeting room to inspect the current technical decision.',
          source_ref: 'mtg_001',
          route_target: {
            view: 'meeting_room',
            meeting_id: 'mtg_001',
          },
          badges: ['meeting', 'technical_decision'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /technical decision meeting/i }))

    expect(window.location.pathname).toBe('/meeting/mtg_001')
    expect(await screen.findByRole('heading', { name: /decide the homepage runtime contract/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /open linked review room/i }))

    expect(window.location.pathname).toBe('/review/brp_001')
    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
  })

  it('shows a clear error when the meeting detail request fails', async () => {
    const { fetchMock } = installBoardroomMock({
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_mtg_001',
          workflow_id: 'wf_001',
          item_type: 'MEETING_ROOM',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-05T10:00:00+08:00',
          title: 'Technical decision meeting: Decide the homepage runtime contract',
          summary: 'Open the meeting room to inspect the current technical decision.',
          source_ref: 'mtg_001',
          route_target: {
            view: 'meeting_room',
            meeting_id: 'mtg_001',
          },
          badges: ['meeting', 'technical_decision'],
        },
      ]),
    })
    const originalImplementation = fetchMock.getMockImplementation()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = (init?.method ?? 'GET').toUpperCase()
      if (method === 'GET' && url.endsWith('/api/v1/projections/meetings/mtg_001')) {
        return new Response('Meeting detail unavailable.', {
          status: 503,
          headers: { 'Content-Type': 'text/plain' },
        })
      }
      return originalImplementation!(input, init)
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /technical decision meeting/i }))

    expect(window.location.pathname).toBe('/meeting/mtg_001')
    expect(await screen.findByText(/meeting detail unavailable\./i)).toBeInTheDocument()
  })

  it('runs the incident inbox to drawer to resolve to snapshot refresh smoke path', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        ops_strip: {
          ...dashboardData().ops_strip,
          open_incidents: 1,
          open_circuit_breakers: 1,
          blocked_nodes: 1,
        },
        inbox_counts: {
          approvals_pending: 0,
          incidents_pending: 1,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_inc_093',
          workflow_id: 'wf_001',
          item_type: 'INCIDENT_ESCALATION',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:10:00+08:00',
          title: 'Repeated runtime timeout on homepage visual node',
          summary: 'The same node exceeded the timeout threshold and opened a breaker.',
          source_ref: 'inc_093',
          route_target: {
            view: 'incident_detail',
            incident_id: 'inc_093',
          },
          badges: ['runtime_timeout', 'circuit_breaker'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    expect(within((await screen.findByText('Incidents')).closest('div') as HTMLElement).getByText('1')).toBeInTheDocument()
    expect(within((await screen.findByText('Blocked')).closest('div') as HTMLElement).getByText('1')).toBeInTheDocument()
    expect((await screen.findAllByText(/board gate clear/i)).length).toBeGreaterThan(0)

    await user.click(await screen.findByRole('button', { name: /repeated runtime timeout on homepage visual node/i }))

    expect(window.location.pathname).toBe('/incident/inc_093')
    expect(await screen.findByRole('heading', { name: /runtime timeout escalation/i })).toBeInTheDocument()
    expect(screen.getByText(/execution timed out repeatedly and the breaker is now open/i)).toBeInTheDocument()
    expect(screen.getByText(/timeout streak count/i)).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('RESTORE_AND_RETRY_LATEST_TIMEOUT')

    await user.type(
      await screen.findByLabelText(/resolution summary/i),
      'Restore execution and retry the latest timeout attempt.',
    )
    await user.click(await screen.findByRole('button', { name: /apply recovery action/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/incident-resolve',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    await waitFor(() => expect(window.location.pathname).toBe('/'))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) => url === '/api/v1/projections/dashboard').length,
      ).toBeGreaterThan(1),
    )

    expect(within(screen.getByText('Incidents').closest('div') as HTMLElement).getByText('0')).toBeInTheDocument()
    expect(within(screen.getByText('Blocked').closest('div') as HTMLElement).getByText('0')).toBeInTheDocument()
    expect((await screen.findAllByText(/board gate clear/i)).length).toBeGreaterThan(0)
    expect(screen.getByText(/no board escalations are waiting right now/i)).toBeInTheDocument()
  })

  it('submits approve and refreshes the board gate state', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_homepage_visual'],
          blocked_node_ids: ['node_homepage_visual'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /review homepage visual milestone/i }))
    await user.click(await screen.findByRole('button', { name: /approve and continue/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/board-approve',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    expect((await screen.findAllByText(/board gate clear/i)).length).toBeGreaterThan(0)
  })

  it('shows the completion card after final review approval and reopens the final evidence', async () => {
    installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_homepage_visual'],
          blocked_node_ids: ['node_homepage_visual'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /review homepage visual milestone/i }))
    await user.click(await screen.findByRole('button', { name: /approve and continue/i }))

    expect(await screen.findByRole('heading', { name: /delivery completed/i })).toBeInTheDocument()
    expect(screen.getAllByText(/approve option a to unblock the main build path/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/proceed with option a/i)).toBeInTheDocument()
    expect(screen.getAllByText(/apr 1, 11:12 pm/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/apr 1, 11:18 pm/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/closeout refs/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /open final review evidence/i }))

    expect(await screen.findByRole('heading', { name: /review homepage visual milestone/i })).toBeInTheDocument()
  })

  it('does not show the completion card when board approval returns but closeout is still running', async () => {
    installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_homepage_visual'],
          blocked_node_ids: ['node_homepage_visual'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
      boardActionDashboard: dashboardData({
        ops_strip: {
          ...dashboardData().ops_strip,
          blocked_nodes: 0,
          active_tickets: 1,
        },
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'EXECUTING', { executing: 1 }),
          ],
          critical_path_node_ids: ['node_closeout_001'],
          blocked_node_ids: [],
        },
        inbox_counts: {
          approvals_pending: 0,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
        runtime_status: dashboardData().runtime_status,
        completion_summary: null,
      }),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /review homepage visual milestone/i }))
    await user.click(await screen.findByRole('button', { name: /approve and continue/i }))

    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: /delivery completed/i })).not.toBeInTheDocument(),
    )
    expect(screen.getByText(/live tickets/i)).toBeInTheDocument()
  })

  it('opens the artifact preview drawer from review evidence source refs', async () => {
    installBoardroomMock({
      reviewRoom: {
        ...reviewRoomData(),
        review_pack: {
          ...reviewRoomData().review_pack,
          evidence_summary: [
            {
              evidence_id: 'evidence_visual_consistency',
              label: 'Visual consistency',
              summary: 'The latest draft keeps the approved river layout and board cue hierarchy.',
              source_ref: 'art://runtime/tkt_visual_002/review-pack.json',
            },
          ],
        },
      },
      artifactMetadataByRef: {
        'art://runtime/tkt_visual_002/review-pack.json': artifactMetadata(
          'art://runtime/tkt_visual_002/review-pack.json',
          {
            path: 'reports/review/review-pack.json',
          },
        ),
      },
      artifactPreviewByRef: {
        'art://runtime/tkt_visual_002/review-pack.json': artifactPreview(
          'art://runtime/tkt_visual_002/review-pack.json',
          {
            json_content: {
              decision: 'option_a',
              summary: 'Board-ready evidence package.',
            },
          },
        ),
      },
    })
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/review/brp_001')

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /open evidence visual consistency/i }))

    expect(await screen.findByRole('heading', { name: /artifact preview/i })).toBeInTheDocument()
    expect(await screen.findByText(/board-ready evidence package/i)).toBeInTheDocument()
  })

  it('opens the same artifact preview drawer from review option refs', async () => {
    installBoardroomMock()
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/review/brp_001')

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /open artifact option a/i }))

    expect(await screen.findByRole('heading', { name: /artifact preview/i })).toBeInTheDocument()
    expect(await screen.findByText(/reports\/review\/option-a\.png/i)).toBeInTheDocument()
  })

  it('opens final and closeout artifacts from the completion card', async () => {
    installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'COMPLETED', { completed: 1 }),
          ],
          critical_path_node_ids: [],
          blocked_node_ids: [],
        },
        completion_summary: {
          workflow_id: 'wf_001',
          final_review_pack_id: 'brp_001',
          approved_at: '2026-04-01T23:12:00+08:00',
          final_review_approved_at: '2026-04-01T23:12:00+08:00',
          closeout_completed_at: '2026-04-01T23:18:00+08:00',
          closeout_ticket_id: 'tkt_closeout_001',
          title: 'Review homepage visual milestone',
          summary: 'Approve option A to unblock the main build path.',
          selected_option_id: 'option_a',
          board_comment: 'Proceed with option A.',
          artifact_refs: ['art://runtime/tkt_visual_002/option-a.png'],
          closeout_artifact_refs: ['art://runtime/tkt_closeout_001/delivery-closeout-package.json'],
          documentation_sync_summary: '2 documentation updates recorded; 0 follow-up items.',
          documentation_update_count: 2,
          documentation_follow_up_count: 0,
        },
      }),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /open artifact option-a\.png/i }))
    expect(await screen.findByText(/reports\/review\/option-a\.png/i)).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /close artifact preview/i }))
    await user.click(await screen.findByRole('button', { name: /open artifact delivery-closeout-package\.json/i }))
    expect(await screen.findByText(/reports\/closeout\/delivery-closeout-package\.json/i)).toBeInTheDocument()
  })

  it('shows download-only and API error fallback states in the artifact preview drawer', async () => {
    installBoardroomMock({
      reviewRoom: {
        ...reviewRoomData(),
        review_pack: {
          ...reviewRoomData().review_pack,
          options: [
            {
              option_id: 'option_zip',
              label: 'Option ZIP',
              summary: 'Download the packaged evidence bundle.',
              artifact_refs: ['art://runtime/tkt_visual_002/evidence-bundle.zip'],
            },
            {
              option_id: 'option_missing',
              label: 'Option Missing',
              summary: 'This evidence ref is no longer available.',
              artifact_refs: ['art://runtime/tkt_visual_002/missing.json'],
            },
          ],
        },
      },
      artifactMetadataByRef: {
        'art://runtime/tkt_visual_002/evidence-bundle.zip': artifactMetadata(
          'art://runtime/tkt_visual_002/evidence-bundle.zip',
          {
            path: 'reports/review/evidence-bundle.zip',
            kind: 'BINARY',
            media_type: 'application/zip',
            preview_kind: 'DOWNLOAD_ONLY',
          },
        ),
      },
      artifactPreviewByRef: {
        'art://runtime/tkt_visual_002/evidence-bundle.zip': artifactPreview(
          'art://runtime/tkt_visual_002/evidence-bundle.zip',
          {
            preview_kind: 'DOWNLOAD_ONLY',
            media_type: 'application/zip',
            json_content: null,
          },
        ),
      },
      artifactErrorsByRef: {
        'art://runtime/tkt_visual_002/missing.json': {
          status: 410,
          detail: "Artifact 'art://runtime/tkt_visual_002/missing.json' is no longer available (DELETED).",
        },
      },
    })
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/review/brp_001')

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /open artifact option zip/i }))
    expect(await screen.findByText(/download this artifact from the local backend/i)).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /close artifact preview/i }))
    await user.click(await screen.findByRole('button', { name: /open artifact option missing/i }))
    expect(
      await screen.findByText(/artifact 'art:\/\/runtime\/tkt_visual_002\/missing\.json' is no longer available/i),
    ).toBeInTheDocument()
  })

  it('submits reject and refreshes the snapshot', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_homepage_visual'],
          blocked_node_ids: ['node_homepage_visual'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /review homepage visual milestone/i }))
    await user.type(await screen.findByLabelText(/reject note/i), 'Needs a stronger hierarchy cue.')
    await user.click(await screen.findByRole('button', { name: /reject and request rework/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/board-reject',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    expect((await screen.findAllByText(/board gate clear/i)).length).toBeGreaterThan(0)
  })

  it('submits modify-constraints and refreshes the snapshot', async () => {
    const { fetchMock } = installBoardroomMock({
      dashboard: dashboardData({
        pipeline_summary: {
          phases: [
            phase('Intake', 'COMPLETED', { completed: 1 }),
            phase('Plan', 'COMPLETED', { completed: 1 }),
            phase('Build', 'COMPLETED', { completed: 1 }),
            phase('Check', 'COMPLETED', { completed: 1 }),
            phase('Review', 'BLOCKED_FOR_BOARD', { blocked_for_board: 1 }),
          ],
          critical_path_node_ids: ['node_homepage_visual'],
          blocked_node_ids: ['node_homepage_visual'],
        },
        inbox_counts: {
          approvals_pending: 1,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      }),
      inbox: inboxData([
        {
          inbox_item_id: 'inbox_apr_001',
          workflow_id: 'wf_001',
          item_type: 'BOARD_APPROVAL',
          priority: 'high',
          status: 'OPEN',
          created_at: '2026-04-01T23:05:00+08:00',
          title: 'Review homepage visual milestone',
          summary: 'Visual milestone is blocked for board review.',
          source_ref: 'apr_001',
          route_target: {
            view: 'review_room',
            review_pack_id: 'brp_001',
          },
          badges: ['visual', 'board_gate'],
        },
      ]),
    })
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /review homepage visual milestone/i }))
    await user.type(await screen.findByLabelText(/add rules/i), 'Keep the board gate copy to one line.')
    await user.click(await screen.findByRole('button', { name: /modify constraints/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/modify-constraints',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })
})
