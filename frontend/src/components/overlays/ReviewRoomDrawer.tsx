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
    user_risk: '用户风险',
    engineering_risk: '工程风险',
    schedule_risk: '进度风险',
    budget_risk: '预算风险',
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
    hard_constraints_too_few: '硬约束条目过少',
    deadline_missing: '缺少截止时间',
    north_star_goal_missing: '缺少北极星目标',
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
        return `待补充信息：${weakSignals.map(formatWeakSignal).join('、')}`
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
      title={reviewPack?.subject.title ?? '评审包加载中'}
      subtitle="评审室"
    >
      {loading ? (
        <div className="review-room-state">正在加载当前董事会评审包...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : reviewPack == null ? (
        <div className="review-room-state">当前条目暂无可用评审包。</div>
      ) : (
        <div className="review-room-content">
          <p className="muted-copy">{reviewPack.trigger.trigger_reason ?? '正在拉取当前董事会评审负载。'}</p>

          <section className="review-room-overview">
            <div>
              <span className="eyebrow">当前为何停在这里</span>
              <p>{reviewPack.trigger.why_now}</p>
            </div>
            <div>
              <span className="eyebrow">建议动作</span>
              <p>{reviewPack.recommendation.summary}</p>
            </div>
            <div>
              <span className="eyebrow">变化摘要</span>
              <p>{deltaSummaryNote ?? '该董事会闸门未附带变化摘要。'}</p>
            </div>
          </section>

          {reviewPack.options.length > 0 ? (
            <section className="review-room-options">
              <h3>董事会可选方案</h3>
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
                          打开产物 {option.label}
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
              <h3>需求澄清问卷</h3>
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
              <h3>证据</h3>
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
                        <span>来源引用</span>
                        <span>{sourceRef}</span>
                        {artifactSourceRef ? (
                          <button
                            type="button"
                            className="ghost-button artifact-ref-button"
                            onClick={() => onOpenArtifact(artifactSourceRef)}
                          >
                            打开证据 {item.label}
                          </button>
                        ) : null}
                      </>
                    ) : null}
                    </li>
                  )
                })}
                {(reviewPack.evidence_summary ?? []).length === 0 ? (
                  <li>
                    <strong>证据摘要</strong>
                    <span>该评审包未附带摘要证据卡片。</span>
                  </li>
                ) : null}
              </ul>
            </div>
            <div className="review-room-column">
              <h3>治理备注</h3>
              <ul className="review-room-list">
                <li>
                  <strong>制作-复核</strong>
                  <span>{reviewPack.maker_checker_summary?.summary ?? '未附带制作-复核摘要。'}</span>
                </li>
                <li>
                  <strong>预算影响</strong>
                  <span>{reviewPack.budget_impact?.summary ?? '当前无需预算例外。'}</span>
                </li>
                <li>
                  <strong>风险</strong>
                  <span>{riskSummaryNote ?? '该评审未附带额外风险备注。'}</span>
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
                  <h3>候选画像</h3>
                  <ProfileSummary
                    label={employeeChange.employee_id ?? '候选人'}
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
                  <h3>替换画像</h3>
                  <p className="muted-copy">
                    将 {employeeChange.employee_id ?? '当前员工'} 替换为{' '}
                    {employeeChange.replacement_employee_id ?? '替换候选人'}。
                  </p>
                  <ProfileSummary
                    label={employeeChange.replacement_employee_id ?? '替换人选'}
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
                  董事会备注
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
                      boardComment: approveNote.trim() || '同意按推荐方案继续推进。',
                      elicitationAnswers: isRequirementElicitation ? normalizedElicitationAnswers : undefined,
                    })
                  }
                >
                  {submittingAction === 'APPROVE' ? '提交中…' : '批准并继续'}
                </button>
              </div>

              <div className="review-room-action-panel">
                <label className="field-label" htmlFor="reject-note">
                  驳回备注
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
                  {submittingAction === 'REJECT' ? '提交中…' : '驳回并要求返工'}
                </button>
              </div>
            </div>

            <div className="review-room-action-panel review-room-constraint-panel">
              <h3>修改约束</h3>
              <label className="field-label" htmlFor="modify-note">
                约束备注
              </label>
              <textarea
                id="modify-note"
                value={modifyNote}
                onChange={(event) => setModifyNote(event.target.value)}
                rows={3}
              />
              <div className="constraint-grid">
                <label>
                  <span className="field-label">新增规则</span>
                  <textarea
                    aria-label="新增规则"
                    value={addRules}
                    onChange={(event) => setAddRules(event.target.value)}
                    rows={3}
                  />
                </label>
                <label>
                  <span className="field-label">移除规则</span>
                  <textarea
                    aria-label="移除规则"
                    value={removeRules}
                    onChange={(event) => setRemoveRules(event.target.value)}
                    rows={3}
                  />
                </label>
                <label>
                  <span className="field-label">替换规则</span>
                  <textarea
                    aria-label="替换规则"
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
                    boardComment: modifyNote.trim() || '应用更新后的董事会约束。',
                    addRules: splitRules(addRules),
                    removeRules: splitRules(removeRules),
                    replaceRules: splitRules(replaceRules),
                    elicitationAnswers: isRequirementElicitation ? normalizedElicitationAnswers : undefined,
                  })
                }
              >
                {submittingAction === 'MODIFY_CONSTRAINTS' ? '提交中…' : '提交约束修改'}
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
              {inspectorVisible ? '收起开发者检查器' : '开发者检查器'}
            </button>
            {inspectorVisible ? (
              <div className="review-room-inspector-panel">
                {inspectorLoading ? (
                  <p>正在加载编译细节…</p>
                ) : inspectorData ? (
                  <>
                    <p>
                      可用性：<strong>{inspectorData.availability}</strong>
                    </p>
                    <p>
                      上下文预算：<strong>{inspectorData.compile_summary?.used_budget_tokens ?? 0}</strong> /{' '}
                      {inspectorData.compile_summary?.total_budget_tokens ?? 0}
                    </p>
                    <p>
                      渲染消息数：<strong>{inspectorData.render_summary?.data_message_count ?? 0}</strong>
                    </p>
                  </>
                ) : (
                  <p>该评审包暂无开发者检查器负载。</p>
                )}
              </div>
            ) : null}
          </section>
        </div>
      )}
    </Drawer>
  )
}
