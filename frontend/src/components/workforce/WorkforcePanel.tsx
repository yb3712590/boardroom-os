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

function formatEmploymentState(value: string) {
  switch (value) {
    case 'ACTIVE':
      return '在岗'
    case 'FROZEN':
      return '冻结'
    case 'REPLACED':
      return '已替换'
    default:
      return value
  }
}

function formatActivityState(value: string) {
  switch (value) {
    case 'IDLE':
      return '空闲'
    case 'EXECUTING':
      return '执行中'
    case 'REVIEWING':
      return '评审中'
    default:
      return value
  }
}

function formatDocumentKindRefs(
  refs: string[],
  byRef: Map<string, string>,
) {
  return refs.map((ref) => `${ref}${byRef.get(ref) ? ` (${byRef.get(ref)})` : ''}`).join(', ')
}

function formatFragmentRefs(refs: string[], byRef: Map<string, string>) {
  return refs.map((ref) => byRef.get(ref) ?? ref).join(', ')
}

function formatBoundaryPathRef(ref: string) {
  return ref.replaceAll('_', ' ')
}

function formatBoundarySummary(template: WorkforceData['role_templates_catalog']['role_templates'][number]) {
  const activePaths = template.mainline_boundary.active_path_refs.map(formatBoundaryPathRef).join(', ')
  const hasCeoCreateTicket = template.mainline_boundary.active_path_refs.includes('ceo_create_ticket')
  if (template.mainline_boundary.boundary_status === 'LIVE_ON_MAINLINE') {
    return `当前在线路径：${activePaths}`
  }
  if (hasCeoCreateTicket) {
    return `部分主线路路径：${activePaths}`
  }
  return `仅目录可见 / 未纳入当前主线路：${activePaths}`
}

