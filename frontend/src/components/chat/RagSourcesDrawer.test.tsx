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

  it('renders citation filename and snippet without storage paths', () => {
    render(<RagSourcesDrawer open response={ragResponse()} onClose={vi.fn()} />)
    expect(screen.getByTestId('rag-sources-drawer')).toBeTruthy()
    expect(screen.getByText(/policy\.txt/)).toBeTruthy()
    expect(screen.getByText(/Reimbursement limit/)).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Close'))
  })
})
