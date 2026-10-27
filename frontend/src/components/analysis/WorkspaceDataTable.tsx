'use client'

import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Download } from 'lucide-react'
import { formatBusinessValue, inferColumnUnitFormat } from '../../lib/businessPresentation'
import { downloadCsv } from '../../lib/exportTableCsv'
import { isMaterialColumn, isRankSortableColumn, workspaceColumnLabel } from '../../lib/workspaceTableLabels'

const RANK_KEY = '__rank__'

type SortDir = 'asc' | 'desc'
type SortState = { column: string; dir: SortDir } | null

type Props = {
  title: string
  columns: string[]
  rows: Record<string, unknown>[]
  metric?: string
  unitFormat?: string | null
  rowCount?: number
}

function compareValues(a: unknown, b: unknown, column: string, metric?: string): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  const na = Number(a)
  const nb = Number(b)
  if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb
  return String(a ?? '').localeCompare(String(b ?? ''), undefined, { numeric: true })
}

function isNumericColumn(column: string, metric?: string): boolean {
  const key = column.toLowerCase()
  if (key === RANK_KEY) return true
  if (key === 'metric_value' || key.includes('pct') || key.endsWith('_val')) return true
  return inferColumnUnitFormat(column, metric) !== null
}

function RankCell({ rank }: { rank: number }) {
  const top = rank <= 3
  return (
    <span
      className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold tabular-nums ${
        top ? 'bg-emerald-100/90 text-emerald-800' : 'text-slate-600'
      }`}
    >
      {rank}
    </span>
  )
}

export function WorkspaceDataTable({ title, columns, rows, metric, unitFormat, rowCount }: Props) {
  const [sort, setSort] = useState<SortState>(null)

  const displayColumns = useMemo(() => [RANK_KEY, ...columns], [columns])

  const sortedRows = useMemo(() => {
    const indexed = rows.map((row, index) => ({ row, rank: index + 1 }))
    if (!sort) return indexed
    const { column, dir } = sort
    const sign = dir === 'asc' ? 1 : -1
    return [...indexed].sort((a, b) => {
      if (column === RANK_KEY) return sign * (a.rank - b.rank)
      return sign * compareValues(a.row[column], b.row[column], column, metric)
    })
  }, [rows, sort, metric])

  const totalRows = rowCount ?? rows.length
  const shown = sortedRows.length

  function toggleSort(column: string) {
    if (!isRankSortableColumn(column)) return
    setSort(current => {
      if (current?.column !== column) return { column, dir: 'desc' }
      if (current.dir === 'desc') return { column, dir: 'asc' }
      return null
    })
  }

  function sortIcon(column: string) {
    if (!isRankSortableColumn(column)) return null
    if (sort?.column !== column) return <ArrowUpDown size={12} className="text-slate-400" aria-hidden />
    return sort.dir === 'asc' ? (
      <ArrowUp size={12} className="text-cloudera-orange" aria-hidden />
    ) : (
      <ArrowDown size={12} className="text-cloudera-orange" aria-hidden />
    )
  }

  function downloadTableCsv() {
    const headers = displayColumns.map(col => (col === RANK_KEY ? 'Rank' : workspaceColumnLabel(col)))
    const csvRows = sortedRows.map(({ row, rank }) =>
      displayColumns.map(col => {
        if (col === RANK_KEY) return String(rank)
        return formatBusinessValue(col, row[col], metric, col === 'metric_value' ? unitFormat : undefined)
      }),
    )
    const safeTitle = title.replace(/[^\w\-]+/g, '_').slice(0, 48) || 'analysis_table'
    downloadCsv(`${safeTitle}.csv`, headers, csvRows)
  }

  if (!columns.length || !rows.length) {
    return <p className="text-sm text-slate-500">No tabular result for this analysis.</p>
  }

  return (
    <div className="space-y-3">
      <h4 className="text-base font-semibold leading-snug text-cloudera-navy">{title}</h4>
      <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-sm">
        <div className="scrollbar-pane max-h-[min(520px,60vh)] overflow-auto">
          <table className="app-data-table min-w-full">
            <thead className="app-table-head sticky top-0 z-[1] backdrop-blur-sm">
              <tr>
                {displayColumns.map(column => {
                  const numeric = isNumericColumn(column, metric)
                  const label = column === RANK_KEY ? 'Rank' : workspaceColumnLabel(column)
                  const sortable = isRankSortableColumn(column)
                  return (
                    <th
                      key={column}
                      className={`px-3 py-2.5 text-[13px] font-semibold text-slate-600 ${
                        numeric ? 'text-right' : 'text-left'
                      } ${column === RANK_KEY ? 'text-center' : ''}`}
                    >
                      {sortable ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column)}
                          className={`inline-flex w-full items-center gap-1 hover:text-cloudera-navy ${
                            numeric ? 'justify-end' : column === RANK_KEY ? 'justify-center' : 'justify-start'
                          }`}
                        >
                          {label}
                          {sortIcon(column)}
                        </button>
                      ) : (
                        label
                      )}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map(({ row, rank }) => {
                const topThree = rank <= 3
                return (
                  <tr
                    key={`${rank}-${JSON.stringify(row).slice(0, 40)}`}
                    className={`border-t border-slate-100 transition-colors hover:bg-slate-50/80 ${
                      topThree ? 'bg-emerald-50/25' : 'bg-white'
                    }`}
                  >
                    {displayColumns.map(column => {
                      if (column === RANK_KEY) {
                        return (
                          <td key={column} className="px-3 py-2 text-center">
                            <RankCell rank={rank} />
                          </td>
                        )
                      }
                      const numeric = isNumericColumn(column, metric)
                      const material = isMaterialColumn(column)
                      return (
                        <td
                          key={column}
                          className={`px-3 py-2 text-[14px] text-slate-700 ${
                            numeric ? 'text-right font-medium tabular-nums' : material ? 'text-left font-medium' : 'text-left'
                          }`}
                        >
                          {formatBusinessValue(
                            column,
                            row[column],
                            metric,
                            column === 'metric_value' ? unitFormat : undefined,
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/50 px-3 py-2.5">
          <p className="text-xs text-slate-500">
            Showing {shown} of {totalRows} row{totalRows === 1 ? '' : 's'}
          </p>
          <button
            type="button"
            onClick={downloadTableCsv}
            className="btn-secondary !px-2.5 !py-1.5 !text-xs"
          >
            <Download size={14} aria-hidden />
            Download CSV
          </button>
        </div>
      </div>
    </div>
  )
}
