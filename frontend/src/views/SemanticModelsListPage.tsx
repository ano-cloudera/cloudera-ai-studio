'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { MoreHorizontal, Plus, Search } from 'lucide-react'
import { PageCenter } from '../components/PageCenter'
import { appConfig } from '../config/appConfig'
import { api } from '../lib/api'
import { safeErrorMessage } from '../lib/apiError'
import type { ConnectorRecord, SemanticModelRecord, SemanticOverviewPayload } from '../types/api'
import { CreateSemanticModelWizard } from './semantic/CreateSemanticModelWizard'
import { formatSemanticModifiedCompact } from './semantic/authoring/semanticFormat'
import { displayModelName, showKey } from '../lib/semanticNames'

export { displayModelName, showKey }

export const SEMANTIC_MODEL_PATH = '/semantic-layer/model'

type Row = { model: SemanticModelRecord; overview: SemanticOverviewPayload | null }

export function modelStatus(overview: SemanticOverviewPayload | null): { label: string; tone: 'live' | 'draft' | 'empty' | 'unknown' } {
  if (!overview) return { label: '—', tone: 'unknown' }
  const published = overview.published_version_number
  const draft = overview.draft_version_number
  if (published != null) return { label: draft != null ? `Published v${published} · draft v${draft} open` : `Published v${published}`, tone: 'live' }
  const counts = overview.counts
  const empty = counts.entities + counts.metrics + counts.dimensions === 0
  if (draft != null) return { label: empty ? `Draft v${draft}, empty` : `Draft v${draft}, not published`, tone: empty ? 'empty' : 'draft' }
  return { label: 'Empty', tone: 'empty' }
}

const TONE: Record<string, string> = {
  live: 'bg-emerald-50 text-emerald-800',
  draft: 'bg-violet-50 text-violet-800',
  empty: 'bg-slate-100 text-slate-600',
  unknown: 'bg-slate-100 text-slate-500',
}

export function isPublished(row: Row): boolean {
  return row.overview?.published_version_number != null || Boolean(row.model.active_version_id)
}

/** What the user must confirm before a model goes away: a published model also leaves Ask Data. */
export function deletionNotice(row: Row): { message: string; needsTyping: boolean } {
  if (isPublished(row)) {
    return {
      needsTyping: true,
      message: `“${displayModelName(row.model.name)}” is published and Ask Data answers from it. Deleting it removes it from Ask Data (and clears it as the default model), together with every version and definition. This cannot be undone.`,
    }
  }
  return { needsTyping: false, message: `Delete “${displayModelName(row.model.name)}” with its draft and definitions? This cannot be undone.` }
}

