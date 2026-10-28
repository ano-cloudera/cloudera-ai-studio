import React from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TestBrandingWrapper } from '../test/testBrandingWrapper'
import { buildPrimaryNavigation, AppShell } from './AppShell'

vi.mock('next/navigation', () => ({ usePathname: () => '/semantic-layer' }))

describe('AppShell semantic layer feature flag', () => {
  afterEach(cleanup)

  it('includes Semantic Layer in Build when feature enabled', async () => {
    vi.doUnmock('../config/appConfig')
    const nav = buildPrimaryNavigation()
    expect(nav.some(item => item.label === 'Semantic Layer' && item.href === '/semantic-layer')).toBe(true)

    render(
      <TestBrandingWrapper>
        <AppShell>
          <div>Semantic content</div>
        </AppShell>
      </TestBrandingWrapper>,
    )
    const primaryNav = screen.getByRole('navigation', { name: 'Primary navigation' })
    const labels = within(primaryNav)
      .getAllByRole('link')
      .map(link => link.textContent?.trim())
    expect(labels).toContain('Semantic Layer')
  })
})
