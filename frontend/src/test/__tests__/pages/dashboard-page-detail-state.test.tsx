import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useDashboardPageDetailState } from '../../../pages/dashboard-page-detail-state'

const { getIncidentDetailMock, getMeetingDetailMock, getDependencyInspectorMock } = vi.hoisted(() => ({
  getIncidentDetailMock: vi.fn(),
  getMeetingDetailMock: vi.fn(),
  getDependencyInspectorMock: vi.fn(),
}))

let capturedInvalidate: (() => void) | null = null

vi.mock('../../../hooks/useSSE', () => ({
  useSSE: (onInvalidate: () => void) => {
    capturedInvalidate = onInvalidate
  },
}))

vi.mock('../../../api/projections', () => ({
  getIncidentDetail: getIncidentDetailMock,
  getMeetingDetail: getMeetingDetailMock,
  getDependencyInspector: getDependencyInspectorMock,
}))

describe('dashboard-page-detail-state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capturedInvalidate = null
    getDependencyInspectorMock.mockResolvedValue(null)
    getMeetingDetailMock.mockResolvedValue(null)
  })

  it('keeps incident drawer content stable when background invalidate refresh fails', async () => {
    getIncidentDetailMock.mockResolvedValueOnce({
      incident: { incident_id: 'inc_001' },
      available_followup_actions: ['RESTORE_ONLY'],
      recommended_followup_action: 'RESTORE_ONLY',
    })
    const loadSnapshot = vi.fn().mockResolvedValue(undefined)
    const loadReviewRoom = vi.fn().mockResolvedValue(undefined)

    const { result } = renderHook(() =>
      useDashboardPageDetailState({
        reviewPackId: undefined,
        meetingId: undefined,
        incidentId: 'inc_001',
        dependencyInspectorOpen: false,
        activeWorkflowId: null,
        loadSnapshot,
        loadReviewRoom,
        clearReview: vi.fn(),
      }),
    )

    await waitFor(() => {
      expect(result.current.incidentDetail).toMatchObject({
        incident: { incident_id: 'inc_001' },
      })
    })

    getIncidentDetailMock.mockRejectedValueOnce(new Error('background incident refresh failed'))
    await act(async () => {
      capturedInvalidate?.()
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(result.current.incidentLoading).toBe(false)
    })
    expect(result.current.incidentDetail).toMatchObject({
      incident: { incident_id: 'inc_001' },
    })
    expect(result.current.incidentError).toBeNull()
  })
})
