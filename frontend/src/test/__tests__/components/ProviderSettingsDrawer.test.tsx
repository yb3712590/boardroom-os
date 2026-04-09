import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProviderSettingsDrawer } from '../../../components/overlays/ProviderSettingsDrawer'

function buildProviderData() {
  return {
    mode: 'OPENAI_RESPONSES_STREAM',
    effective_mode: 'OPENAI_RESPONSES_STREAM_LIVE',
    provider_health_summary: 'HEALTHY',
    provider_id: 'prov_primary',
    base_url: 'https://api.example.test/v1',
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
        base_url: 'https://api.example.test/v1',
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
      {
        target_ref: 'role_profile:frontend_engineer_primary',
        target_label: 'Frontend Engineer',
        provider_model_entry_refs: [],
        max_context_window_override: 180000,
        reasoning_effort_override: 'medium',
      },
    ],
    future_binding_slots: [],
  } as const
}

describe('ProviderSettingsDrawer', () => {
  it('renders multiple providers and role window overrides', () => {
    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={buildProviderData()}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
        onConnectivityTest={vi.fn().mockResolvedValue({ ok: true, resolved_provider: null, response_id: null })}
        onRefreshModels={vi.fn().mockResolvedValue([])}
      />,
    )

    expect(screen.getByRole('button', { name: /add provider/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Provider alias prov_primary')).toHaveValue('example')
    expect(screen.getByLabelText('Provider reasoning effort prov_primary')).toHaveValue('high')
    expect(screen.getByLabelText('CEO Shadow context window override')).toHaveValue(null)
    expect(screen.getByLabelText('CEO Shadow reasoning effort override')).toHaveValue('inherit')
    expect(screen.getByLabelText('Frontend Engineer context window override')).toHaveValue(180000)
    expect(screen.getByLabelText('Frontend Engineer reasoning effort override')).toHaveValue('medium')
  })

  it('applies connectivity fallback result before save', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onConnectivityTest = vi.fn().mockResolvedValue({
      ok: true,
      response_id: 'resp_connectivity',
      resolved_provider: {
        provider_id: 'prov_primary',
        type: 'openai_responses_non_stream',
        base_url: 'https://api.example.test/v1',
        alias: 'example',
        preferred_model: 'gpt-5.3-codex',
        max_context_window: 1000000,
        reasoning_effort: 'high',
        enabled: true,
      },
    })

    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={buildProviderData()}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={onSave}
        onConnectivityTest={onConnectivityTest}
        onRefreshModels={vi.fn().mockResolvedValue([])}
      />,
    )

    await user.click(screen.getByRole('button', { name: /test prov_primary connectivity/i }))
    await waitFor(() =>
      expect(screen.getByLabelText('Provider type prov_primary')).toHaveValue('openai_responses_non_stream'),
    )
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          providers: expect.arrayContaining([
            expect.objectContaining({
              provider_id: 'prov_primary',
              type: 'openai_responses_non_stream',
              reasoning_effort: 'high',
            }),
          ]),
        }),
      ),
    )
  })

  it('loads provider models and submits only selected model entries', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onRefreshModels = vi.fn().mockResolvedValue(['gpt-4.1', 'gpt-5.3-codex'])

    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={buildProviderData()}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={onSave}
        onConnectivityTest={vi.fn().mockResolvedValue({ ok: true, resolved_provider: null, response_id: null })}
        onRefreshModels={onRefreshModels}
      />,
    )

    await user.click(screen.getByRole('button', { name: /load models for prov_primary/i }))
    await user.click(screen.getByLabelText('Model gpt-4.1 for prov_primary'))
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          providerModelEntries: expect.arrayContaining([
            { provider_id: 'prov_primary', model_name: 'gpt-4.1' },
            { provider_id: 'prov_primary', model_name: 'gpt-5.3-codex' },
          ]),
        }),
      ),
    )
  })

  it('submits provider reasoning effort and role reasoning override', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)

    render(
      <ProviderSettingsDrawer
        isOpen
        providerData={buildProviderData()}
        loading={false}
        error={null}
        submitting={false}
        onClose={vi.fn()}
        onSave={onSave}
        onConnectivityTest={vi.fn().mockResolvedValue({ ok: true, resolved_provider: null, response_id: null })}
        onRefreshModels={vi.fn().mockResolvedValue([])}
      />,
    )

    await user.selectOptions(screen.getByLabelText('Provider reasoning effort prov_primary'), 'xhigh')
    await user.selectOptions(screen.getByLabelText('CEO Shadow reasoning effort override'), 'high')
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          providers: expect.arrayContaining([
            expect.objectContaining({
              provider_id: 'prov_primary',
              reasoning_effort: 'xhigh',
            }),
          ]),
          roleBindings: expect.arrayContaining([
            expect.objectContaining({
              target_ref: 'ceo_shadow',
              reasoning_effort_override: 'high',
            }),
            expect.objectContaining({
              target_ref: 'role_profile:frontend_engineer_primary',
              reasoning_effort_override: 'medium',
            }),
          ]),
        }),
      ),
    )
  })
})
