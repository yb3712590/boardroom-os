import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
        onOpenArtifact={vi.fn()}
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

  it('renders evidence source refs when present', () => {
    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_002',
              review_pack_id: 'brp_002',
              review_pack_version: 1,
              workflow_id: 'wf_002',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-06T12:00:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Approve final delivery package',
            },
            trigger: {
              trigger_event_id: 'evt_002',
              trigger_reason: 'Final package is ready for board review.',
              why_now: 'Need final approval before completion.',
            },
            recommendation: {
              recommended_action: 'APPROVE',
              recommended_option_id: 'approve_delivery',
              summary: 'Approve the final package.',
            },
            options: [
              {
                option_id: 'approve_delivery',
                label: 'Approve delivery',
                summary: 'Approve the final package.',
              },
            ],
            evidence_summary: [
              {
                evidence_id: 'ev_closeout_docs',
                label: 'Documentation sync',
                summary: 'Closeout recorded one documentation follow-up item.',
                source_ref: 'art://runtime/tkt_closeout_001/delivery-closeout-package.json',
              } as never,
            ],
            decision_form: {
              allowed_actions: ['APPROVE', 'REJECT'],
              command_target_version: 1,
              requires_comment_on_reject: true,
              requires_constraint_patch_on_modify: false,
            },
          },
          available_actions: ['APPROVE', 'REJECT'],
          draft_defaults: {
            selected_option_id: 'approve_delivery',
            comment_template: '',
          },
        }}
        inspectorData={null}
        inspectorLoading={false}
        error={null}
        submittingAction={null}
        onClose={vi.fn()}
        onOpenInspector={vi.fn()}
        onOpenArtifact={vi.fn()}
        onApprove={vi.fn().mockResolvedValue(undefined)}
        onReject={vi.fn().mockResolvedValue(undefined)}
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Documentation sync')).toBeInTheDocument()
    expect(screen.getByText('Source ref')).toBeInTheDocument()
    expect(screen.getByText('art://runtime/tkt_closeout_001/delivery-closeout-package.json')).toBeInTheDocument()
  })

  it('renders requirement elicitation questionnaire and submits structured answers', async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn().mockResolvedValue(undefined)

    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_003',
              review_pack_id: 'brp_003',
              review_pack_version: 1,
              workflow_id: 'wf_003',
              review_type: 'REQUIREMENT_ELICITATION',
              created_at: '2026-04-06T12:00:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Clarify initialization inputs',
            },
            trigger: {
              trigger_event_id: 'evt_003',
              trigger_reason: 'Initial board directive is still below the minimum executable threshold.',
              why_now: 'Need structured answers before scope kickoff starts.',
            },
            recommendation: {
              recommended_action: 'APPROVE',
              recommended_option_id: 'elicitation_continue',
              summary: 'Capture the missing delivery answers and continue to scope kickoff.',
            },
            options: [
              {
                option_id: 'elicitation_continue',
                label: 'Continue after clarification',
                summary: 'Use the structured answers as the new startup brief.',
              },
            ],
            elicitation_questionnaire: [
              {
                question_id: 'delivery_scope',
                prompt: 'What is the narrowest acceptable delivery slice?',
                response_kind: 'SINGLE_SELECT',
                required: true,
                options: [
                  {
                    option_id: 'scope_mvp_slice',
                    label: 'Single MVP slice',
                    summary: 'One board-reviewable delivery path only.',
                  },
                ],
              },
              {
                question_id: 'hard_boundaries',
                prompt: 'What hard boundaries must the team keep?',
                response_kind: 'TEXT',
                required: true,
                options: [],
              },
            ],
            decision_form: {
              allowed_actions: ['APPROVE', 'MODIFY_CONSTRAINTS'],
              command_target_version: 1,
              requires_comment_on_reject: true,
              requires_constraint_patch_on_modify: true,
            },
          } as never,
          available_actions: ['APPROVE', 'MODIFY_CONSTRAINTS'],
          draft_defaults: {
            selected_option_id: 'elicitation_continue',
            comment_template: '',
            elicitation_answers: [
              {
                question_id: 'hard_boundaries',
                selected_option_ids: [],
                text: 'Keep the system local-first.',
              },
            ],
          } as never,
        }}
        inspectorData={null}
        inspectorLoading={false}
        error={null}
        submittingAction={null}
        onClose={vi.fn()}
        onOpenInspector={vi.fn()}
        onOpenArtifact={vi.fn()}
        onApprove={onApprove}
        onReject={vi.fn().mockResolvedValue(undefined)}
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Requirement elicitation')).toBeInTheDocument()
    await user.click(screen.getByLabelText('Single MVP slice'))
    await user.clear(screen.getByLabelText('What hard boundaries must the team keep?'))
    await user.type(screen.getByLabelText('What hard boundaries must the team keep?'), 'Stay local-first.')
    await user.click(screen.getByRole('button', { name: 'Approve and continue' }))

    expect(onApprove).toHaveBeenCalledWith({
      selectedOptionId: 'elicitation_continue',
      boardComment: 'Approve the recommended option.',
      elicitationAnswers: [
        {
          question_id: 'delivery_scope',
          selected_option_ids: ['scope_mvp_slice'],
          text: '',
        },
        {
          question_id: 'hard_boundaries',
          selected_option_ids: [],
          text: 'Stay local-first.',
        },
      ],
    })
  })

  it('renders advisory context and submits governance patch through modify constraints', async () => {
    const user = userEvent.setup()
    const onModifyConstraints = vi.fn().mockResolvedValue(undefined)

    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_004',
              review_pack_id: 'brp_004',
              review_pack_version: 1,
              workflow_id: 'wf_004',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-15T12:00:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Replan the current delivery branch',
            },
            trigger: {
              trigger_event_id: 'evt_004',
              trigger_reason: 'The board wants a tighter replan baseline.',
              why_now: 'Need an advisory decision before the next pass.',
            },
            recommendation: {
              recommended_action: 'MODIFY_CONSTRAINTS',
              recommended_option_id: 'replan_delivery',
              summary: 'Tighten governance before the next pass.',
            },
            options: [
              {
                option_id: 'replan_delivery',
                label: 'Replan delivery',
                summary: 'Tighten governance before the next pass.',
              },
            ],
            advisory_context: {
              session_id: 'adv_001',
              approval_id: 'apr_004',
              review_pack_id: 'brp_004',
              trigger_type: 'CONSTRAINT_CHANGE',
              status: 'OPEN',
              source_version: 'gv_14',
              governance_profile_ref: 'gp_001',
              affected_nodes: ['node_homepage_visual'],
              decision_pack_refs: [],
              approved_patch_ref: null,
              current_governance_modes: {
                approval_mode: 'AUTO_CEO',
                audit_mode: 'MINIMAL',
              },
              supports_governance_patch: true,
            },
            decision_form: {
              allowed_actions: ['MODIFY_CONSTRAINTS'],
              command_target_version: 1,
              requires_comment_on_reject: true,
              requires_constraint_patch_on_modify: true,
            },
          } as never,
          available_actions: ['MODIFY_CONSTRAINTS'],
          draft_defaults: {
            selected_option_id: 'replan_delivery',
            comment_template: '',
          } as never,
        }}
        inspectorData={null}
        inspectorLoading={false}
        error={null}
        submittingAction={null}
        onClose={vi.fn()}
        onOpenInspector={vi.fn()}
        onOpenArtifact={vi.fn()}
        onApprove={vi.fn().mockResolvedValue(undefined)}
        onReject={vi.fn().mockResolvedValue(undefined)}
        onModifyConstraints={onModifyConstraints}
      />,
    )

    expect(screen.getByText('adv_001')).toBeInTheDocument()
    expect(screen.getByText('AUTO_CEO / MINIMAL')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Approval mode'), 'EXPERT_GATED')
    await user.selectOptions(screen.getByLabelText('Audit mode'), 'FULL_TIMELINE')
    await user.click(screen.getByRole('button', { name: 'Submit constraint changes' }))

    expect(onModifyConstraints).toHaveBeenCalledWith({
      boardComment: 'Apply the updated board constraints.',
      addRules: [],
      removeRules: [],
      replaceRules: [],
      governancePatch: {
        approval_mode: 'EXPERT_GATED',
        audit_mode: 'FULL_TIMELINE',
      },
      elicitationAnswers: undefined,
    })
  })
})
