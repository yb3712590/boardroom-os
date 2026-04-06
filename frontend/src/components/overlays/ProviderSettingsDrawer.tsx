import { useEffect, useState } from 'react'

import type { RuntimeProviderData, RuntimeProviderRoleBinding } from '../../types/api'
import { Drawer } from '../shared/Drawer'

const OPENAI_PROVIDER_ID = 'prov_openai_compat'
const CLAUDE_PROVIDER_ID = 'prov_claude_code'

const CURRENT_ROLE_TARGETS = [
  { target_ref: 'ceo_shadow', target_label: 'CEO Shadow' },
  { target_ref: 'role_profile:ui_designer_primary', target_label: 'Scope Consensus' },
  { target_ref: 'role_profile:frontend_engineer_primary', target_label: 'Frontend Engineer' },
  { target_ref: 'role_profile:checker_primary', target_label: 'Checker' },
]

type EditableRoleBinding = {
  target_ref: string
  target_label: string
  provider_id: string
  model: string
}

type ProviderSettingsDrawerProps = {
  isOpen: boolean
  providerData: RuntimeProviderData | null
  loading: boolean
  error: string | null
  submitting: boolean
  onClose: () => void
  onSave: (input: {
    defaultProviderId: string | null
    providers: Array<{
      provider_id: string
      adapter_kind: string
      label: string
      enabled: boolean
      base_url: string | null
      api_key: string | null
      model: string | null
      timeout_sec: number
      reasoning_effort: string | null
      command_path: string | null
    }>
    roleBindings: Array<{
      target_ref: string
      provider_id: string
      model: string | null
    }>
  }) => Promise<void>
}

function providerBindingMap(bindings: RuntimeProviderRoleBinding[] | undefined) {
  return new Map((bindings ?? []).map((binding) => [binding.target_ref, binding]))
}

function buildEditableBindings(providerData: RuntimeProviderData | null): EditableRoleBinding[] {
  const bindingByRef = providerBindingMap(providerData?.role_bindings)
  return CURRENT_ROLE_TARGETS.map((target) => {
    const binding = bindingByRef.get(target.target_ref)
    return {
      target_ref: target.target_ref,
      target_label: target.target_label,
      provider_id: binding?.provider_id ?? '',
      model: binding?.model ?? '',
    }
  })
}

