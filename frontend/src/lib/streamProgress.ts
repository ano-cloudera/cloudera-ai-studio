export const DETAILED_PROGRESS_STEPS = [
  'Understanding your question',
  'Finding relevant data',
  'Validating the query',
  'Fetching data',
  'Preparing insights',
] as const

export const SUMMARY_PROGRESS_PHASES = [
  'Understanding your question',
  'Analyzing data',
  'Preparing the answer',
] as const

export type ProgressTraceEntry = {
  stage: string
  label: string
  detail?: string | null
}

export function stageToStepIndex(stage: string, label: string): number {
  const bucket = `${stage} ${label}`.toLowerCase()
  if (bucket.includes('understand') || bucket.includes('memahami')) return 0
  if (bucket.includes('retrieve') || bucket.includes('search') || bucket.includes('knowledge')) return 1
  if (bucket.includes('rerank') || bucket.includes('review') || bucket.includes('source')) return 2
  if (bucket.includes('plan') || bucket.includes('merencan')) return 1
  if (bucket.includes('valid') || bucket.includes('validasi')) return 2
  if (bucket.includes('query') || bucket.includes('impala') || bucket.includes('menjalankan')) return 3
  if (bucket.includes('prepar') && bucket.includes('answer')) return 4
  return 4
}

export function mergeProgressStep(current: number, stage: string, label: string): number {
  return Math.max(current, stageToStepIndex(stage, label))
}

/** Map detailed step index (0–4) to summary phase index (0–2). */
export function detailedStepToSummaryPhase(stepIndex: number): number {
  if (stepIndex <= 0) return 0
  if (stepIndex <= 3) return 1
  return 2
}

export function compactProgressLabel(stepIndex: number, complete: boolean): string {
  if (complete) return 'Analysis complete'
  const phase = SUMMARY_PROGRESS_PHASES[detailedStepToSummaryPhase(stepIndex)]
  return phase
}

export function safeProgressDetail(detail: string | null | undefined): string | null {
  if (!detail?.trim()) return null
  const trimmed = detail.trim()
  if (/^\d+\s+baris$/i.test(trimmed)) return trimmed
  if (/row/i.test(trimmed) && trimmed.length < 40) return trimmed
  if (/metric:/i.test(trimmed) || /sat_[a-z]/i.test(trimmed) || trimmed.includes('SELECT')) return null
  if (trimmed.length > 100) return null
  return trimmed
}

export function formatTechnicalLine(entry: ProgressTraceEntry): string {
  const safe = safeProgressDetail(entry.detail)
  const label = entry.label.trim()
  if (safe) return `${label} — ${safe}`
  return label
}

/** User-facing governance chip — no internal agent product names. */
export function governanceDisplayLabel(
  messages: { response?: { strategy?: string } | null }[],
  envChip: string | undefined,
): string {
  const trimmed = envChip?.trim()
  if (trimmed) {
    const lower = trimmed.toLowerCase()
    if (lower.includes('tempo-agent-v3') || lower.includes('ossie')) return 'Governed · Impala'
    if (lower.includes('duckdb') || lower.includes('exploratory')) return 'Exploratory · Local'
    return trimmed
  }
  if (messages.some(message => message.response?.strategy === 'exploratory_local')) {
    return 'Exploratory · Local'
  }
  return 'Governed · Impala'
}
