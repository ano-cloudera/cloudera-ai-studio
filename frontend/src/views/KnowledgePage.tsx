'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, BookOpen, Plus, Upload } from 'lucide-react'
import { EmptyState } from '../components/EmptyState'
import { PageCenter } from '../components/PageCenter'
import { ServiceErrorState } from '../components/ServiceErrorState'
import { EditLibraryModal } from '../components/knowledge/EditLibraryModal'
import { DocumentUploadQueue, type UploadQueueItem } from '../components/knowledge/DocumentUploadQueue'
import { SimpleModal } from '../components/knowledge/SimpleModal'
import { TablePagination } from '../components/knowledge/TablePagination'
import { BulkDeleteDialog } from '../components/table/BulkDeleteDialog'
import { RowActionsMenu } from '../components/table/RowActionsMenu'
import { SortableColumnHeader } from '../components/table/SortableColumnHeader'
import { TableHeaderCheckbox, TableRowCheckbox } from '../components/table/TableSelectionCheckbox'
import { TableSelectionModeButton } from '../components/table/TableSelectionModeButton'
import { bulkDeleteFailureDetails, bulkDeleteSummary } from '../lib/bulkDeleteFeedback'
import { nextSortState } from '../lib/tableSort'
import { useTableSelection } from '../lib/useTableSelection'
import { useTableSelectionMode } from '../lib/useTableSelectionMode'

/** Stable document table viewport on library detail (desktop). */
export const LIBRARY_DOCUMENT_TABLE_MIN_HEIGHT_CLASS = 'min-h-[450px]'
import { api } from '../lib/api'
import { knowledgeLibraryContext, setPendingChatContext } from '../lib/chatContext'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../lib/apiError'
import type { DocumentRecord, DocumentStatus, LibraryRecord } from '../types/api'
import {
  documentStatusLabel,
  formatBytes,
  formatRelative,
  formatShortDate,
  libraryStatusLabel,
  mimeShort,
} from './knowledge/knowledgeFormat'

