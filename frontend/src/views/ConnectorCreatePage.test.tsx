import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConnectorCreatePage } from './ConnectorCreatePage'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams('type=postgres'),
}))

vi.mock('../lib/api', () => ({
  api: {
    createConnector: vi.fn().mockResolvedValue({
      connector: { id: 'new-id', enabled: true },
    }),
    testConnector: vi.fn(),
  },
}))

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}))

describe('ConnectorCreatePage', () => {
  afterEach(cleanup)

  it('shows postgres-specific fields and saves without echoing secret', async () => {
    render(<ConnectorCreatePage />)
    expect(screen.getByText(/independent from the accelerator/i)).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/Data source name/i), { target: { value: 'PG DS' } })
    fireEvent.change(screen.getByLabelText(/^Host$/i), { target: { value: 'localhost' } })
    fireEvent.change(screen.getByLabelText(/^Database$/i), { target: { value: 'analytics' } })
    fireEvent.change(screen.getByLabelText(/Secret reference/i), { target: { value: 'env://MY_SECRET' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save data source' }))
    const { api } = await import('../lib/api')
    await waitFor(() => expect(api.createConnector).toHaveBeenCalled())
    const body = vi.mocked(api.createConnector).mock.calls[0][0]
    expect(body.connector_type).toBe('postgres')
    expect(body.secret_ref).toBe('env://MY_SECRET')
    expect(body.config.host).toBe('localhost')
  })
})
