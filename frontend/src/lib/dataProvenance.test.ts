import { describe, expect, it } from 'vitest'

import { parseDataProvenance } from './dataProvenance'

describe('dataProvenance', () => {
  it('extracts table sources from a bare view name', () => {
    expect(parseDataProvenance('gold.rpt_sap_monthly_executive_semantic')).toEqual({
      note: null,
      sources: ['gold.rpt_sap_monthly_executive_semantic'],
    })
  })

  it('ignores internal clarification references', () => {
    expect(parseDataProvenance('clarification_required')).toBeNull()
  })

  it('ignores sql suffix and keeps prose as note', () => {
    const parsed = parseDataProvenance(
      'Material-level only. Query: SELECT * FROM gold.rpt_sap_sales_office_material_month_semantic',
    )
    expect(parsed?.sources).toContain('gold.rpt_sap_sales_office_material_month_semantic')
    expect(parsed?.note).toMatch(/Material-level/i)
  })
})


describe('bare table references', () => {
  it('treats a connector table identifier as a source, not as a note', () => {
    expect(parseDataProvenance('default.credit_applications')).toEqual({
      note: null,
      sources: ['default.credit_applications'],
    })
  })

  it('handles quoted three-part names', () => {
    expect(parseDataProvenance('"hive"."default"."credit_applications"')?.sources).toEqual([
      'hive.default.credit_applications',
    ])
  })

  it('does not mistake a sentence for a table', () => {
    expect(parseDataProvenance('Computed from the governed metric.')?.sources).toEqual([])
  })
})
