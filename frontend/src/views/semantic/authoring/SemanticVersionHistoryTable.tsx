'use client'

import { useState } from 'react'
import type { SemanticRuntimeStatus, SemanticVersionRecord } from '../../../types/api'
import { SEMANTIC_DEFAULT_PAGE_SIZE } from './semanticTableConstants'
import { SemanticAuthoringTableShell } from './SemanticAuthoringTableShell'

type Props = {
  versions: SemanticVersionRecord[]
  runtimeStatus: SemanticRuntimeStatus | null
  saving: boolean
  onRollback: (version: SemanticVersionRecord) => void
}

export function SemanticVersionHistoryTable({ versions, runtimeStatus, saving, onRollback }: Props) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(SEMANTIC_DEFAULT_PAGE_SIZE)
  const sorted = [...versions].sort((a, b) => (b.version_number ?? 0) - (a.version_number ?? 0))
  const total = sorted.length
  const start = (page - 1) * pageSize
  const pageItems = sorted.slice(start, start + pageSize)

  return (
    <div className="p-4 pt-0">
      <SemanticAuthoringTableShell
        testId="semantic-version-history-table"
        compactToolbar
        searchPlaceholder=""
        search=""
        onSearchChange={() => undefined}
        loading={false}
        error={null}
        onRetry={() => undefined}
        emptyMessage="No versions yet."
        emptyColSpan={4}
        hasRows={pageItems.length > 0}
        addLabel=""
        onAdd={() => undefined}
        readOnly
        selectionMode={{ active: false, enter: () => undefined, exit: () => undefined }}
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={n => {
          setPageSize(n)
          setPage(1)
        }}
        minTableWidthClass="min-w-[520px]"
      >
        <thead className="app-table-head">
          <tr>
            <th className="px-3 py-2">Version</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Published</th>
            <th className="w-28 px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody className="align-middle">
          {pageItems.map(v => (
            <tr key={v.id} className="border-b border-slate-50">
              <td className="whitespace-nowrap px-3 py-2">v{v.version_number}</td>
              <td className="px-3 py-2">
                {(() => {
                  const askDataActive = runtimeStatus?.runtime_active_version === v.version_number
                  if (askDataActive) {
                    return (
                      <span
                        data-testid="semantic-version-ask-data-active"
                        className="inline-flex rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-900"
                      >
                        ACTIVE
                      </span>
                    )
                  }
                  if (v.status === 'ACTIVE') {
                    return (
                      <span
                        data-testid="semantic-version-registry-published"
                        className="inline-flex rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-900"
                      >
                        Published
                      </span>
                    )
                  }
                  return <span className="text-slate-700">{v.status}</span>
                })()}
              </td>
              <td className="whitespace-nowrap">{v.published_at ?? '—'}</td>
              <td className="whitespace-nowrap px-3 py-2">
                {v.status === 'ARCHIVED' ? (
                  <button
                    type="button"
                    className="text-xs font-semibold text-slate-700"
                    disabled={saving}
                    onClick={() => onRollback(v)}
                  >
                    Rollback
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </SemanticAuthoringTableShell>
    </div>
  )
}
