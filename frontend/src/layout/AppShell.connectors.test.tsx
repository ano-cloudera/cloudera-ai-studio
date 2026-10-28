import React from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TestBrandingWrapper } from '../test/testBrandingWrapper'
import { buildPrimaryNavigation, AppShell } from './AppShell'

vi.mock('next/navigation', () => ({ usePathname: () => '/connectors' }))

describe('AppShell connectors feature flag', () => {
  afterEach(cleanup)

  it('includes Data Sources in Context when feature enabled', () => {
    const nav = buildPrimaryNavigation()
    expect(nav.some(item => item.label === 'Data Sources' && item.href === '/connectors')).toBe(true)

    render(
      <TestBrandingWrapper>
        <AppShell>
          <div>Connectors content</div>
        </AppShell>
      </TestBrandingWrapper>,
    )
    const primaryNav = screen.getByRole('navigation', { name: 'Primary navigation' })
    const labels = within(primaryNav)
      .getAllByRole('link')
      .map(link => link.textContent?.trim())
    expect(labels).toContain('Data Sources')
    expect(labels).not.toContain('Connectors')
  })
})
