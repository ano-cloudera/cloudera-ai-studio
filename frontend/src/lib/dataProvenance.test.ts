import { describe, expect, it } from 'vitest'

import { parseDataProvenance } from './dataProvenance'

describe('dataProvenance', () => {
  it('extracts table sources from a bare view name', () => {
    expect(parseDataProvenance('gold.rpt_sap_monthly_executive_semantic')).toEqual({
      note: null,
      sources: ['gold.rpt_sap_monthly_executive_semantic'],
    })
  })

  it('ignores sql suffix and keeps prose as note', () => {
    const parsed = parseDataProvenance(
      'Material-level only. Query: SELECT * FROM gold.rpt_sap_sales_office_material_month_semantic',
    )
    expect(parsed?.sources).toContain('gold.rpt_sap_sales_office_material_month_semantic')
    expect(parsed?.note).toMatch(/Material-level/i)
  })
})
