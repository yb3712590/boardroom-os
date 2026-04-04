import { useState } from 'react'

import { Button } from '../shared/Button'

import type { StaffingHireTemplate } from '../../types/domain'

type StaffingActionsProps = {
  templates: StaffingHireTemplate[]
  submittingAction: string | null
  onRequestHire: (template: StaffingHireTemplate, employeeId: string) => Promise<void>
}

export function StaffingActions({ templates, submittingAction, onRequestHire }: StaffingActionsProps) {
  const [hireDrafts, setHireDrafts] = useState<Record<string, string>>({})

  return (
    <section className="staffing-request-panel" aria-labelledby="staffing-request-title">
      <div className="section-heading workforce-section-heading">
        <p className="eyebrow">Staffing</p>
        <h3 id="staffing-request-title">Request staffing</h3>
      </div>
      <div className="staffing-template-list">
        {templates.map((template) => {
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
              <Button
                type="submit"
                variant="secondary"
                loading={isSubmitting}
                disabled={value.trim().length === 0}
                aria-label={`Request hire for ${template.label}`}
              >
                {isSubmitting ? 'Requesting…' : 'Request hire'}
              </Button>
            </form>
          )
        })}
      </div>
    </section>
  )
}
