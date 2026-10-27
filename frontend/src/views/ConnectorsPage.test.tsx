import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConnectorsPage } from './ConnectorsPage'

const sampleConnector = {
  id: 'c1',
  workspace_id: 'w1',
  project_id: 'p1',
  name: 'Local Postgres',
  key: 'local_postgres',
  description: null,
  connector_type: 'postgres' as const,
  status: 'ACTIVE',
  enabled: true,
  config: { host: 'localhost', port: 5432, database: 'analytics' },
  secret_ref: 'env://PG_SECRET',
  credentials_configured: true,
  last_tested_at: '2026-01-01T00:00:00Z',
  last_test_status: 'SUCCESS',
  last_test_message: null,
  metadata: {},
  created_at: '',
  updated_at: '',
  created_by: null,
}

vi.mock('../lib/api', () => ({
  api: {
    listConnectors: vi.fn(),
    testConnector: vi.fn(),
    patchConnector: vi.fn(),
    deleteConnector: vi.fn(),
  },
}))

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

describe('ConnectorsPage', () => {
  afterEach(cleanup)

  it('renders empty state when no connectors', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [] })
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByText('No data sources yet.'))
    const addLinks = screen.getAllByRole('link', { name: /Add Data Source/i })
    expect(addLinks.some(a => a.getAttribute('href') === '/connectors/new')).toBe(true)
  })

  it('renders connector row with status and does not show secrets', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [sampleConnector] })
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByText('Local Postgres'))
    expect(screen.getByText('Connected')).toBeTruthy()
    expect(screen.queryByText('PG_SECRET')).toBeNull()
    expect(screen.getByText('PostgreSQL')).toBeTruthy()
  })

  it('runs connection test from row action', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [sampleConnector] })
    vi.mocked(api.testConnector).mockResolvedValue({
      status: 'SUCCESS',
      latency_ms: 12,
      server_version: '16',
      server_name: null,
      default_catalog: null,
      default_schema: 'public',
      message: 'ok',
      error_code: null,
      phases: null,
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
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByText('Local Postgres'))
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    await waitFor(() => expect(api.testConnector).toHaveBeenCalledWith('c1'))
  })

  it('paginates data source rows (default 10 per page)', async () => {
    const { api } = await import('../lib/api')
    const many = Array.from({ length: 11 }, (_, i) => ({
      ...sampleConnector,
      id: `c${i}`,
      name: `Source ${i}`,
      key: `source_${i}`,
    }))
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: many })
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByText('Source 0'))
    expect(screen.getByText('Source 9')).toBeTruthy()
    expect(screen.queryByText('Source 10')).toBeNull()
    expect(screen.getByText(/Showing 1–10 of 11/)).toBeTruthy()
  })

  it('confirms delete', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [sampleConnector] })
    vi.mocked(api.deleteConnector).mockResolvedValue({ deleted: true })
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByText('Local Postgres'))
    fireEvent.click(screen.getByLabelText('More actions'))
    fireEvent.click(screen.getByText('Delete'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.deleteConnector).toHaveBeenCalledWith('c1'))
  })
})
