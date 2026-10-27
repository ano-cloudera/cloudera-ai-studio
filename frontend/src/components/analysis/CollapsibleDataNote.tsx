'use client'

import { useState } from 'react'
import { ChevronDown, Info } from 'lucide-react'

const PREVIEW_CHARS = 140

type Props = {
  note: string | null
}

export function CollapsibleDataNote({ note }: Props) {
  const [open, setOpen] = useState(false)
  if (!note?.trim()) return null

  const trimmed = note.trim()
  const needsCollapse = trimmed.length > PREVIEW_CHARS
  const preview = needsCollapse ? `${trimmed.slice(0, PREVIEW_CHARS).trim()}…` : trimmed

  return (
    <div className="rounded-xl border border-slate-200/90 bg-slate-50/60 p-3">
      <div className="flex items-start gap-2">
        <Info size={15} className="mt-0.5 shrink-0 text-slate-400" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-slate-600">Data note</p>
          <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{open ? trimmed : preview}</p>
          {needsCollapse ? (
            <button
              type="button"
              onClick={() => setOpen(v => !v)}
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-cloudera-orange hover:underline"
            >
              {open ? 'Hide details' : 'Show details'}
              <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
