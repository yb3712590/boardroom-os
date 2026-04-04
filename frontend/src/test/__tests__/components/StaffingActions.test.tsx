import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { StaffingActions } from '../../../components/workforce/StaffingActions'

describe('StaffingActions', () => {
  it('submits the selected template with the entered employee id', async () => {
    const user = userEvent.setup()
    const onRequestHire = vi.fn().mockResolvedValue(undefined)
    const template = {
      template_id: 'frontend_backup',
      label: 'Frontend backup maker',
      role_type: 'frontend_engineer',
      role_profile_refs: ['frontend_engineer_primary'],
      employee_id_hint: 'emp_frontend_backup',
      provider_id: 'prov_openai_compat',
      request_summary: 'Hire a backup frontend maker for rework rotation.',
      skill_profile: { primary_domain: 'frontend' },
      personality_profile: { style: 'maker' },
      aesthetic_profile: { preference: 'minimal' },
    }

    render(
      <StaffingActions templates={[template]} submittingAction={null} onRequestHire={onRequestHire} />,
    )

    const employeeIdField = screen.getByLabelText('Frontend backup maker employee id')

    await user.clear(employeeIdField)
    await user.type(employeeIdField, 'emp_frontend_new')
    await user.click(screen.getByRole('button', { name: 'Request hire for Frontend backup maker' }))

    expect(onRequestHire).toHaveBeenCalledWith(template, 'emp_frontend_new')
  })
})
