import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, getJson, postJson } from '../../../api/client'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('api/client', () => {
  it('returns parsed JSON for successful GET requests', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(getJson<{ ok: boolean }>('/api/test')).resolves.toEqual({ ok: true })
  })

  it('throws ApiError with response detail for non-2xx responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Broken request', {
        status: 400,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )

    await expect(postJson('/api/test', { value: 1 })).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Broken request',
      status: 400,
    } satisfies Partial<ApiError>)
  })
})
