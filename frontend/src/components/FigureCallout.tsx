'use client'

import { formatBusinessValue } from '../lib/businessPresentation'
import { answerLocale } from '../lib/chartMetric'
import type { ChatResponse } from '../types/api'

/** The one figure of a single-value answer, when the result is one number. */
export function singleFigure(response: ChatResponse): number | null {
  if (response.status !== 'SUCCESS' || response.strategy === 'agent' || response.data.rows.length !== 1) return null
  const row = response.data.rows[0]
  const numeric = response.data.columns.filter(column => typeof row[column] === 'number')
  if (numeric.length !== 1 || response.data.columns.length > 2) return null
  const value = row[numeric[0]] as number
  return Number.isFinite(value) ? value : null
}

/**
 * What the sentence above cannot say on its own: how the figure stands against the target the model's author declared.
 * The figure itself is already in the answer, so it is not repeated here; without a declared target nothing is shown.
 * Good or bad is said only when the model declares which way is better.
 */
export function FigureCallout({ response, value }: { response: ChatResponse; value: number }) {
  const data = response.data
  const target = typeof data.metric_target === 'number' ? data.metric_target : null
  if (target === null) return null
  const unit = data.unit_format ?? undefined
  const locale = answerLocale(response)
  const show = (n: number) => formatBusinessValue('metric_value', n, data.governed_metric ?? undefined, unit, locale)
  const above = value > target
  const gap = Math.abs(value - target)
  const gapText = unit === 'percent' ? `${Number(gap.toFixed(2)).toLocaleString(locale)} pts` : show(gap)
  const good = data.metric_better ? (data.metric_better === 'up') === above : null
  const tone = value === target ? 'text-slate-800' : good === null ? 'text-slate-800' : good ? 'text-emerald-700' : 'text-rose-700'
  const standing = value === target ? 'on target' : `${gapText} ${above ? 'above' : 'below'} target`
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-sm text-slate-600" data-testid="figure-callout">
      <span>Target {show(target)}</span>
      <span aria-hidden className="text-slate-300">·</span>
      <span className={`font-semibold ${tone}`}>{standing}</span>
    </p>
  )
}
