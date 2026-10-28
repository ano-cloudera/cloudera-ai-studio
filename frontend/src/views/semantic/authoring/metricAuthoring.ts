import type {
  SemanticDimensionRecord,
  SemanticEntityRecord,
  SemanticRelationshipRecord,
} from '../../../types/api'

export type PhysicalColumnMeta = { name: string; normalized_type?: string | null }

function normalizedTypeBase(dataType: string | null | undefined): string {
  return (dataType ?? '').toUpperCase().split('(')[0].trim()
}

function isNumericColumnType(dataType: string | null | undefined): boolean {
  const t = normalizedTypeBase(dataType)
  return /DECIMAL|FLOAT|DOUBLE|NUMBER|NUMERIC|INT|INTEGER|BIGINT|SMALLINT|REAL/.test(t)
}

/** Dimension-style columns (breakdown), not simple measure fields. */
function isStringLikeColumnType(dataType: string | null | undefined): boolean {
  const t = normalizedTypeBase(dataType)
  return /STRING|TEXT|VARCHAR|CHAR|BOOLEAN|BOOL|DATE|TIMESTAMP|DATETIME|TIME/.test(t)
}

export function physicalColumnsFromEntity(entity: SemanticEntityRecord | undefined): PhysicalColumnMeta[] {
  if (!entity?.metadata) return []
  const raw = entity.metadata.physical_columns
  if (!Array.isArray(raw)) return []
  const out: PhysicalColumnMeta[] = []
  for (const row of raw) {
    if (!row || typeof row !== 'object') continue
    const name = String((row as { name?: string }).name ?? '').trim()
    if (!name) continue
    out.push({
      name,
      normalized_type: (row as { normalized_type?: string }).normalized_type ?? null,
    })
  }
  return out
}

/** Columns usable as a simple aggregate measure (includes numeric fields not imported as dimensions). */
export function measureColumnOptions(
  entityKey: string,
  dimensionsByEntity: Record<string, SemanticDimensionRecord[]>,
  entitiesByKey: Record<string, SemanticEntityRecord>,
  calcType: string,
): string[] {
  const fromDims = (dimensionsByEntity[entityKey] ?? []).map(d => d.source_column).filter(Boolean)
  const pk = entitiesByKey[entityKey]?.primary_key?.trim()
  const physical = physicalColumnsFromEntity(entitiesByKey[entityKey]).map(c => c.name)
  const merged = Array.from(new Set([...fromDims, ...physical, ...(pk ? [pk] : [])]))

  const typeByCol = new Map<string, string>()
  for (const d of dimensionsByEntity[entityKey] ?? []) {
    if (d.source_column) typeByCol.set(d.source_column, d.data_type ?? 'string')
  }
  for (const col of physicalColumnsFromEntity(entitiesByKey[entityKey])) {
    typeByCol.set(col.name, col.normalized_type ?? 'string')
  }

  const numericAgg = calcType === 'sum' || calcType === 'avg' || calcType === 'min' || calcType === 'max'
  return merged
    .filter(col => {
      const t = typeByCol.get(col)
      if (numericAgg) return isNumericColumnType(t)
      // Count / count distinct: prefer IDs & numeric measures, not categorical strings.
      if (isStringLikeColumnType(t)) return false
      return isNumericColumnType(t) || col === pk
    })
    .sort((a, b) => a.localeCompare(b))
}

const SIMPLE_AGG_RE = /^(SUM|COUNT|AVG|MIN|MAX)\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)$/i
const COUNT_DISTINCT_RE = /^COUNT\s*\(\s*DISTINCT\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\)$/i

export function parseColumnFromExpression(expression: string): string {
  const expr = expression.trim()
  const cd = expr.match(COUNT_DISTINCT_RE)
  if (cd) return cd[1]
  const sm = expr.match(SIMPLE_AGG_RE)
  if (sm) return sm[2]
  return ''
}

export function relatedEntityKeys(entityKey: string, relationships: SemanticRelationshipRecord[]): Set<string> {
  const keys = new Set<string>([entityKey])
  for (const rel of relationships) {
    if (rel.from_entity_key === entityKey) keys.add(rel.to_entity_key)
    if (rel.to_entity_key === entityKey) keys.add(rel.from_entity_key)
  }
  return keys
}

export function dimensionsForMetric(
  entityKey: string,
  dimensions: SemanticDimensionRecord[],
  relationships: SemanticRelationshipRecord[],
): SemanticDimensionRecord[] {
  const related = relatedEntityKeys(entityKey, relationships)
  return dimensions
    .filter(d => related.has(d.source_entity_key))
    .sort((a, b) => a.name.localeCompare(b.name) || a.key.localeCompare(b.key))
}

/** Metrics with an explicit allowed-dimension subset (not publish defaults). */
export function countMetricsWithExplicitBreakdown(
  metrics: Array<{ allowed_dimension_keys?: string[] }>,
): number {
  return metrics.filter(m => (m.allowed_dimension_keys?.length ?? 0) > 0).length
}

export function formatMetricDimensionsCell(
  metric: { source_entity_key: string; allowed_dimension_keys?: string[] },
  dimensions: SemanticDimensionRecord[],
  relationships: SemanticRelationshipRecord[],
): string {
  const selected = metric.allowed_dimension_keys ?? []
  if (selected.length) {
    return selected.slice(0, 4).join(', ') + (selected.length > 4 ? ` +${selected.length - 4}` : '')
  }
  const avail = dimensionsForMetric(metric.source_entity_key, dimensions, relationships)
  if (!avail.length) return '—'
  return `All on model (${avail.length})`
}
