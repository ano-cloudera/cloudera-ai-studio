'use client'

/*
 * Home: what the published semantic model says matters, computed from the data, for directors and managers.
 * Design read: executive overview in Cloudera's identity, dial ENERGY 2 / RHYTHM 2 / MOTION 1.
 * - Focal point: the Deep Indigo briefing band at the top, with one Cloudera Orange rule across its top edge as the brand moment.
 * - KPI tiles are one size and one structure. Green and red appear only where the model's author declared which way is good
 *   (or a target); without that a change is neutral grey, because Home does not guess whether up is good.
 * - Electric Indigo draws the data (lines, areas, bars); Cloudera Orange marks the one thing to look at in each block: the latest
 *   point, the group that stands out, the top bar.
 * - Only the KPI tiles are lifted (a soft shadow, and 2px up on hover): they are what is read and clicked first; elevation
 *   elsewhere would say nothing.
 * - Flat bordered cards on the light canvas; no illustration, no sparkle icons, no gradient: the figures are the content.
 * - Motion: each block rises once as it arrives (no fill mode, so a paused animation never hides a figure); none under reduced motion.
 * - Text is English unless the Backend is asked for another language; metric and group names are the model's own words.
 */

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ResultMap } from '../components/analysis/ResultMap'
import { pageCenterClassName } from '../components/PageCenter'
import { api } from '../lib/api'
import { detectGeo } from '../lib/geo'
import { useModelSelection } from '../lib/modelSelection'
import type { HomeBriefing, HomeKpi, HomePayload, HomeRows, HomeStandout } from '../types/api'

type Language = 'id' | 'en'

const ORANGE = '#FF5A1F'
const INDIGO = '#5351F6' // Cloudera Electric Indigo: the colour of data lines and areas
const INDIGO_SOFT = '#d9d8fd'
const INDIGO_WASH = '#ecebfe'
const STORAGE_KEY = 'ai-studio.home.v4'
const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange'
const CARD = 'rounded-2xl border border-slate-200 bg-white'

