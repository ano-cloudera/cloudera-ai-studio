import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { ChatResponse } from '../../types/api'
import { ComparisonSummary, comparisonKind } from './ComparisonSummary'

afterEach(cleanup)

const response = (columns: string[], rows: Record<string, unknown>[], period?: string) =>
  ({ data: { columns, rows, row_count: rows.length }, calculation: period ? { period } : null }) as unknown as ChatResponse

describe('comparison summary', () => {
  it('reads the kind of comparison from the columns', () => {
    expect(comparisonKind(['region', 'metric_value', 'previous_value', 'change', 'change_pct'])).toBe('periods')
    expect(comparisonKind(['carrier', 'metric_value', 'overall_value', 'difference'])).toBe('benchmark')
    expect(comparisonKind(['region', 'metric_value'])).toBeNull()
  })

  it('shows before, after and the change with the periods as column names', () => {
    render(
      <ComparisonSummary
        response={response(
          ['region_name', 'metric_value', 'previous_value', 'change', 'change_pct'],
          [{ region_name: 'Sumatera Utara', metric_value: 15.6, previous_value: 6, change: 9.6, change_pct: 160 }],
          '2026-03 to 2026-05 vs 2026-06 to 2026-08',
        )}
      />,
    )
    const table = screen.getByTestId('comparison-summary')
    expect(table.textContent).toContain('2026-03 to 2026-05')
    expect(table.textContent).toContain('2026-06 to 2026-08')
    expect(table.textContent).toContain('Sumatera Utara')
    expect(table.textContent).toContain('+9.6')
    expect(table.textContent).toContain('+160%')
  })

  it('shows each group against the overall value', () => {
    render(
      <ComparisonSummary
        response={response(
          ['carrier', 'metric_value', 'overall_value', 'difference'],
          [{ carrier: 'NusaCargo', metric_value: 13.2, overall_value: 11.26, difference: 1.93 }],
        )}
      />,
    )
    const table = screen.getByTestId('comparison-summary')
    expect(table.textContent).toContain('NusaCargo')
    expect(table.textContent).toContain('Overall')
    expect(table.textContent).toContain('+1.93')
  })

  it('renders nothing for an ordinary result', () => {
    const { container } = render(<ComparisonSummary response={response(['region', 'metric_value'], [{ region: 'A', metric_value: 1 }])} />)
    expect(container.firstChild).toBeNull()
  })
})
