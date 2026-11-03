import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RetrievalPipelineCard, describeEmbedding, describeReranker, shortModelName } from './RetrievalPipelineCard'

describe('descriptions', () => {
  it('shortens paths and says what the reranker does', () => {
    expect(shortModelName('/home/cdsw/models/bge-m3/')).toBe('bge-m3')
    expect(describeEmbedding({ status: 'ready', provider: 'bge_m3', model: '/home/cdsw/models/bge-m3', dimension: 1024 })).toBe('bge_m3 · bge-m3 · 1024 dimensions')
    expect(describeReranker({ status: 'ready', provider: 'none' })).toContain('Not used')
    expect(describeReranker({ status: 'ready', provider: 'bge', model: '/home/cdsw/models/bge-reranker-v2-m3' })).toBe('bge · bge-reranker-v2-m3')
    expect(describeReranker(null)).toBe('Not reported')
  })
})

describe('RetrievalPipelineCard', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows what the Backend reports, also when it answers 503', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ components: { embeddings: { status: 'ready', provider: 'bge_m3', model: '/m/bge-m3', dimension: 1024 }, reranker: { status: 'ready', provider: 'none' } } }),
    }))
    render(<RetrievalPipelineCard />)
    await waitFor(() => expect(screen.getByText('bge_m3 · bge-m3 · 1024 dimensions')).toBeTruthy())
    expect(screen.getByText(/Not used: results are ordered by vector score/)).toBeTruthy()
    expect(screen.queryByRole('combobox')).toBeNull() // nothing to edit here
  })

  it('says so when the Backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<RetrievalPipelineCard />)
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('did not report'))
  })
})
