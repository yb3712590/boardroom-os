import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { WorkflowRiver } from '../../../components/dashboard/WorkflowRiver'
import type { PhaseSummary } from '../../../types/domain'

const phases: PhaseSummary[] = [
  {
    phase_id: 'phase_intake',
    label: 'Intake',
    status: 'COMPLETED',
    node_counts: { pending: 0, executing: 0, under_review: 0, blocked_for_board: 0, fused: 0, completed: 1 },
  },
  {
    phase_id: 'phase_plan',
    label: 'Plan',
    status: 'COMPLETED',
    node_counts: { pending: 0, executing: 0, under_review: 0, blocked_for_board: 0, fused: 0, completed: 2 },
  },
  {
    phase_id: 'phase_build',
    label: 'Build',
    status: 'EXECUTING',
    node_counts: { pending: 1, executing: 2, under_review: 0, blocked_for_board: 0, fused: 0, completed: 0 },
  },
  {
    phase_id: 'phase_check',
    label: 'Check',
    status: 'PENDING',
    node_counts: { pending: 1, executing: 0, under_review: 0, blocked_for_board: 0, fused: 0, completed: 0 },
  },
  {
    phase_id: 'phase_review',
    label: 'Review',
    status: 'BLOCKED_FOR_BOARD',
    node_counts: { pending: 0, executing: 0, under_review: 0, blocked_for_board: 1, fused: 0, completed: 0 },
  },
]

describe('WorkflowRiver', () => {
  it('renders the current five-stage pipeline with armed board gate state', () => {
    render(<WorkflowRiver phases={phases} approvalsPending={2} />)

    expect(screen.getByRole('heading', { name: /board to review, in one governance surface/i })).toBeInTheDocument()
    expect(screen.getByText('Intake')).toBeInTheDocument()
    expect(screen.getByText('Plan')).toBeInTheDocument()
    expect(screen.getByText('Build')).toBeInTheDocument()
    expect(screen.getByText('Check')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Board Gate armed')).toBeInTheDocument()
    expect(screen.getByText('2 item waiting')).toBeInTheDocument()
    expect(screen.getByText('3 nodes')).toBeInTheDocument()
    expect(screen.getByText('Live')).toBeInTheDocument()
    expect(screen.getAllByText('Settled').length).toBeGreaterThan(0)
  })

  it('shows a clear board gate state when nothing is waiting for review', () => {
    render(<WorkflowRiver phases={phases} approvalsPending={0} />)

    expect(screen.getByText('Board Gate clear')).toBeInTheDocument()
    expect(screen.getByText('No board items waiting')).toBeInTheDocument()
  })
})
