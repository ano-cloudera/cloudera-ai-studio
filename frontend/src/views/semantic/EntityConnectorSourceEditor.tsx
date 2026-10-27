'use client'

import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import { api } from '../../lib/api'
import type { ConnectorRecord, SemanticEntityRecord } from '../../types/api'
import { connectorTypeLabel, displayStatus, statusDotClass, statusLabel } from '../connectors/connectorUi'
import { DATA_SOURCE_COLUMN, METADATA_REFRESHED_FROM_DATA_SOURCE } from '../connectors/dataSourceUx'

type Props = {
  entity: SemanticEntityRecord
  readOnly: boolean
  form: SemanticEntityRecord
  setForm: Dispatch<SetStateAction<SemanticEntityRecord>>
  onDirty: () => void
}

export function EntityConnectorSourceEditor({ entity, readOnly, form, setForm, onDirty }: Props) {
  const [connectors, setConnectors] = useState<ConnectorRecord[]>([])
  const [catalogs, setCatalogs] = useState<string[]>([])
  const [schemas, setSchemas] = useState<string[]>([])
  const [tables, setTables] = useState<string[]>([])
  const [sourceWarning, setSourceWarning] = useState('')
  const [refreshMsg, setRefreshMsg] = useState('')

  const selected = useMemo(
    () => connectors.find(c => c.id === form.connection_id) ?? null,
    [connectors, form.connection_id],
  )
  const supportsCatalogs = selected?.connector_type === 'trino'

  useEffect(() => {
    api.listConnectors({ enabled: true }).then(r => setConnectors(r.connectors)).catch(() => setConnectors([]))
  }, [])

  useEffect(() => {
    if (!form.connection_id || readOnly) return
    api.listConnectorCatalogs(form.connection_id).then(r => setCatalogs(r.catalogs.map(c => c.name))).catch(() => setCatalogs([]))
  }, [form.connection_id, readOnly])

  useEffect(() => {
    if (!form.connection_id || readOnly) return
    if (supportsCatalogs && !form.catalog) return
    api
      .listConnectorSchemas(form.connection_id, { catalog: form.catalog ?? undefined, limit: 500 })
      .then(r => setSchemas(r.schemas.map(s => s.name)))
      .catch(() => setSchemas([]))
  }, [form.connection_id, form.catalog, supportsCatalogs, readOnly])

  useEffect(() => {
    if (!form.connection_id || !form.schema || readOnly) return
    api
      .listConnectorTables(form.connection_id, {
        catalog: form.catalog ?? undefined,
        schema: form.schema,
        limit: 200,
      })
      .then(r => setTables(r.tables.map(t => t.name)))
      .catch(() => setTables([]))
  }, [form.connection_id, form.catalog, form.schema, readOnly])

  function patch(partial: Partial<SemanticEntityRecord>) {
    const next = { ...form, ...partial }
    const physicalChanged =
      partial.connection_id != null ||
      partial.catalog != null ||
      partial.schema != null ||
      partial.table_name != null ||
      partial.view_name != null
    if (physicalChanged && entity.id) {
      setSourceWarning(
        'Changing the physical source may affect metrics, dimensions, relationships, and Ask Data behavior.',
      )
    }
    if (partial.connection_id && connectors.length) {
      const conn = connectors.find(c => c.id === partial.connection_id)
      if (conn) next.source_type = conn.connector_type
    }
    setForm(next)
    onDirty()
  }

  async function refreshMetadata() {
    if (!form.connection_id || !form.schema) return
    const table = form.table_name || form.view_name
    if (!table) return
    setRefreshMsg('')
    try {
      await api.describeConnectorTable(form.connection_id, {
        catalog: form.catalog,
        schema: form.schema,
        table,
      })
      setRefreshMsg(METADATA_REFRESHED_FROM_DATA_SOURCE)
    } catch (err) {
      setRefreshMsg(err instanceof Error ? err.message : 'Refresh failed')
    }
  }

  const st = selected ? displayStatus(selected) : null

  return (
    <div className="md:col-span-2 rounded-lg border border-slate-100 bg-slate-50/50 p-3">
      <div className="text-xs font-semibold uppercase text-slate-500">Physical source</div>
      {sourceWarning ? <p className="mt-2 text-xs text-amber-800">{sourceWarning}</p> : null}
      <div className="mt-2 grid gap-3 md:grid-cols-2">
        <label className="block text-sm">
          <span className="font-medium text-slate-700">{DATA_SOURCE_COLUMN}</span>
          <select
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            disabled={readOnly}
            value={form.connection_id ?? ''}
            onChange={e => patch({ connection_id: e.target.value || null })}
          >
            <option value="">Legacy / none</option>
            {connectors.map(c => (
              <option key={c.id} value={c.id}>
                {c.name} ({connectorTypeLabel(c.connector_type)})
              </option>
            ))}
          </select>
        </label>
        {selected && st ? (
          <div className="flex items-end text-sm">
            <span className="inline-flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${statusDotClass(st)}`} />
              Last connection test: {statusLabel(st)}
            </span>
          </div>
        ) : null}
        {supportsCatalogs ? (
          <label className="block text-sm">
            <span className="font-medium text-slate-700">Catalog</span>
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
              disabled={readOnly || !form.connection_id}
              value={form.catalog ?? ''}
              onChange={e => patch({ catalog: e.target.value || null })}
            >
              <option value="">—</option>
              {catalogs.map(c => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="block text-sm">
          <span className="font-medium text-slate-700">{selected?.connector_type === 'impala' ? 'Database' : 'Schema'}</span>
          <select
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            disabled={readOnly || !form.connection_id}
            value={form.schema ?? ''}
            onChange={e => patch({ schema: e.target.value || null })}
          >
            <option value="">—</option>
            {schemas.map(s => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="font-medium text-slate-700">Table / view</span>
          <select
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            disabled={readOnly || !form.connection_id || !form.schema}
            value={form.table_name || form.view_name || ''}
            onChange={e => patch({ table_name: e.target.value, view_name: null })}
          >
            <option value="">—</option>
            {tables.map(t => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        {!form.connection_id ? (
          <>
            <label className="block text-sm md:col-span-2">
              <span className="font-medium text-slate-700">Source type (legacy)</span>
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
                readOnly={readOnly}
                value={form.source_type}
                onChange={e => patch({ source_type: e.target.value })}
              />
            </label>
          </>
        ) : null}
      </div>
      {!readOnly && form.connection_id ? (
        <button type="button" className="mt-3 text-xs font-semibold text-[#FF5500]" onClick={refreshMetadata}>
          Refresh metadata
        </button>
      ) : null}
      {refreshMsg ? <p className="mt-1 text-xs text-slate-600">{refreshMsg}</p> : null}
    </div>
  )
}
