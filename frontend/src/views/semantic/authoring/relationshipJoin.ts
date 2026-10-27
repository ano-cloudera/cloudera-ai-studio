/** Parse and build semantic relationship join expressions (entity_key.column). */

export type ParsedRelationshipJoin = {
  from: string[]
  to: string[]
}

const JOIN_PART = /\s*=\s*/

export function parseRelationshipJoinExpression(
  expression: string,
  fromEntity: string,
  toEntity: string,
): ParsedRelationshipJoin {
  const raw = (expression || '').trim()
  if (!raw) {
    return { from: [], to: [] }
  }
  const fromCols: string[] = []
  const toCols: string[] = []
  const parts = raw.split(/\s+AND\s+/i)
  for (const part of parts) {
    const sides = part.split(JOIN_PART)
    if (sides.length !== 2) continue
    const left = sides[0].trim()
    const right = sides[1].trim()
    const leftMatch = matchEntityColumn(left, fromEntity, toEntity)
    const rightMatch = matchEntityColumn(right, fromEntity, toEntity)
    if (leftMatch?.entity === fromEntity && rightMatch?.entity === toEntity) {
      fromCols.push(leftMatch.column)
      toCols.push(rightMatch.column)
    } else if (leftMatch?.entity === toEntity && rightMatch?.entity === fromEntity) {
      fromCols.push(rightMatch.column)
      toCols.push(leftMatch.column)
    }
  }
  return { from: fromCols, to: toCols }
}

function matchEntityColumn(token: string, fromEntity: string, toEntity: string): { entity: string; column: string } | null {
  for (const entity of [fromEntity, toEntity]) {
    const prefix = `${entity}.`
    if (token.startsWith(prefix)) {
      return { entity, column: token.slice(prefix.length).trim() }
    }
  }
  return null
}

export function buildRelationshipJoinExpression(
  fromEntity: string,
  fromColumns: string[],
  toEntity: string,
  toColumns: string[],
): string {
  const from = fromColumns.map(c => c.trim()).filter(Boolean)
  const to = toColumns.map(c => c.trim()).filter(Boolean)
  if (!from.length || !to.length) return ''
  const pairs = Math.min(from.length, to.length)
  const clauses: string[] = []
  for (let i = 0; i < pairs; i += 1) {
    clauses.push(`${fromEntity}.${from[i]} = ${toEntity}.${to[i]}`)
  }
  return clauses.join(' AND ')
}

export function defaultRelationshipDraft(entityKeys: string[]): {
  from_entity_key: string
  to_entity_key: string
  from_key_columns: string[]
  to_key_columns: string[]
  relationship_type: string
} {
  const hasTx = entityKeys.includes('transactions')
  const hasCust = entityKeys.includes('customers')
  const from = hasTx ? 'transactions' : entityKeys[0] ?? ''
  const to = hasCust ? 'customers' : entityKeys.find(k => k !== from) ?? from
  const key = from === 'transactions' && to === 'customers' ? 'customer_id' : 'id'
  return {
    from_entity_key: from,
    to_entity_key: to,
    from_key_columns: [key],
    to_key_columns: [key],
    relationship_type: 'many_to_one',
  }
}
