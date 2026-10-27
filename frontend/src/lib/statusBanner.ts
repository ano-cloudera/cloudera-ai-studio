export type StatusBannerTone = 'success' | 'error' | 'neutral'

export function statusBannerClassName(tone: StatusBannerTone): string {
  if (tone === 'success') {
    return 'rounded-lg border border-emerald-200/90 bg-emerald-50/90 px-3 py-2 text-sm text-emerald-900'
  }
  if (tone === 'error') {
    return 'rounded-lg border border-red-200/90 bg-red-50/90 px-3 py-2 text-sm text-red-900'
  }
  return 'rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700'
}

/** Shared success styling for inline connection-test panels (connectors, data sources). */
export function connectionTestSuccessPanelClassName(): string {
  return 'rounded-lg border border-emerald-200/90 bg-emerald-50/90 px-4 py-3 text-sm'
}

export function connectionTestFailurePanelClassName(): string {
  return 'rounded-lg border border-red-200/90 bg-red-50/90 px-4 py-3 text-sm'
}
