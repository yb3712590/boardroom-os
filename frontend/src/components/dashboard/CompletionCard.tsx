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

  return (
    <section className="completion-card" aria-labelledby="completion-card-title">
      <div className="completion-card-copy">
        <p className="eyebrow">工作流结果</p>
        <h2 id="completion-card-title">交付已完成</h2>
        <p className="muted-copy">
          {hasFinalReview
            ? `董事会在 ${formatTimestamp(finalReviewApprovedAt, '未记录')} 批准，工作流 ${summary.workflow_id} 于 ${formatTimestamp(summary.closeout_completed_at, '未记录')} 完成收口。`
            : `工作流 ${summary.workflow_id} 于 ${formatTimestamp(summary.closeout_completed_at, '未记录')} 完成收口，当前结果来自 closeout 包与 workflow 链路报告。`}
        </p>
      </div>
      <div className="completion-card-grid">
        <div>
          <span>最终标题</span>
          <strong>{summary.title}</strong>
        </div>
        <div>
          <span>批准时间</span>
          <strong>{hasFinalReview ? formatTimestamp(finalReviewApprovedAt, '未记录') : '未经过最终评审'}</strong>
        </div>
        <div>
          <span>收口完成</span>
          <strong>{formatTimestamp(summary.closeout_completed_at, '未记录')}</strong>
        </div>
        <div>
          <span>选择方案</span>
          <strong>{summary.selected_option_id ?? (hasFinalReview ? '未覆盖方案，按默认批准' : '未经过最终评审')}</strong>
        </div>
        <div>
          <span>董事会备注</span>
          <strong>{summary.board_comment ?? (hasFinalReview ? '暂无董事会备注。' : '本次完成态不依赖董事会最终评审。')}</strong>
        </div>
        <div>
          <span>证据产物</span>
          <strong>{summary.artifact_refs.length}</strong>
          <div className="artifact-ref-list">
            {summary.artifact_refs.map((artifactRef) => (
              <button
                key={artifactRef}
                type="button"
                className="ghost-button artifact-ref-button"
                onClick={() => onOpenArtifact(artifactRef)}
              >
                打开产物 {artifactRefFilename(artifactRef)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span>收口产物</span>
          <strong>{summary.closeout_artifact_refs.length}</strong>
          <div className="artifact-ref-list">
            {summary.closeout_artifact_refs.map((artifactRef) => (
              <button
                key={artifactRef}
                type="button"
                className="ghost-button artifact-ref-button"
                onClick={() => onOpenArtifact(artifactRef)}
              >
                打开产物 {artifactRefFilename(artifactRef)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span>文档更新数</span>
          <strong>{summary.documentation_update_count}</strong>
        </div>
        <div>
          <span>后续文档项</span>
          <strong>{summary.documentation_follow_up_count}</strong>
        </div>
      </div>
      <p className="completion-card-summary">
        <strong>文档同步</strong>
        {': '}
        <span>{summary.documentation_sync_summary ?? '未记录文档同步更新。'}</span>
      </p>
      <p className="completion-card-summary">{summary.summary}</p>
      <div className="completion-card-actions">
        {summary.final_review_pack_id ? (
          <Button type="button" variant="secondary" onClick={() => onOpenReview(summary.final_review_pack_id)}>
            打开最终评审证据
          </Button>
        ) : chainReportArtifactRef ? (
          <Button type="button" variant="secondary" onClick={() => onOpenArtifact(chainReportArtifactRef)}>
            打开 workflow 链路报告
          </Button>
        ) : null}
      </div>
    </section>
  )
}
