import { describe, expect, it } from 'vitest'

import { mergeDataNotes, parseDataProvenance } from './dataProvenance'

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

describe('mcp references', () => {
  it('does not show a raw connector id as a data note', () => {
    expect(parseDataProvenance('mcp:c5c0bb14-273c-48de-be41-ad815637cfda')).toBeNull()
  })
})

describe('mergeDataNotes scope', () => {
  it('uses the plan-based sentence only when the model wrote no note', () => {
    const scope = 'Covers 2026-03-01 to 2026-03-31 in fulfillment_orders, with no breakdown or filter applied.'
    expect(mergeDataNotes([], null, { scope })).toBe(scope)
    expect(mergeDataNotes(['Data reflects March only.'], null, { scope })).toBe('Data reflects March only.')
    expect(mergeDataNotes([], null, {})).toBeNull()
  })
})
