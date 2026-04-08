import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProviderSettingsDrawer } from '../../../components/overlays/ProviderSettingsDrawer'

describe('ProviderSettingsDrawer', () => {
  it('renders reserved bindings as read-only future slots with blocked surfaces', () => {
    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={{
          mode: 'DETERMINISTIC',
          effective_mode: 'LOCAL_DETERMINISTIC',
          provider_health_summary: 'LOCAL_ONLY',
          provider_id: null,
          base_url: null,
          model: null,
          timeout_sec: 30,
          reasoning_effort: null,
          api_key_configured: false,
          api_key_masked: null,
          configured_worker_count: 1,
          effective_reason: 'Runtime is using the local deterministic path.',
          default_provider_id: null,
          providers: [],
          role_bindings: [],
          future_binding_slots: [
            {
              target_ref: 'role_profile:architect_primary',
              label: '架构师 / 设计评审',
              status: 'NOT_ENABLED',
              reason: '角色模板已定义，但尚未纳入当前主线。',
              blocked_path_refs: ['runtime_execution'],
            },
          ],
        }}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Reserved bindings')).toBeInTheDocument()
    expect(screen.getByText(/Catalog-only roles stay read-only here until a later mainline role intake round./i)).toBeInTheDocument()
    expect(screen.getByDisplayValue(/NOT_ENABLED: 角色模板已定义，但尚未纳入当前主线。/i)).toBeDisabled()
    expect(screen.getByText(/Blocked surfaces: runtime execution/i)).toBeInTheDocument()
  })

  it('renders newly live role bindings in the editable current bindings area', () => {
    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={{
          mode: 'DETERMINISTIC',
          effective_mode: 'LOCAL_DETERMINISTIC',
          provider_health_summary: 'LOCAL_ONLY',
          provider_id: null,
          base_url: null,
          model: null,
          timeout_sec: 30,
          reasoning_effort: null,
          api_key_configured: false,
          api_key_masked: null,
          configured_worker_count: 1,
          effective_reason: 'Runtime is using the local deterministic path.',
          default_provider_id: null,
          providers: [],
          role_bindings: [],
          future_binding_slots: [],
        }}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByLabelText('Backend Engineer / 服务交付 provider')).toBeInTheDocument()
    expect(screen.getByLabelText('Database Engineer / 数据可靠性 provider')).toBeInTheDocument()
    expect(screen.getByLabelText('Platform / SRE provider')).toBeInTheDocument()
    expect(screen.getByLabelText('架构师 / 设计评审 provider')).toBeInTheDocument()
    expect(screen.getByLabelText('CTO / 架构治理 provider')).toBeInTheDocument()
    expect(screen.queryByText('Reserved bindings')).not.toBeInTheDocument()
  })

  it('renders cost policy controls and saves them back through onSave', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)

    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={{
          mode: 'OPENAI_COMPAT',
          effective_mode: 'OPENAI_COMPAT_LIVE',
          provider_health_summary: 'HEALTHY',
          provider_id: 'prov_openai_compat',
          base_url: 'https://api.example.test/v1',
          model: 'gpt-5.3-codex',
          timeout_sec: 30,
          reasoning_effort: 'high',
          api_key_configured: true,
          api_key_masked: 'sk-***cret',
          configured_worker_count: 1,
          effective_reason: 'Runtime is using the saved OpenAI-compatible provider config.',
          default_provider_id: 'prov_openai_compat',
          providers: [
            {
              provider_id: 'prov_openai_compat',
              adapter_kind: 'openai_compat',
              label: 'OpenAI Compat',
              enabled: true,
              base_url: 'https://api.example.test/v1',
              api_key_configured: true,
              api_key_masked: 'sk-***cret',
              model: 'gpt-5.3-codex',
              timeout_sec: 30,
              reasoning_effort: 'high',
              command_path: null,
              capability_tags: ['structured_output', 'planning', 'implementation'],
              cost_tier: 'standard',
              participation_policy: 'always_allowed',
              fallback_provider_ids: [],
              health_status: 'HEALTHY',
              health_reason: 'OpenAI-compatible provider is healthy.',
              configured_worker_count: 1,
              is_default: true,
            },
            {
              provider_id: 'prov_claude_code',
              adapter_kind: 'claude_code_cli',
              label: 'Claude Code CLI',
              enabled: true,
              base_url: null,
              api_key_configured: false,
              api_key_masked: null,
              model: 'claude-sonnet-4-6',
              timeout_sec: 30,
              reasoning_effort: null,
              command_path: 'python',
              capability_tags: ['structured_output', 'planning', 'implementation', 'review'],
              cost_tier: 'premium',
              participation_policy: 'low_frequency_only',
              fallback_provider_ids: [],
              health_status: 'HEALTHY',
              health_reason: 'Claude Code CLI provider is healthy.',
              configured_worker_count: 0,
              is_default: false,
            },
          ],
          role_bindings: [],
          future_binding_slots: [],
        }}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    )

    expect(screen.getByLabelText('OpenAI cost tier')).toBeInTheDocument()
    expect(screen.getByLabelText('OpenAI participation policy')).toBeInTheDocument()
    expect(screen.getByLabelText('Claude cost tier')).toBeInTheDocument()
    expect(screen.getByLabelText('Claude participation policy')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Claude participation policy'), 'always_allowed')
    await user.click(screen.getByRole('button', { name: 'Save runtime settings' }))

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          providers: expect.arrayContaining([
            expect.objectContaining({
              provider_id: 'prov_openai_compat',
              cost_tier: 'standard',
              participation_policy: 'always_allowed',
            }),
            expect.objectContaining({
              provider_id: 'prov_claude_code',
              cost_tier: 'premium',
              participation_policy: 'always_allowed',
            }),
          ]),
        }),
      ),
    )
  })
})
