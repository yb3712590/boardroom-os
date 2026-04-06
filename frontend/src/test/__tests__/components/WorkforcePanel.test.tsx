import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { WorkforcePanel } from '../../../components/workforce/WorkforcePanel'

describe('WorkforcePanel', () => {
  it('renders a loading skeleton while the workforce projection is pending', () => {
    const { container } = render(
      <WorkforcePanel
        workforce={null}
        loading={true}
        submittingAction={null}
        onFreeze={vi.fn().mockResolvedValue(undefined)}
        onRestore={vi.fn().mockResolvedValue(undefined)}
        onRequestHire={vi.fn().mockResolvedValue(undefined)}
        onRequestReplacement={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(container.querySelector('.loading-skeleton')).not.toBeNull()
    expect(screen.queryByText('No workforce view is available.')).not.toBeInTheDocument()
  })

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
          governance_templates: {
            role_templates: [
              {
                template_id: 'cto_governance',
                label: 'CTO / 架构治理',
                role_type: 'governance_cto',
                role_profile_ref: 'cto_primary',
                provider_target_ref: 'role_profile:cto_primary',
                participation_mode: 'LOW_FREQUENCY_HIGH_LEVERAGE',
                execution_boundary: '默认不承担日常编码、测试或持续实施主力工作。',
                status: 'NOT_ENABLED',
                default_document_kind_refs: ['architecture_brief', 'technology_decision'],
                summary: 'Own high-leverage architecture and governance decisions.',
              },
            ],
            document_kinds: [
              {
                kind_ref: 'architecture_brief',
                label: '架构方案',
                summary: 'Frame the target architecture and tradeoffs.',
              },
              {
                kind_ref: 'technology_decision',
                label: '技术选型',
                summary: 'Capture option comparisons and final decisions.',
              },
            ],
          },
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
    expect(screen.getByText('Governance templates')).toBeInTheDocument()
    expect(screen.getByText(/CTO \/ 架构治理/i)).toBeInTheDocument()
    expect(screen.getByText(/architecture_brief/i)).toBeInTheDocument()
    expect(screen.getByText(/not_enabled/i)).toBeInTheDocument()
  })
})
