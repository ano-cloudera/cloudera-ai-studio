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
      kpis: [kpi('tingkat_keterlambatan', 'Tingkat Keterlambatan (%)', 16.07, 'percent'), kpi('total_volume', 'Total Volume (KL)', 4996168, 'quantity')],
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
    await waitFor(() => expect(screen.getAllByTestId('home-kpi')).toHaveLength(2))
    expect(screen.getByText('Ringkasan Bisnis')).toBeTruthy()
    expect(screen.getByText('16.1%')).toBeTruthy()
    expect(screen.getByText('4,996,168')).toBeTruthy()
    expect(screen.getByText(/\+1\.0 poin/)).toBeTruthy() // a percent moves in points
    await waitFor(() => expect(screen.getByText('Keterlambatan 16,1% secara keseluruhan.')).toBeTruthy())
    const question = screen.getByText('Kenapa Papua Maluku paling sering terlambat?')
    expect(question.closest('a')?.getAttribute('href')).toBe(`/?ask=${encodeURIComponent('Kenapa Papua Maluku paling sering terlambat?')}`)
    expect(screen.getByText(/Tren bulanan/)).toBeTruthy()
    expect(screen.getByText(/Per Regional/)).toBeTruthy()
    expect(api.home).toHaveBeenCalledWith({ provider: 'qwen', model: 'm' }, false)
  })

  it('says so when no model is published', async () => {
    vi.mocked(api.home).mockResolvedValue({ status: 'no_model', kpis: [] })
    render(<HomePage />)
    await waitFor(() => expect(screen.getByText(/No semantic model is published/)).toBeTruthy())
    expect(api.homeBriefing).not.toHaveBeenCalled()
  })
})