function formatTemplateKindLabel(templateKind: string) {
  switch (templateKind) {
    case 'live_execution':
      return '在线执行模板'
    case 'reserved_execution':
      return '预留执行模板'
    case 'governance':
      return '治理模板'
    default:
      return templateKind.replaceAll('_', ' ')
  }
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
  const roleTemplateDocumentKindsByRef = new Map(
    (workforce?.role_templates_catalog?.document_kinds ?? []).map((kind) => [kind.kind_ref, kind.label]),
  )
  const roleTemplateFragmentsByRef = new Map(
    (workforce?.role_templates_catalog?.fragments ?? []).map((fragment) => [fragment.fragment_id, fragment.label]),
  )
  const roleTemplatesByKind = (workforce?.role_templates_catalog?.role_templates ?? []).reduce<
    Record<string, WorkforceData['role_templates_catalog']['role_templates']>
  >((accumulator, template) => {
    if (accumulator[template.template_kind] == null) {
      accumulator[template.template_kind] = []
    }
    accumulator[template.template_kind].push(template)
    return accumulator
  }, {})

  return (
    <section className="support-panel" aria-labelledby="workforce-panel-title">
      <div className="section-heading">
        <p className="eyebrow">人员池</p>
        <h2 id="workforce-panel-title">在线执行团队</h2>
      </div>
      {loading ? <LoadingSkeleton lines={6} /> : null}
      {!loading && workforce == null ? <p className="muted-copy">暂无人员池视图。</p> : null}
      {workforce != null ? (
        <>
          <div className="support-summary-grid">
            <div>
              <span>活跃</span>
              <strong>{workforce.summary.active_workers}</strong>
            </div>
            <div>
              <span>空闲</span>
              <strong>{workforce.summary.idle_workers}</strong>
            </div>
            <div>
              <span>检查员</span>
              <strong>{workforce.summary.active_checkers}</strong>
            </div>
            <div>
              <span>返工循环</span>
              <strong>{workforce.summary.workers_in_rework_loop}</strong>
            </div>
            <div>
              <span>隔离中</span>
              <strong>{workforce.summary.workers_in_staffing_containment}</strong>
            </div>
          </div>

          <StaffingActions
            templates={workforce.hire_templates}
            submittingAction={submittingAction}
            onRequestHire={onRequestHire}
          />

          {(workforce.role_templates_catalog?.role_templates?.length ?? 0) > 0 ? (
            <section className="staffing-request-panel" aria-labelledby="role-templates-title">
              <div className="section-heading workforce-section-heading">
                <p className="eyebrow">目录</p>
                <h3 id="role-templates-title">角色模板目录</h3>
              </div>
              {Object.entries(roleTemplatesByKind).map(([templateKind, templates]) => (
                <div key={templateKind}>
                  <p className="field-label">{formatTemplateKindLabel(templateKind)}</p>
                  <div className="staffing-template-list">
                    {templates.map((template) => (
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
                          <span>{template.canonical_role_ref}</span>
                          <span>{template.provider_target_ref}</span>
                        </div>
                        <p className="muted-copy">{template.responsibility_summary}</p>
                        <p className="muted-copy">{template.execution_boundary}</p>
                        <p className="muted-copy">
                          {formatBoundarySummary(template)}
                        </p>
                        {template.mainline_boundary.blocked_path_refs.length > 0 ? (
                          <p className="muted-copy">
                            {`受阻路径：${template.mainline_boundary.blocked_path_refs
                              .map(formatBoundaryPathRef)
                              .join(', ')}`}
                          </p>
                        ) : null}
                        <p className="muted-copy">
                          {formatDocumentKindRefs(
                            template.default_document_kind_refs,
                            roleTemplateDocumentKindsByRef,
                          )}
                        </p>
                        <p className="muted-copy">
                          {formatFragmentRefs(
                            template.composition.fragment_refs,
                            roleTemplateFragmentsByRef,
                          )}
                        </p>
                      </article>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          ) : null}

          <div className="lane-list">
            {workforce.role_lanes.map((lane) => (
              <article key={lane.role_type} className="lane-card">
                <header className="lane-header">
                  <div>
                    <strong>{formatRole(lane.role_type)}</strong>
                    <span>
                      {lane.active_count} 活跃 / {lane.idle_count} 空闲
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
                          <Badge variant={employmentVariant(worker.employment_state)}>{formatEmploymentState(worker.employment_state)}</Badge>
                        </div>
                        <div className="worker-card-state">
                          <span>{`雇佣状态 ${formatEmploymentState(worker.employment_state)}`}</span>
                          <span>{`活动状态 ${formatActivityState(worker.activity_state)}`}</span>
                        </div>
                        <div className="worker-card-meta">
                          <span>{worker.current_node_id ?? '无当前节点'}</span>
                          <span>{worker.current_ticket_id ?? '无当前工单'}</span>
                          <span>{worker.provider_id ?? '无供应商绑定'}</span>
                        </div>
                        <ProfileSummary
                          label="当前画像"
                          summary={worker.profile_summary}
                          skillProfile={worker.skill_profile}
                          personalityProfile={worker.personality_profile}
                          aestheticProfile={worker.aesthetic_profile}
                        />
                        {worker.source_template_id ? (
                          <p className="muted-copy">
                            {`来源模板 ${worker.source_template_id}`}
                            {(worker.source_fragment_refs ?? []).length > 0
                              ? ` · ${formatFragmentRefs(worker.source_fragment_refs ?? [], roleTemplateFragmentsByRef)}`
                              : ''}
                          </p>
                        ) : null}
                        <div className="worker-action-row">
                          {freezeAction?.enabled ? (
                            <Button
                              type="button"
                              variant="danger"
                              onClick={() => void onFreeze(worker.employee_id)}
                              loading={submittingAction === `freeze:${worker.employee_id}`}
                              aria-label={`冻结 ${worker.employee_id}`}
                            >
                              {submittingAction === `freeze:${worker.employee_id}` ? '冻结中…' : '冻结'}
                            </Button>
                          ) : null}
                          {restoreAction?.enabled ? (
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={() => void onRestore(worker.employee_id)}
                              loading={submittingAction === `restore:${worker.employee_id}`}
                              aria-label={`恢复 ${worker.employee_id}`}
                            >
                              {submittingAction === `restore:${worker.employee_id}` ? '恢复中…' : '恢复'}
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
                              aria-label={`为 ${worker.employee_id} 发起替换`}
                            >
                              发起替换
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
                              <span>{`为 ${worker.employee_id} 填写替换员工编号`}</span>
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
                              aria-label={`提交 ${worker.employee_id} 的替换请求`}
                            >
                              {submittingAction === `replace:${worker.employee_id}` ? '提交中…' : '提交替换'}
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
