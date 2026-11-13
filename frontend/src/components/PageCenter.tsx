import type { ReactNode } from 'react'

/** Shared width for every page beside the sidebar. The shell already pads `main`, so the page adds only a little, and a wide
 * screen is used up to 1680px instead of leaving a large empty band on both sides. */
export function pageCenterClassName(extra?: string): string {
  const base = 'mx-auto w-full max-w-[1680px] px-1 py-4 sm:px-2 sm:py-5'
  return extra ? `${base} ${extra}` : base
}

export function PageCenter({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={pageCenterClassName(className)}>{children}</div>
}
