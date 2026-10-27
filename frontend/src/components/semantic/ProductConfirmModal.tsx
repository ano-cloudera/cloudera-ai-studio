'use client'

type Props = {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  cancelLabel?: string
  confirmTone?: 'danger' | 'primary'
  busy?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ProductConfirmModal({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel = 'Cancel',
  confirmTone = 'primary',
  busy,
  onCancel,
  onConfirm,
}: Props) {
  if (!open) return null
  const confirmClass = confirmTone === 'danger' ? 'bg-red-600 text-white hover:bg-red-700' : 'btn-primary'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-labelledby="confirm-title">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 id="confirm-title" className="text-lg font-semibold text-cloudera-navy">
          {title}
        </h2>
        <p className="mt-2 whitespace-pre-line text-sm text-slate-600">{message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className={`h-9 rounded-lg px-3 text-sm font-semibold ${confirmClass}`} disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
