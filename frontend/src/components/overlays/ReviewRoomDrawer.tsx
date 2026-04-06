import { useState } from 'react'

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
  onApprove: (input: { selectedOptionId: string; boardComment: string }) => Promise<void>
  onReject: (input: { boardComment: string; rejectionReasons: string[] }) => Promise<void>
  onModifyConstraints: (input: {
    boardComment: string
    addRules: string[]
    removeRules: string[]
    replaceRules: string[]
  }) => Promise<void>
}

function splitRules(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
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

  const reviewPack = reviewData?.review_pack
  const availableActions = reviewData?.available_actions ?? []
  const employeeChange = reviewPack?.employee_change ?? null

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={reviewPack?.subject.title ?? 'Loading review pack'}
      subtitle="Review Room"
    >
      {loading ? (
        <div className="review-room-state">Loading the current board review pack...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : reviewPack == null ? (
        <div className="review-room-state">No review pack is available for this item.</div>
      ) : (
        <div className="review-room-content">
          <p className="muted-copy">{reviewPack.trigger.trigger_reason ?? 'Pulling the current board review payload.'}</p>

          <section className="review-room-overview">
            <div>
              <span className="eyebrow">Why now</span>
              <p>{reviewPack.trigger.why_now}</p>
            </div>
            <div>
              <span className="eyebrow">Recommendation</span>
              <p>{reviewPack.recommendation.summary}</p>
            </div>
            <div>
              <span className="eyebrow">Delta</span>
              <p>{reviewPack.delta_summary ?? 'No delta summary was attached to this board gate.'}</p>
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
                    <span>No compact evidence cards were attached to this review pack.</span>
                  </li>
                ) : null}
              </ul>
            </div>
            <div className="review-room-column">
              <h3>Governance notes</h3>
              <ul className="review-room-list">
                <li>
                  <strong>Maker-checker</strong>
                  <span>{reviewPack.maker_checker_summary?.summary ?? 'No maker-checker summary was attached.'}</span>
                </li>
                <li>
                  <strong>Budget impact</strong>
                  <span>{reviewPack.budget_impact?.summary ?? 'No budget exception required.'}</span>
                </li>
                <li>
                  <strong>Risks</strong>
                  <span>{reviewPack.risk_summary?.join(' ') ?? 'No extra risk note was attached to this review.'}</span>
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
                    Replace {employeeChange.employee_id ?? 'current worker'} with{' '}
                    {employeeChange.replacement_employee_id ?? 'replacement candidate'}.
                  </p>
                  <ProfileSummary
                    label={employeeChange.replacement_employee_id ?? 'Replacement'}
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
                  Board note
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
                    })
                  }
                >
                  {submittingAction === 'APPROVE' ? 'Submitting…' : 'Approve and continue'}
                </button>
              </div>

              <div className="review-room-action-panel">
                <label className="field-label" htmlFor="reject-note">
                  Reject note
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
                Constraint note
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
                  })
                }
              >
                {submittingAction === 'MODIFY_CONSTRAINTS' ? 'Submitting…' : 'Modify constraints'}
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
                  <p>Loading compiler detail…</p>
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
                      Render messages: <strong>{inspectorData.render_summary?.data_message_count ?? 0}</strong>
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
