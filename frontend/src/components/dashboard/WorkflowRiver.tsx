import { motion, useReducedMotion } from 'framer-motion'

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
  const prefersReducedMotion = useReducedMotion()

  if (loading) {
    return (
      <section className="workflow-river workflow-river-loading" aria-label="Workflow River loading" aria-busy="true">
        <div className="workflow-river-loading-copy">
          <p className="eyebrow">Workflow River</p>
          <LoadingSkeleton lines={4} />
        </div>
      </section>
    )
  }

  return (
    <section className="workflow-river" aria-labelledby="workflow-river-title">
      <div className="river-header">
        <div>
          <p className="eyebrow">Workflow River</p>
          <h2 id="workflow-river-title">Board to review, in one governance surface.</h2>
        </div>
        <div className={`board-gate-status ${approvalsPending > 0 ? 'is-armed' : 'is-clear'}`}>
          <span className="board-gate-light" aria-hidden="true" />
          <p>{approvalsPending > 0 ? 'Board Gate armed' : 'Board Gate clear'}</p>
          <span>{approvalsPending > 0 ? `${approvalsPending} item waiting` : 'No board items waiting'}</span>
        </div>
      </div>

      <div className="workflow-river-scroll">
        <div className="river-stage-strip" aria-label="workflow river">
          <div className="river-mainline" aria-hidden="true" />
          <motion.div
            className={`river-board-branch ${approvalsPending > 0 ? 'is-visible' : ''}`}
            initial={prefersReducedMotion ? false : { opacity: 0.2, scaleX: 0.82 }}
            animate={{ opacity: approvalsPending > 0 ? 1 : 0.18, scaleX: approvalsPending > 0 ? 1 : 0.82 }}
            transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.38, ease: 'easeOut' }}
            aria-hidden="true"
          />
          {phases.map((phase, index) => {
            const total = phaseTotal(phase)
            const accent = phaseAccent(phase.status)
            return (
              <motion.article
                key={phase.phase_id}
                className={`river-stage river-stage-${phase.status.toLowerCase()}`}
                initial={prefersReducedMotion ? false : { opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={prefersReducedMotion ? { duration: 0 } : { delay: index * 0.06, duration: 0.28, ease: 'easeOut' }}
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
                    <span>{total} node{total === 1 ? '' : 's'}</span>
                    <span>
                      {phase.node_counts.executing > 0 ? 'Live' : phase.node_counts.completed > 0 ? 'Settled' : 'Queued'}
                    </span>
                  </div>
                </div>
                <div className="river-stage-particles" aria-hidden="true">
                  {Array.from({ length: Math.min(Math.max(total, 1), 4) }).map((_, particleIndex) => (
                    <span
                      key={`${phase.phase_id}-${particleIndex}`}
                      className="river-particle"
                      style={{ animationDelay: `${index * 0.22 + particleIndex * 0.35}s` }}
                    />
                  ))}
                </div>
              </motion.article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
