import type { InboxItem } from '../../types/domain'
import { LoadingSkeleton } from '../shared/LoadingSkeleton'

type InboxWellProps = {
  items: InboxItem[]
  loading: boolean
  onOpenReview: (reviewPackId: string) => void
  onOpenMeeting: (meetingId: string) => void
  onOpenIncident: (incidentId: string) => void
}

export function InboxWell({ items, loading, onOpenReview, onOpenMeeting, onOpenIncident }: InboxWellProps) {
  return (
    <aside className="inbox-well" aria-labelledby="inbox-title">
      <div className="section-heading">
        <p className="eyebrow">Inbox</p>
        <h2 id="inbox-title">Board actions and governance pressure</h2>
      </div>
      {loading ? <LoadingSkeleton lines={5} /> : null}
      {!loading && items.length === 0 ? <p className="muted-copy">There are no board escalations waiting right now.</p> : null}
      <div className="inbox-item-list">
        {items.map((item) => {
          const isReviewRoute = item.route_target.view === 'review_room' && item.route_target.review_pack_id
          const isMeetingRoute = item.route_target.view === 'meeting_room' && item.route_target.meeting_id
          const isIncidentRoute = item.route_target.view === 'incident_detail' && item.route_target.incident_id != null
          const content = (
            <>
              <span className="inbox-item-ribbon" aria-hidden="true" />
              <span className="inbox-item-copy">
                <strong>{item.title}</strong>
                <span>{item.summary}</span>
              </span>
              <span className="inbox-item-badges">{item.badges.join(' | ')}</span>
            </>
          )

          return isReviewRoute || isMeetingRoute || isIncidentRoute ? (
            <button
              key={item.inbox_item_id}
              type="button"
              className={`inbox-item inbox-item-${item.priority}`}
              onClick={() => {
                if (isReviewRoute) {
                  onOpenReview(item.route_target.review_pack_id as string)
                  return
                }
                if (isMeetingRoute) {
                  onOpenMeeting(item.route_target.meeting_id as string)
                  return
                }
                onOpenIncident(item.route_target.incident_id as string)
              }}
            >
              {content}
            </button>
          ) : (
            <div key={item.inbox_item_id} className={`inbox-item inbox-item-${item.priority}`}>
              {content}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
