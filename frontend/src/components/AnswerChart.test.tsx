import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('recharts', () => {
  const container = ({ children, data }: { children?: React.ReactNode; data?: unknown }) => <div data-chart={data ? JSON.stringify(data) : undefined}>{children}</div>
  return {
    ResponsiveContainer: container, ScatterChart: container, BarChart: container, AreaChart: container,
    LineChart: container, PieChart: container, CartesianGrid: () => null, Tooltip: () => null,
    Legend: ({ wrapperStyle }: { wrapperStyle?: { fontSize?: number } }) => <div data-testid="legend" data-font-size={wrapperStyle?.fontSize} />, Cell: () => null, Pie: container,
    XAxis: ({ dataKey, tick, interval }: { dataKey?: string; tick?: { fontSize?: number }; interval?: number }) => <div data-testid="x-axis" data-key={dataKey} data-font-size={tick?.fontSize} data-interval={interval} />,
    YAxis: ({ dataKey, tick }: { dataKey?: string; tick?: { fontSize?: number } }) => <div data-testid="y-axis" data-key={dataKey} data-font-size={tick?.fontSize} />,
    Scatter: ({ name }: { name?: string }) => <div data-testid="scatter" data-name={name} />,
    Bar: ({ dataKey, maxBarSize, children }: { dataKey?: string; maxBarSize?: number; children?: React.ReactNode }) => <div data-testid="bar" data-key={dataKey} data-max-size={maxBarSize}>{children}</div>, Area: () => null, Line: () => null,
    ComposedChart: container, LabelList: () => <div data-testid="value-labels" />, ReferenceLine: () => null,
  }
})

import { AnswerChart } from './AnswerChart'

describe('AnswerChart', () => {
  afterEach(cleanup)

  it('binds both numeric scatter axes and renders declared series', () => {
    render(<AnswerChart chart={{ type: 'scatter', title: 'Stock vs sales', x: 'stock', y: 'sales', series: 'region' }} rows={[
      { stock: 10, sales: 20, region: 'West' },
      { stock: 12, sales: 24, region: 'East' },
    ]} />)

    expect(screen.getByTestId('x-axis').getAttribute('data-key')).toBe('stock')
    expect(screen.getByTestId('y-axis').getAttribute('data-key')).toBe('sales')
    expect(screen.getAllByTestId('scatter')).toHaveLength(2)
    expect(screen.getByTestId('legend')).toBeTruthy()
  })

  it('renders one clean ranking series when every row has a unique series label', () => {
    const { container } = render(<AnswerChart chart={{ type: 'bar', title: 'Top products', x: 'material', y: 'metric_value', series: 'customer' }} rows={[
      { material: '001', customer: 'A', metric_value: 21 },
      { material: '002', customer: 'B', metric_value: 17 },
      { material: '003', customer: 'C', metric_value: 15 },
      { material: '004', customer: 'D', metric_value: 14 },
    ]} />)

    expect(screen.queryByTestId('legend')).toBeNull()
    expect(screen.getAllByTestId('bar')).toHaveLength(1)
    expect(screen.getByTestId('bar').getAttribute('data-key')).toBe('metric_value')
    expect(container.innerHTML).toContain('001 · A')
    expect(screen.getByTestId('x-axis').getAttribute('data-font-size')).toBe('11')
    expect(screen.getByTestId('bar').getAttribute('data-max-size')).toBe('54')
  })

  it('uses readable month ticks for line charts on date dimensions', () => {
    const { container } = render(
      <AnswerChart
        chart={{
          type: 'line',
          title: 'Tren Jumlah Transaksi per Bulan',
          x: 'transactions_transaction_date',
          y: 'metric_value',
        }}
        rows={[
          { transactions_transaction_date: '2026-06-01T00:00:00.000Z', metric_value: 95 },
          { transactions_transaction_date: '2026-08-01T00:00:00.000Z', metric_value: 118 },
        ]}
      />,
    )

    expect(screen.getByTestId('x-axis').getAttribute('data-key')).toBe('__time_tick')
    const chartRoot = container.querySelector('[data-chart]')
    expect(chartRoot?.getAttribute('data-chart')).toMatch(/Agu|Jun|2026/i)
  })

  it('draws a long ranking horizontally, every label on its own line, instead of crowding the x axis', () => {
    render(<AnswerChart chart={{ type: 'bar', title: 'Product ranking', x: 'material', y: 'metric_value' }} rows={
      Array.from({ length: 50 }, (_, index) => ({ material: `very-long-material-label-${index}`, metric_value: 50 - index }))
    } />)

    expect(screen.getByTestId('chart-horizontal')).toBeTruthy()
    expect(screen.getByTestId('y-axis').getAttribute('data-key')).toBe('material')
  })
})

