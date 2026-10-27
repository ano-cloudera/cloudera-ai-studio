import type { ReactNode } from 'react'

/** Shared width for list/settings pages (matches Connectors, Semantic Layer, etc.). */
export function pageCenterClassName(extra?: string): string {
  const base = 'mx-auto w-full max-w-6xl px-4 py-8'
  return extra ? `${base} ${extra}` : base
}

export function PageCenter({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={pageCenterClassName(className)}>{children}</div>
}
