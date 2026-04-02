import { useEffect, useEffectEvent, useState } from 'react'

import { BrowserRouter, Routes, Route, useNavigate, useParams } from 'react-router-dom'

import {
  boardApprove,
  boardReject,
  getDashboard,
  getDeveloperInspector,
  getIncidentDetail,
  getInbox,
  getReviewRoom,
  getWorkforce,
  incidentResolve,
  modifyConstraints,
  projectInit,
  type DashboardData,
  type IncidentDetailData,
  type DeveloperInspectorData,
  type InboxData,
  type InboxItem,
  type ReviewRoomData,
  type WorkforceData,
} from './api'
import { EventTicker } from './components/EventTicker'
import { IncidentDrawer } from './components/IncidentDrawer'
import { ReviewRoomDrawer } from './components/ReviewRoomDrawer'
import { WorkforcePanel } from './components/WorkforcePanel'
import { WorkflowRiver } from './components/WorkflowRiver'
import './App.css'

const DEFAULT_INCIDENT_OPERATOR = 'emp_ops_1'

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
  const [snapshotLoading, setSnapshotLoading] = useState(true)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [inspectorLoading, setInspectorLoading] = useState(false)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [projectInitPending, setProjectInitPending] = useState(false)
  const [submittingAction, setSubmittingAction] = useState<string | null>(null)
  const [submittingIncidentAction, setSubmittingIncidentAction] = useState(false)

  const reloadSnapshot = async () => {
    setSnapshotError(null)
    setSnapshotLoading(true)
    try {
      const [nextDashboard, nextInbox, nextWorkforce] = await Promise.all([
        getDashboard(),
        getInbox(),
        getWorkforce(),
      ])
      setDashboard(nextDashboard)
      setInbox(nextInbox)
      setWorkforce(nextWorkforce)
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Failed to load the latest boardroom snapshot.')
    } finally {
      setSnapshotLoading(false)
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
    const eventSource = new EventSource('/api/v1/events/stream')
    const handleInvalidate = () => {
      void refreshSnapshot()
      if (reviewPackId) {
        void refreshReviewRoom(reviewPackId)
      }
      if (incidentId) {
        void refreshIncidentDetail(incidentId)
      }
    }
    eventSource.addEventListener('boardroom-event', handleInvalidate)
    return () => {
      eventSource.close()
    }
  }, [reviewPackId, incidentId])

  const handleOpenReview = (packId: string) => {
    navigate(`/review/${packId}`)
  }

  const handleOpenIncident = (nextIncidentId: string) => {
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
              ) : activeWorkflow != null && dashboard != null ? (
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
            </section>

            <aside className="boardroom-support">
              <WorkforcePanel workforce={workforce} loading={snapshotLoading && workforce == null} />
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