describe('the metric a chart plots', () => {
  it('is named and explained under the chart, with which way is good when the model says so', async () => {
    const { render, screen, cleanup } = await import('@testing-library/react')
    const { AnswerChart } = await import('./AnswerChart')
    render(
      <AnswerChart
        chart={{ type: 'bar', title: 'Tingkat Keterlambatan per Regional', x: 'regional', y: 'metric_value' }}
        rows={[{ regional: 'Papua Maluku', metric_value: 34.538 }, { regional: 'Jatimbalinus', metric_value: 11.4 }]}
        metric={{ label: 'Tingkat Keterlambatan', unitFormat: 'percent', description: 'Share of finished loading orders that arrived after their SLA.', better: 'down' }}
      />,
    )
    expect(screen.getByTestId('chart-metric-caption').textContent).toBe('Share of finished loading orders that arrived after their SLA. · Lower is better')
    cleanup()
    render(<AnswerChart chart={{ type: 'bar', title: 'x', x: 'regional', y: 'metric_value' }} rows={[{ regional: 'A', metric_value: 1 }, { regional: 'B', metric_value: 2 }]} />)
    expect(screen.queryByTestId('chart-metric-caption')).toBeNull() // nothing to say: no empty line
    cleanup()
  })
})

describe('switching the view of a chart', () => {
  afterEach(cleanup)
  const volume = [
    { produk: 'Pertalite', metric_value: 1530928 },
    { produk: 'Biosolar', metric_value: 956232 },
    { produk: 'Pertamax', metric_value: 770808 },
    { produk: 'Solar Industri', metric_value: 660184 },
  ]

  it('offers a share of the whole for a volume, and draws it from the same rows without a new query', () => {
    render(<AnswerChart chart={{ type: 'bar', title: 'Volume per produk', x: 'produk', y: 'metric_value' }} rows={volume} metric={{ unitFormat: 'quantity' }} />)
    const switcher = screen.getByTestId('chart-view-switch')
    expect(switcher.textContent).toBe('BarShare')
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))
    expect(screen.getByRole('button', { name: 'Share' }).getAttribute('aria-pressed')).toBe('true')
  })

  it('offers each group against the overall value for a rate, never a pie of rates', () => {
    const rates = [{ regional: 'Papua Maluku', metric_value: 34.54 }, { regional: 'Kalimantan', metric_value: 29.66 }, { regional: 'Jatimbalinus', metric_value: 11.4 }]
    render(<AnswerChart chart={{ type: 'bar', title: 'Late rate', x: 'regional', y: 'metric_value' }} rows={rates} metric={{ unitFormat: 'percent' }} overall={16.07} />)
    expect(screen.getByTestId('chart-view-switch').textContent).toBe('Barvs overall')
    fireEvent.click(screen.getByRole('button', { name: 'vs overall' }))
    const drawn = Array.from(document.querySelectorAll('[data-chart]')).map(el => el.getAttribute('data-chart') ?? '').find(json => json.includes('__difference'))
    expect(drawn).toContain('"__difference":18.47')
  })

  it('shows no switch when the rows support only one honest view', () => {
    const rates = [{ regional: 'A', metric_value: 10 }, { regional: 'B', metric_value: 12 }]
    render(<AnswerChart chart={{ type: 'bar', title: 'Late rate', x: 'regional', y: 'metric_value' }} rows={rates} metric={{ unitFormat: 'percent' }} />)
    expect(screen.queryByTestId('chart-view-switch')).toBeNull()
  })

  it('writes the value on each column in the chat when there are ten bars or fewer; more bars go horizontal with the value at the end of each', () => {
    const rows = (n: number) => Array.from({ length: n }, (_, k) => ({ regional: `R${k}`, metric_value: 30 - k }))
    render(<AnswerChart embedded chart={{ type: 'bar', title: 'Late rate', x: 'regional', y: 'metric_value' }} rows={rows(8)} metric={{ unitFormat: 'percent' }} />)
    expect(screen.getAllByTestId('value-labels').length).toBeGreaterThan(0)
    expect(screen.queryByTestId('chart-horizontal')).toBeNull()
    cleanup()
    render(<AnswerChart embedded chart={{ type: 'bar', title: 'Late rate', x: 'regional', y: 'metric_value' }} rows={rows(12)} metric={{ unitFormat: 'percent' }} />)
    expect(screen.getByTestId('chart-horizontal')).toBeTruthy()
  })
})

