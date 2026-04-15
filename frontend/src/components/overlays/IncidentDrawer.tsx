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
    case 'TICKET_GRAPH_UNAVAILABLE':
      return 'The ticket graph snapshot could not be rebuilt, so controller recovery is blocked until the graph compiles again.'
    case 'GRAPH_HEALTH_CRITICAL':
      return 'Graph health reached a critical state, so execution stays fail-closed until the CEO reruns against the latest graph health snapshot.'
    case 'REQUIRED_HOOK_GATE_BLOCKED':
      return 'Required hook receipts are missing, so the node stays fail-closed until recovery replays the missing hooks from persisted terminal truth.'
    case 'RUNTIME_TIMEOUT_ESCALATION':
      return 'Execution timed out repeatedly and the circuit breaker is now open.'
    case 'REPEATED_FAILURE_ESCALATION':
      return 'The same node failed repeatedly with the same fingerprint.'
    case 'PROVIDER_EXECUTION_PAUSED':
      return 'Provider execution is paused and downstream work is blocked.'
    case 'STAFFING_CONTAINMENT':
      return 'Staffing containment interrupted the current execution path.'
    default:
      return 'A governance incident occurred and needs manual attention.'
  }
}

function formatPayloadValue(value: unknown) {
  if (value == null) {
    return 'Empty'
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
    const sourceRef = sourceMatch?.[1] ?? 'the required input artifact'
    const remainingBudget = budgetMatch?.[1]
    const budgetHint = remainingBudget ? ` (remaining budget ${remainingBudget} tokens)` : ''
    const streakHint = streakCount != null ? ` after ${streakCount} repeated failures` : ''
    return `This is not a provider outage. The required input ${sourceRef} could not fit into the current context${budgetHint}${streakHint}, so the system tripped the repeated-failure circuit breaker.`
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
      title={incident ? formatIncidentLabel(incident.incident_type) : 'Loading incident'}
      subtitle="Incident response"
    >
      <p className="muted-copy">
        {incident ? describeIncident(incident.incident_type) : 'Loading the current incident payload.'}
      </p>

      {loading ? (
        <div className="review-room-state">Loading incident details...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : incident == null ? (
        <div className="review-room-state">No incident details are available for this item.</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">Status</span>
              <p>{incident.status}</p>
            </div>
            <div>
              <span className="eyebrow">Circuit breaker</span>
              <p>{incident.circuit_breaker_state ?? 'Unknown'}</p>
            </div>
            <div>
              <span className="eyebrow">Severity</span>
              <p>{incident.severity ?? 'Unknown'}</p>
            </div>
          </section>

          <section className="review-room-columns">
            <div className="review-room-column">
              <h3>Incident scope</h3>
              <ul className="review-room-list">
                <li>
                  <strong>Workflow</strong>
                  <span>{incident.workflow_id}</span>
                </li>
                <li>
                  <strong>Node</strong>
                  <span>{incident.node_id ?? 'No linked node'}</span>
                </li>
                <li>
                  <strong>Ticket</strong>
                  <span>{incident.ticket_id ?? 'No linked ticket'}</span>
                </li>
                <li>
                  <strong>Provider</strong>
                  <span>{incident.provider_id ?? 'No linked provider'}</span>
                </li>
              </ul>
            </div>
            <div className="review-room-column">
              <h3>Incident payload</h3>
              <ul className="review-room-list">
                {Object.entries(incident.payload).map(([key, value]) => (
                  <li key={key}>
                    <strong>{formatIncidentLabel(key)}</strong>
                    <span>{formatPayloadValue(value)}</span>
                  </li>
                ))}
                {Object.keys(incident.payload).length === 0 ? (
                  <li>
                    <strong>Payload</strong>
                    <span>No structured payload was attached.</span>
                  </li>
                ) : null}
              </ul>
            </div>
          </section>

          {incidentInterpretation ? (
            <section className="review-room-action-panel incident-action-panel">
              <h3>Interpretation</h3>
              <p className="muted-copy">{incidentInterpretation}</p>
            </section>
          ) : null}

          <section className="review-room-action-panel incident-action-panel">
            <h3>Recovery action</h3>
            <label>
              <span className="field-label">Follow-up action</span>
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
              <span className="field-label">Resolution summary</span>
              <textarea
                aria-label="Resolution summary"
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
              {submitting ? 'Submitting...' : 'Run recovery action'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