export function ProviderSettingsDrawer({
  isOpen,
  providerData,
  loading,
  error,
  submitting,
  onClose,
  onSave,
}: ProviderSettingsDrawerProps) {
  const openaiProvider = providerData?.providers.find((provider) => provider.provider_id === OPENAI_PROVIDER_ID)
  const claudeProvider = providerData?.providers.find((provider) => provider.provider_id === CLAUDE_PROVIDER_ID)

  const [mode, setMode] = useState(providerData?.mode ?? 'DETERMINISTIC')
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState(openaiProvider?.base_url ?? '')
  const [openaiApiKey, setOpenaiApiKey] = useState('')
  const [openaiModel, setOpenaiModel] = useState(openaiProvider?.model ?? '')
  const [openaiTimeoutSec, setOpenaiTimeoutSec] = useState(String(openaiProvider?.timeout_sec ?? 30))
  const [openaiReasoningEffort, setOpenaiReasoningEffort] = useState(openaiProvider?.reasoning_effort ?? '')
  const [claudeCommandPath, setClaudeCommandPath] = useState(claudeProvider?.command_path ?? '')
  const [claudeModel, setClaudeModel] = useState(claudeProvider?.model ?? '')
  const [claudeTimeoutSec, setClaudeTimeoutSec] = useState(String(claudeProvider?.timeout_sec ?? 30))
  const [roleBindings, setRoleBindings] = useState<EditableRoleBinding[]>(buildEditableBindings(providerData))

  useEffect(() => {
    if (!isOpen) {
      return
    }
    const nextOpenaiProvider = providerData?.providers.find((provider) => provider.provider_id === OPENAI_PROVIDER_ID)
    const nextClaudeProvider = providerData?.providers.find((provider) => provider.provider_id === CLAUDE_PROVIDER_ID)
    setMode(providerData?.mode ?? 'DETERMINISTIC')
    setOpenaiBaseUrl(nextOpenaiProvider?.base_url ?? '')
    setOpenaiApiKey('')
    setOpenaiModel(nextOpenaiProvider?.model ?? '')
    setOpenaiTimeoutSec(String(nextOpenaiProvider?.timeout_sec ?? 30))
    setOpenaiReasoningEffort(nextOpenaiProvider?.reasoning_effort ?? '')
    setClaudeCommandPath(nextClaudeProvider?.command_path ?? '')
    setClaudeModel(nextClaudeProvider?.model ?? '')
    setClaudeTimeoutSec(String(nextClaudeProvider?.timeout_sec ?? 30))
    setRoleBindings(buildEditableBindings(providerData))
  }, [isOpen, providerData])

  const updateBinding = (targetRef: string, patch: Partial<EditableRoleBinding>) => {
    setRoleBindings((current) =>
      current.map((binding) => (binding.target_ref === targetRef ? { ...binding, ...patch } : binding)),
    )
  }

  const handleSave = () => {
    const selectedProviderIds = new Set(
      roleBindings.map((binding) => binding.provider_id).filter((providerId) => providerId.length > 0),
    )
    const defaultProviderId =
      mode === 'OPENAI_COMPAT' ? OPENAI_PROVIDER_ID : mode === 'CLAUDE_CODE_CLI' ? CLAUDE_PROVIDER_ID : null
    if (defaultProviderId) {
      selectedProviderIds.add(defaultProviderId)
    }

    void onSave({
      defaultProviderId,
      providers: [
        {
          provider_id: OPENAI_PROVIDER_ID,
          adapter_kind: 'openai_compat',
          label: 'OpenAI Compat',
          enabled:
            selectedProviderIds.has(OPENAI_PROVIDER_ID) ||
            Boolean(openaiBaseUrl.trim() || openaiModel.trim() || openaiApiKey.trim()),
          base_url: openaiBaseUrl.trim() || null,
          api_key: openaiApiKey.trim() || null,
          model: openaiModel.trim() || null,
          timeout_sec: Number.parseFloat(openaiTimeoutSec) || 30,
          reasoning_effort: openaiReasoningEffort || null,
          command_path: null,
        },
        {
          provider_id: CLAUDE_PROVIDER_ID,
          adapter_kind: 'claude_code_cli',
          label: 'Claude Code CLI',
          enabled:
            selectedProviderIds.has(CLAUDE_PROVIDER_ID) || Boolean(claudeCommandPath.trim() || claudeModel.trim()),
          base_url: null,
          api_key: null,
          model: claudeModel.trim() || null,
          timeout_sec: Number.parseFloat(claudeTimeoutSec) || 30,
          reasoning_effort: null,
          command_path: claudeCommandPath.trim() || null,
        },
      ],
      roleBindings: roleBindings
        .filter((binding) => binding.provider_id.length > 0)
        .map((binding) => ({
          target_ref: binding.target_ref,
          provider_id: binding.provider_id,
          model: binding.model.trim() || null,
        })),
    })
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Runtime provider" subtitle="Runtime">
      <p className="muted-copy">
        Manage the local provider registry, choose the default runtime path, and bind the current live roles to
        OpenAI Compat or Claude Code CLI without leaving the boardroom shell.
      </p>

      {loading ? (
        <div className="review-room-state">Loading runtime provider...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">Effective mode</span>
              <p>{providerData?.effective_mode ?? 'Unknown'}</p>
            </div>
            <div>
              <span className="eyebrow">Health</span>
              <p>{providerData?.provider_health_summary ?? 'Unknown'}</p>
            </div>
            <div>
              <span className="eyebrow">Default provider</span>
              <p>{providerData?.default_provider_id ?? 'Local deterministic only'}</p>
            </div>
            <div>
              <span className="eyebrow">Workers</span>
              <p>{providerData?.configured_worker_count ?? 0}</p>
            </div>
          </section>
          <p className="muted-copy">{providerData?.effective_reason ?? 'Runtime provider state is not available.'}</p>

          <section className="review-room-action-panel provider-settings-panel">
            <label>
              <span className="field-label">Provider mode</span>
              <select
                aria-label="Provider mode"
                value={mode}
                onChange={(event) => setMode(event.target.value)}
                disabled={submitting}
              >
                <option value="DETERMINISTIC">Deterministic</option>
                <option value="OPENAI_COMPAT">OpenAI Compat</option>
                <option value="CLAUDE_CODE_CLI">Claude Code CLI</option>
              </select>
            </label>

            <section className="review-room-overview">
              <div>
                <span className="eyebrow">OpenAI key</span>
                <p>{openaiProvider?.api_key_masked ?? 'No key saved'}</p>
              </div>
              <div>
                <span className="eyebrow">Claude command</span>
                <p>{claudeProvider?.command_path ?? 'Not configured'}</p>
              </div>
              <div>
                <span className="eyebrow">OpenAI workers</span>
                <p>{openaiProvider?.configured_worker_count ?? 0}</p>
              </div>
              <div>
                <span className="eyebrow">Claude workers</span>
                <p>{claudeProvider?.configured_worker_count ?? 0}</p>
              </div>
            </section>

            <label>
              <span className="field-label">OpenAI Base URL</span>
              <input
                aria-label="OpenAI Base URL"
                value={openaiBaseUrl}
                onChange={(event) => setOpenaiBaseUrl(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">OpenAI API key</span>
              <input
                aria-label="OpenAI API key"
                type="password"
                value={openaiApiKey}
                placeholder={openaiProvider?.api_key_masked ?? ''}
                onChange={(event) => setOpenaiApiKey(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">OpenAI model</span>
              <input
                aria-label="OpenAI model"
                value={openaiModel}
                onChange={(event) => setOpenaiModel(event.target.value)}
              />
            </label>
            <div className="provider-settings-grid">
              <label>
                <span className="field-label">OpenAI timeout (sec)</span>
                <input
                  aria-label="OpenAI timeout (sec)"
                  type="number"
                  min="1"
                  value={openaiTimeoutSec}
                  onChange={(event) => setOpenaiTimeoutSec(event.target.value)}
                />
              </label>
              <label>
                <span className="field-label">OpenAI reasoning effort</span>
                <select
                  aria-label="OpenAI reasoning effort"
                  value={openaiReasoningEffort}
                  onChange={(event) => setOpenaiReasoningEffort(event.target.value)}
                >
                  <option value="">Default</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="xhigh">XHigh</option>
                </select>
              </label>
            </div>

            <label>
              <span className="field-label">Claude command path</span>
              <input
                aria-label="Claude command path"
                value={claudeCommandPath}
                onChange={(event) => setClaudeCommandPath(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">Claude model</span>
              <input
                aria-label="Claude model"
                value={claudeModel}
                onChange={(event) => setClaudeModel(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">Claude timeout (sec)</span>
              <input
                aria-label="Claude timeout (sec)"
                type="number"
                min="1"
                value={claudeTimeoutSec}
                onChange={(event) => setClaudeTimeoutSec(event.target.value)}
              />
            </label>

            <div>
              <span className="field-label">Current role bindings</span>
              <div className="provider-settings-grid">
                {roleBindings.map((binding) => (
                  <label key={binding.target_ref}>
                    <span className="field-label">{binding.target_label}</span>
                    <select
                      aria-label={`${binding.target_label} provider`}
                      value={binding.provider_id}
                      onChange={(event) => updateBinding(binding.target_ref, { provider_id: event.target.value })}
                    >
                      <option value="">Follow default</option>
                      <option value={OPENAI_PROVIDER_ID}>OpenAI Compat</option>
                      <option value={CLAUDE_PROVIDER_ID}>Claude Code CLI</option>
                    </select>
                    <input
                      aria-label={`${binding.target_label} model override`}
                      value={binding.model}
                      placeholder="Model override (optional)"
                      onChange={(event) => updateBinding(binding.target_ref, { model: event.target.value })}
                    />
                  </label>
                ))}
              </div>
            </div>

            {providerData?.future_binding_slots?.length ? (
              <div>
                <span className="field-label">Future governance roles</span>
                <div className="provider-settings-grid">
                  {providerData.future_binding_slots.map((slot) => (
                    <label key={slot.target_ref}>
                      <span className="field-label">{slot.label}</span>
                      <input aria-label={`${slot.label} status`} value={`${slot.status}: ${slot.reason}`} disabled />
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            <button type="button" className="secondary-button" disabled={submitting} onClick={handleSave}>
              {submitting ? 'Saving...' : 'Save runtime settings'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
