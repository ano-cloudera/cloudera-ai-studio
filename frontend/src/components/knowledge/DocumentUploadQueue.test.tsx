import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DocumentUploadQueue } from './DocumentUploadQueue'

describe('DocumentUploadQueue', () => {
  afterEach(cleanup)

  it('renders per-file statuses and summary', () => {
    render(
      <DocumentUploadQueue
        items={[
          { id: '1', name: 'policy.pdf', status: 'READY' },
          { id: '2', name: 'notes.txt', status: 'PROCESSING' },
          { id: '3', name: 'bad.exe', status: 'FAILED', error: 'Unsupported' },
        ]}
        onRetry={vi.fn()}
        onRemove={vi.fn()}
      />,
    )
    expect(screen.getByText(/1 \/ 3 ready/)).toBeTruthy()
    expect(screen.getByText('policy.pdf')).toBeTruthy()
    expect(screen.getByText('Retry')).toBeTruthy()
  })
})
