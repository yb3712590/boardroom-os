import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { resetBoardroomStore, useBoardroomStore } from '../../../stores/boardroom-store'

function envelope<T>(data: T) {
  return {
    schema_version: '2026-04-04.boardroom.v1',
    generated_at: '2026-04-04T04:00:00+08:00',
    projection_version: 1,
    cursor: 'evt_001',
    data,
  }
}

describe('boardroom-store', () => {
  beforeEach(() => {
    resetBoardroomStore()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    resetBoardroomStore()
  })

  it('loads dashboard, inbox, workforce, and runtime provider together', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)

      if (url.endsWith('/api/v1/projections/dashboard')) {
        return new Response(JSON.stringify(envelope({ workspace: { workspace_id: 'ws', workspace_name: 'Default' } })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/api/v1/projections/inbox')) {
        return new Response(JSON.stringify(envelope({ items: [] })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/api/v1/projections/workforce')) {
        return new Response(JSON.stringify(envelope({ summary: { active_workers: 1 } })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return new Response(JSON.stringify(envelope({ effective_mode: 'LOCAL_DETERMINISTIC' })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })

    await useBoardroomStore.getState().loadSnapshot()

    expect(useBoardroomStore.getState().dashboard).toMatchObject({
      workspace: { workspace_id: 'ws', workspace_name: 'Default' },
    })
    expect(useBoardroomStore.getState().runtimeProvider).toMatchObject({
      effective_mode: 'LOCAL_DETERMINISTIC',
    })
    expect(useBoardroomStore.getState().snapshotError).toBeNull()
  })

  it('keeps snapshot data and records runtime provider errors when provider read fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)

      if (url.endsWith('/api/v1/projections/runtime-provider')) {
        return new Response('provider unavailable', {
          status: 503,
          headers: { 'Content-Type': 'text/plain' },
        })
      }
      if (url.endsWith('/api/v1/projections/dashboard')) {
        return new Response(JSON.stringify(envelope({ workspace: { workspace_id: 'ws', workspace_name: 'Default' } })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/api/v1/projections/inbox')) {
        return new Response(JSON.stringify(envelope({ items: [] })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return new Response(JSON.stringify(envelope({ summary: { active_workers: 1 } })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })

    await useBoardroomStore.getState().loadSnapshot()

    expect(useBoardroomStore.getState().dashboard).not.toBeNull()
    expect(useBoardroomStore.getState().runtimeProvider).toBeNull()
    expect(useBoardroomStore.getState().runtimeProviderError).toBe('provider unavailable')
  })

  it('records snapshot errors when the main projection batch fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('dashboard unavailable', {
        status: 503,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )

    await useBoardroomStore.getState().loadSnapshot()

    expect(useBoardroomStore.getState().dashboard).toBeNull()
    expect(useBoardroomStore.getState().snapshotError).toBe('请求失败：503')
  })
})
