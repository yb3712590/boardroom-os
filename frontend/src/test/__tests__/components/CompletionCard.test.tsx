import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CompletionCard } from '../../../components/dashboard/CompletionCard'
import type { DashboardData } from '../../../types/api'

describe('CompletionCard', () => {
  it('shows documentation sync summary and counts', async () => {
    const onOpenReview = vi.fn()
    const user = userEvent.setup()

    render(
      <CompletionCard
        summary={
          {
            workflow_id: 'wf_001',
            final_review_pack_id: 'brp_001',
            approved_at: '2026-04-06T10:00:00+08:00',
            final_review_approved_at: '2026-04-06T10:00:00+08:00',
            closeout_completed_at: '2026-04-06T10:30:00+08:00',
            closeout_ticket_id: 'tkt_closeout_001',
            title: 'Ship M7 closeout package',
            summary: 'Closeout package completed with documentation sync notes.',
            selected_option_id: 'option_a',
            board_comment: 'Proceed with option A.',
            artifact_refs: ['art://runtime/review/final.json'],
            closeout_artifact_refs: ['art://runtime/tkt_closeout_001/delivery-closeout-package.json'],
            documentation_sync_summary: '2 documentation updates recorded; 1 follow-up item.',
            documentation_update_count: 2,
            documentation_follow_up_count: 1,
          } as NonNullable<DashboardData['completion_summary']>
        }
        onOpenReview={onOpenReview}
      />,
    )

    expect(screen.getByText('Documentation sync')).toBeInTheDocument()
    expect(screen.getByText('2 documentation updates recorded; 1 follow-up item.')).toBeInTheDocument()
    expect(screen.getByText('Documentation updates')).toBeInTheDocument()
    expect(screen.getByText('Follow-up docs')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /open final review evidence/i }))

    expect(onOpenReview).toHaveBeenCalledWith('brp_001')
  })
})
