'use client'

import type { ReactNode } from 'react'

type Props = {
  icon?: ReactNode
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-8 py-14 text-center">
      {icon ? <div className="mx-auto mb-4 flex justify-center text-slate-500">{icon}</div> : null}
      <h2 className="text-lg font-semibold text-cloudera-navy">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">{description}</p>
      {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
    </div>
  )
}
