'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { ArrowDownRight, ArrowRight, ArrowUpRight, Map as MapIcon, RefreshCw, Send, Sparkles, TrendingUp } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ResultMap } from '../components/analysis/ResultMap'
import { api } from '../lib/api'
import { formatBusinessValue } from '../lib/businessPresentation'
import { detectGeo } from '../lib/geo'
import { useModelSelection } from '../lib/modelSelection'
import type { HomeBriefing, HomeKpi, HomePayload, HomeRows } from '../types/api'

type Language = 'id' | 'en'

const TEXT = {
  id: {
    title: 'Ringkasan Bisnis',
    subtitle: 'Angka utama dari semantic model, dihitung langsung dari data.',
    coverage: 'Data',
    refresh: 'Muat ulang',
    briefing: 'Briefing AI',
    briefingLoading: 'Menyusun briefing dari angka di bawah…',
    briefingNone: 'Briefing belum tersedia. Angka di bawah tetap terbaru.',
    askNext: 'Tanyakan',
    vsPrevious: 'vs bulan sebelumnya',
    overall: 'Keseluruhan',
    trend: 'Tren bulanan',
    breakdown: 'Per',
    map: 'Peta',
    askPlaceholder: 'Tanyakan apa saja tentang data Anda…',
    ask: 'Tanya',
    loading: 'Menghitung angka utama…',
    failed: 'Angka utama belum bisa dimuat.',
    retry: 'Coba lagi',
    noModel: 'Belum ada semantic model yang dipublikasikan ke Ask Data.',
    openAsk: 'Buka Ask Data',
    pp: 'poin',
  },
  en: {
    title: 'Business Overview',
    subtitle: 'The headline figures of the semantic model, computed from the data.',
    coverage: 'Data',
    refresh: 'Refresh',
    briefing: 'AI briefing',
    briefingLoading: 'Writing the briefing from the figures below…',
    briefingNone: 'No briefing yet. The figures below are current.',
    askNext: 'Ask',
    vsPrevious: 'vs the month before',
    overall: 'Overall',
    trend: 'Monthly trend',
    breakdown: 'By',
    map: 'Map',
    askPlaceholder: 'Ask anything about your data…',
    ask: 'Ask',
    loading: 'Computing the headline figures…',
    failed: 'The headline figures could not be loaded.',
    retry: 'Try again',
    noModel: 'No semantic model is published to Ask Data yet.',
    openAsk: 'Open Ask Data',
    pp: 'pts',
  },
} as const

function monthLabel(month: string, language: Language): string {
  const [year, number] = month.split('-').map(Number)
  if (!year || !number) return month
  return new Intl.DateTimeFormat(language === 'id' ? 'id-ID' : 'en-US', { month: 'short', year: 'numeric' }).format(new Date(year, number - 1, 1))
}

function format(value: number | null | undefined, unit: string | null | undefined, metric?: string): string {
  if (value === null || value === undefined) return '—'
  return formatBusinessValue('metric_value', value, metric, unit ?? 'quantity')
}

function askHref(question: string): string {
  return `/?ask=${encodeURIComponent(question)}`
}

function Change({ kpi, language }: { kpi: HomeKpi; language: Language }) {
  if (kpi.change === undefined || !kpi.last_month) return null
  const up = kpi.change >= 0
  const Arrow = up ? ArrowUpRight : ArrowDownRight
  const text =
    kpi.unit_format === 'percent'
      ? `${up ? '+' : '−'}${Math.abs(kpi.change).toFixed(1)} ${TEXT[language].pp}`
      : kpi.change_pct !== undefined
        ? `${up ? '+' : '−'}${Math.abs(kpi.change_pct).toFixed(1)}%`
        : null
  if (!text) return null
  return (
    <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
      <span className="inline-flex items-center gap-0.5 rounded-full bg-slate-100 px-2 py-0.5 font-semibold text-slate-700">
        <Arrow size={12} aria-hidden />
        {text}
      </span>
      <span>
        {monthLabel(kpi.last_month.month, language)} {TEXT[language].vsPrevious}
      </span>
    </div>
  )
}

