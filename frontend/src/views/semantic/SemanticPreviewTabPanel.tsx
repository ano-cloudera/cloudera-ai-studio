import type { SemanticArtifactPreview } from '../../types/api'
import { SemanticArtifactPreviewPanel } from './authoring/SemanticArtifactPreviewPanel'

type Props = {
  artifact: SemanticArtifactPreview | null
  artifactLoading: boolean
  previewVersionId: string | null
  saving: boolean
  onRefreshArtifact: () => void
  onGoToPublish: () => void
  compareSections: Array<{ label: string; added: string[]; changed: string[]; removed: string[] }>
}

export function SemanticPreviewTabPanel({
  artifact,
  artifactLoading,
  previewVersionId,
  saving,
  onRefreshArtifact,
  onGoToPublish,
  compareSections,
}: Props) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="semantic-preview-tab-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <p className="text-sm text-slate-600">
          Review the generated artifact from your draft. When it looks correct, publish from the Publish tab.
        </p>
        <button
          type="button"
          className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-cloudera-navy shadow-sm hover:bg-slate-50"
          disabled={saving}
          onClick={() => onGoToPublish()}
        >
          Continue to Publish
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-slate-100 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Semantic preview
        </div>
        {!previewVersionId ? (
          <p className="p-4 text-sm text-slate-500">No semantic version available to preview yet.</p>
        ) : (
          <SemanticArtifactPreviewPanel
            artifact={artifact}
            loading={artifactLoading}
            onRefresh={onRefreshArtifact}
            defaultExpanded
          />
        )}
        {compareSections.length ? (
          <div className="border-t border-slate-100 p-4 text-sm">
            <h3 className="font-semibold text-cloudera-navy">Compare draft vs published</h3>
            {compareSections.map(section => (
              <div key={section.label} className="mt-2 rounded-lg border border-slate-100 p-2 text-xs">
                <div className="font-semibold">{section.label}</div>
                {section.added.length ? <div>Added: {section.added.join('; ')}</div> : null}
                {section.changed.length ? <div>Changed: {section.changed.join('; ')}</div> : null}
                {section.removed.length ? <div>Removed: {section.removed.join('; ')}</div> : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
