import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('shows the briefing band, KPIs coloured only by what the model declares, the briefing detail, what stands out, the trend and the breakdown', async () => {
    vi.mocked(api.home).mockResolvedValue({
      status: 'ok',
      language: 'en',
      data_coverage: { first: '2025-01-01', last: '2026-10-31' },
      kpis: [
        { ...kpi('late', 'Late rate', 16.07, 'percent'), change: -0.2, better: 'down', target: 15 },
        { ...kpi('volume', 'Total Volume', 4996168, 'quantity'), unit: 'KL', change: 11224, change_pct: 4.8, better: 'up' },
        { ...kpi('quota', 'Quota attainment', 93.7, 'percent'), change: -0.6, target: 100 },
      ],
      breakdown: {
        metric: 'late',
        label: 'Late rate',
        dimension: 'regional',
        columns: ['regional', 'metric_value'],
        rows: [{ regional: 'Papua Maluku', metric_value: 34.54 }, { regional: 'Jatimbalinus', metric_value: 11.4 }],
        column_labels: { regional: 'Regional' },
        overall_value: 16.07,
        unit_format: 'percent',
      },
      standout: {
        metric: 'late', label: 'Late rate', by: 'Terminal', overall_value: 16.07, unit_format: 'percent', better: 'down',
        groups: [{ group: 'Sorong', value: 36.31, difference: 20.24 }, { group: 'Wayame', value: 35.2, difference: 19.13 }],
      },
      map: null,
    })
    vi.mocked(api.homeBriefing).mockResolvedValue({
      status: 'ok',
      headline: 'Late deliveries improved 0.2 points, but Sorong is still the main outlier.',
      what_happened: 'The late rate fell to 15.6% in October 2026.',
      why_it_matters: 'Sorong at 36.3% holds the national rate up.',
      look_next: ['Sorong at 36.3%.'],
      ask_next: ['Why is Sorong so late?'],
    })
    render(<HomePage />)
    await waitFor(() => expect(screen.getAllByTestId('home-kpi')).toHaveLength(3))
    expect(screen.getByText('Business Overview')).toBeTruthy()
    expect(screen.getByText('16.1%')).toBeTruthy()
    expect(screen.getByText('4,996,168 KL')).toBeTruthy() // with the unit the metric declares
    // status: against the target when there is one; coloured only when the model says which way is good
    expect(screen.getByText('Above target').className).toContain('rose') // lower is better, 16.1% > 15%
    expect(screen.getByText('Below target').className).toContain('slate') // quota: no direction declared, so neutral
    expect(screen.getByText('Improving').className).toContain('emerald') // volume rose and higher is better
    expect(screen.getByText('0.2 pts').closest('span')?.className).toContain('emerald') // the late rate fell: good
    const sizes = screen.getAllByTestId('home-kpi').map(tile => tile.className)
    expect(new Set(sizes).size).toBe(1) // one size and one structure, so the tiles compare at a glance
    await waitFor(() => expect(screen.getByText(/Sorong is still the main outlier/)).toBeTruthy())
    const question = screen.getByText('Why is Sorong so late?')
    expect(question.closest('a')?.getAttribute('href')).toBe(`/?ask=${encodeURIComponent('Why is Sorong so late?')}`)
    expect(screen.getByText('What happened')).toBeTruthy()
    expect(screen.getByTestId('home-standout').textContent).toContain('Sorong')
    expect(screen.getByTestId('home-standout').textContent).toContain('+20.2 pts')
    expect(screen.getAllByRole('tab')).toHaveLength(3) // the trend switches between the KPIs
    fireEvent.click(screen.getByRole('tab', { name: 'Total Volume' }))
    expect(screen.getByText(/Monthly trend: Total Volume/)).toBeTruthy()
    expect(screen.getByText(/Late rate by Regional/)).toBeTruthy()
    expect(api.home).toHaveBeenCalledWith({ provider: 'qwen', model: 'm' }, false)
  })

  it('asks for metrics to be marked when the model marks none, instead of showing any', async () => {
    vi.mocked(api.home).mockResolvedValue({ status: 'no_home_metrics', kpis: [], language: 'en', metric_count: 12 })
    vi.mocked(api.homeBriefing).mockResolvedValue({ status: 'no_data' })
    render(<HomePage />)
    await waitFor(() => expect(screen.getByText(/No metric is marked for Home yet/)).toBeTruthy())
    expect(screen.queryAllByTestId('home-kpi')).toHaveLength(0)
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
    localStorage.setItem('ai-studio.home.v4', JSON.stringify(stored))
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
