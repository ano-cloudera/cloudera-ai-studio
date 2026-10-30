import { describe, expect, it } from 'vitest'

import {
  aiRegistryErrorMessage,
  assignmentSourceLabel,
  isValidProviderKey,
  isValidSecretRef,
  normalizeProviderKey,
} from './aiRegistryUi'

describe('aiRegistryUi', () => {
  it('accepts env secret refs and rejects plaintext keys', () => {
    expect(isValidSecretRef('env://GEMINI_API_KEY')).toBe(true)
    expect(isValidSecretRef('sk-live-secret')).toBe(false)
  })

  it('validates provider keys as lowercase ids', () => {
    expect(isValidProviderKey('gemini')).toBe(true)
    expect(isValidProviderKey('google_gemini')).toBe(true)
    expect(isValidProviderKey('XXXX')).toBe(false)
    expect(normalizeProviderKey('Google Gemini')).toBe('google_gemini')
  })

  it('maps assignment sources for display', () => {
    expect(assignmentSourceLabel('LEGACY_FALLBACK')).toMatch(/legacy/i)
    expect(assignmentSourceLabel('PROJECT')).toMatch(/project/i)
  })

  it('maps provider in use errors', () => {
    expect(aiRegistryErrorMessage({ code: 'PROVIDER_IN_USE', status: 409, message: 'x', retryable: false })).toMatch(
      /could not be deleted/i,
    )
  })
})
