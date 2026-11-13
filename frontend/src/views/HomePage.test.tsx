import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../lib/modelSelection', () => ({ useModelSelection: () => ({ selection: { provider: 'qwen', model: 'm' } }) }))
vi.mock('../lib/api', () => ({ api: { home: vi.fn(), homeBriefing: vi.fn() } }))
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }
})

import { api } from '../lib/api'
import { HomePage } from './HomePage'

const kpi = (metric: string, label: string, value: number, unit: string) => ({
  metric,
  label,
  unit_format: unit,
  value,
  series: [
    { month: '2026-08', value: value - 1 },
    { month: '2026-09', value: value + 1 },
    { month: '2026-10', value: value + 2 },
  ],
  last_month: { month: '2026-10', value: value + 2 },
  previous_month: { month: '2026-09', value: value + 1 },
  change: 1,
  change_pct: 6.2,
})

describe('HomePage', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows the KPIs, the briefing with questions that open Ask Data, the trend and the breakdown', async () => {
    vi.mocked(api.home).mockResolvedValue({
      status: 'ok',
      language: 'id',
      data_coverage: { first: '2025-01-01', last: '2026-10-31' },
      kpis: [kpi('tingkat_keterlambatan', 'Tingkat Keterlambatan (%)', 16.07, 'percent'), { ...kpi('total_volume', 'Total Volume', 4996168, 'quantity'), unit: 'KL' }, kpi('pencapaian_kuota', 'Pencapaian Kuota', 93.7, 'percent')],
      trend: kpi('tingkat_keterlambatan', 'Tingkat Keterlambatan (%)', 16.07, 'percent'),
      breakdown: {
        metric: 'tingkat_keterlambatan',
        label: 'Tingkat Keterlambatan (%)',
        dimension: 'regional',
        columns: ['regional', 'metric_value'],
        rows: [{ regional: 'Papua Maluku', metric_value: 34.54 }, { regional: 'Jatimbalinus', metric_value: 11.4 }],
        column_labels: { regional: 'Regional' },
        overall_value: 16.07,
        unit_format: 'percent',
      },
      map: null,
    })
    vi.mocked(api.homeBriefing).mockResolvedValue({
      status: 'ok',
      headline: 'Keterlambatan 16,1% secara keseluruhan.',
      points: ['Papua Maluku tertinggi di 34,5%.'],
      ask_next: ['Kenapa Papua Maluku paling sering terlambat?'],
    })
    render(<HomePage />)
    await waitFor(() => expect(screen.getAllByTestId('home-kpi')).toHaveLength(3))
    expect(screen.getByText('Ringkasan Bisnis')).toBeTruthy()
    expect(screen.getByText('16,1%')).toBeTruthy() // the language of the model: a decimal comma
    expect(screen.getByText('4.996.168 KL')).toBeTruthy() // with the unit the metric declares
    expect(screen.getAllByText(/\+1,0 poin/).length).toBeGreaterThan(0) // a percent moves in points
    expect(screen.getAllByTestId('home-kpi')[0].className).toContain('sm:col-span-2') // the headline tile leads
    await waitFor(() => expect(screen.getByText('Keterlambatan 16,1% secara keseluruhan.')).toBeTruthy())
    const question = screen.getByText('Kenapa Papua Maluku paling sering terlambat?')
    expect(question.closest('a')?.getAttribute('href')).toBe(`/?ask=${encodeURIComponent('Kenapa Papua Maluku paling sering terlambat?')}`)
    expect(screen.getByText(/Tren bulanan/)).toBeTruthy()
    expect(screen.getByText(/per Regional/)).toBeTruthy()
    expect(api.home).toHaveBeenCalledWith({ provider: 'qwen', model: 'm' }, false)
  })

  it('says so when no model is published', async () => {
    vi.mocked(api.home).mockResolvedValue({ status: 'no_model', kpis: [] })
    vi.mocked(api.homeBriefing).mockResolvedValue({ status: 'no_data' })
    render(<HomePage />)
    await waitFor(() => expect(screen.getByText(/No semantic model is published/)).toBeTruthy())
    expect(screen.getByRole('link', { name: 'Open Semantic Layer' }).getAttribute('href')).toBe('/semantic-layer')
    expect(screen.queryByTestId('home-briefing')).toBeNull()
  })

  it('shows the figures this browser saw last at once, then the fresh ones', async () => {
    const stored = { home: { status: 'ok', language: 'en', kpis: [kpi('late', 'Late rate', 12.5, 'percent')] }, briefing: null }
    localStorage.setItem('ai-studio.home.v2', JSON.stringify(stored))
    let resolve: (value: unknown) => void = () => {}
    vi.mocked(api.home).mockReturnValue(new Promise(r => (resolve = r)) as never)
    vi.mocked(api.homeBriefing).mockResolvedValue({ status: 'no_data' })
    render(<HomePage />)
    expect(await screen.findByText('12.5%')).toBeTruthy() // no placeholder while the fresh figures load
    resolve({ status: 'ok', language: 'en', kpis: [kpi('late', 'Late rate', 13.25, 'percent')] })
    await waitFor(() => expect(screen.getByText('13.3%')).toBeTruthy())
    localStorage.clear()
  })

  it('shows the layout while the figures load, and says what failed with a way to retry', async () => {
    vi.mocked(api.home).mockRejectedValue({ message: 'down' })
    vi.mocked(api.homeBriefing).mockRejectedValue({ message: 'down' })
    render(<HomePage />)
    expect(screen.getByRole('status').textContent).toContain('Computing the headline figures')
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('could not be loaded'))
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })
})

describe('formatFigure', () => {
  it('writes figures in the language of the page with their unit, and says when there is none', async () => {
    const { formatFigure } = await import('./HomePage')
    expect(formatFigure(58_537_828_400_000, 'currency_idr', 'IDR', 'id')).toBe('Rp58,54 T')
    expect(formatFigure(58_537_828_400_000, 'currency_idr', 'IDR', 'en')).toBe('Rp58.54T')
    expect(formatFigure(168.54, 'minutes', 'minutes', 'id')).toBe('168,5 menit')
    expect(formatFigure(3000, 'quantity', 'stations', 'id')).toBe('3.000 stations')
    expect(formatFigure(null, 'percent', '%', 'id')).toBe('Tidak tersedia')
  })
})
