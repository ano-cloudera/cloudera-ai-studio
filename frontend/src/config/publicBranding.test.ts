import { afterEach, describe, expect, it, vi } from 'vitest'

import { resolvePublicBranding } from './publicBranding'

describe('header tagline', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('is empty by default, so the stock header is unchanged', () => {
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', '')
    expect(resolvePublicBranding().headerTagline).toBe('')
  })

  it('is empty when it only repeats the name, however it is written', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_NAME', 'PINTAR')
    vi.stubEnv('NEXT_PUBLIC_APP_NAME', 'PINTAR')
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', 'pintar')
    expect(resolvePublicBranding().headerTagline).toBe('')
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', 'Anywhere AI Studio')
    expect(resolvePublicBranding().headerTagline).toBe('')
  })

  it('carries a line that says more than the name', () => {
    vi.stubEnv('NEXT_PUBLIC_APP_NAME', 'PINTAR')
    vi.stubEnv('NEXT_PUBLIC_APP_TAGLINE', 'Pertamina INtelligence for Trusted Analytics and Reporting')
    expect(resolvePublicBranding().headerTagline).toBe('Pertamina INtelligence for Trusted Analytics and Reporting')
  })
})
