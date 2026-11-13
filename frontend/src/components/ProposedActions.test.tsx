import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({ api: { runMcpAction: vi.fn() } }))

import { api } from '../lib/api'
import { ProposedActions } from './ProposedActions'

const action = {
  id: 'a1',
  server_id: 'ops',
  server: 'Operations Desk',
  tool: 'create_ticket',
  title: 'Buat tiket: keterlambatan Sorong',
  arguments: { title: 'Keterlambatan Sorong', priority: 'high', location: 'Sorong', evidence: '36,3% vs 16,1%' },
}

describe('ProposedActions', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('runs nothing until approved, then shows what was created', async () => {
    vi.mocked(api.runMcpAction).mockResolvedValue({
      ok: true,
      server: 'Operations Desk',
      tool: 'create_ticket',
      result: JSON.stringify({ created: { id: 'OPS-261113-AB12', title: 'Keterlambatan Sorong', due_date: '2026-11-16' } }),
    })
    render(<ProposedActions actions={[action]} language="id" requestId="req-1" />)
    expect(screen.getByText('Proposed actions')).toBeTruthy()
    expect(screen.getByText('36,3% vs 16,1%')).toBeTruthy()
    expect(api.runMcpAction).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Run/ }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('OPS-261113-AB12'))
    expect(api.runMcpAction).toHaveBeenCalledWith({ server_id: 'ops', tool: 'create_ticket', arguments: action.arguments, title: action.title, request_id: 'req-1' })
    expect(screen.queryByRole('button', { name: /Run/ })).toBeNull()
  })

  it('says when an action failed and lets the user retry', async () => {
    vi.mocked(api.runMcpAction).mockRejectedValue({ message: 'server unavailable' })
    render(<ProposedActions actions={[action]} language="en" />)
    fireEvent.click(screen.getByRole('button', { name: /Run/ }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('server unavailable'))
    expect(screen.getByRole('button', { name: /Retry/ })).toBeTruthy()
  })
})
