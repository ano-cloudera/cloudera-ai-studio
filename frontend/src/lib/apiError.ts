export type AppApiError = {
  code: string
  status: number
  message: string
  requestId?: string
  details?: unknown
  retryable: boolean
}

export function isAppApiError(error: unknown): error is AppApiError {
  return Boolean(error && typeof error === 'object' && 'status' in error && 'message' in error)
}

export function parseApiError(status: number, body: unknown, fallbackText: string): AppApiError {
  let message = fallbackText
  let code = `HTTP_${status}`
  let requestId: string | undefined
  let details: unknown
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    const detail = record.detail
    if (typeof detail === 'string') {
      message = detail
    } else if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>
      if (typeof d.message === 'string') message = d.message
      if (typeof d.code === 'string') code = d.code
      if (typeof d.request_id === 'string') requestId = d.request_id
      details = detail
    }
    if (typeof record.message === 'string') message = record.message
    if (typeof record.code === 'string') code = record.code
    if (typeof record.request_id === 'string') requestId = record.request_id
  }
  return {
    code,
    status,
    message: productSafeMessage(status, message),
    requestId,
    details,
    retryable: status >= 500 || status === 408 || status === 429,
  }
}

function productSafeMessage(status: number, raw: string): string {
  const text = raw.trim()
  if (/^\d{3}\s/.test(text) || text.toLowerCase().includes('not found')) {
    if (status === 404) return 'The requested resource was not found.'
    if (status >= 500) return 'The server encountered an error.'
    return 'The request could not be completed.'
  }
  return text || 'Something went wrong.'
}

export function safeErrorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  return toAppApiError(error).message || fallback
}

export function toAppApiError(error: unknown): AppApiError {
  if (isAppApiError(error)) return error
  if (error instanceof TypeError) {
    return {
      code: 'NETWORK_ERROR',
      status: 0,
      message: 'We could not reach the backend service.',
      retryable: true,
    }
  }
  if (error instanceof Error) {
    const match = error.message.match(/^(\d{3})\s+(.*)$/)
    if (match) {
      return parseApiError(Number(match[1]), null, match[2])
    }
    return { code: 'UNKNOWN', status: 0, message: error.message, retryable: true }
  }
  return { code: 'UNKNOWN', status: 0, message: 'Something went wrong.', retryable: true }
}
