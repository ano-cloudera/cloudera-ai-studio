import { describe, expect, it } from 'vitest'

import { compactSingleRowEvidence } from './singleRowPresentation'

describe('compactSingleRowEvidence', () => {
  it('compact material + metric_value', () => {
    const out = compactSingleRowEvidence(['material', 'metric_value'], [{ material: '802-25-42', metric_value: 2614.4 }])
    expect(out?.metricColumn).toBe('metric_value')
    expect(out?.dimensions).toHaveLength(1)
  })

  it('skips wide single rows', () => {
    const cols = ['a', 'b', 'c', 'd', 'e']
    expect(compactSingleRowEvidence(cols, [Object.fromEntries(cols.map(c => [c, 1]))])).toBeNull()
  })
})
