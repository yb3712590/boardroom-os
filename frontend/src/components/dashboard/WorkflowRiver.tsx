import type { PhaseSummary } from '../../types/domain'
import { LoadingSkeleton } from '../shared/LoadingSkeleton'

type WorkflowRiverProps = {
  phases: PhaseSummary[]
  approvalsPending: number
  loading?: boolean
}

function phaseTotal(phase: PhaseSummary) {
  const counts = phase.node_counts
  return (
    counts.pending +
    counts.executing +
    counts.under_review +
    counts.blocked_for_board +
    counts.fused +
    counts.completed
  )
}

function phaseAccent(status: string) {
  if (status === 'FUSED') {
    return 'var(--incident-rose)'
  }
  if (status === 'BLOCKED_FOR_BOARD') {
    return 'var(--board-gold)'
  }
  if (status === 'EXECUTING') {
    return 'var(--active-ice)'
  }
  if (status === 'COMPLETED') {
    return 'var(--line-blue)'
  }
  return 'var(--muted-label)'
}

export function WorkflowRiver({ phases, approvalsPending, loading = false }: WorkflowRiverProps) {
  if (loading) {
    return (
      <section className="workflow-river workflow-river-loading" aria-label="Workflow River loading" aria-busy="true">
        <div className="workflow-river-loading-copy">
          <p className="eyebrow">工作流河道</p>
          <LoadingSkeleton lines={4} />
        </div>
      </section>
    )
  }

  return (
    <section className="workflow-river" aria-labelledby="workflow-river-title">
      <div className="river-header">
        <div>
          <p className="eyebrow">工作流河道</p>
          <h2 id="workflow-river-title">从董事会到评审闸门，一屏看清治理推进。</h2>
        </div>
        <div className={`board-gate-status ${approvalsPending > 0 ? 'is-armed' : 'is-clear'}`}>
          <span className="board-gate-light" aria-hidden="true" />
          <p>{approvalsPending > 0 ? '董事会闸门已触发' : '董事会闸门已清空'}</p>
          <span>{approvalsPending > 0 ? `待处理 ${approvalsPending} 项` : '当前无待处理项'}</span>
        </div>
      </div>

      <div className="workflow-river-scroll">
        <div className="river-stage-strip" aria-label="workflow river">
          <div className="river-mainline" aria-hidden="true" />
          <div
            className={`river-board-branch ${approvalsPending > 0 ? 'is-visible' : ''}`}
            aria-hidden="true"
          />
          {phases.map((phase) => {
            const total = phaseTotal(phase)
            const accent = phaseAccent(phase.status)
            return (
              <article
                key={phase.phase_id}
                className={`river-stage river-stage-${phase.status.toLowerCase()}`}
              >
                <div className="river-stage-shell" style={{ ['--phase-accent' as string]: accent }}>
                  <div className="river-stage-knot" aria-hidden="true">
                    <span className="river-stage-core" />
                  </div>
                  <div className="river-stage-copy">
                    <span className="river-stage-label">{phase.label}</span>
                    <span className="river-stage-status">{phase.status.replaceAll('_', ' ')}</span>
                  </div>
                  <div className="river-stage-meta">
                    <span>{total} 个节点</span>
                    <span>
                      {phase.node_counts.executing > 0 ? '执行中' : phase.node_counts.completed > 0 ? '已稳定' : '待排队'}
                    </span>
                  </div>
                </div>
                <div className="river-stage-particles" aria-hidden="true">
                  {Array.from({ length: Math.min(Math.max(total, 1), 4) }).map((_, particleIndex) => (
                    <span
                      key={`${phase.phase_id}-${particleIndex}`}
                      className="river-particle"
                    />
                  ))}
                </div>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
