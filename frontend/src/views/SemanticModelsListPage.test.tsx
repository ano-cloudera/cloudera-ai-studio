import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SemanticModelsListPage, deletionNotice, displayModelName, isPublished, modelStatus, showKey } from './SemanticModelsListPage'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }), usePathname: () => '/', useSearchParams: () => new URLSearchParams() }))
vi.mock('../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn(),
    getSemanticModelOverview: vi.fn(),
    deleteSemanticModel: vi.fn(),
    getAskDataSettings: vi.fn(),
    putAskDataSettings: vi.fn(),
    listConnectors: vi.fn(),
  },
}))
vi.mock('./semantic/CreateSemanticModelWizard', () => ({
  CreateSemanticModelWizard: ({ open, onCreated }: { open: boolean; onCreated: (id: string) => void }) =>
    open ? <button onClick={() => onCreated('new-id')}>wizard-finish</button> : null,
}))

function menu(name: string, item: string) {
  fireEvent.click(screen.getByLabelText(`More actions for ${name}`))
  fireEvent.click(screen.getByRole('menuitem', { name: item }))
}

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

describe('names', () => {
  it('shows a key-like name as words and hides a key that adds nothing', () => {
    expect(displayModelName('fulfillment_delivery')).toBe('Fulfillment Delivery')
    expect(displayModelName('credit-risk')).toBe('Credit Risk')
    expect(displayModelName('Commercial Sales')).toBe('Commercial Sales')
    expect(displayModelName('Fulfillment')).toBe('Fulfillment')
    expect(showKey({ name: 'fulfillment_delivery', key: 'fulfillment_delivery' })).toBe(false)
    expect(showKey({ name: 'Fulfillment Delivery', key: 'fulfillment_delivery' })).toBe(false)
    expect(showKey({ name: 'Fulfillment', key: 'fulfil_v2' })).toBe(true)
  })
})

describe('helpers', () => {
  it('names the status of a model', () => {
    expect(modelStatus(null).tone).toBe('unknown')
    expect(modelStatus(overview(2, null) as never).label).toBe('Published v2')
    expect(modelStatus(overview(2, 3) as never).label).toBe('Published v2 · draft v3 open')
    expect(modelStatus(overview(null, 1) as never).label).toBe('Draft v1, not published')
    expect(modelStatus(overview(null, 1, { entities: 0, metrics: 0, dimensions: 0, relationships: 0, terms: 0 }) as never)).toEqual({ label: 'Draft v1, empty', tone: 'empty' })
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
    vi.mocked(api.getAskDataSettings).mockResolvedValue({ settings: { default_semantic_model_id: 'm1', auto_attach_semantic_model: true, starter_questions: ['Q'] } } as never)
    vi.mocked(api.putAskDataSettings).mockResolvedValue({} as never)
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
    menu('Scratch', 'Delete')
    expect(push).not.toHaveBeenCalled() // the menu does not open the row
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.deleteSemanticModel).toHaveBeenCalledWith('m2', false))
    await waitFor(() => expect(screen.getAllByTestId('semantic-model-row')).toHaveLength(1))
    expect(screen.getByRole('status').textContent).toContain('Deleted')
  })

  it('makes the user type the key before a published model goes away', async () => {
    const { api } = await import('../lib/api')
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    menu('Fulfillment', 'Delete')
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
    menu('Scratch', 'Delete')
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

describe('Set as default', () => {
  afterEach(cleanup)

  async function setup(defaultId: string | null) {
    const { api } = await import('../lib/api')
    vi.mocked(api.listSemanticModels).mockResolvedValue({ models: [model('m1', 'Fulfillment', 'v1'), model('m2', 'Scratch'), model('m3', 'Other', 'v3')] } as never)
    vi.mocked(api.getSemanticModelOverview).mockImplementation((async (id: string) => (id === 'm2' ? overview(null, 1) : overview(1, null))) as never)
    vi.mocked(api.getAskDataSettings).mockResolvedValue({ settings: { default_semantic_model_id: defaultId, auto_attach_semantic_model: false, starter_questions: ['Q'] } } as never)
    vi.mocked(api.putAskDataSettings).mockResolvedValue({} as never)
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [] } as never)
    return api
  }

  it('is offered only for published models that are not already the default', async () => {
    await setup('m1')
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    const offered = (name: string) => {
      fireEvent.click(screen.getByLabelText(`More actions for ${name}`))
      const found = screen.queryByRole('menuitem', { name: 'Set as default' }) !== null
      fireEvent.click(screen.getByLabelText(`More actions for ${name}`)) // close it again
      return found
    }
    expect(offered('Fulfillment')).toBe(false) // already the default
    expect(offered('Scratch')).toBe(false) // not published
    expect(offered('Other')).toBe(true)
    expect(isPublished({ model: model('x', 'X') as never, overview: overview(null, 1) as never })).toBe(false)
  })

  it('keeps the other settings, switches auto-attach on and moves the badge', async () => {
    const api = await setup('m1')
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    menu('Other', 'Set as default')
    await waitFor(() => expect(api.putAskDataSettings).toHaveBeenCalledWith({ default_semantic_model_id: 'm3', auto_attach_semantic_model: true, starter_questions: ['Q'] }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('“Other” is now the default model'))
    const rows = screen.getAllByTestId('semantic-model-row')
    expect(within(rows[2]).getByText('Default for Ask Data')).toBeTruthy()
    expect(within(rows[0]).queryByText('Default for Ask Data')).toBeNull()
    fireEvent.click(screen.getByLabelText('More actions for Fulfillment'))
    expect(screen.getByRole('menuitem', { name: 'Set as default' })).toBeTruthy() // the old default can be chosen again
  })

  it('says so when saving fails and leaves the badge where it was', async () => {
    const api = await setup('m1')
    vi.mocked(api.putAskDataSettings).mockRejectedValue(new Error('no write access'))
    render(<SemanticModelsListPage />)
    await screen.findAllByTestId('semantic-model-row')
    menu('Other', 'Set as default')
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('no write access'))
    expect(within(screen.getAllByTestId('semantic-model-row')[0]).getByText('Default for Ask Data')).toBeTruthy()
  })
})

