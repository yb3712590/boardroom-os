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
          role_templates_catalog: {
            role_templates: [
              {
                template_id: 'frontend_delivery_primary',
                template_kind: 'live_execution',
                label: 'Frontend Engineer / 实施交付',
                role_family: 'frontend_uiux',
                role_type: 'frontend_engineer',
                canonical_role_ref: 'frontend_engineer_primary',
                alias_role_profile_refs: [],
                provider_target_ref: 'role_profile:frontend_engineer_primary',
                participation_mode: 'HIGH_FREQUENCY_DELIVERY',
                execution_boundary: '负责当前主线 BUILD / REVIEW / closeout 的前端实施与交付整理。',
                status: 'LIVE',
                default_document_kind_refs: ['detailed_design'],
                responsibility_summary: '承担前端实施、交付整理和视觉落地。',
                summary: 'Own the thin boardroom shell implementation path.',
                composition: {
                  fragment_refs: ['skill_frontend_ui', 'delivery_execution_loop'],
                },
                mainline_boundary: {
                  boundary_status: 'LIVE_ON_MAINLINE',
                  active_path_refs: ['catalog_readonly', 'governance_document_live', 'implementation_delivery'],
                  blocked_path_refs: [],
                },
              },
              {
                template_id: 'backend_execution_reserved',
                template_kind: 'reserved_execution',
                label: 'Backend Engineer / 服务交付',
                role_family: 'backend_engineer',
                role_type: 'backend_engineer',
                canonical_role_ref: 'backend_engineer_primary',
                alias_role_profile_refs: [],
                provider_target_ref: 'role_profile:backend_engineer_primary',
                participation_mode: 'HIGH_FREQUENCY_DELIVERY',
                execution_boundary: '已定义为未来执行角色，但当前不进入主线 staffing 或 runtime。',
                status: 'NOT_ENABLED',
                default_document_kind_refs: ['detailed_design'],
                responsibility_summary: '负责服务实现、接口落地和集成切片。',
                summary: 'Reserved for future service delivery slices.',
                composition: {
                  fragment_refs: ['skill_backend_services', 'delivery_execution_loop'],
                },
                mainline_boundary: {
                  boundary_status: 'CATALOG_ONLY',
                  active_path_refs: ['catalog_readonly', 'provider_future_slot'],
                  blocked_path_refs: ['staffing', 'ceo_create_ticket', 'runtime_execution', 'workforce_lane'],
                },
              },
              {
                template_id: 'cto_governance',
                template_kind: 'governance',
                label: 'CTO / 架构治理',
                role_family: 'cto',
                role_type: 'governance_cto',
                canonical_role_ref: 'cto_primary',
                alias_role_profile_refs: [],
                provider_target_ref: 'role_profile:cto_primary',
                participation_mode: 'LOW_FREQUENCY_HIGH_LEVERAGE',
                execution_boundary: '默认不承担日常编码、测试或持续实施主力工作。',
                status: 'NOT_ENABLED',
                default_document_kind_refs: ['architecture_brief', 'technology_decision'],
                responsibility_summary: '负责高杠杆架构决策、治理边界和路线判断。',
                summary: 'Own high-leverage architecture and governance decisions.',
                composition: {
                  fragment_refs: ['skill_architecture_governance', 'delivery_document_first'],
                },
                mainline_boundary: {
                  boundary_status: 'CATALOG_ONLY',
                  active_path_refs: ['catalog_readonly', 'provider_future_slot'],
                  blocked_path_refs: ['staffing', 'ceo_create_ticket', 'runtime_execution', 'workforce_lane'],
                },
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
            fragments: [
              {
                fragment_id: 'skill_frontend_ui',
                fragment_kind: 'skill_domain',
                label: 'Frontend / UI',
                summary: 'Focus on the boardroom shell and UI delivery details.',
                payload: {
                  primary_domain: 'frontend',
                },
              },
              {
                fragment_id: 'skill_backend_services',
                fragment_kind: 'skill_domain',
                label: 'Backend services',
                summary: 'Focus on API, orchestration and service integration work.',
                payload: {
                  primary_domain: 'backend',
                },
              },
              {
                fragment_id: 'skill_architecture_governance',
                fragment_kind: 'skill_domain',
                label: 'Architecture governance',
                summary: 'Focus on architecture framing and key decision tradeoffs.',
                payload: {
                  decision_scope: 'architecture',
                },
              },
              {
                fragment_id: 'delivery_execution_loop',
                fragment_kind: 'delivery_mode',
                label: 'Execution loop',
                summary: 'Optimized for frequent implementation and rework loops.',
                payload: {
                  default_mode: 'execution',
                },
              },
              {
                fragment_id: 'delivery_document_first',
                fragment_kind: 'delivery_mode',
                label: 'Document first',
                summary: 'Optimized for low-frequency, document-led participation.',
                payload: {
                  default_mode: 'document',
                },
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
                  source_template_id: 'frontend_delivery_primary',
                  source_fragment_refs: ['skill_frontend_ui', 'delivery_execution_loop'],
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
    expect(screen.getByText('Role template catalog')).toBeInTheDocument()
    expect(screen.getByText('Live execution templates')).toBeInTheDocument()
    expect(screen.getByText('Reserved execution templates')).toBeInTheDocument()
    expect(screen.getByText('Governance templates')).toBeInTheDocument()
    expect(
      screen.getByText(/Source template frontend_delivery_primary.*Execution loop/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/CTO \/ 架构治理/i)).toBeInTheDocument()
    expect(screen.getByText(/Backend Engineer \/ 服务交付/i)).toBeInTheDocument()
    expect(screen.getByText(/architecture_brief/i)).toBeInTheDocument()
    expect(screen.getByText(/Current live path/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Catalog only \/ not on current mainline/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/implementation delivery/i)).toBeInTheDocument()
    expect(screen.getAllByText(/blocked: staffing, ceo create ticket, runtime execution, workforce lane/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/not_enabled/i).length).toBeGreaterThan(0)
  })
})
