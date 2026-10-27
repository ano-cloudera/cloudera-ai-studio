import type { SemanticOverviewPayload } from '../../types/api'
import { formatSemanticModifiedCompact } from './authoring/semanticFormat'
import { SemanticOverviewChecklist } from './SemanticOverviewChecklist'

type OverviewNavTab = 'entities' | 'metrics' | 'dimensions' | 'relationships' | 'glossary' | 'preview' | 'publish_config'

type Props = {
  overview: SemanticOverviewPayload | null
  editingDraftVersionNumber?: number | null
  showWelcomeChecklist?: boolean
  isEditable?: boolean
  previewReviewed?: boolean
  publishComplete?: boolean
  metricsWithExplicitBreakdown?: number
  publishIssueCount?: number
  onDismissWelcome?: () => void
  onNavigateTab?: (tab: OverviewNavTab) => void
}

const SUMMARY_CARD_TABS: Record<string, OverviewNavTab> = {
  'Data Models': 'entities',
  Metrics: 'metrics',
  Dimensions: 'dimensions',
  Relationships: 'relationships',
  'Glossary terms': 'glossary',
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

export function SemanticOverviewPanel({
  overview,
  editingDraftVersionNumber = null,
  showWelcomeChecklist = false,
  isEditable = false,
  previewReviewed = false,
  publishComplete = false,
  metricsWithExplicitBreakdown = 0,
  publishIssueCount = 0,
  onDismissWelcome,
  onNavigateTab,
}: Props) {
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
  if (editingDraftVersionNumber != null) {
    metadataParts.push(`Editing draft v${editingDraftVersionNumber}`)
  } else if (overview?.published_version_number != null) {
    metadataParts.push(`Published v${overview.published_version_number}`)
  } else if (overview?.draft_version_number != null) {
    metadataParts.push(`Draft v${overview.draft_version_number}`)
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
        {summaryCards.map(([label, value]) => {
          const targetTab = onNavigateTab ? SUMMARY_CARD_TABS[label] : undefined
          const inner = (
            <>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
              <div className="text-2xl font-semibold leading-none text-cloudera-navy">{value}</div>
            </>
          )
          return targetTab ? (
            <button
              key={label}
              type="button"
              className="flex h-[88px] flex-col justify-between rounded-md border border-slate-100 bg-slate-50/80 px-2.5 py-2 text-left transition hover:border-violet-200 hover:bg-violet-50/40"
              onClick={() => onNavigateTab!(targetTab)}
            >
              {inner}
            </button>
          ) : (
            <div
              key={label}
              className="flex h-[88px] flex-col justify-between rounded-md border border-slate-100 bg-slate-50/80 px-2.5 py-2"
            >
              {inner}
            </div>
          )
        })}
      </div>

      {onNavigateTab ? (
        <SemanticOverviewChecklist
          welcome={showWelcomeChecklist}
          isEditable={isEditable}
          entityCount={counts?.entities ?? 0}
          metricCount={counts?.metrics ?? 0}
          dimensionCount={counts?.dimensions ?? 0}
          relationshipCount={counts?.relationships ?? 0}
          termCount={counts?.terms ?? 0}
          metricsWithExplicitBreakdown={metricsWithExplicitBreakdown}
          publishIssueCount={publishIssueCount}
          previewReviewed={previewReviewed}
          publishComplete={publishComplete}
          onGoTo={onNavigateTab}
          onDismissWelcome={onDismissWelcome}
        />
      ) : null}
    </div>
  )
}
