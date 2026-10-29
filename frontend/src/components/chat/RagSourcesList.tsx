import type { CitationRecord } from '../../types/api'
import { SourceFileIcon } from './SourceFileIcon'

type Props = {
  citations: CitationRecord[]
  onViewSources?: () => void
  /** At most this many distinct file/page rows are listed inline. */
  limit?: number
}

function distinctSources(citations: CitationRecord[], limit: number): CitationRecord[] {
  const seen = new Set<string>()
  const rows: CitationRecord[] = []
  for (const cite of citations) {
    const key = `${cite.document_id}|${cite.page_number ?? ''}`
    if (seen.has(key)) continue
    seen.add(key)
    rows.push(cite)
    if (rows.length >= limit) break
  }
  return rows
}

/** The sources under a document answer: a white card, one row per file and page, with a typed file icon. */
export function RagSourcesList({ citations, onViewSources, limit = 5 }: Props) {
  const rows = distinctSources(citations, limit)
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm" data-testid="rag-sources-card">
      <div className="mb-2 text-xs font-semibold text-cloudera-navy">Sources</div>
      <ul className="space-y-2">
        {rows.map((cite, index) => (
          <li key={cite.chunk_id || index} className="flex items-center gap-2.5">
            <SourceFileIcon filename={cite.filename} />
            <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-slate-700">
              {cite.filename?.trim() || `Document ${index + 1}`}
            </span>
            {cite.page_number != null ? (
              <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                Page {cite.page_number}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="mt-3 text-xs font-semibold text-cloudera-orange hover:underline"
        data-testid="rag-view-sources"
        onClick={onViewSources}
      >
        {citations.length} source{citations.length === 1 ? '' : 's'} · View sources
      </button>
    </div>
  )
}
