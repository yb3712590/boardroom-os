type BoardGateIndicatorProps = {
  approvalsPending: number
}

export function BoardGateIndicator({ approvalsPending }: BoardGateIndicatorProps) {
  return (
    <div className={`board-chip ${approvalsPending > 0 ? 'is-armed' : 'is-clear'}`}>
      <span className="board-chip-light" aria-hidden="true" />
      <strong>{approvalsPending > 0 ? 'Board Gate armed' : 'Board Gate clear'}</strong>
      <span>{approvalsPending > 0 ? `${approvalsPending} approval${approvalsPending === 1 ? '' : 's'} pending` : 'No approvals pending'}</span>
    </div>
  )
}
