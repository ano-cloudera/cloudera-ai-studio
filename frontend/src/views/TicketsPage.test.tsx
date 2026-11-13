import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({ api: { readableMcpTools: vi.fn(), readMcpTool: vi.fn() } }))

import { api } from '../lib/api'
import { TicketsPage } from './TicketsPage'

const ticket = (id: string, priority: string, title: string) => ({
  id,
  title,
  description: 'Audit the fleet and reschedule loading.',
  priority,
  location: 'Sorong',
  assignee_role: 'Terminal manager',
  due_date: '2026-11-27',
  evidence: 'late rate 36.3% vs 16.1% overall',
  status: 'open',
  created_at: '2026-11-13T08:00:00+00:00',
})

describe('TicketsPage', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('lists the tickets, highest priority first, and opens one to show what to do and its evidence', async () => {
    vi.mocked(api.readableMcpTools).mockResolvedValue({ tools: [{ server_id: 'ops', server: 'Operations Desk', tool: 'list_tickets', description: '' }] })
    vi.mocked(api.readMcpTool).mockResolvedValue({
      ok: true,
      server: 'Operations Desk',
      tool: 'list_tickets',
      result: JSON.stringify({ tickets: [ticket('OPS-1', 'low', 'Review slots'), ticket('OPS-2', 'high', 'Investigate Sorong')], count: 2 }),
    })
    render(<TicketsPage />)
    await waitFor(() => expect(screen.getByText('Investigate Sorong')).toBeTruthy())
    expect(api.readMcpTool).toHaveBeenCalledWith({ server_id: 'ops', tool: 'list_tickets', arguments: { status: 'all', limit: 100 } })
    const titles = screen.getAllByRole('button', { name: /Review slots|Investigate Sorong/ }).map(button => button.textContent)
    expect(titles).toEqual(['Investigate Sorong', 'Review slots']) // high before low
    fireEvent.click(screen.getByRole('button', { name: 'Investigate Sorong' }))
    expect(screen.getByText('late rate 36.3% vs 16.1% overall')).toBeTruthy()
  })

  it('says what to do when there is no server, no tickets yet, or a failure', async () => {
    vi.mocked(api.readableMcpTools).mockResolvedValue({ tools: [] })
    render(<TicketsPage />)
    await waitFor(() => expect(screen.getByText(/No MCP server with a ticket list/)).toBeTruthy())
    cleanup()
    vi.mocked(api.readableMcpTools).mockResolvedValue({ tools: [{ server_id: 'ops', server: 'Operations Desk', tool: 'list_tickets', description: '' }] })
    vi.mocked(api.readMcpTool).mockResolvedValue({ ok: true, server: 'x', tool: 'list_tickets', result: JSON.stringify({ tickets: [] }) })
    render(<TicketsPage />)
    await waitFor(() => expect(screen.getByText(/No tickets yet/)).toBeTruthy())
    cleanup()
    vi.mocked(api.readableMcpTools).mockRejectedValue({ message: 'server down' })
    render(<TicketsPage />)
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('server down'))
  })
})
