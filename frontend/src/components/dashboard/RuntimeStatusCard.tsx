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
      return 'warning'
    case 'LOCAL_DETERMINISTIC':
    default:
      return 'local'
  }
}

function runtimeHealthLabel(value: string) {
  switch (value) {
    case 'LOCAL_ONLY':
      return '仅本地'
    case 'HEALTHY':
      return '健康'
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
          <p className="eyebrow">执行模式</p>
          <strong>{providerLabel}</strong>
        </div>
        <Button type="button" variant="ghost" onClick={onOpenSettings}>
          运行时设置
        </Button>
      </div>
      <p className="runtime-status-copy">{reason}</p>
      <dl className="runtime-status-grid">
        <div>
          <dt>模型</dt>
          <dd>{model ?? '本地确定性运行时'}</dd>
        </div>
        <div>
          <dt>执行人数</dt>
          <dd>{workerCount}</dd>
        </div>
        <div>
          <dt>健康状态</dt>
          <dd>{runtimeHealthLabel(healthSummary)}</dd>
        </div>
      </dl>
    </section>
  )
}
