'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Plus, Search, Trash2 } from 'lucide-react'
import { PageCenter } from '../components/PageCenter'
import { appConfig } from '../config/appConfig'
import { api } from '../lib/api'
import { safeErrorMessage } from '../lib/apiError'
import type { ConnectorRecord, SemanticModelRecord, SemanticOverviewPayload } from '../types/api'
import { CreateSemanticModelWizard } from './semantic/CreateSemanticModelWizard'
import { formatSemanticModifiedCompact } from './semantic/authoring/semanticFormat'

export const SEMANTIC_MODEL_PATH = '/semantic-layer/model'

type Row = { model: SemanticModelRecord; overview: SemanticOverviewPayload | null }

export function modelStatus(overview: SemanticOverviewPayload | null): { label: string; tone: 'live' | 'draft' | 'empty' | 'unknown' } {
  if (!overview) return { label: '—', tone: 'unknown' }
  const published = overview.published_version_number
  const draft = overview.draft_version_number
  if (published != null) return { label: draft != null ? `Published v${published} · draft v${draft} open` : `Published v${published}`, tone: 'live' }
  if (draft != null) return { label: `Draft v${draft}, not published`, tone: 'draft' }
  return { label: 'Empty', tone: 'empty' }
}

const TONE: Record<string, string> = {
  live: 'bg-emerald-50 text-emerald-800',
  draft: 'bg-violet-50 text-violet-800',
  empty: 'bg-slate-100 text-slate-600',
  unknown: 'bg-slate-100 text-slate-500',
}

/** What the user must confirm before a model goes away: a published model also leaves Ask Data. */
export function deletionNotice(row: Row): { message: string; needsTyping: boolean } {
  const published = row.overview?.published_version_number != null || Boolean(row.model.active_version_id)
  if (published) {
    return {
      needsTyping: true,
      message: `“${row.model.name}” is published and Ask Data answers from it. Deleting it removes it from Ask Data (and clears it as the default model), together with every version and definition. This cannot be undone.`,
    }
  }
  return { needsTyping: false, message: `Delete “${row.model.name}” with its draft and definitions? This cannot be undone.` }
}

