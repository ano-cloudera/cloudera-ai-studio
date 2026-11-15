import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { detectRoutes } from '../../lib/routes'
import { fewRecords, RouteMap } from './RouteMap'

const square = (name: string, lon: number, lat: number) => ({
  type: 'Feature',
  properties: { name },
  geometry: { type: 'MultiPolygon', coordinates: [[[[lon, lat], [lon + 3, lat], [lon + 3, lat - 3], [lon, lat - 3], [lon, lat]]]] },
})
const geo = { fuel_terminal: { Wayame: [-3.6, 128.2], Plumpang: [-6.1, 106.9], Panjang: [-5.5, 105.3] } }
const rows = [
  { fuel_terminal: 'Plumpang', provinsi: 'DKI Jakarta', rate: 12.0, lo: 9000 },
  { fuel_terminal: 'Wayame', provinsi: 'Maluku', rate: 37.1, lo: 3107 },
  { fuel_terminal: 'Panjang', provinsi: 'Lampung', rate: 13.5, lo: 5000 },
]
const columns = ['fuel_terminal', 'provinsi', 'rate', 'lo']

describe('RouteMap', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  function renderMap(onAsk = vi.fn()) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ type: 'FeatureCollection', features: [square('Jakarta Raya', 106, -5), square('Maluku', 127, -2), square('Lampung', 104, -4)] }),
      }),
    )
    render(
      <RouteMap
        rows={rows}
        detection={detectRoutes(columns, rows, geo)!}
        metricLabel="Tingkat Keterlambatan (%)"
        unitFormat="percent"
        better="down"
        target={15}
        overall={16.1}
        language="id"
        onAsk={onAsk}
      />,
    )
    return onAsk
  }

  it('opens on the worst route, lists the routes worst first, and marks the target', async () => {
    renderMap()
    await waitFor(() => expect(screen.getByTestId('route-card')).toBeTruthy())
    expect(screen.getByTestId('route-card').textContent).toContain('Wayame')
    expect(screen.getByTestId('route-card').textContent).toContain('missed')
    const list = screen.getByRole('list', { name: 'Routes, worst first' })
    expect([...list.querySelectorAll('button')].map(button => button.textContent?.replace(/[\d.,]+%$/, ''))).toEqual([
      '1Wayame → Maluku',
      '2Panjang → Lampung',
      '3Plumpang → DKI Jakarta',
    ])
    expect(document.querySelectorAll('[data-route]')).toHaveLength(3)
    expect(screen.getByTestId('route-legend').textContent).toContain('line width is')
  })

  it('shows a route picked from the list and asks the agent why, in the language of the answer', async () => {
    const onAsk = renderMap()
    await waitFor(() => expect(screen.getByTestId('route-card')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /Panjang → Lampung/ }))
    expect(screen.getByTestId('route-card').textContent).toContain('Lampung')
    fireEvent.click(screen.getByTestId('route-ask-why'))
    expect(onAsk).toHaveBeenCalledWith('Kenapa tingkat keterlambatan rute Panjang ke Lampung rendah, dan apa penyebab utamanya?')
  })

  it('flags a route counted on far fewer records than the others', () => {
    expect(fewRecords(33, [33, 3000, 3100, 4000, 5000])).toBe(true)
    expect(fewRecords(2900, [33, 3000, 3100, 4000, 5000])).toBe(false)
    expect(fewRecords(null, [1, 2, 3])).toBe(false)
  })
})
