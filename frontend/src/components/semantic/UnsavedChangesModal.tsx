type Props = {
  open: boolean
  onKeepEditing: () => void
  onDiscard: () => void
  onSaveAndContinue: () => void
  saving?: boolean
}

export function UnsavedChangesModal({ open, onKeepEditing, onDiscard, onSaveAndContinue, saving }: Props) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-labelledby="unsaved-title"
      data-testid="unsaved-changes-modal"
    >
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 id="unsaved-title" className="text-lg font-semibold text-cloudera-navy">
          Unsaved changes
        </h2>
        <p className="mt-2 text-sm text-slate-600">You have changes that have not been saved.</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button type="button" className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-semibold" onClick={onKeepEditing}>
            Keep editing
          </button>
          <button type="button" className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-red-700" onClick={onDiscard}>
            Discard changes
          </button>
          <button type="button" className="btn-primary h-9 px-3 text-sm" disabled={saving} onClick={onSaveAndContinue}>
            Save and continue
          </button>
        </div>
      </div>
    </div>
  )
}
