'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import {
  initSuggestionDecisions,
  labelForSuggestion,
  selectionsFromDecisions,
  SUGGESTION_SECTIONS,
  type SuggestionBucket,
  type SuggestionDecision,
  type SuggestionItem,
} from './semanticSuggestionsUi'

type Props = {
  open: boolean
  modelId: string
  versionId: string
  connectionId: string
  tables: string[]
  onClose: () => void
  onApplied: () => void
}

export function SemanticSuggestionsApplyModal({
  open,
  modelId,
  versionId,
  connectionId,
  tables,
  onClose,
  onApplied,
}: Props) {
  const [suggestions, setSuggestions] = useState<SuggestionBucket | null>(null)
  const [decisions, setDecisions] = useState<Record<string, SuggestionDecision>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const res = (await api.semanticSuggestions({
        connection_id: connectionId,
        tables,
      })) as SuggestionBucket
      setSuggestions(res)
      setDecisions(
        initSuggestionDecisions(res, {
          defaultAcceptedTypes: new Set(['metric', 'dimension', 'relationship', 'term']),
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load suggestions')
      setSuggestions(null)
      setDecisions({})
    } finally {
      setBusy(false)
    }
  }, [connectionId, tables])

  useEffect(() => {
    if (!open) return
    void load()
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
        {busy && !suggestions ? <p className="mt-4 text-sm text-slate-600">Loading suggestions…</p> : null}

        <div className="mt-3 space-y-3 text-sm">
          {SUGGESTION_SECTIONS.filter(s => s.type !== 'entity').map(section => {
            const items = (suggestions?.[section.key] as SuggestionItem[] | undefined) ?? []
            if (!items.length) return null
            return (
              <div key={section.key} className="rounded-lg border border-slate-100 p-3">
                <div className="text-xs font-semibold uppercase text-slate-500">{section.label}</div>
                <ul className="mt-2 space-y-2">
                  {items.map(item => {
                    const sid = String(item.suggestion_id ?? `${section.type}:${item.key}`)
                    const d = decisions[sid]
                    if (!d) return null
                    return (
                      <li key={sid} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-100 px-2 py-2">
                        <span className="font-medium">{labelForSuggestion({ ...item, ...d.edits })}</span>
                        <div className="flex gap-2 text-xs">
                          <button
                            type="button"
                            className={d.accepted ? 'font-semibold text-emerald-700' : 'text-slate-500'}
                            onClick={() => setDecision(sid, { accepted: true })}
                          >
                            Accept
                          </button>
                          <button
                            type="button"
                            className={!d.accepted ? 'font-semibold text-red-700' : 'text-slate-500'}
                            onClick={() => setDecision(sid, { accepted: false })}
                          >
                            Skip
                          </button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
          {suggestions && !Object.keys(decisions).some(k => decisions[k]?.type !== 'entity') ? (
            <p className="text-xs text-slate-500">No extra metrics or dimensions suggested for this table.</p>
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button type="button" className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-semibold" onClick={onClose} disabled={busy}>
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
