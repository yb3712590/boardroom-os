import { useEffect, useState } from 'react'

import type { RuntimeProviderData } from '../../types/api'
import { Drawer } from '../shared/Drawer'

type ProviderSettingsDrawerProps = {
  isOpen: boolean
  providerData: RuntimeProviderData | null
  loading: boolean
  error: string | null
  submitting: boolean
  onClose: () => void
  onSave: (input: {
    mode: string
    baseUrl: string | null
    apiKey: string | null
    model: string | null
    timeoutSec: number
    reasoningEffort: string | null
  }) => Promise<void>
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
  const [mode, setMode] = useState(providerData?.mode ?? 'DETERMINISTIC')
  const [baseUrl, setBaseUrl] = useState(providerData?.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(providerData?.model ?? '')
  const [timeoutSec, setTimeoutSec] = useState(String(providerData?.timeout_sec ?? 30))
  const [reasoningEffort, setReasoningEffort] = useState(providerData?.reasoning_effort ?? '')

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setMode(providerData?.mode ?? 'DETERMINISTIC')
    setBaseUrl(providerData?.base_url ?? '')
    setApiKey('')
    setModel(providerData?.model ?? '')
    setTimeoutSec(String(providerData?.timeout_sec ?? 30))
    setReasoningEffort(providerData?.reasoning_effort ?? '')
  }, [isOpen, providerData])

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Runtime provider" subtitle="Runtime">
      <p className="muted-copy">
        Switch between the local deterministic path and the saved OpenAI-compatible provider config without leaving the
        boardroom shell.
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
              <span className="eyebrow">Saved key</span>
              <p>{providerData?.api_key_masked ?? 'No key saved'}</p>
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
              </select>
            </label>
            <label>
              <span className="field-label">Base URL</span>
              <input aria-label="Base URL" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
            </label>
            <label>
              <span className="field-label">API key</span>
              <input
                aria-label="API key"
                type="password"
                value={apiKey}
                placeholder={providerData?.api_key_masked ?? ''}
                onChange={(event) => setApiKey(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">Model</span>
              <input aria-label="Model" value={model} onChange={(event) => setModel(event.target.value)} />
            </label>
            <div className="provider-settings-grid">
              <label>
                <span className="field-label">Timeout (sec)</span>
                <input
                  aria-label="Timeout (sec)"
                  type="number"
                  min="1"
                  value={timeoutSec}
                  onChange={(event) => setTimeoutSec(event.target.value)}
                />
              </label>
              <label>
                <span className="field-label">Reasoning effort</span>
                <select
                  aria-label="Reasoning effort"
                  value={reasoningEffort}
                  onChange={(event) => setReasoningEffort(event.target.value)}
                >
                  <option value="">Default</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="xhigh">XHigh</option>
                </select>
              </label>
            </div>
            <button
              type="button"
              className="secondary-button"
              disabled={submitting}
              onClick={() =>
                void onSave({
                  mode,
                  baseUrl: baseUrl.trim() || null,
                  apiKey: apiKey.trim() || null,
                  model: model.trim() || null,
                  timeoutSec: Number.parseFloat(timeoutSec) || 30,
                  reasoningEffort: reasoningEffort || null,
                })
              }
            >
              {submitting ? 'Saving...' : 'Save runtime settings'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
