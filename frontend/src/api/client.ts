export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function parseError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get('content-type') ?? ''
  let detail: unknown = null

  try {
    if (contentType.includes('application/json')) {
      detail = await response.json()
    } else {
      detail = await response.text()
    }
  } catch {
    detail = null
  }

  const message =
    typeof detail === 'string' && detail.trim().length > 0
      ? detail
      : `Request failed: ${response.status}`

  return new ApiError(message, response.status, detail)
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw await parseError(response)
  }

  return response.json() as Promise<T>
}

export function getJson<T>(path: string): Promise<T> {
  return requestJson<T>(path)
}

export function postJson<T>(path: string, payload: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
