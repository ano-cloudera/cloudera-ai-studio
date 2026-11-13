import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ReportDocumentSection } from './ReportDocumentSection'
import type { ChatResponse } from '../types/api'

function response(rowCount: number): ChatResponse {
  const rows = Array.from({ length: rowCount }, (_, index) => ({
    region: `Region ${index + 1}`,
    metric_value: 30 - index,
  }))
  return {
    request_id: 'r1',
    status: 'SUCCESS',
    strategy: 'agent',
    language: 'en',
    answer: {
      direct_answer: 'Region 1 has the highest rate.',
      executive_summary: 'The gap is concentrated in the first two regions.',
      insights: ['Chat finding one', 'Chat finding two', 'Workspace finding three'],
      business_implications: ['Check the process used in Region 1.'],
      caveats: [],
      data_reference: 'governed_result',
      follow_up_questions: [],
      chart_spec: null,
    },
    chart_spec: { type: 'bar', x: 'region', y: 'metric_value', title: 'Rate by region' },
    data: {
      columns: ['region', 'metric_value'],
      rows,
      row_count: rows.length,
      governed_metric: 'Rate',
    },
    governed_sql: 'SELECT region, metric_value FROM governed_result',
  } as unknown as ChatResponse
}

describe('Analysis workspace summary', () => {
  afterEach(cleanup)

  it('shows only findings that were not already presented in chat', () => {
    render(<ReportDocumentSection response={response(14)} chatNarrativeShown chatInsightCount={2} chartShownInChat />)

    expect(screen.queryByText('Region 1 has the highest rate.')).toBeNull()
    expect(screen.queryByText('The gap is concentrated in the first two regions.')).toBeNull()
    expect(screen.queryByText('Chat finding one')).toBeNull()
    expect(screen.queryByText('Chat finding two')).toBeNull()
    expect(screen.getByText('Workspace finding three')).toBeTruthy()
    expect(screen.queryByText('Rate by region')).toBeNull()
  })

  it('keeps the chart in its own tab of the workspace, larger than in the chat', () => {
    render(<ReportDocumentSection response={response(16)} chatInsightCount={2} chartShownInChat={false} />)

    fireEvent.click(screen.getByRole('tab', { name: 'Chart' }))
    expect(screen.getByTestId('workspace-chart').textContent).toContain('Rate by region')
  })

  it('opens on the agent full analysis, which is not the chat summary', () => {
    const agent = { ...response(8), analysis_report: '### Where it concentrates\n\nRegion 1 and Region 2 carry most of it.' } as ChatResponse
    render(<ReportDocumentSection response={agent} chatNarrativeShown chatInsightCount={2} chartShownInChat />)
    expect(screen.getByRole('tab', { name: 'Analysis' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByTestId('analysis-report').textContent).toContain('Region 1 and Region 2 carry most of it.')
    expect(screen.queryByText('The gap is concentrated in the first two regions.')).toBeNull() // that is the chat's
  })

  it('opens on the LLM-written analysis of a governed breakdown, not on a table the Table tab already has', () => {
    const governed = {
      ...response(8),
      strategy: 'governed',
      answer: { ...response(8).answer, insights: [], business_implications: [] },
      analysis_report: '### Cara membacanya\n\nTiga dari delapan regional berada di atas nilai keseluruhan.',
    } as ChatResponse
    render(<ReportDocumentSection response={governed} chatNarrativeShown chatInsightCount={2} chartShownInChat />)
    expect(screen.getByRole('tab', { name: 'Analysis' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByTestId('analysis-report').textContent).toContain('Tiga dari delapan regional')
    expect(screen.queryByTestId('group-standings')).toBeNull()
  })

  it('puts the steps of an agent answer in the Query tab, numbered once, with no separate Checks tab', () => {
    const agent = {
      ...response(8),
      agent_steps: [
        { title: 'Late rate per regional', tool: 'query_metric', status: 'ok', row_count: 8, sql: 'SELECT regional FROM t' },
        { title: 'SOP thresholds', tool: 'search_documents', status: 'ok', row_count: 2, sources: [{ file: 'SOP.pdf', page: 2 }] },
      ],
      calculation: { summary: 'x', metric: 'Late rate', formula: null, breakdown: [], period: null, filters: [], source: [], comparison: null, steps: ['1. Data: late rate - by regional', '2. Documents: SOP'], checks: [], scope: null },
    } as unknown as ChatResponse
    render(<ReportDocumentSection response={agent} chatNarrativeShown chatInsightCount={2} chartShownInChat />)
    expect(screen.queryByRole('tab', { name: 'Checks' })).toBeNull()
    fireEvent.click(screen.getByRole('tab', { name: 'Query' }))
    const steps = screen.getByTestId('query-steps')
    expect(steps.textContent).toContain('Late rate per regional')
    expect(steps.textContent).toContain('The agent ran 2 steps')
    expect(screen.getByText('SQL of the chart shown')).toBeTruthy()
    expect(document.body.textContent).not.toContain('1. Data: late rate') // the plain list is replaced by the cards, so no "1. 1."
  })

  it('leaves the Analysis tab out when the chat already said everything, and opens on the table', () => {
    const plain = { ...response(3), strategy: 'governed', answer: { ...response(3).answer, insights: ['a', 'b'], business_implications: [] } } as unknown as ChatResponse
    render(<ReportDocumentSection response={plain} chatNarrativeShown chatInsightCount={2} chartShownInChat />)
    expect(screen.queryByRole('tab', { name: 'Analysis' })).toBeNull()
    expect(screen.getByRole('tab', { name: 'Table' }).getAttribute('aria-selected')).toBe('true')
    fireEvent.click(screen.getByRole('tab', { name: 'Query' }))
    expect(screen.getByRole('tab', { name: 'Query' }).getAttribute('aria-selected')).toBe('true')
  })
})
