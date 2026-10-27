'use client'

import { useCallback } from 'react'
import type { BulkDeleteResponse } from '../../../types/api'
import { useTableSelection } from '../../../lib/useTableSelection'
import { useTableSelectionMode } from '../../../lib/useTableSelectionMode'

export function useSemanticAuthoringSelection() {
  const selection = useTableSelection()
  const mode = useTableSelectionMode(selection.clear)
  return { selection, mode }
}

export function useSemanticBulkDeleteAction(
  versionId: string | null,
  bulkFn: (versionId: string, ids: string[]) => Promise<BulkDeleteResponse>,
  onComplete: () => Promise<void> | void,
  selection: ReturnType<typeof useTableSelection>,
  mode: ReturnType<typeof useTableSelectionMode>,
) {
  return useCallback(async () => {
    if (!versionId || selection.selectedCount <= 0) return
    const ids = [...selection.selectedIds]
    await bulkFn(versionId, ids)
    selection.clear()
    mode.exit()
    await onComplete()
  }, [versionId, bulkFn, onComplete, selection, mode])
}

type SelectionBarProps = {
  entityLabel: string
  selectedCount: number
  onCancel: () => void
  onDelete?: () => void
  deleteDisabled?: boolean
}

export function SemanticSelectionBar({ entityLabel, selectedCount, onDelete, onCancel, deleteDisabled }: SelectionBarProps) {
  return (
    <>
      <span className="text-sm font-semibold text-cloudera-navy" aria-live="polite">
        {selectedCount} {entityLabel} selected
      </span>
      {onDelete ? (
        <button
          type="button"
          className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          disabled={deleteDisabled ?? selectedCount <= 0}
          onClick={onDelete}
        >
          Delete selected
        </button>
      ) : null}
      <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={onCancel}>
        Cancel
      </button>
    </>
  )
}
