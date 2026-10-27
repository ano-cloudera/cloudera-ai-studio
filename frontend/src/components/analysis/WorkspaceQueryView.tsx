'use client'

import { useState } from 'react'
import { Check, Copy, Database, ExternalLink } from 'lucide-react'
import { appConfig } from '../../config/appConfig'
import { mergeDataNotes, parseDataProvenance } from '../../lib/dataProvenance'
import type { ChatResponse } from '../../types/api'
import { CollapsibleDataNote } from './CollapsibleDataNote'
import { WorkspaceSqlBlock } from './WorkspaceSqlBlock'
import { WorkspaceSection, WorkspaceSectionContent, WorkspaceSectionHeader } from './WorkspaceSectionParts'

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
}

export function WorkspaceQueryView({ response }: Props) {
  const [wrapLines, setWrapLines] = useState(true)
  const [copied, setCopied] = useState(false)
  const sql = response.governed_sql?.trim() ?? ''
  const engine = response.data.connector_type?.trim()
  const sourceName = response.data.connector_name?.trim()
  const provenance = parseDataProvenance(response.answer.data_reference)
  const dataNote = mergeDataNotes(response.answer.caveats, provenance)
  const sources = resolveSources(response.answer.data_reference.trim(), provenance?.sources ?? [])
  async function copySql() {
    if (!sql) return
    try {
      await navigator.clipboard.writeText(sql)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="mt-6 space-y-5">
      <WorkspaceSection className="first:pt-0">
        <WorkspaceSectionHeader icon={Database} tone="slate" title="Governed query" />
        <WorkspaceSectionContent>
          <p className="workspace-body-text">
            Read-only SQL executed against the governed semantic layer
            {engine ? ` (${engine}${sourceName ? ` · ${sourceName}` : ''})` : ' datasource'}.
          </p>
          {response.data.execution_ms > 0 ? (
            <p className="mt-1 text-xs text-slate-500">Execution: {Math.round(response.data.execution_ms)} ms</p>
          ) : null}
        </WorkspaceSectionContent>
      </WorkspaceSection>

      {sql ? (
        <div className="sm:ml-[calc(3rem+1rem)] lg:ml-[calc(3rem+1.125rem)]">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">SQL</p>
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
        <p className="text-sm text-slate-500 sm:ml-[calc(3rem+1rem)]">SQL text was not returned for this turn.</p>
      )}

      <div className="space-y-3 sm:ml-[calc(3rem+1rem)] lg:ml-[calc(3rem+1.125rem)]">
        <CollapsibleDataNote note={dataNote} />

        {sources.length > 0 ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Source</p>
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
