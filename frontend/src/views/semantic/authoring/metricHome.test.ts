import { describe, expect, it } from 'vitest'
import { withHomeFields } from './SemanticOtherTabs'

describe('the Home fields of a metric', () => {
  it('are written into the reference extension and keep everything else in the metadata', () => {
    const metadata = { ossie_metric: 'late', reference_extension: { base_dataset: 'shipments', headline: 3 } }
    const next = withHomeFields(metadata, { homeOrder: 1, better: 'down', target: '15' })
    expect(next).toEqual({ ossie_metric: 'late', reference_extension: { base_dataset: 'shipments', headline: 1, better: 'down', target: 15 } })
  })

  it('are removed when the metric is no longer shown or the target is cleared', () => {
    const metadata = { reference_extension: { headline: 2, better: 'up', target: 100 } }
    expect(withHomeFields(metadata, { homeOrder: 0, better: '', target: '' })).toEqual({})
    expect(withHomeFields(metadata, { homeOrder: 2, better: 'up', target: 'abc' })).toEqual({ reference_extension: { headline: 2, better: 'up' } })
  })
})
