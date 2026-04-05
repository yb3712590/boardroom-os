import type { DashboardData } from '../../types/api'
import { LoadingSkeleton } from '../shared/LoadingSkeleton'
import { formatRelativeTime } from '../../utils/format'

type EventTickerProps = {
  events: DashboardData['event_stream_preview']
  loading?: boolean
}

export function EventTicker({ events, loading = false }: EventTickerProps) {
  return (
    <section className="support-panel" aria-labelledby="event-ticker-title">
      <div className="section-heading">
        <p className="eyebrow">Events</p>
        <h2 id="event-ticker-title">Recent event pulse</h2>
      </div>
      {loading ? <LoadingSkeleton lines={4} /> : null}
      {!loading && events.length === 0 ? <p className="muted-copy">No recent events were emitted.</p> : null}
      <div className="event-list">
        {!loading &&
          events.map((event) => (
          <article key={event.event_id} className={`event-card severity-${event.severity.toLowerCase()}`}>
            <div className="event-card-main">
              <strong>{event.message}</strong>
              <span>{event.category}</span>
            </div>
            <div className="event-card-meta">
              <span>{event.related_ref ?? 'No related ref'}</span>
              <span>{formatRelativeTime(event.occurred_at)}</span>
            </div>
          </article>
          ))}
      </div>
    </section>
  )
}
