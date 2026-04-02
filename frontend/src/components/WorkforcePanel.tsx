import type { WorkforceData } from '../api'

type WorkforcePanelProps = {
  workforce: WorkforceData | null
  loading: boolean
}

function formatRole(roleType: string) {
  return roleType.replaceAll('_', ' ')
}

export function WorkforcePanel({ workforce, loading }: WorkforcePanelProps) {
  return (
    <section className="support-panel" aria-labelledby="workforce-panel-title">
      <div className="section-heading">
        <p className="eyebrow">Workforce</p>
        <h2 id="workforce-panel-title">Live workforce</h2>
      </div>
      {loading ? <p className="muted-copy">Loading workforce lanes...</p> : null}
      {!loading && workforce == null ? <p className="muted-copy">No workforce view is available.</p> : null}
      {workforce != null ? (
        <>
          <div className="support-summary-grid">
            <div>
              <span>Active</span>
              <strong>{workforce.summary.active_workers}</strong>
            </div>
            <div>
              <span>Idle</span>
              <strong>{workforce.summary.idle_workers}</strong>
            </div>
            <div>
              <span>Checkers</span>
              <strong>{workforce.summary.active_checkers}</strong>
            </div>
            <div>
              <span>Rework loops</span>
              <strong>{workforce.summary.workers_in_rework_loop}</strong>
            </div>
            <div>
              <span>Contained</span>
              <strong>{workforce.summary.workers_in_staffing_containment}</strong>
            </div>
          </div>
          <div className="lane-list">
            {workforce.role_lanes.map((lane) => (
              <article key={lane.role_type} className="lane-card">
                <header className="lane-header">
                  <div>
                    <strong>{formatRole(lane.role_type)}</strong>
                    <span>
                      {lane.active_count} active / {lane.idle_count} idle
                    </span>
                  </div>
                </header>
                <div className="worker-list">
                  {lane.workers.map((worker) => (
                    <div key={worker.employee_id} className="worker-card">
                      <div className="worker-card-main">
                        <strong>{worker.employee_id}</strong>
                        <span>{worker.activity_state}</span>
                      </div>
                      <div className="worker-card-meta">
                        <span>{worker.current_node_id ?? 'No current node'}</span>
                        <span>{worker.current_ticket_id ?? 'No current ticket'}</span>
                        <span>{worker.provider_id ?? 'No provider binding'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}
