'use client'

import { formatBusinessValue } from '../lib/businessPresentation'
import type { ChatResponse } from '../types/api'

/** The one figure of a single-value answer, when the result is one number: shown large, with its target when one is declared. */
export function singleFigure(response: ChatResponse): number | null {
  if (response.status !== 'SUCCESS' || response.strategy === 'agent' || response.data.rows.length !== 1) return null
  const row = response.data.rows[0]
  const numeric = response.data.columns.filter(column => typeof row[column] === 'number')
  if (numeric.length !== 1 || response.data.columns.length > 2) return null
  const value = row[numeric[0]] as number
  return Number.isFinite(value) ? value : null
}

/**
 * Large number, the metric's name, and how it stands against the declared target. Whether that is good or bad is said only
 * when the semantic model declares which way is better; otherwise the gap is stated without judging it.
 */
export function FigureCallout({ response, value }: { response: ChatResponse; value: number }) {
  const data = response.data
  const unit = data.unit_format ?? undefined
  const show = (n: number) => formatBusinessValue('metric_value', n, data.governed_metric ?? undefined, unit)
  const label = data.governed_metric_display_name || data.governed_metric || ''
  const target = typeof data.metric_target === 'number' ? data.metric_target : null
  let standing: { text: string; tone: 'good' | 'bad' | 'plain' } | null = null
  if (target !== null && value !== target) {
    const above = value > target
    const gap = Math.abs(value - target)
    const gapText = unit === 'percent' ? `${Number(gap.toFixed(2))} pts` : show(gap)
    const good = data.metric_better ? (data.metric_better === 'up') === above : null
    standing = { text: `${gapText} ${above ? 'above' : 'below'} target`, tone: good === null ? 'plain' : good ? 'good' : 'bad' }
  }
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-2 rounded-lg bg-cloudera-mist px-4 py-3" data-testid="figure-callout">
      <div className="min-w-0">
        {label && <div className="text-xs font-medium text-slate-600">{label}</div>}
        <div className="text-3xl font-semibold tabular-nums tracking-tight text-cloudera-navy">{show(value)}</div>
      </div>
      {target !== null && (
        <div className="pb-1 text-sm text-slate-600">
          Target {show(target)}
          {standing && (
            <>
              {' · '}
              <span className={standing.tone === 'bad' ? 'font-semibold text-rose-700' : standing.tone === 'good' ? 'font-semibold text-emerald-700' : 'font-semibold text-slate-800'}>
                {standing.text}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  )
}
