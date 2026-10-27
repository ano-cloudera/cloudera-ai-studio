'use client'

import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

export type WorkspaceIconTone = 'sky' | 'amber' | 'orange' | 'violet' | 'slate'

const ICON_TONE_CLASS: Record<WorkspaceIconTone, string> = {
  sky: 'bg-sky-100/90 text-sky-700',
  amber: 'bg-amber-100/85 text-amber-900',
  orange: 'bg-orange-50 text-cloudera-orange',
  violet: 'bg-violet-100/80 text-cloudera-violet',
  slate: 'bg-slate-100 text-cloudera-navy',
}

type SectionHeaderProps = {
  icon: LucideIcon
  tone: WorkspaceIconTone
  title: string
  action?: ReactNode
}

export function WorkspaceSectionHeader({ icon: Icon, tone, title, action }: SectionHeaderProps) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3.5 sm:gap-4">
        <span
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl sm:h-12 sm:w-12 ${ICON_TONE_CLASS[tone]}`}
          aria-hidden
        >
          <Icon size={21} strokeWidth={2} />
        </span>
        <h3 className="workspace-section-title">{title}</h3>
      </div>
      {action ? <div className="shrink-0 self-center">{action}</div> : null}
    </div>
  )
}

export function WorkspaceSection({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`border-t border-slate-200/70 mt-10 pt-10 first:mt-0 first:border-t-0 first:pt-0 ${className}`}
    >
      {children}
    </section>
  )
}

/** Content aligned with title text (indented past icon column on sm+). */
export function WorkspaceSectionContent({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`workspace-section-body sm:ml-[calc(3rem+1rem)] lg:ml-[calc(3rem+1.125rem)] ${className}`}
    >
      {children}
    </div>
  )
}

export function InsightNumberBadge({ index }: { index: number }) {
  return (
    <span
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-100/95 text-sm font-semibold tabular-nums text-emerald-800"
      aria-hidden
    >
      {index}
    </span>
  )
}

export function InsightListItem({ index, children }: { index: number; children: ReactNode }) {
  return (
    <li className="flex items-start gap-3.5 sm:gap-3.5">
      <InsightNumberBadge index={index} />
      <span className="workspace-body-text min-w-0 flex-1 pt-1">{children}</span>
    </li>
  )
}
