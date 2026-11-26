import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CreateSemanticModelWizard } from './CreateSemanticModelWizard'
import { SemanticSuggestionsApplyModal } from './SemanticSuggestionsApplyModal'
import { remapEntityKey, type SuggestionBucket } from './semanticSuggestionsUi'

const api = vi.hoisted(() => ({
  listConnectorSchemas: vi.fn(),
  listConnectorTables: vi.fn(),
  startSemanticDraft: vi.fn(),
  getSemanticDraft: vi.fn(),
  semanticSuggestions: vi.fn(),
  createSemanticModel: vi.fn(),
  acceptSemanticSuggestions: vi.fn(),
}))
vi.mock('../../lib/api', () => ({ api }))

const connectors = [{ id: 'c1', name: 'Warehouse', connector_type: 'trino', status: 'READY' }] as never

const DRAFT: SuggestionBucket = {
  drafted: true,
  provider: 'studio-llm',
  entities: [{ suggestion_id: 'entity:orders', key: 'orders', name: 'Order', schema: 'shop', table_name: 'orders', evidence: { row_count: 400 } }],
  metrics: [
    {
      suggestion_id: 'metric:late_rate',
      key: 'late_rate',
      name: 'Late Rate (%)',
      description: 'Late orders over finished orders.',
      expression: "COUNT(CASE WHEN status = 'Late' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)",
      unit: 'percent',
      better: 'down',
      source_entity_key: 'orders',
      synonyms: ['late share'],
      metadata: { reference_extension: { headline: 1, better: 'down' } },
      evidence: { value: 33.3333, rows: 400, whole_table: true },
    },
  ],
  dimensions: [
    { suggestion_id: 'dimension:status', key: 'status', name: 'Status', source_column: 'status', source_entity_key: 'orders', evidence: { distinct: 3, examples: ['Delivered', 'Late'] } },
  ],
  relationships: [],
  glossary_suggestions: [],
  dropped: [{ type: 'metric', name: 'Lost Revenue', table: 'orders', reason: 'It names a column the table does not have: lost_amount.' }],
  notes: ['orders: profiled on the first 50,000 of 80,000 rows.'],
}

async function toTables() {
  fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'Shop' } })
  fireEvent.change(screen.getByPlaceholderText(/deliveries from our depots/), { target: { value: 'An online shop; amounts in IDR' } })
  fireEvent.change(screen.getByLabelText('Language for names and descriptions'), { target: { value: 'id' } })
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  fireEvent.click(await screen.findByRole('checkbox'))
}

