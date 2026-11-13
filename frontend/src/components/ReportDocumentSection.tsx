'use client'

import { formatBusinessValue, rememberColumnLabels } from '../lib/businessPresentation'
import { chartMetric } from '../lib/chartMetric'
import { answerSectionLabels } from '../lib/answerSectionLabels'

import { useMemo, useState } from 'react'
import { ArrowLeftRight, BarChart3, Briefcase, FileText, Lightbulb } from 'lucide-react'
import {
  InsightListItem,
  WorkspaceSection,
  WorkspaceSectionContent,
  WorkspaceSectionHeader,
} from './analysis/WorkspaceSectionParts'
import { AgentSteps } from './AgentSteps'
import { AnswerChart } from './AnswerChart'
import { AnswerProse } from './AnswerProse'
import { WorkspaceDataTable } from './analysis/WorkspaceDataTable'
import { WorkspaceQueryView } from './analysis/WorkspaceQueryView'
import { ResultMap } from './analysis/ResultMap'
import { KpiCard } from './KpiCard'
import { ComparisonSummary, comparisonKind } from './analysis/ComparisonSummary'
import { detectGeo } from '../lib/geo'
import { formatCitationLabel, isRagResponse } from '../lib/ragReport'
import type { ChatResponse } from '../types/api'

type WorkspaceTab = 'summary' | 'map' | 'table' | 'query' | 'sources' | 'checks'

type GroupStanding = { group: string; value: number; difference: number }

/**
 * Where every group stands against the overall value, worked out from the rows (not written by the model): the detail the
 * chat leaves out ("3 of 8 above"), and the same facts the answer's words are checked against.
 */
export function standingsAgainstOverall(response: ChatResponse): { overall: number; above: GroupStanding[]; below: GroupStanding[] } | null {
  const overall = response.data.overall_value
  const rows = response.data.rows
  if (typeof overall !== 'number' || rows.length < 2 || !response.data.columns.includes('metric_value')) return null
  const labelColumn = response.data.columns.find(column => column !== 'metric_value' && rows.every(row => typeof row[column] !== 'number'))
  if (!labelColumn) return null
  const standings = rows
    .filter(row => typeof row.metric_value === 'number')
    .map(row => ({ group: String(row[labelColumn] ?? ''), value: row.metric_value as number, difference: (row.metric_value as number) - overall }))
    .sort((a, b) => b.value - a.value)
  if (standings.length < 2) return null
  return { overall, above: standings.filter(s => s.difference > 0), below: standings.filter(s => s.difference < 0) }
}

function GroupStandings({ response, standings }: { response: ChatResponse; standings: NonNullable<ReturnType<typeof standingsAgainstOverall>> }) {
  const unit = response.data.unit_format ?? undefined
  const show = (n: number) => formatBusinessValue('metric_value', n, response.data.governed_metric ?? undefined, unit)
  const gap = (n: number) => (unit === 'percent' ? `${n > 0 ? '+' : '-'}${Number(Math.abs(n).toFixed(2))} pts` : `${n > 0 ? '+' : '-'}${show(Math.abs(n))}`)
  const total = standings.above.length + standings.below.length
  const list = (title: string, items: GroupStanding[]) =>
    items.length > 0 ? (
      <div>
        <p className="text-sm font-semibold text-cloudera-navy">
          {title} <span className="font-normal text-slate-600">({items.length} of {total})</span>
        </p>
        <ul className="mt-1.5 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {items.map(item => (
            <li key={item.group} className="flex items-baseline justify-between gap-3 px-3 py-1.5 text-sm">
              <span className="min-w-0 truncate text-slate-700">{item.group}</span>
              <span className="shrink-0 tabular-nums text-slate-600">
                {show(item.value)} <span className="font-semibold text-slate-800">{gap(item.difference)}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    ) : null
  return (
    <div className="space-y-3" data-testid="group-standings">
      <p className="workspace-body-text">Overall value across all groups: <strong className="font-semibold text-cloudera-navy">{show(standings.overall)}</strong></p>
      <div className="grid gap-4 xl:grid-cols-2">
        {list('Above overall', standings.above)}
        {list('Below overall', standings.below)}
      </div>
    </div>
  )
}

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
  hasChecks = false,
  hasAnalysis = true,
): { id: WorkspaceTab; label: string; disabled?: boolean }[] {
  const tabs: { id: WorkspaceTab; label: string; disabled?: boolean }[] = hasAnalysis ? [{ id: 'summary', label: 'Analysis' }] : []
  if (hasSources) tabs.push({ id: 'sources', label: 'Sources' })
  if (hasMap) tabs.push({ id: 'map', label: 'Map' })
  if (hasChecks) tabs.push({ id: 'checks', label: 'Checks' })
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
  const kpiField = response.chart_spec?.type === 'kpi' ? response.chart_spec.y || response.data.columns[0] : null
  const kpiValue = kpiField ? response.data.rows[0]?.[kpiField] : undefined
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
  const standings = rag || report ? null : standingsAgainstOverall(response)
  const workspaceInsightsFirst = response.answer.insights.filter(item => item.trim()).slice(chatInsightCount)
  const chartInPanel = !chartShownInChat && (response.chart_spec?.type === 'kpi' || hasVisualChart)
  const hasAnalysis = Boolean(
    report || standings || !chatNarrativeShown || comparison || workspaceInsightsFirst.length || chartInPanel || response.answer.business_implications.length,
  )
  const tabs = workspaceTabs(hasTable, hasQuery || Boolean(calculation), hasSources, Boolean(geo), checks.length > 0, hasAnalysis)
  const [tab, setTab] = useState<WorkspaceTab>(() => tabs.find(item => !item.disabled)?.id ?? 'table')
  const summarySame =
    response.answer.executive_summary.trim() === response.answer.direct_answer.trim()
  const chartTitle = response.chart_spec?.title || 'Visualization'
  const workspaceInsights = workspaceInsightsFirst
  return (
    <div>
      <WorkspaceTabBar tab={tab} tabs={tabs} onSelect={setTab} />

      {tab === 'checks' && (
        <div className="mt-6" role="tabpanel">
          <AgentSteps steps={checks} />
        </div>
      )}

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

          {standings && (
            <WorkspaceSection>
              <WorkspaceSectionHeader icon={ArrowLeftRight} tone="violet" title="How each group compares" />
              <WorkspaceSectionContent>
                <GroupStandings response={response} standings={standings} />
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

          {chartInPanel && (
            <WorkspaceSection>
              <WorkspaceSectionHeader
                icon={BarChart3}
                tone="orange"
                title={chartTitle}
                action={null}
              />
              <WorkspaceSectionContent className="pb-4">
                {response.chart_spec?.type === 'kpi' && (
                  <div className="max-w-sm">
                    <KpiCard label={response.chart_spec.title} value={kpiValue} format="" icon={BarChart3} />
                  </div>
                )}
                {hasVisualChart && response.chart_spec && (
                  <AnswerChart chart={response.chart_spec} rows={response.data.rows} embedded hideTitle metric={chartMetric(response)} />
                )}
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
          <WorkspaceQueryView response={response} calculation={calculation} />
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