export function SemanticModelsListPage() {
  const router = useRouter()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [defaultModelId, setDefaultModelId] = useState<string | null>(null)
  const [connectors, setConnectors] = useState<ConnectorRecord[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Row | null>(null)
  const [typed, setTyped] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const { models } = await api.listSemanticModels()
      const overviews = await Promise.allSettled(models.map(model => api.getSemanticModelOverview(model.id)))
      setRows(models.map((model, index) => ({ model, overview: overviews[index].status === 'fulfilled' ? (overviews[index] as PromiseFulfilledResult<SemanticOverviewPayload>).value : null })))
    } catch (err) {
      setError(safeErrorMessage(err, 'Failed to load the semantic models'))
      setRows([])
    }
  }, [])

  useEffect(() => {
    void load()
    api.getAskDataSettings().then(res => setDefaultModelId(res.settings.default_semantic_model_id ?? null)).catch(() => setDefaultModelId(null))
    if (appConfig.features.connectors) api.listConnectors().then(res => setConnectors(res.connectors)).catch(() => setConnectors([]))
  }, [load])

  const open = (id: string) => router.push(`${SEMANTIC_MODEL_PATH}?model=${encodeURIComponent(id)}`)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (rows ?? []).filter(row => !needle || `${row.model.name} ${row.model.key}`.toLowerCase().includes(needle))
  }, [rows, search])

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    setDeleteError('')
    try {
      const published = deletionNotice(pendingDelete).needsTyping
      await api.deleteSemanticModel(pendingDelete.model.id, published)
      setRows(current => (current ?? []).filter(row => row.model.id !== pendingDelete.model.id))
      if (defaultModelId === pendingDelete.model.id) setDefaultModelId(null)
      setNotice(`Deleted “${pendingDelete.model.name}”.`)
      setPendingDelete(null)
      setTyped('')
    } catch (err) {
      setDeleteError(safeErrorMessage(err, 'Delete failed'))
    } finally {
      setDeleting(false)
    }
  }

  const notice_ = pendingDelete ? deletionNotice(pendingDelete) : null
  const canDelete = pendingDelete && (!notice_?.needsTyping || typed.trim() === pendingDelete.model.key)

  return (
    <PageCenter>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-cloudera-navy">Semantic models</h1>
          <p className="mt-1 text-sm text-slate-600">The trusted business definitions Ask Data answers from. Open a model to edit and publish it.</p>
        </div>
        <button type="button" className="btn-primary inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" aria-hidden />
          Create semantic model
        </button>
      </div>

      {notice ? (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          <span>{error}</span>
          <button type="button" className="font-semibold underline" onClick={() => void load()}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="relative mt-5 max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input className="input w-full pl-9" placeholder="Search models…" aria-label="Search semantic models" value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Data models</th>
              <th className="px-4 py-3 text-right">Metrics</th>
              <th className="px-4 py-3 text-right">Dimensions</th>
              <th className="px-4 py-3">Last modified</th>
              <th className="px-4 py-3 text-right">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows === null ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-600">
                  {rows.length === 0 ? 'No semantic model yet. Create one to start answering questions from your data.' : 'No model matches your search.'}
                </td>
              </tr>
            ) : (
              visible.map(row => {
                const status = modelStatus(row.overview)
                const counts = row.overview?.counts
                return (
                  <tr key={row.model.id} className="cursor-pointer hover:bg-slate-50/70" onClick={() => open(row.model.id)} data-testid="semantic-model-row">
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="font-semibold text-cloudera-navy hover:underline"
                        onClick={event => {
                          event.stopPropagation()
                          open(row.model.id)
                        }}
                      >
                        {row.model.name}
                      </button>
                      {defaultModelId === row.model.id ? (
                        <span className="ml-2 rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-orange-800">Default for Ask Data</span>
                      ) : null}
                      <div className="font-mono text-xs text-slate-500">{row.model.key}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${TONE[status.tone]}`}>{status.label}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{counts?.entities ?? '—'}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{counts?.metrics ?? '—'}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{counts?.dimensions ?? '—'}</td>
                    <td className="px-4 py-3 text-slate-600">{formatSemanticModifiedCompact(row.overview?.model.updated_at ?? row.model.updated_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        aria-label={`Delete ${row.model.name}`}
                        className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:border-red-200 hover:bg-red-50 hover:text-red-700"
                        onClick={event => {
                          event.stopPropagation()
                          setTyped('')
                          setDeleteError('')
                          setPendingDelete(row)
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {pendingDelete && notice_ ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-labelledby="delete-model-title">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
            <h2 id="delete-model-title" className="text-lg font-semibold text-cloudera-navy">
              Delete semantic model?
            </h2>
            <p className="mt-2 text-sm text-slate-600">{notice_.message}</p>
            {notice_.needsTyping ? (
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Type <span className="font-mono">{pendingDelete.model.key}</span> to confirm
                <input className="input mt-1 w-full font-mono text-sm" value={typed} onChange={e => setTyped(e.target.value)} autoFocus />
              </label>
            ) : null}
            {deleteError ? (
              <p className="mt-3 text-sm text-red-700" role="alert">
                {deleteError}
              </p>
            ) : null}
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold" onClick={() => setPendingDelete(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="h-9 rounded-lg bg-red-600 px-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                disabled={!canDelete || deleting}
                onClick={() => void confirmDelete()}
              >
                {deleting ? 'Deleting…' : notice_.needsTyping ? 'Delete and remove from Ask Data' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <CreateSemanticModelWizard
        open={createOpen}
        connectors={connectors}
        onClose={() => setCreateOpen(false)}
        onCreated={id => {
          setCreateOpen(false)
          open(id)
        }}
      />
    </PageCenter>
  )
}