describe('drafting a semantic model with the AI model', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listConnectorSchemas.mockResolvedValue({ schemas: [{ name: 'shop' }] })
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'shop', name: 'orders' }] })
    api.startSemanticDraft.mockResolvedValue({ job_id: 'j1', status: 'running', stage: 'Profiled 1 of 1 table(s)', elapsed_seconds: 1, result: null, error: null })
    api.getSemanticDraft.mockResolvedValue({ job_id: 'j1', status: 'done', stage: 'Done', elapsed_seconds: 9, result: DRAFT, error: null })
  })
  afterEach(cleanup)

  it('sends the language and what the data is about, shows the progress, then the draft with what the data said', async () => {
    render(<CreateSemanticModelWizard open connectors={connectors} onClose={() => undefined} onCreated={() => undefined} />)
    await toTables()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    expect(api.startSemanticDraft).toHaveBeenCalledWith({ connection_id: 'c1', tables: ['shop.orders'], language: 'id', context: 'An online shop; amounts in IDR' })
    expect((await screen.findByTestId('wizard-draft-progress')).textContent).toContain('Profiled 1 of 1 table(s)')

    await waitFor(() => expect(screen.getByTestId('suggestion-review-source').textContent).toContain('studio-llm'), { timeout: 4000 })
    expect(screen.getByTestId('suggestion-metric-value').textContent).toBe('Ran on the data: 33.33% (all 400 rows)')
    expect(screen.getByText('Lower is better')).toBeTruthy()
    expect(screen.getByText('Home overview #1')).toBeTruthy()
    expect(screen.getByText(/3 values · e\.g\. Delivered, Late/)).toBeTruthy()
    expect(screen.getByTestId('suggestion-review-dropped').textContent).toContain('1 suggestion(s) left out by the checks')
    expect(screen.getByTestId('suggestion-review-notes').textContent).toContain('first 50,000 of 80,000 rows')
    expect(api.semanticSuggestions).not.toHaveBeenCalled()
  })

  it('saves an edited description with the rest of the drafted metric', async () => {
    api.createSemanticModel.mockResolvedValue({ model: { id: 'm1', name: 'Shop', key: 'shop' } })
    api.acceptSemanticSuggestions.mockResolvedValue({ version_id: 'v1', persisted: [], conflicts: [], counts: { metrics: 1 } })
    render(<CreateSemanticModelWizard open connectors={connectors} onClose={() => undefined} onCreated={() => undefined} />)
    await toTables()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => screen.getByTestId('suggestion-review-source'), { timeout: 4000 })
    fireEvent.click(screen.getAllByText('Edit')[1]) // the metric
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Share of finished orders that arrived late.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => expect(api.acceptSemanticSuggestions).toHaveBeenCalled())
    const metric = api.acceptSemanticSuggestions.mock.calls[0][1].selections.find((s: { suggestion_id: string }) => s.suggestion_id === 'metric:late_rate')
    expect(metric.payload.description).toBe('Share of finished orders that arrived late.')
    expect(metric.payload.business_definition).toBe('Share of finished orders that arrived late.')
    expect(metric.payload.metadata).toEqual({ reference_extension: { headline: 1, better: 'down' } })
    expect(metric.payload.unit).toBe('percent')
  })

  it('shows why a draft failed', async () => {
    api.getSemanticDraft.mockResolvedValue({ job_id: 'j1', status: 'failed', stage: 'Drafting', elapsed_seconds: 3, result: null, error: 'shop.orders: Table not found' })
    render(<CreateSemanticModelWizard open connectors={connectors} onClose={() => undefined} onCreated={() => undefined} />)
    await toTables()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => expect(screen.getByText('shop.orders: Table not found')).toBeTruthy(), { timeout: 4000 })
  })

  it('without an AI model, says so and offers the basic suggestions', async () => {
    api.startSemanticDraft.mockRejectedValue({ code: 'no_model', status: 409, message: 'No AI model', retryable: false })
    api.semanticSuggestions.mockResolvedValue({ metrics: [{ suggestion_id: 'metric:total', key: 'total', name: 'Total' }] })
    render(<CreateSemanticModelWizard open connectors={connectors} onClose={() => undefined} onCreated={() => undefined} />)
    await toTables()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    expect((await screen.findByTestId('suggestion-review-basic')).textContent).toContain('No AI model is available')
    expect(screen.getByText('Total')).toBeTruthy()
  })
})

describe('the suggestions after importing one table', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.startSemanticDraft.mockResolvedValue({ job_id: 'j2', status: 'done', stage: 'Done', elapsed_seconds: 5, result: DRAFT, error: null })
    api.acceptSemanticSuggestions.mockResolvedValue({ version_id: 'v1', persisted: [], conflicts: [], counts: {} })
  })
  afterEach(cleanup)

  it('points the draft at the key the table was imported under', async () => {
    render(
      <SemanticSuggestionsApplyModal open modelId="m1" versionId="v1" connectionId="c1" tables={['shop.orders']} entityKey="sales_orders" onClose={() => undefined} onApplied={() => undefined} />,
    )
    await screen.findByTestId('suggestion-review')
    expect(screen.queryByText('Data Models')).toBeNull() // the data model already exists
    fireEvent.click(screen.getByRole('button', { name: 'Apply selected' }))
    await waitFor(() => expect(api.acceptSemanticSuggestions).toHaveBeenCalled())
    const selections = api.acceptSemanticSuggestions.mock.calls[0][1].selections as Array<{ type: string; accepted: boolean; payload: Record<string, unknown> }>
    expect(selections.find(s => s.type === 'metric')?.payload.source_entity_key).toBe('sales_orders')
    expect(selections.find(s => s.type === 'dimension')?.payload.source_entity_key).toBe('sales_orders')
    expect(selections.find(s => s.type === 'entity')?.accepted).toBe(false)
  })
})

describe('remapEntityKey', () => {
  it('moves every reference to the imported key, and leaves other tables alone', () => {
    const bucket: SuggestionBucket = {
      entities: [{ suggestion_id: 'entity:orders', key: 'orders' }, { suggestion_id: 'entity:customers', key: 'customers' }],
      relationships: [{ from_entity_key: 'orders', to_entity_key: 'customers', join_expression: 'orders.customer_code = customers.customer_code' }],
    }
    const out = remapEntityKey(bucket, 'orders', 'sales_orders')
    expect(out.entities?.map(e => e.key)).toEqual(['sales_orders', 'customers'])
    expect(out.relationships?.[0]).toMatchObject({ from_entity_key: 'sales_orders', to_entity_key: 'customers', join_expression: 'sales_orders.customer_code = customers.customer_code' })
  })
})
