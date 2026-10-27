import type { ConnectorRecord, ConnectorType } from '../../types/api'

export type ConnectorDisplayStatus = 'connected' | 'failed' | 'not_tested' | 'disabled'

export function connectorTypeLabel(type: ConnectorType | string): string {
  if (type === 'impala') return 'Impala'
  if (type === 'trino') return 'Trino'
  if (type === 'postgres') return 'PostgreSQL'
  return type
}

export function slugConnectorKey(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64) || 'connector'
}

export function displayStatus(connector: ConnectorRecord): ConnectorDisplayStatus {
  if (!connector.enabled) return 'disabled'
  if (connector.last_test_status === 'SUCCESS') return 'connected'
  if (connector.last_test_status === 'FAILED') return 'failed'
  return 'not_tested'
}

export function statusLabel(status: ConnectorDisplayStatus): string {
  if (status === 'connected') return 'Connected'
  if (status === 'failed') return 'Failed'
  if (status === 'disabled') return 'Disabled'
  return 'Not Tested'
}

export function statusDotClass(status: ConnectorDisplayStatus): string {
  if (status === 'connected') return 'bg-emerald-500'
  if (status === 'failed') return 'bg-red-500'
  if (status === 'disabled') return 'bg-slate-300'
  return 'bg-slate-400'
}

export function maskHost(host: string): string {
  const trimmed = host.trim()
  if (trimmed.length <= 8) return trimmed
  return `${trimmed.slice(0, 4)}…${trimmed.slice(-4)}`
}

export function defaultContextLabel(connector: ConnectorRecord): string {
  const cfg = connector.config || {}
  if (connector.connector_type === 'trino') {
    const parts = [cfg.catalog, cfg.schema].filter(Boolean)
    return parts.length ? parts.join(' / ') : '—'
  }
  if (connector.connector_type === 'postgres') {
    return String(cfg.database || '—')
  }
  return String(cfg.database || '—')
}

export function hostFromConfig(connector: ConnectorRecord): string {
  const cfg = connector.config || {}
  const host = String(cfg.host || '')
  const port = cfg.port != null ? String(cfg.port) : ''
  if (!host) return '—'
  return port ? `${maskHost(host)}:${port}` : maskHost(host)
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function capabilityLabels(caps: Record<string, boolean> | null | undefined): string[] {
  if (!caps) return []
  const labels: string[] = []
  if (caps.sql) labels.push('SQL')
  if (caps.metadata) labels.push('Metadata Discovery')
  if (caps.tables) labels.push('Tables')
  if (caps.views) labels.push('Views')
  if (caps.sample_preview) labels.push('Sample Preview')
  if (caps.kerberos) labels.push('Kerberos')
  return labels
}

export const CONNECTOR_TYPE_BLURBS: Record<ConnectorType, string> = {
  impala: 'Connect to governed Cloudera Impala datasets.',
  trino: 'Connect to Trino-compatible distributed SQL endpoints.',
  postgres: 'Connect to local or external PostgreSQL databases.',
}
