import { describe, expect, it } from 'vitest'
import { computePresentationTier, shouldAutoOpenAnalysisPanel } from './presentationTier'
import type { ChatResponse } from '../types/api'

function base(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    request_id: 'r1',
    session_id: 's1',
    status: 'SUCCESS',
    provider: 'qwen',
    model: 'm',
    strategy: 'governed',
    answer: {
      direct_answer: 'ok',
      executive_summary: 'ok',
      insights: [],
      business_implications: [],
      caveats: [],
      data_reference: 'ref',
    },
    data: { columns: [], rows: [], row_count: 0, execution_ms: 12 },
    timings: { context_ms: 0, planning_ms: 0, validation_ms: 0, query_ms: 0, analysis_ms: 0, total_ms: 0 },
    retry_count: 0,
    governed_sql: 'SELECT 1',
    ...overrides,
  }
}

describe('computePresentationTier', () => {
  it('tier 1 for single-value KPI', () => {
    const response = base({
      chart_spec: { type: 'kpi', title: 'Total', x: null, y: 'total' },
      data: { columns: ['total'], rows: [{ total: 31375 }], row_count: 1, execution_ms: 5 },
    })
    expect(computePresentationTier(response)).toBe(1)
    expect(shouldAutoOpenAnalysisPanel(response)).toBe(false)
  })

  it('tier 2 for multi-row without chart', () => {
    const response = base({
      answer: {
        direct_answer: 'ok',
        executive_summary: 'ok',
        insights: ['One insight'],
        business_implications: [],
        caveats: [],
        data_reference: 'ref',
      },
      data: {
        columns: ['region', 'n'],
        rows: [
          { region: 'a', n: 1 },
          { region: 'b', n: 2 },
        ],
        row_count: 2,
        execution_ms: 5,
      },
    })
    expect(computePresentationTier(response)).toBe(2)
  })

  it('tier 3 for visual chart', () => {
    const response = base({
      chart_spec: { type: 'bar', title: 'By region', x: 'region', y: 'n' },
      data: {
        columns: ['region', 'n'],
        rows: [
          { region: 'a', n: 1 },
          { region: 'b', n: 2 },
        ],
        row_count: 2,
        execution_ms: 5,
      },
    })
    expect(computePresentationTier(response)).toBe(3)
    expect(shouldAutoOpenAnalysisPanel(response)).toBe(true)
  })

  it('respects backend presentation_tier override', () => {
    const response = base({
      presentation_tier: 3,
      data: { columns: ['x'], rows: [{ x: 1 }], row_count: 1, execution_ms: 1 },
    } as ChatResponse & { presentation_tier: 3 })
    expect(computePresentationTier(response)).toBe(3)
  })
})
