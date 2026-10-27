import type { ChatResponse } from '../types/api'
import { analysisArtifactFromResponse } from './analysisArtifact'
import { responseHasReportEvidence } from './reportDocument'
import { isRagResponse } from './ragReport'
import { getPresentationTierConfig, type PresentationTierConfig } from './presentationTierConfig'

export type PresentationTier = 1 | 2 | 3

const VISUAL_CHART_TYPES = ['bar', 'line', 'area', 'scatter', 'pie'] as const

function hasVisualChart(response: ChatResponse): boolean {
  const spec = response.chart_spec
  if (!spec?.type || !VISUAL_CHART_TYPES.includes(spec.type as (typeof VISUAL_CHART_TYPES)[number])) {
    return false
  }
  return Boolean(spec.x && spec.y && response.data.rows.length > 0)
}

function backendTierOverride(response: ChatResponse): PresentationTier | null {
  const raw = response.presentation_tier
  if (raw === 1 || raw === 2 || raw === 3) return raw
  return null
}

function tierFromPayload(response: ChatResponse, cfg: PresentationTierConfig): PresentationTier {
  if (!cfg.enabled) return 1
  if (isRagResponse(response) || response.status !== 'SUCCESS') return 1

  if (cfg.force_tier3_on_visual_chart && hasVisualChart(response)) return 3

  const rowCount = Math.max(response.data.row_count ?? 0, response.data.rows.length)
  const insightCount = response.answer.insights.length
  const implicationCount = response.answer.business_implications.length

  if (rowCount >= cfg.tier3_min_rows) return 3
  if (insightCount >= cfg.tier3_min_insights || implicationCount >= cfg.tier3_min_implications) return 3

  const artifact = analysisArtifactFromResponse(response)
  if (artifact === 'none') return 1
  if (artifact === 'kpi') return 1

  if (
    rowCount <= cfg.tier1_max_rows &&
    response.data.columns.length <= cfg.tier1_max_columns &&
    insightCount === 0 &&
    implicationCount === 0
  ) {
    return 1
  }

  if (insightCount >= 1 || rowCount > cfg.tier1_max_rows || implicationCount >= 1) return 2
  if (artifact === 'query') return 1

  return 2
}

/**
 * Tier 1 — simple lookup: answer in chat; query/table in collapsed footer.
 * Tier 2 — light analysis in chat; table/query in collapsed footer.
 * Tier 3 — full Analysis Workspace (panel + viz).
 */
export function computePresentationTier(response: ChatResponse): PresentationTier {
  const override = backendTierOverride(response)
  if (override != null) return override
  return tierFromPayload(response, getPresentationTierConfig())
}

export function shouldAutoOpenAnalysisPanel(response: ChatResponse): boolean {
  const cfg = getPresentationTierConfig()
  if (response.status !== 'SUCCESS' || !responseHasReportEvidence(response)) return false
  if (cfg.panel_auto_open === 'never') return false
  if (cfg.panel_auto_open === 'always') return true
  return computePresentationTier(response) === 3
}

export function qualifiesForAnalysisWorkspaceCard(response: ChatResponse): boolean {
  return shouldAutoOpenAnalysisPanel(response)
}

export function shouldShowChatExpand(response: ChatResponse, tier: PresentationTier): boolean {
  const cfg = getPresentationTierConfig()
  if (tier === 1) return cfg.chat_expand_tier1
  if (tier === 2) return cfg.chat_expand_tier2
  return false
}
