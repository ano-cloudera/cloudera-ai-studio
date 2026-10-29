import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CitationRecord } from '../../types/api'
import { RagSourcesList } from './RagSourcesList'
import { sourceFileKind } from './SourceFileIcon'

const cite = (over: Partial<CitationRecord>): CitationRecord => ({
  chunk_id: 'c',
  document_id: 'd1',
  filename: 'Credit approval policy.pdf',
  page_number: 2,
  snippet: 's',
  score: 1,
  ...over,
})

describe('sourceFileKind', () => {
  it.each([
    ['policy.pdf', 'pdf'],
    ['POLICY.PDF', 'pdf'],
    ['data.csv', 'spreadsheet'],
    ['book.xlsx', 'spreadsheet'],
    ['guide.docx', 'document'],
    ['notes.md', 'text'],
    ['archive.bin', 'other'],
    [null, 'other'],
  ])('%s is %s', (name, kind) => {
    expect(sourceFileKind(name as string | null)).toBe(kind)
  })
})

describe('RagSourcesList', () => {
  afterEach(cleanup)

  it('lists each file once with every cited page and a typed icon', () => {
    render(
      <RagSourcesList
        onViewSources={vi.fn()}
        citations={[
          cite({ chunk_id: 'a', page_number: 2 }),
          cite({ chunk_id: 'b', page_number: 1 }),
          cite({ chunk_id: 'c', page_number: 2 }),
          cite({ chunk_id: 'd', document_id: 'd2', filename: 'rates.csv', page_number: null }),
        ]}
      />,
    )
    expect(screen.getAllByText('Credit approval policy.pdf')).toHaveLength(1)
    const kinds = screen.getAllByTestId('source-file-icon').map(node => node.getAttribute('data-kind'))
    expect(kinds).toEqual(['pdf', 'spreadsheet'])
    expect(screen.getAllByText(/^Page \d$/).map(node => node.textContent)).toEqual(['Page 1', 'Page 2'])
  })

  it('opens the original PDF from the row and from each page chip', () => {
    render(<RagSourcesList citations={[cite({ page_number: 2 }), cite({ chunk_id: 'b', page_number: 1 })]} />)
    const links = screen.getAllByRole('link')
    const hrefs = links.map(link => link.getAttribute('href'))
    expect(hrefs).toContain('/api/v1/documents/d1/file#page=1')
    expect(hrefs).toContain('/api/v1/documents/d1/file#page=2')
    expect(links.every(link => link.getAttribute('target') === '_blank')).toBe(true)
  })

  it('does not link a source that is not a PDF', () => {
    render(<RagSourcesList citations={[cite({ filename: 'rates.csv', page_number: null })]} />)
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('opens the sources drawer from the footer link', () => {
    const onView = vi.fn()
    render(<RagSourcesList onViewSources={onView} citations={[cite({})]} />)
    fireEvent.click(screen.getByTestId('rag-view-sources'))
    expect(onView).toHaveBeenCalledTimes(1)
  })
})
