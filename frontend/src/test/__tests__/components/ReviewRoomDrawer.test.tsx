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

  it('renders advisory context and enters the change flow through modify constraints', async () => {
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
              change_flow_status: 'OPEN',
              source_version: 'gv_14',
              governance_profile_ref: 'gp_001',
              affected_nodes: ['node_homepage_visual'],
              working_turns: [],
              decision_pack_refs: [],
              latest_patch_proposal_ref: null,
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
    await user.click(screen.getByRole('button', { name: 'Enter change flow' }))

    expect(onModifyConstraints).toHaveBeenCalledWith({
      boardComment: 'Enter the advisory change flow with these constraints.',
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

  it('renders drafting turns and requests analysis', async () => {
    const user = userEvent.setup()
    const onAppendAdvisoryTurn = vi.fn().mockResolvedValue(undefined)
    const onRequestAdvisoryAnalysis = vi.fn().mockResolvedValue(undefined)

    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_005',
              review_pack_id: 'brp_005',
              review_pack_version: 1,
              workflow_id: 'wf_005',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-16T12:00:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Draft an advisory patch',
            },
            trigger: {
              trigger_event_id: 'evt_005',
              trigger_reason: 'The board opened a dedicated change flow.',
              why_now: 'Need a structured proposal before runtime import.',
            },
            recommendation: {
              recommended_action: 'MODIFY_CONSTRAINTS',
              recommended_option_id: 'draft_change_flow',
              summary: 'Draft the request, then ask for analysis.',
            },
            options: [],
            advisory_context: {
              session_id: 'adv_005',
              approval_id: 'apr_005',
              review_pack_id: 'brp_005',
              trigger_type: 'CONSTRAINT_CHANGE',
              status: 'DRAFTING',
              change_flow_status: 'DRAFTING',
              source_version: 'gv_22',
              governance_profile_ref: 'gp_005',
              affected_nodes: ['node_homepage_visual'],
              working_turns: [
                {
                  turn_id: 'advturn_001',
                  actor_type: 'board',
                  content: 'Keep the branch frozen until the proposal is reviewed.',
                  created_at: '2026-04-16T12:01:00+08:00',
                },
              ],
              decision_pack_refs: ['pa://decision-summary/adv_005@1'],
              latest_patch_proposal_ref: null,
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
            selected_option_id: 'draft_change_flow',
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
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
        onAppendAdvisoryTurn={onAppendAdvisoryTurn}
        onRequestAdvisoryAnalysis={onRequestAdvisoryAnalysis}
      />,
    )

    expect(screen.getByText('Keep the branch frozen until the proposal is reviewed.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Draft note'), 'Compare the pros and cons before runtime import.')
    await user.click(screen.getByRole('button', { name: 'Add draft note' }))
    expect(onAppendAdvisoryTurn).toHaveBeenCalledWith({
      sessionId: 'adv_005',
      content: 'Compare the pros and cons before runtime import.',
    })
    await user.click(screen.getByRole('button', { name: 'Request analysis' }))
    expect(onRequestAdvisoryAnalysis).toHaveBeenCalledWith({ sessionId: 'adv_005' })
  })

  it('renders a pending advisory analysis state without draft actions', () => {
    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_005b',
              review_pack_id: 'brp_005b',
              review_pack_version: 1,
              workflow_id: 'wf_005b',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-16T12:15:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Wait for the advisory analysis run',
            },
            trigger: {
              trigger_event_id: 'evt_005b',
              trigger_reason: 'The analysis run is executing outside the request transaction.',
              why_now: 'The board needs to wait for the explicit analysis result before confirming a patch.',
            },
            recommendation: {
              recommended_action: 'MODIFY_CONSTRAINTS',
              recommended_option_id: 'draft_change_flow',
              summary: 'Wait for the dedicated advisory analysis run to finish.',
            },
            options: [],
            advisory_context: {
              session_id: 'adv_005b',
              approval_id: 'apr_005b',
              review_pack_id: 'brp_005b',
              trigger_type: 'CONSTRAINT_CHANGE',
              status: 'PENDING_ANALYSIS',
              change_flow_status: 'PENDING_ANALYSIS',
              source_version: 'gv_23',
              governance_profile_ref: 'gp_005b',
              affected_nodes: ['node_homepage_visual'],
              working_turns: [
                {
                  turn_id: 'advturn_005b',
                  actor_type: 'board',
                  content: 'Compare the pros and cons before any patch is proposed.',
                  created_at: '2026-04-16T12:16:00+08:00',
                },
              ],
              decision_pack_refs: ['pa://decision-summary/adv_005b@1'],
              latest_patch_proposal_ref: null,
              approved_patch_ref: null,
              latest_analysis_run_id: 'adrun_005b',
              latest_analysis_status: 'RUNNING',
              latest_analysis_error: null,
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
            selected_option_id: 'draft_change_flow',
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
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
        onAppendAdvisoryTurn={vi.fn().mockResolvedValue(undefined)}
        onRequestAdvisoryAnalysis={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText(/analysis is running for the current advisory draft/i)).toBeInTheDocument()
    expect(screen.getByText('adrun_005b')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add draft note' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request analysis' })).not.toBeInTheDocument()
  })

  it('renders proposal confirmation and applies the approved runtime patch', async () => {
    const user = userEvent.setup()
    const onApplyAdvisoryPatch = vi.fn().mockResolvedValue(undefined)

    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_006',
              review_pack_id: 'brp_006',
              review_pack_version: 1,
              workflow_id: 'wf_006',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-16T12:20:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Confirm the advisory patch',
            },
            trigger: {
              trigger_event_id: 'evt_006',
              trigger_reason: 'Analysis finished and the board can confirm the patch.',
              why_now: 'Need final confirmation before runtime import.',
            },
            recommendation: {
              recommended_action: 'MODIFY_CONSTRAINTS',
              recommended_option_id: 'confirm_patch',
              summary: 'Review the pros and cons, then import the patch.',
            },
            options: [],
            advisory_context: {
              session_id: 'adv_006',
              approval_id: 'apr_006',
              review_pack_id: 'brp_006',
              trigger_type: 'CONSTRAINT_CHANGE',
              status: 'PENDING_BOARD_CONFIRMATION',
              change_flow_status: 'PENDING_BOARD_CONFIRMATION',
              source_version: 'gv_24',
              governance_profile_ref: 'gp_006',
              affected_nodes: ['node_homepage_visual'],
              working_turns: [],
              decision_pack_refs: [
                'pa://decision-summary/adv_006@1',
                'pa://graph-patch-proposal/adv_006@1',
              ],
              latest_patch_proposal_ref: 'pa://graph-patch-proposal/adv_006@1',
              approved_patch_ref: null,
              proposal_summary: 'Freeze the affected branch and rerun CEO after board confirmation.',
              pros: ['Keeps runtime changes gated until the board confirms the patch.'],
              cons: ['The branch stays blocked until the next replan pass.'],
              risk_alerts: ['The current proposal freezes the affected node.'],
              impact_summary: 'Freeze 1 affected node and focus the next CEO pass on it.',
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
            selected_option_id: 'confirm_patch',
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
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
        onApplyAdvisoryPatch={onApplyAdvisoryPatch}
      />,
    )

    expect(screen.getByText('Freeze the affected branch and rerun CEO after board confirmation.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve runtime patch' }))
    expect(onApplyAdvisoryPatch).toHaveBeenCalledWith({
      sessionId: 'adv_006',
      proposalRef: 'pa://graph-patch-proposal/adv_006@1',
    })
  })

  it('renders advisory archive actions when full timeline refs are present', async () => {
    const user = userEvent.setup()
    const onOpenArtifact = vi.fn()

    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_007',
              review_pack_id: 'brp_007',
              review_pack_version: 1,
              workflow_id: 'wf_007',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-16T12:30:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Inspect the archived advisory transcript',
            },
            trigger: {
              trigger_event_id: 'evt_007',
              trigger_reason: 'The board wants a full advisory archive before import.',
              why_now: 'Need quick access to the transcript and timeline index.',
            },
            recommendation: {
              recommended_action: 'MODIFY_CONSTRAINTS',
              recommended_option_id: 'inspect_archive',
              summary: 'Review the archived advisory transcript first.',
            },
            options: [],
            advisory_context: {
              session_id: 'adv_007',
              approval_id: 'apr_007',
              review_pack_id: 'brp_007',
              trigger_type: 'CONSTRAINT_CHANGE',
              status: 'PENDING_BOARD_CONFIRMATION',
              change_flow_status: 'PENDING_BOARD_CONFIRMATION',
              source_version: 'gv_30',
              governance_profile_ref: 'gp_007',
              affected_nodes: ['node_homepage_visual'],
              working_turns: [],
              decision_pack_refs: ['pa://decision-summary/adv_007@1'],
              latest_patch_proposal_ref: 'pa://graph-patch-proposal/adv_007@1',
              approved_patch_ref: null,
              latest_timeline_index_ref: 'pa://timeline-index/adv_007@3',
              latest_transcript_archive_artifact_ref: 'art://board-advisory/wf_007/adv_007/transcript-v3.json',
              timeline_archive_version_int: 3,
              current_governance_modes: {
                approval_mode: 'EXPERT_GATED',
                audit_mode: 'FULL_TIMELINE',
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
            selected_option_id: 'inspect_archive',
            comment_template: '',
          } as never,
        }}
        inspectorData={null}
        inspectorLoading={false}
        error={null}
        submittingAction={null}
        onClose={vi.fn()}
        onOpenInspector={vi.fn()}
        onOpenArtifact={onOpenArtifact}
        onApprove={vi.fn().mockResolvedValue(undefined)}
        onReject={vi.fn().mockResolvedValue(undefined)}
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Archive version')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open transcript archive' }))
    await user.click(screen.getByRole('button', { name: 'Open timeline index' }))

    expect(onOpenArtifact).toHaveBeenNthCalledWith(
      1,
      'art://board-advisory/wf_007/adv_007/transcript-v3.json',
    )
    expect(onOpenArtifact).toHaveBeenNthCalledWith(
      2,
      'art://board-advisory/wf_007/adv_007/timeline-index-v3.json',
    )
  })

  it('hides advisory archive actions when full timeline refs are absent', () => {
    render(
      <ReviewRoomDrawer
        isOpen
        loading={false}
        reviewData={{
          review_pack: {
            meta: {
              approval_id: 'apr_008',
              review_pack_id: 'brp_008',
              review_pack_version: 1,
              workflow_id: 'wf_008',
              review_type: 'VISUAL_MILESTONE',
              created_at: '2026-04-16T12:40:00+08:00',
              priority: 'high',
            },
            subject: {
              title: 'Draft without archive refs',
            },
            trigger: {
              trigger_event_id: 'evt_008',
              trigger_reason: 'Still drafting the change flow.',
              why_now: 'No archive has been materialized yet.',
            },
            recommendation: {
              recommended_action: 'MODIFY_CONSTRAINTS',
              recommended_option_id: 'draft_without_archive',
              summary: 'Keep drafting before archive output exists.',
            },
            options: [],
            advisory_context: {
              session_id: 'adv_008',
              approval_id: 'apr_008',
              review_pack_id: 'brp_008',
              trigger_type: 'CONSTRAINT_CHANGE',
              status: 'DRAFTING',
              change_flow_status: 'DRAFTING',
              source_version: 'gv_31',
              governance_profile_ref: 'gp_008',
              affected_nodes: ['node_homepage_visual'],
              working_turns: [],
              decision_pack_refs: ['pa://decision-summary/adv_008@1'],
              latest_patch_proposal_ref: null,
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
            selected_option_id: 'draft_without_archive',
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
        onModifyConstraints={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Open transcript archive' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open timeline index' })).not.toBeInTheDocument()
  })
})
