import { useEffect, useRef, useState } from 'react'

import type {
  RuntimeProviderConfigRequest,
  RuntimeProviderConnectivityTestResult,
  RuntimeProviderData,
  RuntimeProviderModelEntry,
} from '../../types/api'
import { Drawer } from '../shared/Drawer'

const CURRENT_ROLE_TARGETS = [
  { target_ref: 'ceo_shadow', target_label: 'CEO Shadow' },
  { target_ref: 'role_profile:ui_designer_primary', target_label: 'Scope Consensus' },
  { target_ref: 'role_profile:frontend_engineer_primary', target_label: 'Frontend Engineer' },
  { target_ref: 'role_profile:checker_primary', target_label: 'Checker' },
  { target_ref: 'role_profile:backend_engineer_primary', target_label: 'Backend Engineer / Service Delivery' },
  { target_ref: 'role_profile:database_engineer_primary', target_label: 'Database Engineer / Data Reliability' },
  { target_ref: 'role_profile:platform_sre_primary', target_label: 'Platform / SRE' },
  { target_ref: 'role_profile:architect_primary', target_label: 'Architect / Design Review' },
  { target_ref: 'role_profile:cto_primary', target_label: 'CTO / Architecture Governance' },
] as const

type EditableProvider = {
  provider_id: string
  type: string
  base_url: string
  api_key: string
  alias: string
  preferred_model: string
  max_context_window: string
  enabled: boolean
}

type EditableRoleBinding = {
  target_ref: string
  target_label: string
  provider_model_entry_refs: string[]
  max_context_window_override: string
}

type ProviderSettingsDrawerProps = {
  isOpen: boolean
  providerData: RuntimeProviderData | null
  loading: boolean
  error: string | null
  submitting: boolean
  onClose: () => void
  onSave: (input: {
    providers: RuntimeProviderConfigRequest[]
    providerModelEntries: Array<{
      provider_id: string
      model_name: string
    }>
    roleBindings: Array<{
      target_ref: string
      provider_model_entry_refs: string[]
      max_context_window_override: number | null
    }>
  }) => Promise<void>
  onConnectivityTest: (
    provider: RuntimeProviderConfigRequest,
  ) => Promise<RuntimeProviderConnectivityTestResult>
  onRefreshModels: (providerId: string) => Promise<string[]>
}

function buildEditableProviders(providerData: RuntimeProviderData | null): EditableProvider[] {
  if (!providerData?.providers.length) {
    return []
  }
  return providerData.providers.map((provider) => ({
    provider_id: provider.provider_id,
    type: provider.type,
    base_url: provider.base_url ?? '',
    api_key: '',
    alias: provider.alias ?? '',
    preferred_model: provider.preferred_model ?? provider.model ?? '',
    max_context_window: String(provider.max_context_window ?? ''),
    enabled: provider.enabled,
  }))
}

function buildEditableBindings(providerData: RuntimeProviderData | null): EditableRoleBinding[] {
  const bindingMap = new Map((providerData?.role_bindings ?? []).map((binding) => [binding.target_ref, binding]))
  return CURRENT_ROLE_TARGETS.map((target) => {
    const binding = bindingMap.get(target.target_ref)
    return {
      target_ref: target.target_ref,
      target_label: target.target_label,
      provider_model_entry_refs: Array.from(binding?.provider_model_entry_refs ?? []),
      max_context_window_override:
        binding?.max_context_window_override == null ? '' : String(binding.max_context_window_override),
    }
  })
}

function buildSelectedEntryMap(providerData: RuntimeProviderData | null) {
  const entries = new Set<string>()
  for (const entry of providerData?.provider_model_entries ?? []) {
    entries.add(entry.entry_ref)
  }
  return entries
}

function buildEntryRef(providerId: string, modelName: string) {
  return `${providerId}::${modelName}`
}

function buildProviderPayload(provider: EditableProvider): RuntimeProviderConfigRequest {
  return {
    provider_id: provider.provider_id,
    type: provider.type,
    base_url: provider.base_url.trim(),
    api_key: provider.api_key.trim(),
    alias: provider.alias.trim() || null,
    preferred_model: provider.preferred_model.trim() || null,
    max_context_window: Number.parseInt(provider.max_context_window, 10) || null,
    enabled: provider.enabled,
  }
}

function entryLabel(entry: RuntimeProviderModelEntry) {
  return `${entry.provider_label} / ${entry.model_name}`
}

