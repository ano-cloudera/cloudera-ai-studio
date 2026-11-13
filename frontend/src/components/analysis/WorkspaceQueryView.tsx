'use client'

import { useState } from 'react'
import { Check, Copy, ExternalLink } from 'lucide-react'
import { appConfig } from '../../config/appConfig'
import { mergeDataNotes, parseDataProvenance } from '../../lib/dataProvenance'
import type { AgentStepCard, CalculationNote, ChatResponse } from '../../types/api'
import { AgentSteps } from '../AgentSteps'
import { CalculationNoteRows } from '../chat/CalculationNoteBlock'
import { CollapsibleDataNote } from './CollapsibleDataNote'
import { formatSql } from '../../lib/formatSql'
import { WorkspaceSqlBlock } from './WorkspaceSqlBlock'

function resolveSources(dataReference: string, provenanceSources: string[]): string[] {
  const fromRef = (dataReference.match(/\b(?:gold|silver|bronze)\.[a-z0-9_]+/gi) ?? []).map(s =>
    s.toLowerCase(),
  )
  return [...new Set([...provenanceSources.map(s => s.toLowerCase()), ...fromRef])]
}

function lineageUrlForSource(source: string): string | null {
  const base = appConfig.viewLineageBaseUrl.trim()
  if (!base) return null
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}table=${encodeURIComponent(source)}`
}

type Props = {
  response: ChatResponse
  calculation?: CalculationNote | null
  /** The steps of an agent answer: shown as cards with their rows and queries, in place of the plain list. */
  steps?: AgentStepCard[]
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-2 py-1">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="min-w-0 text-sm text-slate-700">{children}</dd>
    </div>
  )
}

/** The Query tab: what was computed and how (one card), then the SQL that ran. */
export function WorkspaceQueryView({ response, calculation = null, steps = [] }: Props) {
  const [wrapLines, setWrapLines] = useState(true)
  const [copied, setCopied] = useState(false)
  const sql = response.governed_sql?.trim() ?? ''
  const engine = response.data.connector_type?.trim()
  const sourceName = response.data.connector_name?.trim()
  const provenance = parseDataProvenance(response.answer.data_reference)
  const dataNote = mergeDataNotes(response.answer.caveats, provenance)
  const sources = resolveSources(response.answer.data_reference.trim(), provenance?.sources ?? [])
  const governedLabel =
    response.data.governed_metric_display_name?.trim() ||
    (response.data.governed_metric ? response.data.governed_metric.replace(/_/g, ' ') : null)
  async function copySql() {
    if (!sql) return
    try {
      await navigator.clipboard.writeText(formatSql(sql))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  const executedOn = [engine, sourceName].filter(Boolean).join(' · ')
  const timing = response.data.execution_ms > 0 ? `${Math.round(response.data.execution_ms)} ms` : ''

  return (
    <div className="mt-6 space-y-5" data-testid="workspace-calculation">
      {calculation?.scope || calculation?.summary ? (
        <p className="text-sm text-slate-600">{calculation.scope ?? calculation.summary}</p>
      ) : null}
      <dl className="divide-y divide-slate-100 rounded-xl border border-slate-200/90 px-4 py-2">
        {calculation ? (
          <CalculationNoteRows note={calculation} hideSteps={steps.length > 0} />
        ) : (
          <>
            {governedLabel ? <Row label="Metric">{governedLabel}</Row> : null}
            {response.data.governed_metric_expression ? (
              <Row label="Formula">
                <code className="break-words font-mono text-xs">{response.data.governed_metric_expression}</code>
              </Row>
            ) : null}
            {response.data.governed_base_dataset ? <Row label="Source">{response.data.governed_base_dataset}</Row> : null}
          </>
        )}
        {executedOn || timing ? (
          <Row label="Executed on">
            {[executedOn ? `${executedOn}, read-only` : 'Read-only', timing].filter(Boolean).join(' · ')}
          </Row>
        ) : null}
      </dl>

      {steps.length > 0 ? (
        <div data-testid="query-steps">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Steps</p>
          <AgentSteps steps={steps} />
        </div>
      ) : null}

      {sql ? (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{steps.length > 0 ? 'SQL of the chart shown' : 'SQL'}</p>
            <div className="flex items-center gap-2">
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-medium text-slate-600">
                <input
                  type="checkbox"
                  checked={wrapLines}
                  onChange={e => setWrapLines(e.target.checked)}
                  className="rounded border-slate-300 text-cloudera-orange focus:ring-cloudera-orange/30"
                />
                Wrap lines
              </label>
              <button type="button" onClick={() => void copySql()} className="btn-secondary !px-2.5 !py-1 !text-xs">
                {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                {copied ? 'Copied' : 'Copy SQL'}
              </button>
            </div>
          </div>
          <WorkspaceSqlBlock sql={sql} wrapLines={wrapLines} />
        </div>
      ) : (
        <p className="text-sm text-slate-500">SQL text was not returned for this turn.</p>
      )}

      <div className="space-y-3">
        <CollapsibleDataNote note={dataNote} />

        {sources.length > 0 && appConfig.viewLineageBaseUrl.trim() ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Lineage</p>
            <ul className="mt-2 space-y-2">
              {sources.map(source => {
                const lineage = lineageUrlForSource(source)
                return (
                  <li key={source} className="flex flex-wrap items-center gap-2">
                    <code className="inline-block max-w-full break-all rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-slate-700">
                      {source}
                    </code>
                    {lineage ? (
                      <a
                        href={lineage}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-semibold text-cloudera-orange hover:underline"
                      >
                        View lineage
                        <ExternalLink size={12} />
                      </a>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  )
}
