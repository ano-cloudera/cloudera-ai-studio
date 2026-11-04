import { describe, expect, it } from 'vitest'

import type { ChatResponse } from '../types/api'
import { assistantChartNode, conversationPdfFilename, downloadConversationPdf } from './chatPdfExport'
import type { StoredMessage } from './chatSessions'

describe('chatPdfExport', () => {
  it('builds a safe pdf filename from the session title', () => {
    expect(conversationPdfFilename('Top sell-in Q4?')).toMatch(/^ai-studio-Top-sell-in-Q4-\d{4}-\d{2}-\d{2}\.pdf$/)
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

describe('chart pairing', () => {
  const answer = (id: string, drawsChart: boolean) =>
    ({
      request_id: id,
      chart_spec: drawsChart ? { type: 'bar', x: 'a', y: 'b', title: 't' } : { type: 'bar', x: 'a', y: 'b', title: 't' },
      data: { rows: [{ a: 1, b: 2 }] },
    }) as unknown as ChatResponse
  const node = (id: string) => {
    const el = document.createElement('div')
    el.setAttribute('data-pdf-export-chart', id)
    return el
  }

  it('pairs a chart with its own answer even when an earlier answer drew none', () => {
    const nodes = [node('r6'), node('r14')] // r3 has a chart spec but nothing was drawn for it on screen
    expect(assistantChartNode(answer('r3', true), nodes, 0)).toBeNull()
    expect(assistantChartNode(answer('r6', true), nodes, 0)).toBe(nodes[0])
    expect(assistantChartNode(answer('r14', true), nodes, 1)).toBe(nodes[1])
  })

  it('falls back to the order of the charts when none of them carries an id', () => {
    const nodes = [node(''), node('')]
    expect(assistantChartNode(answer('x', true), nodes, 1)).toBe(nodes[1])
  })
})
