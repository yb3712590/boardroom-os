import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SSEManager } from '../../../api/sse'

class FakeEventSource {
  static instances: FakeEventSource[] = []

  url: string
  listeners = new Map<string, Set<() => void>>()
  onerror: (() => void) | null = null
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: () => void) {
    const listeners = this.listeners.get(type) ?? new Set()
    listeners.add(listener)
    this.listeners.set(type, listeners)
  }

  emit(type: string) {
    this.listeners.get(type)?.forEach((listener) => listener())
  }
}

describe('api/sse', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('connects and dispatches boardroom invalidation events', () => {
    const onEvent = vi.fn()
    const manager = new SSEManager({
      url: '/api/v1/events/stream',
      onEvent,
    })

    manager.connect()
    FakeEventSource.instances[0].emit('boardroom-event')

    expect(onEvent).toHaveBeenCalledTimes(1)
  })

  it('reconnects after transport errors', () => {
    const onEvent = vi.fn()
    const manager = new SSEManager({
      url: '/api/v1/events/stream',
      onEvent,
      reconnectDelayMs: 1000,
      maxReconnectDelayMs: 4000,
    })

    manager.connect()
    FakeEventSource.instances[0].onerror?.()

    vi.advanceTimersByTime(1000)

    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('disposes active connection and stops reconnect timers', () => {
    const manager = new SSEManager({
      url: '/api/v1/events/stream',
      onEvent: vi.fn(),
      reconnectDelayMs: 1000,
    })

    manager.connect()
    FakeEventSource.instances[0].onerror?.()
    manager.dispose()
    vi.runAllTimers()

    expect(FakeEventSource.instances[0].close).toHaveBeenCalled()
    expect(FakeEventSource.instances).toHaveLength(1)
  })
})
