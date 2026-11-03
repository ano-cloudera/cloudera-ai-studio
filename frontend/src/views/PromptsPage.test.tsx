import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { PromptsPage } from './PromptsPage'

vi.mock('../lib/api', () => ({
  api: {
    listPrompts: vi.fn(),
    createPrompt: vi.fn(),
    listPromptVersions: vi.fn(),
    publishPromptVersion: vi.fn(),
  },
}))

describe('Prompts page shell', () => {
  afterEach(cleanup)

  it('shows ServiceErrorState when list API fails', async () => {
    vi.mocked(api.listPrompts).mockRejectedValue(new Error('sit backend unavailable'))
    render(<PromptsPage />)
    expect(await screen.findByText('Unable to load Prompts')).toBeTruthy()
    expect(screen.getByText(/couldn't reach the backend/i)).toBeTruthy()
  })

  it('shows loading copy before first fetch completes', () => {
    vi.mocked(api.listPrompts).mockImplementation(() => new Promise(() => undefined))
    render(<PromptsPage />)
    expect(screen.getByText(/Loading prompts/i)).toBeTruthy()
  })

  it('publishes a new prompt straight from the create drawer and closes it', async () => {
    const record = { id: 'p1', name: 'RAG answers', key: 'rag.system', scope: 'global', description: null, updated_at: '2026-01-01T00:00:00Z' }
    const draft = { id: 'v1', version_number: 1, status: 'DRAFT', content: 'x', created_at: '2026-01-01T00:00:00Z' }
    vi.mocked(api.listPrompts).mockResolvedValueOnce({ prompts: [] } as never).mockResolvedValue({ prompts: [record] } as never)
    vi.mocked(api.createPrompt).mockResolvedValue({ prompt: record } as never)
    vi.mocked(api.listPromptVersions).mockResolvedValue({ versions: [draft] } as never)
    vi.mocked(api.publishPromptVersion).mockResolvedValue({ version: { ...draft, status: 'ACTIVE' } } as never)
    render(<PromptsPage />)
    fireEvent.click(await screen.findByRole('button', { name: /Create prompt/i }))
    fireEvent.change(screen.getAllByRole('textbox')[1], { target: { value: 'RAG answers' } })
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }))
    await waitFor(() => expect(api.publishPromptVersion).toHaveBeenCalledWith('p1', 'v1'))
    await waitFor(() => expect(screen.queryByText('Overrides the built-in prompt for every project. Needs the platform metadata database.')).toBeNull())
  })
})

