import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SemanticAuthoringTableShell } from './authoring/SemanticAuthoringTableShell'
import { SEMANTIC_DEFAULT_PAGE_SIZE, SEMANTIC_PAGE_SIZE_OPTIONS, semanticTableBodyMaxHeightClass } from './authoring/semanticTableConstants'
import { useSemanticPaginatedList } from './authoring/useSemanticPaginatedList'

function TableHarness() {
  const list = useSemanticPaginatedList(
    'v1',
    async () => ({
      items: [{ id: '1', name: 'Row' }],
      meta: { total: 14, page: 1, page_size: SEMANTIC_DEFAULT_PAGE_SIZE },
    }),
    [],
  )
  return (
    <SemanticAuthoringTableShell
      testId="semantic-table-harness"
      searchPlaceholder="Search…"
      search={list.search}
      onSearchChange={list.setSearch}
      loading={false}
      error={null}
      onRetry={() => undefined}
      emptyMessage="Empty"
      emptyColSpan={2}
      hasRows={list.items.length > 0}
      addLabel=""
      onAdd={() => undefined}
      readOnly
      selectionMode={{ active: false, enter: () => undefined, exit: () => undefined }}
      page={list.page}
      pageSize={list.pageSize}
      total={list.total}
      onPageChange={list.setPage}
      onPageSizeChange={list.setPageSize}
    >
      <thead className="app-table-head">
        <tr>
          <th className="px-3 py-2">Name</th>
        </tr>
      </thead>
      <tbody>
        {list.items.map(r => (
          <tr key={r.id}>
            <td className="px-3 py-2">{r.name}</td>
          </tr>
        ))}
      </tbody>
    </SemanticAuthoringTableShell>
  )
}

describe('Semantic table UX', () => {
  afterEach(cleanup)

  it('defaults page size to 5', () => {
    expect(SEMANTIC_DEFAULT_PAGE_SIZE).toBe(5)
    expect([...SEMANTIC_PAGE_SIZE_OPTIONS]).toEqual([5, 10, 20])
  })

  it('bounds scroll body height from page size', () => {
    expect(semanticTableBodyMaxHeightClass(5)).toContain('max-h')
    expect(semanticTableBodyMaxHeightClass(10)).not.toBe(semanticTableBodyMaxHeightClass(5))
  })

  it('renders scroll body and pagination outside scroll region', async () => {
    render(<TableHarness />)
    await waitFor(() => expect(screen.getByTestId('semantic-table-harness-scroll-body')).toBeTruthy())
    expect(screen.getByTestId('semantic-table-harness-pagination')).toBeTruthy()
    expect(screen.getByText(/Showing 1–/)).toBeTruthy()
    expect(screen.getByDisplayValue('5')).toBeTruthy()
    SEMANTIC_PAGE_SIZE_OPTIONS.forEach(n => {
      expect(screen.getByRole('option', { name: String(n) })).toBeTruthy()
    })
  })

  it('page size change updates selector', async () => {
    render(<TableHarness />)
    await waitFor(() => screen.getByDisplayValue('5'))
    fireEvent.change(screen.getByDisplayValue('5'), { target: { value: '10' } })
    expect(screen.getByDisplayValue('10')).toBeTruthy()
  })
})