function StatusPill({ status }: { status: DocumentStatus | string }) {
  const normalized = String(status).toUpperCase()
  const tone =
    normalized === 'READY'
      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
      : normalized === 'FAILED'
        ? 'bg-red-50 text-red-800 border-red-200'
        : normalized === 'PROCESSING' || normalized === 'QUEUED'
          ? 'bg-amber-50 text-amber-900 border-amber-200'
          : 'bg-slate-50 text-slate-700 border-slate-200'
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${tone}`}>
      {documentStatusLabel(status as DocumentStatus)}
    </span>
  )
}

type LibrarySortField = 'name' | 'updated_at' | 'created_at' | 'document_count'
type DocumentSortField =
  | 'original_filename'
  | 'mime_type'
  | 'size_bytes'
  | 'chunk_count'
  | 'status'
  | 'created_at'
  | 'updated_at'

export function KnowledgePage() {
  const router = useRouter()
  const [selectedLibraryId, setSelectedLibraryId] = useState('')
  const [libraryDetail, setLibraryDetail] = useState<LibraryRecord | null>(null)

  const [libPage, setLibPage] = useState(1)
  const [libPageSize, setLibPageSize] = useState(10)
  const [libSearch, setLibSearch] = useState('')
  const [libSearchDebounced, setLibSearchDebounced] = useState('')
  const [libSort, setLibSort] = useState<LibrarySortField>('updated_at')
  const [libOrder, setLibOrder] = useState<'asc' | 'desc'>('desc')
  const [libTotal, setLibTotal] = useState(0)
  const [libraries, setLibraries] = useState<LibraryRecord[]>([])

  const [docPage, setDocPage] = useState(1)
  const [docPageSize, setDocPageSize] = useState(10)
  const [docSearch, setDocSearch] = useState('')
  const [docSearchDebounced, setDocSearchDebounced] = useState('')
  const [docStatus, setDocStatus] = useState('all')
  const [docSort, setDocSort] = useState<DocumentSortField>('updated_at')
  const [docOrder, setDocOrder] = useState<'asc' | 'desc'>('desc')
  const [docTotal, setDocTotal] = useState(0)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])

  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const [actionError, setActionError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [newLibraryName, setNewLibraryName] = useState('')
  const [newLibraryDescription, setNewLibraryDescription] = useState('')
  const [editLibraryTarget, setEditLibraryTarget] = useState<LibraryRecord | null>(null)
  const [editLibrarySaving, setEditLibrarySaving] = useState(false)
  const [editLibraryError, setEditLibraryError] = useState('')
  const editLibraryFocusRef = useRef<HTMLButtonElement | null>(null)
  const [deleteLibraryTarget, setDeleteLibraryTarget] = useState<LibraryRecord | null>(null)
  const [deleteDocTarget, setDeleteDocTarget] = useState<DocumentRecord | null>(null)
  const [reprocessTarget, setReprocessTarget] = useState<DocumentRecord | null>(null)
  const [renameDocTarget, setRenameDocTarget] = useState<DocumentRecord | null>(null)
  const [renameDocValue, setRenameDocValue] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadQueue, setUploadQueue] = useState<UploadQueueItem[]>([])
  const [libraryBulkConfirm, setLibraryBulkConfirm] = useState(false)
  const [documentBulkConfirm, setDocumentBulkConfirm] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const librarySelection = useTableSelection()
  const documentSelection = useTableSelection()
  const librarySelectionMode = useTableSelectionMode(librarySelection.clear)
  const documentSelectionMode = useTableSelectionMode(documentSelection.clear)

  const searchLibTimer = useRef<number | null>(null)
  const searchDocTimer = useRef<number | null>(null)

  useEffect(() => {
    window.clearTimeout(searchLibTimer.current ?? undefined)
    searchLibTimer.current = window.setTimeout(() => setLibSearchDebounced(libSearch), 300)
    return () => window.clearTimeout(searchLibTimer.current ?? undefined)
  }, [libSearch])

  useEffect(() => {
    window.clearTimeout(searchDocTimer.current ?? undefined)
    searchDocTimer.current = window.setTimeout(() => setDocSearchDebounced(docSearch), 300)
    return () => window.clearTimeout(searchDocTimer.current ?? undefined)
  }, [docSearch])

  const inDetail = Boolean(selectedLibraryId && libraryDetail)

  const documentLimit = libraryDetail?.document_limit ?? 100
  const documentCount = libraryDetail?.document_count ?? documents.length
  const atCapacity = documentCount >= documentLimit
  const capacityWarning = documentLimit > 0 && documentCount / documentLimit >= 0.8

  const refreshLibraries = useCallback(async () => {
    setTableLoading(true)
    try {
      const result = await api.listLibrariesPaginated({
        page: libPage,
        page_size: libPageSize,
        search: libSearchDebounced || undefined,
        sort: libSort,
        order: libOrder,
      })
      setLibraries(result.items)
      setLibTotal(result.total)
      if (result.total_pages && libPage > result.total_pages) {
        setLibPage(result.total_pages || 1)
      }
      setLoadError(null)
    } catch (err) {
      setLoadError(toAppApiError(err))
    } finally {
      setTableLoading(false)
      setLoading(false)
    }
  }, [libPage, libPageSize, libSearchDebounced, libSort, libOrder])

  const refreshLibraryDetail = useCallback(async () => {
    if (!selectedLibraryId) return
    const { library } = await api.getLibrary(selectedLibraryId)
    setLibraryDetail(library)
  }, [selectedLibraryId])

  const refreshDocuments = useCallback(async () => {
    if (!selectedLibraryId) {
      setDocuments([])
      return
    }
    setTableLoading(true)
    try {
      const result = await api.listLibraryDocumentsPaginated(selectedLibraryId, {
        page: docPage,
        page_size: docPageSize,
        search: docSearchDebounced || undefined,
        status: docStatus,
        sort: docSort,
        order: docOrder,
      })
      setDocuments(result.items)
      setDocTotal(result.total)
      if (result.total_pages && docPage > result.total_pages) {
        setDocPage(result.total_pages || 1)
      }
    } catch (err) {
      setActionError(safeErrorMessage(err, 'Unable to load documents'))
    } finally {
      setTableLoading(false)
    }
  }, [selectedLibraryId, docPage, docPageSize, docSearchDebounced, docStatus, docSort, docOrder])

  useEffect(() => {
    librarySelectionMode.exit()
  }, [libSearchDebounced])

  useEffect(() => {
    documentSelectionMode.exit()
  }, [docSearchDebounced, docStatus])

  useEffect(() => {
    return () => {
      librarySelectionMode.exit()
      documentSelectionMode.exit()
    }
  }, [])

  function openLibraryDetail(lib: LibraryRecord) {
    librarySelectionMode.exit()
    setSelectedLibraryId(lib.id)
    setLibraryDetail(lib)
    setDocPage(1)
    documentSelectionMode.exit()
  }

  useEffect(() => {
    if (inDetail) return
    void refreshLibraries()
  }, [inDetail, refreshLibraries])

  useEffect(() => {
    if (!selectedLibraryId) return
    refreshLibraryDetail().catch(err => setActionError(safeErrorMessage(err, 'Unable to load library')))
    void refreshDocuments()
  }, [selectedLibraryId, refreshDocuments, refreshLibraryDetail])

  function flashSuccess(message: string) {
    setSuccessMessage(message)
    window.setTimeout(() => setSuccessMessage(''), 3500)
  }

  function askThisLibrary(library: LibraryRecord) {
    setPendingChatContext([knowledgeLibraryContext(library)])
    router.push('/')
  }

  async function handleCreateLibrary() {
    const name = newLibraryName.trim()
    if (!name) return
    setActionError('')
    try {
      const { library } = await api.createLibrary({
        name,
        description: newLibraryDescription.trim() || undefined,
      })
      setCreateOpen(false)
      setNewLibraryName('')
      setNewLibraryDescription('')
      flashSuccess('Library created')
      setSelectedLibraryId(library.id)
      setLibraryDetail(library)
    } catch (err) {
      setActionError(safeErrorMessage(err, 'Unable to create library'))
    }
  }

  function openEditLibrary(library: LibraryRecord) {
    setEditLibraryError('')
    setEditLibraryTarget(library)
  }

  async function handleSaveEditLibrary(payload: { name: string; description: string | null }) {
    if (!editLibraryTarget) return
    setEditLibrarySaving(true)
    setEditLibraryError('')
    try {
      const { library } = await api.updateLibrary(editLibraryTarget.id, payload)
      setEditLibraryTarget(null)
      flashSuccess('Library updated')
      if (selectedLibraryId === library.id) {
        setLibraryDetail(library)
        await refreshLibraryDetail()
      }
      await refreshLibraries()
    } catch (err) {
      setEditLibraryError(safeErrorMessage(err, 'Unable to update library'))
    } finally {
      setEditLibrarySaving(false)
    }
  }

  const editLibraryModal = editLibraryTarget ? (
    <EditLibraryModal
      library={editLibraryTarget}
      saving={editLibrarySaving}
      error={editLibraryError}
      returnFocusRef={editLibraryFocusRef}
      onClose={() => {
        setEditLibraryTarget(null)
        setEditLibraryError('')
      }}
      onSave={handleSaveEditLibrary}
    />
  ) : null

  async function handleLibraryBulkDelete() {
    const ids = librarySelection.selectedList
    if (!ids.length) return
    setBulkDeleting(true)
    setActionError('')
    try {
      const result = await api.bulkDeleteLibraries({ ids })
      flashSuccess(bulkDeleteSummary(result, 'library'))
      if (result.failed_count) {
        setActionError(bulkDeleteFailureDetails(result))
        librarySelection.setSelection(result.failed.map(item => item.id))
      } else {
        librarySelection.clear()
        librarySelectionMode.exit()
      }
      if (selectedLibraryId && result.deleted.some(item => item.id === selectedLibraryId)) {
        setSelectedLibraryId('')
        setLibraryDetail(null)
      }
      setLibraryBulkConfirm(false)
      await refreshLibraries()
    } catch (err) {
      setActionError(safeErrorMessage(err, 'Unable to delete libraries'))
    } finally {
      setBulkDeleting(false)
    }
  }

  async function handleDocumentBulkDelete() {
    if (!selectedLibraryId) return
    const ids = documentSelection.selectedList
    if (!ids.length) return
    setBulkDeleting(true)
    setActionError('')
    try {
      const result = await api.bulkDeleteDocuments({ ids, library_id: selectedLibraryId })
      flashSuccess(bulkDeleteSummary(result, 'document'))
      if (result.failed_count) {
        setActionError(bulkDeleteFailureDetails(result))
        documentSelection.setSelection(result.failed.map(item => item.id))
      } else {
        documentSelection.clear()
        documentSelectionMode.exit()
      }
      setDocumentBulkConfirm(false)
      await refreshLibraryDetail()
      await refreshDocuments()
    } catch (err) {
      setActionError(safeErrorMessage(err, 'Unable to delete documents'))
    } finally {
      setBulkDeleting(false)
    }
  }

  async function confirmDeleteLibrary() {
    if (!deleteLibraryTarget) return
    try {
      await api.deleteLibrary(deleteLibraryTarget.id)
      setDeleteLibraryTarget(null)
      flashSuccess('Library deleted')
      if (selectedLibraryId === deleteLibraryTarget.id) {
        setSelectedLibraryId('')
        setLibraryDetail(null)
      }
      await refreshLibraries()
    } catch (err) {
      setActionError(safeErrorMessage(err, 'Unable to delete library'))
    }
  }

  useEffect(() => {
    const pending = uploadQueue.filter(
      item => item.documentId && (item.status === 'PROCESSING' || item.status === 'QUEUED' || item.status === 'UPLOADING'),
    )
    if (!pending.length) return
    let cancelled = false
    const tick = async () => {
      const updates = await Promise.all(
        pending.map(async item => {
          if (!item.documentId) return item
          try {
            const { document } = await api.fetchDocument(item.documentId)
            const st = String(document.status).toUpperCase()
            if (st === 'READY') return { ...item, status: 'READY' as const }
            if (st === 'FAILED') return { ...item, status: 'FAILED' as const, error: document.error_summary ?? 'Failed' }
            return { ...item, status: 'PROCESSING' as const }
          } catch {
            return item
          }
        }),
      )
      if (!cancelled) setUploadQueue(current => current.map(item => updates.find(u => u.id === item.id) ?? item))
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 2500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [uploadQueue])

  async function handleUpload(files: FileList | null) {
    if (!files?.length || !selectedLibraryId || atCapacity) return
    const batch = Array.from(files)
    const queued: UploadQueueItem[] = batch.map(file => ({
      id: `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`,
      name: file.name,
      status: 'QUEUED',
    }))
    setUploadQueue(current => [...queued, ...current])
    setUploading(true)
    setActionError('')
    setUploadQueue(current =>
      current.map(item => (queued.some(q => q.id === item.id) ? { ...item, status: 'UPLOADING' } : item)),
    )
    try {
      const result = await api.batchUploadLibraryDocuments(selectedLibraryId, batch)
      if (result.rejected.length && !result.accepted.length) {
        throw new Error(result.rejected[0]?.message || 'Upload failed')
      }
      setUploadQueue(current =>
        current.map(item => {
          const accepted = result.accepted.find(doc => doc.original_filename === item.name || doc.filename === item.name)
          if (accepted) {
            return { ...item, status: 'PROCESSING', documentId: accepted.id }
          }
          const rejected = result.rejected.find(r => r.filename === item.name)
          if (rejected) return { ...item, status: 'FAILED', error: rejected.message }
          return item
        }),
      )
      if (result.rejected.length) {
        setActionError(`${result.rejected.length} file(s) could not be uploaded. Others were queued.`)
      }
      if (result.accepted.length) {
        flashSuccess(
          result.accepted.length > 1 ? `${result.accepted.length} documents uploaded` : 'Document uploaded',
        )
      }
      await refreshLibraryDetail()
      await refreshDocuments()
    } catch (err) {
      setUploadQueue(current =>
        current.map(item => (queued.some(q => q.id === item.id) ? { ...item, status: 'FAILED', error: 'Upload failed' } : item)),
      )
      setActionError(safeErrorMessage(err, 'Unable to upload document'))
    } finally {
      setUploading(false)
    }
  }

  function applyLibSort(field: string) {
    const next = nextSortState(libSort, libOrder, field)
    setLibSort(next.field as LibrarySortField)
    setLibOrder(next.order)
    setLibPage(1)
  }

  function applyDocSort(field: string) {
    const next = nextSortState(docSort, docOrder, field)
    setDocSort(next.field as DocumentSortField)
    setDocOrder(next.order)
    setDocPage(1)
  }

  const uploadInputId = 'knowledge-upload-input'

  if (loading && !libraries.length && !loadError && !inDetail) {
    return (
      <PageCenter>
        <p className="text-sm text-slate-600">Loading knowledge libraries…</p>
      </PageCenter>
    )
  }

  if (loadError && !libraries.length && !inDetail) {
    return (
      <PageCenter>
        <ServiceErrorState title="Unable to load libraries" message="We couldn't load knowledge libraries." error={loadError} onRetry={() => void refreshLibraries()} />
      </PageCenter>
    )
  }

  if (inDetail && libraryDetail) {
    return (
      <PageCenter className="space-y-5">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-cloudera-navy"
          onClick={() => {
            setSelectedLibraryId('')
            setLibraryDetail(null)
            setDocPage(1)
            documentSelectionMode.exit()
          }}
        >
          <ArrowLeft size={16} aria-hidden />
          Back to All libraries
        </button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="type-app-title text-cloudera-navy">{libraryDetail.name}</h1>
            <p className="mt-1 text-sm text-slate-600">
              {documentCount} / {documentLimit} documents · {libraryStatusLabel(libraryDetail.library_status)} · Updated{' '}
              {formatRelative(libraryDetail.updated_at)}
            </p>
            {capacityWarning && !atCapacity ? (
              <p className="mt-1 text-xs text-amber-800">Approaching document capacity for this library.</p>
            ) : null}
            {atCapacity ? (
              <p className="mt-1 text-xs text-red-700">This library has reached its {documentLimit}-document limit.</p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn-secondary px-3 py-2 text-sm font-semibold" onClick={() => askThisLibrary(libraryDetail)}>
              Ask this library
            </button>
            <label htmlFor={uploadInputId} className={`btn-primary inline-flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${atCapacity ? 'pointer-events-none opacity-50' : ''}`}>
              <Upload size={16} />
              {uploading ? 'Uploading…' : 'Upload documents'}
            </label>
            <input id={uploadInputId} type="file" className="sr-only" multiple disabled={uploading || atCapacity} accept=".pdf,.txt,.md,.docx" onChange={e => void handleUpload(e.target.files)} />
            <RowActionsMenu
              label="Library actions"
              menuButtonRef={editLibraryFocusRef}
              items={[
                { key: 'edit', label: 'Edit library', onClick: () => openEditLibrary(libraryDetail) },
                { key: 'sep', separator: true },
                { key: 'delete', label: 'Delete library', danger: true, onClick: () => setDeleteLibraryTarget(libraryDetail) },
              ]}
            />
          </div>
        </div>

        {successMessage ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">{successMessage}</p> : null}
        {actionError ? <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{actionError}</p> : null}
        <DocumentUploadQueue
          items={uploadQueue}
          onClearCompleted={() => setUploadQueue(current => current.filter(item => item.status !== 'READY'))}
          onRemove={id => setUploadQueue(current => current.filter(item => item.id !== id))}
          onRetry={id => {
            const item = uploadQueue.find(entry => entry.id === id)
            if (item?.documentId) void api.processDocument(item.documentId)
          }}
        />

        {documents.length === 0 && !docSearchDebounced && docStatus === 'all' && !tableLoading ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-6 py-16 text-center">
            <Upload className="h-10 w-10 text-cloudera-orange" strokeWidth={1.25} />
            <h2 className="mt-4 text-lg font-semibold text-cloudera-navy">Add documents to this library</h2>
            <p className="mt-2 max-w-md text-sm text-slate-600">
              Upload PDF, DOCX, TXT and other supported formats. Documents will be indexed automatically.
            </p>
            <label htmlFor={`${uploadInputId}-empty`} className={`btn-primary mt-6 inline-flex cursor-pointer items-center gap-2 px-4 py-2 text-sm ${atCapacity ? 'pointer-events-none opacity-50' : ''}`}>
              Upload documents
            </label>
            <input id={`${uploadInputId}-empty`} type="file" className="sr-only" multiple disabled={atCapacity} onChange={e => void handleUpload(e.target.files)} />
            <p className="mt-3 text-xs text-slate-500">or drag and drop onto this page from your file manager</p>
          </div>
        ) : (
          <section
            data-testid="library-document-table-panel"
            className={`flex ${LIBRARY_DOCUMENT_TABLE_MIN_HEIGHT_CLASS} flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm`}
          >
            <div className="space-y-2 border-b border-slate-100 px-3 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="search"
                  placeholder="Search documents…"
                  value={docSearch}
                  onChange={e => { setDocSearch(e.target.value); setDocPage(1) }}
                  className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <select className="rounded-lg border border-slate-200 px-2 py-2 text-sm" value={docStatus} onChange={e => { setDocStatus(e.target.value); setDocPage(1) }}>
                  <option value="all">All status</option>
                  <option value="READY">Ready</option>
                  <option value="PROCESSING">Processing</option>
                  <option value="QUEUED">Queued</option>
                  <option value="FAILED">Failed</option>
                  <option value="UPLOADED">Uploaded</option>
                </select>
                {documentSelectionMode.active ? (
                  <>
                    <span className="text-sm font-semibold text-cloudera-navy" aria-live="polite">
                      {documentSelection.selectedCount} selected
                    </span>
                    <button
                      type="button"
                      className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                      disabled={documentSelection.selectedCount <= 0}
                      onClick={() => setDocumentBulkConfirm(true)}
                    >
                      Delete selected
                    </button>
                    <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => documentSelectionMode.exit()}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <TableSelectionModeButton
                    entityLabel="documents"
                    active={documentSelectionMode.active}
                    onClick={() => documentSelectionMode.enter()}
                  />
                )}
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-x-auto overflow-y-auto">
              <table className="min-w-full w-full table-fixed text-left text-sm">
                <thead className="app-table-head">
                  <tr>
                    {documentSelectionMode.active ? (
                      <th className="w-11 px-2 py-2">
                        <TableHeaderCheckbox
                          state={documentSelection.pageCheckboxState(documents.map(doc => doc.id))}
                          onToggle={() => documentSelection.togglePage(documents.map(doc => doc.id))}
                        />
                      </th>
                    ) : null}
                    <th className="px-3 py-2">
                      <SortableColumnHeader label="Document" field="original_filename" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="px-3 py-2">
                      <SortableColumnHeader label="Type" field="mime_type" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="w-20 px-3 py-2">
                      <SortableColumnHeader label="Size" field="size_bytes" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="w-20 px-3 py-2">
                      <SortableColumnHeader label="Chunks" field="chunk_count" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="px-3 py-2">
                      <SortableColumnHeader label="Status" field="status" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="px-3 py-2">
                      <SortableColumnHeader label="Created" field="created_at" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="px-3 py-2">
                      <SortableColumnHeader label="Modified" field="updated_at" activeField={docSort} order={docOrder} onSort={applyDocSort} />
                    </th>
                    <th className="w-24 px-3 py-2 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="min-h-[280px]">
                  {tableLoading && !documents.length ? (
                    <tr><td colSpan={documentSelectionMode.active ? 9 : 8} className="px-3 py-8 text-center text-slate-500">Loading documents…</td></tr>
                  ) : documents.length === 0 ? (
                    <tr><td colSpan={documentSelectionMode.active ? 9 : 8} className="px-3 py-8 text-center text-slate-500">No documents match the current filters.</td></tr>
                  ) : (
                    documents.map(doc => (
                      <tr
                        key={doc.id}
                        className={`h-11 border-b border-slate-50 hover:bg-slate-50/60 ${documentSelection.isSelected(doc.id) ? 'bg-cloudera-violet/5' : ''}`}
                      >
                        {documentSelectionMode.active ? (
                          <td className="w-11 px-2 py-2">
                            <TableRowCheckbox
                              checked={documentSelection.isSelected(doc.id)}
                              label={`Select ${doc.original_filename}`}
                              onToggle={() => documentSelection.toggle(doc.id)}
                            />
                          </td>
                        ) : null}
                        <td className="truncate px-3 py-2 font-medium text-cloudera-navy">{doc.original_filename}</td>
                        <td className="truncate px-3 py-2 text-slate-600">{mimeShort(doc.mime_type)}</td>
                        <td className="px-3 py-2 text-slate-600">{formatBytes(doc.size_bytes)}</td>
                        <td className="px-3 py-2 text-slate-600">{doc.chunk_count ?? '—'}</td>
                        <td className="px-3 py-2"><StatusPill status={doc.status} /></td>
                        <td className="px-3 py-2 text-slate-600">{formatShortDate(doc.created_at)}</td>
                        <td className="px-3 py-2 text-slate-600">{formatRelative(doc.updated_at)}</td>
                        <td className="px-3 py-2">
                          <RowActionsMenu
                            label={`Actions for ${doc.original_filename}`}
                            items={[
                              {
                                key: 'rename',
                                label: 'Edit name',
                                onClick: () => {
                                  setRenameDocTarget(doc)
                                  setRenameDocValue(doc.original_filename)
                                },
                              },
                              { key: 'reprocess', label: 'Reprocess', onClick: () => setReprocessTarget(doc) },
                              { key: 'sep', separator: true },
                              { key: 'delete', label: 'Delete', danger: true, onClick: () => setDeleteDocTarget(doc) },
                            ]}
                          />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="mt-auto shrink-0 border-t border-slate-100">
              <TablePagination page={docPage} pageSize={docPageSize} total={docTotal} onPageChange={setDocPage} onPageSizeChange={size => { setDocPageSize(size); setDocPage(1) }} />
            </div>
          </section>
        )}

        {editLibraryModal}

        {documentBulkConfirm ? (
          <BulkDeleteDialog
            count={documentSelection.selectedCount}
            entityLabel="document"
            description="This will permanently remove the selected documents and their indexed chunks."
            loading={bulkDeleting}
            onCancel={() => setDocumentBulkConfirm(false)}
            onConfirm={() => void handleDocumentBulkDelete()}
          />
        ) : null}

        {renameDocTarget ? (
          <SimpleModal title="Rename document" onClose={() => setRenameDocTarget(null)}>
            <label className="block text-sm font-medium text-slate-700">
              Display name
              <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={renameDocValue} onChange={e => setRenameDocValue(e.target.value)} />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => setRenameDocTarget(null)}>Cancel</button>
              <button type="button" className="btn-primary px-3 py-2 text-sm" onClick={() => void (async () => {
                if (!renameDocTarget) return
                await api.renameDocument(renameDocTarget.id, { original_filename: renameDocValue.trim() })
                setRenameDocTarget(null)
                flashSuccess('Document renamed')
                await refreshDocuments()
              })()}>Save</button>
            </div>
          </SimpleModal>
        ) : null}

        {reprocessTarget ? (
          <SimpleModal title="Reprocess document?" onClose={() => setReprocessTarget(null)}>
            <p className="text-sm text-slate-600">Queue {reprocessTarget.original_filename} for ingestion again?</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => setReprocessTarget(null)}>Cancel</button>
              <button type="button" className="btn-primary px-3 py-2 text-sm" onClick={() => void (async () => {
                if (!reprocessTarget) return
                await api.processDocument(reprocessTarget.id)
                setReprocessTarget(null)
                flashSuccess('Document queued for reprocessing')
                await refreshDocuments()
              })()}>Reprocess</button>
            </div>
          </SimpleModal>
        ) : null}

        {deleteDocTarget ? (
          <SimpleModal title={`Delete ${deleteDocTarget.original_filename}?`} onClose={() => setDeleteDocTarget(null)}>
            <p className="text-sm text-slate-600">This removes the document and its indexed chunks from this library.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => setDeleteDocTarget(null)}>Cancel</button>
              <button type="button" className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => void (async () => {
                if (!deleteDocTarget) return
                await api.deleteDocument(deleteDocTarget.id)
                setDeleteDocTarget(null)
                flashSuccess('Document deleted')
                await refreshLibraryDetail()
                await refreshDocuments()
              })()}>Delete</button>
            </div>
          </SimpleModal>
        ) : null}

        {deleteLibraryTarget ? (
          <SimpleModal title={`Delete ${deleteLibraryTarget.name}?`} onClose={() => setDeleteLibraryTarget(null)}>
            <p className="text-sm text-slate-600">This removes the library and its associated indexed document data.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => setDeleteLibraryTarget(null)}>Cancel</button>
              <button type="button" className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => void confirmDeleteLibrary()}>Delete library</button>
            </div>
          </SimpleModal>
        ) : null}
      </PageCenter>
    )
  }

  return (
    <PageCenter className="space-y-5">
      <div>
        <h1 className="type-app-title text-cloudera-navy">Knowledge</h1>
        <p className="mt-1 text-sm text-slate-600">Build grounded AI knowledge from your documents.</p>
      </div>

      {successMessage ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">{successMessage}</p> : null}
      {actionError ? <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{actionError}</p> : null}

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Search libraries…"
          value={libSearch}
          onChange={e => { setLibSearch(e.target.value); setLibPage(1) }}
          className="min-w-[240px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        {librarySelectionMode.active ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-cloudera-navy" aria-live="polite">
              {librarySelection.selectedCount} selected
            </span>
            <button
              type="button"
              className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              disabled={librarySelection.selectedCount <= 0}
              onClick={() => setLibraryBulkConfirm(true)}
            >
              Delete selected
            </button>
            <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => librarySelectionMode.exit()}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <TableSelectionModeButton
              entityLabel="libraries"
              active={librarySelectionMode.active}
              onClick={() => librarySelectionMode.enter()}
            />
            <button type="button" className="btn-primary inline-flex items-center gap-2 text-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={16} aria-hidden />
              Create library
            </button>
          </div>
        )}
      </div>

      {libraries.length === 0 && !tableLoading ? (
        libSearchDebounced ? (
          <p className="text-sm text-slate-600">No libraries match your search.</p>
        ) : (
          <EmptyState
            icon={<BookOpen className="h-10 w-10" strokeWidth={1.25} />}
            title="No knowledge libraries yet."
            description="Create a library and upload documents to ground chat answers on your content."
            action={<button type="button" className="btn-primary text-sm" onClick={() => setCreateOpen(true)}>Create library</button>}
          />
        )
      ) : (
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full w-full table-fixed text-left text-sm">
              <thead className="app-table-head">
                <tr>
                  {librarySelectionMode.active ? (
                    <th className="w-11 px-2 py-2">
                      <TableHeaderCheckbox
                        state={librarySelection.pageCheckboxState(libraries.map(lib => lib.id))}
                        onToggle={() => librarySelection.togglePage(libraries.map(lib => lib.id))}
                      />
                    </th>
                  ) : null}
                  <th className="px-3 py-2">
                    <SortableColumnHeader label="Library name" field="name" activeField={libSort} order={libOrder} onSort={applyLibSort} />
                  </th>
                  <th className="w-24 px-3 py-2">
                    <SortableColumnHeader label="Documents" field="document_count" activeField={libSort} order={libOrder} onSort={applyLibSort} />
                  </th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2">
                    <SortableColumnHeader label="Created" field="created_at" activeField={libSort} order={libOrder} onSort={applyLibSort} />
                  </th>
                  <th className="px-3 py-2">
                    <SortableColumnHeader label="Modified" field="updated_at" activeField={libSort} order={libOrder} onSort={applyLibSort} />
                  </th>
                  <th className="w-24 px-3 py-2 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tableLoading && !libraries.length ? (
                  <tr><td colSpan={librarySelectionMode.active ? 7 : 6} className="px-3 py-8 text-center text-slate-500">Loading libraries…</td></tr>
                ) : (
                  libraries.map(lib => (
                    <tr
                      key={lib.id}
                      className={`h-11 border-b border-slate-50 hover:bg-slate-50/70 ${librarySelection.isSelected(lib.id) ? 'bg-cloudera-violet/5' : ''}`}
                    >
                      {librarySelectionMode.active ? (
                        <td className="w-11 px-2 py-2">
                          <TableRowCheckbox
                            checked={librarySelection.isSelected(lib.id)}
                            label={`Select ${lib.name}`}
                            onToggle={() => librarySelection.toggle(lib.id)}
                          />
                        </td>
                      ) : null}
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          className="truncate font-semibold text-cloudera-navy hover:underline"
                          onClick={() => openLibraryDetail(lib)}
                        >
                          {lib.name}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-slate-600">{lib.document_count ?? 0}</td>
                      <td className="px-3 py-2">
                        <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                          {libraryStatusLabel(lib.library_status)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-slate-600">{formatShortDate(lib.created_at)}</td>
                      <td className="px-3 py-2 text-slate-600">{formatRelative(lib.updated_at)}</td>
                      <td className="px-3 py-2">
                        <RowActionsMenu
                          label={`Actions for ${lib.name}`}
                          menuButtonRef={editLibraryFocusRef}
                          items={[
                            { key: 'edit', label: 'Edit', onClick: () => openEditLibrary(lib) },
                            { key: 'ask', label: 'Ask this library', onClick: () => askThisLibrary(lib) },
                            { key: 'sep', separator: true },
                            { key: 'delete', label: 'Delete', danger: true, onClick: () => setDeleteLibraryTarget(lib) },
                          ]}
                        />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <TablePagination page={libPage} pageSize={libPageSize} total={libTotal} onPageChange={setLibPage} onPageSizeChange={size => { setLibPageSize(size); setLibPage(1) }} />
        </section>
      )}

      {createOpen ? (
        <SimpleModal title="Create knowledge library" onClose={() => setCreateOpen(false)}>
          <label className="block text-sm font-medium text-slate-700">
            Library name
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={newLibraryName} onChange={e => setNewLibraryName(e.target.value)} />
          </label>
          <label className="mt-3 block text-sm font-medium text-slate-700">
            Description <span className="font-normal text-slate-500">(optional)</span>
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={newLibraryDescription} onChange={e => setNewLibraryDescription(e.target.value)} />
          </label>
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button type="button" className="btn-primary px-3 py-2 text-sm" onClick={() => void handleCreateLibrary()}>Create library</button>
          </div>
        </SimpleModal>
      ) : null}

      {editLibraryModal}

      {libraryBulkConfirm ? (
        <BulkDeleteDialog
          count={librarySelection.selectedCount}
          entityLabel="library"
          description="This will permanently remove the selected libraries and their indexed documents."
          loading={bulkDeleting}
          onCancel={() => setLibraryBulkConfirm(false)}
          onConfirm={() => void handleLibraryBulkDelete()}
        />
      ) : null}

      {deleteLibraryTarget ? (
        <SimpleModal title={`Delete ${deleteLibraryTarget.name}?`} onClose={() => setDeleteLibraryTarget(null)}>
          <p className="text-sm text-slate-600">This removes the library and its associated indexed document data.</p>
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => setDeleteLibraryTarget(null)}>Cancel</button>
            <button type="button" className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => void confirmDeleteLibrary()}>Delete library</button>
          </div>
        </SimpleModal>
      ) : null}
    </PageCenter>
  )
}
