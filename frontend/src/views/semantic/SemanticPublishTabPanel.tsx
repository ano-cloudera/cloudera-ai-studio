type PublishMode = 'draft' | 'activate' | 'none'

type Props = {
  saving: boolean
  canPublish: boolean
  publishMode: PublishMode
  onPublish: () => void
  onGoToPreview: () => void
}

export function SemanticPublishTabPanel({ saving, canPublish, publishMode, onPublish, onGoToPreview }: Props) {
  const helper =
    publishMode === 'draft'
      ? 'Publish validates your draft, updates the registry, and activates Ask Data in one step.'
      : publishMode === 'activate'
        ? 'Registry is already published. Publish will activate this version for Ask Data.'
        : 'Edit the model and save a draft to publish changes. Review the Preview tab first.'

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="semantic-publish-tab-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
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
      <div className="flex flex-1 flex-col justify-center px-6 py-10 text-sm text-slate-600">
        <p className="max-w-xl">{helper}</p>
        <p className="mt-3 max-w-xl text-xs text-slate-500">
          Toolbar <span className="font-semibold">Save</span> only stores draft edits — it does not publish.
        </p>
      </div>
    </div>
  )
}
