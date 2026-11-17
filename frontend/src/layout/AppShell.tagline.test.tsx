import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PublicBrandingProvider } from '../config/PublicBrandingContext'
import { resolvePublicBranding } from '../config/publicBranding'
import { AppShell } from './AppShell'

vi.mock('next/navigation', () => ({ usePathname: () => '/' }))

describe('header tagline', () => {
  afterEach(cleanup)

  it('shows what the name stands for beside the header title when one is configured', () => {
    const branding = { ...resolvePublicBranding(), headerTitle: 'PINTAR', headerTagline: 'Pertamina INtelligence for Trusted Analytics and Reporting' }
    render(
      <PublicBrandingProvider branding={branding}>
        <AppShell>
          <div>content</div>
        </AppShell>
      </PublicBrandingProvider>,
    )
    expect(screen.getByTestId('header-tagline').textContent).toBe('Pertamina INtelligence for Trusted Analytics and Reporting')
  })

  it('shows nothing extra when there is none', () => {
    const branding = { ...resolvePublicBranding(), headerTagline: '' }
    render(
      <PublicBrandingProvider branding={branding}>
        <AppShell>
          <div>content</div>
        </AppShell>
      </PublicBrandingProvider>,
    )
    expect(screen.queryByTestId('header-tagline')).toBeNull()
  })
})
