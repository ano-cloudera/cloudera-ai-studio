import React from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { appConfig } from '../config/appConfig'
import { TestBrandingWrapper } from '../test/testBrandingWrapper'
import { buildPrimaryNavigation, AppShell } from './AppShell'

vi.mock('next/navigation', () => ({ usePathname: () => '/' }))

describe('V2 application shell', () => {
  afterEach(cleanup)

  it('exposes accelerator navigation including Prompts and Skills', () => {
    const nav = buildPrimaryNavigation()
    expect(nav.map(item => item.label)).toEqual([
      'Ask Data',
      'Knowledge',
      'Semantic Layer',
      'Prompts',
      'Skills',
      'Data Sources',
      'Usage',
      'Settings',
    ])

    render(
      <TestBrandingWrapper>
        <AppShell>
          <div>Ask Data content</div>
        </AppShell>
      </TestBrandingWrapper>,
    )

    const primaryNav = screen.getByRole('navigation', { name: 'Primary navigation' })
    const labels = within(primaryNav)
      .getAllByRole('link')
      .map(link => link.textContent?.trim())
      .filter(Boolean)
    expect(labels).toEqual(['Ask Data', 'Knowledge', 'Semantic Layer', 'Prompts', 'Skills', 'Data Sources', 'Usage', 'Settings'])

    expect(screen.queryByText('Dashboard')).toBeNull()
    expect(screen.queryByText('AI Monitoring')).toBeNull()
    expect(screen.queryByText('Scan Intelligence')).toBeNull()
    expect(screen.getAllByText(appConfig.sidebarBrandTitle).length).toBeGreaterThan(0)
    screen.getByText('Ask Data content')
  })
})
