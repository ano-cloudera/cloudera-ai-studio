export type PanelAutoOpenMode = 'heuristic' | 'always' | 'never'

export type AudienceMode = 'executive' | 'analyst'

export type PresentationTierConfig = {
  enabled: boolean
  audience_mode: AudienceMode
  panel_auto_open: PanelAutoOpenMode
  tier3_min_rows: number
  tier3_min_insights: number
  tier3_min_implications: number
  rank_tier3_above_n: number
  rank_min_tier: 1 | 2 | 3
  tier1_max_rows: number
  tier1_max_columns: number
  force_tier3_on_pareto: boolean
  force_tier3_on_operational_analysis: boolean
  force_tier3_on_visual_chart: boolean
  chat_expand_tier1: boolean
  chat_expand_tier2: boolean
  chat_details_default_open: boolean
  tier1_show_narrative: boolean
}

function envBool(key: string, fallback: boolean): boolean {
  const value = process.env[key]?.trim().toLowerCase()
  if (value === 'true' || value === '1') return true
  if (value === 'false' || value === '0') return false
  return fallback
}

function envInt(key: string, fallback: number): number {
  const raw = process.env[key]?.trim()
  if (!raw) return fallback
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) ? n : fallback
}

function envPanelMode(key: string, fallback: PanelAutoOpenMode): PanelAutoOpenMode {
  const value = process.env[key]?.trim().toLowerCase()
  if (value === 'always' || value === 'never' || value === 'heuristic') return value
  return fallback
}

/** Build-time defaults (AMP deployment / NEXT_PUBLIC_*). Backend API overrides at runtime. */
export function presentationTierConfigFromEnv(): PresentationTierConfig {
  const audienceRaw = process.env.NEXT_PUBLIC_ASK_DATA_AUDIENCE_MODE?.trim().toLowerCase()
  const audience_mode: AudienceMode = audienceRaw === 'analyst' ? 'analyst' : 'executive'

  return {
    enabled: envBool('NEXT_PUBLIC_ASK_DATA_PRESENTATION_TIER_ENABLED', true),
    audience_mode,
    panel_auto_open: envPanelMode('NEXT_PUBLIC_ASK_DATA_PANEL_AUTO_OPEN', 'heuristic'),
    tier3_min_rows: envInt('NEXT_PUBLIC_ASK_DATA_TIER3_MIN_ROWS', 13),
    tier3_min_insights: envInt('NEXT_PUBLIC_ASK_DATA_TIER3_MIN_INSIGHTS', 3),
    tier3_min_implications: envInt('NEXT_PUBLIC_ASK_DATA_TIER3_MIN_IMPLICATIONS', 2),
    rank_tier3_above_n: envInt('NEXT_PUBLIC_ASK_DATA_RANK_TIER3_ABOVE_N', 5),
    rank_min_tier: Math.min(3, Math.max(1, envInt('NEXT_PUBLIC_ASK_DATA_RANK_MIN_TIER', 2))) as 1 | 2 | 3,
    tier1_max_rows: envInt('NEXT_PUBLIC_ASK_DATA_TIER1_MAX_ROWS', 1),
    tier1_max_columns: envInt('NEXT_PUBLIC_ASK_DATA_TIER1_MAX_COLUMNS', 2),
    force_tier3_on_pareto: envBool('NEXT_PUBLIC_ASK_DATA_FORCE_TIER3_PARETO', true),
    force_tier3_on_operational_analysis: envBool('NEXT_PUBLIC_ASK_DATA_FORCE_TIER3_OPERATIONAL', true),
    force_tier3_on_visual_chart: envBool('NEXT_PUBLIC_ASK_DATA_FORCE_TIER3_CHART', true),
    chat_expand_tier1: envBool('NEXT_PUBLIC_ASK_DATA_CHAT_EXPAND_TIER1', true),
    chat_expand_tier2: envBool('NEXT_PUBLIC_ASK_DATA_CHAT_EXPAND_TIER2', true),
    chat_details_default_open: envBool('NEXT_PUBLIC_ASK_DATA_CHAT_DETAILS_DEFAULT_OPEN', false),
    tier1_show_narrative: envBool('NEXT_PUBLIC_ASK_DATA_TIER1_SHOW_NARRATIVE', false),
  }
}

export function tier1ShowNarrativeEnabled(): boolean {
  return getPresentationTierConfig().tier1_show_narrative
}

let runtimePresentationConfig: PresentationTierConfig = presentationTierConfigFromEnv()

export function getPresentationTierConfig(): PresentationTierConfig {
  return runtimePresentationConfig
}

export function setPresentationTierConfig(next: PresentationTierConfig): void {
  runtimePresentationConfig = next
}

export function mergePresentationTierConfig(partial: Partial<PresentationTierConfig>): void {
  runtimePresentationConfig = { ...runtimePresentationConfig, ...partial }
}
