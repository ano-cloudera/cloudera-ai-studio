import { describe, expect, it } from 'vitest'
import { clarificationChoices } from './clarificationPrompts'
import type { ChatResponse } from '../types/api'

function clarificationResponse(direct: string): ChatResponse {
  return {
    request_id: 'r1',
    session_id: 's1',
    status: 'CLARIFICATION',
    provider: 'gemini',
    model: 'gemini-3.8-flash',
    strategy: 'clarification',
    answer: {
      direct_answer: direct,
      executive_summary: '',
      insights: [],
      business_implications: [],
      caveats: [],
      data_reference: '',
      chart_spec: null,
    },
    data: { columns: [], rows: [], row_count: 0, execution_ms: 0 },
    chart_spec: null,
    timings: { total_ms: 1 },
    retry_count: 0,
  }
}

describe('clarificationChoices', () => {
  it('uses structured API options when present', () => {
    const response = clarificationResponse('pick one')
    response.status = 'clarification_required'
    response.clarification = {
      reason: 'AMBIGUOUS_DATA_SOURCE',
      message: 'pick',
      options: [{ type: 'table', id: 'tr:abc', name: 'Sales Sell In' }],
    }
    const choices = clarificationChoices(response)
    expect(choices?.[0].label).toBe('Sales Sell In')
    expect(choices?.[0].contextSource?.id).toBe('tr:abc')
  })

  it('offers no chips when the backend sent no options', () => {
    expect(clarificationChoices(clarificationResponse('Which metric do you mean?'))).toBeNull()
  })

  it('returns null for success answers', () => {
    const response = clarificationResponse('ok')
    response.status = 'SUCCESS'
    response.strategy = 'governed'
    expect(clarificationChoices(response)).toBeNull()
  })
})
