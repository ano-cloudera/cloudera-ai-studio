'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { TablePagination } from '../components/knowledge/TablePagination'
import { Cable, MoreHorizontal, Plus, Search } from 'lucide-react'
import { PageCenter } from '../components/PageCenter'
import { ServiceErrorState } from '../components/ServiceErrorState'
import { appConfig } from '../config/appConfig'
import { api } from '../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../lib/apiError'
import type { ConnectorRecord } from '../types/api'
import {
  connectorTypeLabel,
  defaultContextLabel,
  displayStatus,
  formatDateTime,
  hostFromConfig,
  statusDotClass,
  statusLabel,
} from './connectors/connectorUi'
import {
  ADD_DATA_SOURCE,
  DATA_SOURCES_DISABLED,
  DATA_SOURCES_PAGE_SUBTITLE,
  DELETE_DATA_SOURCE_BODY,
  DELETE_DATA_SOURCE_TITLE,
  EMPTY_DATA_SOURCES_BODY,
  EMPTY_DATA_SOURCES_TITLE,
  SEARCH_DATA_SOURCES_ARIA,
  SEARCH_DATA_SOURCES_PLACEHOLDER,
  UNABLE_TO_LOAD_DATA_SOURCES,
} from './connectors/dataSourceUx'

function RowActions({
  connector,
  onTest,
  onToggle,
  onDelete,
  testing,
}: {
  connector: ConnectorRecord
  onTest: () => void
  onToggle: () => void
  onDelete: () => void
  testing: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative flex items-center gap-2">
      <Link
        href={`/connectors/${connector.id}`}
        className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
      >
        Open
      </Link>
      <button
        type="button"
        disabled={!connector.enabled || testing}
        onClick={onTest}
        className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {testing ? 'Testing…' : 'Test'}
      </button>
      <button
        type="button"
        aria-label="More actions"
        onClick={() => setOpen(v => !v)}
        className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open ? (
        <div className="absolute right-0 top-10 z-10 min-w-[10rem] rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          <Link
            href={`/connectors/${connector.id}?tab=config`}
            className="block px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            onClick={() => setOpen(false)}
          >
            Edit
          </Link>
          <button
            type="button"
            className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
            onClick={() => {
              setOpen(false)
              onToggle()
            }}
          >
            {connector.enabled ? 'Disable' : 'Enable'}
          </button>
          <button
            type="button"
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

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const [bannerError, setBannerError] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ConnectorRecord | null>(null)

  const refresh = useCallback(async () => {
    const response = await api.listConnectors()
    setConnectors(response.connectors)
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      await refresh()
    } catch (err) {
      setLoadError(toAppApiError(err))
    } finally {
      setLoading(false)
    }
  }, [refresh])

  useEffect(() => {
    void reload()
  }, [reload])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return connectors
    return connectors.filter(
      c =>
        c.name.toLowerCase().includes(q) ||
        c.key.toLowerCase().includes(q) ||
        c.connector_type.includes(q),
    )
  }, [connectors, search])

  useEffect(() => {
    setPage(1)
  }, [search])

  const pagedConnectors = useMemo(() => {
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [filtered, page, pageSize])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize) || 1)
    if (page > totalPages) setPage(totalPages)
  }, [filtered.length, page, pageSize])

  async function handleTest(connector: ConnectorRecord) {
    setTestingId(connector.id)
    setBannerError('')
    try {
      await api.testConnector(connector.id)
      await refresh()
    } catch (err) {
      setBannerError(safeErrorMessage(err, 'Connection test failed'))
      await refresh()
    } finally {
      setTestingId(null)
    }
  }

  async function handleToggle(connector: ConnectorRecord) {
    setBannerError('')
    try {
      await api.patchConnector(connector.id, { enabled: !connector.enabled })
      await refresh()
    } catch (err) {
      setBannerError(safeErrorMessage(err, 'Update failed'))
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setBannerError('')
    try {
      await api.deleteConnector(deleteTarget.id)
      setDeleteTarget(null)
      await refresh()
    } catch (err) {
      setBannerError(safeErrorMessage(err, 'Delete failed'))
    }
  }

  if (!appConfig.features.connectors) {
    return (
      <PageCenter>
        <p className="text-slate-600">{DATA_SOURCES_DISABLED}</p>
      </PageCenter>
    )
  }

  return (
    <PageCenter>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{appConfig.navigationConnectors}</h1>
          <p className="mt-1 text-sm text-slate-600">{DATA_SOURCES_PAGE_SUBTITLE}</p>
        </div>
        <Link
          href="/connectors/new"
          className="inline-flex items-center gap-2 rounded-xl bg-[#FF5500] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#e64d00]"
        >
          <Plus className="h-4 w-4" />
          {ADD_DATA_SOURCE}
        </Link>
      </div>

      {loadError && !connectors.length && !loading ? (
        <ServiceErrorState
          title={UNABLE_TO_LOAD_DATA_SOURCES}
          message="We couldn't reach the backend service."
          error={loadError}
          onRetry={() => void reload()}
        />
      ) : null}

      {bannerError ? (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          {bannerError}
        </div>
      ) : null}

      <div className="mb-4 flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
        <Search className="h-4 w-4 text-slate-400" />
        <input
          type="search"
          placeholder={SEARCH_DATA_SOURCES_PLACEHOLDER}
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full border-0 bg-transparent text-sm outline-none"
          aria-label={SEARCH_DATA_SOURCES_ARIA}
        />
      </div>

      {loadError && !connectors.length ? null : loading ? (
        <div className="space-y-3" aria-busy="true">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-8 py-16 text-center">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-slate-100 text-slate-600">
            <Cable className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900">{EMPTY_DATA_SOURCES_TITLE}</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">{EMPTY_DATA_SOURCES_BODY}</p>
          <Link
            href="/connectors/new"
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#FF5500] px-4 py-2.5 text-sm font-semibold text-white"
          >
            <Plus className="h-4 w-4" />
            {ADD_DATA_SOURCE}
          </Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="app-table-head">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Project</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last connection test</th>
                <th className="px-4 py-3 font-medium">Default context</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pagedConnectors.map(connector => {
                const st = displayStatus(connector)
                return (
                  <tr key={connector.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3">
                      <div className="min-w-0">
                        <div className="font-medium text-slate-900">{connector.name}</div>
                        <div className="text-xs text-slate-500">{hostFromConfig(connector)}</div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                        {connectorTypeLabel(connector.connector_type)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{appConfig.projectName}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-2 text-slate-700">
                        <span className={`h-2 w-2 rounded-full ${statusDotClass(st)}`} aria-hidden />
                        {statusLabel(st)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{formatDateTime(connector.last_tested_at)}</td>
                    <td className="px-4 py-3 text-slate-600">{defaultContextLabel(connector)}</td>
                    <td className="px-4 py-3">
                      <RowActions
                        connector={connector}
                        testing={testingId === connector.id}
                        onTest={() => handleTest(connector)}
                        onToggle={() => handleToggle(connector)}
                        onDelete={() => setDeleteTarget(connector)}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={filtered.length}
            onPageChange={setPage}
            onPageSizeChange={size => {
              setPageSize(size)
              setPage(1)
            }}
          />
        </div>
      )}

      {deleteTarget ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-lg font-semibold text-slate-900">{DELETE_DATA_SOURCE_TITLE}</h2>
            <p className="mt-2 text-sm text-slate-600">
              {DELETE_DATA_SOURCE_BODY}{' '}
              <strong>{deleteTarget.name}</strong> will be removed. This action cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm"
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white"
                onClick={confirmDelete}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </PageCenter>
  )
}
