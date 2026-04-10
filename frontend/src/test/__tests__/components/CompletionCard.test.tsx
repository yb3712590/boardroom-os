import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CompletionCard } from '../../../components/dashboard/CompletionCard'
import type { DashboardData } from '../../../types/api'

describe('CompletionCard', () => {
  it('shows the traditional final review path and opens the final review evidence', async () => {
    const onOpenReview = vi.fn()
    const onOpenArtifact = vi.fn()
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
            source_delivery_summary: {
              ticket_id: 'tkt_build_001',
              summary: 'Structured source code delivery submitted.',
              source_file_refs: ['art://workspace/tkt_build_001/source.ts'],
              source_file_count: 1,
              verification_evidence_refs: ['art://workspace/tkt_build_001/test-report.json'],
              verification_evidence_count: 1,
              git_commit_sha: 'abc1234',
              git_branch_ref: 'codex/tkt_build_001',
              git_merge_status: 'PENDING_REVIEW_GATE',
            },
            workflow_chain_report_artifact_ref: null,
          } as NonNullable<DashboardData['completion_summary']>
        }
        onOpenReview={onOpenReview}
        onOpenArtifact={onOpenArtifact}
      />,
    )

    expect(screen.getByText('Delivery completed')).toBeInTheDocument()
    expect(screen.getByText('Documentation sync')).toBeInTheDocument()
    expect(screen.getByText('2 documentation updates recorded; 1 follow-up item.')).toBeInTheDocument()
    expect(screen.getByText('Source delivery evidence')).toBeInTheDocument()
    expect(screen.getByText('PENDING_REVIEW_GATE')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Open artifact source\.ts/i }))
    await user.click(screen.getByRole('button', { name: /Open artifact test-report\.json/i }))

    await user.click(screen.getByRole('button', { name: /Open final review evidence/i }))

    expect(onOpenReview).toHaveBeenCalledWith('brp_001')
    expect(onOpenArtifact).toHaveBeenNthCalledWith(1, 'art://workspace/tkt_build_001/source.ts')
    expect(onOpenArtifact).toHaveBeenNthCalledWith(2, 'art://workspace/tkt_build_001/test-report.json')
  })

  it('shows the autopilot closeout path without final review and opens the workflow chain report', async () => {
    const onOpenReview = vi.fn()
    const onOpenArtifact = vi.fn()
    const user = userEvent.setup()

    render(
      <CompletionCard
        summary={
          {
            workflow_id: 'wf_autopilot_001',
            final_review_pack_id: null,
            approved_at: null,
            final_review_approved_at: null,
            closeout_completed_at: '2026-04-06T10:30:00+08:00',
            closeout_ticket_id: 'tkt_closeout_001',
            title: 'Autopilot closeout package',
            summary: 'Structured delivery closeout package submitted.',
            selected_option_id: null,
            board_comment: null,
            artifact_refs: [],
            closeout_artifact_refs: ['art://runtime/tkt_closeout_001/delivery-closeout-package.json'],
            documentation_sync_summary: null,
            documentation_update_count: 0,
            documentation_follow_up_count: 0,
            source_delivery_summary: null,
            workflow_chain_report_artifact_ref: 'art://workflow-chain/wf_autopilot_001/workflow-chain-report.json',
          } as NonNullable<DashboardData['completion_summary']>
        }
        onOpenReview={onOpenReview}
        onOpenArtifact={onOpenArtifact}
      />,
    )

    expect(screen.getByText(/Workflow wf_autopilot_001 closed out on/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Open final review evidence/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Source delivery evidence')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Open workflow chain report/i }))

    expect(onOpenArtifact).toHaveBeenCalledWith(
      'art://workflow-chain/wf_autopilot_001/workflow-chain-report.json',
    )
    expect(onOpenReview).not.toHaveBeenCalled()
  })
})
