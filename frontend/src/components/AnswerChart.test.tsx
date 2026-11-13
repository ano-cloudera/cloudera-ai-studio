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
    Bar: ({ dataKey, maxBarSize }: { dataKey?: string; maxBarSize?: number }) => <div data-testid="bar" data-key={dataKey} data-max-size={maxBarSize} />, Area: () => null, Line: () => null,
    ComposedChart: container, LabelList: () => null, ReferenceLine: () => null,
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

  it('allows automatic tick skipping for long rankings', () => {
    render(<AnswerChart chart={{ type: 'bar', title: 'Product ranking', x: 'material', y: 'metric_value' }} rows={
      Array.from({ length: 50 }, (_, index) => ({ material: `very-long-material-label-${index}`, metric_value: 50 - index }))
    } />)

    expect(screen.getByTestId('x-axis').getAttribute('data-interval')).toBe('0')
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
})
