'use client'

import { useCallback, useState } from 'react'
import { SortableColumnHeader } from '../../../components/table/SortableColumnHeader'
import { RowActionsMenu } from '../../../components/table/RowActionsMenu'
import { api } from '../../../lib/api'
import { SemanticAuthoringTableShell } from './SemanticAuthoringTableShell'
import { formatSemanticModifiedCompact } from './semanticFormat'
import { useSemanticPaginatedList } from './useSemanticPaginatedList'

type Props = { versionId: string | null }

export function RecentDefinitionsPanel({ versionId }: Props) {
  const [typeFilter, setTypeFilter] = useStateFilter()
  const fetchPage = useCallback(
    async (vid: string, params: Parameters<typeof api.listSemanticRecentDefinitions>[1]) => {
      const r = await api.listSemanticRecentDefinitions(vid, { ...params, type: typeFilter || undefined })
      return {
        items: r.definitions,
        meta: r.total != null ? { total: r.total, page: r.page ?? 1, page_size: r.page_size ?? r.definitions.length } : undefined,
      }
    },
    [typeFilter],
  )
  const list = useSemanticPaginatedList(versionId, fetchPage, [typeFilter])

  return (
    <div className="pt-2">
      <h3 className="px-4 pb-2 text-sm font-semibold text-cloudera-navy">Recent definitions</h3>
      <SemanticAuthoringTableShell
        testId="semantic-recent-definitions"
        layout="overview"
        tableLayout="auto"
        minTableWidthClass="min-w-[720px]"
        searchPlaceholder="Search definitions…"
        search={list.search}
        onSearchChange={list.setSearch}
        loading={list.loading}
        error={list.error}
        onRetry={() => void list.reload()}
        emptyMessage="No definitions yet."
        emptyColSpan={7}
        hasRows={list.items.length > 0}
        addLabel=""
        onAdd={() => undefined}
        readOnly
        selectionMode={{ active: false, enter: () => undefined, exit: () => undefined }}
        page={list.page}
        pageSize={list.pageSize}
        total={list.total}
        onPageChange={list.setPage}
        onPageSizeChange={list.setPageSize}
      >
        <thead className="app-table-head">
          <tr>
            <th className="px-3 py-2">
              <SortableColumnHeader label="Name" field="name" activeField={list.sort} order={list.order} onSort={list.applySort} />
            </th>
            <th className="px-3 py-2">
              <select className="rounded border border-slate-200 text-xs normal-case" value={typeFilter} onChange={e => { setTypeFilter(e.target.value); list.setPage(1) }} aria-label="Type filter">
                <option value="">All types</option>
                <option value="metric">Metric</option>
                <option value="dimension">Dimension</option>
                <option value="relationship">Relationship</option>
                <option value="glossary">Glossary</option>
              </select>
            </th>
            <th className="px-3 py-2">Definition</th>
            <th className="px-3 py-2">Source</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">
              <SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} />
            </th>
            <th className="w-24 px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody className="align-middle">
          {list.items.map(row => (
            <tr key={`${row.object_kind}-${row.object_id}`} className="border-b border-slate-50">
              <td className="whitespace-nowrap px-3 py-2 font-medium">{row.name}</td>
              <td className="whitespace-nowrap px-3 py-2 text-xs">{row.type}</td>
              <td className="max-w-[12rem] truncate px-3 py-2">{row.definition || '—'}</td>
              <td className="max-w-[10rem] truncate px-3 py-2 text-xs">{row.source}</td>
              <td className="whitespace-nowrap px-3 py-2 text-xs text-emerald-800">{row.status}</td>
              <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-600">{formatSemanticModifiedCompact(row.modified_at)}</td>
              <td className="w-24 whitespace-nowrap px-3 py-2">
                <RowActionsMenu label={`Actions for ${row.name}`} items={[{ key: 'view', label: 'View in tab', onClick: () => undefined }]} />
              </td>
            </tr>
          ))}
        </tbody>
      </SemanticAuthoringTableShell>
    </div>
  )
}

function useStateFilter() {
  const [typeFilter, setTypeFilter] = useState('')
  return [typeFilter, setTypeFilter] as const
}
