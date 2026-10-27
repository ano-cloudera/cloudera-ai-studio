import { describe, expect, it } from 'vitest'

import {
  detailedStepToSummaryPhase,
  governanceDisplayLabel,
  mergeProgressStep,
  stageToStepIndex,
} from './streamProgress'

describe('streamProgress', () => {
  it('maps backend stages to user-facing steps', () => {
    expect(stageToStepIndex('understand', 'Memahami pertanyaan')).toBe(0)
    expect(stageToStepIndex('plan', 'Merencanakan kueri terkelola')).toBe(1)
    expect(stageToStepIndex('validate', 'Memvalidasi query governed')).toBe(2)
    expect(stageToStepIndex('query', 'Menjalankan kueri ke Impala')).toBe(3)
    expect(stageToStepIndex('analyze', 'Menyusun jawaban')).toBe(4)
  })

  it('maps detailed steps to summary phases', () => {
    expect(detailedStepToSummaryPhase(0)).toBe(0)
    expect(detailedStepToSummaryPhase(1)).toBe(1)
    expect(detailedStepToSummaryPhase(3)).toBe(1)
    expect(detailedStepToSummaryPhase(4)).toBe(2)
  })

  it('never decreases the active step index', () => {
    expect(mergeProgressStep(3, 'plan', 'Merencanakan')).toBe(3)
    expect(mergeProgressStep(1, 'query', 'Menjalankan')).toBe(3)
  })

  it('hides tempo-agent-v3 from governance chip', () => {
    expect(governanceDisplayLabel([], 'Governed · tempo-agent-v3 + Impala')).toBe('Governed · Impala')
    expect(governanceDisplayLabel([], undefined)).toBe('Governed · Impala')
  })
})
