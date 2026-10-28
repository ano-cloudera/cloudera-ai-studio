import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildPrimaryNavigation, AppShell } from '../layout/AppShell'
import { TestBrandingWrapper } from '../test/testBrandingWrapper'
import { appConfig } from '../config/appConfig'
import {
  ADD_DATA_SOURCE,
  CREATE_DATA_SOURCE_TYPE_HINT,
  DATA_SOURCES_PAGE_SUBTITLE,
  DELETE_DATA_SOURCE_TITLE,
  SEARCH_DATA_SOURCES_PLACEHOLDER,
} from './connectors/dataSourceUx'
import { ConnectorsPage } from './ConnectorsPage'
import { ConnectorCreatePage } from './ConnectorCreatePage'

vi.mock('next/navigation', () => ({
  usePathname: () => '/connectors',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('../lib/api', () => ({
  api: {
    listConnectors: vi.fn().mockResolvedValue({ connectors: [] }),
    createConnector: vi.fn(),
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

describe('DATA_SOURCES_UX_RENAME', () => {
  afterEach(cleanup)

  it('sidebar shows Data Sources and not Connectors in primary navigation', () => {
    const nav = buildPrimaryNavigation()
    const labels = nav.map(item => item.label)
    expect(labels).toContain('Data Sources')
    expect(labels).not.toContain('Connectors')
    expect(nav.some(item => item.href === '/connectors' && item.label === 'Data Sources')).toBe(true)

    render(
      <TestBrandingWrapper>
        <AppShell>
          <div>Data sources page</div>
        </AppShell>
      </TestBrandingWrapper>,
    )
    const primaryNav = screen.getByRole('navigation', { name: 'Primary navigation' })
    const linkLabels = within(primaryNav)
      .getAllByRole('link')
      .map(link => link.textContent?.trim())
    expect(linkLabels).toContain(appConfig.navigationConnectors)
    expect(linkLabels).not.toContain('Connectors')
  })

  it('list page title, subtitle, search, and CTA use data source terminology', async () => {
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByRole('heading', { name: 'Data Sources' }))
    expect(screen.getByText(DATA_SOURCES_PAGE_SUBTITLE)).toBeTruthy()
    expect(screen.getByPlaceholderText(SEARCH_DATA_SOURCES_PLACEHOLDER)).toBeTruthy()
    expect(screen.getAllByRole('link', { name: ADD_DATA_SOURCE }).length).toBeGreaterThan(0)
  })

  it('delete confirmation uses data source copy', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listConnectors).mockResolvedValue({
      connectors: [
        {
          id: 'c1',
          workspace_id: 'w1',
          project_id: 'p1',
          name: 'Demo PG',
          key: 'demo_pg',
          description: null,
          connector_type: 'postgres',
          status: 'ACTIVE',
          enabled: true,
          config: { host: 'localhost', port: 5432, database: 'analytics' },
          secret_ref: null,
          credentials_configured: true,
          last_tested_at: null,
          last_test_status: 'SUCCESS',
          last_test_message: null,
          metadata: {},
          created_at: '',
          updated_at: '',
          created_by: null,
        },
      ],
    })
    render(<ConnectorsPage />)
    await waitFor(() => screen.getByText('Demo PG'))
    fireEvent.click(screen.getByLabelText('More actions'))
    fireEvent.click(screen.getByText('Delete'))
    expect(screen.getByText(DELETE_DATA_SOURCE_TITLE)).toBeTruthy()
    expect(screen.getByText(/will no longer be available to Ask Data or Semantic Layer/i)).toBeTruthy()
  })

  it('create flow uses data source terminology and still posts to connector API', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.createConnector).mockResolvedValue({
      connector: {
        id: 'new-id',
        workspace_id: 'w1',
        project_id: 'p1',
        name: 'PG DS',
        key: 'pg_ds',
        description: null,
        connector_type: 'postgres',
        status: 'ACTIVE',
        enabled: true,
        config: {},
        secret_ref: null,
        credentials_configured: false,
        last_tested_at: null,
        last_test_status: null,
        last_test_message: null,
        metadata: {},
        created_at: '',
        updated_at: '',
        created_by: null,
      },
    })

    render(<ConnectorCreatePage />)
    expect(screen.getByRole('heading', { name: 'Add Data Source' })).toBeTruthy()
    expect(screen.getByText(CREATE_DATA_SOURCE_TYPE_HINT)).toBeTruthy()
    expect(screen.getByText('Data source type')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /PostgreSQL/i }))
    fireEvent.change(screen.getByLabelText(/Data source name/i), { target: { value: 'PG DS' } })
    fireEvent.change(screen.getByLabelText(/^Host$/i), { target: { value: 'localhost' } })
    fireEvent.change(screen.getByLabelText(/^Port$/i), { target: { value: '5432' } })
    fireEvent.change(screen.getByLabelText(/^Database$/i), { target: { value: 'analytics' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save data source' }))
    await waitFor(() => expect(api.createConnector).toHaveBeenCalled())
    const body = vi.mocked(api.createConnector).mock.calls[0][0]
    expect(body.connector_type).toBe('postgres')
  })
})
