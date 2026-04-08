import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReviewRoomDrawer } from '../../../components/overlays/ReviewRoomDrawer'

function buildReviewData() {
  return {
    review_pack: {
      meta: {
        approval_id: 'apr_persist_001',
        review_pack_id: 'brp_persist_001',
        review_pack_version: 1,
        workflow_id: 'wf_persist_001',
        review_type: 'REQUIREMENT_ELICITATION',
        created_at: '2026-04-08T12:00:00+08:00',
        priority: 'high',
      },
      subject: {
        title: 'Clarify initialization inputs',
      },
      trigger: {
        trigger_event_id: 'evt_persist_001',
        trigger_reason: 'Initial board directive is still below the minimum executable threshold.',
        why_now: 'Need structured answers before scope kickoff starts.',
      },
      recommendation: {
        recommended_action: 'APPROVE',
        recommended_option_id: 'elicitation_continue',
        summary: 'Capture the missing delivery answers and continue to scope kickoff.',
      },
      options: [
        {
          option_id: 'elicitation_continue',
          label: 'Continue after clarification',
          summary: 'Use the structured answers as the new startup brief.',
        },
      ],
      elicitation_questionnaire: [
        {
          question_id: 'delivery_scope',
          prompt: 'What is the narrowest acceptable delivery slice?',
          response_kind: 'SINGLE_SELECT',
          required: true,
          options: [
            {
              option_id: 'scope_single_a',
              label: 'Single A',
              summary: 'One path.',
            },
            {
              option_id: 'scope_single_b',
              label: 'Single B',
              summary: 'One path with closeout.',
            },
          ],
        },
        {
          question_id: 'core_roles',
          prompt: 'Which core roles must stay on the initial path?',
          response_kind: 'MULTI_SELECT',
          required: true,
          options: [
            {
              option_id: 'role_multi_a',
              label: 'Multi A',
              summary: 'Planner.',
            },
            {
              option_id: 'role_multi_b',
              label: 'Multi B',
              summary: 'Executor.',
            },
          ],
        },
      ],
      decision_form: {
        allowed_actions: ['APPROVE'],
        command_target_version: 1,
        requires_comment_on_reject: true,
        requires_constraint_patch_on_modify: false,
      },
    } as never,
    available_actions: ['APPROVE'],
    draft_defaults: {
      selected_option_id: 'elicitation_continue',
      comment_template: '',
      // Deliberately provide a fresh array on each refresh payload.
      elicitation_answers: [],
    } as never,
  }
}

describe('ReviewRoomDrawer persistence', () => {
  it('keeps single-select and multi-select answers after same-pack refresh rerender', async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn().mockResolvedValue(undefined)
    const commonProps = {
      isOpen: true,
      loading: false,
      inspectorData: null,
      inspectorLoading: false,
      error: null,
      submittingAction: null,
      onClose: vi.fn(),
      onOpenInspector: vi.fn(),
      onOpenArtifact: vi.fn(),
      onApprove,
      onReject: vi.fn().mockResolvedValue(undefined),
      onModifyConstraints: vi.fn().mockResolvedValue(undefined),
    }

    const { rerender } = render(<ReviewRoomDrawer {...commonProps} reviewData={buildReviewData()} />)

    await user.click(screen.getByLabelText('Single B'))
    await user.click(screen.getByLabelText('Multi A'))
    await user.click(screen.getByLabelText('Multi B'))

    expect(screen.getByLabelText('Single B')).toBeChecked()
    expect(screen.getByLabelText('Multi A')).toBeChecked()
    expect(screen.getByLabelText('Multi B')).toBeChecked()

    rerender(<ReviewRoomDrawer {...commonProps} reviewData={buildReviewData()} />)

    expect(screen.getByLabelText('Single B')).toBeChecked()
    expect(screen.getByLabelText('Multi A')).toBeChecked()
    expect(screen.getByLabelText('Multi B')).toBeChecked()
  })
})
