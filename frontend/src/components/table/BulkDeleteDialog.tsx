'use client'

import { SimpleModal } from '../knowledge/SimpleModal'

type Props = {
  count: number
  entityLabel: string
  description: string
  loading?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function BulkDeleteDialog({
  count,
  entityLabel,
  description,
  loading,
  onCancel,
  onConfirm,
}: Props) {
  const label = count === 1 ? entityLabel : `${entityLabel}s`
  return (
    <SimpleModal title={`Delete ${count} ${label}?`} onClose={onCancel}>
      <p className="text-sm text-slate-600">{description}</p>
      <p className="mt-2 text-sm text-slate-600">This action cannot be undone.</p>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={onCancel} disabled={loading}>
          Cancel
        </button>
        <button
          type="button"
          className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          onClick={onConfirm}
          disabled={loading}
        >
          Delete {count} {label}
        </button>
      </div>
    </SimpleModal>
  )
}
