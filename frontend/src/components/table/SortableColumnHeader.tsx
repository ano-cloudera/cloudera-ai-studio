'use client'

import { ChevronDown, ChevronUp } from 'lucide-react'

type Props = {
  label: string
  field: string
  activeField: string
  order: 'asc' | 'desc'
  onSort: (field: string) => void
  className?: string
}

export function SortableColumnHeader({ label, field, activeField, order, onSort, className = '' }: Props) {
  const active = activeField === field
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-0.5 text-xs font-semibold uppercase tracking-wide text-cloudera-violet hover:text-cloudera-navy ${className}`}
      onClick={() => onSort(field)}
      aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      {label}
      {active ? (
        order === 'asc' ? (
          <ChevronUp size={14} aria-hidden className="text-cloudera-violet" />
        ) : (
          <ChevronDown size={14} aria-hidden className="text-cloudera-violet" />
        )
      ) : (
        <span className="inline-block w-[14px]" aria-hidden />
      )}
    </button>
  )
}
