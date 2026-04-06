import { lazy, Suspense, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { CompletionCard } from '../components/dashboard/CompletionCard'
import { InboxWell } from '../components/dashboard/InboxWell'
import { ProjectInitForm } from '../components/dashboard/ProjectInitForm'
import { WorkflowRiver } from '../components/dashboard/WorkflowRiver'
import { EventTicker } from '../components/events/EventTicker'
import { AppShell } from '../components/layout/AppShell'
import { ThreeColumnLayout } from '../components/layout/ThreeColumnLayout'
import { TopChrome } from '../components/layout/TopChrome'
import { Button } from '../components/shared/Button'
import { ErrorBoundary } from '../components/shared/ErrorBoundary'
import { LoadingSkeleton } from '../components/shared/LoadingSkeleton'
import { WorkforcePanel } from '../components/workforce/WorkforcePanel'
import { useBoardroomStore } from '../stores/boardroom-store'
import { useReviewStore } from '../stores/review-store'
import { useUIStore } from '../stores/ui-store'
import { formatTimestamp } from '../utils/format'
import { useDashboardPageActions } from './dashboard-page-actions'
import { useDashboardPageDetailState } from './dashboard-page-detail-state'
import { runtimeModeLabel } from './dashboard-page-helpers'

const ReviewRoomDrawer = lazy(() =>
  import('../components/overlays/ReviewRoomDrawer').then((module) => ({ default: module.ReviewRoomDrawer })),
)
const MeetingRoomDrawer = lazy(() =>
  import('../components/overlays/MeetingRoomDrawer').then((module) => ({ default: module.MeetingRoomDrawer })),
)
const IncidentDrawer = lazy(() =>
  import('../components/overlays/IncidentDrawer').then((module) => ({ default: module.IncidentDrawer })),
)
const DependencyInspectorDrawer = lazy(() =>
  import('../components/overlays/DependencyInspectorDrawer').then((module) => ({
    default: module.DependencyInspectorDrawer,
  })),
)
const ProviderSettingsDrawer = lazy(() =>
  import('../components/overlays/ProviderSettingsDrawer').then((module) => ({ default: module.ProviderSettingsDrawer })),
)
const ArtifactPreviewDrawer = lazy(() =>
  import('../components/overlays/ArtifactPreviewDrawer').then((module) => ({ default: module.ArtifactPreviewDrawer })),
)

export function DashboardPage() {
  const navigate = useNavigate()
  const { reviewPackId, meetingId, incidentId } = useParams()

  const dashboard = useBoardroomStore((state) => state.dashboard)
  const inbox = useBoardroomStore((state) => state.inbox)
  const workforce = useBoardroomStore((state) => state.workforce)
  const runtimeProvider = useBoardroomStore((state) => state.runtimeProvider)
  const snapshotLoading = useBoardroomStore((state) => state.snapshotLoading)
  const snapshotError = useBoardroomStore((state) => state.snapshotError)
  const runtimeProviderLoading = useBoardroomStore((state) => state.runtimeProviderLoading)
  const runtimeProviderError = useBoardroomStore((state) => state.runtimeProviderError)
  const loadSnapshot = useBoardroomStore((state) => state.loadSnapshot)
  const setSnapshotError = useBoardroomStore((state) => state.setSnapshotError)
  const setRuntimeProviderError = useBoardroomStore((state) => state.setRuntimeProviderError)

  const reviewRoom = useReviewStore((state) => state.reviewRoom)
  const developerInspector = useReviewStore((state) => state.developerInspector)
  const reviewLoading = useReviewStore((state) => state.loading)
  const inspectorLoading = useReviewStore((state) => state.inspectorLoading)
  const reviewError = useReviewStore((state) => state.error)
  const submittingAction = useReviewStore((state) => state.submittingAction)
  const loadReviewRoom = useReviewStore((state) => state.loadReviewRoom)
  const loadDeveloperInspector = useReviewStore((state) => state.loadDeveloperInspector)
  const clearReview = useReviewStore((state) => state.clearReview)
  const setSubmittingAction = useReviewStore((state) => state.setSubmittingAction)
  const setReviewError = useReviewStore((state) => state.setError)

  const dependencyInspectorOpen = useUIStore((state) => state.dependencyInspectorOpen)
  const providerSettingsOpen = useUIStore((state) => state.providerSettingsOpen)
  const projectInitPending = useUIStore((state) => state.projectInitPending)
  const submittingStaffingAction = useUIStore((state) => state.submittingStaffingAction)
  const submittingIncidentAction = useUIStore((state) => state.submittingIncidentAction)
  const runtimeProviderSubmitting = useUIStore((state) => state.runtimeProviderSubmitting)
  const setDependencyInspectorOpen = useUIStore((state) => state.setDependencyInspectorOpen)
  const setProviderSettingsOpen = useUIStore((state) => state.setProviderSettingsOpen)
  const setProjectInitPending = useUIStore((state) => state.setProjectInitPending)
  const setSubmittingStaffingAction = useUIStore((state) => state.setSubmittingStaffingAction)
  const setSubmittingIncidentAction = useUIStore((state) => state.setSubmittingIncidentAction)
  const setRuntimeProviderSubmitting = useUIStore((state) => state.setRuntimeProviderSubmitting)

  const activeWorkflowId = dashboard?.active_workflow?.workflow_id ?? null
  const reviewPack = reviewRoom?.review_pack
  const [artifactPreviewRef, setArtifactPreviewRef] = useState<string | null>(null)

  const {
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
  } = useDashboardPageDetailState({
    reviewPackId,
    meetingId,
    incidentId,
    dependencyInspectorOpen,
    activeWorkflowId,
    loadSnapshot,
    loadReviewRoom,
    clearReview,
  })

  const {
    handleOpenReview,
    handleOpenMeeting,
    handleOpenIncident,
    handleProjectInit,
    handleRuntimeProviderSave,
    handleIncidentResolve,
    handleEmployeeFreeze,
    handleEmployeeRestore,
    handleEmployeeHireRequest,
    handleEmployeeReplaceRequest,
    handleApprove,
    handleReject,
    handleModifyConstraints,
    closeReviewRoom,
    closeMeeting,
    closeIncident,
    openInspectorForReview,
  } = useDashboardPageActions({
    activeWorkflowId,
    reviewPackId,
    meetingId,
    navigate,
    loadSnapshot,
    reviewPack,
    incidentDetail,
    setProjectInitPending,
    setSnapshotError,
    setRuntimeProviderError,
    setProviderSettingsOpen,
    setRuntimeProviderSubmitting,
    setSubmittingIncidentAction,
    setIncidentError,
    setSubmittingStaffingAction,
    setSubmittingAction,
    setReviewError,
  })

  const handleOpenReviewRoom = (packId: string) => {
    setDependencyInspectorOpen(false)
    handleOpenReview(packId)
  }

  const handleOpenMeetingRoom = (nextMeetingId: string) => {
    setDependencyInspectorOpen(false)
    handleOpenMeeting(nextMeetingId)
  }

  const handleOpenIncidentRoom = (nextIncidentId: string) => {
    setDependencyInspectorOpen(false)
    handleOpenIncident(nextIncidentId)
  }

  const handleOpenInspector = async () => {
    await openInspectorForReview(loadDeveloperInspector)
  }

  const handleOpenArtifactPreview = (artifactRef: string) => {
    setArtifactPreviewRef(artifactRef)
  }

  const approvalsPending = dashboard?.inbox_counts.approvals_pending ?? 0
  const activeWorkflow = dashboard?.active_workflow
  const runtimeStatus = dashboard?.runtime_status
  const completionSummary = dashboard?.completion_summary
  const effectiveRuntimeMode = runtimeStatus?.effective_mode ?? runtimeProvider?.effective_mode ?? 'LOCAL_DETERMINISTIC'
  const runtimeProviderLabel =
    runtimeStatus?.provider_label ?? runtimeModeLabel(runtimeProvider?.effective_mode ?? effectiveRuntimeMode)
  const runtimeModel = runtimeStatus?.model ?? runtimeProvider?.model
  const runtimeWorkerCount = runtimeStatus?.configured_worker_count ?? runtimeProvider?.configured_worker_count ?? 0
  const runtimeReason =
    runtimeStatus?.reason ??
    runtimeProvider?.effective_reason ??
    'Runtime is using the currently saved local execution settings.'
  const runtimeHealth =
    runtimeStatus?.provider_health_summary ??
    runtimeProvider?.provider_health_summary ??
    dashboard?.ops_strip.provider_health_summary ??
    'LOCAL_ONLY'

  return (
    <ErrorBoundary>
      <AppShell>
        <TopChrome
          title={activeWorkflow?.title ?? 'Boardroom governance shell'}
          northStarGoal={
            activeWorkflow?.north_star_goal ?? 'The workflow shell is waiting for the next local directive.'
          }
          effectiveRuntimeMode={effectiveRuntimeMode}
          runtimeProviderLabel={runtimeProviderLabel}
          runtimeModel={runtimeModel}
          runtimeWorkerCount={runtimeWorkerCount}
          runtimeHealth={runtimeHealth}
          runtimeReason={runtimeReason}
          approvalsPending={approvalsPending}
          budgetRemaining={dashboard?.ops_strip.budget_remaining ?? 0}
          activeTickets={dashboard?.ops_strip.active_tickets ?? 0}
          blockedNodes={dashboard?.ops_strip.blocked_nodes ?? 0}
          deadlineAt={activeWorkflow?.deadline_at}
          onOpenRuntimeSettings={() => setProviderSettingsOpen(true)}
        />

        <ThreeColumnLayout
          left={
            <InboxWell
              items={inbox?.items ?? []}
              loading={snapshotLoading}
              onOpenReview={handleOpenReviewRoom}
              onOpenMeeting={handleOpenMeetingRoom}
              onOpenIncident={handleOpenIncidentRoom}
            />
          }
          center={
            <section className="boardroom-center">
              {snapshotError ? <div className="shell-error">{snapshotError}</div> : null}
              {snapshotLoading && dashboard == null ? (
                <>
                  <WorkflowRiver phases={[]} approvalsPending={0} loading={true} />
                  <section className="center-detail-grid center-detail-grid-loading" aria-label="Current workflow loading" aria-busy="true">
                    <LoadingSkeleton lines={4} className="center-detail-skeleton" />
                    <LoadingSkeleton lines={4} className="center-detail-skeleton" />
                  </section>
                </>
              ) : null}
              {!snapshotLoading && activeWorkflow == null ? (
                <ProjectInitForm submitting={projectInitPending} onSubmit={handleProjectInit} />
              ) : null}
              {activeWorkflow != null && dashboard != null ? (
                <>
                  <WorkflowRiver
                    phases={dashboard.pipeline_summary.phases}
                    approvalsPending={dashboard.inbox_counts.approvals_pending}
                  />
                  <section className="center-detail-grid">
                    <div>
                      <p className="eyebrow">Current workflow</p>
                      <h2>{activeWorkflow.north_star_goal}</h2>
                      <p className="muted-copy">
                        Workspace {dashboard.workspace.workspace_name} · started{' '}
                        {formatTimestamp(activeWorkflow.started_at, 'Not recorded')}
                      </p>
                      <Button
                        type="button"
                        variant="secondary"
                        className="inspector-launch"
                        onClick={() => setDependencyInspectorOpen(true)}
                      >
                        Inspect dependency chain
                      </Button>
                    </div>
                    <div className="center-detail-list">
                      <div>
                        <span>Provider health</span>
                        <strong>{dashboard.ops_strip.provider_health_summary}</strong>
                      </div>
                      <div>
                        <span>Idle workers</span>
                        <strong>{dashboard.workforce_summary.idle_workers}</strong>
                      </div>
                      <div>
                        <span>Active workers</span>
                        <strong>{dashboard.workforce_summary.active_workers}</strong>
                      </div>
                      <div>
                        <span>Incidents</span>
                        <strong>{dashboard.ops_strip.open_incidents}</strong>
                      </div>
                    </div>
                  </section>
                </>
              ) : null}
              {completionSummary && !reviewPackId ? (
                <CompletionCard
                  summary={completionSummary}
                  onOpenReview={handleOpenReviewRoom}
                  onOpenArtifact={handleOpenArtifactPreview}
                />
              ) : null}
            </section>
          }
          right={
            <aside className="boardroom-support">
              <WorkforcePanel
                workforce={workforce}
                loading={snapshotLoading && workforce == null}
                submittingAction={submittingStaffingAction}
                onFreeze={handleEmployeeFreeze}
                onRestore={handleEmployeeRestore}
                onRequestHire={handleEmployeeHireRequest}
                onRequestReplacement={handleEmployeeReplaceRequest}
              />
              <EventTicker events={dashboard?.event_stream_preview ?? []} loading={snapshotLoading && dashboard == null} />
            </aside>
          }
        />
      </AppShell>

      <Suspense fallback={null}>
        <ReviewRoomDrawer
          key={
            reviewRoom?.review_pack != null
              ? `${reviewRoom.review_pack.meta.review_pack_id}:${reviewRoom.review_pack.meta.review_pack_version}`
              : reviewPackId ?? 'review-room-closed'
          }
          isOpen={Boolean(reviewPackId)}
          loading={reviewLoading}
          reviewData={reviewRoom}
          inspectorData={developerInspector}
          inspectorLoading={inspectorLoading}
          error={reviewError}
          submittingAction={submittingAction}
          onClose={closeReviewRoom}
          onOpenInspector={handleOpenInspector}
          onOpenArtifact={handleOpenArtifactPreview}
          onApprove={handleApprove}
          onReject={handleReject}
          onModifyConstraints={handleModifyConstraints}
        />

        <MeetingRoomDrawer
          key={
            meetingDetail != null
              ? `${meetingDetail.meeting_id}:${meetingDetail.updated_at}`
              : meetingId ?? 'meeting-room-closed'
          }
          isOpen={Boolean(meetingId)}
          loading={meetingLoading}
          meetingData={meetingDetail}
          error={meetingError}
          onClose={closeMeeting}
          onOpenReview={handleOpenReviewRoom}
        />

        <IncidentDrawer
          key={
            incidentDetail != null
              ? `${incidentDetail.incident.incident_id}:${incidentDetail.recommended_followup_action ?? 'none'}`
              : incidentId ?? 'incident-closed'
          }
          isOpen={Boolean(incidentId)}
          loading={incidentLoading}
          incidentData={incidentDetail}
          error={incidentError}
          submitting={submittingIncidentAction}
          onClose={closeIncident}
          onResolve={handleIncidentResolve}
        />

        <DependencyInspectorDrawer
          isOpen={dependencyInspectorOpen}
          loading={dependencyInspectorLoading}
          inspectorData={dependencyInspector}
          error={dependencyInspectorError}
          onClose={() => setDependencyInspectorOpen(false)}
          onOpenReview={handleOpenReviewRoom}
          onOpenIncident={handleOpenIncidentRoom}
        />

        <ProviderSettingsDrawer
          isOpen={providerSettingsOpen}
          providerData={runtimeProvider}
          loading={runtimeProviderLoading}
          error={runtimeProviderError}
          submitting={runtimeProviderSubmitting}
          onClose={() => setProviderSettingsOpen(false)}
          onSave={handleRuntimeProviderSave}
        />

        <ArtifactPreviewDrawer
          isOpen={artifactPreviewRef != null}
          artifactRef={artifactPreviewRef}
          onClose={() => setArtifactPreviewRef(null)}
        />
      </Suspense>
    </ErrorBoundary>
  )
}
