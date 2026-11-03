import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { CalculationNoteBlock } from './CalculationNoteBlock'
import type { CalculationNote } from '../../types/api'

const note: CalculationNote = {
  kind: 'governed',
  summary: 'Late Delivery Rate (%) · by region name · delivery_shipments',
  metric: 'Late Delivery Rate (%)',
  formula: 'COUNT(CASE WHEN is_late THEN 1 END) * 100.0 / COUNT(shipment_id)',
  breakdown: ['region name'],
  filters: ['carrier: NusaCargo'],
  period: '2026-03-01 to 2026-05-31',
  source: ['delivery_shipments'],
  comparison: null,
  steps: [],
  checks: [{ name: 'period', status: 'warning', message: 'The period asked for is not in the query.' }],
}

describe('CalculationNoteBlock', () => {
  afterEach(cleanup)

  it('shows the summary and opens the details on click', () => {
    render(<CalculationNoteBlock note={note} />)
    expect(screen.getByText(note.summary)).toBeTruthy()
    expect(screen.getByText('1 to check')).toBeTruthy()
    expect(screen.queryByText('carrier: NusaCargo')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /How this was calculated/i }))
    expect(screen.getByText('carrier: NusaCargo')).toBeTruthy()
    expect(screen.getByText('2026-03-01 to 2026-05-31')).toBeTruthy()
    expect(screen.getByText(/The period asked for is not in the query/)).toBeTruthy()
  })
})
