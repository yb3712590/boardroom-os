import { useEffect, useEffectEvent, useState } from 'react'

import { getDependencyInspector, getIncidentDetail, getMeetingDetail } from '../api/projections'
import { useSSE } from '../hooks/useSSE'
import type { DependencyInspectorData, IncidentDetailData, MeetingDetailData } from '../types/api'

type DashboardPageDetailStateArgs = {
  reviewPackId: string | undefined
  meetingId: string | undefined
  incidentId: string | undefined
  dependencyInspectorOpen: boolean
  activeWorkflowId: string | null
  loadSnapshot: () => Promise<void>
  loadReviewRoom: (reviewPackId: string) => Promise<void>
  clearReview: () => void
}

export function useDashboardPageDetailState({
  reviewPackId,
  meetingId,
  incidentId,
  dependencyInspectorOpen,
  activeWorkflowId,
  loadSnapshot,
  loadReviewRoom,
  clearReview,
}: DashboardPageDetailStateArgs) {
  const [incidentDetail, setIncidentDetail] = useState<IncidentDetailData | null>(null)
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetailData | null>(null)
  const [dependencyInspector, setDependencyInspector] = useState<DependencyInspectorData | null>(null)
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [meetingLoading, setMeetingLoading] = useState(false)
  const [dependencyInspectorLoading, setDependencyInspectorLoading] = useState(false)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [meetingError, setMeetingError] = useState<string | null>(null)
  const [dependencyInspectorError, setDependencyInspectorError] = useState<string | null>(null)

  const refreshSnapshot = useEffectEvent(async () => {
    await loadSnapshot()
  })

  const refreshReviewRoom = useEffectEvent(async (packId: string) => {
    await loadReviewRoom(packId)
  })

  const refreshIncidentDetail = useEffectEvent(async (nextIncidentId: string) => {
    setIncidentLoading(true)
    setIncidentError(null)
    try {
      const payload = await getIncidentDetail(nextIncidentId)
      setIncidentDetail(payload)
    } catch (error) {
      setIncidentError(error instanceof Error ? error.message : 'Failed to load the current incident detail.')
      setIncidentDetail(null)
    } finally {
      setIncidentLoading(false)
    }
  })

  const refreshMeetingDetail = useEffectEvent(async (nextMeetingId: string) => {
    setMeetingLoading(true)
    setMeetingError(null)
    try {
      const payload = await getMeetingDetail(nextMeetingId)
      setMeetingDetail(payload)
    } catch (error) {
      setMeetingDetail(null)
      setMeetingError(error instanceof Error ? error.message : 'Failed to load the current meeting room.')
    } finally {
      setMeetingLoading(false)
    }
  })

  const refreshDependencyInspector = useEffectEvent(async (workflowId: string) => {
    setDependencyInspectorLoading(true)
    setDependencyInspectorError(null)
    try {
      const payload = await getDependencyInspector(workflowId)
      setDependencyInspector(payload)
    } catch (error) {
      setDependencyInspector(null)
      setDependencyInspectorError(
        error instanceof Error ? error.message : 'Failed to load the current dependency inspector.',
      )
    } finally {
      setDependencyInspectorLoading(false)
    }
  })

  useEffect(() => {
    void refreshSnapshot()
  }, [])

  const handleInvalidate = useEffectEvent(async () => {
    await refreshSnapshot()
    if (reviewPackId) {
      await refreshReviewRoom(reviewPackId)
    }
    if (meetingId) {
      await refreshMeetingDetail(meetingId)
    }
    if (incidentId) {
      await refreshIncidentDetail(incidentId)
    }
    if (dependencyInspectorOpen && activeWorkflowId) {
      await refreshDependencyInspector(activeWorkflowId)
    }
  })

  useEffect(() => {
    if (!reviewPackId) {
      clearReview()
      return
    }
    void refreshReviewRoom(reviewPackId)
  }, [reviewPackId])

  useEffect(() => {
    if (!incidentId) {
      setIncidentDetail(null)
      setIncidentLoading(false)
      setIncidentError(null)
      return
    }
    void refreshIncidentDetail(incidentId)
  }, [incidentId])

  useEffect(() => {
    if (!meetingId) {
      setMeetingDetail(null)
      setMeetingLoading(false)
      setMeetingError(null)
      return
    }
    void refreshMeetingDetail(meetingId)
  }, [meetingId])

  useEffect(() => {
    if (!dependencyInspectorOpen) {
      return
    }
    if (!activeWorkflowId) {
      setDependencyInspector(null)
      setDependencyInspectorLoading(false)
      setDependencyInspectorError(null)
      return
    }
    void refreshDependencyInspector(activeWorkflowId)
  }, [dependencyInspectorOpen, activeWorkflowId])

  useSSE(() => {
    void handleInvalidate()
  })

  return {
    incidentDetail,
    meetingDetail,
    dependencyInspector,
    incidentLoading,
    meetingLoading,
    dependencyInspectorLoading,
    incidentError,
    meetingError,
    dependencyInspectorError,
    setIncidentError,
  }
}
