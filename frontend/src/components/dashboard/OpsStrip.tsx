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
        <dt>预算</dt>
        <dd>{formatNumber(budgetRemaining)}</dd>
      </div>
      <div>
        <dt>进行中工单</dt>
        <dd>{activeTickets}</dd>
      </div>
      <div>
        <dt>阻塞节点</dt>
        <dd>{blockedNodes}</dd>
      </div>
      <div>
        <dt>截止时间</dt>
        <dd>{formatTimestamp(deadlineAt)}</dd>
      </div>
    </dl>
  )
}