const TEXT = {
  id: {
    title: 'Ringkasan Bisnis',
    subtitle: 'Yang dinyatakan penting oleh semantic model, dihitung langsung dari data.',
    coverage: 'Periode data',
    updated: 'Dihitung',
    refresh: 'Hitung ulang',
    refreshing: 'Menghitung…',
    briefing: 'Briefing',
    briefingNote: 'Ditulis AI dari angka di halaman ini; setiap angkanya sudah dicek.',
    briefingLoading: 'Menyusun briefing dari angka di bawah…',
    briefingNone: 'Briefing belum tersedia. Angka di bawah tetap terbaru.',
    askNext: 'Tanyakan berikutnya',
    happened: 'Yang terjadi',
    matters: 'Kenapa penting',
    lookNext: 'Yang perlu dicek',
    vs: 'vs',
    overall: 'Seluruh periode data',
    trend: 'Tren bulanan',
    by: 'per',
    map: 'Peta',
    question: 'Tanya data',
    askPlaceholder: 'Contoh: regional mana yang paling sering terlambat bulan ini?',
    ask: 'Tanyakan',
    loading: 'Menghitung angka utama dari data…',
    failed: 'Angka utama belum bisa dimuat. Periksa koneksi ke data source, lalu coba lagi.',
    retry: 'Coba lagi',
    noModel: 'Belum ada semantic model yang dipublikasikan ke Ask Data, jadi belum ada angka untuk ditampilkan.',
    noHome: 'Belum ada metrik yang ditandai untuk Home. Buka Semantic Layer, pilih metrik, lalu isi bagian Home: Show on Home, arah yang baik, dan target.',
    openSemantic: 'Buka Semantic Layer',
    noData: 'Semantic model sudah dipublikasikan, tetapi query angka utamanya belum mengembalikan data.',
    dashed: 'Garis putus-putus',
    targetLine: 'garis hijau',
    points: 'poin',
    up: 'naik',
    down: 'turun',
    inMonth: 'di',
    openTrend: 'Buka tren bulanan di Ask Data',
    unavailable: 'Tidak tersedia',
    standout: 'Paling menonjol',
    fromOverall: 'dari keseluruhan',
    target: 'target',
    improving: 'Membaik',
    worsening: 'Memburuk',
    onTarget: 'Sesuai target',
    aboveTarget: 'Di atas target',
    belowTarget: 'Di bawah target',
  },
  en: {
    title: 'Business Overview',
    subtitle: 'What the semantic model says matters, computed from the data.',
    coverage: 'Data period',
    updated: 'Computed',
    refresh: 'Recompute',
    refreshing: 'Computing…',
    briefing: 'Briefing',
    briefingNote: 'Written by AI from the figures on this page; every figure in it was checked.',
    briefingLoading: 'Writing the briefing from the figures below…',
    briefingNone: 'No briefing yet. The figures below are current.',
    askNext: 'Ask next',
    happened: 'What happened',
    matters: 'Why it matters',
    lookNext: 'What to look at next',
    vs: 'vs',
    overall: 'Whole data period',
    trend: 'Monthly trend',
    by: 'by',
    map: 'Map',
    question: 'Ask your data',
    askPlaceholder: 'For example: which region was late most often this month?',
    ask: 'Ask',
    loading: 'Computing the headline figures from the data…',
    failed: 'The headline figures could not be loaded. Check the data source connection, then try again.',
    retry: 'Try again',
    noModel: 'No semantic model is published to Ask Data yet, so there are no figures to show.',
    noHome: 'No metric is marked for Home yet. In Semantic Layer, open a metric and fill in its Home section: Show on Home, which way is good, and a target.',
    openSemantic: 'Open Semantic Layer',
    noData: 'A semantic model is published, but its headline queries returned no data yet.',
    dashed: 'Dashed line',
    targetLine: 'green line',
    points: 'pts',
    up: 'up',
    down: 'down',
    inMonth: 'in',
    openTrend: 'Open the monthly trend in Ask Data',
    unavailable: 'Not available',
    standout: 'Stands out',
    fromOverall: 'from overall',
    target: 'target',
    improving: 'Improving',
    worsening: 'Worsening',
    onTarget: 'On target',
    aboveTarget: 'Above target',
    belowTarget: 'Below target',
  },
} as const

type Words = (typeof TEXT)[Language]
type Tone = 'good' | 'bad' | 'neutral'

type Cached = { home: HomePayload; briefing: HomeBriefing | null }

function readCached(): Cached | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Cached
    return parsed?.home?.status === 'ok' ? parsed : null
  } catch {
    return null
  }
}

function writeCached(value: Cached): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // a full or blocked storage only means the next visit waits for the figures
  }
}

function locale(language: Language): string {
  return language === 'id' ? 'id-ID' : 'en-US'
}

function number(value: number, language: Language, decimals: number): string {
  return new Intl.NumberFormat(locale(language), { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value)
}

/** A figure in the language of the page, with the unit its metric declares. */
export function formatFigure(value: number | null | undefined, unitFormat: string | null | undefined, unit: string | null | undefined, language: Language): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return TEXT[language].unavailable
  if (unitFormat === 'percent') return `${number(value, language, 1)}%`
  if (unitFormat === 'currency_idr') {
    const steps: [number, string, string][] = [
      [1e12, ' T', 'T'],
      [1e9, ' M', 'B'],
      [1e6, ' jt', 'M'],
    ]
    const step = steps.find(([size]) => Math.abs(value) >= size)
    if (step) return `Rp${number(value / step[0], language, 2)}${language === 'id' ? step[1] : step[2]}`
    return `Rp${number(value, language, 0)}`
  }
  if (unitFormat === 'minutes') return `${number(value, language, 1)} ${language === 'id' ? 'menit' : 'min'}`
  if (unitFormat === 'ratio') return number(value, language, 2)
  const decimals = Math.abs(value) >= 100 || Number.isInteger(value) ? 0 : 1
  const shownUnit = unit && !['percent', '%', 'idr', 'minutes'].includes(unit.toLowerCase()) ? ` ${unit}` : ''
  return `${number(value, language, decimals)}${shownUnit}`
}

