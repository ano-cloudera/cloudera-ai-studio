import type { ChatResponse } from '../types/api'
import { isRagResponse } from './ragReport'

export type AnalysisArtifactType = 'none' | 'table' | 'chart' | 'query' | 'kpi'

export function analysisArtifactFromResponse(response: ChatResponse): AnalysisArtifactType {
  if (isRagResponse(response)) return 'none'
  if (response.status !== 'SUCCESS') return 'none'

  if (response.chart_spec?.type === 'kpi') return 'kpi'
  const visual = ['bar', 'line', 'area', 'scatter', 'pie']
  if (
    response.chart_spec?.type &&
    visual.includes(response.chart_spec.type) &&
    response.chart_spec.x &&
    response.chart_spec.y &&
    response.data.rows.length > 0
  ) {
    return 'chart'
  }
  if (response.data.rows.length > 0) return 'table'
  if (
    (response.strategy === 'governed' || response.strategy === 'sql_fallback') &&
    response.data.execution_ms > 0
  ) {
    return 'query'
  }
  return 'none'
}

export function shouldOpenAnalysisPanel(response: ChatResponse): boolean {
  return analysisArtifactFromResponse(response) !== 'none'
}
