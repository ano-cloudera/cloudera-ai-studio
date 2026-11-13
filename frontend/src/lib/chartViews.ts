/**
 * The two ways a result can be drawn: its own chart, and at most one alternative that the same rows support, so switching
 * never needs a new query. An alternative is offered only when it is honest for the data:
 * - a share of the whole (pie) or a Pareto only for a measure that adds up (a volume, a count, an amount), never for a rate;
 * - "vs overall" (each group's distance from the overall value) for a rate or an average, when the overall value is known;
 * - stacked bars only for a measure that adds up, when the result has a series;
 * - a line for a breakdown over time drawn as bars, and bars for a line.
 */
export type ChartView = 'native' | 'bar' | 'line' | 'pie' | 'pareto' | 'vs_overall' | 'stacked'

export type ChartViewOption = { id: ChartView; label: string }

const NON_ADDITIVE_UNITS = new Set(['percent', 'ratio', 'minutes'])

/** A measure that adds up across groups. Unknown units are treated as not adding up, so no share is drawn by guess. */
export function isAdditiveUnit(unitFormat: string | null | undefined): boolean {
  return Boolean(unitFormat) && !NON_ADDITIVE_UNITS.has(String(unitFormat))
}

const NATIVE_LABEL: Record<string, string> = { bar: 'Bar', line: 'Line', area: 'Area', pie: 'Pie', scatter: 'Scatter' }

export function chartViews(input: {
  type: string
  values: number[]
  unitFormat?: string | null
  overall?: number | null
  hasSeries: boolean
  timeOnX: boolean
}): ChartViewOption[] {
  const native: ChartViewOption = { id: 'native', label: NATIVE_LABEL[input.type] ?? 'Chart' }
  const additive = isAdditiveUnit(input.unitFormat)
  const count = input.values.length
  const nonNegative = input.values.every(value => value >= 0)
  let alternative: ChartViewOption | null = null
  if (input.type === 'line' || input.type === 'area') {
    alternative = { id: 'bar', label: 'Bar' }
  } else if (input.type === 'bar' && input.hasSeries) {
    alternative = additive && nonNegative ? { id: 'stacked', label: 'Stacked' } : null
  } else if (input.type === 'bar' && input.timeOnX) {
    alternative = count >= 3 ? { id: 'line', label: 'Line' } : null
  } else if (input.type === 'bar') {
    if (!additive && typeof input.overall === 'number' && count >= 2) alternative = { id: 'vs_overall', label: 'vs overall' }
    else if (additive && nonNegative && count >= 2 && count <= 6) alternative = { id: 'pie', label: 'Share' }
    else if (additive && nonNegative && count >= 3) alternative = { id: 'pareto', label: 'Pareto' }
  }
  return alternative ? [native, alternative] : [native]
}

/** Rows sorted largest first with the running share of the total, for a Pareto. */
export function paretoRows(rows: Record<string, unknown>[], x: string, y: string): Record<string, unknown>[] {
  const sorted = [...rows].filter(row => typeof row[y] === 'number').sort((a, b) => (b[y] as number) - (a[y] as number))
  const total = sorted.reduce((sum, row) => sum + (row[y] as number), 0)
  let running = 0
  return sorted.map(row => {
    running += row[y] as number
    return { [x]: row[x], [y]: row[y], __cumulative: total ? Math.round((running / total) * 10000) / 100 : 0 }
  })
}

/** Each group's distance from the overall value, largest first. */
export function differenceRows(rows: Record<string, unknown>[], x: string, y: string, overall: number): Record<string, unknown>[] {
  return rows
    .filter(row => typeof row[y] === 'number')
    .map(row => ({ [x]: row[x], __difference: Math.round(((row[y] as number) - overall) * 10000) / 10000 }))
    .sort((a, b) => (b.__difference as number) - (a.__difference as number))
}
