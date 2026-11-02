import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResultMap } from './ResultMap'
import type { GeoCollection } from '../../lib/geo'

const square = (name: string, lon: number, lat: number) => ({
  type: 'Feature' as const,
  properties: { name },
  geometry: {
    type: 'MultiPolygon' as const,
    coordinates: [[[[lon, lat], [lon + 3, lat], [lon + 3, lat - 3], [lon, lat - 3], [lon, lat]]]],
  },
})
const boundaries: GeoCollection = {
  type: 'FeatureCollection',
  features: [square('Jawa Timur', 112, -7), square('Kalimantan Timur', 114, 1), square('Bali', 115, -8)],
}
const detection = { geoColumn: 'region_name', valueColumn: 'metric_value', matched: 2, unmatched: ['Atlantis'] }
const rows = [
  { region_name: 'Jawa Timur', metric_value: 16.3 },
  { region_name: 'Kalimantan Timur', metric_value: 23.1 },
  { region_name: 'Atlantis', metric_value: 1 },
]

describe('ResultMap', () => {
  beforeEach(() => {
    vi.resetModules()
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('draws the provinces, ranks the values and switches to bubbles', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => boundaries }))
    const { ResultMap: Fresh } = await import('./ResultMap')
    render(<Fresh columns={['region_name', 'metric_value']} rows={rows} detection={detection} metric="Late Delivery Rate (%)" />)
    await waitFor(() => expect(screen.getByTestId('result-map')).toBeTruthy())
    expect(document.querySelectorAll('path[data-province]').length).toBe(3)
    const ranking = screen.getByRole('list', { name: /highest first/i })
    expect(ranking.textContent?.indexOf('Kalimantan Timur')).toBeLessThan(ranking.textContent?.indexOf('Jawa Timur') ?? 0)
    expect(screen.getByRole('note').textContent).toContain('Atlantis')
    expect(document.querySelectorAll('circle[data-bubble]').length).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: 'Bubbles' }))
    expect(document.querySelectorAll('circle[data-bubble]').length).toBe(2)
    const big = document.querySelector('circle[data-bubble="Kalimantan Timur"]')!
    const small = document.querySelector('circle[data-bubble="Jawa Timur"]')!
    expect(Number(big.getAttribute('r'))).toBeGreaterThan(Number(small.getAttribute('r')))
  })

  it('says so when the boundaries cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))
    const { ResultMap: Fresh } = await import('./ResultMap')
    render(<Fresh columns={['region_name', 'metric_value']} rows={rows} detection={detection} />)
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('could not be loaded'))
  })

  it('keeps the unused import honest', () => {
    expect(ResultMap).toBeTypeOf('function')
  })
})
