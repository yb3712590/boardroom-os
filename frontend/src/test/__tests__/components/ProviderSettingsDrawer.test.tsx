import { render, screen } from '@testing-library/react'
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
              blocked_path_refs: ['staffing', 'ceo_create_ticket', 'runtime_execution', 'workforce_lane'],
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
    expect(screen.getByText(/Blocked surfaces: staffing, ceo create ticket, runtime execution, workforce lane/i)).toBeInTheDocument()
  })
})
