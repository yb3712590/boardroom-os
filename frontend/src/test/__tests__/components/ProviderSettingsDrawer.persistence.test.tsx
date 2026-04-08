import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProviderSettingsDrawer } from '../../../components/overlays/ProviderSettingsDrawer'

function buildProviderData(baseUrl: string) {
  return {
    mode: 'OPENAI_COMPAT',
    effective_mode: 'OPENAI_COMPAT_LIVE',
    provider_health_summary: 'HEALTHY',
    provider_id: 'prov_openai_compat',
    base_url: baseUrl,
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
        base_url: baseUrl,
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
        enabled: false,
        base_url: null,
        api_key_configured: false,
        api_key_masked: null,
        model: null,
        timeout_sec: 30,
        reasoning_effort: null,
        command_path: null,
        capability_tags: ['structured_output', 'planning', 'implementation', 'review'],
        cost_tier: 'premium',
        participation_policy: 'low_frequency_only',
        fallback_provider_ids: [],
        health_status: 'DISABLED',
        health_reason: 'Claude Code CLI provider is disabled.',
        configured_worker_count: 0,
        is_default: false,
      },
    ],
    role_bindings: [],
    future_binding_slots: [],
  } as const
}

describe('ProviderSettingsDrawer persistence', () => {
  it('keeps unsaved draft input when parent projection refreshes while drawer is open', async () => {
    const user = userEvent.setup()
    const commonProps = {
      isOpen: true,
      loading: false,
      error: null,
      submitting: false,
      onClose: vi.fn(),
      onSave: vi.fn().mockResolvedValue(undefined),
    }
    const { rerender } = render(
      <ProviderSettingsDrawer
        {...commonProps}
        providerData={buildProviderData('https://api.example.test/v1')}
      />,
    )

    await user.clear(screen.getByLabelText('OpenAI Base URL'))
    await user.type(screen.getByLabelText('OpenAI Base URL'), 'https://draft.example.test/v1')
    await user.type(screen.getByLabelText('OpenAI API Key'), 'sk-local-draft')

    rerender(
      <ProviderSettingsDrawer
        {...commonProps}
        providerData={buildProviderData('https://api.example.test/v1')}
      />,
    )

    expect(screen.getByLabelText('OpenAI Base URL')).toHaveValue('https://draft.example.test/v1')
    expect(screen.getByLabelText('OpenAI API Key')).toHaveValue('sk-local-draft')
  })
})
