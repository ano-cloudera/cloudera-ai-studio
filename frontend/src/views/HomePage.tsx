'use client'

/*
 * Home: the headline figures of the published semantic model for directors and managers.
 * Design read: business overview, calm data-product language. Dial ENERGY 1 / RHYTHM 2 / MOTION 1.
 * - KPI tiles are one size and one structure, so they compare at a glance; the focal point is the navy briefing below them.
 * - One accent: the product orange marks the latest point of each sparkline, the trend line and the top group, nothing else.
 * - Flat bordered cards (no shadow): the page is read, not stacked; elevation would say nothing here.
 * - Motion: each section rises once as its figures arrive, so late sections do not jump the page; none under reduced motion.
 * - The page is in English unless the Backend is asked for another language; figures follow that language and carry the unit
 *   the metric declares (16.1%, 4,996,168 KL). Metric and group names are the semantic model's own words.
 */

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ResultMap } from '../components/analysis/ResultMap'
import { pageCenterClassName } from '../components/PageCenter'
import { api } from '../lib/api'
import { detectGeo } from '../lib/geo'
import { useModelSelection } from '../lib/modelSelection'
import type { HomeBriefing, HomeKpi, HomePayload, HomeRows } from '../types/api'

type Language = 'id' | 'en'

const ACCENT = '#FF5A1F'
const MUTED_BAR = '#cbd5e1'
const NAVY = '#15084A'
const STORAGE_KEY = 'ai-studio.home.v3'
const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange'

const TEXT = {
  id: {
    title: 'Ringkasan Bisnis',
    subtitle: 'Angka utama dari semantic model, dihitung langsung dari data.',
    coverage: 'Periode data',
    updated: 'Dihitung',
    refresh: 'Hitung ulang',
    refreshing: 'Menghitung…',
    briefing: 'Briefing',
    briefingNote: 'Ditulis AI dari angka di halaman ini; setiap angkanya sudah dicek.',
    briefingLoading: 'Menyusun briefing dari angka di bawah…',
    briefingNone: 'Briefing belum tersedia. Angka di bawah tetap terbaru.',
    vsPrevious: 'vs bulan sebelumnya',
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
    openSemantic: 'Buka Semantic Layer',
    noData: 'Semantic model sudah dipublikasikan, tetapi query angka utamanya belum mengembalikan data.',
    dashed: 'Garis putus-putus',
    points: 'poin',
    openTrend: 'Buka tren bulanan di Ask Data',
    unavailable: 'Tidak tersedia',
  },
  en: {
    title: 'Business Overview',
    subtitle: 'The headline figures of the semantic model, computed from the data.',
    coverage: 'Data period',
    updated: 'Computed',
    refresh: 'Recompute',
    refreshing: 'Computing…',
    briefing: 'Briefing',
    briefingNote: 'Written by AI from the figures on this page; every figure in it was checked.',
    briefingLoading: 'Writing the briefing from the figures below…',
    briefingNone: 'No briefing yet. The figures below are current.',
    vsPrevious: 'vs previous month',
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
    openSemantic: 'Open Semantic Layer',
    noData: 'A semantic model is published, but its headline queries returned no data yet.',
    dashed: 'Dashed line',
    points: 'pts',
    openTrend: 'Open the monthly trend in Ask Data',
    unavailable: 'Not available',
  },
} as const

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

function changeText(kpi: HomeKpi, language: Language): string | null {
  if (kpi.change === undefined || !kpi.last_month) return null
  const sign = kpi.change >= 0 ? '+' : '−'
  if (kpi.unit_format === 'percent') return `${sign}${number(Math.abs(kpi.change), language, 1)} ${TEXT[language].points}`
  if (kpi.change_pct === undefined) return null
  return `${sign}${number(Math.abs(kpi.change_pct), language, 1)}%`
}

