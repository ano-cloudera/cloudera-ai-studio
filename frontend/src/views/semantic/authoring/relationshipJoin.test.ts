import { describe, expect, it } from 'vitest'
import {
  buildRelationshipJoinExpression,
  defaultRelationshipDraft,
  parseRelationshipJoinExpression,
} from './relationshipJoin'

describe('relationshipJoin', () => {
  it('builds single-column join', () => {
    expect(
      buildRelationshipJoinExpression('transactions', ['customer_id'], 'customers', ['customer_id']),
    ).toBe('transactions.customer_id = customers.customer_id')
  })

  it('builds composite join', () => {
    expect(
      buildRelationshipJoinExpression('a', ['k1', 'k2'], 'b', ['k1', 'k2']),
    ).toBe('a.k1 = b.k1 AND a.k2 = b.k2')
  })

  it('parses join back into columns', () => {
    const parsed = parseRelationshipJoinExpression(
      'transactions.customer_id = customers.customer_id',
      'transactions',
      'customers',
    )
    expect(parsed.from).toEqual(['customer_id'])
    expect(parsed.to).toEqual(['customer_id'])
  })

  it('defaults banking entities to customer_id', () => {
    const d = defaultRelationshipDraft(['customers', 'transactions'])
    expect(d.from_entity_key).toBe('transactions')
    expect(d.to_entity_key).toBe('customers')
    expect(d.from_key_columns).toEqual(['customer_id'])
  })
})
