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
      title={meetingData?.topic ?? 'Loading meeting room'}
      subtitle="Meeting Room"
    >
      {loading ? (
        <div className="review-room-state">Loading the current meeting room...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : meetingData == null ? (
        <div className="review-room-state">No meeting detail is available for this item.</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">Meeting type</span>
              <p>{meetingData.meeting_type}</p>
            </div>
            <div>
              <span className="eyebrow">Status</span>
              <p>{meetingData.status}</p>
            </div>
            <div>
              <span className="eyebrow">Review status</span>
              <p>{meetingData.review_status ?? 'Not submitted'}</p>
            </div>
          </section>

          <section className="review-room-columns">
            <div className="review-room-column">
              <h3>Participants</h3>
              <ul className="review-room-list">
                {meetingData.participants.map((participant) => (
                  <li key={participant.employee_id}>
                    <strong>
                      {participant.employee_id}
                      {participant.is_recorder ? ' (Recorder)' : ''}
                    </strong>
                    <span>
                      {participant.role_type} · {participant.meeting_responsibility}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="review-room-column">
              <h3>Linked records</h3>
              <ul className="review-room-list">
                <li>
                  <strong>Recorder</strong>
                  <span>{meetingData.recorder_employee_id}</span>
                </li>
                <li>
                  <strong>Source ticket</strong>
                  <span>{meetingData.source_ticket_id}</span>
                </li>
                <li>
                  <strong>Source node</strong>
                  <span>{meetingData.source_node_id}</span>
                </li>
                <li>
                  <strong>Opened</strong>
                  <span>{formatTimestamp(meetingData.opened_at, 'Unknown')}</span>
                </li>
              </ul>
            </div>
          </section>

          <section className="review-room-column">
            <h3>Round timeline</h3>
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
                  <span>{formatTimestamp(round.completed_at, 'Unknown')}</span>
                </li>
              ))}
              {meetingData.rounds.length === 0 ? (
                <li>
                  <strong>Rounds</strong>
                  <span>No round summary is available yet.</span>
                </li>
              ) : null}
            </ul>
          </section>

          <section className="review-room-columns">
            <div className="review-room-column">
              <h3>Consensus</h3>
              <p className="muted-copy">
                {meetingData.consensus_summary ?? 'No consensus summary has been generated yet.'}
              </p>
            </div>
            <div className="review-room-column">
              <h3>No-consensus reason</h3>
              <p className="muted-copy">
                {meetingData.no_consensus_reason ?? 'The meeting closed with a candidate conclusion.'}
              </p>
            </div>
          </section>

          <section className="review-room-action-panel">
            <h3>Next stop</h3>
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
              Open linked review room
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
