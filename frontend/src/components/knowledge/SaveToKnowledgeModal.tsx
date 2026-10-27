'use client'

import { useEffect, useState } from 'react'
import { SimpleModal } from './SimpleModal'
import { api } from '../../lib/api'
import type { LibraryRecord } from '../../types/api'

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

  useEffect(() => {
    if (!open) return
    setError('')
    setNewLibraryName('')
    void api.listLibrariesPaginated({ page: 1, page_size: 100 }).then(res => {
      setLibraries(res.items)
      setLibraryId(res.items[0]?.id ?? '')
    })
  }, [open])

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
            disabled={loading}
            onChange={e => setLibraryId(e.target.value)}
          >
            {libraries.map(lib => (
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
          <input
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            placeholder="Library name"
            value={newLibraryName}
            disabled={loading}
            onChange={e => setNewLibraryName(e.target.value)}
          />
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
