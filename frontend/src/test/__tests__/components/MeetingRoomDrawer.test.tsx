import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { MeetingRoomDrawer } from '../../../components/overlays/MeetingRoomDrawer'

describe('MeetingRoomDrawer', () => {
  it('renders meeting rounds and opens linked review evidence', async () => {
    const user = userEvent.setup()
    const onOpenReview = vi.fn()

    render(
      <MeetingRoomDrawer
        isOpen
        loading={false}
        meetingData={{
          meeting_id: 'mtg_001',
          workflow_id: 'wf_001',
          meeting_type: 'TECHNICAL_DECISION',
          topic: 'Decide the homepage runtime contract',
          status: 'CLOSED',
          review_status: 'BOARD_REVIEW_PENDING',
          source_ticket_id: 'tkt_meeting_001',
          source_graph_node_id: 'node_meeting_001::execution',
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
          decision_record: {
            format: 'ADR_V1',
            context: 'Homepage contract alignment is blocking implementation.',
            decision: 'Use the narrower runtime contract for MVP.',
            rationale: [
              'It keeps board-approved scope stable.',
              'It avoids reopening remote handoff this round.',
            ],
            consequences: [
              'Implementation must stay inside the narrowed contract.',
              'Deferred alternatives require a later governance ticket.',
            ],
            archived_context_refs: ['art://runtime/tkt_meeting_001/meeting-digest.json'],
          },
        } as any}
        error={null}
        onClose={vi.fn()}
        onOpenReview={onOpenReview}
      />,
    )

    expect(screen.getByRole('heading', { name: /decide the homepage runtime contract/i })).toBeInTheDocument()
    expect(screen.getByText(/technical_decision/i)).toBeInTheDocument()
    expect(screen.getByText(/use the narrower runtime contract for mvp/i)).toBeInTheDocument()
    expect(screen.getByText(/homepage contract alignment is blocking implementation/i)).toBeInTheDocument()
    expect(screen.getByText(/art:\/\/runtime\/tkt_meeting_001\/meeting-digest\.json/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /audit trail/i })).toBeInTheDocument()
    expect(screen.getByText(/node_meeting_001::execution/i)).toBeInTheDocument()
    expect(screen.getByText(/position round closed/i)).toBeInTheDocument()
    expect(screen.getByText(/the meeting converged on one runtime contract/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /open linked review room/i }))

    expect(onOpenReview).toHaveBeenCalledWith('brp_001')
  })
})