function Sparkline({ kpi }: { kpi: HomeKpi }) {
  if (kpi.series.length < 3) return null
  return (
    <div className="mt-3 h-10" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={kpi.series} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line type="monotone" dataKey="value" stroke="#FF5A1F" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function KpiTile({ kpi, language, main }: { kpi: HomeKpi; language: Language; main: boolean }) {
  return (
    <Link
      href={askHref(language === 'id' ? `Bagaimana tren ${kpi.label} per bulan?` : `How has ${kpi.label} moved by month?`)}
      className={`card group block p-5 transition-shadow hover:shadow-md ${main ? 'border-orange-200 ring-1 ring-orange-100' : ''}`}
      data-testid="home-kpi"
      title={kpi.description || kpi.label}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">{kpi.label}</div>
        <ArrowRight size={14} className="shrink-0 text-slate-300 transition-colors group-hover:text-cloudera-orange" aria-hidden />
      </div>
      <div className="mt-2 text-3xl font-black tracking-tight text-cloudera-navy">{format(kpi.value, kpi.unit_format, kpi.metric)}</div>
      <div className="text-[11px] text-slate-400">{TEXT[language].overall}</div>
      <Change kpi={kpi} language={language} />
      <Sparkline kpi={kpi} />
    </Link>
  )
}

function BriefingCard({ briefing, loading, language }: { briefing: HomeBriefing | null; loading: boolean; language: Language }) {
  const text = TEXT[language]
  return (
    <section className="card overflow-hidden" aria-label={text.briefing} data-testid="home-briefing">
      <div className="flex items-center gap-2 border-b border-slate-100 bg-gradient-to-r from-violet-50 to-orange-50 px-5 py-3">
        <Sparkles size={16} className="text-cloudera-violet" aria-hidden />
        <h2 className="text-sm font-bold text-cloudera-navy">{text.briefing}</h2>
      </div>
      <div className="space-y-3 px-5 py-4">
        {loading && <p className="animate-pulse text-sm text-slate-500">{text.briefingLoading}</p>}
        {!loading && briefing?.status !== 'ok' && <p className="text-sm text-slate-500">{text.briefingNone}</p>}
        {!loading && briefing?.status === 'ok' && (
          <>
            <p className="text-base font-semibold leading-relaxed text-slate-900">{briefing.headline}</p>
            <ul className="space-y-2">
              {(briefing.points ?? []).map(point => (
                <li key={point} className="flex gap-2 text-sm leading-relaxed text-slate-700">
                  <span className="mt-[0.5em] h-1.5 w-1.5 shrink-0 rounded-full bg-cloudera-orange" aria-hidden />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
            {(briefing.ask_next ?? []).length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {(briefing.ask_next ?? []).map(question => (
                  <Link
                    key={question}
                    href={askHref(question)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-cloudera-orange/50 hover:bg-orange-50"
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

function TrendCard({ kpi, language }: { kpi: HomeKpi; language: Language }) {
  const data = kpi.series.map(point => ({ ...point, label: monthLabel(point.month, language) }))
  return (
    <section className="card p-5" aria-label={`${TEXT[language].trend}: ${kpi.label}`}>
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp size={16} className="text-cloudera-orange" aria-hidden />
        <h2 className="text-sm font-bold text-cloudera-navy">
          {TEXT[language].trend} · {kpi.label}
        </h2>
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#eef0f5" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} width={56} tickFormatter={v => format(Number(v), kpi.unit_format, kpi.metric)} />
            <Tooltip formatter={value => format(Number(value), kpi.unit_format, kpi.metric)} />
            <ReferenceLine y={kpi.value} stroke="#94a3b8" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="value" name={kpi.label} stroke="#FF5A1F" strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

function groupColumn(block: HomeRows): string | null {
  return block.columns.find(column => column !== 'metric_value') ?? null
}

function BreakdownCard({ block, language }: { block: HomeRows; language: Language }) {
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
  return (
    <section className="card p-5" aria-label={`${block.label} ${TEXT[language].breakdown} ${by}`}>
      <h2 className="mb-3 text-sm font-bold text-cloudera-navy">
        {block.label} · {TEXT[language].breakdown} {by}
      </h2>
      <div style={{ height: Math.max(180, rows.length * 30) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 24, bottom: 0, left: 8 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12, fill: '#334155' }} tickLine={false} axisLine={false} />
            <Tooltip formatter={value => format(Number(value), block.unit_format, block.metric)} />
            {typeof block.overall_value === 'number' && <ReferenceLine x={block.overall_value} stroke="#64748b" strokeDasharray="4 4" />}
            <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {rows.map(row => (
                <Cell key={row.name} fill={row.value === top ? '#FF5A1F' : '#c7cde0'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {typeof block.overall_value === 'number' && (
        <p className="mt-2 text-[11px] text-slate-500">
          - - - {TEXT[language].overall}: {format(block.overall_value, block.unit_format, block.metric)}
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
    <section className="card p-5" aria-label={`${TEXT[language].map}: ${block.label}`} data-testid="home-map">
      <div className="mb-3 flex items-center gap-2">
        <MapIcon size={16} className="text-cloudera-violet" aria-hidden />
        <h2 className="text-sm font-bold text-cloudera-navy">
          {TEXT[language].map} · {block.label} · {TEXT[language].breakdown} {block.column_labels[column] || column}
        </h2>
      </div>
      <ResultMap columns={block.columns} rows={block.rows} detection={detection} metric={block.metric} unitFormat={block.unit_format ?? undefined} />
    </section>
  )
}

export function HomePage() {
  const router = useRouter()
  const { selection } = useModelSelection()
  const [home, setHome] = useState<HomePayload | null>(null)
  const [failed, setFailed] = useState(false)
  const [briefing, setBriefing] = useState<HomeBriefing | null>(null)
  const [briefingLoading, setBriefingLoading] = useState(false)
  const [question, setQuestion] = useState('')

  const load = useCallback(
    (refresh = false) => {
      setFailed(false)
      if (refresh) setHome(null)
      api
        .home(selection, refresh)
        .then(payload => {
          setHome(payload)
          if (payload.status !== 'ok') return
          setBriefingLoading(true)
          api
            .homeBriefing(selection, refresh)
            .then(setBriefing, () => setBriefing({ status: 'failed' }))
            .finally(() => setBriefingLoading(false))
        })
        .catch(() => setFailed(true))
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
  const coverage = home?.data_coverage?.first && home?.data_coverage?.last ? `${home.data_coverage.first} – ${home.data_coverage.last}` : null

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8" data-testid="home-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-cloudera-navy">{text.title}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {text.subtitle}
            {coverage && <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{text.coverage}: {coverage}</span>}
          </p>
        </div>
        <button
          type="button"
          onClick={() => load(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-cloudera-navy"
        >
          <RefreshCw size={14} aria-hidden /> {text.refresh}
        </button>
      </header>

      <form onSubmit={onAsk} className="card flex items-center gap-2 p-2 pl-4" role="search">
        <Sparkles size={18} className="shrink-0 text-cloudera-orange" aria-hidden />
        <input
          value={question}
          onChange={event => setQuestion(event.target.value)}
          placeholder={text.askPlaceholder}
          aria-label={text.askPlaceholder}
          className="min-w-0 flex-1 bg-transparent py-2 text-sm text-slate-800 outline-none placeholder:text-slate-400"
        />
        <button type="submit" className="inline-flex items-center gap-1.5 rounded-lg bg-cloudera-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!question.trim()}>
          <Send size={14} aria-hidden /> {text.ask}
        </button>
      </form>

      {failed && (
        <div className="card flex items-center justify-between gap-3 p-4 text-sm text-slate-700" role="alert">
          {text.failed}
          <button type="button" onClick={() => load(true)} className="font-semibold text-cloudera-navy hover:underline">{text.retry}</button>
        </div>
      )}
      {!failed && !home && <p className="animate-pulse py-10 text-center text-sm text-slate-500" role="status">{text.loading}</p>}
      {home && home.status !== 'ok' && (
        <div className="card p-6 text-sm text-slate-600">
          {text.noModel}{' '}
          <Link href="/" className="font-semibold text-cloudera-navy hover:underline">{text.openAsk}</Link>
        </div>
      )}

      {home?.status === 'ok' && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {home.kpis.map((kpi, index) => (
              <KpiTile key={kpi.metric} kpi={kpi} language={language} main={index === 0} />
            ))}
          </div>
          <BriefingCard briefing={briefing} loading={briefingLoading} language={language} />
          <div className="grid gap-4 lg:grid-cols-2">
            {home.trend && <TrendCard kpi={home.trend} language={language} />}
            {home.breakdown && <BreakdownCard block={home.breakdown} language={language} />}
          </div>
          {home.map && <MapCard block={home.map} language={language} />}
        </>
      )}
    </div>
  )
}
