type TabTarget = 'entities' | 'metrics' | 'dimensions' | 'relationships' | 'glossary' | 'preview' | 'publish_config'

type Props = {
  welcome?: boolean
  isEditable: boolean
  entityCount: number
  metricCount: number
  dimensionCount: number
  relationshipCount: number
  termCount?: number
  metricsWithExplicitBreakdown?: number
  previewReviewed: boolean
  publishComplete: boolean
  publishIssueCount?: number
  onGoTo: (tab: TabTarget) => void
  onDismissWelcome?: () => void
}

type Step = {
  id: string
  label: string
  done: boolean
  tab: TabTarget
}

function StepList({ steps, onGoTo }: { steps: Step[]; onGoTo: (tab: TabTarget) => void }) {
  return (
    <ul className="space-y-1.5">
      {steps.map(step => (
        <li key={step.id}>
          <button
            type="button"
            className="flex w-full items-start gap-2 rounded-md px-1 py-1 text-left text-sm hover:bg-slate-50"
            onClick={() => onGoTo(step.tab)}
          >
            <span
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                step.done ? 'bg-emerald-100 text-emerald-800' : 'border border-slate-300 text-slate-400'
              }`}
              aria-hidden
            >
              {step.done ? '✓' : '·'}
            </span>
            <span className={step.done ? 'text-slate-600' : 'font-medium text-cloudera-navy'}>{step.label}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

export function SemanticOverviewChecklist({
  welcome,
  isEditable,
  entityCount,
  metricCount,
  dimensionCount,
  relationshipCount,
  termCount = 0,
  metricsWithExplicitBreakdown = 0,
  previewReviewed,
  publishComplete,
  publishIssueCount = 0,
  onGoTo,
  onDismissWelcome,
}: Props) {
  const needsRelationships = entityCount > 1

  const requiredSteps: Step[] = [
    {
      id: 'models',
      label: entityCount ? `${entityCount} data model(s) defined` : 'Add data models from your connection',
      done: entityCount > 0,
      tab: 'entities',
    },
    {
      id: 'metrics',
      label: metricCount ? `${metricCount} metric(s) defined` : 'Add or accept suggested metrics',
      done: metricCount > 0,
      tab: 'metrics',
    },
    {
      id: 'dimensions',
      label: dimensionCount ? `${dimensionCount} dimension(s) defined` : 'Confirm dimensions on each model',
      done: dimensionCount > 0,
      tab: 'dimensions',
    },
    {
      id: 'relationships',
      label: needsRelationships
        ? relationshipCount
          ? `${relationshipCount} relationship(s) for cross-model joins`
          : 'Define joins between data models'
        : relationshipCount
          ? `${relationshipCount} relationship(s) defined`
          : 'Relationships optional with one data model',
      done: needsRelationships ? relationshipCount > 0 : true,
      tab: 'relationships',
    },
    {
      id: 'preview',
      label: 'Review semantic preview',
      done: previewReviewed,
      tab: 'preview',
    },
    {
      id: 'publish',
      label: publishComplete
        ? 'Published and active in Ask Data'
        : publishIssueCount > 0
          ? `Resolve ${publishIssueCount} publish issue(s) before activating`
          : 'Publish when preview looks correct',
      done: publishComplete,
      tab: 'publish_config',
    },
  ]

  const requiredDone = requiredSteps.filter(s => s.id !== 'publish').every(s => s.done)

  const recommendedSteps: Step[] = [
    ...(metricCount > 0
      ? [
          {
            id: 'metric_breakdowns',
            label:
              metricsWithExplicitBreakdown > 0
                ? `Custom breakdown scope on ${metricsWithExplicitBreakdown} metric(s)`
                : 'Breakdown dimensions use defaults (all eligible) — optional: restrict per metric',
            done: true,
            tab: 'metrics' as TabTarget,
          },
        ]
      : []),
    ...(termCount > 0
      ? [
          {
            id: 'glossary',
            label: `Review ${termCount} glossary term(s)`,
            done: termCount > 0,
            tab: 'glossary' as TabTarget,
          },
        ]
      : [
          {
            id: 'glossary',
            label: 'Add glossary terms for business language (optional)',
            done: false,
            tab: 'glossary' as TabTarget,
          },
        ]),
  ]

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white px-3 py-3 shadow-sm"
      data-testid="semantic-overview-checklist"
    >
      {welcome ? (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2 rounded-md border border-emerald-100 bg-emerald-50/80 px-3 py-2 text-sm text-emerald-950">
          <p>
            <span className="font-semibold">Semantic model created.</span> Use any tab to edit — you do not need to
            finish every step in order. Publish when validation passes.
          </p>
          {onDismissWelcome ? (
            <button type="button" className="text-xs font-semibold text-emerald-900 underline" onClick={onDismissWelcome}>
              Dismiss
            </button>
          ) : null}
        </div>
      ) : null}

      <p className="text-xs text-slate-500">
        Edit in any order. Only validation errors block publish; recommended steps improve Ask Data quality.
      </p>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Required for publish</h3>
      {!requiredDone && !publishComplete ? (
        <p className="mt-1 text-xs text-amber-900">Complete unchecked items below (or fix issues on the Publish tab).</p>
      ) : null}
      <div className="mt-2" data-testid="semantic-checklist-required">
        <StepList steps={requiredSteps} onGoTo={onGoTo} />
      </div>

      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Recommended</h3>
      <div className="mt-2" data-testid="semantic-checklist-recommended">
        <StepList steps={recommendedSteps} onGoTo={onGoTo} />
      </div>

      {!isEditable ? (
        <p className="mt-3 text-xs text-amber-900">Select Edit in the toolbar to change definitions.</p>
      ) : null}
    </div>
  )
}