function Change({ kpi, language }: { kpi: HomeKpi; language: Language }) {
  const text = changeText(kpi, language)
  if (!text || !kpi.last_month) return null
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
      <span className="whitespace-nowrap rounded-md bg-slate-100 px-2 py-0.5 font-semibold tabular-nums text-slate-800">{text}</span>
      <span>
        {monthLabel(kpi.last_month.month, language)} {TEXT[language].vsPrevious}
      </span>
    </p>
  )
}

/** The latest month is the one the change is about, so it alone carries the accent. */
function lastPoint(total: number) {
  return function Dot(props: { cx?: number; cy?: number; index?: number }) {
    if (props.index !== total - 1 || props.cx === undefined || props.cy === undefined) return <g />
    return <circle cx={props.cx} cy={props.cy} r={4} fill={ACCENT} stroke="#ffffff" strokeWidth={2} />
  }
}

function Sparkline({ kpi }: { kpi: HomeKpi }) {
  if (kpi.series.length < 3) return <div className="mt-4 h-16" aria-hidden />
  return (
    <div className="mt-4 h-16" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={kpi.series} margin={{ top: 8, right: 8, bottom: 2, left: 8 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Area type="monotone" dataKey="value" stroke={NAVY} strokeWidth={1.75} fill="#eceef7" dot={lastPoint(kpi.series.length)} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function KpiTile({ kpi, language }: { kpi: HomeKpi; language: Language }) {
  const text = TEXT[language]
  const value = formatFigure(kpi.value, kpi.unit_format, kpi.unit, language)
  const change = changeText(kpi, language)
  const question = language === 'id' ? `Bagaimana tren ${kpi.label} per bulan?` : `How has ${kpi.label} moved by month?`
  const name = [`${kpi.label}: ${value}`, change && kpi.last_month ? `${change} ${monthLabel(kpi.last_month.month, language)} ${text.vsPrevious}` : '', text.openTrend]
    .filter(Boolean)
    .join('. ')
  return (
    <Link
      href={askHref(question)}
      aria-label={name}
      title={kpi.description || undefined}
      className={`flex min-h-[15rem] flex-col rounded-2xl border border-slate-200 bg-white p-5 transition-colors hover:border-slate-400 active:bg-slate-50 ${FOCUS}`}
      data-testid="home-kpi"
    >
      <div className="text-sm font-semibold text-slate-700">{kpi.label}</div>
      <div className="mt-3 text-4xl font-black tracking-tight tabular-nums text-cloudera-navy">{value}</div>
      <div className="mt-1 text-xs text-slate-600">{text.overall}</div>
      <div className="min-h-[2.5rem]">
        <Change kpi={kpi} language={language} />
      </div>
      <div className="mt-auto">
        <Sparkline kpi={kpi} />
      </div>
    </Link>
  )
}

/** Columns follow the number of KPIs, so the row is always full and every tile is the same size. */
function tileGrid(count: number): string {
  if (count >= 4) return 'sm:grid-cols-2 xl:grid-cols-4'
  if (count === 3) return 'lg:grid-cols-3'
  if (count === 2) return 'sm:grid-cols-2'
  return ''
}

function BriefingCard({ briefing, loading, language }: { briefing: HomeBriefing | null; loading: boolean; language: Language }) {
  const text = TEXT[language]
  return (
    <section className="home-rise home-rise-1 rounded-2xl bg-cloudera-navy text-white" aria-labelledby="home-briefing-title" data-testid="home-briefing">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-6 pt-5">
        <h2 id="home-briefing-title" className="text-sm font-semibold text-white/90">
          {text.briefing}
        </h2>
        <p className="text-xs text-white/80">{text.briefingNote}</p>
      </div>
      <div className="space-y-4 px-6 pb-6 pt-3">
        {loading && !briefing && (
          <div role="status" className="space-y-2">
            <p className="text-sm text-white/90">{text.briefingLoading}</p>
            <div className="home-placeholder h-4 w-3/4 rounded bg-white/15" />
            <div className="home-placeholder h-4 w-2/3 rounded bg-white/15" />
          </div>
        )}
        {!loading && briefing?.status !== 'ok' && <p className="text-sm text-white/90">{text.briefingNone}</p>}
        {briefing?.status === 'ok' && (
          <>
            <p className="max-w-4xl text-balance text-xl font-semibold leading-snug">{briefing.headline}</p>
            <ul className="grid gap-x-8 gap-y-3 lg:grid-cols-2">
              {(briefing.points ?? []).map(point => (
                <li key={point} className="flex gap-3 text-sm leading-relaxed text-white/90">
                  <span className="mt-[0.5em] h-1.5 w-1.5 shrink-0 rounded-full bg-cloudera-orange" aria-hidden />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
            {(briefing.ask_next ?? []).length > 0 && (
              <div className="flex flex-wrap gap-2 border-t border-white/15 pt-4">
                {(briefing.ask_next ?? []).map(question => (
                  <Link
                    key={question}
                    href={askHref(question)}
                    className="rounded-lg border border-white/30 px-3 py-2 text-left text-xs font-medium text-white transition-colors hover:bg-white/10 active:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                  >
                    {question}
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}

function TrendCard({ kpi, language, className }: { kpi: HomeKpi; language: Language; className: string }) {
  const text = TEXT[language]
  const data = kpi.series.map(point => ({ ...point, label: monthLabel(point.month, language) }))
  const format = (value: number) => formatFigure(value, kpi.unit_format, kpi.unit, language)
  return (
    <section className={`home-rise home-rise-2 rounded-2xl border border-slate-200 bg-white p-5 ${className}`} aria-labelledby="home-trend-title">
      <h2 id="home-trend-title" className="text-base font-bold text-cloudera-navy">
        {text.trend}: {kpi.label}
      </h2>
      <div className="mt-3 h-60">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#eef0f5" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} interval="preserveStartEnd" tickMargin={10} height={32} />
            <YAxis tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} width={64} domain={['auto', 'auto']} padding={{ top: 8, bottom: 8 }} tickFormatter={value => format(Number(value))} />
            <Tooltip formatter={value => format(Number(value))} />
            <ReferenceLine y={kpi.value} stroke="#64748b" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="value" name={kpi.label} stroke={ACCENT} strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-slate-600">
        {text.dashed}: {text.overall.toLowerCase()} {format(kpi.value)}
      </p>
    </section>
  )
}

function groupColumn(block: HomeRows): string | null {
  return block.columns.find(column => column !== 'metric_value') ?? null
}

function BreakdownCard({ block, language, className }: { block: HomeRows; language: Language; className: string }) {
  const text = TEXT[language]
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
    <section className={`home-rise home-rise-3 rounded-2xl border border-slate-200 bg-white p-5 ${className}`} aria-labelledby="home-breakdown-title">
      <h2 id="home-breakdown-title" className="text-base font-bold text-cloudera-navy">
        {block.label} {text.by} {by}
      </h2>
      <div className="mt-3" style={{ height: Math.max(200, rows.length * 32) }}>
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
                <Cell key={row.name} fill={row.value === top ? ACCENT : MUTED_BAR} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {typeof block.overall_value === 'number' && (
        <p className="mt-2 text-xs text-slate-600">
          {text.dashed}: {text.overall.toLowerCase()} {format(block.overall_value)}
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
    <section className="home-rise home-rise-3 rounded-2xl border border-slate-200 bg-white p-5" aria-labelledby="home-map-title" data-testid="home-map">
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

/** The layout of the page while its figures load, so nothing moves when they arrive. */
function Placeholder({ language }: { language: Language }) {
  const block = 'home-placeholder rounded-2xl border border-slate-200 bg-white'
  return (
    <div role="status" aria-live="polite" className="space-y-5">
      <p className="text-sm text-slate-600">{TEXT[language].loading}</p>
      <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
        <div className={`${block} h-60`} />
        <div className={`${block} h-60`} />
        <div className={`${block} h-60`} />
      </div>
      <div className={`${block} h-40`} aria-hidden />
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

  // The last figures this browser saw are shown at once; the fresh ones replace them when they arrive.
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
      // Both start together: the briefing endpoint shares the figures the Home request computes.
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
  const text = TEXT[language]
  const onAsk = (event: FormEvent) => {
    event.preventDefault()
    if (question.trim()) router.push(askHref(question.trim()))
  }
  const coverage =
    home?.data_coverage?.first && home?.data_coverage?.last
      ? `${dayLabel(home.data_coverage.first, language)} – ${dayLabel(home.data_coverage.last, language)}`
      : null
  const grid = tileGrid(home?.kpis.length ?? 0)

  return (
    <div className={pageCenterClassName('space-y-5')} data-testid="home-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-cloudera-navy">{text.title}</h1>
          <p className="mt-1 text-sm text-slate-600">{text.subtitle}</p>
          {(coverage || home?.computed_at) && (
            <p className="mt-1 text-xs text-slate-600">
              {coverage && (
                <span>
                  {text.coverage}: {coverage}
                </span>
              )}
              {coverage && home?.computed_at && <span aria-hidden> · </span>}
              {home?.computed_at && (
                <span>
                  {text.updated}{' '}
                  {new Intl.DateTimeFormat(locale(language), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(home.computed_at))}
                </span>
              )}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={loading || !selection}
          className={`min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-400 hover:text-cloudera-navy active:bg-slate-50 disabled:opacity-60 ${FOCUS}`}
        >
          {loading ? text.refreshing : text.refresh}
        </button>
      </header>

      <form onSubmit={onAsk} role="search" className="rounded-2xl border border-slate-200 bg-white p-3 focus-within:border-cloudera-orange/60">
        <label htmlFor="home-question" className="mb-1.5 block px-1 text-sm font-semibold text-slate-700">
          {text.question}
        </label>
        <div className="flex items-center gap-2">
          <input
            id="home-question"
            value={question}
            onChange={event => setQuestion(event.target.value)}
            placeholder={text.askPlaceholder}
            className="min-h-11 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 placeholder:text-slate-500 focus-visible:border-cloudera-orange focus-visible:outline focus-visible:outline-2 focus-visible:outline-cloudera-orange/40"
          />
          <button
            type="submit"
            disabled={!question.trim()}
            className={`min-h-11 rounded-lg bg-cloudera-navy px-5 text-sm font-semibold text-white transition-colors hover:bg-cloudera-navy/90 active:bg-cloudera-navy/80 disabled:opacity-50 ${FOCUS}`}
          >
            {text.ask}
          </button>
        </div>
      </form>

      {failed && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" role="alert">
          <span>{text.failed}</span>
          <button
            type="button"
            onClick={() => load(true)}
            className={`min-h-11 rounded-lg border border-rose-300 bg-white px-4 font-semibold text-rose-900 hover:bg-rose-100 ${FOCUS}`}
          >
            {text.retry}
          </button>
        </div>
      )}

      {!failed && !home && <Placeholder language={language} />}

      {home?.status === 'no_model' && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-700">
          <p>{text.noModel}</p>
          <Link href="/semantic-layer" className={`mt-2 inline-block font-semibold text-cloudera-navy underline underline-offset-2 ${FOCUS}`}>
            {text.openSemantic}
          </Link>
        </div>
      )}
      {home?.status === 'no_data' && <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-700">{text.noData}</div>}

      {home?.status === 'ok' && (
        <>
          <div className={`home-rise grid gap-4 ${grid}`}>
            {home.kpis.map(kpi => (
              <KpiTile key={kpi.metric} kpi={kpi} language={language} />
            ))}
          </div>
          <BriefingCard briefing={briefing} loading={briefingLoading} language={language} />
          <div className="grid gap-4 lg:grid-cols-3">
            {home.trend && <TrendCard kpi={home.trend} language={language} className="lg:col-span-2" />}
            {home.breakdown && <BreakdownCard block={home.breakdown} language={language} className={home.trend ? '' : 'lg:col-span-3'} />}
          </div>
          {home.map && <MapCard block={home.map} language={language} />}
        </>
      )}
    </div>
  )
}
