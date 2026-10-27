/** When governed SQL returns one row, prefer a metric card over a 1-row table. */

const METRIC_COLUMN_RE =
  /^(metric_value|value|amount|qty|quantity|rate|fill_rate|cover|months_of_cover|bill_val|bill_qty)$/i

export type CompactSingleRow = {
  dimensions: { column: string; value: unknown }[]
  metricColumn: string
  metricValue: unknown
}

export function compactSingleRowEvidence(
  columns: string[],
  rows: Record<string, unknown>[],
): CompactSingleRow | null {
  if (rows.length !== 1 || !columns.length) return null
  if (columns.length > 4) return null

  const row = rows[0]
  let metricColumn =
    columns.find(c => c === 'metric_value') ??
    columns.find(c => METRIC_COLUMN_RE.test(c)) ??
    columns.find(c => typeof row[c] === 'number')

  if (!metricColumn) {
    if (columns.length === 1) metricColumn = columns[0]
    else return null
  }

  const dimensions = columns.filter(c => c !== metricColumn).map(c => ({ column: c, value: row[c] }))
  return { dimensions, metricColumn, metricValue: row[metricColumn] }
}
