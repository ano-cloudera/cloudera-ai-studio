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
  it('formats human-readable metadata without raw ms', () => {
    expect(formatResponseMetadata(base)).toBe('Gemini · Governed · 36s')
  })

  it('names the model assigned in AI Models, not the provider bucket it runs through', () => {
    const viaRegistry = {
      ...base,
      provider: 'qwen',
      model: 'nvidia/nemotron-3-super-120b-a12b',
      timings: { total_ms: 7200 },
      model_resolution: { model_name: 'nvidia/nemotron-3-super-120b-a12b', model_key: 'nemotron_super', provider_name: 'nemotron' },
    } satisfies ChatResponse
    expect(formatResponseMetadata(viaRegistry)).toBe('nemotron-3-super-120b-a12b · Governed · 7.2s')
    expect(formatResponseMetadata({ ...viaRegistry, model_resolution: { model_key: 'qwen3.5-9b' } })).toBe('qwen3.5-9b · Governed · 7.2s')
    expect(formatResponseMetadata({ ...viaRegistry, model_resolution: null })).toBe('Qwen · Governed · 7.2s')
  })

  it('formats sub-10s durations with one decimal', () => {
    expect(formatDurationSeconds(8200)).toBe('8.2s')
  })
})
