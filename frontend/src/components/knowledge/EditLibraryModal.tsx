'use client'

import { useState } from 'react'
import type { LibraryRecord } from '../../types/api'
import { SimpleModal } from './SimpleModal'

type Props = {
  library: LibraryRecord
  saving?: boolean
  error?: string
  returnFocusRef?: React.RefObject<HTMLElement | null>
  onClose: () => void
  onSave: (payload: { name: string; description: string | null }) => void | Promise<void>
}

export function EditLibraryModal({ library, saving, error, returnFocusRef, onClose, onSave }: Props) {
  const [name, setName] = useState(library.name)
  const [description, setDescription] = useState(library.description ?? '')

  return (
    <SimpleModal title="Edit library" onClose={onClose} returnFocusRef={returnFocusRef}>
      <form
        onSubmit={event => {
          event.preventDefault()
          const trimmed = name.trim()
          if (!trimmed || saving) return
          void onSave({
            name: trimmed,
            description: description.trim() ? description.trim() : null,
          })
        }}
      >
        <label className="block text-sm font-medium text-slate-700">
          Library name
          <input
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={name}
            onChange={event => setName(event.target.value)}
            required
          />
        </label>
        <label className="mt-3 block text-sm font-medium text-slate-700">
          Description
          <textarea
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            rows={3}
            value={description}
            onChange={event => setDescription(event.target.value)}
          />
        </label>
        {error ? (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="btn-primary px-3 py-2 text-sm" disabled={saving || !name.trim()}>
            Save changes
          </button>
        </div>
      </form>
    </SimpleModal>
  )
}
