import { useEffect, useRef, useState } from 'react'

import type { IncidentDetailData } from '../../types/api'
import { Drawer } from '../shared/Drawer'

type IncidentDrawerProps = {
  isOpen: boolean
  loading: boolean
  incidentData: IncidentDetailData | null
  error: string | null
  submitting: boolean
  onClose: () => void
  onResolve: (input: { resolutionSummary: string; followupAction: string }) => Promise<void>
}

function formatIncidentLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function describeIncident(incidentType: string) {
  switch (incidentType) {
    case 'RUNTIME_TIMEOUT_ESCALATION':
      return '执行连续超时，熔断器已开启。'
    case 'REPEATED_FAILURE_ESCALATION':
      return '同一节点以相同指纹连续失败。'
    case 'PROVIDER_EXECUTION_PAUSED':
      return '供应商执行已暂停，下游流程被阻塞。'
    case 'STAFFING_CONTAINMENT':
      return '人员变更隔离中断了当前执行链路。'
    default:
      return '出现治理故障，需要人工处理。'
  }
}

function formatPayloadValue(value: unknown) {
  if (value == null) {
    return '空'
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return JSON.stringify(value)
}

function readPayloadString(payload: Record<string, unknown>, key: string) {
  const value = payload[key]
  return typeof value === 'string' ? value : ''
}

function readPayloadNumber(payload: Record<string, unknown>, key: string) {
  const value = payload[key]
  return typeof value === 'number' ? value : null
}

function buildIncidentInterpretation(incident: IncidentDetailData['incident']): string | null {
  const payload = incident.payload ?? {}
  if (incident.incident_type !== 'REPEATED_FAILURE_ESCALATION') {
    return null
  }

  const latestFailureKind = readPayloadString(payload, 'latest_failure_kind')
  const latestFailureMessage = readPayloadString(payload, 'latest_failure_message')
  const streakCount = readPayloadNumber(payload, 'failure_streak_count')

  if (
    latestFailureKind === 'RUNTIME_INPUT_ERROR' &&
    latestFailureMessage.includes('Mandatory explicit source') &&
    latestFailureMessage.includes('cannot fit within the remaining token budget')
  ) {
    const sourceMatch = latestFailureMessage.match(/Mandatory explicit source (.+?) cannot fit within/)
    const budgetMatch = latestFailureMessage.match(/remaining token budget \((\d+)\)/)
    const sourceRef = sourceMatch?.[1] ?? '关键输入产物'
    const remainingBudget = budgetMatch?.[1]
    const budgetHint = remainingBudget ? `（剩余预算 ${remainingBudget} tokens）` : ''
    const streakHint = streakCount != null ? `，并已连续失败 ${streakCount} 次` : ''
    return `这次不是供应商故障，而是输入预算超限：必需输入 ${sourceRef} 在当前上下文里放不下${budgetHint}${streakHint}，系统触发了重复失败熔断。`
  }

  return null
}

export function IncidentDrawer({
  isOpen,
  loading,
  incidentData,
  error,
  submitting,
  onClose,
  onResolve,
}: IncidentDrawerProps) {
  const incidentIdentity = incidentData?.incident.incident_id ?? null
  const initialFollowupAction =
    incidentData?.recommended_followup_action ?? incidentData?.available_followup_actions[0] ?? ''
  const [followupAction, setFollowupAction] = useState(initialFollowupAction)
  const [resolutionSummary, setResolutionSummary] = useState('')
  const hydratedIncidentRef = useRef<string | null>(null)

  const incident = incidentData?.incident
  const incidentInterpretation = incident != null ? buildIncidentInterpretation(incident) : null

  useEffect(() => {
    if (!isOpen) {
      hydratedIncidentRef.current = null
      setFollowupAction('')
      setResolutionSummary('')
      return
    }
    if (incidentIdentity == null) {
      return
    }
    if (hydratedIncidentRef.current === incidentIdentity) {
      return
    }
    setFollowupAction(initialFollowupAction)
    setResolutionSummary('')
    hydratedIncidentRef.current = incidentIdentity
  }, [incidentIdentity, initialFollowupAction, isOpen])

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={incident ? formatIncidentLabel(incident.incident_type) : '故障加载中'}
      subtitle="故障处理"
    >
      <p className="muted-copy">
        {incident ? describeIncident(incident.incident_type) : '正在拉取当前故障负载。'}
      </p>

      {loading ? (
        <div className="review-room-state">正在加载故障详情...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : incident == null ? (
        <div className="review-room-state">当前条目暂无故障详情。</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">状态</span>
              <p>{incident.status}</p>
            </div>
            <div>
              <span className="eyebrow">熔断器</span>
              <p>{incident.circuit_breaker_state ?? '未知'}</p>
            </div>
            <div>
              <span className="eyebrow">严重级别</span>
              <p>{incident.severity ?? '未知'}</p>
            </div>
          </section>

          <section className="review-room-columns">
            <div className="review-room-column">
              <h3>故障范围</h3>
              <ul className="review-room-list">
                <li>
                  <strong>工作流</strong>
                  <span>{incident.workflow_id}</span>
                </li>
                <li>
                  <strong>节点</strong>
                  <span>{incident.node_id ?? '未关联节点'}</span>
                </li>
                <li>
                  <strong>工单</strong>
                  <span>{incident.ticket_id ?? '未关联工单'}</span>
                </li>
                <li>
                  <strong>供应商</strong>
                  <span>{incident.provider_id ?? '未关联供应商'}</span>
                </li>
              </ul>
            </div>
            <div className="review-room-column">
              <h3>故障负载</h3>
              <ul className="review-room-list">
                {Object.entries(incident.payload).map(([key, value]) => (
                  <li key={key}>
                    <strong>{formatIncidentLabel(key)}</strong>
                    <span>{formatPayloadValue(value)}</span>
                  </li>
                ))}
                {Object.keys(incident.payload).length === 0 ? (
                  <li>
                    <strong>负载</strong>
                    <span>未附带结构化负载。</span>
                  </li>
                ) : null}
              </ul>
            </div>
          </section>

          {incidentInterpretation ? (
            <section className="review-room-action-panel incident-action-panel">
              <h3>故障解读</h3>
              <p className="muted-copy">{incidentInterpretation}</p>
            </section>
          ) : null}

          <section className="review-room-action-panel incident-action-panel">
            <h3>恢复动作</h3>
            <label>
              <span className="field-label">后续动作</span>
              <select
                value={followupAction}
                onChange={(event) => setFollowupAction(event.target.value)}
                disabled={submitting}
              >
                {incidentData?.available_followup_actions.map((action) => (
                  <option key={action} value={action}>
                    {formatIncidentLabel(action)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">恢复说明</span>
              <textarea
                aria-label="恢复说明"
                value={resolutionSummary}
                onChange={(event) => setResolutionSummary(event.target.value)}
                rows={4}
              />
            </label>
            <button
              type="button"
              className="secondary-button"
              disabled={submitting || followupAction.length === 0 || resolutionSummary.trim().length === 0}
              onClick={() =>
                void onResolve({
                  resolutionSummary: resolutionSummary.trim(),
                  followupAction,
                })
              }
            >
              {submitting ? '提交中...' : '执行恢复动作'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
