import { describe, expect, it } from 'vitest'
import { formatSql, tokenizeLine } from './formatSql'

const FUEL = `SELECT d.regional AS regional, COUNT(CASE WHEN status_pengiriman = 'Terlambat' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN status_pengiriman <> 'Dalam_Perjalanan' THEN 1 END), 0) AS metric_value FROM "iceberg"."default"."fuel_deliveries" AS d WHERE (d.tanggal_transaksi >= CAST('2025-01-01' AS DATE) AND d.tanggal_transaksi < CAST('2026-11-01' AS DATE)) GROUP BY d.regional ORDER BY metric_value DESC LIMIT 5`

describe('formatSql', () => {
  it('lays a query out one clause per line and one column per line', () => {
    expect(formatSql(FUEL).split('\n')).toEqual([
      'SELECT',
      '  d.regional AS regional,',
      "  COUNT(CASE WHEN status_pengiriman = 'Terlambat' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN status_pengiriman <> 'Dalam_Perjalanan' THEN 1 END), 0) AS metric_value",
      'FROM "iceberg"."default"."fuel_deliveries" AS d',
      'WHERE',
      "  (d.tanggal_transaksi >= CAST('2025-01-01' AS DATE) AND d.tanggal_transaksi < CAST('2026-11-01' AS DATE))",
      'GROUP BY d.regional',
      'ORDER BY metric_value DESC',
      'LIMIT 5',
    ])
  })

  it('puts each condition, sub-query and join condition on its own indented line, and keeps BETWEEN x AND y together', () => {
    const out = formatSql("WITH t AS (SELECT regional, SUM(v) AS v FROM x WHERE a BETWEEN 1 AND 5 AND b IN ('x', 'y') GROUP BY regional) SELECT t.regional FROM t LEFT JOIN y ON t.regional = y.regional AND y.ok = 1 WHERE t.v > (SELECT AVG(v) FROM t)")
    expect(out).toContain('    a BETWEEN 1 AND 5\n    AND b IN (\'x\', \'y\')')
    expect(out).toContain('LEFT JOIN y ON t.regional = y.regional\n  AND y.ok = 1')
    expect(out).toContain('t.v > (\n    SELECT\n      AVG(v)\n    FROM t\n  )')
  })

  it('changes only whitespace: the words, strings and numbers are the ones that ran', () => {
    const squash = (text: string) => text.replace(/\s+/g, '').replace(/\(\s+/g, '(')
    expect(squash(formatSql(FUEL))).toBe(squash(FUEL))
  })

  it('colours keywords, functions, strings and numbers', () => {
    const kinds = Object.fromEntries(tokenizeLine("  COUNT(x) = 'a' AND 100.0").filter(t => t.kind !== 'space').map(t => [t.text, t.kind]))
    expect(kinds).toMatchObject({ COUNT: 'function', "'a'": 'string', AND: 'keyword', '100.0': 'number' })
  })
})
