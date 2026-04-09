import { BoardGateIndicator } from '../dashboard/BoardGateIndicator'
import { OpsStrip } from '../dashboard/OpsStrip'
import { RuntimeStatusCard } from '../dashboard/RuntimeStatusCard'

type TopChromeProps = {
  title: string
  northStarGoal: string
  effectiveRuntimeMode: string
  runtimeProviderLabel: string
  runtimeModel: string | null | undefined
  runtimeWorkerCount: number
  runtimeHealth: string
  runtimeReason: string
  approvalsPending: number
  budgetRemaining: number
  activeTickets: number
  blockedNodes: number
  deadlineAt: string | null | undefined
  onOpenRuntimeSettings: () => void
}

export function TopChrome({
  title,
  northStarGoal,
  effectiveRuntimeMode,
  runtimeProviderLabel,
  runtimeModel,
  runtimeWorkerCount,
  runtimeHealth,
  runtimeReason,
  approvalsPending,
  budgetRemaining,
  activeTickets,
  blockedNodes,
  deadlineAt,
  onOpenRuntimeSettings,
}: TopChromeProps) {
  return (
    <header className="top-chrome">
      <div>
        <p className="eyebrow">Boardroom system</p>
        <h1>{title}</h1>
        <p className="top-chrome-copy">{northStarGoal}</p>
      </div>
      <div className="top-chrome-meta">
        <RuntimeStatusCard
          effectiveMode={effectiveRuntimeMode}
          providerLabel={runtimeProviderLabel}
          model={runtimeModel}
          workerCount={runtimeWorkerCount}
          healthSummary={runtimeHealth}
          reason={runtimeReason}
          onOpenSettings={onOpenRuntimeSettings}
        />
        <BoardGateIndicator approvalsPending={approvalsPending} />
        <OpsStrip
          budgetRemaining={budgetRemaining}
          activeTickets={activeTickets}
          blockedNodes={blockedNodes}
          deadlineAt={deadlineAt}
        />
      </div>
    </header>
  )
}
