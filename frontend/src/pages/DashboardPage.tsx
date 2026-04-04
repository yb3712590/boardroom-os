import { useEffect, useEffectEvent, useState } from 'react'

import { useNavigate, useParams } from 'react-router-dom'

import {
  boardApprove,
  boardReject,
  employeeFreeze,
  employeeHireRequest,
  employeeReplaceRequest,
  employeeRestore,
  incidentResolve,
  modifyConstraints,
  projectInit,
  runtimeProviderUpsert,
} from '../api/commands'
import { getDependencyInspector, getIncidentDetail } from '../api/projections'
import { CompletionCard } from '../components/dashboard/CompletionCard'
import { InboxWell } from '../components/dashboard/InboxWell'
import { ProjectInitForm } from '../components/dashboard/ProjectInitForm'
import { WorkflowRiver } from '../components/dashboard/WorkflowRiver'
import { EventTicker } from '../components/events/EventTicker'
import { AppShell } from '../components/layout/AppShell'
import { ThreeColumnLayout } from '../components/layout/ThreeColumnLayout'
import { TopChrome } from '../components/layout/TopChrome'
import { DependencyInspectorDrawer } from '../components/overlays/DependencyInspectorDrawer'
import { IncidentDrawer } from '../components/overlays/IncidentDrawer'
import { ProviderSettingsDrawer } from '../components/overlays/ProviderSettingsDrawer'
import { ReviewRoomDrawer } from '../components/overlays/ReviewRoomDrawer'
import { Button } from '../components/shared/Button'
import { ErrorBoundary } from '../components/shared/ErrorBoundary'
import { WorkforcePanel } from '../components/workforce/WorkforcePanel'
import { useSSE } from '../hooks/useSSE'
import { useBoardroomStore } from '../stores/boardroom-store'
import { useReviewStore } from '../stores/review-store'
import { useUIStore } from '../stores/ui-store'
import type { CommandAck, DependencyInspectorData, IncidentDetailData } from '../types/api'
import type { StaffingHireTemplate } from '../types/domain'

const DEFAULT_INCIDENT_OPERATOR = 'emp_ops_1'

