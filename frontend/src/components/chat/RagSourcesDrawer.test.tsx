import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RagSourcesDrawer } from './RagSourcesDrawer'
import type { ChatResponse } from '../../types/api'

function ragResponse(): ChatResponse {
  return {
    request_id: 'r1',
    session_id: 's1',
    status: 'SUCCESS',
    provider: 'gemini',
    model: 'm',
    strategy: 'rag',
    route: 'rag',
    answer: {
      direct_answer: 'Grounded.',
      executive_summary: 'Grounded.',
      insights: [],
      business_implications: [],
      caveats: [],
      data_reference: '',
    },
    data: { columns: [], rows: [], row_count: 0, execution_ms: 0 },
    timings: { context_ms: 0, planning_ms: 0, validation_ms: 0, query_ms: 0, analysis_ms: 0, total_ms: 0 },
    retry_count: 0,
    citations: [
      {
        chunk_id: 'c1',
        document_id: 'd1',
        filename: 'policy.txt',
        page_number: 2,
        snippet: 'Reimbursement limit is documented.',
        score: 0.9,
      },
    ],
  }
}

describe('RagSourcesDrawer', () => {
  afterEach(cleanup)

  it('links a PDF source to the original at the cited page and tidies a mid-word snippet', () => {
    const response = ragResponse()
    response.citations = [
      {
        chunk_id: 'c2',
        document_id: 'doc-9',
        filename: 'Credit approval policy.pdf',
        page_number: 2,
        snippet: 'ult affordability metric.   Investigation is triggered only when the rate is above 15 percent.',
        score: 0.8,
      },
    ]
    render(<RagSourcesDrawer open response={response} onClose={vi.fn()} />)
    const link = screen.getByRole('link', { name: /Open PDF at page 2/ })
    expect(link.getAttribute('href')).toBe('/api/v1/documents/doc-9/file#page=2')
    expect(link.getAttribute('target')).toBe('_blank')
    expect(screen.getByText(/^\u2026affordability metric\./)).toBeTruthy()
  })

  it('offers no preview link for a non-PDF source', () => {
    render(<RagSourcesDrawer open response={ragResponse()} onClose={vi.fn()} />)
    expect(screen.queryByRole('link', { name: /Open PDF/ })).toBeNull()
  })

  it('renders citation filename and snippet without storage paths', () => {
    render(<RagSourcesDrawer open response={ragResponse()} onClose={vi.fn()} />)
    expect(screen.getByTestId('rag-sources-drawer')).toBeTruthy()
    expect(screen.getByText(/policy\.txt/)).toBeTruthy()
    expect(screen.getByText(/Reimbursement limit/)).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Close'))
  })
})
