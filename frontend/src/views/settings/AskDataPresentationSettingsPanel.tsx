'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { mergePresentationTierConfig, type PresentationTierConfig } from '../../lib/presentationTierConfig'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../../lib/apiError'
import type { AskDataSettingsPayload, PresentationTierOverridesPayload } from '../../types/api'

const PANEL_MODES = [
  { value: 'heuristic', label: 'Heuristic (tier 3 only)' },
  { value: 'always', label: 'Always open workspace' },
  { value: 'never', label: 'Never auto-open' },
] as const

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

const DEFAULT_PRESENTATION: PresentationTierConfig = {
  enabled: true,
  audience_mode: 'executive',
  panel_auto_open: 'heuristic',
  tier3_min_rows: 13,
  tier3_min_insights: 3,
  tier3_min_implications: 2,
  rank_tier3_above_n: 5,
  rank_min_tier: 2,
  tier1_max_rows: 1,
  tier1_max_columns: 2,
  force_tier3_on_pareto: true,
  force_tier3_on_operational_analysis: true,
  force_tier3_on_visual_chart: true,
  chat_expand_tier1: true,
  chat_expand_tier2: true,
  chat_details_default_open: false,
  tier1_show_narrative: false,
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

  return (
    <div className="space-y-4 border-t border-slate-100 pt-6">
      <div>
        <h2 className="text-[15px] font-semibold text-cloudera-navy">Ask Data — presentation tier</h2>
        <p className="type-chat-meta mt-1 text-slate-500">
          Workspace overrides for chat vs Analysis Workspace (AMP). Deployment env remains the default baseline.
        </p>
      </div>

      <label className="block text-sm font-medium text-slate-700">
        Audience
        <select
          className="app-select mt-1 w-full max-w-md"
          value={draft.audience_mode}
          onChange={e =>
            setDraft(d => ({
              ...d,
              audience_mode: e.target.value as PresentationTierConfig['audience_mode'],
            }))
          }
        >
          <option value="executive">Executive — minimal technical chrome</option>
          <option value="analyst">Analyst — full metadata, SQL, workspace links</option>
        </select>
      </label>

      <label className="block text-sm font-medium text-slate-700">
        Auto-open panel
        <select
          className="app-select mt-1 w-full max-w-md"
          value={draft.panel_auto_open}
          onChange={e =>
            setDraft(d => ({
              ...d,
              panel_auto_open: e.target.value as PresentationTierConfig['panel_auto_open'],
            }))
          }
        >
          {PANEL_MODES.map(mode => (
            <option key={mode.value} value={mode.value}>
              {mode.label}
            </option>
          ))}
        </select>
      </label>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block text-sm font-medium text-slate-700">
          Tier 3 min rows
          <input
            type="number"
            min={1}
            max={1000}
            className="input mt-1"
            value={draft.tier3_min_rows}
            onChange={e => setDraft(d => ({ ...d, tier3_min_rows: Number(e.target.value) || 1 }))}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Rank → tier 3 above N
          <input
            type="number"
            min={0}
            max={500}
            className="input mt-1"
            value={draft.rank_tier3_above_n}
            onChange={e => setDraft(d => ({ ...d, rank_tier3_above_n: Number(e.target.value) || 0 }))}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Rank min tier
          <select
            className="app-select mt-1 w-full"
            value={draft.rank_min_tier}
            onChange={e =>
              setDraft(d => ({
                ...d,
                rank_min_tier: Number(e.target.value) as 1 | 2 | 3,
              }))
            }
          >
            <option value={1}>1</option>
            <option value={2}>2</option>
            <option value={3}>3</option>
          </select>
        </label>
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={draft.chat_details_default_open}
          onChange={e => setDraft(d => ({ ...d, chat_details_default_open: e.target.checked }))}
        />
        Expand data/query footer by default (tier 1–2)
      </label>

      <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={draft.tier1_show_narrative}
          onChange={e => setDraft(d => ({ ...d, tier1_show_narrative: e.target.checked }))}
        />
        Show narrative on simple KPI answers (tier 1) — executive summary &amp; insights below the headline
      </label>

      {banner ? <p className="type-chat-meta text-emerald-700">{banner}</p> : null}
      {error ? <p className="type-chat-meta text-rose-700">{safeErrorMessage(error)}</p> : null}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={!dirty || saving} onClick={() => void save()}>
          {saving ? 'Saving…' : 'Save presentation settings'}
        </button>
        {dirty ? <p className="type-chat-meta text-slate-500">Unsaved changes</p> : null}
      </div>
    </div>
  )
}
