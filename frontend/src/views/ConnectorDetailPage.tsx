'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { ConnectorTypeIcon } from '../components/connectors/ConnectorTypeIcon'
import { PageCenter } from '../components/PageCenter'
import { api } from '../lib/api'
import type {
  ConnectorCapabilities,
  ConnectorRecord,
  ConnectorTestResult,
  ConnectorType,
  SamplePreview,
  TableDetail,
  TableInfo,
} from '../types/api'
import {
  buildConfig,
  ConnectorTypeForm,
  defaultFormState,
  formFromConnector,
  type ConnectorFormState,
} from './connectors/ConnectorFormFields'
import { appConfig } from '../config/appConfig'
import {
  capabilityLabels,
  connectorTypeLabel,
  defaultContextLabel,
  displayStatus,
  formatDateTime,
  hostFromConfig,
  statusDotClass,
  statusLabel,
} from './connectors/connectorUi'
import { AddToSemanticLayerModal } from './semantic/AddToSemanticLayerModal'
import type { ConnectorReferences } from '../types/api'
import {
  BACK_TO_DATA_SOURCES,
  DATA_SOURCE_DISABLED_BROWSE,
  DATA_SOURCE_NOT_FOUND,
  DELETE_DATA_SOURCE_ACTION,
} from './connectors/dataSourceUx'

type Tab = 'overview' | 'browse' | 'config'

function breadcrumbPath(
  type: ConnectorType,
  catalog: string | null,
  schema: string | null,
  table: string | null,
): string[] {
  const parts: string[] = []
  if (type === 'trino' && catalog) parts.push(catalog)
  if (schema) parts.push(schema)
  if (table) parts.push(table)
  return parts
}

function TestResultPanel({ result }: { result: ConnectorTestResult }) {
  const ok = result.status === 'SUCCESS'
  return (
    <div
      className={`text-sm ${ok ? 'rounded-lg border border-emerald-200/90 bg-emerald-50/90 px-4 py-3' : 'rounded-lg border border-red-200/90 bg-red-50/90 px-4 py-3'}`}
    >
      <div className="font-semibold text-slate-900">{ok ? 'Connected' : 'Connection failed'}</div>
      {result.phases ? (
        <ul className="mt-2 space-y-1 text-xs text-slate-600">
          {Object.entries(result.phases).map(([k, v]) => (
            <li key={k}>
              {k}: {v}
            </li>
          ))}
        </ul>
      ) : null}
      {ok ? (
        <dl className="mt-2 grid gap-1 text-slate-700">
          <div>Latency: {Math.round(result.latency_ms)} ms</div>
          {result.server_version ? <div>Server: {result.server_version}</div> : null}
          {result.default_catalog || result.default_schema ? (
            <div>
              Context: {[result.default_catalog, result.default_schema].filter(Boolean).join(' / ')}
            </div>
          ) : null}
        </dl>
      ) : (
        <div className="mt-2 text-slate-800">
          {result.error_code ? <div>Code: {result.error_code}</div> : null}
          <div>{result.message}</div>
        </div>
      )}
      {result.capabilities ? (
        <div className="mt-2 text-xs text-slate-600">Capabilities: {capabilityLabels(result.capabilities).join(', ')}</div>
      ) : null}
    </div>
  )
}

