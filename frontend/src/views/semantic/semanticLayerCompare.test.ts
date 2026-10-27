import { describe, expect, it } from 'vitest'

import { buildVersionCompare } from './semanticLayerCompare'

describe('semanticLayerCompare', () => {
  it('reports added and changed metrics between draft and active', () => {
    const sections = buildVersionCompare({
      draftEntities: [],
      activeEntities: [],
      draftMetrics: [{ key: 'sales', name: 'Sales', expression: 'SUM(a)' }],
      activeMetrics: [{ key: 'sales', name: 'Sales', expression: 'SUM(b)' }],
      draftDimensions: [],
      activeDimensions: [],
      draftRelationships: [],
      activeRelationships: [],
      draftTerms: [{ key: 't1', term: 'Revenue' }],
      activeTerms: [],
    })
    const metrics = sections.find(s => s.label === 'Metrics')
    expect(metrics?.changed.length).toBe(1)
    const glossary = sections.find(s => s.label === 'Glossary')
    expect(glossary?.added.length).toBe(1)
  })
})
