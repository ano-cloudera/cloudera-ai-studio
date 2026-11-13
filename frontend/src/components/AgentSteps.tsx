'use client'

import { useState } from 'react'
import { formatBusinessValue } from '../lib/businessPresentation'
import type { AgentStepCard } from '../types/api'

const TEXT = { checks: (n: number) => `${n} checks`, rows: (n: number) => `${n} rows`, sources: (n: number) => `${n} sources`, noData: 'no data', failed: 'failed', query: 'View query', overall: 'Overall', more: (n: number) => `+${n} more rows` }

function cell(column: string, value: unknown, unitFormat?: string | null): string {
  if (typeof value === 'number') return formatBusinessValue(column, value, undefined, column === 'metric_value' ? unitFormat ?? undefined : undefined)
  return String(value ?? '')
}

function StepCard({ step, index, words }: { step: AgentStepCard; index: number; words: typeof TEXT }) {
  const [open, setOpen] = useState(false)
  const columns = step.columns ?? []
  const rows = step.rows ?? []
  const status =
    step.status === 'ok'
      ? step.tool === 'search_documents'
        ? words.sources(step.row_count)
        : words.rows(step.row_count)
      : step.status === 'no_data'
        ? words.noData
        : words.failed
  return (
    <li className="rounded-xl border border-cloudera-border bg-white">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange"
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-cloudera-indigo/10 text-xs font-semibold text-cloudera-indigo">{index + 1}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-cloudera-ink">{step.title}</span>
        <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold ${step.status === 'ok' ? 'bg-slate-100 text-slate-700' : 'bg-amber-50 text-amber-900'}`}>{status}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-3 py-3">
          {columns.length > 0 && rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="text-slate-600">
                  <tr>
                    {columns.map(column => (
                      <th key={column} scope="col" className="px-2 py-1 font-semibold">
                        {step.column_labels?.[column] ?? column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-800">
                  {rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {columns.map(column => (
                        <td key={column} className="whitespace-nowrap px-2 py-1 tabular-nums">
                          {cell(column, row[column], step.unit_format)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {step.row_count > rows.length && <p className="mt-1 text-xs text-slate-600">{words.more(step.row_count - rows.length)}</p>}
            </div>
          )}
          {typeof step.overall_value === 'number' && (
            <p className="text-xs text-slate-600">
              {words.overall}: {cell('metric_value', step.overall_value, step.unit_format)}
            </p>
          )}
          {(step.sources ?? []).length > 0 && (
            <ul className="text-xs text-slate-700">
              {(step.sources ?? []).map((source, sourceIndex) => (
                <li key={sourceIndex}>
                  {source.file}
                  {source.page ? `, p. ${source.page}` : ''}
                </li>
              ))}
            </ul>
          )}
          {step.sql && (
            <details>
              <summary className="text-xs font-semibold text-cloudera-indigo">{words.query}</summary>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-2 text-[11px] text-slate-700">{step.sql}</pre>
            </details>
          )}
        </div>
      )}
    </li>
  )
}

/** The checks behind an agent's answer, each opening to its rows and governed query, the way an analyst shows their work. */
export function AgentSteps({ steps }: { steps: AgentStepCard[] }) {
  if (!steps.length) return null
  return (
    <div data-testid="agent-steps">
      <p className="mb-3 text-sm text-slate-600">{TEXT.checks(steps.length)} the agent ran to reach this answer. Open one to see its rows and the governed query.</p>
      <ol className="space-y-2">
        {steps.map((step, index) => (
          <StepCard key={`${index}-${step.title}`} step={step} index={index} words={TEXT} />
        ))}
      </ol>
    </div>
  )
}
