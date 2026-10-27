import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { UsagePage } from './UsagePage'

vi.mock('../lib/api', () => ({
  api: {
    usageSummary: vi.fn(),
    usageEvents: vi.fn(),
    usageExportCsvUrl: vi.fn(() => '/api/usage/export.csv?days=7'),
  },
}))

describe('Usage page', () => {
  afterEach(cleanup)

  it('shows loading then summary cards', async () => {
    vi.mocked(api.usageSummary).mockResolvedValue({
      period_days: 7,
      mtd: false,
      totals: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30, llm_calls: 1, turns: 1 },
      mtd_totals: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30, llm_calls: 1, turns: 1 },
      daily: [],
      by_model: [{ provider: 'gemini', model: 'gemini-3.8-flash', tokens: 30, turns: 1 }],
      monthly_token_budget: 0,
    })
    vi.mocked(api.usageEvents).mockResolvedValue({
      events: [
        {
          request_id: 'r1',
          created_at: '2026-10-15T08:00:00+00:00',
          provider: 'gemini',
          model: 'gemini-3.8-flash',
          strategy: 'rag',
          status: 'SUCCESS',
          total_tokens: 30,
          llm_calls: 1,
        },
      ],
    })
    render(<UsagePage />)
    expect(await screen.findByText('Total tokens')).toBeTruthy()
    expect(screen.getByText('Recent turns')).toBeTruthy()
  })

  it('paginates recent turns (default 10 per page)', async () => {
    vi.mocked(api.usageSummary).mockResolvedValue({
      period_days: 7,
      mtd: false,
      totals: { prompt_tokens: 100, completion_tokens: 200, total_tokens: 300, llm_calls: 11, turns: 11 },
      mtd_totals: { prompt_tokens: 100, completion_tokens: 200, total_tokens: 300, llm_calls: 11, turns: 11 },
      daily: [],
      by_model: [],
      monthly_token_budget: 0,
    })
    vi.mocked(api.usageEvents).mockResolvedValue({
      events: Array.from({ length: 11 }, (_, i) => ({
        request_id: `r${i}`,
        created_at: '2026-10-15T08:00:00+00:00',
        provider: 'gemini',
        model: 'gemini-3.8-flash',
        strategy: 'rag',
        status: 'SUCCESS',
        total_tokens: 30,
        llm_calls: 1,
      })),
    })
    render(<UsagePage />)
    expect(await screen.findByText(/Showing 1–10 of 11/)).toBeTruthy()
  })

  it('shows empty recent turns message', async () => {
    vi.mocked(api.usageSummary).mockResolvedValue({
      period_days: 7,
      mtd: false,
      totals: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, llm_calls: 0, turns: 0 },
      mtd_totals: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, llm_calls: 0, turns: 0 },
      daily: [],
      by_model: [],
      monthly_token_budget: 0,
    })
    vi.mocked(api.usageEvents).mockResolvedValue({ events: [] })
    render(<UsagePage />)
    expect(await screen.findByText('No events in this period.')).toBeTruthy()
  })

  it('shows ServiceErrorState when API fails', async () => {
    vi.mocked(api.usageSummary).mockRejectedValue(new Error('sit backend unavailable'))
    render(<UsagePage />)
    expect(await screen.findByText('Unable to load Usage')).toBeTruthy()
  })
})
