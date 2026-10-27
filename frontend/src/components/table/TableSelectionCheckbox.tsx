'use client'

import type { PageCheckboxState } from '../../lib/useTableSelection'

type RowProps = {
  checked: boolean
  label: string
  onToggle: () => void
}

export function TableRowCheckbox({ checked, label, onToggle }: RowProps) {
  return (
    <input
      type="checkbox"
      className="h-4 w-4 rounded border-slate-300 text-cloudera-violet focus:ring-cloudera-violet"
      checked={checked}
      aria-label={label}
      onClick={event => event.stopPropagation()}
      onChange={event => {
        event.stopPropagation()
        onToggle()
      }}
    />
  )
}

type HeaderProps = {
  state: PageCheckboxState
  onToggle: () => void
}

export function TableHeaderCheckbox({ state, onToggle }: HeaderProps) {
  return (
    <input
      type="checkbox"
      className="h-4 w-4 rounded border-slate-300 text-cloudera-violet focus:ring-cloudera-violet"
      checked={state === 'checked'}
      ref={input => {
        if (input) input.indeterminate = state === 'indeterminate'
      }}
      aria-label="Select all rows"
      title="Select all rows"
      onClick={event => event.stopPropagation()}
      onChange={event => {
        event.stopPropagation()
        onToggle()
      }}
    />
  )
}
