type BoardGateIndicatorProps = {
  approvalsPending: number
}

export function BoardGateIndicator({ approvalsPending }: BoardGateIndicatorProps) {
  return (
    <div className={`board-chip ${approvalsPending > 0 ? 'is-armed' : 'is-clear'}`}>
      <span className="board-chip-light" aria-hidden="true" />
      <strong>{approvalsPending > 0 ? '董事会闸门已触发' : '董事会闸门已清空'}</strong>
      <span>{approvalsPending > 0 ? `待审批 ${approvalsPending} 项` : '当前无待审批项'}</span>
    </div>
  )
}
