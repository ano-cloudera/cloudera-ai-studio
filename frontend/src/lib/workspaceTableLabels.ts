import { formatBusinessLabel } from './businessPresentation'

const WORKSPACE_COLUMN_LABELS: Record<string, string> = {
  metric_value: 'Sales Value',
  contribution_pct: 'Contribution',
  cumulative_pct: 'Cumulative Contribution',
}

export function workspaceColumnLabel(column: string): string {
  const key = column.trim().toLowerCase()
  return WORKSPACE_COLUMN_LABELS[key] ?? formatBusinessLabel(column)
}

export function isMaterialColumn(column: string): boolean {
  return /material|matnr|product|sku|item_code|material_code/i.test(column.trim())
}

export function isRankSortableColumn(column: string): boolean {
  const key = column.trim().toLowerCase()
  if (key === '__rank__') return false
  return true
}
