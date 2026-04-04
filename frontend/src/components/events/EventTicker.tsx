import type { DashboardData } from '../../types/api'

type EventTickerProps = {
  events: DashboardData['event_stream_preview']
}

function formatRelativeTime(value: string) {
  const diff = Date.now() - new Date(value).getTime()
  const seconds = Math.max(0, Math.floor(diff / 1000))
  if (seconds < 60) {
    return `${seconds}s ago`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
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
              <span>{formatRelativeTime(event.occurred_at)}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
