import { formatNumber, formatTimestamp } from '../../utils/format'

type OpsStripProps = {
  budgetRemaining: number
  activeTickets: number
  blockedNodes: number
  deadlineAt: string | null | undefined
}

export function OpsStrip({ budgetRemaining, activeTickets, blockedNodes, deadlineAt }: OpsStripProps) {
  return (
    <dl className="ops-strip">
      <div>
        <dt>Budget</dt>
        <dd>{formatNumber(budgetRemaining)}</dd>
      </div>
      <div>
        <dt>Active tickets</dt>
        <dd>{activeTickets}</dd>
      </div>
      <div>
        <dt>Blocked nodes</dt>
        <dd>{blockedNodes}</dd>
      </div>
      <div>
        <dt>Deadline</dt>
        <dd>{formatTimestamp(deadlineAt)}</dd>
      </div>
    </dl>
  )
}
