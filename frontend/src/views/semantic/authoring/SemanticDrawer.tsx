'use client'

import type { ReactNode } from 'react'

type Props = {
  open: boolean
  title: string
  onClose: () => void
  onSave: () => void
  onCancel: () => void
  saving?: boolean
  saveDisabled?: boolean
  errors?: string[]
  footer?: 'save-cancel' | 'close-only'
  children: ReactNode
}

export function SemanticDrawer({ open, title, onClose, onSave, onCancel, saving, saveDisabled, errors, footer = 'save-cancel', children }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="dialog" aria-label={title}>
      <button type="button" className="flex-1" aria-label="Close drawer backdrop" onClick={onCancel} />
      <div className="flex h-full w-full max-w-lg flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="text-lg font-semibold text-cloudera-navy">{title}</h2>
          <button type="button" className="text-sm text-slate-600" onClick={onCancel}>
            Close
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 text-sm">{children}</div>
        {errors?.length ? (
          <div className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-800">
            {errors.map(e => (
              <div key={e}>{e}</div>
            ))}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-slate-100 px-4 py-3">
          {footer === 'close-only' ? (
            <button type="button" className="btn-secondary h-9 px-4 text-sm" onClick={onCancel}>
              Close
            </button>
          ) : (
            <>
              <button type="button" className="btn-secondary h-9 px-4 text-sm" disabled={saving} onClick={onCancel}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary h-9 px-4 text-sm"
                disabled={saving || saveDisabled}
                onClick={() => {
                  void Promise.resolve(onSave()).catch(() => undefined)
                }}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
