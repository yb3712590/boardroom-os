import type { DependencyInspectorData } from '../../types/api'
import { Drawer } from '../shared/Drawer'

type DependencyInspectorDrawerProps = {
  isOpen: boolean
  loading: boolean
  inspectorData: DependencyInspectorData | null
  error: string | null
  onClose: () => void
  onOpenReview: (reviewPackId: string) => void
  onOpenIncident: (incidentId: string) => void
}

function formatLabel(value: string | null | undefined) {
  if (!value) {
    return '无'
  }
  return value.replaceAll('_', ' ')
}

export function DependencyInspectorDrawer({
  isOpen,
  loading,
  inspectorData,
  error,
  onClose,
  onOpenReview,
  onOpenIncident,
}: DependencyInspectorDrawerProps) {
  const currentStop = inspectorData?.summary.current_stop

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="依赖链路" subtitle="依赖检查器">
      <p className="muted-copy">
        查看每个阶段依赖的上游工单、当前停点位置，以及应回到评审室或故障处理的节点。
      </p>

      {loading ? (
        <div className="review-room-state">正在加载依赖检查器...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : inspectorData == null ? (
        <div className="review-room-state">当前工作流暂无依赖快照。</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">当前停点</span>
              <p>{formatLabel(currentStop?.reason)}</p>
            </div>
            <div>
              <span className="eyebrow">阻塞节点</span>
              <p>{inspectorData.summary.blocked_nodes}</p>
            </div>
            <div>
              <span className="eyebrow">关键路径</span>
              <p>{inspectorData.summary.critical_path_nodes}</p>
            </div>
          </section>

          <section className="dependency-summary-grid">
            <div className="review-room-action-panel">
              <span className="eyebrow">工作流</span>
              <p>{inspectorData.workflow.title}</p>
              <p className="muted-copy">
                {inspectorData.workflow.workflow_id} · {formatLabel(inspectorData.workflow.current_stage)}
              </p>
            </div>
            <div className="review-room-action-panel">
              <span className="eyebrow">审批数</span>
              <p>{inspectorData.summary.open_approvals}</p>
              <p className="muted-copy">当前链路中尚未关闭的董事会审批。</p>
            </div>
            <div className="review-room-action-panel">
              <span className="eyebrow">故障数</span>
              <p>{inspectorData.summary.open_incidents}</p>
              <p className="muted-copy">可能阻断下游推进的未关闭故障。</p>
            </div>
          </section>

          <section className="dependency-node-list" aria-label="依赖节点列表">
            {inspectorData.nodes.map((node) => (
              <article
                key={node.node_id}
                className={`dependency-node ${node.is_blocked ? 'is-blocked' : ''} ${
                  node.is_critical_path ? 'is-critical' : ''
                }`}
              >
                <div className="dependency-node-header">
                  <div>
                    <p className="eyebrow">{node.phase}</p>
                    <h3>{node.ticket_id ?? node.node_id}</h3>
                  </div>
                  <div className="dependency-node-badges">
                    <span>{formatLabel(node.block_reason)}</span>
                    <span>{formatLabel(node.node_status)}</span>
                  </div>
                </div>

                <dl className="dependency-node-grid">
                  <div>
                    <dt>依赖上游</dt>
                    <dd>{node.depends_on_ticket_id ?? '根节点'}</dd>
                  </div>
                  <div>
                    <dt>下游影响</dt>
                    <dd>
                      {node.dependent_ticket_ids.length > 0
                        ? node.dependent_ticket_ids.join(', ')
                        : '无下游工单'}
                    </dd>
                  </div>
                  <div>
                    <dt>执行角色</dt>
                    <dd>{node.role_profile_ref ?? '未分配'}</dd>
                  </div>
                  <div>
                    <dt>输出结构</dt>
                    <dd>{node.output_schema_ref ?? '无输出结构'}</dd>
                  </div>
                </dl>

                <div className="dependency-node-footer">
                  <div>
                    <strong>产物范围</strong>
                    <p>
                      {node.expected_artifact_scope.length > 0
                        ? node.expected_artifact_scope.join(' · ')
                        : '未附带写入范围。'}
                    </p>
                  </div>
                  <div className="dependency-node-actions">
                    {node.open_review_pack_id ? (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => onOpenReview(node.open_review_pack_id as string)}
                      >
                        打开评审室
                      </button>
                    ) : null}
                    {node.open_incident_id ? (
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => onOpenIncident(node.open_incident_id as string)}
                      >
                        打开故障详情
                      </button>
                    ) : null}
                  </div>
                </div>
              </article>
            ))}
          </section>
        </div>
      )}
    </Drawer>
  )
}
