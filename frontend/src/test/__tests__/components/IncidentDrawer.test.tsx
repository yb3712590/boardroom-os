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

    await user.type(screen.getByLabelText('恢复说明'), 'Draft incident summary.')
    await user.selectOptions(screen.getByRole('combobox'), 'ESCALATE_TO_BOARD')

    rerender(
      <IncidentDrawer
        {...props}
        isOpen={true}
        incidentData={buildIncidentData()}
      />,
    )

    expect(screen.getByLabelText('恢复说明')).toHaveValue('Draft incident summary.')
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

    expect(screen.getByLabelText('恢复说明')).toHaveValue('')
    expect(screen.getByRole('combobox')).toHaveValue('RESTORE_AND_RETRY_LATEST_TIMEOUT')
    expect(
      screen.getByText(/这次不是供应商故障，而是输入预算超限：必需输入 art:\/\/runtime\/tkt_closeout\/delivery-closeout-package\.json/i),
    ).toBeInTheDocument()
  })
})
