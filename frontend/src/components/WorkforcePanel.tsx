import { useState } from 'react'

import type { StaffingHireTemplate, WorkforceData, WorkforceWorkerAction } from '../api'

type WorkforcePanelProps = {
  workforce: WorkforceData | null
  loading: boolean
  submittingAction: string | null
  onFreeze: (employeeId: string) => Promise<void>
  onRestore: (employeeId: string) => Promise<void>
  onRequestHire: (template: StaffingHireTemplate, employeeId: string) => Promise<void>
  onRequestReplacement: (
    employeeId: string,
    template: StaffingHireTemplate,
    replacementEmployeeId: string,
  ) => Promise<void>
}

function formatRole(roleType: string) {
  return roleType.replaceAll('_', ' ')
}

function findAction(actions: WorkforceWorkerAction[], actionType: string) {
  return actions.find((action) => action.action_type === actionType) ?? null
}

export function WorkforcePanel({
  workforce,
  loading,
  submittingAction,
  onFreeze,
  onRestore,
  onRequestHire,
  onRequestReplacement,
}: WorkforcePanelProps) {
  const [hireDrafts, setHireDrafts] = useState<Record<string, string>>({})
  const [replaceDrafts, setReplaceDrafts] = useState<Record<string, string>>({})
  const [replaceOpenFor, setReplaceOpenFor] = useState<string | null>(null)

  const templatesById = new Map((workforce?.hire_templates ?? []).map((template) => [template.template_id, template]))

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

          <section className="staffing-request-panel" aria-labelledby="staffing-request-title">
            <div className="section-heading workforce-section-heading">
              <p className="eyebrow">Staffing</p>
              <h3 id="staffing-request-title">Request staffing</h3>
            </div>
            <div className="staffing-template-list">
              {workforce.hire_templates.map((template) => {
                const value = hireDrafts[template.template_id] ?? template.employee_id_hint
                const isSubmitting = submittingAction === `hire:${template.template_id}`
                return (
                  <form
                    key={template.template_id}
                    className="staffing-template-card"
                    onSubmit={(event) => {
                      event.preventDefault()
                      const trimmedValue = value.trim()
                      if (!trimmedValue) {
                        return
                      }
                      void onRequestHire(template, trimmedValue)
                    }}
                  >
                    <div className="staffing-template-copy">
                      <strong>{template.label}</strong>
                      <span>{template.request_summary}</span>
                    </div>
                    <label className="staffing-inline-field">
                      <span>{template.label} employee id</span>
                      <input
                        type="text"
                        value={value}
                        onChange={(event) =>
                          setHireDrafts((current) => ({
                            ...current,
                            [template.template_id]: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <button
                      type="submit"
                      className="secondary-button"
                      disabled={isSubmitting || value.trim().length === 0}
                      aria-label={`Request hire for ${template.label}`}
                    >
                      {isSubmitting ? 'Requesting…' : 'Request hire'}
                    </button>
                  </form>
                )
              })}
            </div>
          </section>

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
                  {lane.workers.map((worker) => {
                    const freezeAction = findAction(worker.available_actions, 'FREEZE')
                    const restoreAction = findAction(worker.available_actions, 'RESTORE')
                    const replaceAction = findAction(worker.available_actions, 'REPLACE')
                    const replaceTemplate =
                      replaceAction?.template_id != null ? templatesById.get(replaceAction.template_id) ?? null : null
                    const replaceValue =
                      replaceDrafts[worker.employee_id] ?? replaceTemplate?.employee_id_hint ?? ''

                    return (
                      <div key={worker.employee_id} className="worker-card">
                        <div className="worker-card-main">
                          <strong>{worker.employee_id}</strong>
                          <span>{worker.activity_state}</span>
                        </div>
                        <div className="worker-card-state">
                          <span>{`Employment ${worker.employment_state}`}</span>
                          <span>{`Activity ${worker.activity_state}`}</span>
                        </div>
                        <div className="worker-card-meta">
                          <span>{worker.current_node_id ?? 'No current node'}</span>
                          <span>{worker.current_ticket_id ?? 'No current ticket'}</span>
                          <span>{worker.provider_id ?? 'No provider binding'}</span>
                        </div>
                        <div className="worker-action-row">
                          {freezeAction?.enabled ? (
                            <button
                              type="button"
                              className="danger-button"
                              onClick={() => void onFreeze(worker.employee_id)}
                              disabled={submittingAction === `freeze:${worker.employee_id}`}
                              aria-label={`Freeze ${worker.employee_id}`}
                            >
                              {submittingAction === `freeze:${worker.employee_id}` ? 'Freezing…' : 'Freeze'}
                            </button>
                          ) : null}
                          {restoreAction?.enabled ? (
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() => void onRestore(worker.employee_id)}
                              disabled={submittingAction === `restore:${worker.employee_id}`}
                              aria-label={`Restore ${worker.employee_id}`}
                            >
                              {submittingAction === `restore:${worker.employee_id}` ? 'Restoring…' : 'Restore'}
                            </button>
                          ) : null}
                          {replaceAction?.enabled && replaceTemplate != null ? (
                            <button
                              type="button"
                              className="ghost-button"
                              onClick={() =>
                                setReplaceOpenFor((current) =>
                                  current === worker.employee_id ? null : worker.employee_id,
                                )
                              }
                              disabled={submittingAction === `replace:${worker.employee_id}`}
                              aria-label={`Request replacement for ${worker.employee_id}`}
                            >
                              Request replacement
                            </button>
                          ) : null}
                        </div>
                        {replaceOpenFor === worker.employee_id && replaceTemplate != null ? (
                          <form
                            className="staffing-replacement-form"
                            onSubmit={async (event) => {
                              event.preventDefault()
                              const trimmedValue = replaceValue.trim()
                              if (!trimmedValue) {
                                return
                              }
                              await onRequestReplacement(worker.employee_id, replaceTemplate, trimmedValue)
                              setReplaceOpenFor(null)
                            }}
                          >
                            <label className="staffing-inline-field">
                              <span>{`Replacement employee id for ${worker.employee_id}`}</span>
                              <input
                                type="text"
                                value={replaceValue}
                                onChange={(event) =>
                                  setReplaceDrafts((current) => ({
                                    ...current,
                                    [worker.employee_id]: event.target.value,
                                  }))
                                }
                              />
                            </label>
                            <button
                              type="submit"
                              className="secondary-button"
                              disabled={
                                replaceValue.trim().length === 0 ||
                                submittingAction === `replace:${worker.employee_id}`
                              }
                              aria-label={`Submit replacement for ${worker.employee_id}`}
                            >
                              {submittingAction === `replace:${worker.employee_id}` ? 'Submitting…' : 'Submit replacement'}
                            </button>
                          </form>
                        ) : null}
                        {freezeAction?.enabled !== true && freezeAction?.disabled_reason ? (
                          <p className="worker-action-hint">{freezeAction.disabled_reason}</p>
                        ) : null}
                        {restoreAction?.enabled !== true && restoreAction?.disabled_reason ? (
                          <p className="worker-action-hint">{restoreAction.disabled_reason}</p>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </article>
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}
