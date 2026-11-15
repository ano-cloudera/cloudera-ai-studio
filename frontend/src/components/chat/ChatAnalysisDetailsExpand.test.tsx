import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ChatAnalysisDetailsExpand } from './ChatAnalysisDetailsExpand'
import type { CalculationNote, ChatResponse } from '../../types/api'

const note = { summary: 'Jumlah Industri · fuel_customers', metric: 'Jumlah Industri', formula: 'COUNT(id)', breakdown: [], period: null, filters: [], source: ['fuel_customers'], comparison: null, steps: [], checks: [{ name: 'range', status: 'warning', message: 'check me' }], scope: null } as unknown as CalculationNote
const response = { status: 'SUCCESS', strategy: 'governed', governed_sql: 'SELECT COUNT(id) FROM fuel_customers', data: { columns: ['metric_value'], rows: [{ metric_value: 400 }], row_count: 1, execution_ms: 1 } } as unknown as ChatResponse

describe('ChatAnalysisDetailsExpand', () => {
  afterEach(cleanup)

  it('is one row for how the figure was calculated and the query that ran, under one short title', () => {
    render(<ChatAnalysisDetailsExpand response={response} tier={1} kpiBlock={null} tableBlock={null} calculation={note} executiveQueryOnly />)
    const toggle = screen.getByRole('button', { name: /Query details/ })
    expect(toggle.textContent).toContain('Jumlah Industri · fuel_customers')
    expect(toggle.textContent).toContain('1 to check')
    expect(screen.queryByText('How this was calculated')).toBeNull()
    expect(screen.queryByTestId('query-details-calculation')).toBeNull() // closed until clicked
    fireEvent.click(toggle)
    expect(screen.getByTestId('query-details-calculation').textContent).toContain('COUNT(id)')
    expect(screen.getByTestId('workspace-sql').textContent).toContain('SELECT')
  })
})
