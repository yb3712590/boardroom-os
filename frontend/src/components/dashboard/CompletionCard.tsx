import { Button } from '../shared/Button'

import type { DashboardData } from '../../types/api'

type CompletionCardProps = {
  summary: NonNullable<DashboardData['completion_summary']>
  onOpenReview: (reviewPackId: string) => void
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return 'Not recorded'
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function CompletionCard({ summary, onOpenReview }: CompletionCardProps) {
  const finalReviewApprovedAt = summary.final_review_approved_at ?? summary.approved_at ?? null

  return (
    <section className="completion-card" aria-labelledby="completion-card-title">
      <div className="completion-card-copy">
        <p className="eyebrow">Workflow result</p>
        <h2 id="completion-card-title">Delivery completed</h2>
        <p className="muted-copy">
          Board approved {formatTimestamp(finalReviewApprovedAt)} and closeout completed{' '}
          {formatTimestamp(summary.closeout_completed_at)} for workflow {summary.workflow_id}.
        </p>
      </div>
      <div className="completion-card-grid">
        <div>
          <span>Final title</span>
          <strong>{summary.title}</strong>
        </div>
        <div>
          <span>Board approved</span>
          <strong>{formatTimestamp(finalReviewApprovedAt)}</strong>
        </div>
        <div>
          <span>Closeout completed</span>
          <strong>{formatTimestamp(summary.closeout_completed_at)}</strong>
        </div>
        <div>
          <span>Selected option</span>
          <strong>{summary.selected_option_id ?? 'Board approved without option override'}</strong>
        </div>
        <div>
          <span>Board comment</span>
          <strong>{summary.board_comment ?? 'No board comment recorded.'}</strong>
        </div>
        <div>
          <span>Evidence refs</span>
          <strong>{summary.artifact_refs.length}</strong>
        </div>
        <div>
          <span>Closeout refs</span>
          <strong>{summary.closeout_artifact_refs.length}</strong>
        </div>
      </div>
      <p className="completion-card-summary">{summary.summary}</p>
      <div className="completion-card-actions">
        <Button type="button" variant="secondary" onClick={() => onOpenReview(summary.final_review_pack_id)}>
          Open final review evidence
        </Button>
      </div>
    </section>
  )
}
