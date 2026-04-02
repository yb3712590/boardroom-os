import { act, render, screen, waitFor } from '@testing-library/react'
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
            last_update_at: '2026-04-01T23:08:00+08:00',
          },
          {
            employee_id: 'emp_frontend_backup',
            role_type: 'frontend_engineer',
            employment_state: 'ACTIVE',
            activity_state: 'IDLE',
            current_ticket_id: null,
            current_node_id: null,
            provider_id: null,
            last_update_at: '2026-04-01T23:07:00+08:00',
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
            last_update_at: '2026-04-01T23:08:00+08:00',
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
      provider_health_summary: 'UNKNOWN',
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

function installBoardroomMock(options?: {
  dashboard?: JsonRecord
  inbox?: JsonRecord
  workforce?: JsonRecord
  reviewRoom?: JsonRecord
  inspector?: JsonRecord
  dependencyInspector?: JsonRecord
  incidentDetail?: JsonRecord
}) {
  const state = {
    dashboard: options?.dashboard ?? dashboardData(),
    inbox: options?.inbox ?? inboxData(),
    workforce: options?.workforce ?? workforceData(),
    reviewRoom: options?.reviewRoom ?? reviewRoomData(),
    inspector: options?.inspector ?? inspectorData(),
    dependencyInspector: options?.dependencyInspector ?? dependencyInspectorData(),
    incidentDetail: options?.incidentDetail ?? incidentDetailData(),
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = (init?.method ?? 'GET').toUpperCase()

    if (method === 'GET' && url.endsWith('/api/v1/projections/dashboard')) {
      return jsonResponse(envelope(state.dashboard))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/inbox')) {
      return jsonResponse(envelope(state.inbox))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/workforce')) {
      return jsonResponse(envelope(state.workforce))
    }
    if (method === 'GET' && url.endsWith('/api/v1/projections/review-room/brp_001')) {
      return jsonResponse(envelope(state.reviewRoom))
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
    if (method === 'POST' && url.endsWith('/api/v1/commands/project-init')) {
      state.dashboard = dashboardData({
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
    if (
      method === 'POST' &&
      ['/api/v1/commands/board-approve', '/api/v1/commands/board-reject', '/api/v1/commands/modify-constraints'].some(
        (path) => url.endsWith(path),
      )
    ) {
      state.dashboard = dashboardData({
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

  it('opens the incident drawer when an inbox incident item is clicked', async () => {
    installBoardroomMock({
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

    await user.click(await screen.findByRole('button', { name: /repeated runtime timeout on homepage visual node/i }))

    expect(await screen.findByRole('heading', { name: /runtime timeout escalation/i })).toBeInTheDocument()
    expect(screen.getByText(/timeout streak count/i)).toBeInTheDocument()
  })

  it('submits incident resolve and refreshes the snapshot', async () => {
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

    await user.click(await screen.findByRole('button', { name: /repeated runtime timeout on homepage visual node/i }))
    await user.type(await screen.findByLabelText(/resolution summary/i), 'Restore execution and retry the latest timeout attempt.')
    await user.click(await screen.findByRole('button', { name: /apply recovery action/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/commands/incident-resolve',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
    expect((await screen.findAllByText(/board gate clear/i)).length).toBeGreaterThan(0)
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
