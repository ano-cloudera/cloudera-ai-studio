'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import type {
  ConnectorRecord,
  SemanticEntityImportPreview,
  SemanticModelRecord,
  SemanticVersionRecord,
} from '../../types/api'
import { connectorTypeLabel } from '../connectors/connectorUi'

type Props = {
  connector: ConnectorRecord
  catalog: string | null
  schema: string | null
  table: string
  onClose: () => void
  onImported: (entityId: string) => void
}

function slugKey(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64)
}

export function AddToSemanticLayerModal({ connector, catalog, schema, table, onClose, onImported }: Props) {
  const [models, setModels] = useState<SemanticModelRecord[]>([])
  const [modelId, setModelId] = useState('')
  const [versions, setVersions] = useState<SemanticVersionRecord[]>([])
  const [draftId, setDraftId] = useState('')
  const [preview, setPreview] = useState<SemanticEntityImportPreview | null>(null)
  const [name, setName] = useState(table.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))
  const [key, setKey] = useState(slugKey(table))
  const [description, setDescription] = useState('')
  const [selectedDims, setSelectedDims] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const loadModels = useCallback(async () => {
    const res = await api.listSemanticModels()
    setModels(res.models)
    if (res.models[0]) setModelId(res.models[0].id)
  }, [])

  useEffect(() => {
    loadModels().catch(err => setError(err instanceof Error ? err.message : 'Failed to load models'))
  }, [loadModels])

  useEffect(() => {
    if (!modelId) return
    api
      .listSemanticVersions(modelId)
      .then(res => {
        setVersions(res.versions)
        const draft = res.versions.find(v => v.status === 'DRAFT')
        setDraftId(draft?.id ?? '')
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load versions'))
  }, [modelId])

  useEffect(() => {
    if (!draftId) {
      setPreview(null)
      setLoading(false)
      return
    }
    setLoading(true)
    api
      .previewSemanticEntityImport(draftId, {
        connector_id: connector.id,
        catalog,
        schema,
        table,
      })
      .then(res => {
        setPreview(res.preview)
        const init: Record<string, boolean> = {}
        for (const c of res.preview.candidate_dimensions) {
          init[c.column] = true
        }
        setSelectedDims(init)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Preview failed'))
      .finally(() => setLoading(false))
  }, [draftId, connector.id, catalog, schema, table])

  const pathLabel = useMemo(() => {
    return [catalog, schema, table].filter(Boolean).join(' / ')
  }, [catalog, schema, table])

  async function ensureDraft(): Promise<string> {
    const draft = versions.find(v => v.status === 'DRAFT')
    if (draft) return draft.id
    const active = versions.find(v => v.status === 'ACTIVE')
    if (active) {
      const cloned = await api.cloneSemanticVersion(active.id)
      const vid = cloned.version.id
      const res = await api.listSemanticVersions(modelId)
      setVersions(res.versions)
      setDraftId(vid)
      return vid
    }
    const created = await api.createSemanticVersion(modelId)
    const vid = created.version.id
    const res = await api.listSemanticVersions(modelId)
    setVersions(res.versions)
    setDraftId(vid)
    return vid
  }

  async function handleImport() {
    setSaving(true)
    setError('')
    try {
      const vid = draftId || (await ensureDraft())
      if (preview?.existing_entity) {
        setError('An entity for this table already exists in the selected draft.')
        setSaving(false)
        return
      }
      const dimension_columns = Object.entries(selectedDims)
        .filter(([, on]) => on)
        .map(([col]) => col)
      const res = await api.importSemanticEntity(vid, {
        connector_id: connector.id,
        catalog,
        schema,
        table,
        name: name.trim(),
        key: key.trim() || slugKey(name),
        description: description.trim() || null,
        dimension_columns,
      })
      onImported(res.entity.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
        <h2 className="text-lg font-semibold text-slate-900">Add to Semantic Layer</h2>
        <p className="mt-1 text-xs text-slate-600">
          Source: {connector.name} ({connectorTypeLabel(connector.connector_type)}) · {pathLabel}
        </p>

        {error ? <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div> : null}

        {preview?.existing_entity ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
            Already imported as <strong>{preview.existing_entity.name}</strong>.
            <Link href="/semantic-layer" className="ml-2 text-[#FF5500]">
              Open Semantic Layer
            </Link>
          </div>
        ) : null}

        <div className="mt-4 grid gap-3 text-sm">
          <label className="block">
            <span className="font-medium text-slate-700">Semantic model</span>
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
              value={modelId}
              onChange={e => setModelId(e.target.value)}
            >
              {models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          {!draftId ? (
            <p className="text-xs text-amber-800">No draft version — import will create a draft from active or a new draft.</p>
          ) : null}
          <label className="block">
            <span className="font-medium text-slate-700">Entity name</span>
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" value={name} onChange={e => setName(e.target.value)} />
          </label>
          <label className="block">
            <span className="font-medium text-slate-700">Entity key</span>
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" value={key} onChange={e => setKey(e.target.value)} />
          </label>
          <label className="block">
            <span className="font-medium text-slate-700">Description</span>
            <textarea className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" rows={2} value={description} onChange={e => setDescription(e.target.value)} />
          </label>
        </div>

        {loading ? (
          <div className="mt-4 h-24 animate-pulse rounded bg-slate-100" />
        ) : preview ? (
          <div className="mt-4">
            <div className="text-xs font-medium uppercase text-slate-500">Candidate dimensions</div>
            <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-sm">
              {preview.candidate_dimensions.map(c => (
                <li key={c.column}>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedDims[c.column] ?? false}
                      onChange={e => setSelectedDims(prev => ({ ...prev, [c.column]: e.target.checked }))}
                    />
                    {c.column}
                    <span className="text-xs text-slate-400">{c.normalized_type}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            disabled={saving || loading || Boolean(preview?.existing_entity)}
            className="rounded-lg bg-[#FF5500] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            onClick={handleImport}
          >
            {saving ? 'Creating…' : 'Create entity'}
          </button>
        </div>
      </div>
    </div>
  )
}
