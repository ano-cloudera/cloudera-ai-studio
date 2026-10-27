import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppShell } from './AppShell'

vi.mock('next/navigation', () => ({ usePathname: () => '/knowledge' }))

describe('AppShell knowledge nav', () => {
  afterEach(cleanup)

  it('shows Knowledge when documents feature is enabled', () => {
    render(<AppShell><div>Knowledge content</div></AppShell>)
    expect(screen.getAllByText('Knowledge').length).toBeGreaterThan(0)
  })
})
