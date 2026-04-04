import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReviewRoomDrawer } from '../../../components/overlays/ReviewRoomDrawer'

describe('ReviewRoomDrawer', () => {
  it('renders staffing candidate profiles from employee_change', () => {
    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_001',
              review_pack_id: 'brp_001',
              review_pack_version: 1,
              workflow_id: 'wf_001',
              review_type: 'CORE_HIRE_APPROVAL',
              created_at: '2026-04-04T18:00:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Approve hire: emp_frontend_backup',
              change_kind: 'EMPLOYEE_HIRE',
              employee_id: 'emp_frontend_backup',
            },
            trigger: {
              trigger_event_id: 'evt_001',
              trigger_reason: 'Core staffing changes require explicit board approval.',
              why_now: 'Need more frontend coverage.',
            },
            recommendation: {
              recommended_action: 'APPROVE',
              recommended_option_id: 'approve_employee_change',
              summary: 'Approve the complementary hire.',
            },
            options: [
              {
                option_id: 'approve_employee_change',
                label: 'Approve staffing change',
                summary: 'Approve the complementary hire.',
              },
            ],
            decision_form: {
              allowed_actions: ['APPROVE', 'REJECT'],
              command_target_version: 1,
              requires_comment_on_reject: true,
              requires_constraint_patch_on_modify: false,
            },
            employee_change: {
              change_kind: 'EMPLOYEE_HIRE',
              employee_id: 'emp_frontend_backup',
              skill_profile: {
                primary_domain: 'frontend',
                system_scope: 'surface_polish',
                validation_bias: 'finish_first',
              },
              personality_profile: {
                risk_posture: 'cautious',
                challenge_style: 'probing',
                execution_pace: 'measured',
                detail_rigor: 'rigorous',
                communication_style: 'concise',
              },
              aesthetic_profile: {
                surface_preference: 'polished',
                information_density: 'layered',
                motion_tolerance: 'restrained',
              },
            },
          },
          available_actions: ['APPROVE', 'REJECT'],
          draft_defaults: {
            selected_option_id: 'approve_employee_change',
            comment_template: '',
          },
        }}
        inspectorData={null}
        inspectorLoading={false}
        error={null}
        submittingAction={null}
        onClose={vi.fn()}
        onOpenInspector={vi.fn()}
        onApprove={vi.fn().mockResolvedValue(undefined)}
        onReject={vi.fn().mockResolvedValue(undefined)}
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Candidate profile')).toBeInTheDocument()
    expect(screen.getByText('emp_frontend_backup')).toBeInTheDocument()
    expect(screen.getAllByText(/surface polish/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/risk posture: cautious/i).length).toBeGreaterThan(0)
  })
})
