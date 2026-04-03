type SSEManagerOptions = {
  url: string
  onEvent: () => void
  reconnectDelayMs?: number
  maxReconnectDelayMs?: number
}

export class SSEManager {
  private readonly url: string
  private readonly onEvent: () => void
  private readonly reconnectDelayMs: number
  private readonly maxReconnectDelayMs: number
  private eventSource: EventSource | null = null
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  constructor(options: SSEManagerOptions) {
    this.url = options.url
    this.onEvent = options.onEvent
    this.reconnectDelayMs = options.reconnectDelayMs ?? 2000
    this.maxReconnectDelayMs = options.maxReconnectDelayMs ?? 30000
  }

  connect(): void {
    if (this.disposed || typeof EventSource === 'undefined') {
      return
    }

    this.cleanupEventSource()
    this.clearReconnectTimer()

    const source = new EventSource(this.url)
    this.eventSource = source

    source.addEventListener('boardroom-event', () => {
      this.reconnectAttempts = 0
      this.onEvent()
    })

    source.addEventListener('heartbeat', () => {
      this.reconnectAttempts = 0
    })

    source.onerror = () => {
      this.cleanupEventSource()
      this.scheduleReconnect()
    }
  }

  dispose(): void {
    this.disposed = true
    this.clearReconnectTimer()
    this.cleanupEventSource()
  }

  private scheduleReconnect(): void {
    if (this.disposed) {
      return
    }

    const delay = Math.min(
      this.reconnectDelayMs * 2 ** this.reconnectAttempts,
      this.maxReconnectDelayMs,
    )
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => this.connect(), delay)
  }

  private cleanupEventSource(): void {
    if (this.eventSource != null) {
      this.eventSource.close()
      this.eventSource = null
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer != null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}
