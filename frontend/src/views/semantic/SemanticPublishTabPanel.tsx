type PublishMode = 'draft' | 'activate' | 'none'

type Props = {
  saving: boolean
  canPublish: boolean
  publishMode: PublishMode
  onPublish: () => void
  onGoToPreview: () => void
}

const STEPS: Record<PublishMode, string[]> = {
  draft: ['Validate the draft', 'Update the registry', 'Activate this version for Ask Data'],
  activate: ['The registry is already published', 'Activate this version for Ask Data'],
  none: [],
}

export function SemanticPublishTabPanel({ saving, canPublish, publishMode, onPublish, onGoToPreview }: Props) {
  const helper =
    publishMode === 'draft'
      ? 'Publish validates your draft, updates the registry, and activates Ask Data in one step.'
      : publishMode === 'activate'
        ? 'Registry is already published. Publish will activate this version for Ask Data.'
        : 'Edit the model and save a draft to publish changes. Review the Preview tab first.'
  const steps = STEPS[publishMode]

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5" data-testid="semantic-publish-tab-panel">
      <section className="max-w-2xl space-y-4">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-cloudera-navy">Publish this version</h3>
          <p className="text-sm text-slate-600">{helper}</p>
        </div>

        {steps.length ? (
          <ol className="space-y-2">
            {steps.map((step, index) => (
              <li key={step} className="flex items-center gap-3 text-sm text-slate-700">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-50 text-xs font-semibold text-cloudera-violet">
                  {index + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        ) : null}

        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Toolbar <span className="font-semibold">Save</span> only stores draft edits — it does not publish.
        </p>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            type="button"
            data-testid="semantic-save-publish"
            className="btn-primary h-9 px-4 text-sm"
            disabled={saving || !canPublish}
            onClick={() => onPublish()}
          >
            Publish
          </button>
          <button
            type="button"
            className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
            disabled={saving}
            onClick={() => onGoToPreview()}
          >
            Back to Preview
          </button>
        </div>
      </section>
    </div>
  )
}
