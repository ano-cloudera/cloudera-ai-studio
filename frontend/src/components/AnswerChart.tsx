import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import type { ChartSpec } from '../types/api'
import { truncateAxisLabel } from '../lib/answerFormatting'
import {
  compareTimeAxisValues,
  formatBusinessLabel,
  formatTimeAxisLabel,
  isTimeAxisField,
} from '../lib/businessPresentation'
import { ASSISTANT_CHART_CLASS } from './ConversationInner'

const COLORS = ['#FF5A1F', '#635BFF', '#3EBAA5', '#9A8CFF']
const tick = { fontSize: 11, fill: '#64748B' }
const CHART_MARGIN_DENSE_BOTTOM = 88
const CHART_MARGIN_DENSE_BOTTOM_EMBEDDED = 44
const CHART_MARGIN_DEFAULT_BOTTOM = 52
const CHART_MARGIN_DEFAULT_BOTTOM_EMBEDDED = 32
/** Extra headroom above tallest bar/line so values do not touch the chart top. */
const Y_AXIS_HEADROOM = 1.2

function formatAxisNumber(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(abs % 1_000_000_000 === 0 ? 0 : 1)}B`
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(abs % 1_000_000 === 0 ? 0 : 1)}M`
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs % 1_000 === 0 ? 0 : 1)}K`
  return String(value)
}

function formatTooltipValue(value: unknown): string {
  return typeof value === 'number' ? value.toLocaleString('id-ID') : String(value ?? '')
}

export function AnswerChart({
  chart,
  rows,
  className = '',
  embedded = false,
  hideTitle = false,
}: {
  chart: ChartSpec | null
  rows: Record<string, unknown>[]
  className?: string
  /** Render inside a parent card (no outer answer-surface). */
  embedded?: boolean
  hideTitle?: boolean
}) {
  if (!chart || chart.type === 'table' || chart.type === 'kpi' || !chart.x || !chart.y || !rows.length) return null
  const seriesNames = chart.series ? [...new Set(rows.map(row => String(row[chart.series!] ?? 'Unknown')))] : []
  const flattenRankingSeries = chart.type === 'bar' && Boolean(chart.series) && rows.length > 1 && seriesNames.length === rows.length
  const xKey = flattenRankingSeries ? '__category' : chart.x
  const visibleSeriesNames = flattenRankingSeries ? [] : seriesNames
  const yField = chart.y!
  const coerceY = (value: unknown): number | null => {
    if (value === null || value === undefined || value === '') return null
    if (typeof value === 'number' && Number.isFinite(value)) return value
    const parsed = Number(String(value).replace(/,/g, ''))
    return Number.isFinite(parsed) ? parsed : null
  }
  const rawYValues = rows.map(row => coerceY(row[yField])).filter((v): v is number => v !== null)
  const plausibleY = rawYValues.filter(v => v >= 0 && v < 1e12)
  const maxY = (plausibleY.length ? plausibleY : rawYValues).length
    ? Math.max(...(plausibleY.length ? plausibleY : rawYValues))
    : 0
  const scaleRatioToPercent =
    chart.type === 'bar' &&
    yField === 'metric_value' &&
    rawYValues.every(value => value >= 0 && value <= 1.5) &&
    (maxY <= 1 || /fill rate|service level|sl\b/i.test(chart.title))
  const toDisplayY = (value: unknown) => {
    const numeric = coerceY(value) ?? 0
    return scaleRatioToPercent ? numeric * 100 : numeric
  }
  let data = flattenRankingSeries
    ? rows.map(row => ({ ...row, __category: `${String(row[chart.x!] ?? '')} · ${String(row[chart.series!] ?? 'Unknown')}`, [yField]: toDisplayY(row[yField]) }))
    : seriesNames.length
    ? [...rows.reduce((groups, row) => {
        const category = String(row[chart.x!] ?? '')
        const point = groups.get(category) || { [chart.x!]: row[chart.x!] }
        point[String(row[chart.series!] ?? 'Unknown')] = toDisplayY(row[chart.y!])
        groups.set(category, point)
        return groups
      }, new Map<string, Record<string, unknown>>()).values()]
    : rows.map(row => ({ ...row, [yField]: toDisplayY(row[yField]) }))
  const timeOnX = isTimeAxisField(chart.x ?? '')
  if (timeOnX && data.length > 1) {
    data = [...data].sort((left, right) =>
      compareTimeAxisValues(left[chart.x!], right[chart.x!]),
    )
    data = data.map(row => ({
      ...row,
      __time_tick:
        formatTimeAxisLabel(row[chart.x!]) ??
        truncateAxisLabel(String(row[chart.x!] ?? ''), 16),
    }))
  }
  const displayXKey = timeOnX ? '__time_tick' : xKey
  const categoryCount = data.length
  const denseTimeAxis =
    timeOnX && (chart.type === 'line' || chart.type === 'area') && categoryCount >= 4
  const denseBarCategories = chart.type === 'bar' && categoryCount >= 6
  const denseCategories = denseBarCategories || denseTimeAxis
  const chartMargin = {
    top: embedded ? 8 : 12,
    right: 16,
    bottom: denseTimeAxis
      ? embedded
        ? 24
        : 36
      : denseBarCategories
        ? embedded
          ? CHART_MARGIN_DENSE_BOTTOM_EMBEDDED
          : CHART_MARGIN_DENSE_BOTTOM
        : embedded
          ? CHART_MARGIN_DEFAULT_BOTTOM_EMBEDDED
          : CHART_MARGIN_DEFAULT_BOTTOM,
    left: 4,
  }
  const keys = visibleSeriesNames.length ? visibleSeriesNames : [yField]
  const yHeadroom = denseTimeAxis ? 1.1 : Y_AXIS_HEADROOM
  const yCeiling =
    maxY > 0 ? Math.ceil(maxY * yHeadroom) : scaleRatioToPercent ? 100 : 1
  const yDomain: [number, number] = scaleRatioToPercent
    ? [0, Math.min(100, yCeiling)]
    : [0, yCeiling]

  const xTickInterval = denseTimeAxis
    ? Math.max(0, Math.floor(categoryCount / 6) - 1)
    : denseCategories
      ? 0
      : 'preserveStartEnd'

  const xTickProps = denseTimeAxis
    ? { ...tick, dy: 4 }
    : denseCategories
      ? { ...tick, dy: 6 }
      : tick

  const xAxis = (
    <XAxis
      dataKey={displayXKey}
      tick={xTickProps}
      axisLine={false}
      tickLine={false}
      interval={xTickInterval}
      minTickGap={denseTimeAxis ? 28 : denseCategories ? 0 : 24}
      height={
        denseTimeAxis
          ? embedded
            ? 36
            : 44
          : denseBarCategories
            ? embedded
              ? 48
              : 76
            : embedded
              ? 36
              : 48
      }
      angle={denseTimeAxis ? -28 : denseBarCategories ? -32 : 0}
      textAnchor={denseCategories ? 'end' : 'middle'}
      padding={{ left: 8, right: 8 }}
      tickFormatter={value => {
        if (timeOnX) {
          return truncateAxisLabel(String(value), denseCategories ? 14 : 18)
        }
        return truncateAxisLabel(value, denseCategories ? 18 : 24)
      }}
    />
  )
  const axes = (
    <>
      <CartesianGrid vertical={false} stroke="#E7E8F0" />
      {xAxis}
      <YAxis
        tick={tick}
        axisLine={false}
        tickLine={false}
        width={56}
        tickFormatter={formatAxisNumber}
        domain={yDomain}
      />
      <Tooltip
        formatter={formatTooltipValue}
        labelFormatter={label =>
          timeOnX ? formatTimeAxisLabel(label) ?? String(label) : String(label)
        }
      />
      {visibleSeriesNames.length > 0 && <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />}
    </>
  )
  const chartHeight = denseCategories
    ? embedded
      ? 'h-[16.1rem]'
      : 'h-[25.3rem]'
    : embedded
      ? 'h-[14.95rem]'
      : 'h-[20.7rem]'
  const body = (
    <>
      {!hideTitle && (
        <div className={`${embedded ? 'answer-chart-title mb-1.5' : 'text-sm font-semibold text-cloudera-navy mb-4'}`}>
          {chart.title}
        </div>
      )}
      <div className={chartHeight}>
        <ResponsiveContainer width="100%" height="100%">
    {chart.type === 'bar' ? <BarChart data={data} margin={chartMargin}>{axes}{keys.map((key, index) => <Bar key={key} dataKey={key} fill={COLORS[index % COLORS.length]} radius={[6, 6, 0, 0]} maxBarSize={54} />)}</BarChart>
      : chart.type === 'area' ? <AreaChart data={data} margin={chartMargin}>{axes}{keys.map((key, index) => <Area key={key} dataKey={key} stroke={COLORS[index % COLORS.length]} fill={COLORS[index % COLORS.length]} fillOpacity={0.12} />)}</AreaChart>
      : chart.type === 'scatter' ? <ScatterChart margin={chartMargin}><CartesianGrid vertical={false} stroke="#E7E8F0" /><XAxis type="number" dataKey={chart.x} name={chart.x} tick={tick} /><YAxis type="number" dataKey={chart.y} name={chart.y} tick={tick} width={56} tickFormatter={formatAxisNumber} /><Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={formatTooltipValue} />{chart.series ? seriesNames.map((name, index) => <Scatter key={name} name={name} data={rows.filter(row => String(row[chart.series!] ?? 'Unknown') === name)} fill={COLORS[index % COLORS.length]} />) : <Scatter data={data} fill={COLORS[2]} />}{chart.series && <Legend wrapperStyle={{ fontSize: 11 }} />}</ScatterChart>
      : chart.type === 'pie' ? <PieChart margin={{ bottom: 16 }}><Pie data={data} dataKey={chart.y} nameKey={chart.x} innerRadius={52} outerRadius={88}>{data.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}</Pie><Tooltip formatter={formatTooltipValue} /><Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, paddingTop: 8 }} /></PieChart>
      : <LineChart data={data} margin={chartMargin}>{axes}{keys.map((key, index) => (
            <Line
              key={key}
              dataKey={key}
              name={key === 'metric_value' ? formatBusinessLabel(chart.title || 'Nilai') : formatBusinessLabel(key)}
              stroke={COLORS[index % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          ))}</LineChart>}
        </ResponsiveContainer>
      </div>
    </>
  )

  if (embedded) {
    return (
      <div className={`${ASSISTANT_CHART_CLASS} ${className}`.trim()} data-pdf-export-chart>
        {body}
      </div>
    )
  }

  return (
    <div className={`answer-surface pb-6 ${ASSISTANT_CHART_CLASS} ${className}`.trim()} data-pdf-export-chart>
      {body}
    </div>
  )
}
