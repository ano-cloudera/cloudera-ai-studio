import { BarChart3 } from 'lucide-react'

import { formatBusinessLabel, formatBusinessValue } from '../lib/businessPresentation'
import type { CompactSingleRow } from '../lib/singleRowPresentation'
import { KpiCard } from './KpiCard'

export function SingleRowEvidence({
  compact,
  metric,
  unitFormat,
  title,
}: {
  compact: CompactSingleRow
  metric?: string
  unitFormat?: string | null
  title?: string
}) {
  const metricLabel = formatBusinessLabel(compact.metricColumn)
  const formatted = formatBusinessValue(
    compact.metricColumn,
    compact.metricValue,
    metric,
    compact.metricColumn === 'metric_value' ? unitFormat : undefined,
  )
  const context = compact.dimensions
    .map(d => `${formatBusinessLabel(d.column)}: ${formatBusinessValue(d.column, d.value, metric)}`)
    .join(' · ')

  if (compact.dimensions.length === 0) {
    return (
      <div className="max-w-md">
        <KpiCard label={title || metricLabel} value={compact.metricValue as number | string} format={unitFormat || ''} icon={BarChart3} />
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-slate-200/90 bg-gradient-to-br from-white to-slate-50/80 p-4">
      {compact.dimensions.length > 0 && (
        <dl className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
          {compact.dimensions.map(d => (
            <div key={d.column} className="flex flex-wrap gap-1">
              <dt className="font-semibold text-slate-500">{formatBusinessLabel(d.column)}</dt>
              <dd className="font-medium text-cloudera-navy">{formatBusinessValue(d.column, d.value, metric)}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="border-t border-slate-200/80 pt-3">
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">{title || metricLabel}</div>
        <div className="mt-1 text-2xl font-black tracking-tight text-cloudera-navy">{formatted}</div>
      </div>
    </div>
  )
}
