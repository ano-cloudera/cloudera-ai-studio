import React from 'react'
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { useModelSelection } from '../lib/modelSelection'
import { renderWithProviders } from '../test/renderWithProviders'
import { SettingsPage } from './SettingsPage'

vi.mock('../lib/api', () => ({
  api: {
    models: vi.fn(),
    listAiProviders: vi.fn().mockResolvedValue({ providers: [] }),
    listAiModels: vi.fn().mockResolvedValue({ models: [] }),
    listModelAssignments: vi.fn().mockResolvedValue({ assignments: [] }),
    getMcpSettings: vi.fn().mockResolvedValue({ workspace_slug: 'default', settings: { servers: [] } }),
    putMcpSettings: vi.fn(),
    testMcpConnection: vi.fn().mockResolvedValue({
      ok: true,
      message: 'Connected (1 tool: search)',
      tools: ['search'],
      latency_ms: 10,
      missing_env_var_names: [],
    }),
  },
}))

function SelectionProbe() {
  const value = useModelSelection()
  return (
    <span data-testid="committed-model">
      {value.selection ? `${value.selection.provider}:${value.selection.model}` : 'none'}
    </span>
  )
}

describe('V2 Settings', () => {
  afterEach(cleanup)

  it('uses one AI model selector and disables unavailable models', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [
      { provider: 'qwen', id: 'qwen-configured', label: 'Qwen Private', available: true, reason: null },
      { provider: 'gemini', id: 'gemini-configured', label: 'Gemini', available: false, reason: 'API key not configured' },
      { provider: 'openai', id: 'gpt-configured', label: 'ChatGPT', available: true, reason: null },
    ] })
    renderWithProviders(
      <>
        <SettingsPage />
        <SelectionProbe />
      </>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /AI models/i }))
    const modelSelect = await screen.findByLabelText('Chat model')
    const geminiOption = within(modelSelect).getByRole('option', { name: /^Gemini$/ }) as HTMLOptionElement
    expect(geminiOption.disabled).toBe(true)

    fireEvent.change(modelSelect, { target: { value: 'openai::gpt-configured' } })
    expect(screen.getByText(/Unsaved change/i)).toBeTruthy()
    expect(screen.getByTestId('committed-model').textContent).not.toBe('openai:gpt-configured')

    fireEvent.click(screen.getByRole('button', { name: 'Save model' }))
    await waitFor(() => expect(screen.getByTestId('committed-model').textContent).toBe('openai:gpt-configured'))
    expect(screen.getByText(/Saved for new chat/i)).toBeTruthy()
    expect(screen.getByText(/Provider: OpenAI/i)).toBeTruthy()
  })

  it('shows MCP settings on the MCP tab, not on General', async () => {
    renderWithProviders(<SettingsPage />)

    expect(screen.getByRole('button', { name: /^MCP$/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Save MCP connections/i })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /^MCP$/i }))
    expect(await screen.findByRole('heading', { name: /^MCP$/i })).toBeTruthy()
    expect(await screen.findByRole('button', { name: /Save MCP connections/i })).toBeTruthy()
    expect(api.getMcpSettings).toHaveBeenCalled()
  })
})
