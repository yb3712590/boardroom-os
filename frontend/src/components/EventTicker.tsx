import type { DashboardData } from '../api'

type EventTickerProps = {
  events: DashboardData['event_stream_preview']
}

export function EventTicker({ events }: EventTickerProps) {
  return (
    <section className="support-panel" aria-labelledby="event-ticker-title">
      <div className="section-heading">
        <p className="eyebrow">Events</p>
        <h2 id="event-ticker-title">Recent event pulse</h2>
      </div>
      {events.length === 0 ? <p className="muted-copy">No recent events were emitted.</p> : null}
      <div className="event-list">
        {events.map((event) => (
          <article key={event.event_id} className={`event-card severity-${event.severity.toLowerCase()}`}>
            <div className="event-card-main">
              <strong>{event.message}</strong>
              <span>{event.category}</span>
            </div>
            <div className="event-card-meta">
              <span>{event.related_ref ?? 'No related ref'}</span>
              <span>{new Date(event.occurred_at).toLocaleString('en-US')}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
