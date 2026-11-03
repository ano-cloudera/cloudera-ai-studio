import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../lib/api'
import { SemanticQualityTabPanel, parseExampleLines } from './SemanticQualityTabPanel'

vi.mock('../../lib/modelSelection', () => ({
  useModelSelection: () => ({ selection: { provider: 'gemini', model: 'g-1' } }),
}))
vi.mock('../../lib/api', () => ({
  api: { getSemanticKnowledge: vi.fn(), putSemanticKnowledge: vi.fn(), runSemanticBenchmarks: vi.fn() },
}))

const example = { question: 'How many orders?', expected_value: 8000, tolerance: 0.05, match: null }

describe('SemanticQualityTabPanel', () => {
  beforeEach(() => {
    vi.mocked(api.getSemanticKnowledge).mockResolvedValue({ instructions: 'Late means after the SLA.', examples: [example], runs: [] })
  })
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads the saved instructions and examples and saves edits', async () => {
    vi.mocked(api.putSemanticKnowledge).mockImplementation(async (_id, body) => ({ ...body, runs: [] }))
    render(<SemanticQualityTabPanel modelId="m1" published />)
    expect(await screen.findByDisplayValue('Late means after the SLA.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Instructions'), { target: { value: 'Report in IDR millions.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.putSemanticKnowledge).toHaveBeenCalledWith('m1', { instructions: 'Report in IDR millions.', examples: [example] }))
    expect(await screen.findByText(/Saved/)).toBeTruthy()
  })

  it('runs the benchmark with the selected model and lists pass and fail', async () => {
    vi.mocked(api.runSemanticBenchmarks).mockResolvedValue({
      run: { at: '2026-11-03T10:00:00+00:00', published_version: 2, passed: 0, total: 1 },
      runs: [{ at: '2026-11-03T10:00:00+00:00', published_version: 2, passed: 0, total: 1 }],
      results: [{ question: 'How many orders?', expected: 8000, tolerance: 0.05, match: null, actual: 7990, status: 'fail', message: 'Expected 8000, got 7990.' }],
    })
    render(<SemanticQualityTabPanel modelId="m1" published />)
    fireEvent.click(await screen.findByRole('button', { name: /Run benchmark \(1\)/ }))
    await waitFor(() => expect(api.runSemanticBenchmarks).toHaveBeenCalledWith('m1', { provider: 'gemini', model: 'g-1' }))
    expect(await screen.findByText('Fail')).toBeTruthy()
    expect(screen.getByText('Expected 8000, got 7990.')).toBeTruthy()
    expect(screen.getByText(/v2 · 0 of 1 passed/)).toBeTruthy()
  })

  it('cannot run before the model is published', async () => {
    render(<SemanticQualityTabPanel modelId="m1" published={false} />)
    const button = (await screen.findByRole('button', { name: /Run benchmark/ })) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(screen.getByText('Publish the model first.')).toBeTruthy()
  })

  it('turns pasted lines into examples', () => {
    expect(parseExampleLines('# comment\nWhich region is highest? | 23,15 | 0.1 | Kalimantan Timur\nHow many orders?\n\nBad number | abc')).toEqual([
      { question: 'Which region is highest?', expected_value: 23.15, tolerance: 0.1, match: 'Kalimantan Timur' },
      { question: 'How many orders?', expected_value: null, tolerance: 0.05, match: null },
      { question: 'Bad number', expected_value: null, tolerance: 0.05, match: null },
    ])
  })
})
