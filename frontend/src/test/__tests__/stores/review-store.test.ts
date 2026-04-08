import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { resetReviewStore, useReviewStore } from '../../../stores/review-store'

function envelope<T>(data: T) {
  return {
    schema_version: '2026-04-04.boardroom.v1',
    generated_at: '2026-04-04T04:00:00+08:00',
    projection_version: 1,
    cursor: 'evt_001',
    data,
  }
}

describe('review-store', () => {
  beforeEach(() => {
    resetReviewStore()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    resetReviewStore()
  })

  it('loads review room data and clears stale inspector data', async () => {
    useReviewStore.setState({ developerInspector: { availability: 'stale' } as never })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(envelope({ review_pack: { meta: { review_pack_id: 'brp_001' } } })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await useReviewStore.getState().loadReviewRoom('brp_001')

    expect(useReviewStore.getState().reviewRoom).toMatchObject({
      review_pack: { meta: { review_pack_id: 'brp_001' } },
    })
    expect(useReviewStore.getState().developerInspector).toBeNull()
  })

  it('loads developer inspector detail for the active review pack', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(envelope({ availability: 'ready' })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await useReviewStore.getState().loadDeveloperInspector('brp_001')

    expect(useReviewStore.getState().developerInspector).toMatchObject({ availability: 'ready' })
    expect(useReviewStore.getState().error).toBeNull()
  })

  it('records a readable error when review room loading fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('review missing', {
        status: 404,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )

    await useReviewStore.getState().loadReviewRoom('brp_missing')

    expect(useReviewStore.getState().reviewRoom).toBeNull()
    expect(useReviewStore.getState().error).toBe('review missing')
  })

  it('keeps current review content and avoids error flash when background review refresh fails', async () => {
    useReviewStore.setState({
      reviewRoom: { review_pack: { meta: { review_pack_id: 'brp_001' } } as never } as never,
      error: null,
    })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('temporary fetch failure', {
        status: 503,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )

    await useReviewStore.getState().loadReviewRoom('brp_001', { background: true })

    expect(useReviewStore.getState().reviewRoom).toMatchObject({
      review_pack: { meta: { review_pack_id: 'brp_001' } },
    })
    expect(useReviewStore.getState().error).toBeNull()
  })
})