function assertAcceptedCommand(ack: CommandAck, fallbackMessage: string) {
  if (ack.status === 'ACCEPTED' || ack.status === 'DUPLICATE') {
    return
  }
  throw new Error(ack.reason ?? fallbackMessage)
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return 'No deadline'
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

function runtimeModeLabel(value: string | null | undefined) {
  switch (value) {
    case 'OPENAI_COMPAT_LIVE':
      return 'OpenAI Compat'
    case 'OPENAI_COMPAT_INCOMPLETE':
      return 'OpenAI Compat incomplete'
    case 'OPENAI_COMPAT_PAUSED':
      return 'OpenAI Compat paused'
    case 'LOCAL_DETERMINISTIC':
    default:
      return 'Local deterministic'
  }
}

export function DashboardPage() {
  const navigate = useNavigate()
  const { reviewPackId, incidentId } = useParams()

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

  const [incidentDetail, setIncidentDetail] = useState<IncidentDetailData | null>(null)
  const [dependencyInspector, setDependencyInspector] = useState<DependencyInspectorData | null>(null)
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [dependencyInspectorLoading, setDependencyInspectorLoading] = useState(false)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [dependencyInspectorError, setDependencyInspectorError] = useState<string | null>(null)

  const activeWorkflowId = dashboard?.active_workflow?.workflow_id ?? null

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

  const handleOpenReview = (packId: string) => {
    setDependencyInspectorOpen(false)
    navigate(`/review/${packId}`)
  }

  const handleOpenIncident = (nextIncidentId: string) => {
    setDependencyInspectorOpen(false)
    navigate(`/incident/${nextIncidentId}`)
  }

  const handleProjectInit = async (payload: {
    northStarGoal: string
    hardConstraints: string[]
    budgetCap: number
  }) => {
    setProjectInitPending(true)
    setSnapshotError(null)
    try {
      await projectInit({
        north_star_goal: payload.northStarGoal,
        hard_constraints: payload.hardConstraints,
        budget_cap: payload.budgetCap,
        deadline_at: null,
      })
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Failed to launch the local workflow.')
    } finally {
      setProjectInitPending(false)
    }
  }

  const handleOpenInspector = async () => {
    if (!reviewPackId) {
      return
    }
    await loadDeveloperInspector(reviewPackId)
  }

  const reviewPack = reviewRoom?.review_pack

  const handleRuntimeProviderSave = async (input: {
    mode: string
    baseUrl: string | null
    apiKey: string | null
    model: string | null
    timeoutSec: number
    reasoningEffort: string | null
  }) => {
    setRuntimeProviderSubmitting(true)
    setRuntimeProviderError(null)
    try {
      await runtimeProviderUpsert({
        mode: input.mode,
        base_url: input.baseUrl,
        api_key: input.apiKey,
        model: input.model,
        timeout_sec: input.timeoutSec,
        reasoning_effort: input.reasoningEffort,
        idempotency_key: `runtime-provider-upsert:${Date.now()}`,
      })
      await loadSnapshot()
      setProviderSettingsOpen(false)
    } catch (error) {
      setRuntimeProviderError(error instanceof Error ? error.message : 'Failed to save runtime provider settings.')
    } finally {
      setRuntimeProviderSubmitting(false)
    }
  }

  const handleIncidentResolve = async (input: {
    resolutionSummary: string
    followupAction: string
  }) => {
    if (!incidentDetail) {
      return
    }
    setSubmittingIncidentAction(true)
    try {
      await incidentResolve({
        incident_id: incidentDetail.incident.incident_id,
        resolved_by: DEFAULT_INCIDENT_OPERATOR,
        resolution_summary: input.resolutionSummary,
        followup_action: input.followupAction,
        idempotency_key: `incident-resolve:${incidentDetail.incident.incident_id}:${Date.now()}`,
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setIncidentError(error instanceof Error ? error.message : 'Incident recovery failed.')
    } finally {
      setSubmittingIncidentAction(false)
    }
  }

  const handleEmployeeFreeze = async (employeeId: string) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `freeze:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeFreeze({
        workflow_id: activeWorkflowId,
        employee_id: employeeId,
        frozen_by: DEFAULT_INCIDENT_OPERATOR,
        reason: 'Pause this worker from taking new tickets.',
        idempotency_key: `employee-freeze:${activeWorkflowId}:${employeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee freeze failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee freeze failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeRestore = async (employeeId: string) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `restore:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeRestore({
        workflow_id: activeWorkflowId,
        employee_id: employeeId,
        restored_by: DEFAULT_INCIDENT_OPERATOR,
        reason: 'Return this worker to active duty.',
        idempotency_key: `employee-restore:${activeWorkflowId}:${employeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee restore failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee restore failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeHireRequest = async (template: StaffingHireTemplate, employeeId: string) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `hire:${template.template_id}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeHireRequest({
        workflow_id: activeWorkflowId,
        employee_id: employeeId,
        role_type: template.role_type,
        role_profile_refs: template.role_profile_refs,
        skill_profile: template.skill_profile,
        personality_profile: template.personality_profile,
        aesthetic_profile: template.aesthetic_profile,
        provider_id: template.provider_id,
        request_summary: template.request_summary,
        idempotency_key: `employee-hire-request:${activeWorkflowId}:${employeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee hire request failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee hire request failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeReplaceRequest = async (
    employeeId: string,
    template: StaffingHireTemplate,
    replacementEmployeeId: string,
  ) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `replace:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeReplaceRequest({
        workflow_id: activeWorkflowId,
        replaced_employee_id: employeeId,
        replacement_employee_id: replacementEmployeeId,
        replacement_role_type: template.role_type,
        replacement_role_profile_refs: template.role_profile_refs,
        replacement_skill_profile: template.skill_profile,
        replacement_personality_profile: template.personality_profile,
        replacement_aesthetic_profile: template.aesthetic_profile,
        replacement_provider_id: template.provider_id,
        request_summary: `Replace ${employeeId} with a supported ${template.label.toLowerCase()} to keep the local delivery loop moving.`,
        idempotency_key: `employee-replace-request:${activeWorkflowId}:${employeeId}:${replacementEmployeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee replacement request failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee replacement request failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleApprove = async (input: { selectedOptionId: string; boardComment: string }) => {
    if (!reviewPack) {
      return
    }
    setSubmittingAction('APPROVE')
    try {
      await boardApprove({
        review_pack_id: reviewPack.meta.review_pack_id,
        review_pack_version: reviewPack.meta.review_pack_version,
        command_target_version: reviewPack.decision_form.command_target_version,
        approval_id: reviewPack.meta.approval_id,
        selected_option_id: input.selectedOptionId,
        board_comment: input.boardComment,
        idempotency_key: `board-approve:${reviewPack.meta.approval_id}:${Date.now()}`,
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Board approve failed.')
    } finally {
      setSubmittingAction(null)
    }
  }

  const handleReject = async (input: { boardComment: string; rejectionReasons: string[] }) => {
    if (!reviewPack) {
      return
    }
    setSubmittingAction('REJECT')
    try {
      await boardReject({
        review_pack_id: reviewPack.meta.review_pack_id,
        review_pack_version: reviewPack.meta.review_pack_version,
        command_target_version: reviewPack.decision_form.command_target_version,
        approval_id: reviewPack.meta.approval_id,
        board_comment: input.boardComment,
        rejection_reasons: input.rejectionReasons,
        idempotency_key: `board-reject:${reviewPack.meta.approval_id}:${Date.now()}`,
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Board reject failed.')
    } finally {
      setSubmittingAction(null)
    }
  }

  const handleModifyConstraints = async (input: {
    boardComment: string
    addRules: string[]
    removeRules: string[]
    replaceRules: string[]
  }) => {
    if (!reviewPack) {
      return
    }
    setSubmittingAction('MODIFY_CONSTRAINTS')
    try {
      await modifyConstraints({
        review_pack_id: reviewPack.meta.review_pack_id,
        review_pack_version: reviewPack.meta.review_pack_version,
        command_target_version: reviewPack.decision_form.command_target_version,
        approval_id: reviewPack.meta.approval_id,
        constraint_patch: {
          add_rules: input.addRules,
          remove_rules: input.removeRules,
          replace_rules: input.replaceRules,
        },
        board_comment: input.boardComment,
        idempotency_key: `modify-constraints:${reviewPack.meta.approval_id}:${Date.now()}`,
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Constraint update failed.')
    } finally {
      setSubmittingAction(null)
    }
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
              onOpenReview={handleOpenReview}
              onOpenIncident={handleOpenIncident}
            />
          }
          center={
            <section className="boardroom-center">
              {snapshotError ? <div className="shell-error">{snapshotError}</div> : null}
              {snapshotLoading && dashboard == null ? <div className="shell-loading">Loading boardroom snapshot...</div> : null}
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
                        Workspace {dashboard.workspace.workspace_name} · started {formatTimestamp(activeWorkflow.started_at)}
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
                <CompletionCard summary={completionSummary} onOpenReview={handleOpenReview} />
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
              <EventTicker events={dashboard?.event_stream_preview ?? []} />
            </aside>
          }
        />
      </AppShell>

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
        onClose={() => navigate('/')}
        onOpenInspector={handleOpenInspector}
        onApprove={handleApprove}
        onReject={handleReject}
        onModifyConstraints={handleModifyConstraints}
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
        onClose={() => navigate('/')}
        onResolve={handleIncidentResolve}
      />

      <DependencyInspectorDrawer
        isOpen={dependencyInspectorOpen}
        loading={dependencyInspectorLoading}
        inspectorData={dependencyInspector}
        error={dependencyInspectorError}
        onClose={() => setDependencyInspectorOpen(false)}
        onOpenReview={handleOpenReview}
        onOpenIncident={handleOpenIncident}
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
    </ErrorBoundary>
  )
}
