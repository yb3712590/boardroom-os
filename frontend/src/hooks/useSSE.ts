import { useEffect, useRef } from 'react'

import { SSEManager } from '../api/sse'

type UseSSEOptions = {
  debounceMs?: number
}

export function useSSE(onInvalidate: () => void, options?: UseSSEOptions): void {
  const invalidateRef = useRef(onInvalidate)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  invalidateRef.current = onInvalidate
  const debounceMs = options?.debounceMs ?? 500

  useEffect(() => {
    const manager = new SSEManager({
      url: '/api/v1/events/stream',
      onEvent: () => {
        if (debounceMs <= 0) {
          invalidateRef.current()
          return
        }

        if (debounceTimerRef.current != null) {
          clearTimeout(debounceTimerRef.current)
        }

        debounceTimerRef.current = setTimeout(() => {
          debounceTimerRef.current = null
          invalidateRef.current()
        }, debounceMs)
      },
    })

    manager.connect()
    return () => {
      if (debounceTimerRef.current != null) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
      manager.dispose()
    }
  }, [debounceMs])
}
