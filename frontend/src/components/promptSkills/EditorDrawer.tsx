'use client'

import type { ReactNode } from 'react'
import { X } from 'lucide-react'

type Tab = { id: string; label: string }

type Props = {
  open: boolean
  title: string
  subtitle?: string
  tabs: Tab[]
  activeTab: string
  onTabChange: (id: string) => void
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}

export function EditorDrawer({ open, title, subtitle, tabs, activeTab, onTabChange, onClose, children, footer }: Props) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="presentation" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-[min(900px,100vw)] flex-col bg-white shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-drawer-title"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <h2 id="editor-drawer-title" className="truncate text-lg font-semibold text-cloudera-navy">
              {title}
            </h2>
            {subtitle ? <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p> : null}
          </div>
          <button type="button" aria-label="Close editor" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex shrink-0 gap-1 border-b border-slate-100 px-5" role="tablist">
          {tabs.map(tab => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`border-b-2 px-3 py-2.5 text-sm font-medium ${
                activeTab === tab.id
                  ? 'border-cloudera-violet text-cloudera-violet'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {footer ? <div className="shrink-0 border-t border-slate-100 px-5 py-3">{footer}</div> : null}
      </div>
    </div>
  )
}
