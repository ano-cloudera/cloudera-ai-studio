'use client'

type Props = {
  entityLabel: string
  onClick: () => void
  active?: boolean
}

export function TableSelectionModeButton({ entityLabel, onClick, active = false }: Props) {
  return (
    <button
      type="button"
      className={`btn-secondary px-3 py-2 text-sm font-semibold ${active ? 'ring-1 ring-cloudera-violet/40' : ''}`}
      aria-label={`Select ${entityLabel}`}
      aria-pressed={active}
      onClick={onClick}
    >
      Select
    </button>
  )
}
