import type { ChartMetric } from '../components/AnswerChart'
import type { ChatResponse } from '../types/api'

/** The plotted metric of an answer: its label from the result's column labels, unit, definition and which way is good. */
export function chartMetric(response: ChatResponse): ChartMetric {
  const data = response.data
  return {
    label: data.column_labels?.metric_value ?? data.governed_metric_display_name ?? null,
    unitFormat: data.unit_format ?? null,
    description: data.metric_description ?? null,
    better: data.metric_better ?? null,
  }
}