export function ProviderSettingsDrawer({
  isOpen,
  providerData,
  loading,
  error,
  submitting,
  onClose,
  onSave,
  onConnectivityTest,
  onRefreshModels,
}: ProviderSettingsDrawerProps) {
  const [providers, setProviders] = useState<EditableProvider[]>(buildEditableProviders(providerData))
  const [roleBindings, setRoleBindings] = useState<EditableRoleBinding[]>(buildEditableBindings(providerData))
  const [availableModelsByProvider, setAvailableModelsByProvider] = useState<Record<string, string[]>>({})
  const [selectedEntryRefs, setSelectedEntryRefs] = useState<Set<string>>(buildSelectedEntryMap(providerData))
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const hydratedOpenSessionRef = useRef(false)

  useEffect(() => {
    if (!isOpen) {
      hydratedOpenSessionRef.current = false
      return
    }
    if (hydratedOpenSessionRef.current || providerData == null) {
      return
    }
    setProviders(buildEditableProviders(providerData))
    setRoleBindings(buildEditableBindings(providerData))
    setSelectedEntryRefs(buildSelectedEntryMap(providerData))
    hydratedOpenSessionRef.current = true
  }, [isOpen, providerData])

  const updateProvider = (providerId: string, patch: Partial<EditableProvider>) => {
    setProviders((current) =>
      current.map((provider) => (provider.provider_id === providerId ? { ...provider, ...patch } : provider)),
    )
  }

  const updateBinding = (targetRef: string, patch: Partial<EditableRoleBinding>) => {
    setRoleBindings((current) =>
      current.map((binding) => (binding.target_ref === targetRef ? { ...binding, ...patch } : binding)),
    )
  }

  const toggleSelectedEntry = (entryRef: string) => {
    setSelectedEntryRefs((current) => {
      const next = new Set(current)
      if (next.has(entryRef)) {
        next.delete(entryRef)
      } else {
        next.add(entryRef)
      }
      return next
    })
  }

  const handleAddProvider = () => {
    const nextId = `prov_${providers.length + 1}`
    setProviders((current) => [
      ...current,
      {
        provider_id: nextId,
        type: 'openai_responses_stream',
        base_url: '',
        api_key: '',
        alias: '',
        preferred_model: '',
        max_context_window: '',
        enabled: true,
      },
    ])
  }

  const handleConnectivityTest = async (providerId: string) => {
    const provider = providers.find((item) => item.provider_id === providerId)
    if (!provider) {
      return
    }
    const result = await onConnectivityTest(buildProviderPayload(provider))
    if (result.resolved_provider != null) {
      updateProvider(providerId, {
        type: result.resolved_provider.type,
        base_url: result.resolved_provider.base_url,
        alias: result.resolved_provider.alias ?? '',
        preferred_model: result.resolved_provider.preferred_model ?? '',
        max_context_window: String(result.resolved_provider.max_context_window ?? ''),
        enabled: result.resolved_provider.enabled,
      })
    }
    setStatusMessage(result.ok ? `Connectivity ok for ${providerId}.` : `Connectivity failed for ${providerId}.`)
  }

  const handleRefreshModels = async (providerId: string) => {
    const result = await onRefreshModels(providerId)
    const allowedRefs = new Set(result.map((modelName) => buildEntryRef(providerId, modelName)))
    setAvailableModelsByProvider((current) => ({ ...current, [providerId]: result }))
    setSelectedEntryRefs((current) => {
      const next = new Set(
        Array.from(current).filter((entryRef) => !entryRef.startsWith(`${providerId}::`) || allowedRefs.has(entryRef)),
      )
      for (const modelName of result) {
        const entryRef = buildEntryRef(providerId, modelName)
        if (providerData?.provider_model_entries.some((entry) => entry.entry_ref === entryRef)) {
          next.add(entryRef)
        }
      }
      return next
    })
  }

  const handleSave = () => {
    const providerModelEntries = Array.from(selectedEntryRefs)
      .map((entryRef) => {
        const [providerId, modelName] = entryRef.split('::')
        if (!providerId || !modelName) {
          return null
        }
        return {
          provider_id: providerId,
          model_name: modelName,
        }
      })
      .filter((item): item is { provider_id: string; model_name: string } => item != null)

    void onSave({
      providers: providers.map(buildProviderPayload),
      providerModelEntries,
      roleBindings: roleBindings.map((binding) => ({
        target_ref: binding.target_ref,
        provider_model_entry_refs: binding.provider_model_entry_refs,
        max_context_window_override: Number.parseInt(binding.max_context_window_override, 10) || null,
      })),
    })
  }

  const allEntries: RuntimeProviderModelEntry[] = [
    ...(providerData?.provider_model_entries ?? []),
    ...providers.flatMap((provider) =>
      (availableModelsByProvider[provider.provider_id] ?? []).map((modelName) => ({
        entry_ref: buildEntryRef(provider.provider_id, modelName),
        provider_id: provider.provider_id,
        provider_label: provider.alias || provider.provider_id,
        model_name: modelName,
        max_context_window: Number.parseInt(provider.max_context_window, 10) || 0,
      })),
    ),
  ].filter(
    (entry, index, entries) => entries.findIndex((candidate) => candidate.entry_ref === entry.entry_ref) === index,
  )

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Runtime providers" subtitle="Runtime">
      <p className="muted-copy">
        Manage provider connections, load selectable models, and bind CEO or delivery roles to provider-model entries.
      </p>

      {loading ? (
        <div className="review-room-state">Loading runtime providers...</div>
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
          <p className="muted-copy">{providerData?.effective_reason ?? 'Runtime provider status is unavailable.'}</p>
          {statusMessage ? <p className="muted-copy">{statusMessage}</p> : null}

          <section className="review-room-action-panel provider-settings-panel">
            <button type="button" className="secondary-button" onClick={handleAddProvider}>
              Add provider
            </button>

            {providers.map((provider) => (
              <section key={provider.provider_id} className="provider-settings-panel">
                <h3>{provider.provider_id}</h3>
                <label>
                  <span className="field-label">Provider type</span>
                  <select
                    aria-label={`Provider type ${provider.provider_id}`}
                    value={provider.type}
                    onChange={(event) => updateProvider(provider.provider_id, { type: event.target.value })}
                  >
                    <option value="openai_responses_stream">OpenAI Responses stream</option>
                    <option value="openai_responses_non_stream">OpenAI Responses non-stream</option>
                    <option value="claude_stream">Claude stream (reserved)</option>
                    <option value="gemini_stream">Gemini stream (reserved)</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">Base URL</span>
                  <input
                    aria-label={`Provider base URL ${provider.provider_id}`}
                    value={provider.base_url}
                    onChange={(event) => updateProvider(provider.provider_id, { base_url: event.target.value })}
                  />
                </label>
                <label>
                  <span className="field-label">API key</span>
                  <input
                    aria-label={`Provider API key ${provider.provider_id}`}
                    type="password"
                    value={provider.api_key}
                    onChange={(event) => updateProvider(provider.provider_id, { api_key: event.target.value })}
                  />
                </label>
                <label>
                  <span className="field-label">Alias</span>
                  <input
                    aria-label={`Provider alias ${provider.provider_id}`}
                    value={provider.alias}
                    onChange={(event) => updateProvider(provider.provider_id, { alias: event.target.value })}
                  />
                </label>
                <label>
                  <span className="field-label">Preferred model</span>
                  <input
                    aria-label={`Provider preferred model ${provider.provider_id}`}
                    value={provider.preferred_model}
                    onChange={(event) => updateProvider(provider.provider_id, { preferred_model: event.target.value })}
                  />
                </label>
                <label>
                  <span className="field-label">Context window</span>
                  <input
                    aria-label={`Provider context window ${provider.provider_id}`}
                    type="number"
                    value={provider.max_context_window}
                    onChange={(event) => updateProvider(provider.provider_id, { max_context_window: event.target.value })}
                  />
                </label>
                <div className="provider-settings-grid">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void handleConnectivityTest(provider.provider_id)}
                  >
                    {`Test ${provider.provider_id} connectivity`}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void handleRefreshModels(provider.provider_id)}
                  >
                    {`Load models for ${provider.provider_id}`}
                  </button>
                </div>

                {(availableModelsByProvider[provider.provider_id] ?? []).length ? (
                  <div>
                    <span className="field-label">Selectable models</span>
                    <div className="provider-settings-grid">
                      {availableModelsByProvider[provider.provider_id].map((modelName) => {
                        const entryRef = buildEntryRef(provider.provider_id, modelName)
                        return (
                          <label key={entryRef}>
                            <input
                              aria-label={`Model ${modelName} for ${provider.provider_id}`}
                              type="checkbox"
                              checked={selectedEntryRefs.has(entryRef)}
                              onChange={() => toggleSelectedEntry(entryRef)}
                            />
                            <span>{modelName}</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                ) : null}
              </section>
            ))}

            <div>
              <span className="field-label">Role bindings</span>
              <div className="provider-settings-grid">
                {roleBindings.map((binding) => (
                  <label key={binding.target_ref}>
                    <span className="field-label">{binding.target_label}</span>
                    <div className="provider-settings-grid">
                      {allEntries.map((entry) => (
                        <label key={`${binding.target_ref}:${entry.entry_ref}`}>
                          <input
                            aria-label={`${binding.target_label} uses ${entry.entry_ref}`}
                            type="checkbox"
                            checked={binding.provider_model_entry_refs.includes(entry.entry_ref)}
                            onChange={() => {
                              const nextRefs = binding.provider_model_entry_refs.includes(entry.entry_ref)
                                ? binding.provider_model_entry_refs.filter((value) => value !== entry.entry_ref)
                                : [...binding.provider_model_entry_refs, entry.entry_ref]
                              updateBinding(binding.target_ref, { provider_model_entry_refs: nextRefs })
                            }}
                          />
                          <span>{entryLabel(entry)}</span>
                        </label>
                      ))}
                    </div>
                    <input
                      aria-label={`${binding.target_label} context window override`}
                      type="number"
                      value={binding.max_context_window_override}
                      placeholder="Inherit provider window"
                      onChange={(event) =>
                        updateBinding(binding.target_ref, { max_context_window_override: event.target.value })
                      }
                    />
                  </label>
                ))}
              </div>
            </div>

            <button type="button" className="secondary-button" disabled={submitting} onClick={handleSave}>
              {submitting ? 'Saving...' : 'Save runtime settings'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