function PreviewTable({ preview }: { preview: SamplePreview }) {
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">
        Preview limited to {preview.row_count} row{preview.row_count === 1 ? '' : 's'}.
      </p>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="app-data-table min-w-full">
          <thead className="app-table-head sticky top-0">
            <tr>
              {preview.columns.map(col => (
                <th key={col} className="whitespace-nowrap px-3 py-2 font-medium text-slate-600">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row, idx) => (
              <tr key={idx} className="border-t border-slate-100">
                {preview.columns.map(col => (
                  <td key={col} className="whitespace-nowrap px-3 py-2 text-slate-800">
                    {row[col] == null ? (
                      <span className="text-slate-400">null</span>
                    ) : typeof row[col] === 'object' ? (
                      JSON.stringify(row[col])
                    ) : (
                      String(row[col])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ConnectorDetailPage({ connectorId }: { connectorId: string }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const tabParam = searchParams.get('tab')
  const [tab, setTab] = useState<Tab>(
    tabParam === 'config' || tabParam === 'browse' ? tabParam : 'overview',
  )
  const [connector, setConnector] = useState<ConnectorRecord | null>(null)
  const [capabilities, setCapabilities] = useState<ConnectorCapabilities | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState<ConnectorTestResult | null>(null)
  const [testing, setTesting] = useState(false)

  const [form, setForm] = useState<ConnectorFormState>(defaultFormState('postgres'))
  const [savingConfig, setSavingConfig] = useState(false)
  const [pendingRetest, setPendingRetest] = useState(false)

  const [catalogs, setCatalogs] = useState<string[]>([])
  const [schemas, setSchemas] = useState<string[]>([])
  const [tables, setTables] = useState<TableInfo[]>([])
  const tablesLengthRef = useRef(0)
  const schemaRequestRef = useRef(0)
  const [tableTotal, setTableTotal] = useState(0)
  const [selectedCatalog, setSelectedCatalog] = useState<string | null>(null)
  const [selectedSchema, setSelectedSchema] = useState<string | null>(null)
  const [selectedTable, setSelectedTable] = useState<string | null>(null)
  const [tableSearch, setTableSearch] = useState('')
  const [tableDetail, setTableDetail] = useState<TableDetail | null>(null)
  const [preview, setPreview] = useState<SamplePreview | null>(null)
  const [detailTab, setDetailTab] = useState<'columns' | 'preview'>('columns')
  const [previewLimit, setPreviewLimit] = useState(10)
  const [metaLoading, setMetaLoading] = useState(false)
  const [browseError, setBrowseError] = useState('')
  const [references, setReferences] = useState<ConnectorReferences | null>(null)
  const [addSemanticOpen, setAddSemanticOpen] = useState(false)

  const loadConnector = useCallback(async () => {
    const { connector: row } = await api.getConnector(connectorId)
    setConnector(row)
    setForm(prev => ({
      ...defaultFormState(row.connector_type),
      ...prev,
      name: row.name,
      key: row.key,
      description: row.description ?? '',
      secretRef: '',
      ...formFromConnector(row.connector_type, row.config),
    }))
    try {
      const caps = await api.getConnectorCapabilities(connectorId)
      setCapabilities(caps.capabilities)
    } catch {
      setCapabilities(null)
    }
  }, [connectorId])

  useEffect(() => {
    setLoading(true)
    setError('')
    loadConnector()
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load data source'))
      .finally(() => setLoading(false))
  }, [loadConnector])

  useEffect(() => {
    api.getConnectorReferences(connectorId).then(r => setReferences(r.references)).catch(() => setReferences(null))
  }, [connectorId])

  const type = connector?.connector_type
  const supportsCatalogs = capabilities?.catalogs ?? type === 'trino'

  const refreshCatalogs = useCallback(
    async (refresh = false) => {
      if (!connector || !connector.enabled) return
      setMetaLoading(true)
      setBrowseError('')
      try {
        const res = await api.listConnectorCatalogs(connectorId, refresh)
        const names = res.catalogs.map(c => c.name)
        setCatalogs(names)
        if (supportsCatalogs && names.length) {
          setSelectedCatalog(prev => prev ?? names[0])
        }
      } catch (err) {
        setBrowseError(err instanceof Error ? err.message : 'Failed to load catalogs')
      } finally {
        setMetaLoading(false)
      }
    },
    [connector, connectorId, supportsCatalogs],
  )

  const refreshSchemas = useCallback(
    async (refresh = false) => {
      if (!connector || !connector.enabled) return
      const requestId = ++schemaRequestRef.current
      setMetaLoading(true)
      setBrowseError('')
      try {
        const res = await api.listConnectorSchemas(connectorId, {
          catalog: selectedCatalog ?? undefined,
          limit: 500,
          refresh,
        })
        if (requestId !== schemaRequestRef.current) return // a newer catalog selection superseded this response
        const names = res.schemas.map(s => s.name)
        setSchemas(names)
        if (names.length) {
          setSelectedSchema(prev => prev ?? names[0])
        }
      } catch (err) {
        setBrowseError(err instanceof Error ? err.message : 'Failed to load schemas')
      } finally {
        setMetaLoading(false)
      }
    },
    [connector, connectorId, selectedCatalog],
  )

  const refreshTables = useCallback(
    async (refresh = false, append = false) => {
      if (!connector || !connector.enabled || !selectedSchema) return
      setMetaLoading(true)
      setBrowseError('')
      try {
        const offset = append ? tablesLengthRef.current : 0
        const res = await api.listConnectorTables(connectorId, {
          catalog: selectedCatalog ?? undefined,
          schema: selectedSchema,
          search: tableSearch.trim() || undefined,
          limit: 100,
          offset,
          refresh,
        })
        setTableTotal(res.total)
        setTables(prev => {
          const next = append ? [...prev, ...res.tables] : res.tables
          tablesLengthRef.current = next.length
          return next
        })
      } catch (err) {
        setBrowseError(err instanceof Error ? err.message : 'Failed to load tables')
      } finally {
        setMetaLoading(false)
      }
    },
    [connector, connectorId, selectedCatalog, selectedSchema, tableSearch],
  )

  useEffect(() => {
    if (tab !== 'browse' || !connector?.enabled) return
    if (supportsCatalogs) {
      refreshCatalogs(false)
    } else {
      refreshSchemas(false)
    }
  }, [tab, connector?.enabled, supportsCatalogs, refreshCatalogs, refreshSchemas])

  useEffect(() => {
    if (tab !== 'browse' || !connector?.enabled) return
    if (!supportsCatalogs) return
    if (!selectedCatalog) return
    setSelectedSchema(null)
    setSelectedTable(null)
    setSchemas([])
    setTables([])
    tablesLengthRef.current = 0
    refreshSchemas(false)
  }, [tab, connector?.enabled, supportsCatalogs, selectedCatalog, refreshSchemas])

  useEffect(() => {
    if (tab !== 'browse' || !connector?.enabled || !selectedSchema) return
    setSelectedTable(null)
    setTableDetail(null)
    setPreview(null)
    refreshTables(false)
  }, [tab, connector?.enabled, selectedSchema, refreshTables])

  useEffect(() => {
    if (tab !== 'browse' || !connector?.enabled || !selectedSchema) return
    const t = setTimeout(() => refreshTables(false), 300)
    return () => clearTimeout(t)
  }, [tableSearch, tab, connector?.enabled, selectedSchema, refreshTables])

  async function loadTableDetail(tableName: string) {
    setSelectedTable(tableName)
    setDetailTab('columns')
    setTableDetail(null)
    setPreview(null)
    setBrowseError('')
    try {
      const res = await api.describeConnectorTable(connectorId, {
        catalog: selectedCatalog,
        schema: selectedSchema,
        table: tableName,
      })
      setTableDetail(res.table)
    } catch (err) {
      setBrowseError(err instanceof Error ? err.message : 'Describe failed')
    }
  }

  async function loadPreview(limit: number) {
    if (!selectedTable) return
    setBrowseError('')
    try {
      const res = await api.previewConnectorTable(connectorId, {
        catalog: selectedCatalog,
        schema: selectedSchema,
        table: selectedTable,
        limit,
      })
      setPreview(res.preview)
    } catch (err) {
      setBrowseError(err instanceof Error ? err.message : 'Preview failed')
    }
  }

  useEffect(() => {
    if (detailTab === 'preview' && selectedTable) {
      loadPreview(previewLimit)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detailTab, previewLimit, selectedTable])

  async function runTest() {
    if (!connector) return
    setTesting(true)
    setTestResult(null)
    setError('')
    try {
      const result = await api.testConnector(connectorId)
      setTestResult(result)
      setPendingRetest(false)
      await loadConnector()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test failed')
      await loadConnector()
    } finally {
      setTesting(false)
    }
  }

  async function saveConfig() {
    if (!connector) return
    setSavingConfig(true)
    setError('')
    try {
      const patch = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        config: buildConfig(connector.connector_type, form),
        ...(form.secretRef.trim() ? { secret_ref: form.secretRef.trim() } : {}),
      }
      const updated = await api.patchConnector(connectorId, patch)
      setConnector(updated.connector)
      setPendingRetest(true)
      setForm(f => ({ ...f, secretRef: '' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSavingConfig(false)
    }
  }

  async function handleDelete() {
    if (!connector || !window.confirm(`Delete ${connector.name}?`)) return
    try {
      await api.deleteConnector(connectorId)
      router.push('/connectors')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const displayConnector = useMemo(() => {
    if (!connector) return null
    if (!pendingRetest) return connector
    return { ...connector, last_test_status: 'NOT_TESTED' as string | null }
  }, [connector, pendingRetest])

  if (loading) {
    return (
      <PageCenter>
        <div className="h-8 w-48 animate-pulse rounded bg-slate-100" />
        <div className="mt-6 h-64 animate-pulse rounded-xl bg-slate-100" />
      </PageCenter>
    )
  }

  if (!connector || !displayConnector) {
    return (
      <PageCenter>
        <p className="text-slate-600">{error || DATA_SOURCE_NOT_FOUND}</p>
        <Link href="/connectors" className="mt-4 inline-block text-sm text-[#FF5500]">
          {BACK_TO_DATA_SOURCES}
        </Link>
      </PageCenter>
    )
  }

  const st = displayStatus(displayConnector)
  const crumbs = breadcrumbPath(connector.connector_type, selectedCatalog, selectedSchema, selectedTable)

  return (
    <PageCenter>
      <Link href="/connectors" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" />
        {appConfig.navigationConnectors}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
            <ConnectorTypeIcon
              connectorType={connector.connector_type}
              size={connector.connector_type === 'impala' ? 38 : 28}
            />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">{connector.name}</h1>
            <p className="mt-1 text-sm text-slate-600">
              {connectorTypeLabel(connector.connector_type)} · {hostFromConfig(connector)}
            </p>
          </div>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm">
          <span className={`h-2 w-2 rounded-full ${statusDotClass(st)}`} />
          {statusLabel(st)}
        </span>
      </div>

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      ) : null}

      <div className="mt-6 flex gap-4 border-b border-slate-200" role="tablist">
        {(['overview', 'browse', 'config'] as Tab[]).map(t => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`border-b-2 px-1 pb-2 text-sm font-medium capitalize ${
              tab === t ? 'border-[#FF5500] text-slate-900' : 'border-transparent text-slate-500'
            }`}
          >
            {t === 'browse' ? 'Browse Data' : t}
          </button>
        ))}
      </div>

      {tab === 'overview' ? (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="text-slate-500">Last connection test</dt>
                <dd className="font-medium text-slate-900">{formatDateTime(connector.last_tested_at)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Default context</dt>
                <dd className="font-medium text-slate-900">{defaultContextLabel(connector)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Credentials</dt>
                <dd className="font-medium text-slate-900">
                  {connector.credentials_configured ? 'Configured' : 'Not configured'}
                  {connector.secret_ref ? (
                    <span className="ml-2 text-xs font-normal text-slate-500">({connector.secret_ref})</span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Capabilities</dt>
                <dd className="text-slate-900">{capabilityLabels(capabilities ?? undefined).join(', ') || '—'}</dd>
              </div>
              {references && references.count > 0 ? (
                <div>
                  <dt className="text-slate-500">Used by Semantic Layer</dt>
                  <dd className="text-slate-900">
                    {references.count} semantic entit{references.count === 1 ? 'y' : 'ies'}
                    <Link href="/semantic-layer" className="ml-2 text-xs text-[#FF5500]">
                      Open Semantic Layer
                    </Link>
                  </dd>
                </div>
              ) : null}
            </dl>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!connector.enabled || testing}
                onClick={runTest}
                className="rounded-xl bg-[#FF5500] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {testing ? 'Testing…' : 'Test connection'}
              </button>
              <button
                type="button"
                onClick={() => setTab('config')}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm"
              >
                Edit configuration
              </button>
            </div>
            {testResult ? <div className="mt-4">{<TestResultPanel result={testResult} />}</div> : null}
            {connector.last_test_message && connector.last_test_status === 'FAILED' ? (
              <p className="mt-3 text-xs text-red-700">{connector.last_test_message}</p>
            ) : null}
          </div>
        </div>
      ) : null}

      {tab === 'browse' ? (
        <div className="mt-6">
          {!connector.enabled ? (
            <p className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-600">
              {DATA_SOURCE_DISABLED_BROWSE}
            </p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                {crumbs.map((part, i) => (
                  <span key={`${part}-${i}`}>
                    {i > 0 ? ' / ' : ''}
                    <button
                      type="button"
                      className="hover:text-[#FF5500]"
                      onClick={() => {
                        if (i === crumbs.length - 1 && selectedTable) {
                          setSelectedTable(null)
                          setTableDetail(null)
                        } else if (part === selectedCatalog) {
                          setSelectedSchema(null)
                          setSelectedTable(null)
                        }
                      }}
                    >
                      {part}
                    </button>
                  </span>
                ))}
                <button
                  type="button"
                  className="ml-auto inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs"
                  onClick={() => {
                    if (supportsCatalogs) refreshCatalogs(true)
                    refreshSchemas(true)
                    refreshTables(true)
                  }}
                >
                  <RefreshCw className="h-3 w-3" />
                  Refresh
                </button>
              </div>
              {browseError ? (
                <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{browseError}</div>
              ) : null}
              <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
                <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  {metaLoading && !schemas.length ? (
                    <div className="h-32 animate-pulse rounded bg-slate-100" />
                  ) : (
                    <>
                      {supportsCatalogs ? (
                        <div className="mb-3">
                          <div className="mb-1 text-xs font-medium uppercase text-slate-500">Catalog</div>
                          <select
                            className="w-full rounded border border-slate-200 px-2 py-1"
                            value={selectedCatalog ?? ''}
                            onChange={e => setSelectedCatalog(e.target.value || null)}
                          >
                            {catalogs.map(c => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : null}
                      <div className="mb-1 text-xs font-medium uppercase text-slate-500">
                        {connector.connector_type === 'impala' ? 'Database' : 'Schema'}
                      </div>
                      <ul className="max-h-48 overflow-y-auto">
                        {schemas.map(s => (
                          <li key={s}>
                            <button
                              type="button"
                              className={`w-full rounded px-2 py-1 text-left ${
                                selectedSchema === s ? 'bg-slate-100 font-medium' : 'hover:bg-slate-50'
                              }`}
                              onClick={() => setSelectedSchema(s)}
                            >
                              {s}
                            </button>
                          </li>
                        ))}
                      </ul>
                      {selectedSchema ? (
                        <>
                          <input
                            className="mt-3 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                            placeholder="Search tables…"
                            value={tableSearch}
                            onChange={e => setTableSearch(e.target.value)}
                          />
                          <ul className="mt-2 max-h-56 overflow-y-auto">
                            {tables.map(t => (
                              <li key={t.name}>
                                <button
                                  type="button"
                                  className={`w-full rounded px-2 py-1 text-left text-xs ${
                                    selectedTable === t.name ? 'bg-orange-50 font-medium text-[#FF5500]' : 'hover:bg-slate-50'
                                  }`}
                                  onClick={() => loadTableDetail(t.name)}
                                >
                                  {t.name}
                                  {t.table_type ? (
                                    <span className="ml-1 text-slate-400">{t.table_type}</span>
                                  ) : null}
                                </button>
                              </li>
                            ))}
                          </ul>
                          {tables.length < tableTotal ? (
                            <button
                              type="button"
                              className="mt-2 text-xs text-[#FF5500]"
                              onClick={() => refreshTables(false, true)}
                            >
                              Load more
                            </button>
                          ) : null}
                        </>
                      ) : null}
                    </>
                  )}
                </div>
                <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-4">
                  {!selectedTable ? (
                    <p className="text-sm text-slate-500">Select a table to inspect columns and preview sample data.</p>
                  ) : tableDetail ? (
                    <>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h2 className="text-lg font-semibold">{tableDetail.name}</h2>
                          <p className="text-xs text-slate-500">
                            {tableDetail.table_type}
                            {tableDetail.schema ? ` · ${tableDetail.schema}` : ''}
                          </p>
                        </div>
                        {appConfig.features.semanticLayer && connector.enabled ? (
                          <button
                            type="button"
                            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
                            onClick={() => setAddSemanticOpen(true)}
                          >
                            Add to Semantic Layer
                          </button>
                        ) : null}
                      </div>
                      <div className="mt-4 flex gap-3 border-b border-slate-200">
                        <button
                          type="button"
                          className={`pb-2 text-sm ${detailTab === 'columns' ? 'border-b-2 border-[#FF5500] font-medium' : 'text-slate-500'}`}
                          onClick={() => setDetailTab('columns')}
                        >
                          Columns
                        </button>
                        <button
                          type="button"
                          className={`pb-2 text-sm ${detailTab === 'preview' ? 'border-b-2 border-[#FF5500] font-medium' : 'text-slate-500'}`}
                          onClick={() => setDetailTab('preview')}
                        >
                          Preview
                        </button>
                      </div>
                      {detailTab === 'columns' ? (
                        <div className="mt-4 overflow-x-auto">
                        <table className="app-data-table min-w-full">
                          <thead className="app-table-head">
                            <tr>
                              <th className="py-2">Column</th>
                              <th className="py-2">Native type</th>
                              <th className="py-2">Normalized</th>
                              <th className="py-2">Nullable</th>
                              <th className="py-2">Description</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tableDetail.columns.map(col => (
                              <tr key={col.name} className="border-t border-slate-100">
                                <td className="py-2 font-medium">{col.name}</td>
                                <td className="py-2">{col.native_type || col.data_type}</td>
                                <td className="py-2">{col.normalized_type}</td>
                                <td className="py-2">{col.nullable == null ? '—' : col.nullable ? 'Yes' : 'No'}</td>
                                <td className="py-2 text-slate-600">{col.comment || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        </div>
                      ) : (
                        <div className="mt-4">
                          <div className="mb-2 flex items-center gap-2 text-sm">
                            <span>Rows:</span>
                            {[10, 25, 50].map(n => (
                              <button
                                key={n}
                                type="button"
                                className={`rounded px-2 py-0.5 ${previewLimit === n ? 'bg-slate-900 text-white' : 'bg-slate-100'}`}
                                onClick={() => setPreviewLimit(n)}
                              >
                                {n}
                              </button>
                            ))}
                          </div>
                          {preview ? (
                            <PreviewTable preview={preview} />
                          ) : (
                            <div className="h-24 animate-pulse rounded bg-slate-100" />
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="h-32 animate-pulse rounded bg-slate-100" />
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      ) : null}

      {tab === 'config' ? (
        <div className="mt-6 max-w-2xl rounded-xl border border-slate-200 bg-white p-5">
          <ConnectorTypeForm
            type={connector.connector_type}
            form={form}
            setForm={setForm}
            credentialsConfigured={connector.credentials_configured}
          />
          <div className="mt-6 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={savingConfig}
              onClick={saveConfig}
              className="rounded-xl bg-[#FF5500] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {savingConfig ? 'Saving…' : 'Save changes'}
            </button>
            <button type="button" onClick={handleDelete} className="rounded-xl border border-red-200 px-4 py-2 text-sm text-red-700">
              {DELETE_DATA_SOURCE_ACTION}
            </button>
          </div>
          {pendingRetest ? (
            <p className="mt-3 text-xs text-amber-700">Connection settings changed — status is Not Tested until you run a test.</p>
          ) : null}
        </div>
      ) : null}

      {addSemanticOpen && connector && selectedTable ? (
        <AddToSemanticLayerModal
          connector={connector}
          catalog={selectedCatalog}
          schema={selectedSchema}
          table={selectedTable}
          onClose={() => setAddSemanticOpen(false)}
          onImported={() => {
            setAddSemanticOpen(false)
            api.getConnectorReferences(connectorId).then(r => setReferences(r.references))
          }}
        />
      ) : null}
    </PageCenter>
  )
}
