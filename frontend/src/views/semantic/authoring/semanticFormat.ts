import type { ConnectorRecord, SemanticEntityRecord } from '../../../types/api'
import { connectorTypeLabel } from '../../connectors/connectorUi'

export function formatSemanticModified(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return '—'
  }
}

/** Compact timestamp for dense overview tables. */
export function formatSemanticModifiedCompact(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return '—'
  }
}

export function physicalSource(entity: SemanticEntityRecord): string {
  const parts = [entity.catalog, entity.schema, entity.table_name || entity.view_name].filter(Boolean)
  return parts.join('.') || '—'
}

export function entityConnectorLabel(entity: SemanticEntityRecord, connectors: ConnectorRecord[]): string {
  if (!entity.connection_id) return entity.source_type
  const conn = connectors.find(c => c.id === entity.connection_id)
  return conn ? `${connectorTypeLabel(conn.connector_type)} · ${conn.name}` : 'Data source'
}

export function semanticKeyFromName(name: string): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
  return (base || 'object').slice(0, 96)
}

export function entityFieldCount(entity: SemanticEntityRecord): string {
  const meta = entity.metadata ?? {}
  const n = meta.field_count ?? meta.column_count ?? meta.columns_discovered
  return n != null ? String(n) : '—'
}
