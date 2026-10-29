'use client'

import { ExternalLink, X } from 'lucide-react'
import type { ChatResponse } from '../../types/api'
import { citationPdfUrl, tidySnippet } from '../../lib/ragReport'
import { SourceFileIcon } from './SourceFileIcon'

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
          {response.citations.map((cite, index) => {
            const pdfUrl = citationPdfUrl(cite)
            const snippet = tidySnippet(cite.snippet)
            return (
              <li
                key={cite.chunk_id || `${index}`}
                className="rounded-xl border border-slate-200 bg-white p-3.5"
                data-testid="rag-source-item"
              >
                <div className="flex items-start gap-2.5">
                  <SourceFileIcon filename={cite.filename} />
                  <div className="min-w-0 flex-1">
                    <div className="break-words font-semibold leading-snug text-cloudera-navy">
                      [{index + 1}] {cite.filename?.trim() || `Document ${index + 1}`}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      {cite.page_number != null ? (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                          Page {cite.page_number}
                        </span>
                      ) : null}
                      {cite.section?.trim() ? <span>{cite.section}</span> : null}
                    </div>
                  </div>
                </div>
                {snippet ? (
                  <p className="mt-3 border-l-2 border-slate-200 pl-3 text-[13px] leading-relaxed text-slate-600">
                    {snippet}
                  </p>
                ) : null}
                {pdfUrl ? (
                  <a
                    href={pdfUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-cloudera-orange hover:underline"
                  >
                    Open PDF{cite.page_number != null ? ` at page ${cite.page_number}` : ''}
                    <ExternalLink size={12} aria-hidden />
                  </a>
                ) : null}
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
