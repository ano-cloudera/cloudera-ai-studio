import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConnectorDetailPage } from './ConnectorDetailPage'

const connector = {
  id: 'c1',
  workspace_id: 'w1',
  project_id: 'p1',
  name: 'Postgres Dev',
  key: 'postgres_dev',
  description: null,
  connector_type: 'postgres' as const,
  status: 'ACTIVE',
  enabled: true,
  config: { host: 'localhost', port: 5432, database: 'analytics' },
  secret_ref: 'env://PG',
  credentials_configured: true,
  last_tested_at: null,
  last_test_status: null,
  last_test_message: null,
  metadata: {},
  created_at: '',
  updated_at: '',
  created_by: null,
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}))

vi.mock('../lib/api', () => ({
  api: {
    getConnector: vi.fn(),
    getConnectorCapabilities: vi.fn(),
    testConnector: vi.fn(),
    listConnectorCatalogs: vi.fn(),
    listConnectorSchemas: vi.fn(),
    listConnectorTables: vi.fn(),
    describeConnectorTable: vi.fn(),
    previewConnectorTable: vi.fn(),
    patchConnector: vi.fn(),
    deleteConnector: vi.fn(),
    getConnectorReferences: vi.fn().mockResolvedValue({ references: [] }),
    listEnvironmentReferences: vi.fn().mockResolvedValue({ references: [] }),
  },
}))

describe('ConnectorDetailPage', () => {
  afterEach(cleanup)

  it('loads browse hierarchy and preview', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.getConnector).mockResolvedValue({ connector })
    vi.mocked(api.getConnectorCapabilities).mockResolvedValue({
      capabilities: {
        sql: true,
        metadata: true,
        catalogs: false,
        schemas: true,
        tables: true,
        views: true,
        read_only_query: true,
        sample_preview: true,
        transactions: false,
        kerberos: false,
      },
    })
    vi.mocked(api.listConnectorSchemas).mockResolvedValue({
      schemas: [{ name: 'public', catalog: null, comment: null }],
      total: 1,
      limit: 500,
      offset: 0,
      resolved_context: {},
    })
    vi.mocked(api.listConnectorTables).mockResolvedValue({
      tables: [{ name: 'customers', schema: 'public', catalog: null, table_type: 'TABLE', comment: null }],
      total: 1,
      limit: 100,
      offset: 0,
      resolved_context: {},
    })
    vi.mocked(api.describeConnectorTable).mockResolvedValue({
      table: {
        catalog: null,
        schema: 'public',
        name: 'customers',
        table_type: 'TABLE',
        comment: null,
        primary_key: null,
        metadata: {},
        columns: [
          {
            name: 'id',
            data_type: 'bigint',
            native_type: 'bigint',
            normalized_type: 'INTEGER',
            nullable: false,
            ordinal_position: 1,
            comment: null,
          },
        ],
      },
    })
    vi.mocked(api.previewConnectorTable).mockResolvedValue({
      preview: {
        columns: ['id'],
        rows: [{ id: 1 }],
        row_count: 1,
        truncated: false,
        query_duration_ms: 3,
        resolved_context: { catalog: null, schema: 'public', table: 'customers' },
      },
    })

    render(<ConnectorDetailPage connectorId="c1" />)
    await waitFor(() => screen.getByText('Postgres Dev'))
    fireEvent.click(screen.getByRole('tab', { name: 'Browse Data' }))
    await waitFor(() => screen.getByRole('button', { name: /^customers/i }))
    fireEvent.click(screen.getByRole('button', { name: /^customers/i }))
    await waitFor(() => screen.getByText('INTEGER'))
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await waitFor(() => expect(api.previewConnectorTable).toHaveBeenCalled())
    expect(screen.getByText('Preview limited to 1 row.')).toBeTruthy()
  })

  it('shows normalized connection test failure', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.getConnector).mockResolvedValue({ connector })
    vi.mocked(api.getConnectorCapabilities).mockResolvedValue({
      capabilities: {
        sql: true,
        metadata: true,
        catalogs: false,
        schemas: true,
        tables: true,
        views: true,
        read_only_query: true,
        sample_preview: true,
        transactions: false,
        kerberos: false,
      },
    })
    vi.mocked(api.testConnector).mockResolvedValue({
      status: 'FAILED',
      latency_ms: 5,
      server_version: null,
      server_name: null,
      default_catalog: null,
      default_schema: null,
      message: 'Authentication was rejected by the target server.',
      error_code: 'AUTHENTICATION_FAILED',
      phases: { authenticating: 'failed' },
      capabilities: {
        sql: true,
        metadata: true,
        catalogs: true,
        schemas: true,
        tables: true,
        views: true,
        read_only_query: true,
        sample_preview: true,
        transactions: false,
        kerberos: false,
      },
    })
    render(<ConnectorDetailPage connectorId="c1" />)
    await waitFor(() => screen.getByText('Postgres Dev'))
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => screen.getByText('Connection failed'))
    expect(screen.getByText(/AUTHENTICATION_FAILED/)).toBeTruthy()
  })
})

