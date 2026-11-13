import type { ChatResponse } from '../types/api'
import { computePresentationTierFor, shouldAutoOpenPanelFor, type PresentationTier } from './presentationTier'
import type { PresentationTierConfig } from './presentationTierConfig'

/** What the product ships with: executive wording, the panel opens for bigger answers only. */
export const DEFAULT_PRESENTATION: PresentationTierConfig = {
  enabled: true,
  audience_mode: 'executive',
  panel_auto_open: 'heuristic',
  tier3_min_rows: 13,
  tier3_min_insights: 3,
  tier3_min_implications: 2,
  rank_tier3_above_n: 5,
  rank_min_tier: 2,
  tier1_max_rows: 1,
  tier1_max_columns: 2,
  force_tier3_on_pareto: true,
  force_tier3_on_operational_analysis: true,
  force_tier3_on_visual_chart: true,
  chat_expand_tier1: true,
  chat_expand_tier2: true,
  chat_details_default_open: false,
  tier1_show_narrative: false,
}

export type PresetId = 'demo' | 'analyst' | 'minimal'

export const PRESETS: { id: PresetId; title: string; description: string; values: Partial<PresentationTierConfig> }[] = [
  {
    id: 'demo',
    title: 'Demo',
    description: 'Short answers for executives. The full analysis panel opens only for bigger results.',
    values: {},
  },
  {
    id: 'analyst',
    title: 'Analyst workbench',
    description: 'The analysis panel always opens, and the table and SQL are shown under each answer.',
    values: { audience_mode: 'analyst', panel_auto_open: 'always', chat_details_default_open: true },
  },
  {
    id: 'minimal',
    title: 'Minimal chat',
    description: 'Just the answer in the chat. The panel never opens by itself.',
    values: { panel_auto_open: 'never' },
  },
]

const PRESET_KEYS: (keyof PresentationTierConfig)[] = ['audience_mode', 'panel_auto_open', 'chat_details_default_open', 'tier1_show_narrative']

export function applyPreset(current: PresentationTierConfig, id: PresetId): PresentationTierConfig {
  const preset = PRESETS.find(item => item.id === id)!
  return { ...current, ...DEFAULT_PRESENTATION_PRESET_FIELDS(), ...preset.values }
}

function DEFAULT_PRESENTATION_PRESET_FIELDS(): Partial<PresentationTierConfig> {
  return Object.fromEntries(PRESET_KEYS.map(key => [key, DEFAULT_PRESENTATION[key]])) as Partial<PresentationTierConfig>
}

export function presetOf(cfg: PresentationTierConfig): PresetId | 'custom' {
  for (const preset of PRESETS) {
    const expected = { ...DEFAULT_PRESENTATION, ...preset.values }
    if (PRESET_KEYS.every(key => cfg[key] === expected[key])) return preset.id
  }
  return 'custom'
}

// ---- the preview: three typical answers shown under the current settings --------------------------------------------

function sample(rows: number, columns: string[], insights: number, chart: 'kpi' | 'bar' | null): ChatResponse {
  const data = Array.from({ length: rows }, (_, index) => Object.fromEntries(columns.map(column => [column, column === 'metric_value' ? index + 1 : `Group ${index + 1}`])))
  const chartSpec = chart === 'kpi' ? { type: 'kpi', title: 'x', y: 'metric_value' } : chart === 'bar' ? { type: 'bar', title: 'x', x: columns[0], y: 'metric_value' } : null
  return {
    request_id: 'preview',
    status: 'SUCCESS',
    strategy: 'governed',
    answer: { direct_answer: 'x', executive_summary: 'x', insights: Array.from({ length: insights }, () => 'x'), business_implications: [], caveats: [], data_reference: 'x', chart_spec: null },
    chart_spec: chartSpec,
    data: { columns, rows: data, row_count: rows, execution_ms: 5 },
  } as unknown as ChatResponse
}

export const PREVIEW_SAMPLES: { title: string; response: ChatResponse }[] = [
  { title: 'A single number ("How many orders?")', response: sample(1, ['metric_value'], 0, 'kpi') },
  { title: 'A short table (8 rows)', response: sample(8, ['region_name', 'metric_value'], 1, null) },
  { title: 'An answer with a chart', response: sample(5, ['region_name', 'metric_value'], 1, 'bar') },
  { title: 'A large table (20 rows)', response: sample(20, ['region_name', 'metric_value'], 3, null) },
]

const TIER_TEXT: Record<PresentationTier, string> = {
  1: 'the answer only',
  2: 'the answer with its highlights',
  3: 'the answer with its highlights',
}

export function previewOutcome(response: ChatResponse, cfg: PresentationTierConfig): string {
  const tier = computePresentationTierFor(response, cfg)
  if (shouldAutoOpenPanelFor(response, cfg)) return 'The full analysis panel (chart, table, SQL) opens next to the chat.'
  const details = cfg.chat_details_default_open ? 'the table and SQL are shown under it' : 'the table and SQL are one click away'
  return `In the chat: ${TIER_TEXT[tier]}; ${details}.`
}
