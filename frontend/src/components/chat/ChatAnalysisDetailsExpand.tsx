'use client'

import { ChevronDown, Database } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { ChatResponse } from '../../types/api'
import type { PresentationTier } from '../../lib/presentationTier'
import { getPresentationTierConfig } from '../../lib/presentationTierConfig'
import { DataTable } from '../DataTable'
import { SingleRowEvidence } from '../SingleRowEvidence'
import { compactSingleRowEvidence } from '../../lib/singleRowPresentation'
import { WorkspaceSqlBlock } from '../analysis/WorkspaceSqlBlock'

type DetailTab = 'data' | 'query'

type Props = {
  response: ChatResponse
  tier: PresentationTier
  kpiBlock: ReactNode
  tableBlock: ReactNode
  executiveMode?: boolean
  /** Tier 1 executive: show SQL only (no duplicate KPI table). */
  executiveQueryOnly?: boolean
}

export function ChatAnalysisDetailsExpand({
  response,
  tier,
  kpiBlock,
  tableBlock,
  executiveMode = false,
  executiveQueryOnly = false,
}: Props) {
  const defaultOpen = getPresentationTierConfig().chat_details_default_open
  const [open, setOpen] = useState(defaultOpen)
  const sql = response.governed_sql?.trim() ?? ''
  const hasSql = Boolean(sql)
  const hasTable = response.data.rows.length > 0
  const showKpi = Boolean(kpiBlock) && !(executiveMode && tier === 1) && !executiveQueryOnly
  const hasKpi = showKpi
  const showTableInExpand = hasTable && !executiveQueryOnly
  const [tab, setTab] = useState<DetailTab>(executiveQueryOnly && hasSql ? 'query' : hasTable || hasKpi ? 'data' : 'query')

  if (!hasSql && !showTableInExpand && !hasKpi) return null

  const label = executiveQueryOnly
    ? 'Lihat query yang dijalankan'
    : executiveMode
      ? 'Detail data'
    : tier === 1
      ? hasSql
        ? 'Sumber data & query'
        : 'Sumber data'
      : 'Detail tabel & query'

  const showDataTab = showTableInExpand || hasKpi
  const showQueryTab = hasSql && (!executiveMode || executiveQueryOnly)

  return (
    <div className="rounded-xl border border-slate-200/90 bg-slate-50/40">
      <button
        type="button"
        onClick={() => setOpen(previous => !previous)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs font-semibold text-cloudera-navy transition-colors hover:bg-slate-50"
        aria-expanded={open}
      >
        <Database size={14} className="shrink-0 text-cloudera-orange" aria-hidden />
        {label}
        <ChevronDown
          size={14}
          className={`ml-auto shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="border-t border-slate-200/80 px-3 py-3">
          {showDataTab && showQueryTab && !executiveMode ? (
            <div className="mb-3 flex gap-1 rounded-lg bg-slate-100/80 p-1" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === 'data'}
                className={`flex-1 rounded-md px-2 py-1.5 text-xs font-semibold transition-colors ${
                  tab === 'data' ? 'bg-white text-cloudera-navy shadow-sm' : 'text-slate-600 hover:text-cloudera-navy'
                }`}
                onClick={() => setTab('data')}
              >
                Data
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === 'query'}
                className={`flex-1 rounded-md px-2 py-1.5 text-xs font-semibold transition-colors ${
                  tab === 'query' ? 'bg-white text-cloudera-navy shadow-sm' : 'text-slate-600 hover:text-cloudera-navy'
                }`}
                onClick={() => setTab('query')}
              >
                Query
              </button>
            </div>
          ) : null}

          {(executiveQueryOnly || tab === 'data') && showDataTab ? (
            <div className="space-y-3">
              {hasKpi ? kpiBlock : null}
              {showTableInExpand ? tableBlock : null}
            </div>
          ) : null}

          {(executiveQueryOnly || tab === 'query') && showQueryTab ? (
            <div className="space-y-1">
              <WorkspaceSqlBlock sql={sql} wrapLines />
            </div>
          ) : null}

          {tab === 'data' && !showDataTab && showQueryTab ? (
            <p className="text-xs text-slate-500">No tabular result for this answer.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

/** Table-only block for expand (no duplicate section chrome). */
export function expandTableBlock(response: ChatResponse): ReactNode {
  const visualChartTypes = ['bar', 'line', 'area', 'scatter', 'pie']
  const hasVisualChart = Boolean(
    response.chart_spec &&
      visualChartTypes.includes(response.chart_spec.type) &&
      response.chart_spec.x &&
      response.chart_spec.y &&
      response.data.rows.length > 0,
  )
  const compactSingleRow =
    !hasVisualChart &&
    response.chart_spec?.type !== 'kpi' &&
    response.data.rows.length === 1
      ? compactSingleRowEvidence(response.data.columns, response.data.rows)
      : null

  if (response.data.rows.length === 0) return null

  if (compactSingleRow && !hasVisualChart) {
    return (
      <SingleRowEvidence
        compact={compactSingleRow}
        metric={response.data.governed_metric ?? undefined}
        unitFormat={response.data.unit_format ?? undefined}
        title={response.chart_spec?.title ?? undefined}
      />
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200/90 bg-white">
      <DataTable
        columns={response.data.columns}
        rows={response.data.rows}
        metric={response.data.governed_metric ?? undefined}
        unitFormat={response.data.unit_format ?? undefined}
      />
    </div>
  )
}
