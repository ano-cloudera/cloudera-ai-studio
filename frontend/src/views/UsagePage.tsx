'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { modelDisplayName, providerDisplayName } from '../lib/modelLabels'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { TablePagination } from '../components/knowledge/TablePagination'
import { TableHeaderCheckbox, TableRowCheckbox } from '../components/table/TableSelectionCheckbox'
import { TableSelectionActionBar } from '../components/table/TableSelectionActionBar'
import { PageCenter } from '../components/PageCenter'
import { useTableSelection } from '../lib/useTableSelection'
import { useTableSelectionMode } from '../lib/useTableSelectionMode'
import { ServiceErrorState } from '../components/ServiceErrorState'
import { appConfig } from '../config/appConfig'
import { api } from '../lib/api'
import { toAppApiError, type AppApiError } from '../lib/apiError'
import { formatUsageTimestampWib } from '../lib/formatDateTime'
import { formatCompactTokens } from '../lib/formatTokens'
import type { UsageEvent, UsageSummary } from '../types/api'

type PeriodKey = '7d' | '30d' | 'mtd'

const PERIODS: { key: PeriodKey; label: string; days?: number; mtd?: boolean }[] = [
  { key: '7d', label: '7d', days: 7 },
  { key: '30d', label: '30d', days: 30 },
  { key: 'mtd', label: 'MTD', mtd: true },
]

