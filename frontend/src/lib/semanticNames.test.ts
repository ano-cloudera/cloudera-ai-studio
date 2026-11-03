import { describe, expect, it } from 'vitest'
import { discardDraftMessage, displayModelName, showKey } from './semanticNames'

describe('semantic names', () => {
  it('turns a key-like name into words and leaves a written name alone', () => {
    expect(displayModelName('fulfillment_delivery')).toBe('Fulfillment Delivery')
    expect(displayModelName('credit-risk-model')).toBe('Credit Risk Model')
    expect(displayModelName('Commercial Sales')).toBe('Commercial Sales')
    expect(displayModelName('Q3 sales_report')).toBe('Q3 sales_report') // has a space: written by a person
    expect(displayModelName('')).toBe('')
  })

  it('shows the key only when it differs from the name', () => {
    expect(showKey({ name: 'Fulfillment Delivery', key: 'fulfillment_delivery' })).toBe(false)
    expect(showKey({ name: 'Sales', key: 'sales_v2' })).toBe(true)
  })
})

describe('discardDraftMessage', () => {
  it('names what is lost when the model was never published', () => {
    const text = discardDraftMessage(1, null, { entities: 3, metrics: 11, dimensions: 32 })
    expect(text).toContain('never been published')
    expect(text).toContain('3 data models, 11 metrics and 32 dimensions')
    expect(text).toContain('stays in the list, but empty')
    expect(discardDraftMessage(1, null, null)).toContain('all its data models, metrics and dimensions')
  })

  it('goes back to the published version otherwise', () => {
    const text = discardDraftMessage(3, { versionNumber: 2 }, { entities: 1, metrics: 1, dimensions: 1 })
    expect(text).toContain('return to published v2')
    expect(text).not.toContain('never been published')
  })
})
