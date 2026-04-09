import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProviderSettingsDrawer } from '../../../components/overlays/ProviderSettingsDrawer'

function buildProviderData(baseUrl: string) {
  return {
    mode: 'OPENAI_RESPONSES_STREAM',
    effective_mode: 'OPENAI_RESPONSES_STREAM_LIVE',
    provider_health_summary: 'HEALTHY',
    provider_id: 'prov_primary',
    base_url: baseUrl,
    alias: 'example',
    model: 'gpt-5.3-codex',
    max_context_window: 1000000,
    timeout_sec: 30,
    reasoning_effort: 'high',
    api_key_configured: true,
    api_key_masked: 'sk-***cret',
    configured_worker_count: 1,
    effective_reason: 'example is ready with streaming Responses.',
    default_provider_id: 'prov_primary',
    providers: [
      {
        provider_id: 'prov_primary',
        type: 'openai_responses_stream',
        adapter_kind: 'openai_compat',
        label: 'example',
        alias: 'example',
        enabled: true,
        base_url: baseUrl,
        api_key_configured: true,
        api_key_masked: 'sk-***cret',
        model: 'gpt-5.3-codex',
        preferred_model: 'gpt-5.3-codex',
        max_context_window: 1000000,
        timeout_sec: 30,
        reasoning_effort: 'high',
        command_path: null,
        capability_tags: ['structured_output', 'planning', 'implementation', 'review'],
        cost_tier: 'standard',
        participation_policy: 'always_allowed',
        fallback_provider_ids: [],
        health_status: 'HEALTHY',
        health_reason: 'example is ready with streaming Responses.',
        configured_worker_count: 1,
        is_default: true,
      },
    ],
    provider_model_entries: [
      {
        entry_ref: 'prov_primary::gpt-5.3-codex',
        provider_id: 'prov_primary',
        provider_label: 'example',
        model_name: 'gpt-5.3-codex',
        max_context_window: 1000000,
      },
    ],
    role_bindings: [
      {
        target_ref: 'ceo_shadow',
        target_label: 'CEO Shadow',
        provider_model_entry_refs: ['prov_primary::gpt-5.3-codex'],
        max_context_window_override: null,
        reasoning_effort_override: null,
      },
    ],
    future_binding_slots: [],
  } as const
}

describe('ProviderSettingsDrawer persistence', () => {
  it('keeps unsaved provider draft input when parent projection refreshes while drawer is open', async () => {
    const user = userEvent.setup()
    const commonProps = {
      isOpen: true,
      loading: false,
      error: null,
      submitting: false,
      onClose: vi.fn(),
      onSave: vi.fn().mockResolvedValue(undefined),
      onConnectivityTest: vi.fn().mockResolvedValue({ ok: true, resolved_provider: null, response_id: null }),
      onRefreshModels: vi.fn().mockResolvedValue([]),
    }
    const { rerender } = render(
      <ProviderSettingsDrawer
        {...commonProps}
        providerData={buildProviderData('https://api.example.test/v1')}
      />,
    )

    await user.clear(screen.getByLabelText('Provider base URL prov_primary'))
    await user.type(screen.getByLabelText('Provider base URL prov_primary'), 'https://draft.example.test/v1')
    await user.type(screen.getByLabelText('Provider API key prov_primary'), 'sk-local-draft')
    await user.selectOptions(screen.getByLabelText('Provider reasoning effort prov_primary'), 'xhigh')

    rerender(
      <ProviderSettingsDrawer
        {...commonProps}
        providerData={buildProviderData('https://api.example.test/v1')}
      />,
    )

    expect(screen.getByLabelText('Provider base URL prov_primary')).toHaveValue('https://draft.example.test/v1')
    expect(screen.getByLabelText('Provider API key prov_primary')).toHaveValue('sk-local-draft')
    expect(screen.getByLabelText('Provider reasoning effort prov_primary')).toHaveValue('xhigh')
  })
})
