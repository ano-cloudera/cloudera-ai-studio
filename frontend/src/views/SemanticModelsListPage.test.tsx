import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SemanticModelsListPage, deletionNotice, modelStatus } from './SemanticModelsListPage'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }), usePathname: () => '/', useSearchParams: () => new URLSearchParams() }))
vi.mock('../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn(),
    getSemanticModelOverview: vi.fn(),
    deleteSemanticModel: vi.fn(),
    getAskDataSettings: vi.fn(),
    listConnectors: vi.fn(),
  },
}))
vi.mock('./semantic/CreateSemanticModelWizard', () => ({
  CreateSemanticModelWizard: ({ open, onCreated }: { open: boolean; onCreated: (id: string) => void }) =>
    open ? <button onClick={() => onCreated('new-id')}>wizard-finish</button> : null,
}))

const model = (id: string, name: string, active: string | null = null) => ({ id, name, key: name.toLowerCase(), description: null, active_version_id: active, created_at: '', updated_at: '2026-11-03T10:00:00Z' })
const overview = (published: number | null, draft: number | null, counts = { entities: 3, metrics: 11, dimensions: 32, relationships: 0, terms: 0 }) => ({
  model: { id: 'x', name: 'x', key: 'x', updated_at: '2026-11-03T10:00:00Z' },
  state: 'Draft',
  readiness: 'READY',
  issue_count: 0,
  published_version_number: published,
  draft_version_number: draft,
  counts,
  ready_to_publish: true,
})

describe('helpers', () => {
  it('names the status of a model', () => {
    expect(modelStatus(null).tone).toBe('unknown')
    expect(modelStatus(overview(2, null) as never).label).toBe('Published v2')
    expect(modelStatus(overview(2, 3) as never).label).toBe('Published v2 · draft v3 open')
    expect(modelStatus(overview(null, 1) as never).label).toBe('Draft v1, not published')
    expect(modelStatus(overview(null, null) as never).label).toBe('Empty')
  })

  it('asks for the key only when the model is published', () => {
    expect(deletionNotice({ model: model('1', 'A') as never, overview: overview(null, 1) as never }).needsTyping).toBe(false)
    expect(deletionNotice({ model: model('1', 'A', 'v') as never, overview: overview(null, 1) as never }).needsTyping).toBe(true)
    expect(deletionNotice({ model: model('1', 'A') as never, overview: overview(2, null) as never }).message).toContain('removes it from Ask Data')
  })
})

describe('SemanticModelsListPage', () => {
  beforeEach(async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listSemanticModels).mockResolvedValue({ models: [model('m1', 'Fulfillment', 'v1'), model('m2', 'Scratch')] } as never)
    vi.mocked(api.getSemanticModelOverview).mockImplementation((async (id: string) => (id === 'm1' ? overview(1, null) : overview(null, 1, { entities: 1, metrics: 0, dimensions: 4, relationships: 0, terms: 0 }))) as never)
    vi.mocked(api.getAskDataSettings).mockResolvedValue({ settings: { default_semantic_model_id: 'm1' } } as never)
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [] } as never)
    vi.mocked(api.deleteSemanticModel).mockResolvedValue({ deleted: true } as never)
    push.mockClear()
  })
  afterEach(cleanup)

  it('lists the models with their status and counts, and opens one on click', async () => {
    render(<SemanticModelsListPage />)
    const rows = await screen.findAllByTestId('semantic-model-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Published v1')).toBeTruthy()
    expect(within(rows[0]).getByText('11')).toBeTruthy()
    expect(within(rows[0]).getByText('Default for Ask Data')).toBeTruthy()
    expect(within(rows[1]).getByText('Draft v1, not published')).toBeTruthy()
    fireEvent.click(rows[1])
    expect(push).toHaveBeenCalledWith('/semantic-layer/model?model=m2')
  })

  it('filters by name or key and says when nothing matches', async () => {
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    fireEvent.change(screen.getByLabelText('Search semantic models'), { target: { value: 'scr' } })
    expect(screen.getAllByTestId('semantic-model-row')).toHaveLength(1)
    fireEvent.change(screen.getByLabelText('Search semantic models'), { target: { value: 'zzz' } })
    expect(screen.getByText('No model matches your search.')).toBeTruthy()
  })

  it('deletes an unpublished model after one confirmation', async () => {
    const { api } = await import('../lib/api')
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    fireEvent.click(screen.getByLabelText('Delete Scratch'))
    expect(push).not.toHaveBeenCalled() // the delete button does not open the row
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.deleteSemanticModel).toHaveBeenCalledWith('m2', false))
    await waitFor(() => expect(screen.getAllByTestId('semantic-model-row')).toHaveLength(1))
    expect(screen.getByRole('status').textContent).toContain('Deleted')
  })

  it('makes the user type the key before a published model goes away', async () => {
    const { api } = await import('../lib/api')
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    fireEvent.click(screen.getByLabelText('Delete Fulfillment'))
    const confirm = screen.getByRole('button', { name: 'Delete and remove from Ask Data' }) as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByRole('textbox', { name: /to confirm/ }), { target: { value: 'wrong' } })
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByRole('textbox', { name: /to confirm/ }), { target: { value: 'fulfillment' } })
    expect(confirm.disabled).toBe(false)
    fireEvent.click(confirm)
    await waitFor(() => expect(api.deleteSemanticModel).toHaveBeenCalledWith('m1', true))
    await waitFor(() => expect(screen.queryByText('Default for Ask Data')).toBeNull()) // no longer the default
  })

  it('shows the reason when a delete fails and keeps the model', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.deleteSemanticModel).mockRejectedValue(new Error('boom'))
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    fireEvent.click(screen.getByLabelText('Delete Scratch'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('boom'))
    expect(screen.getAllByTestId('semantic-model-row')).toHaveLength(2)
  })

  it('shows an empty state, and the wizard opens the new model', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listSemanticModels).mockResolvedValue({ models: [] } as never)
    render(<SemanticModelsListPage />)
    expect(await screen.findByText(/No semantic model yet/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Create semantic model/ }))
    fireEvent.click(screen.getByText('wizard-finish'))
    expect(push).toHaveBeenCalledWith('/semantic-layer/model?model=new-id')
  })
})
