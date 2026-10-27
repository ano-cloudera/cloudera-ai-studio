'use client'

import { useState } from 'react'
import { BarChart3, Briefcase, FileText, Lightbulb } from 'lucide-react'
import {
  InsightListItem,
  WorkspaceSection,
  WorkspaceSectionContent,
  WorkspaceSectionHeader,
} from './analysis/WorkspaceSectionParts'
import { AnswerChart } from './AnswerChart'
import { AnswerProse } from './AnswerProse'
import { WorkspaceDataTable } from './analysis/WorkspaceDataTable'
import { WorkspaceQueryView } from './analysis/WorkspaceQueryView'
import { KpiCard } from './KpiCard'
import { formatCitationLabel, isRagResponse } from '../lib/ragReport'
import type { ChatResponse } from '../types/api'

type WorkspaceTab = 'summary' | 'table' | 'query' | 'sources'

type Props = {
  response: ChatResponse
}

function workspaceTabs(
  hasTable: boolean,
  hasQuery: boolean,
  hasSources: boolean,
): { id: WorkspaceTab; label: string; disabled?: boolean }[] {
  const tabs: { id: WorkspaceTab; label: string; disabled?: boolean }[] = [{ id: 'summary', label: 'Summary' }]
  if (hasSources) tabs.push({ id: 'sources', label: 'Sources' })
  tabs.push({ id: 'table', label: 'Table', disabled: !hasTable })
  tabs.push({ id: 'query', label: 'Query', disabled: !hasQuery })
  return tabs
}

