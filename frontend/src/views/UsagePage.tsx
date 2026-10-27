'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
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

  const budget = summary?.monthly_token_budget ?? 0
  const mtdTokens = summary?.mtd_totals.total_tokens ?? 0
  const budgetPct = budget > 0 ? Math.min(100, (mtdTokens / budget) * 100) : 0

  return (
    <PageCenter>
      <div className="mb-6">
        <h1 className="type-app-title text-2xl">{appConfig.navigationUsage}</h1>
        <p className="type-chat-body mt-1 text-slate-500">
          LLM token usage for this workspace (recorded on the backend).
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {PERIODS.map(item => (
          <button
            key={item.key}
            type="button"
            onClick={() => setPeriod(item.key)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              period === item.key
                ? 'bg-cloudera-navy text-white'
                : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            {item.label}
          </button>
        ))}
        <a
          href={api.usageExportCsvUrl(periodConfig.mtd ? 31 : periodConfig.days ?? 7)}
          className="ml-auto inline-flex items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 hover:border-cloudera-orange/40 hover:bg-orange-50/50"
        >
          Export CSV
        </a>
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
          {budget > 0 && (
            <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium text-cloudera-navy">Monthly token budget</span>
                <span className="text-sm text-slate-600">
                  {formatCompactTokens(mtdTokens)} / {formatCompactTokens(budget)}
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-cloudera-orange transition-all"
                  style={{ width: `${budgetPct}%` }}
                />
              </div>
            </div>
          )}

          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: 'Total tokens', value: summary.totals.total_tokens },
              { label: 'Prompt', value: summary.totals.prompt_tokens },
              { label: 'Completion', value: summary.totals.completion_tokens },
              { label: 'LLM calls', value: summary.totals.llm_calls },
            ].map(card => (
              <div key={card.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{card.label}</div>
                <div className="mt-1 text-2xl font-semibold text-cloudera-navy">
                  {typeof card.value === 'number' && card.label !== 'LLM calls'
                    ? formatCompactTokens(card.value)
                    : card.value}
                </div>
                {card.label === 'Total tokens' && (
                  <div className="mt-0.5 text-xs text-slate-500">{summary.totals.turns} Ask Data turns</div>
                )}
              </div>
            ))}
          </div>

          <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
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
                      formatter={value => [formatCompactTokens(Number(value ?? 0)), 'Tokens']}
                      labelFormatter={label => String(label)}
                    />
                    <Bar dataKey="tokens" fill="#FF5A1F" radius={[4, 4, 0, 0]} maxBarSize={48} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {summary.by_model.length > 0 && (
            <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-cloudera-navy">By model</h2>
              <ul className="mt-2 divide-y divide-slate-100">
                {summary.by_model.map(row => (
                  <li key={`${row.provider}-${row.model}`} className="flex items-center justify-between py-2 text-sm">
                    <span className="text-slate-700">
                      <span className="font-medium capitalize">{row.provider}</span>
                      <span className="text-slate-400"> · </span>
                      <span className="text-slate-600">{row.model}</span>
                    </span>
                    <span className="font-medium text-cloudera-navy">{formatCompactTokens(row.tokens)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
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
                          <span className="capitalize">{ev.provider}</span>
                          <span className="block text-sm text-slate-500">{ev.model}</span>
                        </td>
                        <td>{ev.strategy || '—'}</td>
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
