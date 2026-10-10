// API client. The access token lives only in memory (never localStorage).
// The refresh token is an httpOnly cookie the browser sends to /api/auth/* automatically.

let accessToken: string | null = null
let refreshInFlight: Promise<boolean> | null = null
let onSessionLost: (() => void) | null = null

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function setSessionLostHandler(fn: () => void) {
  onSessionLost = fn
}

// Single-flight: concurrent 401s share one refresh call. The server treats reuse of a
// rotated refresh token as theft, so two parallel refreshes would log the user out.
export function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' })
      .then(async (r) => {
        if (!r.ok) return false
        setAccessToken((await r.json()).access_token)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

async function parseError(r: Response): Promise<ApiError> {
  let detail: unknown = r.statusText
  try {
    const body = await r.json()
    detail = body.detail ?? body
  } catch {
    /* non-JSON error body */
  }
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg}]
    detail = detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ')
  }
  return new ApiError(r.status, detail)
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const r = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (r.status === 401 && retry && !path.startsWith('/api/auth/login')) {
    if (await refreshAccessToken()) return api<T>(path, init, false)
    setAccessToken(null)
    onSessionLost?.()
  }
  if (!r.ok) throw await parseError(r)
  if (r.status === 204) return undefined as T
  return (await r.json()) as T
}
