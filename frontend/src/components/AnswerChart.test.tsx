import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
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

  it('allows automatic tick skipping for long rankings', () => {
    render(<AnswerChart chart={{ type: 'bar', title: 'Product ranking', x: 'material', y: 'metric_value' }} rows={
      Array.from({ length: 50 }, (_, index) => ({ material: `very-long-material-label-${index}`, metric_value: 50 - index }))
    } />)

    expect(screen.getByTestId('x-axis').getAttribute('data-interval')).toBe('0')
  })
})
