import { describe, expect, it } from 'vitest'

import { formatDurationSeconds, formatResponseMetadata } from './responseMetadata'
import type { ChatResponse } from '../types/api'

const base = {
  request_id: 'r',
  session_id: 's',
  status: 'SUCCESS' as const,
  provider: 'gemini',
  model: 'gemini-3.8-flash',
  strategy: 'governed' as const,
  answer: {
    direct_answer: 'x',
    executive_summary: 'x',
    insights: [],
    business_implications: [],
    caveats: [],
    data_reference: '',
    chart_spec: null,
  },
  data: { columns: [], rows: [], row_count: 0, execution_ms: 0 },
  chart_spec: null,
  timings: { total_ms: 35714 },
  retry_count: 0,
} satisfies ChatResponse

describe('responseMetadata', () => {
  it('formats human-readable metadata without model id or raw ms', () => {
    expect(formatResponseMetadata(base)).toBe('Gemini · Governed · 36s')
  })

  it('formats sub-10s durations with one decimal', () => {
    expect(formatDurationSeconds(8200)).toBe('8.2s')
  })
})
