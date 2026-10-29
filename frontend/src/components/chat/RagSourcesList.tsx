import type { CitationRecord } from '../../types/api'
import { citationPdfUrl } from '../../lib/ragReport'
import { SourceFileIcon } from './SourceFileIcon'

type Props = {
  citations: CitationRecord[]
  onViewSources?: () => void
  /** At most this many distinct files are listed inline. */
  limit?: number
}

type SourceGroup = {
  key: string
  cite: CitationRecord
  pages: number[]
}

/** One row per file, with every cited page, so the same document is not listed twice. */
export function groupSources(citations: CitationRecord[], limit: number): SourceGroup[] {
  const groups = new Map<string, SourceGroup>()
  for (const cite of citations) {
    const key = cite.document_id || cite.filename || cite.chunk_id
    let group = groups.get(key)
    if (!group) {
      if (groups.size >= limit) continue
      group = { key, cite, pages: [] }
      groups.set(key, group)
    }
    if (cite.page_number != null && !group.pages.includes(cite.page_number)) group.pages.push(cite.page_number)
  }
  return [...groups.values()].map(group => ({ ...group, pages: [...group.pages].sort((a, b) => a - b) }))
}

const LINK_CLASS = 'rounded-md outline-offset-2 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2'

/** The sources under a document answer: a white card, one row per file, each page opening the original PDF. */
export function RagSourcesList({ citations, onViewSources, limit = 5 }: Props) {
  const groups = groupSources(citations, limit)
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm" data-testid="rag-sources-card">
      <div className="mb-2 text-xs font-semibold text-cloudera-navy">Sources</div>
      <ul className="space-y-1.5">
        {groups.map((group, index) => {
          const name = group.cite.filename?.trim() || `Document ${index + 1}`
          const firstUrl = citationPdfUrl({ ...group.cite, page_number: group.pages[0] ?? null })
          const label = (
            <>
              <SourceFileIcon filename={group.cite.filename} />
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-slate-700">{name}</span>
            </>
          )
          return (
            <li key={group.key} className="flex items-center gap-2.5">
              {firstUrl ? (
                <a
                  href={firstUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`flex min-w-0 flex-1 items-center gap-2.5 py-0.5 ${LINK_CLASS}`}
                  title="Open the PDF"
                >
                  {label}
                </a>
              ) : (
                <div className="flex min-w-0 flex-1 items-center gap-2.5 py-0.5">{label}</div>
              )}
              <div className="flex shrink-0 flex-wrap justify-end gap-1">
                {group.pages.map(page => {
                  const pageUrl = citationPdfUrl({ ...group.cite, page_number: page })
                  const chip = 'rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600'
                  return pageUrl ? (
                    <a
                      key={page}
                      href={pageUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`${chip} hover:bg-slate-200`}
                      title={`Open the PDF at page ${page}`}
                    >
                      Page {page}
                    </a>
                  ) : (
                    <span key={page} className={chip}>
                      Page {page}
                    </span>
                  )
                })}
              </div>
            </li>
          )
        })}
      </ul>
      {onViewSources ? (
        <button
          type="button"
          className="mt-3 text-xs font-semibold text-cloudera-orange hover:underline"
          data-testid="rag-view-sources"
          onClick={onViewSources}
        >
          {citations.length} source{citations.length === 1 ? '' : 's'} · View sources
        </button>
      ) : null}
    </div>
  )
}
