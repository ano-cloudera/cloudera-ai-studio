import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ReportDocumentSection, standingsAgainstOverall } from './ReportDocumentSection'
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

  it('places every group above or below the overall value for a governed breakdown, counted from the rows', () => {
    const regional = { 'Papua Maluku': 34.54, Kalimantan: 29.66, Sulawesi: 19.45, Sumbagut: 15.69, Sumbagsel: 13.88, 'Jawa Bagian Barat': 13.18, 'Jawa Bagian Tengah': 11.84, Jatimbalinus: 11.4 }
    const governed = {
      ...response(0),
      strategy: 'governed',
      answer: { ...response(0).answer, insights: [], business_implications: [] },
      data: { columns: ['regional', 'metric_value'], rows: Object.entries(regional).map(([regional, metric_value]) => ({ regional, metric_value })), row_count: 8, overall_value: 16.07, unit_format: 'percent', governed_metric: 'tingkat_keterlambatan' },
    } as unknown as ChatResponse
    const standings = standingsAgainstOverall(governed)!
    expect(standings.above.map(s => s.group)).toEqual(['Papua Maluku', 'Kalimantan', 'Sulawesi'])
    expect(standings.below).toHaveLength(5) // not "Jatimbalinus is the only one below"
    render(<ReportDocumentSection response={governed} chatNarrativeShown chatInsightCount={2} chartShownInChat />)
    const box = screen.getByTestId('group-standings')
    expect(box.textContent).toContain('Below overall (5 of 8)')
    expect(box.textContent).toContain('+18.47 pts')
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
