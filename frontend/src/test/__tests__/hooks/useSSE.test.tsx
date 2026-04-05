import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSSE } from '../../../hooks/useSSE'

class FakeEventSource {
  static instances: FakeEventSource[] = []

  listeners = new Map<string, Set<() => void>>()
  onerror: (() => void) | null = null

  constructor(_url: string) {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: () => void) {
    const listeners = this.listeners.get(type) ?? new Set()
    listeners.add(listener)
    this.listeners.set(type, listeners)
  }

  close() {}

  emit(type: string) {
    this.listeners.get(type)?.forEach((listener) => listener())
  }
}

function SSEHarness({ onInvalidate }: { onInvalidate: () => void }) {
  useSSE(onInvalidate)
  return null
}

describe('useSSE', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('debounces clustered boardroom invalidations into one refresh', () => {
    const onInvalidate = vi.fn()

    render(<SSEHarness onInvalidate={onInvalidate} />)

    const source = FakeEventSource.instances[0]
    source.emit('boardroom-event')
    source.emit('boardroom-event')
    source.emit('boardroom-event')

    expect(onInvalidate).toHaveBeenCalledTimes(0)

    vi.advanceTimersByTime(499)
    expect(onInvalidate).toHaveBeenCalledTimes(0)

    vi.advanceTimersByTime(1)
    expect(onInvalidate).toHaveBeenCalledTimes(1)
  })

  it('still delivers a later invalidation after the debounce window', () => {
    const onInvalidate = vi.fn()

    render(<SSEHarness onInvalidate={onInvalidate} />)

    const source = FakeEventSource.instances[0]
    source.emit('boardroom-event')
    vi.advanceTimersByTime(500)

    source.emit('boardroom-event')
    vi.advanceTimersByTime(500)

    expect(onInvalidate).toHaveBeenCalledTimes(2)
  })
})
