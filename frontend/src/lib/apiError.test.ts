import { describe, expect, it } from 'vitest'

import { parseApiError, toAppApiError } from './apiError'

describe('apiError', () => {
  it('maps raw 404 text to product-safe copy', () => {
    const err = parseApiError(404, { detail: '404 Not Found' }, '404 Not Found')
    expect(err.message).toBe('The requested resource was not found.')
    expect(err.status).toBe(404)
  })

  it('maps network failures', () => {
    const err = toAppApiError(new TypeError('Failed to fetch'))
    expect(err.code).toBe('NETWORK_ERROR')
    expect(err.message).toContain('backend service')
  })
})
