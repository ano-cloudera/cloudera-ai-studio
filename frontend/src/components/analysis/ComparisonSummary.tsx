import { ArrowDown, ArrowUp, Minus } from 'lucide-react'
import type { ChatResponse } from '../../types/api'

export type ComparisonKind = 'periods' | 'benchmark'

const METRIC_COLUMNS = new Set(['metric_value', 'previous_value', 'change', 'change_pct', 'overall_value', 'difference'])

/** The kind of governed comparison a result is, read from its columns; null for an ordinary result. */
export function comparisonKind(columns: string[]): ComparisonKind | null {
  if (columns.includes('previous_value') && columns.includes('change')) return 'periods'
  if (columns.includes('overall_value') && columns.includes('difference')) return 'benchmark'
  return null
}

function number(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value)
  return null
}

function format(value: unknown): string {
  const n = number(value)
  return n === null ? '–' : n.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

function groupLabel(column: string): string {
  return (column.split('_').slice(-2).join(' ') || column).replace(/^\w/, c => c.toUpperCase())
}

function Delta({ value, suffix }: { value: unknown; suffix: string }) {
  const n = number(value)
  if (n === null) return <span className="text-slate-400">–</span>
  const Icon = n > 0 ? ArrowUp : n < 0 ? ArrowDown : Minus
  const tone = n > 0 ? 'text-orange-700' : n < 0 ? 'text-sky-700' : 'text-slate-500'
  return (
    <span className={`inline-flex items-center gap-1 font-semibold ${tone}`}>
      <Icon size={13} aria-hidden />
      {n > 0 ? '+' : ''}
      {format(n)}
      {suffix}
    </span>
  )
}

/** Before and after, or group against the overall value, in the shape the comparison has. */
export function ComparisonSummary({ response }: { response: ChatResponse }) {
  const kind = comparisonKind(response.data.columns)
  if (!kind || !response.data.rows.length) return null
  const groups = response.data.columns.filter(c => !METRIC_COLUMNS.has(c))
  const [earlier, later] = (response.calculation?.period ?? '').split(' vs ')
  const rows = response.data.rows.slice(0, 12)
  const head = 'px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500'
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200/90" data-testid="comparison-summary">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50">
          <tr>
            {groups.map(g => (
              <th key={g} className={head}>
                {groupLabel(g)}
              </th>
            ))}
            {kind === 'periods' ? (
              <>
                <th className={head}>{earlier || 'Earlier'}</th>
                <th className={head}>{later || 'Later'}</th>
                <th className={head}>Change</th>
                <th className={head}>Change %</th>
              </>
            ) : (
              <>
                <th className={head}>Value</th>
                <th className={head}>Overall</th>
                <th className={head}>Difference</th>
              </>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, index) => (
            <tr key={index}>
              {groups.map(g => (
                <td key={g} className="px-3 py-2 font-medium text-cloudera-navy">
                  {String(row[g] ?? '–')}
                </td>
              ))}
              {kind === 'periods' ? (
                <>
                  <td className="px-3 py-2 text-slate-700">{format(row.previous_value)}</td>
                  <td className="px-3 py-2 text-slate-700">{format(row.metric_value)}</td>
                  <td className="px-3 py-2">
                    <Delta value={row.change} suffix="" />
                  </td>
                  <td className="px-3 py-2">
                    <Delta value={row.change_pct} suffix="%" />
                  </td>
                </>
              ) : (
                <>
                  <td className="px-3 py-2 text-slate-700">{format(row.metric_value)}</td>
                  <td className="px-3 py-2 text-slate-700">{format(row.overall_value)}</td>
                  <td className="px-3 py-2">
                    <Delta value={row.difference} suffix="" />
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