describe('table layout', () => {
  afterEach(cleanup)

  it('ends every row with Open and a menu, under the same header style as Data Sources', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listSemanticModels).mockResolvedValue({ models: [model('m1', 'fulfillment_delivery', 'v1')] } as never)
    vi.mocked(api.getSemanticModelOverview).mockResolvedValue(overview(1, null) as never)
    vi.mocked(api.getAskDataSettings).mockResolvedValue({ settings: { default_semantic_model_id: null } } as never)
    vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [] } as never)
    push.mockClear()
    const { container } = render(<SemanticModelsListPage />)
    const row = await screen.findByTestId('semantic-model-row')
    expect(within(row).getByText('Fulfillment Delivery')).toBeTruthy() // no underscore
    expect(within(row).queryByText('fulfillment_delivery')).toBeNull() // and the key is not repeated
    expect(container.querySelector('thead.app-table-head')).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeTruthy()
    fireEvent.click(within(row).getByRole('button', { name: 'Open Fulfillment Delivery' }))
    expect(push).toHaveBeenCalledWith('/semantic-layer/model?model=m1')
  })

  it('closes the menu when you click elsewhere, and lists the newest model first', async () => {
    const { api } = await import('../lib/api')
    vi.mocked(api.listSemanticModels).mockResolvedValue({ models: [{ ...model('a', 'Older'), updated_at: '2026-01-01T00:00:00Z' }, { ...model('b', 'Newer'), updated_at: '2026-06-01T00:00:00Z' }] } as never)
    vi.mocked(api.getSemanticModelOverview).mockRejectedValue(new Error('no overview')) // the counts fall back to dashes
    render(<SemanticModelsListPage />)
    const rows = await screen.findAllByTestId('semantic-model-row')
    expect(within(rows[0]).getByText('Newer')).toBeTruthy()
    fireEvent.click(within(rows[0]).getByLabelText('More actions for Newer'))
    expect(screen.getByRole('menu')).toBeTruthy()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
  })
})
