import { describe, expect, it } from 'vitest'

import { aiRegistryErrorMessage, assignmentSourceLabel, isValidSecretRef } from './aiRegistryUi'

describe('aiRegistryUi', () => {
  it('accepts env secret refs and rejects plaintext keys', () => {
    expect(isValidSecretRef('env://GEMINI_API_KEY')).toBe(true)
    expect(isValidSecretRef('sk-live-secret')).toBe(false)
  })

  it('maps assignment sources for display', () => {
    expect(assignmentSourceLabel('LEGACY_FALLBACK')).toMatch(/legacy/i)
    expect(assignmentSourceLabel('PROJECT')).toMatch(/project/i)
  })

  it('maps provider in use errors', () => {
    expect(aiRegistryErrorMessage({ code: 'PROVIDER_IN_USE', status: 409, message: 'x', retryable: false })).toMatch(
      /cannot be deleted/i,
    )
  })
})
