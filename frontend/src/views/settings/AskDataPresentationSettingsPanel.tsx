'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { mergePresentationTierConfig, type PresentationTierConfig } from '../../lib/presentationTierConfig'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../../lib/apiError'
import type { AskDataSettingsPayload, PresentationTierOverridesPayload } from '../../types/api'
import {
  DEFAULT_PRESENTATION,
  PREVIEW_SAMPLES,
  PRESETS,
  applyPreset,
  presetOf,
  previewOutcome,
} from '../../lib/presentationPresets'

function overridesFromConfig(cfg: PresentationTierConfig): PresentationTierOverridesPayload {
  return {
    audience_mode: cfg.audience_mode,
    panel_auto_open: cfg.panel_auto_open,
    tier3_min_rows: cfg.tier3_min_rows,
    tier3_min_insights: cfg.tier3_min_insights,
    tier3_min_implications: cfg.tier3_min_implications,
    rank_tier3_above_n: cfg.rank_tier3_above_n,
    rank_min_tier: cfg.rank_min_tier,
    tier1_max_rows: cfg.tier1_max_rows,
    tier1_max_columns: cfg.tier1_max_columns,
    chat_details_default_open: cfg.chat_details_default_open,
    chat_expand_tier1: cfg.chat_expand_tier1,
    chat_expand_tier2: cfg.chat_expand_tier2,
    tier1_show_narrative: cfg.tier1_show_narrative,
  }
}

export const DEFAULT_ASK_DATA_GOVERNED_SCOPE = {
  default_semantic_model_id: null as string | null,
  auto_attach_semantic_model: true,
}

