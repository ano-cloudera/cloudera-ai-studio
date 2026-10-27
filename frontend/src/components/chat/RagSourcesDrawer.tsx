'use client'

import { X } from 'lucide-react'
import type { ChatResponse } from '../../types/api'
import { formatCitationLabel } from '../../lib/ragReport'

type Props = {
  open: boolean
  response: ChatResponse | null
  onClose: () => void
}

export function RagSourcesDrawer({ open, response, onClose }: Props) {
  if (!open || !response?.citations?.length) return null
  return (
    <div className="fixed inset-0 z-[120] flex justify-end bg-black/30" role="dialog" aria-modal="true" aria-label="Sources" data-testid="rag-sources-drawer">
      <button type="button" className="flex-1" aria-label="Close sources" onClick={onClose} />
      <div className="flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-cloudera-navy">Sources</h2>
          <button type="button" aria-label="Close" className="rounded-lg p-1 hover:bg-slate-100" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <ul className="flex-1 space-y-3 overflow-y-auto p-4 text-sm text-slate-700">
          {response.citations.map((cite, index) => (
            <li
              key={cite.chunk_id || `${index}`}
              className="rounded-lg border border-slate-200 p-3"
              data-testid="rag-source-item"
            >
              <div className="font-semibold text-cloudera-navy">[{index + 1}] {formatCitationLabel(cite, index)}</div>
              {cite.snippet ? <p className="mt-2 text-xs leading-relaxed text-slate-600">{cite.snippet}</p> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
