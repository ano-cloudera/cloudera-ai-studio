import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BulkActionBar } from './BulkActionBar'

describe('BulkActionBar', () => {
  afterEach(cleanup)

  it('hidden when nothing selected', () => {
    const { container } = render(
      <BulkActionBar selectedCount={0} entityLabel="library" onClear={vi.fn()} onDelete={vi.fn()} />,
    )
    expect(container.textContent).toBe('')
  })

  it('shows toolbar when selected', () => {
    render(<BulkActionBar selectedCount={2} entityLabel="library" onClear={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText(/2 libraries selected/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Delete selected' })).toBeTruthy()
  })
})
