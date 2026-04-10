import { Button } from '../shared/Button'

import type { DashboardData } from '../../types/api'
import { artifactRefFilename } from '../../utils/artifacts'
import { formatTimestamp } from '../../utils/format'

type CompletionCardProps = {
  summary: NonNullable<DashboardData['completion_summary']>
  onOpenReview: (reviewPackId: string) => void
  onOpenArtifact: (artifactRef: string) => void
}

export function CompletionCard({ summary, onOpenReview, onOpenArtifact }: CompletionCardProps) {
  const finalReviewApprovedAt = summary.final_review_approved_at ?? summary.approved_at ?? null
  const hasFinalReview = summary.final_review_pack_id !== null
  const chainReportArtifactRef = summary.workflow_chain_report_artifact_ref
  const finalReviewPackId = summary.final_review_pack_id
  const sourceDeliverySummary = summary.source_delivery_summary ?? null

  return (
    <section className="completion-card" aria-labelledby="completion-card-title">
      <div className="completion-card-copy">
        <p className="eyebrow">Workflow result</p>
        <h2 id="completion-card-title">Delivery completed</h2>
        <p className="muted-copy">
          {hasFinalReview
            ? `The board approved this workflow on ${formatTimestamp(finalReviewApprovedAt, 'Not recorded')}, and workflow ${summary.workflow_id} closed out on ${formatTimestamp(summary.closeout_completed_at, 'Not recorded')}.`
            : `Workflow ${summary.workflow_id} closed out on ${formatTimestamp(summary.closeout_completed_at, 'Not recorded')}. This completion came from the closeout package and workflow chain report.`}
        </p>
      </div>
      <div className="completion-card-grid">
        <div>
          <span>Final title</span>
          <strong>{summary.title}</strong>
        </div>
        <div>
          <span>Approved at</span>
          <strong>{hasFinalReview ? formatTimestamp(finalReviewApprovedAt, 'Not recorded') : 'No final review'}</strong>
        </div>
        <div>
          <span>Closeout completed</span>
          <strong>{formatTimestamp(summary.closeout_completed_at, 'Not recorded')}</strong>
        </div>
        <div>
          <span>Selected option</span>
          <strong>{summary.selected_option_id ?? (hasFinalReview ? 'Approved without an explicit option override' : 'No final review')}</strong>
        </div>
        <div>
          <span>Board comment</span>
          <strong>{summary.board_comment ?? (hasFinalReview ? 'No board comment recorded.' : 'This completion path did not require a final board review.')}</strong>
        </div>
        <div>
          <span>Evidence artifacts</span>
          <strong>{summary.artifact_refs.length}</strong>
          <div className="artifact-ref-list">
            {summary.artifact_refs.map((artifactRef) => (
              <button
                key={artifactRef}
                type="button"
                className="ghost-button artifact-ref-button"
                onClick={() => onOpenArtifact(artifactRef)}
              >
                Open artifact {artifactRefFilename(artifactRef)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span>Closeout artifacts</span>
          <strong>{summary.closeout_artifact_refs.length}</strong>
          <div className="artifact-ref-list">
            {summary.closeout_artifact_refs.map((artifactRef) => (
              <button
                key={artifactRef}
                type="button"
                className="ghost-button artifact-ref-button"
                onClick={() => onOpenArtifact(artifactRef)}
              >
                Open artifact {artifactRefFilename(artifactRef)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span>Documentation updates</span>
          <strong>{summary.documentation_update_count}</strong>
        </div>
        <div>
          <span>Documentation follow-ups</span>
          <strong>{summary.documentation_follow_up_count}</strong>
        </div>
      </div>
      <p className="completion-card-summary">
        <strong>Documentation sync</strong>
        {': '}
        <span>{summary.documentation_sync_summary ?? 'No documentation sync update recorded.'}</span>
      </p>
      {sourceDeliverySummary ? (
        <div className="completion-card-summary">
          <strong>Source delivery evidence</strong>
          <div className="completion-card-grid">
            <div>
              <span>Source ticket</span>
              <strong>{sourceDeliverySummary.ticket_id}</strong>
            </div>
            <div>
              <span>Source files</span>
              <strong>{sourceDeliverySummary.source_file_count}</strong>
              <div className="artifact-ref-list">
                {sourceDeliverySummary.source_file_refs.map((artifactRef) => (
                  <button
                    key={artifactRef}
                    type="button"
                    className="ghost-button artifact-ref-button"
                    onClick={() => onOpenArtifact(artifactRef)}
                  >
                    Open artifact {artifactRefFilename(artifactRef)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span>Verification evidence</span>
              <strong>{sourceDeliverySummary.verification_evidence_count}</strong>
              <div className="artifact-ref-list">
                {sourceDeliverySummary.verification_evidence_refs.map((artifactRef) => (
                  <button
                    key={artifactRef}
                    type="button"
                    className="ghost-button artifact-ref-button"
                    onClick={() => onOpenArtifact(artifactRef)}
                  >
                    Open artifact {artifactRefFilename(artifactRef)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span>Git branch</span>
              <strong>{sourceDeliverySummary.git_branch_ref ?? 'Not recorded'}</strong>
            </div>
            <div>
              <span>Commit</span>
              <strong>{sourceDeliverySummary.git_commit_sha ?? 'Not recorded'}</strong>
            </div>
            <div>
              <span>Merge status</span>
              <strong>{sourceDeliverySummary.git_merge_status ?? 'Not recorded'}</strong>
            </div>
          </div>
          <span>{sourceDeliverySummary.summary}</span>
        </div>
      ) : null}
      <p className="completion-card-summary">{summary.summary}</p>
      <div className="completion-card-actions">
        {finalReviewPackId != null ? (
          <Button type="button" variant="secondary" onClick={() => onOpenReview(finalReviewPackId)}>
            Open final review evidence
          </Button>
        ) : chainReportArtifactRef ? (
          <Button type="button" variant="secondary" onClick={() => onOpenArtifact(chainReportArtifactRef)}>
            Open workflow chain report
          </Button>
        ) : null}
      </div>
    </section>
  )
}