function RowActions({ row, isDefault, busy, onOpen, onSetDefault, onDelete }: { row: Row; isDefault: boolean; busy: boolean; onOpen: () => void; onSetDefault: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const name = displayModelName(row.model.name)
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  return (
    <div ref={box} className="relative flex items-center gap-2" onClick={event => event.stopPropagation()}>
      <button type="button" aria-label={`Open ${name}`} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50" onClick={onOpen}>
        Open
      </button>
      <button type="button" aria-label={`More actions for ${name}`} aria-expanded={open} className="rounded-lg p-2 text-slate-600 hover:bg-slate-100" onClick={() => setOpen(value => !value)}>
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-10 z-10 min-w-[11rem] rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {isPublished(row) && !isDefault ? (
            <button
              type="button"
              role="menuitem"
              className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              disabled={busy}
              onClick={() => {
                setOpen(false)
                onSetDefault()
              }}
            >
              Set as default
            </button>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="block w-full px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50"
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
          >
            Delete
          </button>
        </div>
      ) : null}
    </div>
  )
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
  const [settingDefaultFor, setSettingDefaultFor] = useState<string | null>(null)

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
    if (appConfig.deploymentFeatures.connectors) api.listConnectors().then(res => setConnectors(res.connectors)).catch(() => setConnectors([]))
  }, [load])

  const open = (id: string) => router.push(`${SEMANTIC_MODEL_PATH}?model=${encodeURIComponent(id)}`)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const matching = (rows ?? []).filter(row => !needle || `${row.model.name} ${displayModelName(row.model.name)} ${row.model.key}`.toLowerCase().includes(needle))
    return [...matching].sort((a, b) => String(b.overview?.model.updated_at ?? b.model.updated_at).localeCompare(String(a.overview?.model.updated_at ?? a.model.updated_at)))
  }, [rows, search])

  async function setAsDefault(row: Row) {
    setSettingDefaultFor(row.model.id)
    setError('')
    setNotice('')
    try {
      const { settings } = await api.getAskDataSettings()
      await api.putAskDataSettings({ ...settings, default_semantic_model_id: row.model.id, auto_attach_semantic_model: true })
      setDefaultModelId(row.model.id)
      setNotice(`“${displayModelName(row.model.name)}” is now the default model: questions without an @ are answered from it.`)
    } catch (err) {
      setError(safeErrorMessage(err, 'Could not set the default model'))
    } finally {
      setSettingDefaultFor(null)
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    setDeleteError('')
    try {
      const published = deletionNotice(pendingDelete).needsTyping
      await api.deleteSemanticModel(pendingDelete.model.id, published)
      setRows(current => (current ?? []).filter(row => row.model.id !== pendingDelete.model.id))
      if (defaultModelId === pendingDelete.model.id) setDefaultModelId(null)
      setNotice(`Deleted “${displayModelName(pendingDelete.model.name)}”.`)
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
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Semantic models</h1>
          <p className="mt-1 text-sm text-slate-600">The trusted business definitions Ask Data answers from. Open a model to edit and publish it.</p>
        </div>
        <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-[#FF5500] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#e64d00]" onClick={() => setCreateOpen(true)}>
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

      <div className="app-table-surface mt-3">
        <div className="app-table-surface-scroll">
          <table className="app-data-table min-w-full">
            <thead className="app-table-head">
              <tr>
                <th>Model</th>
                <th>Status</th>
                <th className="text-right">Data models</th>
                <th className="text-right">Metrics</th>
                <th className="text-right">Dimensions</th>
                <th>Last modified</th>
                <th className="w-44">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows === null ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    Loading…
                  </td>
                </tr>
              ) : visible.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-600">
                    {rows.length === 0 ? 'No semantic model yet. Create one to start answering questions from your data.' : 'No model matches your search.'}
                  </td>
                </tr>
              ) : (
                visible.map(row => {
                  const status = modelStatus(row.overview)
                  const counts = row.overview?.counts
                  const name = displayModelName(row.model.name)
                  return (
                    <tr key={row.model.id} className="cursor-pointer" onClick={() => open(row.model.id)} data-testid="semantic-model-row">
                      <td>
                        <button
                          type="button"
                          className="font-semibold text-slate-900 hover:underline"
                          onClick={event => {
                            event.stopPropagation()
                            open(row.model.id)
                          }}
                        >
                          {name}
                        </button>
                        {defaultModelId === row.model.id ? (
                          <span className="ml-2 rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-orange-800">Default for Ask Data</span>
                        ) : null}
                        {showKey(row.model) ? <div className="text-xs text-slate-500">{row.model.key}</div> : null}
                      </td>
                      <td>
                        <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${TONE[status.tone]}`}>{status.label}</span>
                      </td>
                      <td className="text-right tabular-nums text-slate-700">{counts?.entities ?? '—'}</td>
                      <td className="text-right tabular-nums text-slate-700">{counts?.metrics ?? '—'}</td>
                      <td className="text-right tabular-nums text-slate-700">{counts?.dimensions ?? '—'}</td>
                      <td className="text-slate-600">{formatSemanticModifiedCompact(row.overview?.model.updated_at ?? row.model.updated_at)}</td>
                      <td>
                        <RowActions
                          row={row}
                          isDefault={defaultModelId === row.model.id}
                          busy={settingDefaultFor !== null}
                          onOpen={() => open(row.model.id)}
                          onSetDefault={() => void setAsDefault(row)}
                          onDelete={() => {
                            setTyped('')
                            setDeleteError('')
                            setPendingDelete(row)
                          }}
                        />
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
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
