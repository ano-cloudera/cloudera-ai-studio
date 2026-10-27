type Keyed = {
  key: string
  name?: string
  term?: string
  expression?: string
  source_column?: string
  join_expression?: string
  definition?: string | null
}

export type SemanticDiffSection = {
  label: string
  added: string[]
  removed: string[]
  changed: string[]
}

function label(row: Keyed): string {
  return row.name || row.term || row.key
}

export function compareKeyedLists<T extends Keyed>(left: T[], right: T[], fields: (keyof T)[]): SemanticDiffSection {
  const leftMap = new Map(left.map(r => [r.key, r]))
  const rightMap = new Map(right.map(r => [r.key, r]))
  const added: string[] = []
  const removed: string[] = []
  const changed: string[] = []

  for (const [key, row] of leftMap) {
    if (!rightMap.has(key)) added.push(`${label(row)} (${key})`)
  }
  for (const [key, row] of rightMap) {
    if (!leftMap.has(key)) removed.push(`${label(row)} (${key})`)
  }
  for (const [key, l] of leftMap) {
    const r = rightMap.get(key)
    if (!r) continue
    const diffs = fields.filter(f => String(l[f] ?? '') !== String(r[f] ?? ''))
    if (diffs.length) changed.push(`${label(l)} (${key}): ${diffs.join(', ')}`)
  }

  return { label: '', added, removed, changed }
}

export function buildVersionCompare(params: {
  draftEntities: Keyed[]
  activeEntities: Keyed[]
  draftMetrics: Keyed[]
  activeMetrics: Keyed[]
  draftDimensions: Keyed[]
  activeDimensions: Keyed[]
  draftRelationships: Keyed[]
  activeRelationships: Keyed[]
  draftTerms: Keyed[]
  activeTerms: Keyed[]
}): SemanticDiffSection[] {
  return [
    { ...compareKeyedLists(params.draftEntities, params.activeEntities, ['name']), label: 'Entities' },
    { ...compareKeyedLists(params.draftMetrics, params.activeMetrics, ['name', 'expression']), label: 'Metrics' },
    { ...compareKeyedLists(params.draftDimensions, params.activeDimensions, ['name', 'source_column']), label: 'Dimensions' },
    {
      ...compareKeyedLists(params.draftRelationships, params.activeRelationships, ['join_expression']),
      label: 'Relationships',
    },
    { ...compareKeyedLists(params.draftTerms, params.activeTerms, ['term', 'definition']), label: 'Glossary' },
  ]
}
