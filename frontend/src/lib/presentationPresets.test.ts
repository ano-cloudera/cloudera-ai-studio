import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PRESENTATION,
  PREVIEW_SAMPLES,
  applyPreset,
  applySensitivity,
  presetOf,
  previewOutcome,
  sensitivityOf,
} from './presentationPresets'

describe('presets', () => {
  it('the shipped configuration is the Demo preset and balanced', () => {
    expect(presetOf(DEFAULT_PRESENTATION)).toBe('demo')
    expect(sensitivityOf(DEFAULT_PRESENTATION)).toBe('balanced')
  })

  it('applies a preset and recognises it again, and says custom after a manual change', () => {
    const analyst = applyPreset(DEFAULT_PRESENTATION, 'analyst')
    expect(analyst).toMatchObject({ audience_mode: 'analyst', panel_auto_open: 'always', chat_details_default_open: true })
    expect(presetOf(analyst)).toBe('analyst')
    expect(presetOf({ ...analyst, tier1_show_narrative: true })).toBe('custom')
    expect(presetOf(applyPreset(analyst, 'demo'))).toBe('demo') // switching back resets what the other preset changed
    expect(presetOf(applyPreset(DEFAULT_PRESENTATION, 'minimal'))).toBe('minimal')
  })

  it('keeps the thresholds when a preset is applied and the sensitivity when the preset changes', () => {
    const often = applySensitivity(DEFAULT_PRESENTATION, 'often')
    expect(sensitivityOf(often)).toBe('often')
    expect(applyPreset(often, 'analyst').tier3_min_rows).toBe(often.tier3_min_rows)
    expect(sensitivityOf({ ...often, tier3_min_rows: 99 })).toBe('custom')
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

  it('follows how soon an answer counts as big (a chart always counts)', () => {
    const rarely = outcomes(applySensitivity(DEFAULT_PRESENTATION, 'rarely'))
    expect(opens(rarely[3])).toBe(false)
    expect(opens(rarely[2])).toBe(true)
    expect(opens(outcomes(applySensitivity(DEFAULT_PRESENTATION, 'often'))[1])).toBe(true)
  })

  it('says whether the table and SQL are shown under the answer', () => {
    expect(outcomes({ ...DEFAULT_PRESENTATION, chat_details_default_open: true })[0]).toContain('shown under it')
    expect(outcomes()[0]).toContain('one click away')
  })
})
