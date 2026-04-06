import { Button } from '../shared/Button'

import type { DashboardData } from '../../types/api'
import { formatTimestamp } from '../../utils/format'

type CompletionCardProps = {
  summary: NonNullable<DashboardData['completion_summary']>
  onOpenReview: (reviewPackId: string) => void
}

export function CompletionCard({ summary, onOpenReview }: CompletionCardProps) {
  const finalReviewApprovedAt = summary.final_review_approved_at ?? summary.approved_at ?? null

  return (
    <section className="completion-card" aria-labelledby="completion-card-title">
      <div className="completion-card-copy">
        <p className="eyebrow">Workflow result</p>
        <h2 id="completion-card-title">Delivery completed</h2>
        <p className="muted-copy">
          Board approved {formatTimestamp(finalReviewApprovedAt, 'Not recorded')} and closeout completed{' '}
          {formatTimestamp(summary.closeout_completed_at, 'Not recorded')} for workflow {summary.workflow_id}.
        </p>
      </div>
      <div className="completion-card-grid">
        <div>
          <span>Final title</span>
          <strong>{summary.title}</strong>
        </div>
        <div>
          <span>Board approved</span>
          <strong>{formatTimestamp(finalReviewApprovedAt, 'Not recorded')}</strong>
        </div>
        <div>
          <span>Closeout completed</span>
          <strong>{formatTimestamp(summary.closeout_completed_at, 'Not recorded')}</strong>
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
        <div>
          <span>Documentation updates</span>
          <strong>{summary.documentation_update_count}</strong>
        </div>
        <div>
          <span>Follow-up docs</span>
          <strong>{summary.documentation_follow_up_count}</strong>
        </div>
      </div>
      <p className="completion-card-summary">
        <strong>Documentation sync</strong>
        {': '}
        <span>{summary.documentation_sync_summary ?? 'No documentation sync updates were recorded.'}</span>
      </p>
      <p className="completion-card-summary">{summary.summary}</p>
      <div className="completion-card-actions">
        <Button type="button" variant="secondary" onClick={() => onOpenReview(summary.final_review_pack_id)}>
          Open final review evidence
        </Button>
      </div>
    </section>
  )
}
