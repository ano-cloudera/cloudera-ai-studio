import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { KnowledgePage, LIBRARY_DOCUMENT_TABLE_MIN_HEIGHT_CLASS } from './KnowledgePage'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('../lib/api', () => ({
  api: {
    listLibrariesPaginated: vi.fn(),
    getLibrary: vi.fn(),
    createLibrary: vi.fn(),
    updateLibrary: vi.fn(),
    deleteLibrary: vi.fn(),
    listLibraryDocumentsPaginated: vi.fn(),
    uploadLibraryDocument: vi.fn(),
    deleteDocument: vi.fn(),
    processDocument: vi.fn(),
    renameDocument: vi.fn(),
    bulkDeleteLibraries: vi.fn(),
    bulkDeleteDocuments: vi.fn(),
  },
}))

const sampleLibrary = {
  id: 'lib-1',
  workspace_id: 'w',
  project_id: 'p',
  name: 'Sales docs',
  description: 'Team notes',
  status: 'active',
  created_at: '2026-10-12T00:00:00Z',
  updated_at: '2026-10-16T00:00:00Z',
  document_count: 1,
  library_status: 'ready',
  document_limit: 100,
}

describe('Knowledge page v2.1', () => {
  afterEach(cleanup)

  it('renders library table without default checkboxes and opens detail via name', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [sampleLibrary],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    })
    vi.mocked(api.getLibrary).mockResolvedValue({ library: sampleLibrary })
    vi.mocked(api.listLibraryDocumentsPaginated).mockResolvedValue({
      items: [{
        id: 'doc-1',
        workspace_id: 'w',
        project_id: 'p',
        library_id: 'lib-1',
        filename: 'brief.pdf',
        original_filename: 'brief.pdf',
        mime_type: 'application/pdf',
        size_bytes: 1200,
        status: 'READY',
        checksum: null,
        chunk_count: 3,
        created_at: '2026-10-15T00:00:00Z',
        updated_at: '2026-10-16T00:00:00Z',
      }],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    })

    render(<KnowledgePage />)
    await screen.findByText('Sales docs')
    expect(screen.queryByRole('checkbox', { name: /Select Sales docs/i })).toBeNull()
    expect(screen.getByRole('button', { name: 'Select libraries' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Sales docs' }))
    await waitFor(() => expect(api.listLibraryDocumentsPaginated).toHaveBeenCalled())
    expect(screen.getByText('brief.pdf')).toBeTruthy()
    expect(screen.getByText('Ask this library')).toBeTruthy()

    const panel = screen.getByTestId('library-document-table-panel')
    expect(panel.className).toContain('min-h-[450px]')
    expect(LIBRARY_DOCUMENT_TABLE_MIN_HEIGHT_CLASS).toBe('min-h-[450px]')
    expect(within(panel).getByText('Showing 1–1 of 1')).toBeTruthy()
  })

  it('enters library selection mode and bulk toolbar', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [sampleLibrary],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    })
    render(<KnowledgePage />)
    await screen.findByText('Sales docs')
    fireEvent.click(screen.getByRole('button', { name: 'Select libraries' }))
    const checkbox = screen.getByRole('checkbox', { name: 'Select Sales docs' })
    fireEvent.click(checkbox)
    expect(screen.getByText('1 selected')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Delete selected' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('checkbox', { name: 'Select Sales docs' })).toBeNull()
  })

  it('calls bulk delete with selected library ids', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [sampleLibrary],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    })
    vi.mocked(api.bulkDeleteLibraries).mockResolvedValue({
      deleted: [{ id: 'lib-1', name: 'Sales docs' }],
      failed: [],
      deleted_count: 1,
      failed_count: 0,
    })
    render(<KnowledgePage />)
    await screen.findByText('Sales docs')
    fireEvent.click(screen.getByRole('button', { name: 'Select libraries' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Sales docs' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete selected' }))
    fireEvent.click(screen.getByRole('button', { name: /Delete 1 library/i }))
    await waitFor(() => expect(api.bulkDeleteLibraries).toHaveBeenCalledWith({ ids: ['lib-1'] }))
  })

  it('shows Edit in action menu and opens edit modal', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [sampleLibrary],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    })
    vi.mocked(api.updateLibrary).mockResolvedValue({
      library: { ...sampleLibrary, name: 'Updated name' },
    })

    render(<KnowledgePage />)
    await screen.findByText('Sales docs')
    fireEvent.click(screen.getByRole('button', { name: /Actions for Sales docs/i }))
    expect(screen.queryByText('Open')).toBeNull()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Edit library')).toBeTruthy()
    fireEvent.change(screen.getByDisplayValue('Sales docs'), { target: { value: 'Updated name' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() =>
      expect(api.updateLibrary).toHaveBeenCalledWith('lib-1', {
        name: 'Updated name',
        description: 'Team notes',
      }),
    )
  })

  it('requests library list with sort params', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 10,
      total: 0,
      total_pages: 0,
    })
    render(<KnowledgePage />)
    await waitFor(() => expect(api.listLibrariesPaginated).toHaveBeenCalled())
    expect(api.listLibrariesPaginated).toHaveBeenCalledWith(
      expect.objectContaining({ sort: 'updated_at', order: 'desc' }),
    )
  })

  it('opens create library modal', async () => {
    vi.mocked(api.listLibrariesPaginated).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 10,
      total: 0,
      total_pages: 0,
    })
    render(<KnowledgePage />)
    const createButtons = await screen.findAllByRole('button', { name: /Create library/i })
    fireEvent.click(createButtons[0])
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText('Create knowledge library')).toBeTruthy()
  })
})
