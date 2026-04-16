import { useEffect, useRef, useState } from 'react'

import type { DeveloperInspectorData, ReviewRoomData } from '../../types/api'
import { isArtifactRef } from '../../utils/artifacts'
import { ProfileSummary } from '../shared/ProfileSummary'
import { Drawer } from '../shared/Drawer'

type ReviewRoomDrawerProps = {
  isOpen: boolean
  loading: boolean
  reviewData: ReviewRoomData | null
  inspectorData: DeveloperInspectorData | null
  inspectorLoading: boolean
  error: string | null
  submittingAction: string | null
  onClose: () => void
  onOpenInspector: () => void
  onOpenArtifact: (artifactRef: string) => void
  onApprove: (input: {
    selectedOptionId: string
    boardComment: string
    elicitationAnswers?: Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
  }) => Promise<void>
  onReject: (input: { boardComment: string; rejectionReasons: string[] }) => Promise<void>
  onModifyConstraints: (input: {
    boardComment: string
    addRules: string[]
    removeRules: string[]
    replaceRules: string[]
    governancePatch?: {
      approval_mode?: string
      audit_mode?: string
    }
    elicitationAnswers?: Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
  }) => Promise<void>
  onAppendAdvisoryTurn?: (input: { sessionId: string; content: string }) => Promise<void>
  onRequestAdvisoryAnalysis?: (input: { sessionId: string }) => Promise<void>
  onApplyAdvisoryPatch?: (input: { sessionId: string; proposalRef: string }) => Promise<void>
}

const EMPTY_ELICITATION_ANSWERS: Array<{
  question_id: string
  selected_option_ids: string[]
  text: string
}> = []

const GOVERNANCE_APPROVAL_MODE_OPTIONS = ['AUTO_CEO', 'EXPERT_GATED'] as const
const GOVERNANCE_AUDIT_MODE_OPTIONS = ['MINIMAL', 'TICKET_TRACE', 'FULL_TIMELINE'] as const

