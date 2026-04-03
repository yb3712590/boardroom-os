import { useEffect, useRef } from 'react'

import { SSEManager } from '../api/sse'

export function useSSE(onInvalidate: () => void): void {
  const invalidateRef = useRef(onInvalidate)
  invalidateRef.current = onInvalidate

  useEffect(() => {
    const manager = new SSEManager({
      url: '/api/v1/events/stream',
      onEvent: () => invalidateRef.current(),
    })

    manager.connect()
    return () => manager.dispose()
  }, [])
}
