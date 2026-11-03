import React from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setFeatureOverrides } from '../lib/featureOverrides'
import { TestBrandingWrapper } from '../test/testBrandingWrapper'
import { AppShell } from './AppShell'

let path = '/'
vi.mock('next/navigation', () => ({ usePathname: () => path }))
vi.mock('../lib/api', () => ({ api: { getFeatureOverrides: vi.fn().mockResolvedValue({ overrides: {} }) } }))

const labels = () =>
  within(screen.getByRole('navigation', { name: 'Primary navigation' }))
    .getAllByRole('link')
    .map(link => link.textContent?.trim())

function show(children = <div>Page content</div>) {
  return render(
    <TestBrandingWrapper>
      <AppShell>{children}</AppShell>
    </TestBrandingWrapper>,
  )
}

describe('AppShell with workspace feature switches', () => {
  afterEach(() => {
    cleanup()
    setFeatureOverrides({}, { cache: false })
    path = '/'
  })

  it('removes a switched off menu and adds one that was switched on, without a reload', () => {
    show()
    expect(labels()).toContain('Usage')
    expect(labels()).not.toContain('Skills')
    act(() => setFeatureOverrides({ usage: false, skills: true }, { cache: false }))
    expect(labels()).not.toContain('Usage')
    expect(labels()).toContain('Skills')
    act(() => setFeatureOverrides({}, { cache: false }))
    expect(labels()).toContain('Usage')
  })

  it('shows a notice instead of a page that is switched off, with the way back', () => {
    path = '/prompts'
    show(<div>Prompts content</div>)
    expect(screen.getByText('Prompts content')).toBeTruthy()
    act(() => setFeatureOverrides({ prompts: false }, { cache: false }))
    expect(screen.queryByText('Prompts content')).toBeNull()
    expect(screen.getByTestId('feature-off-notice').textContent).toContain('Prompts is turned off')
    expect(screen.getByRole('link', { name: /Turn it on in Settings/ }).getAttribute('href')).toBe('/settings')
  })

  it('keeps Ask Data and Settings reachable whatever is stored', () => {
    path = '/settings'
    show(<div>Settings content</div>)
    act(() => setFeatureOverrides({ prompts: false, skills: false, usage: false, documents: false, semanticLayer: false, connectors: false }, { cache: false }))
    expect(screen.getByText('Settings content')).toBeTruthy()
    expect(labels()).toEqual(expect.arrayContaining(['Ask Data', 'Settings']))
  })
})
