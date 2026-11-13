import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentSteps } from './AgentSteps'

describe('AgentSteps', () => {
  afterEach(cleanup)

  it('lists the checks behind an answer and opens one to its rows, overall value and query', () => {
    render(
      <AgentSteps
        steps={[
          {
            title: 'Late rate by region', tool: 'query_metric', status: 'ok', row_count: 8, columns: ['regional', 'metric_value'],
            column_labels: { regional: 'Regional', metric_value: 'Late rate' }, rows: [{ regional: 'Papua Maluku', metric_value: 34.54 }],
            unit_format: 'percent', overall_value: 16.07, sql: 'SELECT regional, ... FROM fuel_deliveries',
          },
          { title: 'SOP thresholds', tool: 'search_documents', status: 'ok', row_count: 2, sources: [{ file: 'SOP.pdf', page: 2 }] },
          { title: 'Late rate in Atlantis', tool: 'query_metric', status: 'no_data', row_count: 0 },
        ]}
      />,
    )
    expect(screen.getByText(/The agent ran 3 steps/)).toBeTruthy()
    expect(screen.getByText('8 rows')).toBeTruthy()
    expect(screen.getByText('2 sources')).toBeTruthy()
    expect(screen.getByText('no data')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Late rate by region/ }))
    expect(screen.getByText('Papua Maluku')).toBeTruthy()
    expect(screen.getByText('34.54%')).toBeTruthy()
    expect(screen.getByText(/Overall: 16.07%/)).toBeTruthy()
    expect(screen.getByText('+7 more rows')).toBeTruthy()
    expect(screen.getByText('View query')).toBeTruthy()
  })
})
