import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({ api: { mcpActionHistory: vi.fn() } }))

import { api } from '../lib/api'
import { ActionsPage } from './ActionsPage'

const base = { server_id: 'ops', server: 'Operations Desk', tool: 'create_ticket', at: '2026-11-13T08:20:00+00:00' }

describe('ActionsPage', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('lists approved actions newest first and opens one to show what was sent and what came back', async () => {
    vi.mocked(api.mcpActionHistory).mockResolvedValue({
      actions: [
        { ...base, id: 'b', title: 'Open a ticket for Sorong', arguments: { title: 'Sorong', priority: 'high', location: 'Sorong', evidence: '36.3% vs 16.1%' }, status: 'ok', result: JSON.stringify({ created: { id: 'OPS-1', due_date: '2026-11-27' } }), error: '' },
        { ...base, id: 'a', title: 'Notify the regional lead', server: 'Mail', tool: 'send_email', arguments: { to: 'lead@example.com' }, status: 'failed', result: '', error: 'The action could not run: timeout' },
      ],
    })
    render(<ActionsPage />)
    await waitFor(() => expect(screen.getByText('Open a ticket for Sorong')).toBeTruthy())
    expect(screen.getByText('Done')).toBeTruthy()
    expect(screen.getByText('Failed')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Open a ticket for Sorong' }))
    expect(screen.getByText('36.3% vs 16.1%')).toBeTruthy() // what was sent, as sent
    expect(screen.getByText('OPS-1')).toBeTruthy() // what came back
    fireEvent.click(screen.getByRole('button', { name: 'Notify the regional lead' }))
    expect(screen.getByText('The action could not run: timeout')).toBeTruthy() // a failure is kept too
  })

  it('says how an action gets here when there is none, and what failed with a way to retry', async () => {
    vi.mocked(api.mcpActionHistory).mockResolvedValue({ actions: [] })
    render(<ActionsPage />)
    await waitFor(() => expect(screen.getByText(/No action has been run yet/)).toBeTruthy())
    cleanup()
    vi.mocked(api.mcpActionHistory).mockRejectedValue({ message: 'down' })
    render(<ActionsPage />)
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('down'))
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })
})
