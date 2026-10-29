import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../lib/api'
import { AskDataMcpSettingsPanel } from './AskDataMcpSettingsPanel'

const server = (over: Record<string, unknown> = {}) => ({
  id: 's1',
  name: 'Credit Risk Model',
  description: '',
  enabled: true,
  transport: 'stdio' as const,
  command: '/py/bin/python',
  args: ['/repo/scripts/mcp/credit_risk_server.py'],
  env_var_names: [],
  url: null,
  header_env_var_names: {},
  default_tool: null,
  ...over,
})

describe('AskDataMcpSettingsPanel', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getMcpSettings').mockResolvedValue({ settings: { servers: [server()] } } as never)
    vi.spyOn(api, 'putMcpSettings').mockImplementation(async body => ({ settings: body }) as never)
    vi.spyOn(api, 'testMcpConnection').mockResolvedValue({ ok: true, message: 'Connected (1 tool)', latency_ms: 120 } as never)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows a saved server read-only, with Edit and Test but no Save', async () => {
    render(<AskDataMcpSettingsPanel embedded />)
    await screen.findByTestId('mcp-server-card')
    expect(screen.getByText('Credit Risk Model')).toBeTruthy()
    expect(screen.getByText(/credit_risk_server\.py/)).toBeTruthy()
    expect(screen.queryByPlaceholderText('Display name')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
    expect(screen.getByRole('button', { name: /Edit/ })).toBeTruthy()
  })

  it('tests a saved server and reports the result on its card', async () => {
    render(<AskDataMcpSettingsPanel embedded />)
    await screen.findByTestId('mcp-server-card')
    fireEvent.click(screen.getByRole('button', { name: /Test connection/ }))
    expect((await screen.findByTestId('mcp-test-result')).textContent).toContain('Connected (1 tool) (120 ms)')
  })

  it('edits, saves only that server, and returns to the read-only card', async () => {
    render(<AskDataMcpSettingsPanel embedded />)
    await screen.findByTestId('mcp-server-card')
    fireEvent.click(screen.getByRole('button', { name: /Edit/ }))
    fireEvent.change(screen.getByPlaceholderText('Display name'), { target: { value: 'Risk Model v2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.putMcpSettings).toHaveBeenCalled())
    expect(vi.mocked(api.putMcpSettings).mock.calls[0]![0].servers[0]!.name).toBe('Risk Model v2')
    await screen.findByTestId('mcp-server-card')
    expect(screen.getByText('Risk Model v2')).toBeTruthy()
  })

  it('cancel discards unsaved edits', async () => {
    render(<AskDataMcpSettingsPanel embedded />)
    await screen.findByTestId('mcp-server-card')
    fireEvent.click(screen.getByRole('button', { name: /Edit/ }))
    fireEvent.change(screen.getByPlaceholderText('Display name'), { target: { value: 'Changed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByText('Credit Risk Model')).toBeTruthy()
    expect(api.putMcpSettings).not.toHaveBeenCalled()
  })

  it('a new server starts in the form and is saved once it can be tested', async () => {
    render(<AskDataMcpSettingsPanel embedded />)
    await screen.findByTestId('mcp-server-card')
    fireEvent.click(screen.getByRole('button', { name: /Add server/ }))
    const save = screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.change(screen.getByPlaceholderText('Display name'), { target: { value: 'Second' } })
    expect(save.disabled).toBe(false)
  })

  it('toggling Enabled on a saved card persists immediately', async () => {
    render(<AskDataMcpSettingsPanel embedded />)
    await screen.findByTestId('mcp-server-card')
    fireEvent.click(screen.getByLabelText('Enable Credit Risk Model'))
    await waitFor(() => expect(api.putMcpSettings).toHaveBeenCalled())
    expect(vi.mocked(api.putMcpSettings).mock.calls[0]![0].servers[0]!.enabled).toBe(false)
  })
})
