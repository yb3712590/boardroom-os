import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { IncidentDrawer } from '../../../components/overlays/IncidentDrawer'

function buildIncidentData() {
  return {
    incident: {
      incident_id: 'inc_093',
      workflow_id: 'wf_001',
      node_id: 'node_review',
      ticket_id: 'tkt_review_001',
      provider_id: 'prov_openai_compat',
      incident_type: 'REPEATED_FAILURE_ESCALATION',
      status: 'OPEN',
      severity: 'HIGH',
      fingerprint: 'fp_timeout_001',
      circuit_breaker_state: 'OPEN',
      opened_at: '2026-04-08T18:00:00+08:00',
      closed_at: null,
      payload: {
        timeout_sec: 90,
        failure_streak_count: 4,
        latest_failure_kind: 'RUNTIME_INPUT_ERROR',
        latest_failure_message:
          'Mandatory explicit source art://runtime/tkt_closeout/delivery-closeout-package.json cannot fit within the remaining token budget (328) even as a reference descriptor.',
      },
    },
    available_followup_actions: ['RESTORE_AND_RETRY_LATEST_TIMEOUT', 'ESCALATE_TO_BOARD'],
    recommended_followup_action: 'RESTORE_AND_RETRY_LATEST_TIMEOUT',
  } as const
}

describe('IncidentDrawer', () => {
  it('keeps drafts during same-incident refresh and resets drafts after close/reopen', async () => {
    const user = userEvent.setup()
    const props = {
      loading: false,
      error: null,
      submitting: false,
      onClose: vi.fn(),
      onResolve: vi.fn().mockResolvedValue(undefined),
    }
    const { rerender } = render(
      <IncidentDrawer
        {...props}
        isOpen={true}
        incidentData={buildIncidentData()}
      />,
    )

    await user.type(screen.getByLabelText('Resolution summary'), 'Draft incident summary.')
    await user.selectOptions(screen.getByRole('combobox'), 'ESCALATE_TO_BOARD')

    rerender(
      <IncidentDrawer
        {...props}
        isOpen={true}
        incidentData={buildIncidentData()}
      />,
    )

    expect(screen.getByLabelText('Resolution summary')).toHaveValue('Draft incident summary.')
    expect(screen.getByRole('combobox')).toHaveValue('ESCALATE_TO_BOARD')

    rerender(
      <IncidentDrawer
        {...props}
        isOpen={false}
        incidentData={buildIncidentData()}
      />,
    )
    rerender(
      <IncidentDrawer
        {...props}
        isOpen={true}
        incidentData={buildIncidentData()}
      />,
    )

    expect(screen.getByLabelText('Resolution summary')).toHaveValue('')
    expect(screen.getByRole('combobox')).toHaveValue('RESTORE_AND_RETRY_LATEST_TIMEOUT')
    expect(
      screen.getByText(/This is not a provider outage. The required input art:\/\/runtime\/tkt_closeout\/delivery-closeout-package\.json/i),
    ).toBeInTheDocument()
  })

  it('describes ticket graph unavailable incidents and defaults to rebuild recovery', () => {
    render(
      <IncidentDrawer
        isOpen={true}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onResolve={vi.fn().mockResolvedValue(undefined)}
        incidentData={{
          incident: {
            ...buildIncidentData().incident,
            incident_id: 'inc_graph_001',
            incident_type: 'TICKET_GRAPH_UNAVAILABLE',
            provider_id: null,
            payload: {
              source_component: 'ceo_shadow_snapshot',
              source_stage: 'ticket_graph_snapshot',
              error_class: 'RuntimeError',
              error_message: 'ticket graph unavailable from ceo snapshot',
            },
          },
          available_followup_actions: ['REBUILD_TICKET_GRAPH', 'RESTORE_ONLY'],
          recommended_followup_action: 'REBUILD_TICKET_GRAPH',
        }}
      />,
    )

    expect(screen.getByText(/ticket graph snapshot could not be rebuilt/i)).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('REBUILD_TICKET_GRAPH')
  })

  it('describes required hook gate incidents and defaults to replay recovery', () => {
    render(
      <IncidentDrawer
        isOpen={true}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onResolve={vi.fn().mockResolvedValue(undefined)}
        incidentData={{
          incident: {
            ...buildIncidentData().incident,
            incident_id: 'inc_hook_gate_001',
            incident_type: 'REQUIRED_HOOK_GATE_BLOCKED',
            provider_id: null,
            payload: {
              missing_hook_ids: ['git_closeout'],
              reason_code: 'REQUIRED_HOOK_PENDING:git_closeout',
              reason_detail: 'Required hook receipts are missing for git_closeout.',
            },
          },
          available_followup_actions: ['REPLAY_REQUIRED_HOOKS', 'RESTORE_ONLY'],
          recommended_followup_action: 'REPLAY_REQUIRED_HOOKS',
        }}
      />,
    )

    expect(
      screen.getByText(/required hook receipts are missing, so the node stays fail-closed until recovery replays the missing hooks from persisted terminal truth/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('REPLAY_REQUIRED_HOOKS')
  })
})