function monthLabel(month: string, language: Language): string {
  const [year, index] = month.split('-').map(Number)
  if (!year || !index) return month
  return new Intl.DateTimeFormat(locale(language), { month: 'short', year: 'numeric' }).format(new Date(year, index - 1, 1))
}

function dayLabel(iso: string, language: Language): string {
  const date = new Date(`${iso.slice(0, 10)}T00:00:00`)
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat(locale(language), { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}

function askHref(question: string): string {
  return `/?ask=${encodeURIComponent(question)}`
}

/** Good or bad only when the model says which way is good; otherwise neutral. */
function toneOf(change: number, better: HomeKpi['better']): Tone {
  if (!better || change === 0) return 'neutral'
  return (change > 0) === (better === 'up') ? 'good' : 'bad'
}

const TONE_CHIP: Record<Tone, string> = {
  good: 'bg-emerald-50 text-emerald-800',
  bad: 'bg-rose-50 text-rose-800',
  neutral: 'bg-slate-100 text-slate-700',
}

function changeText(kpi: HomeKpi, language: Language): string | null {
  if (kpi.change === undefined || !kpi.last_month) return null
  if (kpi.unit_format === 'percent') return `${number(Math.abs(kpi.change), language, 1)} ${TEXT[language].points}`
  if (kpi.change_pct === undefined) return null
  return `${number(Math.abs(kpi.change_pct), language, 1)}%`
}

/** The status a tile carries: against its target when it has one, else the direction of the last month, else none. */
export function kpiStatus(kpi: HomeKpi, words: Words): { label: string; tone: Tone } | null {
  if (typeof kpi.target === 'number') {
    const gap = kpi.value - kpi.target
    if (Math.abs(gap) <= Math.abs(kpi.target) * 0.005) return { label: words.onTarget, tone: 'good' }
    const tone: Tone = !kpi.better ? 'neutral' : (gap > 0) === (kpi.better === 'up') ? 'good' : 'bad'
    return { label: gap > 0 ? words.aboveTarget : words.belowTarget, tone }
  }
  if (kpi.better && kpi.change !== undefined && kpi.change !== 0) {
    const tone = toneOf(kpi.change, kpi.better)
    return { label: tone === 'good' ? words.improving : words.worsening, tone }
  }
  return null
}

function lastPoint(total: number) {
  return function Dot(props: { cx?: number; cy?: number; index?: number }) {
    if (props.index !== total - 1 || props.cx === undefined || props.cy === undefined) return <g />
    return <circle cx={props.cx} cy={props.cy} r={4} fill={ORANGE} stroke="#ffffff" strokeWidth={2} />
  }
}

function Sparkline({ kpi }: { kpi: HomeKpi }) {
  if (kpi.series.length < 3) return null
  return (
    <div className="h-14 w-full" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={kpi.series} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Area type="monotone" dataKey="value" stroke={INDIGO} strokeWidth={2} fill={INDIGO_WASH} dot={lastPoint(kpi.series.length)} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function KpiTile({ kpi, language }: { kpi: HomeKpi; language: Language }) {
  const words = TEXT[language]
  const value = formatFigure(kpi.value, kpi.unit_format, kpi.unit, language)
  const change = changeText(kpi, language)
  const tone = kpi.change !== undefined ? toneOf(kpi.change, kpi.better) : 'neutral'
  const status = kpiStatus(kpi, words)
  const rising = (kpi.change ?? 0) >= 0
  const Arrow = rising ? ArrowUp : ArrowDown
  const previous = kpi.previous_month
  const question = language === 'id' ? `Bagaimana tren ${kpi.label} per bulan?` : `How has ${kpi.label} moved by month?`
  const name = [
    `${kpi.label}: ${value}`,
    status?.label ?? '',
    change && kpi.last_month ? `${rising ? words.up : words.down} ${change} ${words.inMonth} ${monthLabel(kpi.last_month.month, language)}` : '',
    words.openTrend,
  ]
    .filter(Boolean)
    .join('. ')
  return (
    <Link
      href={askHref(question)}
      aria-label={name}
      title={kpi.description || undefined}
      className={`${CARD} flex min-h-[11.5rem] flex-col p-5 shadow-[0_1px_2px_rgba(19,0,61,0.06),0_8px_20px_-6px_rgba(19,0,61,0.14)] transition duration-150 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_2px_4px_rgba(19,0,61,0.08),0_14px_28px_-8px_rgba(19,0,61,0.2)] active:translate-y-0 motion-reduce:transform-none ${FOCUS}`}
      data-testid="home-kpi"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-semibold text-slate-700">{kpi.label}</div>
        {status && <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold ${TONE_CHIP[status.tone]}`}>{status.label}</span>}
      </div>
      <div className="mt-2 flex flex-1 flex-col">
        <div className="min-w-0">
          <div className="break-words text-[2rem] font-black leading-tight tracking-tight tabular-nums text-cloudera-navy">{value}</div>
          {change && kpi.last_month ? (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
              <span className={`inline-flex items-center gap-0.5 whitespace-nowrap rounded-md px-1.5 py-0.5 font-semibold tabular-nums ${TONE_CHIP[tone]}`}>
                <Arrow size={12} aria-hidden />
                {change}
              </span>
              <span className="whitespace-nowrap">{monthLabel(kpi.last_month.month, language)}</span>
            </div>
          ) : (
            <div className="mt-2 text-xs text-slate-600">{words.overall}</div>
          )}
          {previous && (
            <div className="mt-1 text-xs text-slate-600">
              {words.vs} {monthLabel(previous.month, language)} ({formatFigure(previous.value, kpi.unit_format, kpi.unit, language)})
              {typeof kpi.target === 'number' && ` · ${words.target} ${formatFigure(kpi.target, kpi.unit_format, kpi.unit, language)}`}
            </div>
          )}
        </div>
        <div className="mt-auto pt-3">
          <Sparkline kpi={kpi} />
        </div>
      </div>
    </Link>
  )
}

function tileGrid(count: number): string {
  if (count >= 4) return 'sm:grid-cols-2 xl:grid-cols-4'
  if (count === 3) return 'lg:grid-cols-3'
  if (count === 2) return 'sm:grid-cols-2'
  return ''
}

/** The focal band: the headline of the briefing, and the questions it suggests asking next. */
function BriefingBand({ briefing, loading, words }: { briefing: HomeBriefing | null; loading: boolean; words: Words }) {
  const ready = briefing?.status === 'ok'
  return (
    <section className="home-rise overflow-hidden rounded-2xl bg-cloudera-navy text-white" aria-labelledby="home-briefing-title" data-testid="home-briefing">
      <div className="h-1 bg-cloudera-orange" aria-hidden />
      <div className="grid gap-6 px-6 py-6 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)]">
        <div>
          <h2 id="home-briefing-title" className="text-sm font-semibold text-white/90">
            {words.briefing}
          </h2>
          {loading && !briefing && (
            <div role="status" className="mt-3 space-y-2">
              <p className="text-sm text-white/90">{words.briefingLoading}</p>
              <div className="home-placeholder h-5 w-3/4 rounded bg-white/15" />
            </div>
          )}
          {!loading && !ready && <p className="mt-3 text-sm text-white/90">{words.briefingNone}</p>}
          {ready && <p className="mt-2 max-w-4xl text-balance text-2xl font-semibold leading-snug">{briefing.headline}</p>}
          <p className="mt-4 text-xs text-white/75">{words.briefingNote}</p>
        </div>
        {ready && (briefing.ask_next ?? []).length > 0 && (
          <div className="lg:border-l lg:border-white/15 lg:pl-6">
            <h3 className="text-sm font-semibold text-white/90">{words.askNext}</h3>
            <ul className="mt-3 space-y-2">
              {(briefing.ask_next ?? []).map(item => (
                <li key={item}>
                  <Link
                    href={askHref(item)}
                    className="block rounded-lg border border-white/25 px-3 py-2 text-sm text-white transition-colors hover:bg-white/10 active:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                  >
                    {item}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}

/** The briefing's body in three parts: what moved, what it means, what to check. */
function BriefingDetail({ briefing, words }: { briefing: HomeBriefing | null; words: Words }) {
  if (briefing?.status !== 'ok') return null
  const parts: [string, ReactNode][] = []
  if (briefing.what_happened) parts.push([words.happened, <p key="h">{briefing.what_happened}</p>])
  if (briefing.why_it_matters) parts.push([words.matters, <p key="m">{briefing.why_it_matters}</p>])
  if ((briefing.look_next ?? []).length)
    parts.push([
      words.lookNext,
      <ul key="l" className="space-y-1.5">
        {(briefing.look_next ?? []).map(item => (
          <li key={item} className="flex gap-2">
            <span className="mt-[0.55em] h-1.5 w-1.5 shrink-0 rounded-full bg-cloudera-orange" aria-hidden />
            <span>{item}</span>
          </li>
        ))}
      </ul>,
    ])
  if (!parts.length) return null
  return (
    <section className={`home-rise home-rise-1 h-full ${CARD} p-5`} aria-label={words.briefing} data-testid="home-briefing-detail">
      <div className={`grid gap-5 md:divide-x md:divide-slate-100 ${parts.length === 3 ? 'md:grid-cols-3' : parts.length === 2 ? 'md:grid-cols-2' : ''}`}>
        {parts.map(([title, body], index) => (
          <div key={title} className={index ? 'md:pl-5' : ''}>
            <h3 className="text-sm font-bold text-cloudera-navy">{title}</h3>
            <div className="mt-2 text-sm leading-relaxed text-slate-700">{body}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

/** The groups or places furthest from the overall value of the main KPI, in the worse direction when the model says which. */
function StandoutCard({ standout, language }: { standout: HomeStandout; language: Language }) {
  const words = TEXT[language]
  const [first, ...rest] = standout.groups
  if (!first) return null
  const format = (value: number) => formatFigure(value, standout.unit_format, standout.unit, language)
  const gap = (difference: number) =>
    standout.unit_format === 'percent'
      ? `${difference > 0 ? '+' : '−'}${number(Math.abs(difference), language, 1)} ${words.points}`
      : `${difference > 0 ? '+' : '−'}${formatFigure(Math.abs(difference), standout.unit_format, standout.unit, language)}`
  const worse = Boolean(standout.better)
  return (
    <section className={`home-rise home-rise-1 ${CARD} p-5`} aria-labelledby="home-standout-title" data-testid="home-standout">
      <h2 id="home-standout-title" className="text-sm font-bold text-cloudera-navy">
        {words.standout}
      </h2>
      <p className="text-xs text-slate-600">
        {standout.label} {words.by} {standout.by}
      </p>
      <div className={`mt-3 rounded-xl border p-4 ${worse ? 'border-rose-200 bg-rose-50/60' : 'border-slate-200 bg-slate-50'}`}>
        <div className="text-base font-semibold text-slate-900">{first.group}</div>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
          <span className={`text-3xl font-black tabular-nums ${worse ? 'text-rose-700' : 'text-cloudera-navy'}`}>{format(first.value)}</span>
          <span className="text-sm font-semibold tabular-nums text-slate-700">{gap(first.difference)}</span>
        </div>
        <div className="mt-1 text-xs text-slate-600">
          {words.fromOverall} {format(standout.overall_value)}
        </div>
      </div>
      {rest.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {rest.map(item => (
            <li key={item.group} className="flex items-center justify-between gap-3 py-2">
              <span className="text-slate-800">{item.group}</span>
              <span className="tabular-nums text-slate-700">
                {format(item.value)} <span className="text-xs text-slate-600">({gap(item.difference)})</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function TrendCard({ kpis, language, className }: { kpis: HomeKpi[]; language: Language; className: string }) {
  const words = TEXT[language]
  const withSeries = kpis.filter(kpi => kpi.series.length >= 2)
  const [chosen, setChosen] = useState(withSeries[0]?.metric ?? '')
  const kpi = withSeries.find(item => item.metric === chosen) ?? withSeries[0]
  if (!kpi) return null
  const data = kpi.series.map(point => ({ ...point, label: monthLabel(point.month, language) }))
  const format = (value: number) => formatFigure(value, kpi.unit_format, kpi.unit, language)
  const last = data[data.length - 1]
  return (
    <section className={`home-rise home-rise-2 ${CARD} p-5 ${className}`} aria-labelledby="home-trend-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="home-trend-title" className="text-base font-bold text-cloudera-navy">
          {words.trend}: {kpi.label}
        </h2>
        {withSeries.length > 1 && (
          <div role="tablist" aria-label={words.trend} className="inline-flex flex-wrap rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            {withSeries.map(item => (
              <button
                key={item.metric}
                role="tab"
                type="button"
                aria-selected={item.metric === kpi.metric}
                onClick={() => setChosen(item.metric)}
                className={`min-h-9 rounded-md px-3 text-xs font-semibold transition-colors ${FOCUS} ${
                  item.metric === kpi.metric ? 'bg-cloudera-navy text-white' : 'text-slate-700 hover:text-cloudera-navy'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="mt-3 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 24, right: 28, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#eef0f5" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} interval="preserveStartEnd" tickMargin={10} height={32} />
            <YAxis tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} width={72} domain={['auto', 'auto']} padding={{ top: 8, bottom: 8 }} tickFormatter={value => format(Number(value))} />
            <Tooltip formatter={value => format(Number(value))} />
            <ReferenceLine y={kpi.value} stroke="#64748b" strokeDasharray="4 4" />
            {typeof kpi.target === 'number' && <ReferenceLine y={kpi.target} stroke="#059669" strokeDasharray="2 4" />}
            <Line
              type="monotone"
              dataKey="value"
              name={kpi.label}
              stroke={INDIGO}
              strokeWidth={2.5}
              dot={lastPoint(data.length)}
              isAnimationActive={false}
              label={(props: { x?: number | string; y?: number | string; index?: number }) =>
                props.index === data.length - 1 && props.x !== undefined && props.y !== undefined ? (
                  <text x={Number(props.x)} y={Number(props.y) - 12} textAnchor="end" fill="#15084A" fontSize={12} fontWeight={700}>
                    {format(last.value)}
                  </text>
                ) : (
                  <g />
                )
              }
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-slate-600">
        {words.dashed}: {words.overall.toLowerCase()} {format(kpi.value)}
        {typeof kpi.target === 'number' && ` · ${words.targetLine}: ${words.target} ${format(kpi.target)}`}
      </p>
    </section>
  )
}

function groupColumn(block: HomeRows): string | null {
  return block.columns.find(column => column !== 'metric_value') ?? null
}

function BreakdownCard({ block, language }: { block: HomeRows; language: Language }) {
  const words = TEXT[language]
  const column = groupColumn(block)
  const rows = useMemo(
    () =>
      column
        ? block.rows
            .map(row => ({ name: String(row[column] ?? ''), value: Number(row.metric_value) }))
            .filter(row => row.name && Number.isFinite(row.value))
            .sort((a, b) => b.value - a.value)
        : [],
    [block.rows, column],
  )
  if (!column || rows.length === 0) return null
  const by = block.column_labels[column] || column
  const top = rows[0]?.value ?? 0
  const format = (value: number) => formatFigure(value, block.unit_format, block.unit, language)
  return (
    <section className={`home-rise home-rise-3 ${CARD} p-5`} aria-labelledby="home-breakdown-title">
      <h2 id="home-breakdown-title" className="text-base font-bold text-cloudera-navy">
        {block.label} {words.by} {by}
      </h2>
      <div className="mt-3" style={{ height: Math.max(220, rows.length * 32) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 8 }}>
            <XAxis type="number" hide domain={[0, 'auto']} />
            <YAxis type="category" dataKey="name" width={124} tick={{ fontSize: 12, fill: '#334155' }} tickLine={false} axisLine={false} />
            <Tooltip formatter={value => format(Number(value))} />
            {typeof block.overall_value === 'number' && <ReferenceLine x={block.overall_value} stroke="#64748b" strokeDasharray="4 4" />}
            <Bar
              dataKey="value"
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
              label={{ position: 'right', fontSize: 11, fill: '#334155', formatter: (value: unknown) => format(Number(value)) }}
            >
              {rows.map(row => (
                <Cell key={row.name} fill={row.value === top ? ORANGE : INDIGO_SOFT} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {typeof block.overall_value === 'number' && (
        <p className="mt-2 text-xs text-slate-600">
          {words.dashed}: {words.overall.toLowerCase()} {format(block.overall_value)}
        </p>
      )}
    </section>
  )
}

function MapCard({ block, language }: { block: HomeRows; language: Language }) {
  const detection = useMemo(() => detectGeo(block.columns, block.rows, block.geo_points), [block])
  if (!detection) return null
  const column = detection.geoColumn
  return (
    <section className={`home-rise home-rise-3 ${CARD} p-5`} aria-labelledby="home-map-title" data-testid="home-map">
      <h2 id="home-map-title" className="mb-3 text-base font-bold text-cloudera-navy">
        {TEXT[language].map}: {block.label} {TEXT[language].by} {block.column_labels[column] || column}
      </h2>
      <ResultMap
        columns={block.columns}
        rows={block.rows}
        detection={detection}
        metric={block.metric}
        unitFormat={block.unit_format ?? undefined}
        formatValue={value => formatFigure(value, block.unit_format, block.unit, language)}
        language={language}
      />
    </section>
  )
}

function Placeholder({ words }: { words: Words }) {
  const block = `home-placeholder ${CARD}`
  return (
    <div role="status" aria-live="polite" className="space-y-5">
      <p className="text-sm text-slate-600">{words.loading}</p>
      <div className="home-placeholder h-36 rounded-2xl bg-cloudera-navy/10" aria-hidden />
      <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
        <div className={`${block} h-48`} />
        <div className={`${block} h-48`} />
        <div className={`${block} h-48`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
        <div className={`${block} h-72 lg:col-span-2`} />
        <div className={`${block} h-72`} />
      </div>
    </div>
  )
}

export function HomePage() {
  const router = useRouter()
  const { selection } = useModelSelection()
  const [home, setHome] = useState<HomePayload | null>(null)
  const [briefing, setBriefing] = useState<HomeBriefing | null>(null)
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [briefingLoading, setBriefingLoading] = useState(false)
  const [question, setQuestion] = useState('')

  useEffect(() => {
    const cached = readCached()
    if (cached) {
      setHome(cached.home)
      setBriefing(cached.briefing)
    }
  }, [])

  const load = useCallback(
    (refresh = false) => {
      setFailed(false)
      setLoading(true)
      setBriefingLoading(true)
      const figures = api.home(selection, refresh)
      const written = api.homeBriefing(selection, refresh)
      figures
        .then(payload => {
          setHome(payload)
          if (payload.status !== 'ok') setBriefing(null)
          return written.then(
            next => {
              setBriefing(next)
              if (payload.status === 'ok') writeCached({ home: payload, briefing: next })
            },
            () => {
              setBriefing(current => current ?? { status: 'failed' })
              if (payload.status === 'ok') writeCached({ home: payload, briefing: null })
            },
          )
        })
        .catch(() => setFailed(true))
        .finally(() => {
          setLoading(false)
          setBriefingLoading(false)
        })
    },
    [selection],
  )

  useEffect(() => {
    if (selection) load(false)
  }, [selection, load])

  const language: Language = home?.language === 'id' ? 'id' : 'en'
  const words = TEXT[language]
  const onAsk = (event: FormEvent) => {
    event.preventDefault()
    if (question.trim()) router.push(askHref(question.trim()))
  }
  const coverage =
    home?.data_coverage?.first && home?.data_coverage?.last
      ? `${dayLabel(home.data_coverage.first, language)} – ${dayLabel(home.data_coverage.last, language)}`
      : null
  const hasDetail = briefing?.status === 'ok' && Boolean(briefing.what_happened || briefing.why_it_matters || (briefing.look_next ?? []).length)

  return (
    <div className={pageCenterClassName('space-y-5')} data-testid="home-page">
      <header className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(24rem,36rem)] xl:items-end">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-cloudera-navy">{words.title}</h1>
          <p className="mt-1 text-sm text-slate-600">{words.subtitle}</p>
          {(coverage || home?.computed_at) && (
            <p className="mt-1 text-xs text-slate-600">
              {coverage && (
                <span>
                  {words.coverage}: {coverage}
                </span>
              )}
              {coverage && home?.computed_at && <span aria-hidden> · </span>}
              {home?.computed_at && (
                <span>
                  {words.updated}{' '}
                  {new Intl.DateTimeFormat(locale(language), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(home.computed_at))}
                </span>
              )}
            </p>
          )}
        </div>
        <div className="flex items-end gap-2">
          <form onSubmit={onAsk} role="search" className="min-w-0 flex-1">
            <label htmlFor="home-question" className="mb-1 block text-xs font-semibold text-slate-700">
              {words.question}
            </label>
            <div className="flex gap-2">
              <input
                id="home-question"
                value={question}
                onChange={event => setQuestion(event.target.value)}
                placeholder={words.askPlaceholder}
                className="min-h-11 min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800 placeholder:text-slate-500 focus-visible:border-cloudera-orange focus-visible:outline focus-visible:outline-2 focus-visible:outline-cloudera-orange/40"
              />
              <button
                type="submit"
                disabled={!question.trim()}
                className={`min-h-11 rounded-lg bg-cloudera-orange px-4 text-sm font-semibold text-white transition-colors hover:bg-[#e94e14] active:bg-[#d24510] disabled:opacity-50 ${FOCUS}`}
              >
                {words.ask}
              </button>
            </div>
          </form>
          <button
            type="button"
            onClick={() => load(true)}
            disabled={loading || !selection}
            className={`min-h-11 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-400 hover:text-cloudera-navy active:bg-slate-50 disabled:opacity-60 ${FOCUS}`}
          >
            {loading ? words.refreshing : words.refresh}
          </button>
        </div>
      </header>

      {failed && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" role="alert">
          <span>{words.failed}</span>
          <button type="button" onClick={() => load(true)} className={`min-h-11 rounded-lg border border-rose-300 bg-white px-4 font-semibold text-rose-900 hover:bg-rose-100 ${FOCUS}`}>
            {words.retry}
          </button>
        </div>
      )}

      {!failed && !home && <Placeholder words={words} />}

      {(home?.status === 'no_model' || home?.status === 'no_home_metrics') && (
        <div className={`${CARD} p-6 text-sm text-slate-700`}>
          <p>{home.status === 'no_model' ? words.noModel : words.noHome}</p>
          <Link href="/semantic-layer" className={`mt-2 inline-block font-semibold text-cloudera-navy underline underline-offset-2 ${FOCUS}`}>
            {words.openSemantic}
          </Link>
        </div>
      )}
      {home?.status === 'no_data' && <div className={`${CARD} p-6 text-sm text-slate-700`}>{words.noData}</div>}

      {home?.status === 'ok' && (
        <>
          <BriefingBand briefing={briefing} loading={briefingLoading} words={words} />
          <div className={`home-rise grid gap-4 ${tileGrid(home.kpis.length)}`}>
            {home.kpis.map(kpi => (
              <KpiTile key={kpi.metric} kpi={kpi} language={language} />
            ))}
          </div>
          {(hasDetail || home.standout) && (
            <div className="grid gap-4 lg:grid-cols-3">
              {hasDetail && (
                <div className={home.standout ? 'lg:col-span-2' : 'lg:col-span-3'}>
                  <BriefingDetail briefing={briefing} words={words} />
                </div>
              )}
              {home.standout && (
                <div className={hasDetail ? '' : 'lg:col-span-3'}>
                  <StandoutCard standout={home.standout} language={language} />
                </div>
              )}
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-3">
            <TrendCard kpis={home.kpis} language={language} className={home.breakdown ? 'lg:col-span-2' : 'lg:col-span-3'} />
            {home.breakdown && <BreakdownCard block={home.breakdown} language={language} />}
          </div>
          {home.map && <MapCard block={home.map} language={language} />}
        </>
      )}
    </div>
  )
}