const capabilities = {
  sql: true,
  metadata: true,
  catalogs: false,
  schemas: true,
  tables: true,
  views: true,
  read_only_query: true,
  sample_preview: true,
  transactions: false,
  kerberos: false,
}

describe('ConnectorDetailPage: saving and refreshing', () => {
  afterEach(cleanup)

  it('returns to the Overview after Save changes and tests the connection', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.getConnector).mockResolvedValue({ connector })
    vi.mocked(api.getConnectorCapabilities).mockResolvedValue({ capabilities })
    vi.mocked(api.patchConnector).mockResolvedValue({ connector })
    vi.mocked(api.testConnector).mockResolvedValue({ status: 'OK', message: 'Connected', latency_ms: 4 } as never)
    render(<ConnectorDetailPage connectorId="c1" />)
    await waitFor(() => screen.getByText('Postgres Dev'))
    fireEvent.click(screen.getByRole('tab', { name: 'config' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.testConnector).toHaveBeenCalledWith('c1'))
    await waitFor(() => expect(screen.getByRole('tab', { name: 'overview' }).getAttribute('aria-selected')).toBe('true'))
    expect(screen.getByRole('status').textContent).toContain('Changes saved')
  })

  it('refreshes one step after another and ignores a second click while it runs', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.getConnector).mockResolvedValue({ connector })
    vi.mocked(api.getConnectorCapabilities).mockResolvedValue({ capabilities })
    const schemasPage = { schemas: [{ name: 'public', catalog: null, comment: null }], total: 1, limit: 500, offset: 0, resolved_context: {} }
    const tablesPage = { tables: [{ name: 'customers', schema: 'public', catalog: null, table_type: 'TABLE', comment: null }], total: 1, limit: 100, offset: 0, resolved_context: {} }
    let releaseSchemas: () => void = () => undefined
    vi.mocked(api.listConnectorSchemas).mockImplementation(((_id: string, params: { refresh?: boolean }) =>
      params?.refresh ? new Promise(resolve => { releaseSchemas = () => resolve(schemasPage) }) : Promise.resolve(schemasPage)) as never)
    vi.mocked(api.listConnectorTables).mockResolvedValue(tablesPage as never)
    render(<ConnectorDetailPage connectorId="c1" />)
    await waitFor(() => screen.getByText('Postgres Dev'))
    fireEvent.click(screen.getByRole('tab', { name: 'Browse Data' }))
    await waitFor(() => screen.getByRole('button', { name: /^customers/i }))
    vi.mocked(api.listConnectorTables).mockClear()

    const button = screen.getByRole('button', { name: 'Refresh' })
    fireEvent.click(button)
    await waitFor(() => expect(screen.getByRole('button', { name: /Refreshing/ }).hasAttribute('disabled')).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: /Refreshing/ }))
    expect(vi.mocked(api.listConnectorTables)).not.toHaveBeenCalled() // tables wait for the schemas step
    releaseSchemas()
    await waitFor(() => expect(vi.mocked(api.listConnectorTables).mock.calls.some(call => (call[1] as { refresh?: boolean }).refresh === true)).toBe(true))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh' }).hasAttribute('disabled')).toBe(false))
    const schemaRefreshes = vi.mocked(api.listConnectorSchemas).mock.calls.filter(call => (call[1] as { refresh?: boolean }).refresh === true)
    expect(schemaRefreshes).toHaveLength(1) // the second click did not start another refresh
  })
})
