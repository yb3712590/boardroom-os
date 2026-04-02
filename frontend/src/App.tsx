import { useEffect, useEffectEvent, useState } from 'react'

import { BrowserRouter, Routes, Route, useNavigate, useParams } from 'react-router-dom'

import {
  boardApprove,
  boardReject,
  employeeFreeze,
  employeeHireRequest,
  employeeReplaceRequest,
  employeeRestore,
  getDashboard,
  getDependencyInspector,
  getDeveloperInspector,
  getIncidentDetail,
  getInbox,
  getRuntimeProvider,
  getReviewRoom,
  getWorkforce,
  incidentResolve,
  modifyConstraints,
  projectInit,
  runtimeProviderUpsert,
  type CommandAck,
  type DashboardData,
  type DependencyInspectorData,
  type StaffingHireTemplate,
  type IncidentDetailData,
  type DeveloperInspectorData,
  type InboxData,
  type InboxItem,
  type RuntimeProviderData,
  type ReviewRoomData,
  type WorkforceData,
} from './api'
import { DependencyInspectorDrawer } from './components/DependencyInspectorDrawer'
import { EventTicker } from './components/EventTicker'
import { IncidentDrawer } from './components/IncidentDrawer'
import { ProviderSettingsDrawer } from './components/ProviderSettingsDrawer'
import { ReviewRoomDrawer } from './components/ReviewRoomDrawer'
import { WorkforcePanel } from './components/WorkforcePanel'
import { WorkflowRiver } from './components/WorkflowRiver'
import './App.css'

const DEFAULT_INCIDENT_OPERATOR = 'emp_ops_1'

