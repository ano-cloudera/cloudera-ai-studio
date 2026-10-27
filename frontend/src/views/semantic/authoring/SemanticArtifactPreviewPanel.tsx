'use client'

import { useState } from 'react'
import type { SemanticArtifactPreview } from '../../../types/api'

type Props = {
  artifact: SemanticArtifactPreview | null
  loading?: boolean
  onRefresh?: () => void
  /** When true, show the full artifact body (Preview tab). */
  defaultExpanded?: boolean
}

export function SemanticArtifactPreviewPanel({ artifact, loading, onRefresh, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div className="flex flex-col gap-3 p-4" data-testid="semantic-artifact-preview-panel">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-cloudera-navy">Preview semantic artifact</h2>
          <p className="mt-1 text-xs text-slate-600">
            Generated from the current draft. This is not the active Ask Data runtime configuration.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {onRefresh ? (
            <button
              type="button"
              className="h-8 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700"
              disabled={loading}
              onClick={onRefresh}
            >
              Refresh preview
            </button>
          ) : null}
          <button
            type="button"
            className="h-8 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700"
            disabled={!artifact?.content_preview}
            onClick={() => {
              if (artifact?.content_preview) void navigator.clipboard.writeText(artifact.content_preview)
            }}
          >
            Copy
          </button>
          <button
            type="button"
            data-testid="semantic-artifact-toggle"
            className="h-8 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-cloudera-violet"
            disabled={!artifact?.content_preview}
            onClick={() => setExpanded(v => !v)}
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>
      {loading ? <p className="text-xs text-slate-500">Generating preview…</p> : null}
      {!artifact?.content_preview && !loading ? (
        <p className="text-sm text-slate-500">No preview yet. Use Refresh preview to generate from the current draft.</p>
      ) : null}
      {artifact?.content_preview ? (
        expanded ? (
          <pre
            data-testid="semantic-artifact-preview-content"
            className="max-h-[28rem] overflow-x-auto overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-800"
          >
            {artifact.content_preview}
          </pre>
        ) : (
          <p className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs text-slate-600">
            {artifact.content_preview.slice(0, 240)}
            {artifact.content_preview.length > 240 ? '…' : ''}
          </p>
        )
      ) : null}
    </div>
  )
}
