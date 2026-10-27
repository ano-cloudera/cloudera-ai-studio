'use client'

import { Download, X } from 'lucide-react'
import { appConfig } from '../config/appConfig'
import type { ReportSection } from '../lib/reportDocument'
import { ReportDocumentSection } from './ReportDocumentSection'

type Props = {
  open: boolean
  onClose: () => void
  documentTitle: string
  userQuestion: string
  sections: ReportSection[]
  activeSectionId: string | null
  onExportPdf?: () => void
  exportingPdf?: boolean
}

export function AnalysisReportPanel({
  open,
  onClose,
  documentTitle,
  userQuestion,
  sections,
  activeSectionId,
  onExportPdf,
  exportingPdf = false,
}: Props) {
  if (!open) return null

  const activeId = activeSectionId ?? sections[sections.length - 1]?.id ?? null
  const activeSection = activeId ? sections.find(s => s.id === activeId) : undefined

  return (
    <>
      <button
        type="button"
        aria-label="Close document panel"
        className="fixed inset-0 z-40 bg-slate-900/20 lg:hidden"
        onClick={onClose}
      />
      <aside
        data-testid="analysis-workspace-panel"
        className="fixed inset-y-0 right-0 z-50 flex h-full min-h-0 w-full max-w-lg flex-col border-l border-slate-200/90 bg-white shadow-xl lg:static lg:z-0 lg:h-full lg:max-w-none lg:shadow-none"
        aria-label={appConfig.reportDocumentLabel}
      >
        <header className="shrink-0 border-b border-slate-200/90 bg-white px-4 py-3.5 sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                {appConfig.reportDocumentLabel}
              </p>
              <h2 className="mt-1 text-base font-bold leading-snug text-cloudera-navy sm:text-lg" title={documentTitle}>
                {documentTitle}
              </h2>
              {userQuestion.trim() ? (
                <p className="mt-1.5 line-clamp-2 text-xs text-slate-500" title={userQuestion}>
                  {userQuestion}
                </p>
              ) : (
                <p className="mt-1 text-xs text-slate-500">{appConfig.reportWorkspaceSubtitle}</p>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-lg border border-slate-200/90 p-2 text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-cloudera-navy"
              aria-label="Close panel"
              title="Close panel"
            >
              <X size={18} />
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200/90 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-800">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
              {appConfig.reportDatabaseStatusLabel}
            </span>
            {onExportPdf ? (
              <button
                type="button"
                disabled={exportingPdf}
                onClick={onExportPdf}
                className="btn-secondary !px-3 !py-1.5 !text-xs disabled:opacity-50"
              >
                <Download size={14} aria-hidden />
                {exportingPdf ? 'Exporting…' : 'Export PDF'}
              </button>
            ) : null}
          </div>
        </header>

        <div className="scrollbar-pane min-h-0 flex-1 overflow-y-scroll overscroll-contain px-4 py-4 sm:px-5 sm:py-5">
          {!activeSection ? (
            <p className="text-sm text-slate-500">Complete an analysis turn to populate this workspace.</p>
          ) : (
            <ReportDocumentSection key={activeSection.id} response={activeSection.response} />
          )}
        </div>
      </aside>
    </>
  )
}
