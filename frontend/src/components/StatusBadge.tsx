const STATUS_TONE: Record<string, string> = {
  Published: 'bg-emerald-50 text-emerald-800',
  Draft: 'bg-violet-50 text-violet-800',
}

/** Published in green and Draft in violet, the same everywhere a version status is shown. */
export function StatusBadge({ label }: { label: string }) {
  return <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${STATUS_TONE[label] ?? 'bg-slate-100 text-slate-600'}`}>{label}</span>
}