function assertAcceptedCommand(ack: CommandAck, fallbackMessage: string) {
  if (ack.status === 'ACCEPTED' || ack.status === 'DUPLICATE') {
    return
  }
  throw new Error(ack.reason ?? fallbackMessage)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(value)
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

function normalizeConstraints(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
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

function runtimeModeTone(value: string | null | undefined) {
  switch (value) {
    case 'OPENAI_COMPAT_LIVE':
      return 'live'
    case 'OPENAI_COMPAT_INCOMPLETE':
    case 'OPENAI_COMPAT_PAUSED':
      return 'warning'
    case 'LOCAL_DETERMINISTIC':
    default:
      return 'local'
  }
}

type ProjectInitFormProps = {
  submitting: boolean
  onSubmit: (payload: {
    northStarGoal: string
    hardConstraints: string[]
    budgetCap: number
  }) => Promise<void>
}

function ProjectInitForm({ submitting, onSubmit }: ProjectInitFormProps) {
  const [goal, setGoal] = useState('Ship the thinnest governance shell from dashboard to review room.')
  const [constraints, setConstraints] = useState(
    'Keep governance explicit.\nDo not move workflow truth into the browser.',
  )
  const [budgetCap, setBudgetCap] = useState('500000')

  return (
    <section className="project-init-panel" aria-labelledby="project-init-title">
      <div className="project-init-copy">
        <p className="eyebrow">Workflow Init</p>
        <h1 id="project-init-title">Launch workflow to first review</h1>
        <p>
          The backend still owns workflow truth. This entry now opens the next workflow, drafts the first scope
          decision, and pushes it through to the first board review.
        </p>
      </div>
      <form
        className="project-init-form"
        onSubmit={(event) => {
          event.preventDefault()
          void onSubmit({
            northStarGoal: goal.trim(),
            hardConstraints: normalizeConstraints(constraints),
            budgetCap: Number.parseInt(budgetCap, 10) || 0,
          })
        }}
      >
        <label>
          <span className="field-label">North star goal</span>
          <textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            rows={4}
          />
        </label>
        <label>
          <span className="field-label">Hard constraints</span>
          <textarea
            value={constraints}
            onChange={(event) => setConstraints(event.target.value)}
            rows={5}
          />
        </label>
        <label>
          <span className="field-label">Budget cap</span>
          <input
            type="number"
            min="0"
            value={budgetCap}
            onChange={(event) => setBudgetCap(event.target.value)}
          />
        </label>
        <button type="submit" className="primary-button" disabled={submitting || goal.trim().length === 0}>
          {submitting ? 'Advancing to first review…' : 'Launch to first review'}
        </button>
      </form>
    </section>
  )
}

type InboxWellProps = {
  items: InboxItem[]
  loading: boolean
  onOpenReview: (reviewPackId: string) => void
  onOpenIncident: (incidentId: string) => void
}

function InboxWell({ items, loading, onOpenReview, onOpenIncident }: InboxWellProps) {
  return (
    <aside className="inbox-well" aria-labelledby="inbox-title">
      <div className="section-heading">
        <p className="eyebrow">Inbox</p>
        <h2 id="inbox-title">Board actions and governance pressure</h2>
      </div>
      {loading ? <p className="muted-copy">Loading current inbox…</p> : null}
      {!loading && items.length === 0 ? (
        <p className="muted-copy">No board escalations are waiting right now.</p>
      ) : null}
      <div className="inbox-item-list">
        {items.map((item) => {
          const isReviewRoute = item.route_target.view === 'review_room' && item.route_target.review_pack_id
          const isIncidentRoute =
            item.route_target.view === 'incident_detail' && item.route_target.incident_id != null
          return isReviewRoute || isIncidentRoute ? (
            <button
              key={item.inbox_item_id}
              type="button"
              className={`inbox-item inbox-item-${item.priority}`}
              onClick={() => {
                if (isReviewRoute) {
                  onOpenReview(item.route_target.review_pack_id as string)
                  return
                }
                onOpenIncident(item.route_target.incident_id as string)
              }}
            >
              <span className="inbox-item-ribbon" aria-hidden="true" />
              <span className="inbox-item-copy">
                <strong>{item.title}</strong>
                <span>{item.summary}</span>
              </span>
              <span className="inbox-item-badges">{item.badges.join(' • ')}</span>
            </button>
          ) : (
            <div key={item.inbox_item_id} className={`inbox-item inbox-item-${item.priority}`}>
              <span className="inbox-item-ribbon" aria-hidden="true" />
              <span className="inbox-item-copy">
                <strong>{item.title}</strong>
                <span>{item.summary}</span>
              </span>
              <span className="inbox-item-badges">{item.badges.join(' • ')}</span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}

function ShellRoute() {
  const navigate = useNavigate()
  const { reviewPackId, incidentId } = useParams()
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [inbox, setInbox] = useState<InboxData | null>(null)
  const [workforce, setWorkforce] = useState<WorkforceData | null>(null)
  const [reviewRoom, setReviewRoom] = useState<ReviewRoomData | null>(null)
  const [incidentDetail, setIncidentDetail] = useState<IncidentDetailData | null>(null)
  const [developerInspector, setDeveloperInspector] = useState<DeveloperInspectorData | null>(null)
  const [dependencyInspector, setDependencyInspector] = useState<DependencyInspectorData | null>(null)
  const [snapshotLoading, setSnapshotLoading] = useState(true)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [inspectorLoading, setInspectorLoading] = useState(false)
  const [dependencyInspectorLoading, setDependencyInspectorLoading] = useState(false)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [dependencyInspectorError, setDependencyInspectorError] = useState<string | null>(null)
  const [projectInitPending, setProjectInitPending] = useState(false)
  const [submittingAction, setSubmittingAction] = useState<string | null>(null)
  const [submittingIncidentAction, setSubmittingIncidentAction] = useState(false)
  const [submittingStaffingAction, setSubmittingStaffingAction] = useState<string | null>(null)
  const [dependencyInspectorOpen, setDependencyInspectorOpen] = useState(false)
  const [runtimeProvider, setRuntimeProvider] = useState<RuntimeProviderData | null>(null)
  const [runtimeProviderLoading, setRuntimeProviderLoading] = useState(true)
  const [runtimeProviderError, setRuntimeProviderError] = useState<string | null>(null)
  const [runtimeProviderSubmitting, setRuntimeProviderSubmitting] = useState(false)
  const [providerSettingsOpen, setProviderSettingsOpen] = useState(false)

  const reloadSnapshot = async () => {
    setSnapshotError(null)
    setSnapshotLoading(true)
    setRuntimeProviderLoading(true)
    try {
      const [snapshotResult, runtimeProviderResult] = await Promise.allSettled([
        Promise.all([getDashboard(), getInbox(), getWorkforce()]),
        getRuntimeProvider(),
      ])
      if (snapshotResult.status === 'rejected') {
        throw snapshotResult.reason
      }
      const [nextDashboard, nextInbox, nextWorkforce] = snapshotResult.value
      setDashboard(nextDashboard)
      setInbox(nextInbox)
      setWorkforce(nextWorkforce)

      if (runtimeProviderResult.status === 'fulfilled') {
        setRuntimeProvider(runtimeProviderResult.value)
        setRuntimeProviderError(null)
      } else {
        setRuntimeProvider(null)
        setRuntimeProviderError(
          runtimeProviderResult.reason instanceof Error
            ? runtimeProviderResult.reason.message
            : 'Failed to load runtime provider settings.',
        )
      }
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Failed to load the latest boardroom snapshot.')
    } finally {
      setSnapshotLoading(false)
      setRuntimeProviderLoading(false)
    }
  }

  const refreshSnapshot = useEffectEvent(async () => {
    await reloadSnapshot()
  })

  const refreshReviewRoom = useEffectEvent(async (packId: string) => {
    setReviewLoading(true)
    setReviewError(null)
    setDeveloperInspector(null)
    try {
      const payload = await getReviewRoom(packId)
      setReviewRoom(payload)
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Failed to load the current review pack.')
      setReviewRoom(null)
    } finally {
      setReviewLoading(false)
    }
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

  useEffect(() => {
    if (!reviewPackId) {
      setReviewRoom(null)
      setDeveloperInspector(null)
      setReviewLoading(false)
      setReviewError(null)
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
    const workflowId = dashboard?.active_workflow?.workflow_id
    if (!workflowId) {
      setDependencyInspector(null)
      setDependencyInspectorLoading(false)
      setDependencyInspectorError(null)
      return
    }
    void refreshDependencyInspector(workflowId)
  }, [dependencyInspectorOpen, dashboard?.active_workflow?.workflow_id])

  useEffect(() => {
    if (typeof EventSource === 'undefined') {
      return
    }
    const eventSource = new EventSource('/api/v1/events/stream')
    const handleInvalidate = () => {
      void refreshSnapshot()
      if (reviewPackId) {
        void refreshReviewRoom(reviewPackId)
      }
      if (incidentId) {
        void refreshIncidentDetail(incidentId)
      }
      if (dependencyInspectorOpen && dashboard?.active_workflow?.workflow_id) {
        void refreshDependencyInspector(dashboard.active_workflow.workflow_id)
      }
    }
    eventSource.addEventListener('boardroom-event', handleInvalidate)
    return () => {
      eventSource.close()
    }
  }, [reviewPackId, incidentId, dependencyInspectorOpen, dashboard?.active_workflow?.workflow_id])

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
      await reloadSnapshot()
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
    setInspectorLoading(true)
    try {
      const payload = await getDeveloperInspector(reviewPackId)
      setDeveloperInspector(payload)
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Failed to load the developer inspector.')
    } finally {
      setInspectorLoading(false)
    }
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
      await reloadSnapshot()
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
      await reloadSnapshot()
      navigate('/')
    } catch (error) {
      setIncidentError(error instanceof Error ? error.message : 'Incident recovery failed.')
    } finally {
      setSubmittingIncidentAction(false)
    }
  }

  const handleEmployeeFreeze = async (employeeId: string) => {
    const workflowId = dashboard?.active_workflow?.workflow_id
    if (!workflowId) {
      return
    }
    const actionKey = `freeze:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeFreeze({
        workflow_id: workflowId,
        employee_id: employeeId,
        frozen_by: DEFAULT_INCIDENT_OPERATOR,
        reason: 'Pause this worker from taking new tickets.',
        idempotency_key: `employee-freeze:${workflowId}:${employeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee freeze failed.')
      await reloadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee freeze failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeRestore = async (employeeId: string) => {
    const workflowId = dashboard?.active_workflow?.workflow_id
    if (!workflowId) {
      return
    }
    const actionKey = `restore:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeRestore({
        workflow_id: workflowId,
        employee_id: employeeId,
        restored_by: DEFAULT_INCIDENT_OPERATOR,
        reason: 'Return this worker to active duty.',
        idempotency_key: `employee-restore:${workflowId}:${employeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee restore failed.')
      await reloadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee restore failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeHireRequest = async (template: StaffingHireTemplate, employeeId: string) => {
    const workflowId = dashboard?.active_workflow?.workflow_id
    if (!workflowId) {
      return
    }
    const actionKey = `hire:${template.template_id}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeHireRequest({
        workflow_id: workflowId,
        employee_id: employeeId,
        role_type: template.role_type,
        role_profile_refs: template.role_profile_refs,
        skill_profile: template.skill_profile,
        personality_profile: template.personality_profile,
        aesthetic_profile: template.aesthetic_profile,
        provider_id: template.provider_id,
        request_summary: template.request_summary,
        idempotency_key: `employee-hire-request:${workflowId}:${employeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee hire request failed.')
      await reloadSnapshot()
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
    const workflowId = dashboard?.active_workflow?.workflow_id
    if (!workflowId) {
      return
    }
    const actionKey = `replace:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeReplaceRequest({
        workflow_id: workflowId,
        replaced_employee_id: employeeId,
        replacement_employee_id: replacementEmployeeId,
        replacement_role_type: template.role_type,
        replacement_role_profile_refs: template.role_profile_refs,
        replacement_skill_profile: template.skill_profile,
        replacement_personality_profile: template.personality_profile,
        replacement_aesthetic_profile: template.aesthetic_profile,
        replacement_provider_id: template.provider_id,
        request_summary: `Replace ${employeeId} with a supported ${template.label.toLowerCase()} to keep the local delivery loop moving.`,
        idempotency_key: `employee-replace-request:${workflowId}:${employeeId}:${replacementEmployeeId}:${Date.now()}`,
      })
      assertAcceptedCommand(ack, 'Employee replacement request failed.')
      await reloadSnapshot()
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
      await reloadSnapshot()
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
      await reloadSnapshot()
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
      await reloadSnapshot()
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
  const runtimeWorkerCount =
    runtimeStatus?.configured_worker_count ?? runtimeProvider?.configured_worker_count ?? 0
  const runtimeReason =
    runtimeStatus?.reason ??
    runtimeProvider?.effective_reason ??
    'Runtime is using the currently saved local execution settings.'
  const runtimeHealth =
    runtimeStatus?.provider_health_summary ?? dashboard?.ops_strip.provider_health_summary ?? 'UNKNOWN'
  const finalReviewApprovedAt =
    completionSummary?.final_review_approved_at ?? completionSummary?.approved_at ?? null

  return (
    <>
      <div className="boardroom-app">
        <div className="boardroom-shell">
          <header className="top-chrome">
            <div>
              <p className="eyebrow">Boardroom OS</p>
              <h1>{activeWorkflow?.title ?? 'Boardroom governance shell'}</h1>
              <p className="top-chrome-copy">
                {activeWorkflow?.north_star_goal ??
                  'The workflow shell is waiting for the next local directive.'}
              </p>
            </div>
            <div className="top-chrome-meta">
              <section className={`runtime-status-card runtime-status-${runtimeModeTone(effectiveRuntimeMode)}`}>
                <div className="runtime-status-head">
                  <div>
                    <p className="eyebrow">Execution mode</p>
                    <strong>{runtimeProviderLabel}</strong>
                  </div>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => setProviderSettingsOpen(true)}
                  >
                    Runtime settings
                  </button>
                </div>
                <p className="runtime-status-copy">{runtimeReason}</p>
                <dl className="runtime-status-grid">
                  <div>
                    <dt>Model</dt>
                    <dd>{runtimeModel ?? 'Deterministic local runtime'}</dd>
                  </div>
                  <div>
                    <dt>Workers</dt>
                    <dd>{runtimeWorkerCount}</dd>
                  </div>
                  <div>
                    <dt>Health</dt>
                    <dd>{runtimeHealth}</dd>
                  </div>
                </dl>
              </section>
              <div className={`board-chip ${approvalsPending > 0 ? 'is-armed' : 'is-clear'}`}>
                <span className="board-chip-light" aria-hidden="true" />
                <strong>{approvalsPending > 0 ? 'Board Gate armed' : 'Board Gate clear'}</strong>
                <span>{approvalsPending > 0 ? `${approvalsPending} approvals pending` : 'No approvals pending'}</span>
              </div>
              <dl className="ops-strip">
                <div>
                  <dt>Budget</dt>
                  <dd>{formatNumber(dashboard?.ops_strip.budget_remaining ?? 0)}</dd>
                </div>
                <div>
                  <dt>Live tickets</dt>
                  <dd>{dashboard?.ops_strip.active_tickets ?? 0}</dd>
                </div>
                <div>
                  <dt>Blocked</dt>
                  <dd>{dashboard?.ops_strip.blocked_nodes ?? 0}</dd>
                </div>
                <div>
                  <dt>Deadline</dt>
                  <dd>{formatTimestamp(activeWorkflow?.deadline_at)}</dd>
                </div>
              </dl>
            </div>
          </header>

          <div className="boardroom-main">
            <InboxWell
              items={inbox?.items ?? []}
              loading={snapshotLoading}
              onOpenReview={handleOpenReview}
              onOpenIncident={handleOpenIncident}
            />

            <section className="boardroom-center">
              {snapshotError ? <div className="shell-error">{snapshotError}</div> : null}
              {snapshotLoading && dashboard == null ? <div className="shell-loading">Loading boardroom snapshot…</div> : null}
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
                      <button
                        type="button"
                        className="secondary-button inspector-launch"
                        onClick={() => setDependencyInspectorOpen(true)}
                      >
                        Inspect dependency chain
                      </button>
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
                <section className="completion-card" aria-labelledby="completion-card-title">
                  <div className="completion-card-copy">
                    <p className="eyebrow">Workflow result</p>
                    <h2 id="completion-card-title">Delivery completed</h2>
                    <p className="muted-copy">
                      Board approved {formatTimestamp(finalReviewApprovedAt)} and closeout completed{' '}
                      {formatTimestamp(completionSummary.closeout_completed_at)} for workflow{' '}
                      {completionSummary.workflow_id}.
                    </p>
                  </div>
                  <div className="completion-card-grid">
                    <div>
                      <span>Final title</span>
                      <strong>{completionSummary.title}</strong>
                    </div>
                    <div>
                      <span>Board approved</span>
                      <strong>{formatTimestamp(finalReviewApprovedAt)}</strong>
                    </div>
                    <div>
                      <span>Closeout completed</span>
                      <strong>{formatTimestamp(completionSummary.closeout_completed_at)}</strong>
                    </div>
                    <div>
                      <span>Selected option</span>
                      <strong>{completionSummary.selected_option_id ?? 'Board approved without option override'}</strong>
                    </div>
                    <div>
                      <span>Board comment</span>
                      <strong>{completionSummary.board_comment ?? 'No board comment recorded.'}</strong>
                    </div>
                    <div>
                      <span>Evidence refs</span>
                      <strong>{completionSummary.artifact_refs.length}</strong>
                    </div>
                    <div>
                      <span>Closeout refs</span>
                      <strong>{completionSummary.closeout_artifact_refs.length}</strong>
                    </div>
                  </div>
                  <p className="completion-card-summary">{completionSummary.summary}</p>
                  <div className="completion-card-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => handleOpenReview(completionSummary.final_review_pack_id)}
                    >
                      Open final review evidence
                    </button>
                  </div>
                </section>
              ) : null}
            </section>

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
          </div>
        </div>
      </div>

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
    </>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ShellRoute />} />
        <Route path="/review/:reviewPackId" element={<ShellRoute />} />
        <Route path="/incident/:incidentId" element={<ShellRoute />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
