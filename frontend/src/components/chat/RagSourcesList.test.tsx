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

  it('shows one white-card row per file and page with a typed icon', () => {
    render(
      <RagSourcesList
        onViewSources={vi.fn()}
        citations={[
          cite({ chunk_id: 'a', page_number: 2 }),
          cite({ chunk_id: 'b', page_number: 2 }),
          cite({ chunk_id: 'c', document_id: 'd2', filename: 'rates.csv', page_number: null }),
        ]}
      />,
    )
    expect(screen.getAllByText('Credit approval policy.pdf')).toHaveLength(1)
    const kinds = screen.getAllByTestId('source-file-icon').map(node => node.getAttribute('data-kind'))
    expect(kinds).toEqual(['pdf', 'spreadsheet'])
    expect(screen.getByText('Page 2')).toBeTruthy()
  })

  it('opens the sources drawer from the footer link', () => {
    const onView = vi.fn()
    render(<RagSourcesList onViewSources={onView} citations={[cite({})]} />)
    fireEvent.click(screen.getByTestId('rag-view-sources'))
    expect(onView).toHaveBeenCalledTimes(1)
  })
})
