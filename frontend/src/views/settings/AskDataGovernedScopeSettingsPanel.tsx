'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../../lib/apiError'
import type { AskDataSettingsPayload, SemanticModelRecord } from '../../types/api'

type Props = {
  settings: AskDataSettingsPayload
  onChange: (next: AskDataSettingsPayload) => void
}

const AUTOMATIC = ''
const NONE = '__none__'

/** One choice that replaces the old "auto-attach" checkbox plus "pinned model" list. */
export function defaultModelChoice(settings: Pick<AskDataSettingsPayload, 'auto_attach_semantic_model' | 'default_semantic_model_id'>): string {
  if (settings.auto_attach_semantic_model === false) return NONE
  return settings.default_semantic_model_id ?? AUTOMATIC
}

export function applyDefaultModelChoice(settings: AskDataSettingsPayload, choice: string): AskDataSettingsPayload {
  if (choice === NONE) return { ...settings, auto_attach_semantic_model: false, default_semantic_model_id: null }
  return { ...settings, auto_attach_semantic_model: true, default_semantic_model_id: choice || null }
}

export function AskDataGovernedScopeSettingsPanel({ settings, onChange }: Props) {
  const [models, setModels] = useState<SemanticModelRecord[] | null>(null)
  const [error, setError] = useState<AppApiError | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const res = await api.listSemanticModels()
      setModels((res.models ?? []).filter(m => m.active_version_id))
    } catch (e) {
      setError(toAppApiError(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const choice = defaultModelChoice(settings)
  const published = models ?? []
  const savedModelMissing = models !== null && choice !== AUTOMATIC && choice !== NONE && !published.some(m => m.id === choice)

  return (
    <div className="space-y-2 rounded-xl border border-slate-200/90 bg-slate-50/40 p-4">
      <label className="block text-sm font-semibold text-cloudera-navy">
        Default semantic model
        <select
          className="app-select mt-1 w-full font-normal"
          value={choice}
          onChange={e => onChange(applyDefaultModelChoice(settings, e.target.value))}
        >
          <option value={AUTOMATIC}>Automatic: the published model (when there is only one)</option>
          {published.map(model => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))}
          {savedModelMissing ? <option value={choice}>A model that is no longer published</option> : null}
          <option value={NONE}>None: every question must start with an @ chip</option>
        </select>
        <span className="mt-1 block text-xs font-normal text-slate-600">
          A question that does not name a model with @ is answered with this one.
        </span>
      </label>
      {error ? <p className="text-xs text-rose-700">{safeErrorMessage(error)}</p> : null}
      {models !== null && published.length === 0 ? (
        <p className="text-xs text-amber-800" role="note">
          No semantic model is published yet. Publish one in the Semantic Layer, then pick it here.
        </p>
      ) : null}
      {models !== null && published.length > 1 && choice === AUTOMATIC ? (
        <p className="text-xs text-amber-800" role="note">
          {published.length} models are published, so “Automatic” cannot choose. Pick the one to use by default.
        </p>
      ) : null}
      {savedModelMissing ? (
        <p className="text-xs text-amber-800" role="note">
          The model chosen before is no longer published. Pick another one.
        </p>
      ) : null}
    </div>
  )
}
