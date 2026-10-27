import React, { createRef } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EditLibraryModal } from './EditLibraryModal'

const library = {
  id: 'lib-99',
  workspace_id: 'w',
  project_id: 'p',
  name: 'Product Knowledge',
  description: 'Internal docs',
  status: 'active',
  created_at: '',
  updated_at: '',
}

describe('EditLibraryModal', () => {
  afterEach(cleanup)

  it('renders in document.body via portal', () => {
    render(
      <EditLibraryModal library={library} onClose={vi.fn()} onSave={vi.fn()} />,
    )
    const dialog = screen.getByRole('dialog')
    expect(document.body.contains(dialog)).toBe(true)
  })

  it('populates fields and saves with preserved id', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()
    const focusRef = createRef<HTMLButtonElement>()
    render(
      <div>
        <button ref={focusRef} type="button">
          trigger
        </button>
        <EditLibraryModal library={library} returnFocusRef={focusRef} onClose={onClose} onSave={onSave} />
      </div>,
    )
    expect(screen.getByDisplayValue('Product Knowledge')).toBeTruthy()
    expect(screen.getByDisplayValue('Internal docs')).toBeTruthy()
    fireEvent.change(screen.getByDisplayValue('Product Knowledge'), { target: { value: 'Renamed library' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(onSave).toHaveBeenCalledWith({ name: 'Renamed library', description: 'Internal docs' })
  })

  it('cancel closes modal', () => {
    const onClose = vi.fn()
    render(<EditLibraryModal library={library} onClose={onClose} onSave={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('Escape closes modal', () => {
    const onClose = vi.fn()
    render(<EditLibraryModal library={library} onClose={onClose} onSave={vi.fn()} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
