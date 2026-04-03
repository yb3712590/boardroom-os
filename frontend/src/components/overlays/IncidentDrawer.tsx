import { useState } from 'react'

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
      return 'Execution timed out repeatedly and the breaker is now open.'
    case 'REPEATED_FAILURE_ESCALATION':
      return 'The same node failed repeatedly with the same fingerprint.'
    case 'PROVIDER_EXECUTION_PAUSED':
      return 'Provider execution is paused and downstream work is blocked.'
    case 'STAFFING_CONTAINMENT':
      return 'Employee change containment interrupted the current execution path.'
    default:
      return 'A governance incident requires operator attention.'
  }
}

function formatPayloadValue(value: unknown) {
  if (value == null) {
    return 'null'
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return JSON.stringify(value)
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
  const [followupAction, setFollowupAction] = useState(
    incidentData?.recommended_followup_action ?? incidentData?.available_followup_actions[0] ?? '',
  )
  const [resolutionSummary, setResolutionSummary] = useState('')

  const incident = incidentData?.incident

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={incident ? formatIncidentLabel(incident.incident_type) : 'Loading incident'}
      subtitle="Incident"
    >
      <p className="muted-copy">
        {incident ? describeIncident(incident.incident_type) : 'Pulling the current incident payload.'}
      </p>

      {loading ? (
        <div className="review-room-state">Loading incident detail...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : incident == null ? (
        <div className="review-room-state">No incident detail is available for this item.</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">Status</span>
              <p>{incident.status}</p>
            </div>
            <div>
              <span className="eyebrow">Breaker</span>
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
                  <span>{incident.node_id ?? 'No node attached'}</span>
                </li>
                <li>
                  <strong>Ticket</strong>
                  <span>{incident.ticket_id ?? 'No ticket attached'}</span>
                </li>
                <li>
                  <strong>Provider</strong>
                  <span>{incident.provider_id ?? 'No provider attached'}</span>
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
              {submitting ? 'Submitting...' : 'Apply recovery action'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
