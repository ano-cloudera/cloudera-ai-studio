'use client'

import { useState } from 'react'
import { appConfig } from '../../config/appConfig'
import { api } from '../../lib/api'
import { safeErrorMessage } from '../../lib/apiError'
import {
  FEATURE_LABELS,
  FEATURE_NOTES,
  LOCKED_FEATURES,
  LOCKED_NOTES,
  SWITCHABLE_FEATURES,
  setFeatureOverrides,
  useFeatureOverrides,
  type FeatureKey,
  type FeatureOverrides,
} from '../../lib/featureOverrides'

/** Display order of the menu. AI Models is also always on but has no row of its own. */
const ORDER: FeatureKey[] = ['askData', 'documents', 'prompts', 'skills', 'semanticLayer', 'connectors', 'usage', 'settings']

/** The overrides after switching one feature: a value equal to the deployment default needs no override. */
export function nextOverrides(current: FeatureOverrides, key: FeatureKey, on: boolean, defaults: Record<FeatureKey, boolean>): FeatureOverrides {
  const next = { ...current }
  if (on === defaults[key]) delete next[key]
  else next[key] = on
  return next
}

export function FeaturesSettingsPanel() {
  const overrides = useFeatureOverrides()
  const defaults = appConfig.deploymentFeatures
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function save(next: FeatureOverrides) {
    setBusy(true)
    setError('')
    const previous = overrides
    setFeatureOverrides(next) // shown at once; put back if the server refuses
    try {
      const res = await api.putFeatureOverrides(next)
      setFeatureOverrides(res.overrides)
    } catch (err) {
      setFeatureOverrides(previous)
      setError(safeErrorMessage(err, 'The change could not be saved'))
    } finally {
      setBusy(false)
    }
  }

  const changed = SWITCHABLE_FEATURES.some(key => overrides[key] !== undefined)

  return (
    <>
      <h2 className="text-[15px] font-semibold text-cloudera-navy">Features</h2>
      <p className="text-sm text-slate-600">
        Switch menus and pages on or off for this workspace. The deployment decides the starting point; a change here applies at once to everyone.
      </p>
      <p className="type-chat-meta text-slate-500">This hides menus and pages. It does not restrict access to the API behind them.</p>

      <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200" data-testid="feature-list">
        {ORDER.map(key => {
          const locked = LOCKED_FEATURES.includes(key)
          const on = appConfig.features[key]
          const overridden = !locked && overrides[key] !== undefined
          return (
            <li key={key} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div className="min-w-0">
                <span className="font-medium text-cloudera-navy">{FEATURE_LABELS[key]}</span>
                {overridden ? (
                  <span className="ml-2 rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-orange-800">
                    Changed from default ({defaults[key] ? 'On' : 'Off'})
                  </span>
                ) : null}
                {!locked && FEATURE_NOTES[key] ? <p className="type-chat-meta mt-0.5 text-slate-500">{FEATURE_NOTES[key]}</p> : null}
                {locked && LOCKED_NOTES[key] ? <p className="type-chat-meta mt-0.5 text-slate-500">{LOCKED_NOTES[key]}</p> : null}
              </div>
              {locked ? (
                <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">Always on</span>
              ) : (
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={`${FEATURE_LABELS[key]} ${on ? 'on' : 'off'}`}
                  disabled={busy}
                  onClick={() => void save(nextOverrides(overrides, key, !on, defaults))}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-60 ${on ? 'bg-emerald-500' : 'bg-slate-300'}`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[1.375rem]' : 'left-0.5'}`} />
                </button>
              )}
            </li>
          )
        })}
      </ul>

      {error ? (
        <p className="mt-3 text-sm text-rose-700" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mt-4">
        <button type="button" className="btn-secondary px-4 py-2 text-sm" disabled={!changed || busy} onClick={() => void save({})}>
          Reset to deployment defaults
        </button>
      </div>
    </>
  )
}
