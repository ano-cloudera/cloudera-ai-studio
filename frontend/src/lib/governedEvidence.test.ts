import { describe, expect, it } from 'vitest'

import type { ChatResponse } from '../types/api'
import { answerPresentation, displayStatus } from './governedEvidence'

function baseResponse(overrides: Partial<ChatResponse>): ChatResponse {
  return {
    request_id: 'r1',
    session_id: 's1',
    status: 'SUCCESS',
    provider: 'gemini',
    model: 'test',
    strategy: 'governed',
    answer: {
      direct_answer: 'ok',
      executive_summary: 'ok',
      insights: [],
      business_implications: [],
      caveats: [],
      data_reference: 'gold.foo',
      chart_spec: null,
    },
    data: { columns: ['x'], rows: [{ x: 1 }], row_count: 1, execution_ms: 1 },
    chart_spec: null,
    timings: { total_ms: 1 },
    retry_count: 0,
    ...overrides,
  }
}

describe('displayStatus', () => {
  it('treats ERROR with query rows as SUCCESS for UI', () => {
    const response = baseResponse({ status: 'ERROR' })
    expect(displayStatus(response)).toBe('SUCCESS')
  })

  it('keeps ERROR when there is no governed evidence', () => {
    const response = baseResponse({
      status: 'ERROR',
      data: { columns: [], rows: [], row_count: 0, execution_ms: 0 },
      answer: {
        direct_answer: 'Maaf',
        executive_summary: 'Coba lagi',
        insights: [],
        business_implications: [],
        caveats: [],
        data_reference: 'No result available.',
        chart_spec: null,
      },
    })
    expect(displayStatus(response)).toBe('ERROR')
  })
})

describe('answerPresentation', () => {
  it('never surfaces ERROR chip or something-went-wrong headline', () => {
    const withData = baseResponse({ status: 'ERROR' })
    expect(answerPresentation(withData)).toEqual({
      title: 'Direct answer',
      showStatusChip: false,
      statusChip: null,
    })

    const bare = baseResponse({
      status: 'ERROR',
      data: { columns: [], rows: [], row_count: 0, execution_ms: 0 },
    })
    expect(answerPresentation(bare).title).toBe('Direct answer')
    expect(answerPresentation(bare).showStatusChip).toBe(false)
    expect(answerPresentation(bare).statusChip).toBeNull()
  })
})
