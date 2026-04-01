import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

type JsonRecord = Record<string, unknown>

class FakeEventSource {
  url: string

  constructor(url: string) {
    this.url = url
  }

  addEventListener() {}

  removeEventListener() {}

  close() {}
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
    event_stream_preview: [],
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
  reviewRoom?: JsonRecord
  inspector?: JsonRecord
}) {
  const state = {
    dashboard: options?.dashboard ?? dashboardData(),
    inbox: options?.inbox ?? inboxData(),
    reviewRoom: options?.reviewRoom ?? reviewRoomData(),
    inspector: options?.inspector ?? inspectorData(),
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
    if (method === 'GET' && url.endsWith('/api/v1/projections/review-room/brp_001')) {
      return jsonResponse(envelope(state.reviewRoom))
    }
    if (
      method === 'GET' &&
      url.endsWith('/api/v1/projections/review-room/brp_001/developer-inspector')
    ) {
      return jsonResponse(envelope(state.inspector))
    }
    if (method === 'POST' && url.endsWith('/api/v1/commands/project-init')) {
      state.dashboard = dashboardData({
        inbox_counts: {
          approvals_pending: 0,
          incidents_pending: 0,
          budget_alerts: 0,
          provider_alerts: 0,
        },
      })
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

    expect(await screen.findByRole('heading', { name: /start local workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /launch workflow/i })).toBeInTheDocument()
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
