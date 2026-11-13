'use client'

import { rememberColumnLabels } from '../lib/businessPresentation'
import { chartMetric } from '../lib/chartMetric'
import { answerSectionLabels } from '../lib/answerSectionLabels'

import { useMemo, useState } from 'react'
import { ArrowLeftRight, Briefcase, FileText, Lightbulb } from 'lucide-react'
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
import { ResultMap } from './analysis/ResultMap'
import { ComparisonSummary, comparisonKind } from './analysis/ComparisonSummary'
import { detectGeo } from '../lib/geo'
import { formatCitationLabel, isRagResponse } from '../lib/ragReport'
import type { ChatResponse } from '../types/api'

type WorkspaceTab = 'summary' | 'chart' | 'map' | 'table' | 'query' | 'sources'

type Props = {
  response: ChatResponse
  chatNarrativeShown?: boolean
  chatInsightCount?: number
  chartShownInChat?: boolean
}

function workspaceTabs(
  hasTable: boolean,
  hasQuery: boolean,
  hasSources: boolean,
  hasMap = false,
  hasAnalysis = true,
  hasChart = false,
): { id: WorkspaceTab; label: string; disabled?: boolean }[] {
  const tabs: { id: WorkspaceTab; label: string; disabled?: boolean }[] = hasAnalysis ? [{ id: 'summary', label: 'Analysis' }] : []
  if (hasChart) tabs.push({ id: 'chart', label: 'Chart' })
  if (hasSources) tabs.push({ id: 'sources', label: 'Sources' })
  if (hasMap) tabs.push({ id: 'map', label: 'Map' })
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

export function ReportDocumentSection({
  response,
  chatNarrativeShown = false,
  chatInsightCount = 0,
  chartShownInChat = false,
}: Props) {
  rememberColumnLabels(response.data.column_labels)
  const sectionLabels = answerSectionLabels(response.language)
  const rag = isRagResponse(response)
  const visualChartTypes = ['bar', 'line', 'area', 'scatter', 'pie']
  const hasVisualChart = Boolean(
    response.chart_spec &&
      visualChartTypes.includes(response.chart_spec.type) &&
      response.chart_spec.x &&
      response.chart_spec.y &&
      response.data.rows.length > 0,
  )
  const sql = response.governed_sql?.trim()
  const hasTable = response.data.rows.length > 0
  const hasQuery = Boolean(sql || response.data.governed_metric || response.answer.data_reference.trim())
  const citations = response.citations ?? []
  const hasSources = rag && citations.length > 0
  const geo = useMemo(() => (rag ? null : detectGeo(response.data.columns, response.data.rows, response.data.geo_points)), [rag, response.data.columns, response.data.rows, response.data.geo_points])
  const calculation = rag ? null : response.calculation ?? null
  const comparison = !rag && comparisonKind(response.data.columns) !== null && hasTable
  const checks = response.status === 'SUCCESS' ? response.agent_steps ?? [] : []
  const report = response.analysis_report?.trim() ?? ''
  const workspaceInsightsFirst = response.answer.insights.filter(item => item.trim()).slice(chatInsightCount)
  // The chart has its own tab (Chart): larger than in the chat, with values on the bars and a second view when the data allows one.
  const hasAnalysis = Boolean(
    report || !chatNarrativeShown || comparison || workspaceInsightsFirst.length || response.answer.business_implications.length,
  )
  const tabs = workspaceTabs(hasTable, hasQuery || Boolean(calculation) || checks.length > 0, hasSources, Boolean(geo), hasAnalysis, hasVisualChart)
  // Opens on what the chat does not show: the fuller analysis, else the map, else the rows. The chart is one click away.
  const [tab, setTab] = useState<WorkspaceTab>(() => {
    const open = (id: WorkspaceTab) => tabs.some(item => item.id === id && !item.disabled)
    return (['summary', 'map', 'table', 'chart', 'query'] as WorkspaceTab[]).find(open) ?? tabs.find(item => !item.disabled)?.id ?? 'table'
  })
  const summarySame =
    response.answer.executive_summary.trim() === response.answer.direct_answer.trim()
  const chartTitle = response.chart_spec?.title || 'Visualization'
  const workspaceInsights = workspaceInsightsFirst
  return (
    <div>
      <WorkspaceTabBar tab={tab} tabs={tabs} onSelect={setTab} />

      {tab === 'summary' && (
        <div className="mt-6" role="tabpanel">
          {report && (
            <WorkspaceSection>
              <WorkspaceSectionHeader icon={FileText} tone="sky" title="Full analysis" />
              <WorkspaceSectionContent>
                <div data-testid="analysis-report">
                  <AnswerProse text={report} variant="support" />
                </div>
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}

          {!chatNarrativeShown && (
            <WorkspaceSection>
              <WorkspaceSectionHeader icon={FileText} tone="sky" title={sectionLabels.executiveSummary} />
              <WorkspaceSectionContent>
                <AnswerProse text={response.answer.direct_answer} omitTables={hasTable} variant="main" />
                {!summarySame && (
                  <AnswerProse text={response.answer.executive_summary} omitTables={response.strategy !== 'agent'} variant="support" />
                )}
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}

          {comparison && (
            <WorkspaceSection>
              <WorkspaceSectionHeader icon={ArrowLeftRight} tone="violet" title={sectionLabels.comparison} />
              <WorkspaceSectionContent>
                <ComparisonSummary response={response} />
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}

          {workspaceInsights.length > 0 && (
            <WorkspaceSection>
              <WorkspaceSectionHeader
                icon={Lightbulb}
                tone="amber"
                title={sectionLabels.keyFindings}
                action={
                  hasTable ? (
                    <button
                      type="button"
                      onClick={() => setTab('table')}
                      className="text-xs font-semibold text-cloudera-orange hover:underline"
                    >
                      View details →
                    </button>
                  ) : null
                }
              />
              <WorkspaceSectionContent>
                <ol className="space-y-4">
                  {workspaceInsights.map((item, index) => (
                    <InsightListItem key={item} index={index + 1}>
                      {item}
                    </InsightListItem>
                  ))}
                </ol>
              </WorkspaceSectionContent>
            </WorkspaceSection>
          )}

          {geo && (
            <p className="mt-4 text-xs text-slate-500 sm:ml-[calc(3rem+1rem)]">
              This result has provinces.{' '}
              <button type="button" onClick={() => setTab('map')} className="font-semibold text-cloudera-orange hover:underline">
                View it on the map →
              </button>
            </p>
          )}

          {!hasVisualChart && response.chart_spec?.type !== 'kpi' && hasTable && (
            <p className="mt-4 text-xs text-slate-500 sm:ml-[calc(3rem+1rem)]">
              No chart for this turn. Open the <strong className="font-semibold">Table</strong> tab for the full
              rows.
            </p>
          )}

          {response.answer.business_implications.length > 0 && (
            <WorkspaceSection className="!mt-5 !pt-9 pb-8">
              <WorkspaceSectionHeader icon={Briefcase} tone="violet" title={sectionLabels.implications} />
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

      {tab === 'chart' && hasVisualChart && response.chart_spec && (
        <div className="mt-6" role="tabpanel" data-testid="workspace-chart">
          <AnswerChart chart={response.chart_spec} rows={response.data.rows} metric={chartMetric(response)} overall={response.data.overall_value ?? null} className="!border-0 !p-0 !shadow-none" />
        </div>
      )}

      {tab === 'map' && geo && (
        <div className="mt-6" role="tabpanel">
          <ResultMap
            columns={response.data.columns}
            rows={response.data.rows}
            detection={geo}
            metric={response.data.governed_metric ?? undefined}
            unitFormat={response.data.unit_format ?? undefined}
          />
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
          <WorkspaceQueryView response={response} calculation={calculation} steps={checks} />
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
