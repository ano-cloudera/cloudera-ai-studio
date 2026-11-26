'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { SuggestionReview } from './SuggestionReview'
import {
  DraftCancelled,
  draftSuggestions,
  initSuggestionDecisions,
  rememberedDraftLanguage,
  remapEntityKey,
  selectionsFromDecisions,
  type SuggestionBucket,
  type SuggestionDecision,
} from './semanticSuggestionsUi'

type Props = {
  open: boolean
  modelId: string
  versionId: string
  connectionId: string
  tables: string[]
  /** The key the table was imported under; the draft's suggestions are pointed at it. */
  entityKey?: string
  onClose: () => void
  onApplied: () => void
}

export function SemanticSuggestionsApplyModal({
  open,
  modelId,
  versionId,
  connectionId,
  tables,
  entityKey,
  onClose,
  onApplied,
}: Props) {
  const [suggestions, setSuggestions] = useState<SuggestionBucket | null>(null)
  const [decisions, setDecisions] = useState<Record<string, SuggestionDecision>>({})
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('')
  const [error, setError] = useState('')
  const run = useRef(0)

  const load = useCallback(async () => {
    const mine = ++run.current
    setBusy(true)
    setError('')
    setStage('Starting')
    try {
      let res = await draftSuggestions(
        { connection_id: connectionId, tables, language: rememberedDraftLanguage() },
        next => {
          if (mine === run.current) setStage(next)
        },
        { cancelled: () => mine !== run.current },
      )
      if (mine !== run.current) return
      const drafted = res.entities?.[0]?.key
      if (entityKey && typeof drafted === 'string') res = remapEntityKey(res, drafted, entityKey)
      setSuggestions(res)
      setDecisions(
        initSuggestionDecisions(res, {
          defaultAcceptedTypes: new Set(['metric', 'dimension', 'relationship', 'term']),
        }),
      )
    } catch (err) {
      if (err instanceof DraftCancelled || mine !== run.current) return
      setError(err instanceof Error ? err.message : 'Could not load suggestions')
      setSuggestions(null)
      setDecisions({})
    } finally {
      if (mine === run.current) {
        setBusy(false)
        setStage('')
      }
    }
  }, [connectionId, tables, entityKey])

  useEffect(() => {
    if (!open) return
    void load()
    return () => {
      run.current += 1 // closing stops the polling
    }
  }, [open, load])

  if (!open) return null

  function setDecision(sid: string, patch: Partial<SuggestionDecision>) {
    setDecisions(prev => ({ ...prev, [sid]: { ...prev[sid], ...patch } }))
  }

  async function apply() {
    setBusy(true)
    setError('')
    try {
      await api.acceptSemanticSuggestions(modelId, {
        version_id: versionId,
        selections: selectionsFromDecisions(decisions),
      })
      onApplied()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Apply failed')
    } finally {
      setBusy(false)
    }
  }

  const hasSelectable = Object.values(decisions).some(d => d.type !== 'entity' && d.accepted)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-label="Apply suggestions">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-4 shadow-xl" data-testid="semantic-suggestions-apply-modal">
        <h2 className="text-lg font-semibold text-cloudera-navy">Suggested metrics &amp; dimensions</h2>
        <p className="mt-1 text-xs text-slate-600">
          Data model imported. Accept recommendations for this table (data model already created).
        </p>
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
        {busy && !suggestions ? (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700" role="status">
            <span className="font-semibold">Loading suggestions…</span> {stage && stage !== 'Starting' ? stage : null}
            <span className="mt-0.5 block text-slate-500">The table is profiled and every suggested metric is run once on the data.</span>
          </div>
        ) : null}

        {suggestions ? (
          <div className="mt-3">
            <SuggestionReview
              bucket={suggestions}
              decisions={decisions}
              onDecision={setDecision}
              types={['metric', 'dimension', 'relationship', 'term']}
              rejectLabel="Skip"
            />
            {!Object.keys(decisions).some(k => decisions[k]?.type !== 'entity') ? (
              <p className="mt-2 text-xs text-slate-500">No extra metrics or dimensions suggested for this table.</p>
            ) : null}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button type="button" className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-semibold" onClick={onClose} disabled={busy && !!suggestions}>
            Skip for now
          </button>
          <button
            type="button"
            className="btn-primary h-9 px-3 text-sm"
            disabled={busy || !hasSelectable}
            onClick={() => void apply()}
          >
            Apply selected
          </button>
        </div>
      </div>
    </div>
  )
}
