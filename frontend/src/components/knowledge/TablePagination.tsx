'use client'

type Props = {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

const DEFAULT_PAGE_SIZES = [10, 25, 50]

type PaginationProps = Props & {
  pageSizeOptions?: readonly number[]
}

export function TablePagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = DEFAULT_PAGE_SIZES,
}: PaginationProps) {
  const totalPages = total ? Math.ceil(total / pageSize) : 0
  const start = total ? (page - 1) * pageSize + 1 : 0
  const end = total ? Math.min(page * pageSize, total) : 0

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
      <span>
        Showing {start}–{end} of {total}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1">
          Rows
          <select
            className="rounded border border-slate-200 px-1 py-0.5"
            value={pageSize}
            onChange={e => onPageSizeChange(Number(e.target.value))}
          >
            {pageSizeOptions.map(size => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="rounded border border-slate-200 px-2 py-1 disabled:opacity-40"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          ‹ Previous
        </button>
        <span className="font-semibold text-cloudera-navy">
          {page}
          {totalPages ? ` / ${totalPages}` : ''}
        </span>
        <button
          type="button"
          className="rounded border border-slate-200 px-2 py-1 disabled:opacity-40"
          disabled={!totalPages || page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next ›
        </button>
      </div>
    </div>
  )
}
