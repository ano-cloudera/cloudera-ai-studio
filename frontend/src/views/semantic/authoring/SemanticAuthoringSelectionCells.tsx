'use client'

import { TableHeaderCheckbox, TableRowCheckbox } from '../../../components/table/TableSelectionCheckbox'
import type { useTableSelection } from '../../../lib/useTableSelection'

type Selection = ReturnType<typeof useTableSelection>

export function SemanticAuthoringSelectHeader({
  active,
  pageIds,
  selection,
}: {
  active: boolean
  pageIds: string[]
  selection: Selection
}) {
  if (!active) return null
  return (
    <th className="w-11 px-2 py-2">
      <TableHeaderCheckbox
        state={selection.pageCheckboxState(pageIds)}
        onToggle={() => selection.togglePage(pageIds)}
      />
    </th>
  )
}

export function SemanticAuthoringSelectCell({
  active,
  id,
  label,
  selection,
}: {
  active: boolean
  id: string
  label: string
  selection: Selection
}) {
  if (!active) return null
  return (
    <td className="w-11 px-2 py-2">
      <TableRowCheckbox
        checked={selection.isSelected(id)}
        label={`Select ${label}`}
        onToggle={() => selection.toggle(id)}
      />
    </td>
  )
}
