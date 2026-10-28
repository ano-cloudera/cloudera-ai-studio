import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../lib/api'
import { SaveToKnowledgeModal } from './SaveToKnowledgeModal'

vi.mock('../../lib/api', () => ({
  api: {
    listLibrariesPaginated: vi.fn(),
    saveChatAttachmentToKnowledge: vi.fn(),
  },
}))

describe('SaveToKnowledgeModal', () => {
  afterEach(cleanup)

  it('loads libraries and saves to existing library', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [{ id: 'lib-1', name: 'Product Knowledge', document_count: 1, document_limit: 100 }],
      page: 1,
      page_size: 100,
      total: 1,
      total_pages: 1,
    } as never)
    vi.mocked(api.saveChatAttachmentToKnowledge).mockResolvedValue({
      saved: { document_id: 'doc-1', library_id: 'lib-1' },
    } as never)
    const onSaved = vi.fn()
    const onClose = vi.fn()

    render(
      <SaveToKnowledgeModal
        open
        attachmentId="att-1"
        attachmentName="notes.txt"
        onClose={onClose}
        onSaved={onSaved}
      />,
    )

    expect(await screen.findByText('Save to Knowledge')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.saveChatAttachmentToKnowledge).toHaveBeenCalledWith('att-1', { library_id: 'lib-1' }))
    expect(onSaved).toHaveBeenCalledWith('Saved to Product Knowledge')
    expect(onClose).toHaveBeenCalled()
  })

  it('allows typing a full library name without losing focus on parent re-render', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
      total_pages: 0,
    } as never)
    const onClose = vi.fn()
    const { rerender } = render(
      <SaveToKnowledgeModal
        open
        attachmentId="att-1"
        attachmentName="Cloudera Deck.pdf"
        onClose={onClose}
        onSaved={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByLabelText('Create new library'))
    const input = await screen.findByPlaceholderText('e.g. Cloudera AI Infrastructure')
    fireEvent.change(input, { target: { value: 'Cloudera Infrastructure' } })
    rerender(
      <SaveToKnowledgeModal
        open
        attachmentId="att-1"
        attachmentName="Cloudera Deck.pdf"
        onClose={() => onClose()}
        onSaved={vi.fn()}
      />,
    )
    expect((input as HTMLInputElement).value).toBe('Cloudera Infrastructure')
  })
})
