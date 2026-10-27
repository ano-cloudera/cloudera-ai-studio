import type { ChatResponse } from '../../types/api'

export function ContextModeBadge({ response }: { response: ChatResponse }) {
  const mode = response.context_mode
  if (mode === 'RAW_TABLE') {
    const label = response.clarification?.options?.[0]?.name ?? 'Selected table'
    return (
      <span
        className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700"
        title="No published business metric was used. Calculation was inferred from the selected source."
      >
        Raw data · {label}
      </span>
    )
  }
  if (mode === 'GOVERNED_SEMANTIC') {
    const metric = response.data.governed_metric
    return (
      <span
        className="inline-flex items-center rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-900"
        title={metric ? `Metric: ${metric}` : 'Governed semantic model'}
      >
        Governed semantic{metric ? ` · ${metric}` : ''}
      </span>
    )
  }
  return null
}
