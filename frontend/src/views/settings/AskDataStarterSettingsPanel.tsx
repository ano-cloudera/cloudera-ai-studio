'use client'

import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api } from '../../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../../lib/apiError'
import type { AskDataSettingsPayload, StarterSource } from '../../types/api'
import { AskDataGovernedScopeSettingsPanel } from './AskDataGovernedScopeSettingsPanel'

const MAX_QUESTIONS = 6

const EMPTY_DRAFT: AskDataSettingsPayload = {
  starter_questions_caption: 'Start with a question',
  starter_questions: ['', '', ''],
  starter_source: 'configured',
  question_bank_limit: 3,
  question_bank_domain: null,
  question_bank_difficulty: null,
  auto_attach_semantic_model: true,
  default_semantic_model_id: null,
}

export function AskDataStarterSettingsPanel() {
  const [draft, setDraft] = useState<AskDataSettingsPayload>(EMPTY_DRAFT)
  const [saved, setSaved] = useState<AskDataSettingsPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<AppApiError | null>(null)
  const [banner, setBanner] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getAskDataSettings()
      const settings = response.settings
      const normalized: AskDataSettingsPayload = {
        ...settings,
        starter_questions:
          settings.starter_questions.length > 0
            ? settings.starter_questions
            : ['', '', ''],
      }
      setDraft(normalized)
      setSaved(normalized)
    } catch (e) {
      setError(toAppApiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const dirty =
    saved != null &&
    JSON.stringify(payloadForSave(draft)) !== JSON.stringify(payloadForSave(saved))

  function payloadForSave(value: AskDataSettingsPayload): AskDataSettingsPayload {
    const questions = value.starter_questions.map(q => q.trim()).filter(Boolean)
    return {
      ...value,
      starter_questions_caption: value.starter_questions_caption.trim() || 'Start with a question',
      starter_questions: questions,
      presentation: value.presentation ?? saved?.presentation ?? null,
    }
  }

  async function save() {
    setSaving(true)
    setBanner('')
    setError(null)
    try {
      const body = payloadForSave(draft)
      const response = await api.putAskDataSettings(body)
      const next: AskDataSettingsPayload = {
        ...response.settings,
        starter_questions:
          response.settings.starter_questions.length > 0
            ? response.settings.starter_questions
            : ['', '', ''],
      }
      setDraft(next)
      setSaved(next)
      setBanner('Starter questions saved. New Ask Data sessions will use these prompts.')
    } catch (e) {
      setError(toAppApiError(e))
    } finally {
      setSaving(false)
    }
  }

  function setSource(source: StarterSource) {
    setDraft(d => ({ ...d, starter_source: source }))
  }

  function updateQuestion(index: number, text: string) {
    setDraft(d => {
      const next = [...d.starter_questions]
      next[index] = text
      return { ...d, starter_questions: next }
    })
  }

  function addQuestion() {
    setDraft(d => {
      if (d.starter_questions.length >= MAX_QUESTIONS) return d
      return { ...d, starter_questions: [...d.starter_questions, ''] }
    })
  }

  function removeQuestion(index: number) {
    setDraft(d => ({
      ...d,
      starter_questions: d.starter_questions.filter((_, i) => i !== index),
    }))
  }

  if (loading) {
    return <p className="type-chat-body text-slate-500">Loading Ask Data settings…</p>
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
        <h2 className="text-[15px] font-semibold text-cloudera-navy">Ask Data — starter questions</h2>
        <p className="type-chat-meta mt-1 text-slate-500">
          Shown on an empty chat. Leave blank to hide the section. Saved per workspace (not random demo defaults).
        </p>
      </div>

      <label className="block text-sm font-medium text-slate-700">
        Section caption
        <input
          className="input mt-1"
          value={draft.starter_questions_caption}
          onChange={e => setDraft(d => ({ ...d, starter_questions_caption: e.target.value }))}
          maxLength={120}
        />
      </label>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-700">Source</legend>
        <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-600">
          <input
            type="radio"
            name="starter_source"
            checked={draft.starter_source === 'configured'}
            onChange={() => setSource('configured')}
            className="mt-1"
          />
          <span>
            <span className="font-medium text-slate-800">Custom list</span> — use the questions below in order (up to {MAX_QUESTIONS}).
          </span>
        </label>
        <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-600">
          <input
            type="radio"
            name="starter_source"
            checked={draft.starter_source === 'question_bank'}
            onChange={() => setSource('question_bank')}
            className="mt-1"
          />
          <span>
            <span className="font-medium text-slate-800">Demo question bank</span> — random governed FMCG examples (legacy UAT).
          </span>
        </label>
      </fieldset>

      {draft.starter_source === 'question_bank' ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700">
            Count
            <input
              type="number"
              min={1}
              max={20}
              className="input mt-1"
              value={draft.question_bank_limit}
              onChange={e =>
                setDraft(d => ({ ...d, question_bank_limit: Math.min(20, Math.max(1, Number(e.target.value) || 1)) }))
              }
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Domain filter (optional)
            <select
              className="app-select mt-1 w-full"
              value={draft.question_bank_domain ?? ''}
              onChange={e =>
                setDraft(d => ({
                  ...d,
                  question_bank_domain: e.target.value ? e.target.value : null,
                }))
              }
            >
              <option value="">All domains</option>
              <option value="sales">sales</option>
              <option value="b2b">b2b</option>
              <option value="stock_tempo">stock_tempo</option>
              <option value="stock_sat_idm">stock_sat_idm</option>
              <option value="sat_oos">sat_oos</option>
              <option value="cross_domain">cross_domain</option>
            </select>
          </label>
        </div>
      ) : (
        <ul className="space-y-2">
          {draft.starter_questions.map((q, index) => (
            <li key={index} className="flex gap-2">
              <input
                className="input flex-1"
                placeholder={`Starter question ${index + 1}`}
                value={q}
                onChange={e => updateQuestion(index, e.target.value)}
                maxLength={500}
              />
              <button
                type="button"
                aria-label={`Remove question ${index + 1}`}
                className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
                onClick={() => removeQuestion(index)}
                disabled={draft.starter_questions.length <= 1}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
          {draft.starter_questions.length < MAX_QUESTIONS ? (
            <li>
              <button type="button" className="btn-secondary inline-flex gap-2 py-2 text-sm" onClick={addQuestion}>
                <Plus className="h-4 w-4" />
                Add question
              </button>
            </li>
          ) : null}
        </ul>
      )}

      <AskDataGovernedScopeSettingsPanel settings={draft} onChange={setDraft} />

      {banner ? <p className="type-chat-meta text-emerald-700">{banner}</p> : null}
      {error ? <p className="type-chat-meta text-rose-700">{safeErrorMessage(error)}</p> : null}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={!dirty || saving} onClick={() => void save()}>
          {saving ? 'Saving…' : 'Save starter questions'}
        </button>
        {dirty ? <p className="type-chat-meta text-slate-500">Unsaved changes</p> : null}
      </div>
    </div>
  )
}
