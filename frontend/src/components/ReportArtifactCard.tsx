'use client'

import { ChevronRight, FileText } from 'lucide-react'

type Props = {
  title: string
  subtitle: string
  active?: boolean
  onOpen: () => void
}

export function ReportArtifactCard({ title, subtitle, active = false, onOpen }: Props) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex w-full max-w-md items-center gap-3 rounded-xl border bg-white p-3.5 text-left shadow-sm transition-all hover:border-cloudera-orange/35 hover:shadow-md ${
        active ? 'border-cloudera-orange/45 ring-2 ring-cloudera-orange/15' : 'border-slate-200/90'
      }`}
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-50 to-slate-50 text-cloudera-violet ring-1 ring-violet-100">
        <FileText size={18} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold text-cloudera-navy">{title}</span>
        <span className="mt-0.5 block truncate text-xs text-slate-500">{subtitle}</span>
      </span>
      <ChevronRight size={18} className="shrink-0 text-cloudera-orange" aria-hidden />
    </button>
  )
}
