'use client'

import type { ActionRecommendation } from '../../types/api'

const PRIORITY_TONE: Record<string, string> = {
  tinggi: 'bg-rose-50 text-rose-800',
  high: 'bg-rose-50 text-rose-800',
  sedang: 'bg-amber-50 text-amber-800',
  medium: 'bg-amber-50 text-amber-800',
  rendah: 'bg-slate-100 text-slate-700',
  low: 'bg-slate-100 text-slate-700',
}

/**
 * The agent's recommended actions as a table to act from: what, why, who, by when, and the document it comes from. A column the
 * agent left empty for every row (no document gave an owner) is not shown, so the table never has a column of dashes.
 */
export function RecommendationsTable({ rows }: { rows: ActionRecommendation[] }) {
  if (!rows.length) return null
  const has = (pick: (row: ActionRecommendation) => string) => rows.some(row => pick(row).trim())
  const showWho = has(row => row.owner) || has(row => row.timeframe)
  const showSource = has(row => row.source)
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200" data-testid="recommendations-table">
      <table className="min-w-full text-left text-sm">
        <caption className="sr-only">Recommended actions</caption>
        <thead className="bg-slate-50 text-xs font-semibold text-slate-700">
          <tr>
            <th scope="col" className="w-10 px-3 py-2">#</th>
            <th scope="col" className="px-3 py-2">Action</th>
            <th scope="col" className="px-3 py-2">Basis</th>
            {showWho ? <th scope="col" className="px-3 py-2">Owner and timeframe</th> : null}
            {showSource ? <th scope="col" className="px-3 py-2">Source</th> : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 align-top text-slate-800">
          {rows.map((row, index) => (
            <tr key={`${index}-${row.action}`}>
              <td className="px-3 py-2 tabular-nums text-slate-600">{index + 1}</td>
              <td className="px-3 py-2">
                <div className="font-medium text-cloudera-navy">{row.action}</div>
                {row.priority ? (
                  <span className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold ${PRIORITY_TONE[row.priority.trim().toLowerCase()] ?? 'bg-slate-100 text-slate-700'}`}>{row.priority}</span>
                ) : null}
              </td>
              <td className="px-3 py-2 text-slate-700">{row.basis}</td>
              {showWho ? (
                <td className="px-3 py-2 text-slate-700">{[row.owner, row.timeframe].filter(item => item.trim()).join(' → ') || '–'}</td>
              ) : null}
              {showSource ? <td className="px-3 py-2 text-slate-600">{row.source || '–'}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
