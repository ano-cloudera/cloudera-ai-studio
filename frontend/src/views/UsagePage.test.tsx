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

  it('summarises how questions were answered and flags the SQL fallback', async () => {
    vi.mocked(api.usageSummary).mockResolvedValue({
      period_days: 7,
      mtd: false,
      totals: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2, llm_calls: 4, turns: 4 },
      mtd_totals: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2, llm_calls: 4, turns: 4 },
      daily: [],
      by_model: [],
      monthly_token_budget: 0,
    })
    const event = (id: string, strategy: string) => ({
      request_id: id,
      created_at: '2026-10-15T08:00:00+00:00',
      provider: 'gemini',
      model: 'm',
      strategy,
      status: 'SUCCESS',
      total_tokens: 1,
      llm_calls: 1,
    })
    vi.mocked(api.usageEvents).mockResolvedValue({
      events: [event('a', 'governed'), event('b', 'governed'), event('c', 'governed'), event('d', 'sql_fallback')],
    } as never)
    render(<UsagePage />)
    const panel = await screen.findByTestId('answer-paths')
    expect(panel.textContent).toContain('Governed metric')
    expect(panel.textContent).toContain('75%')
    expect(panel.textContent).toContain('Controlled SQL (fallback)')
    expect(panel.textContent).toContain('25%')
  })

  it('says how usage moved against the period before, and shows the move on each card without judging it', async () => {
    const totals = { prompt_tokens: 1_000, completion_tokens: 200, total_tokens: 1_200, llm_calls: 12, turns: 6 }
    vi.mocked(api.usageSummary).mockResolvedValue({
      period_days: 7,
      mtd: false,
      totals,
      prior_totals: { prompt_tokens: 800, completion_tokens: 200, total_tokens: 1_000, llm_calls: 10, turns: 5 },
      prior_period_days: 7,
      mtd_totals: totals,
      daily: [
        { day: '2026-11-11', tokens: 800 },
        { day: '2026-11-12', tokens: 400 },
      ],
      by_model: [],
      monthly_token_budget: 0,
    })
    vi.mocked(api.usageEvents).mockResolvedValue({ events: [] })
    render(<UsagePage />)
    const line = await screen.findByTestId('usage-summary-line')
    expect(line.textContent).toContain('Usage is up 20% on the period before')
    expect(line.textContent).toContain('against 1.0K in the 7 days before')
    expect(line.textContent).toContain('Busiest day: Nov 11')
    expect(screen.getByText('+25.0%')).toBeTruthy() // prompt tokens 800 → 1,000
    expect(screen.getAllByText('+20.0%')).toHaveLength(2) // total tokens 1,000 → 1,200 and calls 10 → 12
    expect(document.querySelector('.text-emerald-600, .text-emerald-700, .bg-emerald-100')).toBeNull() // a rise in spend is not good news
  })

  it('has no comparison to draw when nothing came before', async () => {
    const totals = { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30, llm_calls: 1, turns: 1 }
    vi.mocked(api.usageSummary).mockResolvedValue({
      period_days: 7,
      mtd: false,
      totals,
      prior_totals: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, llm_calls: 0, turns: 0 },
      prior_period_days: 7,
      mtd_totals: totals,
      daily: [],
      by_model: [],
      monthly_token_budget: 0,
    })
    vi.mocked(api.usageEvents).mockResolvedValue({ events: [] })
    render(<UsagePage />)
    expect((await screen.findByTestId('usage-summary-line')).textContent).toContain('30 tokens across 1 Ask Data turns')
  })
})
