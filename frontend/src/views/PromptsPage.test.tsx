import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { PromptsPage } from './PromptsPage'

vi.mock('../lib/api', () => ({
  api: {
    listPrompts: vi.fn(),
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
})