export function AskDataPresentationSettingsPanel() {
  const [baseSettings, setBaseSettings] = useState<AskDataSettingsPayload | null>(null)
  const [draft, setDraft] = useState<PresentationTierConfig>(DEFAULT_PRESENTATION)
  const [saved, setSaved] = useState<PresentationTierConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<AppApiError | null>(null)
  const [banner, setBanner] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [settingsRes, configRes] = await Promise.all([
        api.getAskDataSettings(),
        api.askDataPresentationConfig(),
      ])
      setBaseSettings(settingsRes.settings)
      const effective = configRes.presentation
      setDraft(effective)
      setSaved(effective)
      mergePresentationTierConfig(effective)
    } catch (e) {
      setError(toAppApiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const dirty = saved != null && JSON.stringify(draft) !== JSON.stringify(saved)

  async function save() {
    if (!baseSettings) return
    setSaving(true)
    setBanner('')
    setError(null)
    try {
      const body: AskDataSettingsPayload = {
        ...baseSettings,
        presentation: overridesFromConfig(draft),
      }
      await api.putAskDataSettings(body)
      const configRes = await api.askDataPresentationConfig()
      setDraft(configRes.presentation)
      setSaved(configRes.presentation)
      mergePresentationTierConfig(configRes.presentation)
      setBanner('Presentation settings saved for this workspace.')
    } catch (e) {
      setError(toAppApiError(e))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="type-chat-body text-slate-500">Loading presentation settings…</p>
  }

  if (error && !saved) {
    return (
      <div className="space-y-3 rounded-xl border border-rose-100 bg-rose-50/80 px-4 py-3">
        <p className="type-chat-body text-rose-900">{safeErrorMessage(error)}</p>
        <button type="button" className="btn-secondary py-2 text-xs" onClick={() => void load()}>
          Retry
        </button>
      </div>
    )
  }

  const preset = presetOf(draft)
  const atDefaults = JSON.stringify(overridesFromConfig(draft)) === JSON.stringify(overridesFromConfig(DEFAULT_PRESENTATION))

  return (
    <div className="space-y-6 border-t border-slate-100 pt-6">
      <div>
        <h2 className="text-[15px] font-semibold text-cloudera-navy">How answers are shown</h2>
        <p className="type-chat-meta mt-1 text-slate-500">
          Chooses how much of an Ask Data answer appears in the chat and when the full analysis panel opens. It applies to everyone in this
          workspace.
        </p>
      </div>

      <section aria-labelledby="presentation-presets" className="space-y-2">
        <h3 id="presentation-presets" className="text-sm font-semibold text-slate-800">
          Start from a preset
        </h3>
        <div className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-labelledby="presentation-presets">
          {PRESETS.map(item => {
            const active = preset === item.id
            return (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setDraft(d => applyPreset(d, item.id))}
                className={`rounded-xl border px-4 py-3 text-left transition-colors ${
                  active ? 'border-cloudera-orange bg-orange-50/60' : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <span className="block text-sm font-semibold text-cloudera-navy">{item.title}</span>
                <span className="mt-1 block text-xs text-slate-600">{item.description}</span>
              </button>
            )
          })}
        </div>
        {preset === 'custom' ? <p className="type-chat-meta text-slate-500">Your choices below do not match a preset, so they are shown as custom.</p> : null}
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <label className="block text-sm font-medium text-slate-700">
          Who reads the answers?
          <select
            className="app-select mt-1 w-full"
            value={draft.audience_mode}
            onChange={e => setDraft(d => ({ ...d, audience_mode: e.target.value as PresentationTierConfig['audience_mode'] }))}
          >
            <option value="executive">Executives</option>
            <option value="analyst">Analysts</option>
          </select>
          <span className="mt-1 block text-xs font-normal text-slate-500">
            {draft.audience_mode === 'executive'
              ? 'Plain wording; technical details stay out of the way.'
              : 'Shows the metadata, the SQL and links to the workspace.'}
          </span>
        </label>

        <label className="block text-sm font-medium text-slate-700">
          When does the analysis panel open?
          <select
            className="app-select mt-1 w-full"
            value={draft.panel_auto_open}
            onChange={e => setDraft(d => ({ ...d, panel_auto_open: e.target.value as PresentationTierConfig['panel_auto_open'] }))}
          >
            <option value="heuristic">Automatically, for bigger answers (recommended)</option>
            <option value="always">Always</option>
            <option value="never">Never (open it yourself)</option>
          </select>
          <span className="mt-1 block text-xs font-normal text-slate-500">The panel holds the chart, the table and the SQL.</span>
        </label>

      </section>

      <section className="space-y-2">
        <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={draft.chat_details_default_open}
            onChange={e => setDraft(d => ({ ...d, chat_details_default_open: e.target.checked }))}
          />
          <span>Show the table and SQL under each answer, without clicking</span>
        </label>
        <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={draft.tier1_show_narrative}
            onChange={e => setDraft(d => ({ ...d, tier1_show_narrative: e.target.checked }))}
          />
          <span>Add a short explanation under answers that are a single number</span>
        </label>
      </section>

      <section aria-labelledby="presentation-preview" className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
        <h3 id="presentation-preview" className="text-sm font-semibold text-slate-800">
          What you will see
        </h3>
        <p className="type-chat-meta mt-0.5 text-slate-500">Updates as you change the settings above, before you save.</p>
        <ul className="mt-3 space-y-2 text-sm">
          {PREVIEW_SAMPLES.map(item => (
            <li key={item.title} className="grid gap-1 sm:grid-cols-[14rem_minmax(0,1fr)]">
              <span className="font-medium text-slate-800">{item.title}</span>
              <span className="text-slate-600">{previewOutcome(item.response, draft)}</span>
            </li>
          ))}
        </ul>
      </section>

      {banner ? <p className="type-chat-meta text-emerald-700">{banner}</p> : null}
      {error ? <p className="type-chat-meta text-rose-700">{safeErrorMessage(error)}</p> : null}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={!dirty || saving} onClick={() => void save()}>
          {saving ? 'Saving…' : 'Save for this workspace'}
        </button>
        <button type="button" className="btn-secondary px-4 py-2 text-sm" disabled={atDefaults} onClick={() => setDraft(d => ({ ...d, ...overridesFromConfig(DEFAULT_PRESENTATION) }) as PresentationTierConfig)}>
          Reset to defaults
        </button>
        {dirty ? <p className="type-chat-meta text-slate-500">Unsaved changes</p> : null}
      </div>
    </div>
  )
}
