import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { WorkforcePanel } from '../../../components/workforce/WorkforcePanel'

describe('WorkforcePanel', () => {
  it('renders the current worker profile summary', () => {
    render(
      <WorkforcePanel
        workforce={{
          summary: {
            active_workers: 1,
            idle_workers: 0,
            overloaded_workers: 0,
            active_checkers: 0,
            workers_in_rework_loop: 0,
            workers_in_staffing_containment: 0,
          },
          hire_templates: [],
          role_lanes: [
            {
              role_type: 'frontend_engineer',
              active_count: 1,
              idle_count: 0,
              workers: [
                {
                  employee_id: 'emp_frontend_2',
                  role_type: 'frontend_engineer',
                  employment_state: 'ACTIVE',
                  activity_state: 'EXECUTING',
                  current_ticket_id: 'tkt_001',
                  current_node_id: 'node_001',
                  provider_id: 'prov_openai_compat',
                  skill_profile: {
                    primary_domain: 'frontend',
                    system_scope: 'delivery_slice',
                    validation_bias: 'balanced',
                  },
                  personality_profile: {
                    risk_posture: 'assertive',
                    challenge_style: 'constructive',
                    execution_pace: 'fast',
                    detail_rigor: 'focused',
                    communication_style: 'direct',
                  },
                  aesthetic_profile: {
                    surface_preference: 'functional',
                    information_density: 'balanced',
                    motion_tolerance: 'measured',
                  },
                  profile_summary:
                    'Skill frontend, delivery slice, balanced. Personality assertive, constructive, fast, focused, direct. Aesthetic functional, balanced, measured.',
                  last_update_at: '2026-04-04T18:00:00+08:00',
                  available_actions: [],
                },
              ],
            },
          ],
        }}
        loading={false}
        submittingAction={null}
        onFreeze={vi.fn().mockResolvedValue(undefined)}
        onRestore={vi.fn().mockResolvedValue(undefined)}
        onRequestHire={vi.fn().mockResolvedValue(undefined)}
        onRequestReplacement={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Current profile')).toBeInTheDocument()
    expect(screen.getByText(/Skill frontend, delivery slice, balanced/i)).toBeInTheDocument()
    expect(screen.getByText(/risk posture: assertive/i)).toBeInTheDocument()
  })
})