describe('AnswerChart with many bars', () => {
  afterEach(cleanup)
  const bar = { type: 'bar', x: 'fuel_terminal', y: 'metric_value', title: 'Late rate per terminal' } as never

  it('draws more than ten bars horizontally, and says what a repeated label is', () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ fuel_terminal: i < 3 ? 'Panjang' : `Terminal ${i}`, provinsi: `Provinsi ${i}`, metric_value: 90 - i }))
    render(<AnswerChart chart={bar} rows={rows} />)
    expect(screen.getByTestId('chart-horizontal')).toBeTruthy()
  })

  it('keeps ten bars or fewer as columns', () => {
    const rows = Array.from({ length: 6 }, (_, i) => ({ fuel_terminal: `Terminal ${i}`, metric_value: 90 - i }))
    render(<AnswerChart chart={bar} rows={rows} />)
    expect(screen.queryByTestId('chart-horizontal')).toBeNull()
  })

  it('shows the first fifteen of a long ranking and points to the table', () => {
    const rows = Array.from({ length: 30 }, (_, i) => ({ fuel_terminal: `Terminal ${i}`, metric_value: 90 - i }))
    render(<AnswerChart chart={bar} rows={rows} />)
    expect(screen.getByTestId('chart-more-note').textContent).toContain('first 15 of 30')
  })
})

describe('AnswerChart comparing two things', () => {
  afterEach(cleanup)
  const bar = { type: 'bar', x: 'regional', y: 'metric_value', title: 'Total volume per regional' } as never
  const dataOf = () => JSON.parse(document.querySelector('[data-chart]')!.getAttribute('data-chart')!) as Record<string, unknown>[]

  it('opens as stacked bars when a regional is split by product and the measure adds up', () => {
    const rows = ['Jawa', 'Papua', 'Sulawesi'].flatMap((regional, i) => ['Biosolar', 'Pertalite'].map((produk, j) => ({ regional, produk, metric_value: 100 * (i + 1) + 10 * j })))
    render(<AnswerChart chart={bar} rows={rows} metric={{ unitFormat: 'KL' }} />)
    expect(screen.getByRole('button', { name: 'Stacked', pressed: true })).toBeTruthy()
    const points = dataOf()
    expect(points).toHaveLength(3) // one stack per regional
    expect(points[0]).toMatchObject({ regional: 'Sulawesi', Biosolar: 300, Pertalite: 310 }) // the largest first
  })

  it('keeps the five largest products and adds the rest into "Others" for an amount', () => {
    const products = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
    const rows = ['Jawa', 'Papua'].flatMap(regional => products.map((produk, j) => ({ regional, produk, metric_value: 100 - j * 10 })))
    render(<AnswerChart chart={bar} rows={rows} metric={{ unitFormat: 'KL' }} />)
    const first = dataOf()[0]
    expect(Object.keys(first).filter(key => !['regional'].includes(key)).sort()).toEqual(['A', 'B', 'C', 'D', 'E', 'Others'])
    expect(first.Others).toBe(50 + 40) // F and G, the two smallest, added together
  })

  it('never stacks a rate: with many series it falls back to one labelled bar per pair', () => {
    const products = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
    const rows = ['Jawa', 'Papua'].flatMap(regional => products.map((produk, j) => ({ regional, produk, metric_value: 10 + j })))
    render(<AnswerChart chart={bar} rows={rows} metric={{ unitFormat: 'percent' }} />)
    expect(screen.queryByRole('button', { name: 'Stacked' })).toBeNull()
    expect(String(dataOf()[0].__category)).toContain(' · ')
  })
})
