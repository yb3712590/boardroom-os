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
    elicitationAnswers?: Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
  }) => Promise<void>
}

const EMPTY_ELICITATION_ANSWERS: Array<{
  question_id: string
  selected_option_ids: string[]
  text: string
}> = []

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
  const questionnaire = reviewPack?.elicitation_questionnaire ?? []
  const isRequirementElicitation = reviewPack?.meta.review_type === 'REQUIREMENT_ELICITATION'
  const deltaSummaryNote = formatDeltaSummary(reviewPack?.delta_summary)
  const riskSummaryNote = formatRiskSummary(reviewPack?.risk_summary)

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
              <h3>Modify constraints</h3>
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
              <button
                type="button"
                className="secondary-button"
                disabled={submittingAction !== null || addRules.trim().length === 0}
                onClick={() =>
                  void onModifyConstraints({
                    boardComment: modifyNote.trim() || 'Apply the updated board constraints.',
                    addRules: splitRules(addRules),
                    removeRules: splitRules(removeRules),
                    replaceRules: splitRules(replaceRules),
                    elicitationAnswers: isRequirementElicitation ? normalizedElicitationAnswers : undefined,
                  })
                }
              >
                {submittingAction === 'MODIFY_CONSTRAINTS' ? 'Submitting…' : 'Submit constraint changes'}
              </button>
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
