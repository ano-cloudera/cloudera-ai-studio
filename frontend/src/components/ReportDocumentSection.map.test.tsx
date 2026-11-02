import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReportDocumentSection } from './ReportDocumentSection'
import type { ChatResponse } from '../types/api'

const square = (name: string, lon: number, lat: number) => ({
  type: 'Feature',
  properties: { name },
  geometry: { type: 'MultiPolygon', coordinates: [[[[lon, lat], [lon + 3, lat], [lon + 3, lat - 3], [lon, lat - 3], [lon, lat]]]] },
})

function response(rows: Record<string, unknown>[], columns: string[]): ChatResponse {
  return {
    request_id: 'r1',
    status: 'SUCCESS',
    answer: { direct_answer: 'Kalimantan Timur is highest.', executive_summary: 'Kalimantan Timur is highest.', insights: [], business_implications: [], caveats: [], data_reference: 'x', chart_spec: null },
    chart_spec: null,
    data: { columns, rows, row_count: rows.length, governed_metric: 'Late Delivery Rate (%)' },
    governed_sql: 'SELECT 1',
  } as unknown as ChatResponse
}

describe('Map tab', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows a Map tab only when the result has provinces', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ type: 'FeatureCollection', features: [square('Jawa Timur', 112, -7), square('Kalimantan Timur', 114, 1)] }) }))
    const { unmount } = render(
      <ReportDocumentSection response={response([{ region_name: 'Jawa Timur', metric_value: 16.3 }, { region_name: 'Kalimantan Timur', metric_value: 23.1 }], ['region_name', 'metric_value'])} />,
    )
    fireEvent.click(screen.getByRole('tab', { name: 'Map' }))
    await waitFor(() => expect(screen.getByTestId('result-map')).toBeTruthy())
    unmount()
    render(<ReportDocumentSection response={response([{ carrier: 'NusaCargo', metric_value: 13.2 }, { carrier: 'KilatKirim', metric_value: 11.3 }], ['carrier', 'metric_value'])} />)
    expect(screen.queryByRole('tab', { name: 'Map' })).toBeNull()
  })
})