function splitRules(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function formatRiskFieldLabel(field: string) {
  const riskLabelMap: Record<string, string> = {
    user_risk: 'User risk',
    engineering_risk: 'Engineering risk',
    schedule_risk: 'Schedule risk',
    budget_risk: 'Budget risk',
  }
  if (riskLabelMap[field]) {
    return riskLabelMap[field]
  }
  return field
    .split('_')
    .filter(Boolean)
    .join(' ')
}

function formatWeakSignal(signal: string) {
  const signalLabelMap: Record<string, string> = {
    hard_constraints_too_few: 'Too few hard constraints',
    deadline_missing: 'Deadline missing',
    north_star_goal_missing: 'North star goal missing',
  }
  return signalLabelMap[signal] ?? signal.replaceAll('_', ' ')
}

function formatDeltaSummary(deltaSummary: unknown): string | null {
  if (deltaSummary == null) {
    return null
  }
  if (typeof deltaSummary === 'string') {
    const note = deltaSummary.trim()
    return note.length > 0 ? note : null
  }
  if (Array.isArray(deltaSummary)) {
    const notes = deltaSummary.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    return notes.length > 0 ? notes.join('；') : null
  }
  if (typeof deltaSummary === 'object') {
    const payload = deltaSummary as Record<string, unknown>
    if (typeof payload.summary === 'string' && payload.summary.trim().length > 0) {
      return payload.summary.trim()
    }
    const weakSignalsRaw = payload.weak_signals
    if (Array.isArray(weakSignalsRaw)) {
      const weakSignals = weakSignalsRaw.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      if (weakSignals.length > 0) {
        return `Missing information: ${weakSignals.map(formatWeakSignal).join(', ')}`
      }
    }
    const parts = Object.entries(payload)
      .filter(([, value]) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
      .map(([key, value]) => `${formatRiskFieldLabel(key)}: ${String(value)}`)
    return parts.length > 0 ? parts.join('；') : null
  }
  return null
}

function formatRiskSummary(riskSummary: unknown): string | null {
  if (riskSummary == null) {
    return null
  }
  if (Array.isArray(riskSummary)) {
    const notes = riskSummary.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    return notes.length > 0 ? notes.join(' ') : null
  }
  if (typeof riskSummary === 'string') {
    const note = riskSummary.trim()
    return note.length > 0 ? note : null
  }
  if (typeof riskSummary === 'object') {
    const payload = riskSummary as Record<string, unknown>
    if (typeof payload.summary === 'string' && payload.summary.trim().length > 0) {
      return payload.summary.trim()
    }
    const parts = Object.entries(payload)
      .filter(([, value]) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
      .map(([key, value]) => `${formatRiskFieldLabel(key)}: ${String(value)}`)
    return parts.length > 0 ? parts.join(' · ') : null
  }
  return null
}

export function ReviewRoomDrawer({
  isOpen,
  loading,
  reviewData,
  inspectorData,
  inspectorLoading,
  error,
  submittingAction,
  onClose,
  onOpenInspector,
  onOpenArtifact,
  onApprove,
  onReject,
  onModifyConstraints,
  onAppendAdvisoryTurn,
  onRequestAdvisoryAnalysis,
  onApplyAdvisoryPatch,
}: ReviewRoomDrawerProps) {
  const initialSelectedOptionId =
    reviewData?.draft_defaults.selected_option_id ??
    reviewData?.review_pack?.recommendation.recommended_option_id ??
    reviewData?.review_pack?.options[0]?.option_id ??
    ''
  const initialCommentTemplate = reviewData?.draft_defaults.comment_template ?? ''

  const [selectedOptionId, setSelectedOptionId] = useState(initialSelectedOptionId)
  const [approveNote, setApproveNote] = useState(initialCommentTemplate)
  const [rejectNote, setRejectNote] = useState('')
  const [modifyNote, setModifyNote] = useState(initialCommentTemplate)
  const [addRules, setAddRules] = useState('')
  const [removeRules, setRemoveRules] = useState('')
  const [replaceRules, setReplaceRules] = useState('')
  const [patchApprovalMode, setPatchApprovalMode] = useState('')
  const [patchAuditMode, setPatchAuditMode] = useState('')
  const [inspectorVisible, setInspectorVisible] = useState(false)
  const reviewPackIdentity =
    reviewData?.review_pack != null
      ? `${reviewData.review_pack.meta.review_pack_id}:${reviewData.review_pack.meta.review_pack_version}`
      : null
  const initialElicitationAnswers = reviewData?.draft_defaults.elicitation_answers ?? EMPTY_ELICITATION_ANSWERS
  const hydratedDraftIdentityRef = useRef<string | null>(null)
  const [elicitationAnswers, setElicitationAnswers] = useState<
    Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
  >(initialElicitationAnswers)

  const reviewPack = reviewData?.review_pack
  const availableActions = reviewData?.available_actions ?? []
  const employeeChange = reviewPack?.employee_change ?? null
  const advisoryContext = reviewPack?.advisory_context ?? null
  const advisoryFlowStatus = advisoryContext?.change_flow_status ?? advisoryContext?.status ?? null
  const currentGovernanceModes = advisoryContext?.current_governance_modes ?? null
  const questionnaire = reviewPack?.elicitation_questionnaire ?? []
  const isRequirementElicitation = reviewPack?.meta.review_type === 'REQUIREMENT_ELICITATION'
  const deltaSummaryNote = formatDeltaSummary(reviewPack?.delta_summary)
  const riskSummaryNote = formatRiskSummary(reviewPack?.risk_summary)
  const advisoryTurns = advisoryContext?.working_turns ?? []
  const advisoryProposalRef = advisoryContext?.latest_patch_proposal_ref ?? null
  const advisoryAnalysisRunId = advisoryContext?.latest_analysis_run_id ?? null
  const advisoryAnalysisStatus = advisoryContext?.latest_analysis_status ?? null
  const advisoryAnalysisIncidentId = advisoryContext?.latest_analysis_incident_id ?? null
  const advisoryTimelineArchiveVersion = advisoryContext?.timeline_archive_version_int ?? null
  const advisoryTranscriptArchiveArtifactRef = advisoryContext?.latest_transcript_archive_artifact_ref ?? null
  const advisoryTimelineIndexArtifactRef =
    reviewPack?.meta.workflow_id &&
    advisoryContext?.session_id &&
    advisoryTimelineArchiveVersion !== null &&
    advisoryTimelineArchiveVersion !== undefined
      ? `art://board-advisory/${reviewPack.meta.workflow_id}/${advisoryContext.session_id}/timeline-index-v${advisoryTimelineArchiveVersion}.json`
      : null
  const hasAdvisoryArchiveActions =
    advisoryTranscriptArchiveArtifactRef !== null &&
    advisoryTranscriptArchiveArtifactRef !== undefined &&
    advisoryContext?.latest_timeline_index_ref &&
    advisoryTimelineArchiveVersion !== null &&
    advisoryTimelineArchiveVersion !== undefined &&
    advisoryTimelineIndexArtifactRef !== null
  const canEnterChangeFlow = advisoryFlowStatus === 'OPEN'
  const isPendingAnalysis = advisoryFlowStatus === 'PENDING_ANALYSIS'
  const canDraftChangeFlow = advisoryFlowStatus === 'DRAFTING' || advisoryFlowStatus === 'ANALYSIS_REJECTED'
  const canConfirmChangeFlow = advisoryFlowStatus === 'PENDING_BOARD_CONFIRMATION'

  useEffect(() => {
    if (!isOpen) {
      hydratedDraftIdentityRef.current = null
      setInspectorVisible(false)
      return
    }
    if (hydratedDraftIdentityRef.current === reviewPackIdentity && reviewPackIdentity !== null) {
      return
    }

    setSelectedOptionId(initialSelectedOptionId)
    setApproveNote(initialCommentTemplate)
    setRejectNote('')
    setModifyNote(initialCommentTemplate)
    setAddRules('')
    setRemoveRules('')
    setReplaceRules('')
    setPatchApprovalMode('')
    setPatchAuditMode('')
    setElicitationAnswers(initialElicitationAnswers)
    setInspectorVisible(false)
    hydratedDraftIdentityRef.current = reviewPackIdentity
  }, [initialCommentTemplate, initialElicitationAnswers, initialSelectedOptionId, isOpen, reviewPackIdentity])

  function updateElicitationAnswer(
    questionId: string,
    updater: (
      current: {
        question_id: string
        selected_option_ids: string[]
        text: string
      },
    ) => {
      question_id: string
      selected_option_ids: string[]
      text: string
    },
  ) {
    setElicitationAnswers((current) => {
      const existing =
        current.find((item) => item.question_id === questionId) ?? {
          question_id: questionId,
          selected_option_ids: [],
          text: '',
        }
      const next = updater(existing)
      const remaining = current.filter((item) => item.question_id !== questionId)
      return [...remaining, next]
    })
  }

  const normalizedElicitationAnswers = questionnaire.map((question) => {
    const existing = elicitationAnswers.find((item) => item.question_id === question.question_id)
    return {
      question_id: question.question_id,
      selected_option_ids: existing?.selected_option_ids ?? [],
      text: existing?.text ?? '',
    }
  })
  const governancePatch = {
    approval_mode:
      patchApprovalMode && patchApprovalMode !== currentGovernanceModes?.approval_mode
        ? patchApprovalMode
        : undefined,
    audit_mode:
      patchAuditMode && patchAuditMode !== currentGovernanceModes?.audit_mode
        ? patchAuditMode
        : undefined,
  }
  const hasGovernancePatch =
    governancePatch.approval_mode !== undefined || governancePatch.audit_mode !== undefined
  const hasConstraintRules =
    addRules.trim().length > 0 || removeRules.trim().length > 0 || replaceRules.trim().length > 0

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={reviewPack?.subject.title ?? 'Loading review pack'}
      subtitle="Review room"
    >
      {loading ? (
        <div className="review-room-state">Loading the current board review pack...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : reviewPack == null ? (
        <div className="review-room-state">No review pack is available for this item.</div>
      ) : (
        <div className="review-room-content">
          <p className="muted-copy">{reviewPack.trigger.trigger_reason ?? 'Loading the current board review payload.'}</p>

          <section className="review-room-overview">
            <div>
              <span className="eyebrow">Why it stopped here</span>
              <p>{reviewPack.trigger.why_now}</p>
            </div>
            <div>
              <span className="eyebrow">Recommended action</span>
              <p>{reviewPack.recommendation.summary}</p>
            </div>
            <div>
              <span className="eyebrow">Delta summary</span>
              <p>{deltaSummaryNote ?? 'This board gate did not include a delta summary.'}</p>
            </div>
          </section>

          {advisoryContext ? (
            <section className="review-room-overview">
              <div>
                <span className="eyebrow">Advisory session</span>
                <p>{advisoryContext.session_id}</p>
              </div>
              <div>
                <span className="eyebrow">Current governance</span>
                <p>
                  {advisoryContext.current_governance_modes.approval_mode} /{' '}
                  {advisoryContext.current_governance_modes.audit_mode}
                </p>
              </div>
              <div>
                <span className="eyebrow">Graph version</span>
                <p>{advisoryContext.source_version}</p>
              </div>
            </section>
          ) : null}

          {advisoryContext && isPendingAnalysis ? (
            <section className="review-room-action-panel">
              <h3>Analysis status</h3>
              <p className="muted-copy">Analysis is running for the current advisory draft.</p>
              <ul className="review-room-list">
                <li>
                  <strong>Run</strong>
                  <span>{advisoryAnalysisRunId ?? 'Pending run id'}</span>
                </li>
                <li>
                  <strong>Status</strong>
                  <span>{advisoryAnalysisStatus ?? 'PENDING'}</span>
                </li>
              </ul>
            </section>
          ) : null}

          {advisoryContext && hasAdvisoryArchiveActions ? (
            <section className="review-room-overview">
              <div>
                <span className="eyebrow">Archive version</span>
                <p>{advisoryTimelineArchiveVersion}</p>
              </div>
              <div>
                <span className="eyebrow">Transcript archive</span>
                <button
                  type="button"
                  className="ghost-button artifact-ref-button"
                  onClick={() =>
                    advisoryTranscriptArchiveArtifactRef
                      ? onOpenArtifact(advisoryTranscriptArchiveArtifactRef)
                      : undefined
                  }
                >
                  Open transcript archive
                </button>
              </div>
              <div>
                <span className="eyebrow">Timeline index</span>
                <button
                  type="button"
                  className="ghost-button artifact-ref-button"
                  onClick={() =>
                    advisoryTimelineIndexArtifactRef ? onOpenArtifact(advisoryTimelineIndexArtifactRef) : undefined
                  }
                >
                  Open timeline index
                </button>
              </div>
            </section>
          ) : null}

          {reviewPack.options.length > 0 ? (
            <section className="review-room-options">
              <h3>Board options</h3>
              <div className="review-room-option-list">
                {reviewPack.options.map((option) => (
                  <label key={option.option_id} className="review-room-option">
                    <input
                      type="radio"
                      name="review-option"
                      value={option.option_id}
                      checked={selectedOptionId === option.option_id}
                      onChange={() => setSelectedOptionId(option.option_id)}
                    />
                    <div>
                      <strong>{option.label}</strong>
                      <p>{option.summary}</p>
                      {(option.artifact_refs ?? []).map((artifactRef) => (
                        <button
                          key={artifactRef}
                          type="button"
                          className="ghost-button artifact-ref-button"
                          onClick={() => onOpenArtifact(artifactRef)}
                        >
                          Open artifact {option.label}
                        </button>
                      ))}
                    </div>
                  </label>
                ))}
              </div>
            </section>
          ) : null}

          {isRequirementElicitation && questionnaire.length > 0 ? (
            <section className="review-room-options">
              <h3>Requirement elicitation</h3>
              <div className="review-room-option-list">
                {questionnaire.map((question) => {
                  const currentAnswer =
                    normalizedElicitationAnswers.find((item) => item.question_id === question.question_id) ?? null
                  return (
                    <div key={question.question_id} className="review-room-action-panel">
                      <label className="field-label">{question.prompt}</label>
                      {question.response_kind === 'TEXT' ? (
                        <textarea
                          aria-label={question.prompt}
                          rows={3}
                          value={currentAnswer?.text ?? ''}
                          onChange={(event) =>
                            updateElicitationAnswer(question.question_id, (existing) => ({
                              ...existing,
                              text: event.target.value,
                            }))
                          }
                        />
                      ) : (
                        <div className="review-room-option-list">
                          {question.options.map((option) => {
                            const selectedOptionIds = currentAnswer?.selected_option_ids ?? []
                            const checked = selectedOptionIds.includes(option.option_id)
                            return (
                              <label key={option.option_id} className="review-room-option">
                                <input
                                  type={question.response_kind === 'SINGLE_SELECT' ? 'radio' : 'checkbox'}
                                  name={question.question_id}
                                  aria-label={option.label}
                                  checked={checked}
                                  onChange={() =>
                                    updateElicitationAnswer(question.question_id, (existing) => ({
                                      ...existing,
                                      selected_option_ids:
                                        question.response_kind === 'SINGLE_SELECT'
                                          ? [option.option_id]
                                          : checked
                                            ? existing.selected_option_ids.filter((item) => item !== option.option_id)
                                            : [...existing.selected_option_ids, option.option_id],
                                    }))
                                  }
                                />
                                <div>
                                  <strong>{option.label}</strong>
                                  {option.summary ? <p>{option.summary}</p> : null}
                                </div>
                              </label>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          ) : null}

          <section className="review-room-columns">
            <div className="review-room-column">
              <h3>Evidence</h3>
              <ul className="review-room-list">
                {(reviewPack.evidence_summary ?? []).map((item) => {
                  const sourceRef = item.source_ref
                  const artifactSourceRef = isArtifactRef(sourceRef) ? sourceRef : null

                  return (
                    <li key={item.evidence_id}>
                      <strong>{item.label}</strong>
                      <span>{item.summary}</span>
                      {sourceRef ? (
                      <>
                        <span>Source ref</span>
                        <span>{sourceRef}</span>
                        {artifactSourceRef ? (
                          <button
                            type="button"
                            className="ghost-button artifact-ref-button"
                          onClick={() => onOpenArtifact(artifactSourceRef)}
                        >
                            Open evidence {item.label}
                          </button>
                        ) : null}
                      </>
                    ) : null}
                    </li>
                  )
                })}
                {(reviewPack.evidence_summary ?? []).length === 0 ? (
                  <li>
                    <strong>Evidence summary</strong>
                    <span>This review pack did not include summary evidence cards.</span>
                  </li>
                ) : null}
              </ul>
            </div>
            <div className="review-room-column">
              <h3>Governance notes</h3>
              <ul className="review-room-list">
                <li>
                  <strong>Maker-checker</strong>
                  <span>{reviewPack.maker_checker_summary?.summary ?? 'No maker-checker summary attached.'}</span>
                </li>
                <li>
                  <strong>Budget impact</strong>
                  <span>{reviewPack.budget_impact?.summary ?? 'No budget exception is needed right now.'}</span>
                </li>
                <li>
                  <strong>Risk</strong>
                  <span>{riskSummaryNote ?? 'This review did not include extra risk notes.'}</span>
                </li>
              </ul>
            </div>
          </section>

          {employeeChange != null ? (
            <section className="review-room-columns">
              {employeeChange.skill_profile != null &&
              employeeChange.personality_profile != null &&
              employeeChange.aesthetic_profile != null ? (
                <div className="review-room-column">
                  <h3>Candidate profile</h3>
                  <ProfileSummary
                    label={employeeChange.employee_id ?? 'Candidate'}
                    skillProfile={employeeChange.skill_profile}
                    personalityProfile={employeeChange.personality_profile}
                    aestheticProfile={employeeChange.aesthetic_profile}
                  />
                </div>
              ) : null}
              {employeeChange.replacement_skill_profile != null &&
              employeeChange.replacement_personality_profile != null &&
              employeeChange.replacement_aesthetic_profile != null ? (
                <div className="review-room-column">
                  <h3>Replacement profile</h3>
                  <p className="muted-copy">
                    Replace {employeeChange.employee_id ?? 'the current employee'} with{' '}
                    {employeeChange.replacement_employee_id ?? 'the replacement candidate'}.
                  </p>
                  <ProfileSummary
                    label={employeeChange.replacement_employee_id ?? 'Replacement candidate'}
                    skillProfile={employeeChange.replacement_skill_profile}
                    personalityProfile={employeeChange.replacement_personality_profile}
                    aestheticProfile={employeeChange.replacement_aesthetic_profile}
                  />
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="review-room-actions">
            <div className="review-room-action-grid">
              <div className="review-room-action-panel">
                <label className="field-label" htmlFor="approve-note">
                  Board comment
                </label>
                <textarea
                  id="approve-note"
                  value={approveNote}
                  onChange={(event) => setApproveNote(event.target.value)}
                  rows={3}
                />
                <button
                  type="button"
                  className="primary-button"
                  disabled={
                    submittingAction !== null ||
                    selectedOptionId.length === 0 ||
                    !availableActions.includes('APPROVE')
                  }
                  onClick={() =>
                    void onApprove({
                      selectedOptionId,
                      boardComment: approveNote.trim() || 'Approve the recommended option.',
                      elicitationAnswers: isRequirementElicitation ? normalizedElicitationAnswers : undefined,
                    })
                  }
                >
                  {submittingAction === 'APPROVE' ? 'Submitting…' : 'Approve and continue'}
                </button>
              </div>

              <div className="review-room-action-panel">
                <label className="field-label" htmlFor="reject-note">
                  Reject comment
                </label>
                <textarea
                  id="reject-note"
                  value={rejectNote}
                  onChange={(event) => setRejectNote(event.target.value)}
                  rows={3}
                />
                <button
                  type="button"
                  className="danger-button"
                  disabled={submittingAction !== null || rejectNote.trim().length === 0}
                  onClick={() =>
                    void onReject({
                      boardComment: rejectNote.trim(),
                      rejectionReasons: [rejectNote.trim()],
                    })
                  }
                >
                  {submittingAction === 'REJECT' ? 'Submitting…' : 'Reject and request rework'}
                </button>
              </div>
            </div>

            <div className="review-room-action-panel review-room-constraint-panel">
              <h3>Change flow</h3>
              {canEnterChangeFlow || !advisoryContext ? (
                <>
                  <label className="field-label" htmlFor="modify-note">
                    Constraint comment
                  </label>
                  <textarea
                    id="modify-note"
                    value={modifyNote}
                    onChange={(event) => setModifyNote(event.target.value)}
                    rows={3}
                  />
                  <div className="constraint-grid">
                    <label>
                      <span className="field-label">Add rules</span>
                      <textarea
                        aria-label="Add rules"
                        value={addRules}
                        onChange={(event) => setAddRules(event.target.value)}
                        rows={3}
                      />
                    </label>
                    <label>
                      <span className="field-label">Remove rules</span>
                      <textarea
                        aria-label="Remove rules"
                        value={removeRules}
                        onChange={(event) => setRemoveRules(event.target.value)}
                        rows={3}
                      />
                    </label>
                    <label>
                      <span className="field-label">Replace rules</span>
                      <textarea
                        aria-label="Replace rules"
                        value={replaceRules}
                        onChange={(event) => setReplaceRules(event.target.value)}
                        rows={3}
                      />
                    </label>
                  </div>
                  {advisoryContext?.supports_governance_patch ? (
                    <div className="constraint-grid">
                      <label>
                        <span className="field-label">Approval mode</span>
                        <select
                          aria-label="Approval mode"
                          value={patchApprovalMode}
                          onChange={(event) => setPatchApprovalMode(event.target.value)}
                        >
                          <option value="">Keep current ({currentGovernanceModes?.approval_mode ?? 'unknown'})</option>
                          {GOVERNANCE_APPROVAL_MODE_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span className="field-label">Audit mode</span>
                        <select
                          aria-label="Audit mode"
                          value={patchAuditMode}
                          onChange={(event) => setPatchAuditMode(event.target.value)}
                        >
                          <option value="">Keep current ({currentGovernanceModes?.audit_mode ?? 'unknown'})</option>
                          {GOVERNANCE_AUDIT_MODE_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  ) : null}
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={submittingAction !== null || (!hasConstraintRules && !hasGovernancePatch && modifyNote.trim().length === 0)}
                    onClick={() =>
                      void onModifyConstraints({
                        boardComment: modifyNote.trim() || 'Enter the advisory change flow with these constraints.',
                        addRules: splitRules(addRules),
                        removeRules: splitRules(removeRules),
                        replaceRules: splitRules(replaceRules),
                        governancePatch: hasGovernancePatch ? governancePatch : undefined,
                        elicitationAnswers: isRequirementElicitation ? normalizedElicitationAnswers : undefined,
                      })
                    }
                  >
                    {submittingAction === 'MODIFY_CONSTRAINTS' ? 'Submitting…' : 'Enter change flow'}
                  </button>
                </>
              ) : null}

              {canDraftChangeFlow ? (
                <>
                  <p className="muted-copy">Draft the board intent here, then request an evaluated patch proposal.</p>
                  {advisoryContext?.latest_analysis_error ? (
                    <p className="review-room-state review-room-error">{advisoryContext.latest_analysis_error}</p>
                  ) : null}
                  {advisoryAnalysisIncidentId ? (
                    <p className="muted-copy">Latest analysis incident: {advisoryAnalysisIncidentId}</p>
                  ) : null}
                  {advisoryTurns.length > 0 ? (
                    <ul className="review-room-list">
                      {advisoryTurns.map((turn) => (
                        <li key={turn.turn_id}>
                          <strong>{turn.actor_type}</strong>
                          <span>{turn.content}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <label className="field-label" htmlFor="advisory-draft-note">
                    Draft note
                  </label>
                  <textarea
                    id="advisory-draft-note"
                    value={modifyNote}
                    onChange={(event) => setModifyNote(event.target.value)}
                    rows={3}
                  />
                  <div className="constraint-grid">
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={
                        submittingAction !== null ||
                        modifyNote.trim().length === 0 ||
                        !advisoryContext ||
                        !onAppendAdvisoryTurn
                      }
                      onClick={() =>
                        advisoryContext && onAppendAdvisoryTurn
                          ? void onAppendAdvisoryTurn({
                              sessionId: advisoryContext.session_id,
                              content: modifyNote.trim(),
                            })
                          : undefined
                      }
                    >
                      {submittingAction === 'ADVISORY_APPEND' ? 'Submitting…' : 'Add draft note'}
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={submittingAction !== null || !advisoryContext || !onRequestAdvisoryAnalysis}
                      onClick={() =>
                        advisoryContext && onRequestAdvisoryAnalysis
                          ? void onRequestAdvisoryAnalysis({ sessionId: advisoryContext.session_id })
                          : undefined
                      }
                    >
                      {submittingAction === 'ADVISORY_ANALYSIS' ? 'Submitting…' : 'Request analysis'}
                    </button>
                  </div>
                </>
              ) : null}

              {canConfirmChangeFlow ? (
                <>
                  <p className="muted-copy">Review the proposed change. The board only sees the summary, trade-offs, and risk alerts here.</p>
                  <ul className="review-room-list">
                    <li>
                      <strong>Proposal summary</strong>
                      <span>{advisoryContext?.proposal_summary ?? 'No proposal summary is available yet.'}</span>
                    </li>
                    <li>
                      <strong>Pros</strong>
                      <span>{(advisoryContext?.pros ?? []).join(' · ') || 'No explicit pros were attached.'}</span>
                    </li>
                    <li>
                      <strong>Cons</strong>
                      <span>{(advisoryContext?.cons ?? []).join(' · ') || 'No explicit cons were attached.'}</span>
                    </li>
                    <li>
                      <strong>Risk alerts</strong>
                      <span>{(advisoryContext?.risk_alerts ?? []).join(' · ') || 'No additional risk alerts.'}</span>
                    </li>
                    <li>
                      <strong>Impact summary</strong>
                      <span>{advisoryContext?.impact_summary ?? 'No impact summary is available.'}</span>
                    </li>
                  </ul>
                  <button
                    type="button"
                    className="primary-button"
                    disabled={
                      submittingAction !== null ||
                      !advisoryContext ||
                      !advisoryProposalRef ||
                      !onApplyAdvisoryPatch
                    }
                    onClick={() =>
                      advisoryContext && advisoryProposalRef && onApplyAdvisoryPatch
                        ? void onApplyAdvisoryPatch({
                            sessionId: advisoryContext.session_id,
                            proposalRef: advisoryProposalRef,
                          })
                        : undefined
                    }
                  >
                    {submittingAction === 'ADVISORY_APPLY' ? 'Submitting…' : 'Approve runtime patch'}
                  </button>
                </>
              ) : null}
            </div>
          </section>

          <section className="review-room-inspector">
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                setInspectorVisible((value) => !value)
                if (!inspectorVisible) {
                  onOpenInspector()
                }
              }}
            >
              {inspectorVisible ? 'Hide developer inspector' : 'Developer inspector'}
            </button>
            {inspectorVisible ? (
              <div className="review-room-inspector-panel">
                {inspectorLoading ? (
                  <p>Loading compile details…</p>
                ) : inspectorData ? (
                  <>
                    <p>
                      Availability: <strong>{inspectorData.availability}</strong>
                    </p>
                    <p>
                      Context budget: <strong>{inspectorData.compile_summary?.used_budget_tokens ?? 0}</strong> /{' '}
                      {inspectorData.compile_summary?.total_budget_tokens ?? 0}
                    </p>
                    <p>
                      Rendered messages: <strong>{inspectorData.render_summary?.data_message_count ?? 0}</strong>
                    </p>
                  </>
                ) : (
                  <p>No developer inspector payload is available for this review pack.</p>
                )}
              </div>
            ) : null}
          </section>
        </div>
      )}
    </Drawer>
  )
}
