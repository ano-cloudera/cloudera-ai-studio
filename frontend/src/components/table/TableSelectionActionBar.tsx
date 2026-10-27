'use client'

import { TableSelectionModeButton } from './TableSelectionModeButton'

type SelectionMode = {
  active: boolean
  enter: () => void
  exit: () => void
}

type Props = {
  entityLabel: string
  mode: SelectionMode
  selectedCount: number
  showDelete?: boolean
  deleteLabel?: string
  deleting?: boolean
  deleteDisabled?: boolean
  onDelete?: () => void
}

export function TableSelectionActionBar({
  entityLabel,
  mode,
  selectedCount,
  showDelete = false,
  deleteLabel = 'Delete selected',
  deleting = false,
  deleteDisabled = false,
  onDelete,
}: Props) {
  if (!mode.active) {
    return (
      <TableSelectionModeButton entityLabel={entityLabel} active={false} onClick={() => mode.enter()} />
    )
  }
  return (
    <>
      <span className="text-sm font-semibold text-cloudera-navy" aria-live="polite">
        {selectedCount} selected
      </span>
      {showDelete && onDelete ? (
        <button
          type="button"
          className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          disabled={selectedCount <= 0 || deleteDisabled || deleting}
          onClick={onDelete}
        >
          {deleting ? 'Deleting…' : deleteLabel}
        </button>
      ) : null}
      <button type="button" className="btn-secondary px-3 py-2 text-sm" onClick={() => mode.exit()}>
        Cancel
      </button>
    </>
  )
}
