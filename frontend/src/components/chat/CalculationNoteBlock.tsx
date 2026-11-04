'use client'

import { Calculator, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import type { CalculationNote } from '../../types/api'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-2 py-1">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="min-w-0 text-sm text-slate-700">{children}</dd>
    </div>
  )
}

/** "How this was calculated": the one-line summary is always visible, the details open on click. */
export function CalculationNoteBlock({ note, embedded = false }: { note: CalculationNote; embedded?: boolean }) {
  const [open, setOpen] = useState(false)
  const warnings = note.checks.filter(check => check.status === 'warning')
  return (
    <div className={embedded ? 'bg-white' : 'rounded-xl border border-slate-200 bg-white'} data-testid="calculation-note">
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        className={`flex w-full items-start gap-2 py-2.5 text-left transition-colors hover:bg-slate-50 ${embedded ? 'px-4 sm:px-5' : 'px-3'}`}
        aria-expanded={open}
      >
        <Calculator size={14} className="mt-0.5 shrink-0 text-cloudera-orange" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-semibold text-cloudera-navy">How this was calculated</span>
          <span className="block truncate text-xs text-slate-600">{note.summary}</span>
        </span>
        {warnings.length ? (
          <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
            {warnings.length} to check
          </span>
        ) : null}
        <ChevronDown size={14} className={`mt-0.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      {open ? (
        <dl className={`divide-y divide-slate-100 border-t border-slate-200/80 py-2 ${embedded ? 'px-4 sm:px-5' : 'px-3'}`}>
          {note.metric ? <Row label="Metric">{note.metric}</Row> : null}
          {note.formula ? <Row label="Formula"><code className="break-words font-mono text-xs">{note.formula}</code></Row> : null}
          {note.breakdown.length ? <Row label="Broken down by">{note.breakdown.join(', ')}</Row> : null}
          {note.period ? <Row label="Period">{note.period}</Row> : null}
          {note.filters.length ? <Row label="Filters">{note.filters.join('; ')}</Row> : null}
          {note.source.length ? <Row label="Source">{note.source.join(', ')}</Row> : null}
          {note.comparison ? <Row label="Comparison">{note.comparison}</Row> : null}
          {note.steps.length ? (
            <Row label="Steps">
              <ol className="list-decimal space-y-0.5 pl-4">
                {note.steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </Row>
          ) : null}
          {note.checks.length ? (
            <Row label="Checks">
              <ul className="space-y-0.5">
                {note.checks.map((check, index) => (
                  <li key={index} className={check.status === 'warning' ? 'text-amber-800' : 'text-emerald-800'}>
                    {check.status === 'warning' ? '⚠ ' : '✓ '}
                    {check.message}
                  </li>
                ))}
              </ul>
            </Row>
          ) : null}
        </dl>
      ) : null}
    </div>
  )
}
