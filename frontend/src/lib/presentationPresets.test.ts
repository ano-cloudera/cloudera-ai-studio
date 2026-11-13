import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PRESENTATION,
  PREVIEW_SAMPLES,
  applyPreset,
  presetOf,
  previewOutcome,
} from './presentationPresets'

describe('presets', () => {
  it('the shipped configuration is the Demo preset', () => {
    expect(presetOf(DEFAULT_PRESENTATION)).toBe('demo')
  })

  it('applies a preset and recognises it again, and says custom after a manual change', () => {
    const analyst = applyPreset(DEFAULT_PRESENTATION, 'analyst')
    expect(analyst).toMatchObject({ audience_mode: 'analyst', panel_auto_open: 'always', chat_details_default_open: true })
    expect(presetOf(analyst)).toBe('analyst')
    expect(presetOf({ ...analyst, tier1_show_narrative: true })).toBe('custom')
    expect(presetOf(applyPreset(analyst, 'demo'))).toBe('demo') // switching back resets what the other preset changed
    expect(presetOf(applyPreset(DEFAULT_PRESENTATION, 'minimal'))).toBe('minimal')
  })

  it('keeps the thresholds when a preset is applied, so a deployment that tuned them is not undone', () => {
    const tuned = { ...DEFAULT_PRESENTATION, tier3_min_rows: 99 }
    expect(applyPreset(tuned, 'analyst').tier3_min_rows).toBe(99)
  })
})

describe('preview', () => {
  const outcomes = (cfg = DEFAULT_PRESENTATION) => PREVIEW_SAMPLES.map(item => previewOutcome(item.response, cfg))
  const opens = (text: string) => text.includes('analysis panel')

  it('shows the default behaviour: a chart or a large table opens the panel, the rest stays in the chat', () => {
    const [single, shortTable, chart, largeTable] = outcomes()
    expect(single).toContain('the answer only')
    expect(shortTable).toContain('highlights')
    expect(opens(chart)).toBe(true)
    expect(opens(largeTable)).toBe(true)
  })

  it('follows the panel setting', () => {
    expect(outcomes(applyPreset(DEFAULT_PRESENTATION, 'analyst')).every(opens)).toBe(true)
    expect(outcomes(applyPreset(DEFAULT_PRESENTATION, 'minimal')).some(opens)).toBe(false)
  })

  it('follows the size thresholds a deployment sets (a chart always counts)', () => {
    const rarely = outcomes({ ...DEFAULT_PRESENTATION, tier3_min_rows: 30, rank_tier3_above_n: 10, tier3_min_insights: 5, tier3_min_implications: 3 })
    expect(opens(rarely[3])).toBe(false)
    expect(opens(rarely[2])).toBe(true)
    expect(opens(outcomes({ ...DEFAULT_PRESENTATION, tier3_min_insights: 2, tier3_min_implications: 1, tier3_min_rows: 6 })[1])).toBe(true)
  })

  it('says whether the table and SQL are shown under the answer', () => {
    expect(outcomes({ ...DEFAULT_PRESENTATION, chat_details_default_open: true })[0]).toContain('shown under it')
    expect(outcomes()[0]).toContain('one click away')
  })
})
