import type { SemanticOverviewPayload } from '../../types/api'
import { formatSemanticModifiedCompact } from './authoring/semanticFormat'
import { RecentDefinitionsPanel } from './authoring/RecentDefinitionsPanel'

type Props = {
  overview: SemanticOverviewPayload | null
  versionId: string | null
}

function CompactReadiness({ issueCount }: { issueCount: number }) {
  if (issueCount > 0) {
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-amber-900" data-testid="semantic-overview-readiness">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
        Needs attention · {issueCount} issue{issueCount === 1 ? '' : 's'}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 font-medium text-emerald-800" data-testid="semantic-overview-readiness">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
      Ready to publish
    </span>
  )
}

export function SemanticOverviewPanel({ overview, versionId }: Props) {
  const counts = overview?.counts
  const summaryCards = [
    ['Data Models', counts?.entities ?? 0],
    ['Metrics', counts?.metrics ?? 0],
    ['Dimensions', counts?.dimensions ?? 0],
    ['Relationships', counts?.relationships ?? 0],
    ['Glossary terms', counts?.terms ?? 0],
  ] as const

  const metadataParts: string[] = []
  if (overview?.model.updated_at) {
    metadataParts.push(`Last modified ${formatSemanticModifiedCompact(overview.model.updated_at)}`)
  }
  if (overview?.published_version_number != null) {
    metadataParts.push(`Published v${overview.published_version_number}`)
  }

  return (
    <div className="flex flex-col gap-2 p-4 pt-3 pb-4" data-testid="semantic-overview-panel">
      {overview ? (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600" data-testid="semantic-overview-metadata">
          {metadataParts.length ? <span>{metadataParts.join(' · ')} · </span> : null}
          <CompactReadiness issueCount={overview.issue_count ?? 0} />
        </div>
      ) : null}

      <div
        className="grid grid-cols-2 gap-2 lg:grid-cols-5"
        data-testid="semantic-overview-summary"
      >
        {summaryCards.map(([label, value]) => (
          <div
            key={label}
            className="flex h-[88px] flex-col justify-between rounded-md border border-slate-100 bg-slate-50/80 px-2.5 py-2"
          >
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
            <div className="text-2xl font-semibold leading-none text-cloudera-navy">{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-1 flex flex-col overflow-visible rounded-lg border border-slate-200 bg-white shadow-sm" data-testid="semantic-recent-definitions-section">
        <RecentDefinitionsPanel versionId={versionId} />
      </div>
    </div>
  )
}
