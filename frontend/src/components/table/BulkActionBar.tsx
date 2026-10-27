'use client'

type Props = {
  selectedCount: number
  entityLabel: string
  onClear: () => void
  onDelete: () => void
}

export function BulkActionBar({ selectedCount, entityLabel, onClear, onDelete }: Props) {
  if (selectedCount <= 0) return null
  const plural =
    selectedCount === 1
      ? entityLabel
      : entityLabel === 'library'
        ? 'libraries'
        : entityLabel === 'document'
          ? 'documents'
          : `${entityLabel}s`
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-cloudera-violet/20 bg-cloudera-violet/5 px-3 py-2 text-sm">
      <span className="font-semibold text-cloudera-navy">
        {selectedCount} {plural} selected
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary px-3 py-1.5 text-xs" onClick={onClear}>
          Clear selection
        </button>
        <button
          type="button"
          className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
          onClick={onDelete}
        >
          Delete selected
        </button>
      </div>
    </div>
  )
}
