import { describe, expect, it } from 'vitest'
import { analysisArtifactFromResponse, shouldOpenAnalysisPanel } from './analysisArtifact'
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
    data: { columns: [], rows: [], row_count: 0, execution_ms: 0 },
    timings: { context_ms: 0, planning_ms: 0, validation_ms: 0, query_ms: 0, analysis_ms: 0, total_ms: 0 },
    retry_count: 0,
    ...overrides,
  }
}

describe('analysisArtifactFromResponse', () => {
  it('returns none for RAG responses', () => {
    expect(analysisArtifactFromResponse(base({ strategy: 'rag', route: 'rag' }))).toBe('none')
    expect(shouldOpenAnalysisPanel(base({ strategy: 'rag', route: 'rag' }))).toBe(false)
  })

  it('opens for tabular ask data', () => {
    const response = base({
      data: { columns: ['a'], rows: [{ a: 1 }], row_count: 1, execution_ms: 3 },
    })
    expect(analysisArtifactFromResponse(response)).toBe('table')
    expect(shouldOpenAnalysisPanel(response)).toBe(true)
  })
})
