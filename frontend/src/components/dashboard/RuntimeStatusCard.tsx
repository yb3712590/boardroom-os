import { Button } from '../shared/Button'

type RuntimeStatusCardProps = {
  effectiveMode: string | null | undefined
  providerLabel: string
  model: string | null | undefined
  workerCount: number
  healthSummary: string
  reason: string
  onOpenSettings: () => void
}

function runtimeModeTone(value: string | null | undefined) {
  switch (value) {
    case 'OPENAI_COMPAT_LIVE':
      return 'live'
    case 'OPENAI_COMPAT_INCOMPLETE':
    case 'OPENAI_COMPAT_PAUSED':
    case 'PROVIDER_REQUIRED_UNAVAILABLE':
      return 'warning'
    default:
      return 'warning'
  }
}

function runtimeHealthLabel(value: string) {
  switch (value) {
    case 'HEALTHY':
      return 'Healthy'
    default:
      return value.replaceAll('_', ' ')
  }
}

export function RuntimeStatusCard({
  effectiveMode,
  providerLabel,
  model,
  workerCount,
  healthSummary,
  reason,
  onOpenSettings,
}: RuntimeStatusCardProps) {
  return (
    <section className={`runtime-status-card runtime-status-${runtimeModeTone(effectiveMode)}`}>
      <div className="runtime-status-head">
        <div>
          <p className="eyebrow">Execution mode</p>
          <strong>{providerLabel}</strong>
        </div>
        <Button type="button" variant="ghost" onClick={onOpenSettings}>
          Runtime settings
        </Button>
      </div>
      <p className="runtime-status-copy">{reason}</p>
      <dl className="runtime-status-grid">
        <div>
          <dt>Model</dt>
          <dd>{model ?? 'No live provider configured'}</dd>
        </div>
        <div>
          <dt>Workers</dt>
          <dd>{workerCount}</dd>
        </div>
        <div>
          <dt>Health</dt>
          <dd>{runtimeHealthLabel(healthSummary)}</dd>
        </div>
      </dl>
    </section>
  )
}
