import type { ReactNode } from 'react'
import type { SemanticVersionRecord } from '../../types/api'

type StatusPill = { label: string; className: string } | null

type Props = {
  draftVersion: SemanticVersionRecord | null
  activeVersion: SemanticVersionRecord | null
  isEditable: boolean
  needsRuntimeActivation: boolean
  publishNeedsAttention: boolean
  statusPill: StatusPill
  onDiscardDraft?: () => void
  discardDisabled?: boolean
}

/** Version status + hint below the model toolbar (toolbar holds actions only). */
export function SemanticVersionContextBar({
  draftVersion,
  activeVersion,
  isEditable,
  needsRuntimeActivation,
  publishNeedsAttention,
  statusPill,
  onDiscardDraft,
  discardDisabled,
}: Props) {
  const showDiscardLink = Boolean(onDiscardDraft && draftVersion && !isEditable)

  let detail: ReactNode = null

  if (publishNeedsAttention) {
    detail = <span className="text-amber-900">Resolve publish issues before activating Ask Data.</span>
  } else if (isEditable && draftVersion) {
    detail = activeVersion ? (
      <>
        Ask Data still uses{' '}
        <span className="font-medium text-slate-800" data-testid="semantic-version-live-badge">
          published v{activeVersion.version_number}
        </span>
      </>
    ) : (
      <span>Not live until you publish.</span>
    )
  } else if (draftVersion && activeVersion) {
    detail = (
      <>
        Unpublished changes in draft v{draftVersion.version_number}. Ask Data uses{' '}
        <span className="font-medium text-slate-800">published v{activeVersion.version_number}</span>.
      </>
    )
  } else if (needsRuntimeActivation && activeVersion) {
    detail = (
      <span className="text-amber-900">
        Published v{activeVersion.version_number} is not live in Ask Data yet — use{' '}
        <span className="font-semibold">Publish</span> on the Publish tab.
      </span>
    )
  } else if (activeVersion) {
    detail = (
      <span>
        Viewing <span className="font-medium text-slate-800">published v{activeVersion.version_number}</span>.
      </span>
    )
  } else if (draftVersion) {
    detail = <span>Draft v{draftVersion.version_number} — publish when ready.</span>
  } else {
    detail = <span>No published version yet.</span>
  }

  if (!statusPill && !detail && !showDiscardLink) return null

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs leading-relaxed text-slate-600"
      data-testid="semantic-version-context"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {statusPill ? (
          <span
            data-testid="semantic-header-status-badge"
            className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusPill.className}`}
          >
            {statusPill.label}
          </span>
        ) : null}
        <span data-testid="semantic-version-context-detail">{detail}</span>
      </div>
      {showDiscardLink ? (
        <button
          type="button"
          data-testid="semantic-discard-draft"
          className="shrink-0 text-xs font-semibold text-red-800 underline-offset-2 hover:underline disabled:opacity-50"
          disabled={discardDisabled}
          onClick={() => onDiscardDraft?.()}
        >
          Discard draft
        </button>
      ) : null}
    </div>
  )
}
