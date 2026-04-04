type OpsStripProps = {
  budgetRemaining: number
  activeTickets: number
  blockedNodes: number
  deadlineAt: string | null | undefined
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(value)
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return 'No deadline'
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function OpsStrip({ budgetRemaining, activeTickets, blockedNodes, deadlineAt }: OpsStripProps) {
  return (
    <dl className="ops-strip">
      <div>
        <dt>Budget</dt>
        <dd>{formatNumber(budgetRemaining)}</dd>
      </div>
      <div>
        <dt>Live tickets</dt>
        <dd>{activeTickets}</dd>
      </div>
      <div>
        <dt>Blocked</dt>
        <dd>{blockedNodes}</dd>
      </div>
      <div>
        <dt>Deadline</dt>
        <dd>{formatTimestamp(deadlineAt)}</dd>
      </div>
    </dl>
  )
}
