import type {
  SemanticDimensionRecord,
  SemanticEntityRecord,
  SemanticMetricRecord,
  SemanticRelationshipRecord,
} from '../../../types/api'
import { dimensionsForMetric, physicalColumnsFromEntity } from './metricAuthoring'

export type MetricFieldIssue = { field: string; message: string }

const SIMPLE_AGG_RE = /^(SUM|COUNT|AVG|MIN|MAX)\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)$/i
const COUNT_DISTINCT_RE = /^COUNT\s*\(\s*DISTINCT\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\)$/i

function isNumericType(dataType: string | null | undefined): boolean {
  const t = (dataType ?? '').toLowerCase()
  return /int|decimal|numeric|float|double|number|real/.test(t)
}

function columnsForEntity(entityKey: string, dimensions: SemanticDimensionRecord[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const d of dimensions) {
    if (d.source_entity_key === entityKey) m.set(d.source_column, d.data_type ?? 'string')
  }
  return m
}

export function validateMetricDraftLocal(
  form: Pick<
    SemanticMetricRecord,
    'name' | 'business_definition' | 'expression' | 'aggregation' | 'source_entity_key' | 'allowed_dimension_keys'
  > & {
    id?: string
    calcType?: string
  },
  entityKeys: string[],
  dimensions: SemanticDimensionRecord[],
  relationships: SemanticRelationshipRecord[],
  existingMetrics: SemanticMetricRecord[],
  entitiesByKey: Record<string, SemanticEntityRecord> = {},
): MetricFieldIssue[] {
  const issues: MetricFieldIssue[] = []
  if (!form.name.trim()) issues.push({ field: 'name', message: 'Metric name is required.' })
  if (!(form.business_definition ?? '').trim()) issues.push({ field: 'business_definition', message: 'Business definition is required.' })
  if (!form.source_entity_key || !entityKeys.includes(form.source_entity_key)) {
    issues.push({ field: 'source_entity_key', message: 'Select a valid data model.' })
  }
  const dup = existingMetrics.find(
    m => m.name.trim().toLowerCase() === form.name.trim().toLowerCase() && m.id !== form.id,
  )
  if (dup) issues.push({ field: 'name', message: `A metric named \`${form.name}\` already exists.` })

  const expr = form.expression.trim()
  if (!expr) {
    issues.push({ field: 'expression', message: 'Calculation expression is required.' })
    return issues
  }

  const cols = columnsForEntity(form.source_entity_key, dimensions)
  for (const col of physicalColumnsFromEntity(entitiesByKey[form.source_entity_key])) {
    if (!cols.has(col.name)) {
      cols.set(col.name, col.normalized_type ?? 'string')
    }
  }
  const cd = expr.match(COUNT_DISTINCT_RE)
  if (cd) {
    const col = cd[1]
    if (!cols.has(col)) issues.push({ field: 'expression', message: `Column \`${col}\` was not found in ${form.source_entity_key}.` })
    return issues
  }
  const sm = expr.match(SIMPLE_AGG_RE)
  if (sm && form.calcType !== 'formula') {
    const fn = sm[1].toLowerCase()
    const col = sm[2]
    if (!cols.has(col)) issues.push({ field: 'expression', message: `Column \`${col}\` was not found in ${form.source_entity_key}.` })
    else if (['sum', 'avg', 'min', 'max'].includes(fn) && !isNumericType(cols.get(col))) {
      issues.push({ field: 'expression', message: `\`${col}\` cannot be used with ${fn.toUpperCase()}.` })
    }
  } else if (/\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE)\b/i.test(expr)) {
    issues.push({ field: 'expression', message: 'Formula contains disallowed SQL statements.' })
  }

  const allowed = form.allowed_dimension_keys ?? []
  if (allowed.length && form.source_entity_key) {
    const avail = new Set(
      dimensionsForMetric(form.source_entity_key, dimensions, relationships).map(d => d.key),
    )
    for (const key of allowed) {
      if (!avail.has(key)) {
        issues.push({
          field: 'allowed_dimension_keys',
          message: `Dimension \`${key}\` is not available for this metric's data model.`,
        })
      }
    }
  }
  return issues
}
