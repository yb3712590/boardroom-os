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
        <p className="eyebrow">事件</p>
        <h2 id="event-ticker-title">近期事件脉冲</h2>
      </div>
      {loading ? <LoadingSkeleton lines={4} /> : null}
      {!loading && events.length === 0 ? <p className="muted-copy">近期未产生事件。</p> : null}
      <div className="event-list">
        {!loading &&
          events.map((event) => (
          <article key={event.event_id} className={`event-card severity-${event.severity.toLowerCase()}`}>
            <div className="event-card-main">
              <strong>{event.message}</strong>
              <span>{event.category}</span>
            </div>
            <div className="event-card-meta">
              <span>{event.related_ref ?? '无关联引用'}</span>
              <span>{formatRelativeTime(event.occurred_at)}</span>
            </div>
          </article>
          ))}
      </div>
    </section>
  )
}
