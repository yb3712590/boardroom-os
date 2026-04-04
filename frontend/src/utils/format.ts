const DEFAULT_LOCALE = 'en-US'

const TIMESTAMP_OPTIONS: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(DEFAULT_LOCALE).format(value)
}

export function formatTimestamp(
  value: string | null | undefined,
  emptyLabel = 'No deadline',
): string {
  if (!value) {
    return emptyLabel
  }

  return new Intl.DateTimeFormat(DEFAULT_LOCALE, TIMESTAMP_OPTIONS).format(new Date(value))
}

export function formatRelativeTime(value: string): string {
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

  return formatTimestamp(value, 'Unknown time')
}

export function normalizeConstraints(value: string): string[] {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}
