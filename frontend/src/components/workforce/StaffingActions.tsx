import { useEffect, useState } from 'react'

import { Button } from '../shared/Button'
import { ProfileSummary } from '../shared/ProfileSummary'

import type { StaffingHireTemplate } from '../../types/domain'
import { newPrefixedId } from '../../utils/ids'

type StaffingActionsProps = {
  templates: StaffingHireTemplate[]
  submittingAction: string | null
  onRequestHire: (template: StaffingHireTemplate, employeeId: string) => Promise<void>
}

export function StaffingActions({ templates, submittingAction, onRequestHire }: StaffingActionsProps) {
  const [hireDrafts, setHireDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    setHireDrafts((current) => {
      let changed = false
      const next = { ...current }

      for (const template of templates) {
        if (next[template.template_id] != null) {
          continue
        }

        next[template.template_id] = template.employee_id_hint.trim() || newPrefixedId('emp')
        changed = true
      }

      return changed ? next : current
    })
  }, [templates])

  return (
    <section className="staffing-request-panel" aria-labelledby="staffing-request-title">
      <div className="section-heading workforce-section-heading">
        <p className="eyebrow">人员配置</p>
        <h3 id="staffing-request-title">发起招聘请求</h3>
      </div>
      <div className="staffing-template-list">
        {templates.map((template) => {
          const value =
            hireDrafts[template.template_id] ??
            (template.employee_id_hint.trim() || newPrefixedId('emp'))
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
              <ProfileSummary
                label="模板画像"
                skillProfile={template.skill_profile}
                personalityProfile={template.personality_profile}
                aestheticProfile={template.aesthetic_profile}
              />
              <label className="staffing-inline-field">
                <span>{template.label} 员工编号</span>
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
              <Button
                type="submit"
                variant="secondary"
                loading={isSubmitting}
                disabled={value.trim().length === 0}
                aria-label={`为 ${template.label} 发起招聘`}
              >
                {isSubmitting ? '请求中…' : '发起招聘'}
              </Button>
            </form>
          )
        })}
      </div>
    </section>
  )
}
