import { afterEach, describe, expect, it, vi } from 'vitest'

import { resolvePublicBranding } from './publicBranding'

describe('header tagline', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('is empty by default, so the stock header is unchanged', () => {
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', '')
    expect(resolvePublicBranding().headerTagline).toBe('')
  })

  it('is empty when it only repeats the name, however it is written', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_NAME', 'ACME')
    vi.stubEnv('NEXT_PUBLIC_APP_NAME', 'ACME')
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', 'acme')
    expect(resolvePublicBranding().headerTagline).toBe('')
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', 'Anywhere AI Studio')
    expect(resolvePublicBranding().headerTagline).toBe('')
  })

  it('carries a line that says more than the name', () => {
    vi.stubEnv('NEXT_PUBLIC_APP_NAME', 'ACME')
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', 'Acme INtelligence for Trusted Analytics and Reporting')
    expect(resolvePublicBranding().headerTagline).toBe('Acme INtelligence for Trusted Analytics and Reporting')
  })
})
