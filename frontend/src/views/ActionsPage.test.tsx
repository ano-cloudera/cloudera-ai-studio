import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({ api: { mcpActionHistory: vi.fn(), deleteMcpActions: vi.fn() } }))

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
        { ...base, id: 'b', title: 'Open a ticket for Sorong', arguments: { title: 'Sorong', priority: 'high', location: 'Sorong', evidence: '36.3% vs 16.1%' }, status: 'ok', result: JSON.stringify({ created: { id: 'OPS-1', due_date: '2026-11-27' } }), error: '', duration_ms: 1230, request_id: 'req-9' },
        { ...base, id: 'a', title: 'Notify the regional lead', server: 'Mail', tool: 'send_email', arguments: { to: 'lead@example.com' }, status: 'failed', result: '', error: 'The action could not run: timeout' },
      ],
    })
    render(<ActionsPage />)
    await waitFor(() => expect(screen.getByText('Open a ticket for Sorong')).toBeTruthy())
    expect(document.querySelectorAll('td span.inline-flex')).toHaveLength(2) // a result pill on each row
    expect(Array.from(document.querySelectorAll('td span.inline-flex')).map(el => el.textContent)).toEqual(['Done', 'Failed'])
    fireEvent.click(screen.getByRole('button', { name: 'Open a ticket for Sorong' }))
    expect(screen.getByText('36.3% vs 16.1%')).toBeTruthy() // what was sent, as sent
    expect(screen.getByText('1.2 s')).toBeTruthy() // how long the server took
    expect(screen.getByText('req-9')).toBeTruthy() // the answer that proposed it
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

  const two = {
    actions: [
      { ...base, id: 'b', title: 'Open a ticket for Sorong', arguments: {}, status: 'ok', result: '{}', error: '' },
      { ...base, id: 'a', title: 'Notify the regional lead', arguments: {}, status: 'failed', result: '', error: 'timeout' },
    ],
  } as never

  it('deletes one record from its row menu after confirming, and the log is read again', async () => {
    vi.mocked(api.mcpActionHistory).mockResolvedValue(two)
    vi.mocked(api.deleteMcpActions).mockResolvedValue({ deleted: 1 })
    render(<ActionsPage />)
    await screen.findByText('Open a ticket for Sorong')
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Open a ticket for Sorong' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))
    expect(screen.getByText('Delete 1 action?')).toBeTruthy()
    expect(api.deleteMcpActions).not.toHaveBeenCalled() // nothing goes before it is confirmed
    fireEvent.click(screen.getByRole('button', { name: 'Delete 1 action' }))
    await waitFor(() => expect(api.deleteMcpActions).toHaveBeenCalledWith(['b']))
    await waitFor(() => expect(api.mcpActionHistory).toHaveBeenCalledTimes(2))
  })

  it('deletes several at once from the selection mode, like the other tables', async () => {
    vi.mocked(api.mcpActionHistory).mockResolvedValue(two)
    vi.mocked(api.deleteMcpActions).mockResolvedValue({ deleted: 2 })
    render(<ActionsPage />)
    await screen.findByText('Open a ticket for Sorong')
    fireEvent.click(screen.getByRole('button', { name: /Select/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Open a ticket for Sorong' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Notify the regional lead' }))
    expect(screen.getByText('2 selected')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Delete selected' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete 2 actions' }))
    await waitFor(() => expect(api.deleteMcpActions).toHaveBeenCalledWith(expect.arrayContaining(['a', 'b'])))
  })

  it('searches and filters by result', async () => {
    vi.mocked(api.mcpActionHistory).mockResolvedValue(two)
    render(<ActionsPage />)
    await screen.findByText('Open a ticket for Sorong')
    fireEvent.change(screen.getByLabelText('Filter by result'), { target: { value: 'failed' } })
    expect(screen.queryByText('Open a ticket for Sorong')).toBeNull()
    expect(screen.getByText('Notify the regional lead')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Filter by result'), { target: { value: 'all' } })
    fireEvent.change(screen.getByLabelText('Search actions'), { target: { value: 'sorong' } })
    expect(screen.queryByText('Notify the regional lead')).toBeNull()
  })
})
