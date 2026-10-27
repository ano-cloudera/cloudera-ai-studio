'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../../lib/apiError'
import type { AskDataSettingsPayload, SemanticModelRecord } from '../../types/api'

type Props = {
  settings: AskDataSettingsPayload
  onChange: (next: AskDataSettingsPayload) => void
}

export function AskDataGovernedScopeSettingsPanel({ settings, onChange }: Props) {
  const [models, setModels] = useState<SemanticModelRecord[]>([])
  const [error, setError] = useState<AppApiError | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const res = await api.listSemanticModels()
      const published = (res.models ?? []).filter(m => m.active_version_id)
      setModels(published)
    } catch (e) {
      setError(toAppApiError(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const pinned = settings.default_semantic_model_id ?? ''
  const autoAttach = settings.auto_attach_semantic_model !== false

  return (
    <div className="space-y-3 rounded-xl border border-slate-200/90 bg-slate-50/40 p-4">
      <div>
        <h3 className="text-sm font-semibold text-cloudera-navy">Governed scope (Genie-style)</h3>
        <p className="mt-1 text-xs text-slate-600">
          When Ask Data has no @ chip, the backend attaches a published semantic model automatically.
        </p>
      </div>
      {error ? <p className="text-xs text-rose-700">{safeErrorMessage(error)}</p> : null}
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={autoAttach}
          onChange={e => onChange({ ...settings, auto_attach_semantic_model: e.target.checked })}
        />
        Auto-attach semantic model when @ is omitted
      </label>
      <label className="block text-xs font-semibold text-slate-600">
        Space instructions (prompt key)
        <input
          type="text"
          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-cloudera-navy"
          placeholder="e.g. golden_banking_executive_summary"
          value={settings.instruction_prompt_key ?? ''}
          onChange={e =>
            onChange({
              ...settings,
              instruction_prompt_key: e.target.value.trim() || null,
            })
          }
        />
        <span className="mt-1 block font-normal text-slate-500">
          Optional Genie-style instructions resolved from Prompt Management and injected into governed answers.
        </span>
      </label>
      <label className="block text-xs font-semibold text-slate-600">
        Pinned semantic model
        <select
          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-cloudera-navy"
          value={pinned}
          disabled={!autoAttach}
          onChange={e =>
            onChange({
              ...settings,
              default_semantic_model_id: e.target.value || null,
            })
          }
        >
          <option value="">Use sole published model (if only one)</option>
          {models.map(m => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