function formatDayLabel(isoDay: string): string {
  const d = new Date(`${isoDay}T12:00:00`)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const ANSWER_PATH_LABELS: Record<string, string> = {
  governed: 'Governed metric',
  sql_fallback: 'Controlled SQL (fallback)',
  clarification: 'Asked for clarification',
  unsupported: 'Not supported',
  conversational: 'Conversation',
  rag: 'Knowledge documents',
  mcp: 'MCP tool',
  agent: 'Agent analysis',
}

/** How much a figure moved against the stretch before it; null when there was nothing before to compare with. */
function change(current: number, prior: number | undefined): { pct: number; text: string } | null {
  if (prior === undefined || prior <= 0) return null
  const pct = ((current - prior) / prior) * 100
  return { pct, text: `${pct >= 0 ? '+' : '-'}${Math.abs(pct).toFixed(1)}%` }
}

export function UsagePage() {
  const [period, setPeriod] = useState<PeriodKey>('7d')
  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [events, setEvents] = useState<UsageEvent[]>([])
  const [eventsPage, setEventsPage] = useState(1)
  const [eventsPageSize, setEventsPageSize] = useState(10)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const eventsSelection = useTableSelection()
  const eventsSelectionMode = useTableSelectionMode(eventsSelection.clear)

  const periodConfig = PERIODS.find(p => p.key === period) ?? PERIODS[0]

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const days = periodConfig.mtd ? 31 : periodConfig.days ?? 7
      const [sum, ev] = await Promise.all([
        api.usageSummary(periodConfig.mtd ? { mtd: true } : { days: periodConfig.days }),
        api.usageEvents(days, 80),
      ])
      setSummary(sum)
      setEvents(ev.events)
    } catch (e) {
      setLoadError(toAppApiError(e))
    } finally {
      setLoading(false)
    }
  }, [periodConfig])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setEventsPage(1)
  }, [period])

  const pagedEvents = useMemo(() => {
    const start = (eventsPage - 1) * eventsPageSize
    return events.slice(start, start + eventsPageSize)
  }, [events, eventsPage, eventsPageSize])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(events.length / eventsPageSize) || 1)
    if (eventsPage > totalPages) setEventsPage(totalPages)
  }, [events.length, eventsPage, eventsPageSize])

  const chartData = useMemo(
    () => (summary?.daily ?? []).map(row => ({ ...row, label: formatDayLabel(row.day) })),
    [summary?.daily],
  )

  const answerPaths = useMemo(() => {
    const counts = new Map<string, number>()
    for (const ev of events) counts.set(ev.strategy || 'other', (counts.get(ev.strategy || 'other') ?? 0) + 1)
    return Array.from(counts.entries())
      .map(([strategy, count]) => ({ strategy, count, share: events.length ? (count / events.length) * 100 : 0 }))
      .sort((a, b) => b.count - a.count)
  }, [events])

  const budget = summary?.monthly_token_budget ?? 0
  const mtdTokens = summary?.mtd_totals.total_tokens ?? 0
  const budgetPct = budget > 0 ? Math.min(100, (mtdTokens / budget) * 100) : 0

  const prior = summary?.prior_totals
  const total = summary?.totals.total_tokens ?? 0
  const totalChange = change(total, prior?.total_tokens)
  const busiest = chartData.length > 1 ? chartData.reduce((a, b) => (b.tokens > a.tokens ? b : a)) : null
  const modelTotal = (summary?.by_model ?? []).reduce((sum, row) => sum + row.tokens, 0)
  const priorLabel = `${summary?.prior_period_days ?? ''} days before`

  return (
    <PageCenter>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="type-app-title text-2xl">{appConfig.navigationUsage}</h1>
          <p className="type-chat-body mt-1 text-slate-500">
            LLM token usage for this workspace (recorded on the backend).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div role="group" aria-label="Period" className="flex rounded-lg border border-slate-200 bg-white p-0.5">
            {PERIODS.map(item => (
              <button
                key={item.key}
                type="button"
                aria-pressed={period === item.key}
                onClick={() => setPeriod(item.key)}
                className={`min-h-11 sm:min-h-9 rounded-md px-3.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange ${
                  period === item.key ? 'bg-cloudera-navy text-white' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <a
            href={api.usageExportCsvUrl(periodConfig.mtd ? 31 : periodConfig.days ?? 7)}
            className="inline-flex min-h-11 sm:min-h-9 items-center rounded-lg border border-slate-200 bg-white px-3.5 text-sm font-medium text-slate-700 hover:border-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange"
          >
            Export CSV
          </a>
        </div>
      </div>

      {loadError && !summary ? (
        <ServiceErrorState
          title="Unable to load Usage"
          message="We couldn't reach the backend service."
          error={loadError}
          onRetry={() => void load()}
        />
      ) : null}
      {loading && !summary && <p className="text-sm text-slate-500">Loading usage…</p>}

      {summary && (
        <>
          <section aria-label="Summary" className="mb-5 rounded-xl bg-cloudera-mist px-5 py-4" data-testid="usage-summary-line">
            <p className="text-xl font-semibold tracking-tight text-cloudera-navy">
              {totalChange ? (
                Math.abs(totalChange.pct) < 2 ? (
                  'Usage is about the same as the period before'
                ) : (
                  <>
                    Usage is {totalChange.pct > 0 ? 'up' : 'down'} <span className="text-cloudera-orange">{Math.abs(totalChange.pct).toFixed(0)}%</span> on the period before
                  </>
                )
              ) : (
                `${formatCompactTokens(total)} tokens across ${summary.totals.turns} Ask Data turns`
              )}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {totalChange && prior ? `${formatCompactTokens(total)} tokens in this period, against ${formatCompactTokens(prior.total_tokens)} in the ${priorLabel}.` : null}
              {busiest ? `${totalChange ? ' ' : ''}Busiest day: ${busiest.label} (${formatCompactTokens(busiest.tokens)}).` : null}
            </p>
          </section>

          {budget > 0 && (
            <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium text-cloudera-navy">Monthly token budget</span>
                <span className="text-sm text-slate-600">
                  {formatCompactTokens(mtdTokens)} / {formatCompactTokens(budget)}
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-sm bg-slate-100">
                <div className="h-full rounded-sm bg-cloudera-orange transition-all" style={{ width: `${budgetPct}%` }} />
              </div>
            </div>
          )}

          <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: 'Total tokens', value: summary.totals.total_tokens, prior: prior?.total_tokens, tokens: true, lead: true },
              { label: 'Prompt', value: summary.totals.prompt_tokens, prior: prior?.prompt_tokens, tokens: true },
              { label: 'Completion', value: summary.totals.completion_tokens, prior: prior?.completion_tokens, tokens: true },
              { label: 'LLM calls', value: summary.totals.llm_calls, prior: prior?.llm_calls, tokens: false },
            ].map(card => {
              const moved = change(card.value, card.prior)
              const show = (n: number) => (card.tokens ? formatCompactTokens(n) : String(n))
              return (
                <div key={card.label} className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{card.label}</div>
                  <div className={`mt-1 font-semibold text-cloudera-navy ${card.lead ? 'text-3xl' : 'text-2xl'}`}>{show(card.value)}</div>
                  <div className="mt-1 min-h-4 text-xs text-slate-600">
                    {moved ? (
                      <>
                        <span className="font-semibold text-slate-800">{moved.text}</span> vs {show(card.prior ?? 0)} before
                      </>
                    ) : card.lead ? (
                      `${summary.totals.turns} Ask Data turns`
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-cloudera-navy">Usage per day</h2>
            <p className="mb-3 text-xs text-slate-500">Total tokens across all models</p>
            {chartData.length === 0 ? (
              <p className="text-sm text-slate-500">No usage recorded yet. Send a question in Ask Data.</p>
            ) : (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 11, fill: '#64748b' }} tickFormatter={v => formatCompactTokens(Number(v))} />
                    <Tooltip
                      cursor={{ fill: '#F6F7F9' }}
                      formatter={value => [formatCompactTokens(Number(value ?? 0)), 'Tokens']}
                      labelFormatter={label => String(label)}
                    />
                    <Bar dataKey="tokens" fill="#FF5A14" radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="mb-5 grid gap-5 lg:grid-cols-2">
            {summary.by_model.length > 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <h2 className="text-sm font-semibold text-cloudera-navy">By model</h2>
                <ul className="mt-3 space-y-3">
                  {summary.by_model.map((row, index) => {
                    const share = modelTotal ? (row.tokens / modelTotal) * 100 : 0
                    return (
                      <li key={`${row.provider}-${row.model}`} className="text-sm">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="min-w-0 truncate text-slate-700">
                            <span className="font-medium" title={row.model}>{modelDisplayName(row.model)}</span>
                            <span className="text-slate-500"> · {providerDisplayName(row.provider)}</span>
                          </span>
                          <span className="shrink-0 text-slate-600">
                            <span className="font-medium text-cloudera-navy">{formatCompactTokens(row.tokens)}</span>
                            <span className="text-slate-500"> · {share.toFixed(0)}%</span>
                          </span>
                        </div>
                        <div className="mt-1.5 h-2 overflow-hidden rounded-sm bg-slate-100" aria-hidden>
                          <div className={`h-full rounded-sm ${index === 0 ? 'bg-cloudera-orange' : 'bg-cloudera-indigo'}`} style={{ width: `${share}%` }} />
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}

            {answerPaths.length > 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="answer-paths">
                <h2 className="text-sm font-semibold text-cloudera-navy">How questions were answered</h2>
                <p className="text-xs text-slate-500">
                  From the last {events.length} turns. “Controlled SQL” means no governed metric matched, so the model wrote the query.
                </p>
                <ul className="mt-3 space-y-3">
                  {answerPaths.map((row, index) => (
                    <li key={row.strategy} className="text-sm">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className={row.strategy === 'sql_fallback' ? 'font-medium text-amber-700' : 'text-slate-700'}>
                          {ANSWER_PATH_LABELS[row.strategy] ?? row.strategy}
                        </span>
                        <span className="shrink-0 text-slate-600">
                          {row.count} <span className="text-slate-500">· {row.share.toFixed(0)}%</span>
                        </span>
                      </div>
                      <div className="mt-1.5 h-2 overflow-hidden rounded-sm bg-slate-100" aria-hidden>
                        <div className={`h-full rounded-sm ${index === 0 ? 'bg-cloudera-orange' : 'bg-cloudera-indigo'}`} style={{ width: `${row.share}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
              <h2 className="text-sm font-semibold text-cloudera-navy">Recent turns</h2>
              <TableSelectionActionBar
                entityLabel="events"
                mode={eventsSelectionMode}
                selectedCount={eventsSelection.selectedCount}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="app-data-table w-full min-w-[640px]">
                <thead className="app-table-head">
                  <tr>
                    {eventsSelectionMode.active ? (
                      <th className="w-11">
                        <TableHeaderCheckbox
                          state={eventsSelection.datasetCheckboxState(events.length)}
                          onToggle={() =>
                            eventsSelection.toggleDatasetSelection(
                              events.map(ev => ev.request_id),
                              events.length,
                            )
                          }
                        />
                      </th>
                    ) : null}
                    <th>Date (UTC+7)</th>
                    <th>Model</th>
                    <th>Strategy</th>
                    <th className="text-right">Tokens</th>
                    <th className="text-right">Calls</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={eventsSelectionMode.active ? 6 : 5} className="py-6 text-slate-500">
                        No events in this period.
                      </td>
                    </tr>
                  ) : (
                    pagedEvents.map(ev => (
                      <tr key={ev.request_id} className="text-slate-700">
                        {eventsSelectionMode.active ? (
                          <td className="w-11">
                            <TableRowCheckbox
                              checked={eventsSelection.isSelected(ev.request_id)}
                              label={`Select usage event ${ev.request_id}`}
                              onToggle={() => eventsSelection.toggle(ev.request_id)}
                            />
                          </td>
                        ) : null}
                        <td className="whitespace-nowrap text-slate-500">
                          {formatUsageTimestampWib(ev.created_at)}
                        </td>
                        <td>
                          <span title={ev.model}>{modelDisplayName(ev.model)}</span>
                          <span className="block text-sm text-slate-500">{providerDisplayName(ev.provider)}</span>
                        </td>
                        <td>{ev.strategy || '–'}</td>
                        <td className="text-right font-medium">{formatCompactTokens(ev.total_tokens)}</td>
                        <td className="text-right text-slate-500">{ev.llm_calls}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {events.length > 0 ? (
              <TablePagination
                page={eventsPage}
                pageSize={eventsPageSize}
                total={events.length}
                onPageChange={setEventsPage}
                onPageSizeChange={size => {
                  setEventsPageSize(size)
                  setEventsPage(1)
                }}
              />
            ) : null}
          </div>
        </>
      )}
    </PageCenter>
  )
}
