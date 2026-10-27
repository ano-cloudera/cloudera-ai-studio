import type { ChatResponse } from '../../types/api'
import { executiveTrustLine, isExecutiveAudience } from '../../lib/audienceMode'

type Props = {
  response: ChatResponse
  /** When true, use business-friendly labels (management audience). */
  executive?: boolean
}

export function ContextModeBadge({ response, executive = isExecutiveAudience() }: Props) {
  const mode = response.context_mode
  if (mode === 'RAW_TABLE') {
    const label = response.clarification?.options?.[0]?.name ?? 'Selected table'
    if (executive) {
      return (
        <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
          Data table · {label}
        </span>
      )
    }
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
    if (executive) {
      const trust = executiveTrustLine(response)
      if (trust) {
        return (
          <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-medium text-emerald-900">
            {trust}
          </span>
        )
      }
    }
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
