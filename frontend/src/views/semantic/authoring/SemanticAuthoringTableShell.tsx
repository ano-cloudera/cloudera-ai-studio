'use client'

import type { ReactNode } from 'react'
import { ServiceErrorState } from '../../../components/ServiceErrorState'
import { TablePagination } from '../../../components/knowledge/TablePagination'
import { TableSelectionModeButton } from '../../../components/table/TableSelectionModeButton'
import type { AppApiError } from '../../../lib/apiError'
import { SEMANTIC_PAGE_SIZE_OPTIONS, semanticTableBodyMaxHeightClass } from './semanticTableConstants'

type Props = {
  searchPlaceholder: string
  search: string
  onSearchChange: (v: string) => void
  loading: boolean
  error: AppApiError | null
  onRetry: () => void
  emptyMessage: string
  emptyColSpan: number
  hasRows: boolean
  addLabel: string
  onAdd: () => void
  addDisabled?: boolean
  readOnly?: boolean
  selectionMode: { active: boolean; enter: () => void; exit: () => void }
  selectionBar?: ReactNode
  page: number
  pageSize: number
  total: number
  onPageChange: (p: number) => void
  onPageSizeChange: (n: number) => void
  children: ReactNode
  testId?: string
  tableLayout?: 'fixed' | 'auto'
  /** Minimum table width before horizontal scroll (preserves column layout). */
  minTableWidthClass?: string
  /** Hide search row (e.g. version history). */
  compactToolbar?: boolean
  /** Overview: size to content so pagination is not clipped by parent flex. */
  layout?: 'authoring' | 'overview'
}

export function SemanticAuthoringTableShell(props: Props) {
  const layout = props.layout ?? 'authoring'
  const scrollMax =
    layout === 'overview' ? 'max-h-[min(16rem,40vh)]' : semanticTableBodyMaxHeightClass(props.pageSize)
  const minWidth = props.minTableWidthClass ?? 'min-w-[640px]'
  const sectionClass =
    layout === 'overview'
      ? 'flex flex-col overflow-visible border-t border-slate-100'
      : 'flex min-h-0 flex-1 flex-col overflow-hidden border-t border-slate-100'

  return (
    <section
      data-testid={props.testId}
      className={sectionClass}
    >
      {props.compactToolbar ? null : (
        <div className="shrink-0 space-y-2 border-b border-slate-100 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="search"
              placeholder={props.searchPlaceholder}
              value={props.search}
              onChange={e => props.onSearchChange(e.target.value)}
              className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            {props.selectionMode.active ? (
              props.selectionBar
            ) : (
              <TableSelectionModeButton entityLabel="rows" active={false} onClick={() => props.selectionMode.enter()} />
            )}
          </div>
          {!props.readOnly && props.addLabel ? (
            <button type="button" className="text-xs font-semibold text-cloudera-violet" disabled={props.addDisabled} onClick={props.onAdd}>
              {props.addLabel}
            </button>
          ) : null}
        </div>
      )}
      {props.error ? (
        <div className="p-4">
          <ServiceErrorState title="Unable to load" message={props.error.message} error={props.error} onRetry={props.onRetry} />
        </div>
      ) : (
        <>
          <div
            data-testid={props.testId ? `${props.testId}-scroll-body` : 'semantic-table-scroll-body'}
            className={`min-h-0 shrink overflow-x-auto overflow-y-auto ${scrollMax} [&_thead]:border-b [&_thead]:border-violet-100 [&_thead_th]:sticky [&_thead_th]:top-0 [&_thead_th]:z-10 [&_thead_th]:bg-violet-50 [&_thead_th]:text-cloudera-violet [&_thead_th]:shadow-[0_1px_0_0_rgb(237,233,254)]`}
          >
            <table
              className={`app-data-table ${minWidth} ${props.tableLayout === 'auto' ? 'table-auto' : 'table-fixed'}`}
            >
              {props.children}
            </table>
            {!props.loading && !props.hasRows ? (
              <p className="px-4 py-6 text-center text-sm text-slate-500">{props.emptyMessage}</p>
            ) : null}
          </div>
          <div
            className="sticky bottom-0 z-10 shrink-0 border-t border-slate-100 bg-white"
            data-testid={props.testId ? `${props.testId}-pagination` : 'semantic-table-pagination'}
          >
            <TablePagination
              page={props.page}
              pageSize={props.pageSize}
              total={props.total}
              onPageChange={props.onPageChange}
              onPageSizeChange={n => {
                props.onPageSizeChange(n)
                const maxPage = props.total ? Math.ceil(props.total / n) : 1
                if (props.page > maxPage) props.onPageChange(Math.max(1, maxPage))
              }}
              pageSizeOptions={SEMANTIC_PAGE_SIZE_OPTIONS}
            />
          </div>
        </>
      )}
    </section>
  )
}
