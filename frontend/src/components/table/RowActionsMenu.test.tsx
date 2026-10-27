import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RowActionsMenu } from './RowActionsMenu'

describe('RowActionsMenu', () => {
  afterEach(cleanup)

  it('opens menu in portal and closes on Escape', () => {
    const onEdit = vi.fn()
    render(
      <RowActionsMenu
        label="Row actions"
        items={[
          { key: 'edit', label: 'Edit', onClick: onEdit },
          { key: 'sep', separator: true },
          { key: 'del', label: 'Delete', danger: true, onClick: vi.fn() },
        ]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    expect(screen.getByRole('menu')).toBeTruthy()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit' }))
    expect(onEdit).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })
})
