import { describe, expect, it } from 'vitest'

import type { ChatResponse } from '../types/api'
import { conversationPdfFilename, downloadConversationPdf } from './chatPdfExport'
import type { StoredMessage } from './chatSessions'

describe('chatPdfExport', () => {
  it('builds a safe pdf filename from the session title', () => {
    expect(conversationPdfFilename('Top sell-in Q4?')).toMatch(/^tempo-scan-Top-sell-in-Q4-\d{4}-\d{2}-\d{2}\.pdf$/)
  })

  it('generates a PDF for a governed answer with a data table without throwing', async () => {
    const response: ChatResponse = {
      request_id: 'r1',
      session_id: 's1',
      status: 'SUCCESS',
      provider: 'gemini',
      model: 'm',
      strategy: 'governed',
      answer: {
        direct_answer: 'Material A leads sell-in.',
        executive_summary: 'Summary line.',
        insights: ['Insight one'],
        business_implications: [],
        caveats: ['Q4 2024 only'],
        data_reference: 'gold.rpt_sap_material_month_semantic',
        chart_spec: null,
      },
      data: {
        columns: ['material', 'metric_value'],
        rows: [
          { material: '001-00-03', metric_value: 100 },
          { material: '002-00-01', metric_value: 80 },
        ],
        row_count: 2,
        execution_ms: 12,
      },
      chart_spec: null,
      timings: { total_ms: 50 },
      retry_count: 0,
    }

    const messages: StoredMessage[] = [
      { role: 'user', content: 'Top material sell-in?' },
      { role: 'assistant', content: '', response },
    ]

    await expect(
      downloadConversationPdf({ title: 'Top material sell-in?', messages, appName: 'Test App' }),
    ).resolves.toBeUndefined()
  })
})
