import { AnimatePresence, motion } from 'framer-motion'

import type { DependencyInspectorData } from '../api'

type DependencyInspectorDrawerProps = {
  isOpen: boolean
  loading: boolean
  inspectorData: DependencyInspectorData | null
  error: string | null
  onClose: () => void
  onOpenReview: (reviewPackId: string) => void
  onOpenIncident: (incidentId: string) => void
}

function formatLabel(value: string | null | undefined) {
  if (!value) {
    return 'None'
  }
  return value.replaceAll('_', ' ')
}

export function DependencyInspectorDrawer({
  isOpen,
  loading,
  inspectorData,
  error,
  onClose,
  onOpenReview,
  onOpenIncident,
}: DependencyInspectorDrawerProps) {
  const currentStop = inspectorData?.summary.current_stop

  return (
    <AnimatePresence>
      {isOpen ? (
        <motion.aside
          className="review-room-drawer"
          initial={{ opacity: 0, x: 48 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 48 }}
          transition={{ duration: 0.24, ease: 'easeOut' }}
          aria-label="Dependency inspector"
        >
          <div className="review-room-backdrop" onClick={onClose} aria-hidden="true" />
          <motion.section
            className="review-room-panel dependency-inspector-panel"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 18 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
          >
            <header className="review-room-header">
              <div>
                <p className="eyebrow">Dependency Inspector</p>
                <h2>Dependency chain</h2>
                <p>
                  See which stage depends on which upstream ticket, where the current stop sits, and which node should
                  send you back to review or incident handling.
                </p>
              </div>
              <button type="button" className="ghost-button" onClick={onClose}>
                Close
              </button>
            </header>

            {loading ? (
              <div className="review-room-state">Loading dependency inspector...</div>
            ) : error ? (
              <div className="review-room-state review-room-error">{error}</div>
            ) : inspectorData == null ? (
              <div className="review-room-state">No dependency snapshot is available for this workflow.</div>
            ) : (
              <div className="review-room-content">
                <section className="review-room-overview">
                  <div>
                    <span className="eyebrow">Current stop</span>
                    <p>{formatLabel(currentStop?.reason)}</p>
                  </div>
                  <div>
                    <span className="eyebrow">Blocked nodes</span>
                    <p>{inspectorData.summary.blocked_nodes}</p>
                  </div>
                  <div>
                    <span className="eyebrow">Critical path</span>
                    <p>{inspectorData.summary.critical_path_nodes}</p>
                  </div>
                </section>

                <section className="dependency-summary-grid">
                  <div className="review-room-action-panel">
                    <span className="eyebrow">Workflow</span>
                    <p>{inspectorData.workflow.title}</p>
                    <p className="muted-copy">
                      {inspectorData.workflow.workflow_id} · {formatLabel(inspectorData.workflow.current_stage)}
                    </p>
                  </div>
                  <div className="review-room-action-panel">
                    <span className="eyebrow">Approvals</span>
                    <p>{inspectorData.summary.open_approvals}</p>
                    <p className="muted-copy">Open board approvals on this chain.</p>
                  </div>
                  <div className="review-room-action-panel">
                    <span className="eyebrow">Incidents</span>
                    <p>{inspectorData.summary.open_incidents}</p>
                    <p className="muted-copy">Open incidents that can stop downstream work.</p>
                  </div>
                </section>

                <section className="dependency-node-list" aria-label="dependency nodes">
                  {inspectorData.nodes.map((node) => (
                    <article
                      key={node.node_id}
                      className={`dependency-node ${node.is_blocked ? 'is-blocked' : ''} ${
                        node.is_critical_path ? 'is-critical' : ''
                      }`}
                    >
                      <div className="dependency-node-header">
                        <div>
                          <p className="eyebrow">{node.phase}</p>
                          <h3>{node.ticket_id ?? node.node_id}</h3>
                        </div>
                        <div className="dependency-node-badges">
                          <span>{formatLabel(node.block_reason)}</span>
                          <span>{formatLabel(node.node_status)}</span>
                        </div>
                      </div>

                      <dl className="dependency-node-grid">
                        <div>
                          <dt>Depends on</dt>
                          <dd>{node.depends_on_ticket_id ?? 'Root node'}</dd>
                        </div>
                        <div>
                          <dt>Downstream impact</dt>
                          <dd>
                            {node.dependent_ticket_ids.length > 0
                              ? node.dependent_ticket_ids.join(', ')
                              : 'No downstream tickets'}
                          </dd>
                        </div>
                        <div>
                          <dt>Role</dt>
                          <dd>{node.role_profile_ref ?? 'Not assigned'}</dd>
                        </div>
                        <div>
                          <dt>Output</dt>
                          <dd>{node.output_schema_ref ?? 'No output schema'}</dd>
                        </div>
                      </dl>

                      <div className="dependency-node-footer">
                        <div>
                          <strong>Artifact scope</strong>
                          <p>
                            {node.expected_artifact_scope.length > 0
                              ? node.expected_artifact_scope.join(' · ')
                              : 'No write scope attached.'}
                          </p>
                        </div>
                        <div className="dependency-node-actions">
                          {node.open_review_pack_id ? (
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() => onOpenReview(node.open_review_pack_id as string)}
                            >
                              Open review room
                            </button>
                          ) : null}
                          {node.open_incident_id ? (
                            <button
                              type="button"
                              className="danger-button"
                              onClick={() => onOpenIncident(node.open_incident_id as string)}
                            >
                              Open incident
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </article>
                  ))}
                </section>
              </div>
            )}
          </motion.section>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}
