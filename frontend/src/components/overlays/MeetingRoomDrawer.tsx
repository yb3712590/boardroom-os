import type { MeetingDetailData } from '../../types/api'
import { formatTimestamp } from '../../utils/format'
import { Drawer } from '../shared/Drawer'

type MeetingRoomDrawerProps = {
  isOpen: boolean
  loading: boolean
  meetingData: MeetingDetailData | null
  error: string | null
  onClose: () => void
  onOpenReview: (reviewPackId: string) => void
}

export function MeetingRoomDrawer({
  isOpen,
  loading,
  meetingData,
  error,
  onClose,
  onOpenReview,
}: MeetingRoomDrawerProps) {
  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={meetingData?.topic ?? '会议室加载中'}
      subtitle="会议室"
    >
      {loading ? (
        <div className="review-room-state">正在加载当前会议室...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : meetingData == null ? (
        <div className="review-room-state">当前条目暂无会议详情。</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">会议类型</span>
              <p>{meetingData.meeting_type}</p>
            </div>
            <div>
              <span className="eyebrow">状态</span>
              <p>{meetingData.status}</p>
            </div>
            <div>
              <span className="eyebrow">评审状态</span>
              <p>{meetingData.review_status ?? '未提交'}</p>
            </div>
          </section>

          <section className="review-room-columns">
            <div className="review-room-column">
              <h3>参与者</h3>
              <ul className="review-room-list">
                {meetingData.participants.map((participant) => (
                  <li key={participant.employee_id}>
                    <strong>
                      {participant.employee_id}
                      {participant.is_recorder ? '（记录员）' : ''}
                    </strong>
                    <span>
                      {participant.role_type} · {participant.meeting_responsibility}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="review-room-column">
              <h3>关联记录</h3>
              <ul className="review-room-list">
                <li>
                  <strong>记录员</strong>
                  <span>{meetingData.recorder_employee_id}</span>
                </li>
                <li>
                  <strong>来源工单</strong>
                  <span>{meetingData.source_ticket_id}</span>
                </li>
                <li>
                  <strong>来源节点</strong>
                  <span>{meetingData.source_node_id}</span>
                </li>
                <li>
                  <strong>开启时间</strong>
                  <span>{formatTimestamp(meetingData.opened_at, '未知')}</span>
                </li>
              </ul>
            </div>
          </section>

          {meetingData.decision_record ? (
            <section className="review-room-columns">
              <div className="review-room-column">
                <h3>决策记录</h3>
                <ul className="review-room-list">
                  <li>
                    <strong>格式</strong>
                    <span>{meetingData.decision_record.format}</span>
                  </li>
                  <li>
                    <strong>上下文</strong>
                    <span>{meetingData.decision_record.context}</span>
                  </li>
                  <li>
                    <strong>决策</strong>
                    <span>{meetingData.decision_record.decision}</span>
                  </li>
                  <li>
                    <strong>共识摘要</strong>
                    <span>{meetingData.consensus_summary ?? '尚未生成共识摘要。'}</span>
                  </li>
                </ul>
              </div>
              <div className="review-room-column">
                <h3>实施依据</h3>
                <ul className="review-room-list">
                  {meetingData.decision_record.rationale.map((item) => (
                    <li key={`rationale:${item}`}>
                      <strong>理由</strong>
                      <span>{item}</span>
                    </li>
                  ))}
                  {meetingData.decision_record.consequences.map((item) => (
                    <li key={`consequence:${item}`}>
                      <strong>影响</strong>
                      <span>{item}</span>
                    </li>
                  ))}
                  {meetingData.decision_record.archived_context_refs.map((item) => (
                    <li key={`archive:${item}`}>
                      <strong>归档上下文</strong>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          ) : (
            <section className="review-room-columns">
              <div className="review-room-column">
                <h3>共识</h3>
                <p className="muted-copy">
                  {meetingData.consensus_summary ?? '尚未生成共识摘要。'}
                </p>
              </div>
              <div className="review-room-column">
                <h3>未达成共识原因</h3>
                <p className="muted-copy">
                  {meetingData.no_consensus_reason ?? '会议已结束，但当前仅有候选结论。'}
                </p>
              </div>
            </section>
          )}

          <section className="review-room-column">
            <h3>审计轨迹</h3>
            <p className="muted-copy">
              结构化回合会保留为审计材料；后续实施应遵循上方决策记录。
            </p>
            <ul className="review-room-list">
              {meetingData.rounds.map((round) => (
                <li key={`${round.round_type}:${round.round_index}`}>
                  <strong>
                    {round.round_index}. {round.round_type}
                  </strong>
                  <span>{round.summary}</span>
                  {round.notes.map((note) => (
                    <span key={note}>{note}</span>
                  ))}
                  <span>{formatTimestamp(round.completed_at, '未知')}</span>
                </li>
              ))}
              {meetingData.rounds.length === 0 ? (
                <li>
                  <strong>会议回合</strong>
                  <span>暂无回合摘要。</span>
                </li>
              ) : null}
            </ul>
          </section>

          <section className="review-room-action-panel">
            <h3>下一步</h3>
            <button
              type="button"
              className="secondary-button"
              disabled={!meetingData.review_pack_id}
              onClick={() => {
                if (!meetingData.review_pack_id) {
                  return
                }
                onOpenReview(meetingData.review_pack_id)
              }}
            >
              打开关联评审室
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