function WorkspaceTabBar({
  tab,
  tabs,
  onSelect,
}: {
  tab: WorkspaceTab
  tabs: ReturnType<typeof workspaceTabs>
  onSelect: (id: WorkspaceTab) => void
}) {
  return (
    <div className="flex gap-5 border-b border-slate-200/90" role="tablist" aria-label="Analysis workspace views">
      {tabs.map(item => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={tab === item.id}
          disabled={item.disabled}
          onClick={() => onSelect(item.id)}
          className={`-mb-px border-b-2 pb-2.5 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange ${
            tab === item.id
              ? 'border-cloudera-orange text-cloudera-navy'
              : item.disabled
                ? 'cursor-not-allowed border-transparent text-slate-300'
                : 'border-transparent text-slate-500 hover:text-cloudera-navy'
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

export function ReportDocumentSection({ response }: Props) {
  const rag = isRagResponse(response)
  const [tab, setTab] = useState<WorkspaceTab>(rag ? 'summary' : 'summary')
  const visualChartTypes = ['bar', 'line', 'area', 'scatter', 'pie']
  const hasVisualChart = Boolean(
    response.chart_spec &&
      visualChartTypes.includes(response.chart_spec.type) &&
      response.chart_spec.x &&
      response.chart_spec.y &&
      response.data.rows.length > 0,
  )
  const kpiField = response.chart_spec?.type === 'kpi' ? response.chart_spec.y || response.data.columns[0] : null
  const kpiValue = kpiField ? response.data.rows[0]?.[kpiField] : undefined
  const sql = response.governed_sql?.trim()
  const hasTable = response.data.rows.length > 0
  const hasQuery = Boolean(sql || response.data.governed_metric || response.answer.data_reference.trim())
  const citations = response.citations ?? []
  const hasSources = rag && citations.length > 0
  const tabs = workspaceTabs(hasTable, hasQuery, hasSources)
  const summarySame =
    response.answer.executive_summary.trim() === response.answer.direct_answer.trim()
  const chartTitle = response.chart_spec?.title || 'Visualization'

  return (
    <div>
      <WorkspaceTabBar tab={tab} tabs={tabs} onSelect={setTab} />

      {tab === 'summary' && (
        <div className="mt-6" role="tabpanel">
          <WorkspaceSection>
            <WorkspaceSectionHeader icon={FileText} tone="sky" title="Executive summary" />
            <WorkspaceSectionContent>
              <AnswerProse text={response.answer.direct_answer} omitTables={hasTable} variant="main" />
              {!summarySame && (
                <AnswerProse text={response.answer.executive_summary} omitTables variant="support" />
              )}
            </WorkspaceSectionContent>
          </WorkspaceSection>

          {response.answer.insights.length > 0 && (
            <WorkspaceSection>
              <WorkspaceSectionHeader
                icon={Lightbulb}
                tone="amber"
                title="Key findings"
                action={
                  hasTable ? (
                    <button
                      type="button"
                      onClick={() => setTab('table')}
                      className="text-xs font-semibold text-cloudera-orange hover:underline"
                    >
                      Lihat detail →
                    </button>
                  ) : null
                }
              />
              <WorkspaceSectionContent>
                <ol className="space-y-4">
                  {response.answer.insights.map((item, index) => (
                    <InsightListItem key={item} index={index + 1}>
                      {item}
                    </InsightListItem>
                  ))}
                </ol>
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}

          {(response.chart_spec?.type === 'kpi' || hasVisualChart) && (
            <WorkspaceSection>
              <WorkspaceSectionHeader
                icon={BarChart3}
                tone="orange"
                title={chartTitle}
                action={
                  response.data.governed_metric ? (
                    <span className="max-w-[140px] truncate font-mono text-[10px] text-slate-500 sm:max-w-none">
                      {response.data.governed_metric}
                    </span>
                  ) : null
                }
              />
              <WorkspaceSectionContent className="pb-4">
                {response.chart_spec?.type === 'kpi' && (
                  <div className="max-w-sm">
                    <KpiCard label={response.chart_spec.title} value={kpiValue} format="" icon={BarChart3} />
                  </div>
                )}
                {hasVisualChart && response.chart_spec && (
                  <AnswerChart chart={response.chart_spec} rows={response.data.rows} embedded hideTitle />
                )}
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}

          {!hasVisualChart && response.chart_spec?.type !== 'kpi' && hasTable && (
            <p className="mt-4 text-xs text-slate-500 sm:ml-[calc(3rem+1rem)]">
              Tidak ada grafik untuk turn ini — buka tab <strong className="font-semibold">Table</strong> untuk
              baris lengkap.
            </p>
          )}

          {response.answer.business_implications.length > 0 && (
            <WorkspaceSection className="!mt-5 !pt-9 pb-8">
              <WorkspaceSectionHeader icon={Briefcase} tone="violet" title="Business implications" />
              <WorkspaceSectionContent>
                <ul className="workspace-section-body space-y-2.5">
                  {response.answer.business_implications.map(item => (
                    <li key={item} className="flex gap-2.5">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cloudera-violet/70" aria-hidden />
                      <span className="workspace-body-text">{item}</span>
                    </li>
                  ))}
                </ul>
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}
        </div>
      )}

      {tab === 'table' && (
        <div className="mt-6" role="tabpanel">
          <WorkspaceDataTable
            title={chartTitle}
            columns={response.data.columns}
            rows={response.data.rows}
            metric={response.data.governed_metric ?? undefined}
            unitFormat={response.data.unit_format ?? undefined}
            rowCount={response.data.row_count}
          />
        </div>
      )}

      {tab === 'query' && (
        <div role="tabpanel">
          <WorkspaceQueryView response={response} />
        </div>
      )}

      {tab === 'sources' && (
        <div className="mt-6 space-y-4" role="tabpanel">
          {citations.length === 0 ? (
            <p className="text-sm text-slate-500">No document sources were attached to this answer.</p>
          ) : (
            <ol className="space-y-4">
              {citations.map((cite, index) => (
                <li key={cite.chunk_id} className="rounded-lg border border-slate-200/90 bg-slate-50/50 p-3">
                  <p className="text-sm font-semibold text-cloudera-navy">{formatCitationLabel(cite, index)}</p>
                  <p className="mt-2 text-xs leading-relaxed text-slate-600">{cite.snippet}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}
