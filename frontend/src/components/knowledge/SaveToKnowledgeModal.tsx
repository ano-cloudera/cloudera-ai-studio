'use client'

import { useEffect, useMemo, useState } from 'react'
import { SimpleModal } from './SimpleModal'
import { api } from '../../lib/api'
import type { LibraryRecord } from '../../types/api'

const SYSTEM_LIBRARY_NAMES = new Set(['__cai_chat_attachments__'])

function suggestedLibraryName(attachmentName: string): string {
  const base = attachmentName.replace(/\.[^.]+$/, '').trim()
  if (!base) return 'Uploaded documents'
  return base.length > 80 ? `${base.slice(0, 77)}…` : base
}

type Props = {
  open: boolean
  attachmentId: string
  attachmentName: string
  onClose: () => void
  onSaved: (message: string) => void
}

export function SaveToKnowledgeModal({ open, attachmentId, attachmentName, onClose, onSaved }: Props) {
  const [libraries, setLibraries] = useState<LibraryRecord[]>([])
  const [libraryId, setLibraryId] = useState('')
  const [newLibraryName, setNewLibraryName] = useState('')
  const [mode, setMode] = useState<'existing' | 'new'>('existing')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const visibleLibraries = useMemo(
    () => libraries.filter(lib => !SYSTEM_LIBRARY_NAMES.has(lib.name)),
    [libraries],
  )

  useEffect(() => {
    if (!open) return
    setError('')
    setNewLibraryName(suggestedLibraryName(attachmentName))
    void api.listLibrariesPaginated({ page: 1, page_size: 100 }).then(res => {
      const items = res.items.filter(lib => !SYSTEM_LIBRARY_NAMES.has(lib.name))
      setLibraries(res.items)
      setLibraryId(items[0]?.id ?? '')
      setMode(items.length > 0 ? 'existing' : 'new')
    })
  }, [open, attachmentName])

  async function handleSave() {
    setLoading(true)
    setError('')
    try {
      const body =
        mode === 'new'
          ? { new_library_name: newLibraryName.trim() }
          : { library_id: libraryId }
      const result = await api.saveChatAttachmentToKnowledge(attachmentId, body)
      const libId = result.saved.library_id
      const libName =
        libraries.find(l => l.id === libId)?.name ?? (newLibraryName.trim() || 'Knowledge library')
      onSaved(`Saved to ${libName}`)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save to Knowledge')
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <SimpleModal title="Save to Knowledge" onClose={onClose}>
      <p className="mb-3 text-sm text-slate-600">
        Save <span className="font-semibold text-cloudera-navy">{attachmentName}</span> to a persistent library.
      </p>
      <div className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" checked={mode === 'existing'} onChange={() => setMode('existing')} />
          Choose library
        </label>
        {mode === 'existing' && (
          <select
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={libraryId}
            disabled={loading || visibleLibraries.length === 0}
            onChange={e => setLibraryId(e.target.value)}
          >
            {visibleLibraries.length === 0 ? (
              <option value="">No libraries yet — create one below</option>
            ) : null}
            {visibleLibraries.map(lib => (
              <option key={lib.id} value={lib.id}>
                {lib.name}
              </option>
            ))}
          </select>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" checked={mode === 'new'} onChange={() => setMode('new')} />
          Create new library
        </label>
        {mode === 'new' && (
          <label className="block text-sm font-medium text-slate-700">
            Library name
            <input
              type="text"
              autoFocus
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-cloudera-navy"
              placeholder="e.g. Cloudera AI Infrastructure"
              value={newLibraryName}
              disabled={loading}
              onChange={e => setNewLibraryName(e.target.value)}
            />
          </label>
        )}
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary px-3 py-2 text-sm" disabled={loading} onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary px-3 py-2 text-sm disabled:opacity-50"
            disabled={loading || (mode === 'existing' && !libraryId) || (mode === 'new' && !newLibraryName.trim())}
            onClick={() => void handleSave()}
          >
            {loading ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </SimpleModal>
  )
}
