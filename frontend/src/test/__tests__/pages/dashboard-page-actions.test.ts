import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useDashboardPageActions } from '../../../pages/dashboard-page-actions'

const { boardApproveMock } = vi.hoisted(() => ({
  boardApproveMock: vi.fn(),
}))

vi.mock('../../../api/commands', () => ({
  boardApprove: boardApproveMock,
  boardReject: vi.fn(),
  modifyConstraints: vi.fn(),
  projectInit: vi.fn(),
  runtimeProviderUpsert: vi.fn(),
  incidentResolve: vi.fn(),
  employeeFreeze: vi.fn(),
  employeeRestore: vi.fn(),
  employeeHireRequest: vi.fn(),
  employeeReplaceRequest: vi.fn(),
}))

describe('dashboard-page-actions', () => {
  it('treats board approve rejected ack as an error instead of successful completion', async () => {
    boardApproveMock.mockResolvedValue({
      command_id: 'cmd_001',
      idempotency_key: 'board-approve_001',
      status: 'REJECTED',
      received_at: '2026-04-08T18:10:00+08:00',
      reason: 'Elicitation question delivery_scope requires one selection.',
      causation_hint: 'approval:apr_001',
    })
    const navigate = vi.fn()
    const loadSnapshot = vi.fn().mockResolvedValue(undefined)
    const setReviewError = vi.fn()
    const setSubmittingAction = vi.fn()

    const { result } = renderHook(() =>
      useDashboardPageActions({
        activeWorkflowId: 'wf_001',
        reviewPackId: 'brp_001',
        meetingId: undefined,
        navigate,
        loadSnapshot,
        reviewPack: {
          meta: {
            review_pack_id: 'brp_001',
            review_pack_version: 1,
            approval_id: 'apr_001',
          },
          decision_form: {
            command_target_version: 1,
          },
        },
        incidentDetail: null,
        setProjectInitPending: vi.fn(),
        setSnapshotError: vi.fn(),
        setRuntimeProviderError: vi.fn(),
        setProviderSettingsOpen: vi.fn(),
        setRuntimeProviderSubmitting: vi.fn(),
        setSubmittingIncidentAction: vi.fn(),
        setIncidentError: vi.fn(),
        setSubmittingStaffingAction: vi.fn(),
        setSubmittingAction,
        setReviewError,
      }),
    )

    await act(async () => {
      await result.current.handleApprove({
        selectedOptionId: 'option_001',
        boardComment: 'Proceed after clarifying answers.',
        elicitationAnswers: [
          {
            question_id: 'delivery_scope',
            selected_option_ids: [],
            text: '',
          },
        ],
      })
    })

    expect(setReviewError).toHaveBeenCalledWith(
      'Elicitation question delivery_scope requires one selection.',
    )
    expect(loadSnapshot).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
    expect(setSubmittingAction).toHaveBeenLastCalledWith(null)
  })
})
