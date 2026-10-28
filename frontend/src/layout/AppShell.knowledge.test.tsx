import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TestBrandingWrapper } from '../test/testBrandingWrapper'
import { AppShell } from './AppShell'

vi.mock('next/navigation', () => ({ usePathname: () => '/knowledge' }))

describe('AppShell knowledge nav', () => {
  afterEach(cleanup)

  it('shows Knowledge when documents feature is enabled', () => {
    render(
      <TestBrandingWrapper>
        <AppShell>
          <div>Knowledge content</div>
        </AppShell>
      </TestBrandingWrapper>,
    )
    expect(screen.getAllByText('Knowledge').length).toBeGreaterThan(0)
  })
})
