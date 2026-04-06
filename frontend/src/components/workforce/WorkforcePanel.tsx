import { useState } from 'react'

import { Badge } from '../shared/Badge'
import { Button } from '../shared/Button'
import { LoadingSkeleton } from '../shared/LoadingSkeleton'
import { ProfileSummary } from '../shared/ProfileSummary'
import { StaffingActions } from './StaffingActions'

import type { WorkforceData } from '../../types/api'
import { newPrefixedId } from '../../utils/ids'

type WorkforcePanelProps = {
  workforce: WorkforceData | null
  loading: boolean
  submittingAction: string | null
  onFreeze: (employeeId: string) => Promise<void>
  onRestore: (employeeId: string) => Promise<void>
  onRequestHire: (template: WorkforceData['hire_templates'][number], employeeId: string) => Promise<void>
  onRequestReplacement: (
    employeeId: string,
    template: WorkforceData['hire_templates'][number],
    replacementEmployeeId: string,
  ) => Promise<void>
}

function formatRole(roleType: string) {
  return roleType.replaceAll('_', ' ')
}

function formatDocumentKindRefs(
  refs: string[],
  byRef: Map<string, string>,
) {
  return refs.map((ref) => `${ref}${byRef.get(ref) ? ` (${byRef.get(ref)})` : ''}`).join(', ')
}

function findAction(actions: WorkforceData['role_lanes'][number]['workers'][number]['available_actions'], actionType: string) {
  return actions.find((action) => action.action_type === actionType) ?? null
}

function employmentVariant(state: string) {
  switch (state) {
    case 'ACTIVE':
      return 'success'
    case 'FROZEN':
      return 'muted'
    case 'REPLACED':
      return 'critical'
    default:
      return 'info'
  }
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
  const [replaceDrafts, setReplaceDrafts] = useState<Record<string, string>>({})
  const [replaceOpenFor, setReplaceOpenFor] = useState<string | null>(null)

  const templatesById = new Map((workforce?.hire_templates ?? []).map((template) => [template.template_id, template]))
  const governanceDocumentKindsByRef = new Map(
    (workforce?.governance_templates?.document_kinds ?? []).map((kind) => [kind.kind_ref, kind.label]),
  )

  return (
    <section className="support-panel" aria-labelledby="workforce-panel-title">
      <div className="section-heading">
        <p className="eyebrow">Workforce</p>
        <h2 id="workforce-panel-title">Live workforce</h2>
      </div>
      {loading ? <LoadingSkeleton lines={6} /> : null}
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

          <StaffingActions
            templates={workforce.hire_templates}
            submittingAction={submittingAction}
            onRequestHire={onRequestHire}
          />

          {workforce.governance_templates.role_templates.length > 0 ? (
            <section className="staffing-request-panel" aria-labelledby="governance-templates-title">
              <div className="section-heading workforce-section-heading">
                <p className="eyebrow">Governance</p>
                <h3 id="governance-templates-title">Governance templates</h3>
              </div>
              <div className="staffing-template-list">
                {workforce.governance_templates.role_templates.map((template) => (
                  <article key={template.template_id} className="staffing-template-card">
                    <div className="staffing-template-copy">
                      <strong>{template.label}</strong>
                      <span>{template.summary}</span>
                    </div>
                    <div className="worker-card-state">
                      <span>{template.status}</span>
                      <span>{template.participation_mode}</span>
                    </div>
                    <div className="worker-card-meta">
                      <span>{template.role_profile_ref}</span>
                      <span>{template.provider_target_ref}</span>
                    </div>
                    <p className="muted-copy">{template.execution_boundary}</p>
                    <p className="muted-copy">
                      {formatDocumentKindRefs(
                        template.default_document_kind_refs,
                        governanceDocumentKindsByRef,
                      )}
                    </p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

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
                          <Badge variant={employmentVariant(worker.employment_state)}>{worker.employment_state}</Badge>
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
                        <ProfileSummary
                          label="Current profile"
                          summary={worker.profile_summary}
                          skillProfile={worker.skill_profile}
                          personalityProfile={worker.personality_profile}
                          aestheticProfile={worker.aesthetic_profile}
                        />
                        <div className="worker-action-row">
                          {freezeAction?.enabled ? (
                            <Button
                              type="button"
                              variant="danger"
                              onClick={() => void onFreeze(worker.employee_id)}
                              loading={submittingAction === `freeze:${worker.employee_id}`}
                              aria-label={`Freeze ${worker.employee_id}`}
                            >
                              {submittingAction === `freeze:${worker.employee_id}` ? 'Freezing…' : 'Freeze'}
                            </Button>
                          ) : null}
                          {restoreAction?.enabled ? (
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={() => void onRestore(worker.employee_id)}
                              loading={submittingAction === `restore:${worker.employee_id}`}
                              aria-label={`Restore ${worker.employee_id}`}
                            >
                              {submittingAction === `restore:${worker.employee_id}` ? 'Restoring…' : 'Restore'}
                            </Button>
                          ) : null}
                          {replaceAction?.enabled && replaceTemplate != null ? (
                            <Button
                              type="button"
                              variant="ghost"
                              onClick={() => {
                                setReplaceDrafts((current) => {
                                  if (current[worker.employee_id] != null) {
                                    return current
                                  }

                                  return {
                                    ...current,
                                    [worker.employee_id]:
                                      replaceTemplate.employee_id_hint.trim() || newPrefixedId('emp'),
                                  }
                                })
                                setReplaceOpenFor((current) => (current === worker.employee_id ? null : worker.employee_id))
                              }}
                              disabled={submittingAction === `replace:${worker.employee_id}`}
                              aria-label={`Request replacement for ${worker.employee_id}`}
                            >
                              Request replacement
                            </Button>
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
                            <Button
                              type="submit"
                              variant="secondary"
                              loading={submittingAction === `replace:${worker.employee_id}`}
                              disabled={replaceValue.trim().length === 0}
                              aria-label={`Submit replacement for ${worker.employee_id}`}
                            >
                              {submittingAction === `replace:${worker.employee_id}` ? 'Submitting…' : 'Submit replacement'}
                            </Button>
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
