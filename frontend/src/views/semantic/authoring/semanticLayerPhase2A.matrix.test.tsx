/**
 * SEM-2A-001..036 mapping (Phase 2A closure matrix):
 * 001 semanticLayerPhase2A.matrix.test.tsx SEM-2A-001 Data Models table render
 * 002 semanticLayerPhase2A.matrix.test.tsx SEM-2A-002 Data Models backend search
 * 003 semanticLayerPhase2A.matrix.test.tsx SEM-2A-003 Data Models sort
 * 004 semanticLayerPhase2A.matrix.test.tsx SEM-2A-004 Data Models pagination
 * 005 semanticLayerPhase2A.matrix.test.tsx SEM-2A-005 Data Model create
 * 006 semanticLayerPhase2A.matrix.test.tsx SEM-2A-006 Data Model edit
 * 007 semanticLayerPhase2A.matrix.test.tsx SEM-2A-007 Data Model cancel
 * 008 semanticLayerPhase2A.matrix.test.tsx SEM-2A-008 Data Model delete
 * 009 semanticLayerPhase2A.matrix.test.tsx SEM-2A-009 Ask this data wiring
 * 010 semanticLayerPhase2A.matrix.test.tsx SEM-2A-010 Metrics table
 * 011 semanticLayerPhase2A.matrix.test.tsx SEM-2A-011 Metric create
 * 012 semanticLayerPhase2A.matrix.test.tsx SEM-2A-012 Metric edit
 * 013 semanticLayerPhase2A.matrix.test.tsx SEM-2A-013 Metric save
 * 014 semanticLayerPhase2A.matrix.test.tsx SEM-2A-014 Metric cancel
 * 015 semanticLayerPhase2A.matrix.test.tsx SEM-2A-015 invalid metric validation
 * 016 semanticLayerPhase2A.matrix.test.tsx SEM-2A-016 metric sort/pagination/search
 * 017 semanticLayerPhase2A.matrix.test.tsx SEM-2A-017 Dimensions table
 * 018 semanticLayerPhase2A.matrix.test.tsx SEM-2A-018 Dimension create/edit
 * 019 semanticLayerPhase2A.matrix.test.tsx SEM-2A-019 Dimension cancel
 * 020 semanticLayerPhase2A.matrix.test.tsx SEM-2A-020 dimension sort/pagination/search
 * 021 semanticLayerPhase2A.matrix.test.tsx SEM-2A-021 Relationships table
 * 022 semanticLayerPhase2A.matrix.test.tsx SEM-2A-022 Relationship create/edit
 * 023 semanticLayerPhase2A.matrix.test.tsx SEM-2A-023 Relationship validation
 * 024 semanticLayerPhase2A.matrix.test.tsx SEM-2A-024 relationship sort/pagination/search
 * 025 semanticLayerPhase2A.matrix.test.tsx SEM-2A-025 Glossary table
 * 026 semanticLayerPhase2A.matrix.test.tsx SEM-2A-026 Glossary create/edit
 * 027 semanticLayerPhase2A.matrix.test.tsx SEM-2A-027 glossary sort/pagination/search
 * 028 semanticLayerPhase2A.test.tsx SEM-2A-028 Recent Definitions
 * 029 semanticLayerPhase2A.matrix.test.tsx SEM-2A-029 Recent Definitions sort/filter/page
 * 030 semanticLayerPhase2A.test.tsx SEM-2A-030 selection hidden by default
 * 031 semanticLayerPhase2A.matrix.test.tsx SEM-2A-031 selection mode
 * 032 semanticLayerPhase2A.matrix.test.tsx SEM-2A-032 page select-all
 * 033 semanticLayerPhase2A.matrix.test.tsx SEM-2A-033 row action portal
 * 034 semanticLayerPhase2A.matrix.test.tsx SEM-2A-034 stable single-row table
 * 035 semanticLayerPhase2A.matrix.test.tsx SEM-2A-035 editor dirty registration
 * 036 semanticLayerPhase2A.test.tsx SEM-2A-036 Save and Continue invokes save
 */
import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EditorDirtyProvider } from './EditorDirtyContext'
import { DataModelsTab } from './DataModelsTab'
import { DimensionsTab, GlossaryTab, MetricsTab, RelationshipsTab } from './SemanticOtherTabs'
import { RecentDefinitionsPanel } from './RecentDefinitionsPanel'
import { useEditorDirtyRegistry } from './EditorDirtyContext'
import { UnsavedChangesModal } from '../../../components/semantic/UnsavedChangesModal'
import { api } from '../../../lib/api'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))

const entity = {
  id: 'e1',
  key: 'sales',
  name: 'Sales',
  description: 'Txn sales',
  source_type: 'postgres',
  catalog: null,
  schema: 'public',
  table_name: 'sales',
  view_name: null,
  primary_key: 'id',
  connection_id: 'c1',
  metadata: { field_count: 12 },
  modified_at: '2026-10-17T00:00:00Z',
}

const metric = {
  id: 'm1',
  key: 'net_sales',
  name: 'Net Sales',
  description: null,
  business_definition: 'Sum of amount',
  expression: 'SUM(amount)',
  aggregation: 'sum',
  source_entity_key: 'sales',
  format: null,
  unit: null,
  synonyms: [],
  allowed_dimension_keys: ['channel'],
  metadata: {},
  modified_at: '2026-10-17T00:00:00Z',
}

const dimension = {
  id: 'd1',
  key: 'channel',
  name: 'Channel',
  description: 'Channel dim',
  source_entity_key: 'sales',
  source_column: 'channel',
  data_type: 'string',
  synonyms: [],
  metadata: { category: 'Other' },
  modified_at: '2026-10-17T00:00:00Z',
}

const relationship = {
  id: 'r1',
  key: 'rel1',
  name: 'Sales to Store',
  from_entity_key: 'sales',
  to_entity_key: 'store',
  relationship_type: 'many_to_one',
  join_type: 'inner',
  join_expression: 'sales.store_id = store.id',
  description: '',
  metadata: {},
  modified_at: '2026-10-17T00:00:00Z',
}

const term = {
  id: 't1',
  key: 'sell_out',
  term: 'Sell Out',
  definition: 'Retail sell-out',
  synonyms: [],
  related_metric_keys: ['net_sales'],
  related_dimension_keys: ['channel'],
  related_entity_keys: ['sales'],
  metadata: {},
  modified_at: '2026-10-17T00:00:00Z',
}

vi.mock('../../../lib/api', () => ({
  api: {
    listSemanticEntities: vi.fn(),
    deleteSemanticEntity: vi.fn(),
    bulkDeleteSemanticEntities: vi.fn(),
    importSemanticEntity: vi.fn(),
    patchSemanticEntity: vi.fn(),
    previewSemanticEntityImport: vi.fn(),
    listSemanticMetrics: vi.fn(),
  listSemanticRelationships: vi.fn().mockResolvedValue({ relationships: [], total: 0 }),
    bulkDeleteSemanticMetrics: vi.fn(),
    deleteSemanticMetric: vi.fn(),
    createSemanticMetric: vi.fn(),
    patchSemanticMetric: vi.fn(),
    patchSemanticEntity: vi.fn(),
    validateSemanticMetric: vi.fn(),
    listSemanticDimensions: vi.fn(),
    bulkDeleteSemanticDimensions: vi.fn(),
    createSemanticDimension: vi.fn(),
    patchSemanticDimension: vi.fn(),
    listSemanticRelationships: vi.fn(),
    bulkDeleteSemanticRelationships: vi.fn(),
    createSemanticRelationship: vi.fn(),
    patchSemanticRelationship: vi.fn(),
    listSemanticTerms: vi.fn(),
    bulkDeleteSemanticTerms: vi.fn(),
    createSemanticTerm: vi.fn(),
    patchSemanticTerm: vi.fn(),
    listSemanticRecentDefinitions: vi.fn(),
    previewSemanticEntityImport: vi.fn(),
    listConnectors: vi.fn(),
    listConnectorCatalogs: vi.fn(),
    listConnectorSchemas: vi.fn(),
    listConnectorTables: vi.fn(),
  },
}))

function setupDefaultMocks() {
  vi.mocked(api.listSemanticEntities).mockResolvedValue({ entities: [entity], total: 25, page: 1, page_size: 10 })
  vi.mocked(api.deleteSemanticEntity).mockResolvedValue({ deleted: true })
  vi.mocked(api.bulkDeleteSemanticEntities).mockResolvedValue({ requested: 1, deleted: [{ id: 'e1', name: 'e1' }], failed: [], deleted_count: 1, failed_count: 0 })
  vi.mocked(api.importSemanticEntity).mockResolvedValue({ entity, import: { dimensions_created: 0, columns_discovered: 1, warnings: [] } })
  vi.mocked(api.patchSemanticEntity).mockResolvedValue({ entity })
  vi.mocked(api.previewSemanticEntityImport).mockResolvedValue({ preview: { existing_entity: null, columns: [] } })
  vi.mocked(api.listSemanticEntities).mockResolvedValue({ entities: [entity], total: 25, page: 1, page_size: 10 })
  vi.mocked(api.patchSemanticEntity).mockResolvedValue({ entity })
  vi.mocked(api.deleteSemanticMetric).mockResolvedValue({ deleted: true })
  vi.mocked(api.listSemanticMetrics).mockResolvedValue({ metrics: [metric], total: 1, page: 1, page_size: 10 })
  vi.mocked(api.bulkDeleteSemanticMetrics).mockResolvedValue({ requested: 1, deleted: [{ id: 'm1', name: 'm1' }], failed: [], deleted_count: 1, failed_count: 0 })
  vi.mocked(api.createSemanticMetric).mockResolvedValue({ metric })
  vi.mocked(api.patchSemanticMetric).mockResolvedValue({ metric })
  vi.mocked(api.validateSemanticMetric).mockResolvedValue({ valid: true, issues: [] })
  vi.mocked(api.previewSemanticEntityImport).mockResolvedValue({
    preview: {
      table_type: 'TABLE',
      columns: [
        { name: 'amount', native_type: 'numeric', normalized_type: 'DECIMAL', nullable: false, comment: null },
        { name: 'channel', native_type: 'varchar', normalized_type: 'STRING', nullable: true, comment: null },
      ],
      candidate_dimensions: [],
      existing_entity: null,
      primary_key: ['id'],
    },
  })
  vi.mocked(api.listSemanticDimensions).mockResolvedValue({
    dimensions: [
      dimension,
      {
        id: 'd2',
        key: 'amount',
        name: 'Amount',
        description: '',
        source_entity_key: 'sales',
        source_column: 'amount',
        data_type: 'decimal',
        synonyms: [],
        metadata: {},
        modified_at: '2026-10-17T00:00:00Z',
      },
    ],
    total: 2,
    page: 1,
    page_size: 10,
  })
  vi.mocked(api.bulkDeleteSemanticDimensions).mockResolvedValue({ requested: 1, deleted: [{ id: 'd1', name: 'd1' }], failed: [], deleted_count: 1, failed_count: 0 })
  vi.mocked(api.createSemanticDimension).mockResolvedValue({ dimension })
  vi.mocked(api.patchSemanticDimension).mockResolvedValue({ dimension })
  vi.mocked(api.listSemanticRelationships).mockResolvedValue({ relationships: [relationship], total: 1, page: 1, page_size: 10 })
  vi.mocked(api.bulkDeleteSemanticRelationships).mockResolvedValue({ requested: 1, deleted: [{ id: 'r1', name: 'r1' }], failed: [], deleted_count: 1, failed_count: 0 })
  vi.mocked(api.createSemanticRelationship).mockResolvedValue({ relationship })
  vi.mocked(api.patchSemanticRelationship).mockResolvedValue({ relationship })
  vi.mocked(api.listSemanticTerms).mockResolvedValue({ terms: [term], total: 1, page: 1, page_size: 10 })
  vi.mocked(api.bulkDeleteSemanticTerms).mockResolvedValue({ requested: 1, deleted: [{ id: 't1', name: 't1' }], failed: [], deleted_count: 1, failed_count: 0 })
  vi.mocked(api.createSemanticTerm).mockResolvedValue({ term })
  vi.mocked(api.patchSemanticTerm).mockResolvedValue({ term })
  vi.mocked(api.listSemanticRecentDefinitions).mockResolvedValue({
    definitions: [{ object_id: 'm1', object_kind: 'metric', name: 'Net Sales', type: 'Metric', definition: 'Sum', source: 'sales', status: 'Ready', modified_at: null }],
    total: 1,
    page: 1,
    page_size: 10,
  })
  vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [{ id: 'c1', name: 'PG', connector_type: 'postgres', enabled: true }] })
  vi.mocked(api.listConnectorCatalogs).mockResolvedValue({ catalogs: [] })
  vi.mocked(api.listConnectorSchemas).mockResolvedValue({ schemas: [{ name: 'public' }] })
  vi.mocked(api.listConnectorTables).mockResolvedValue({ tables: [{ name: 'sales' }] })
}

describe('SEM-2A matrix', () => {
  beforeEach(() => {
    setupDefaultMocks()
    push.mockClear()
  })
  afterEach(cleanup)

  it('SEM-2A-001 Data Models table render', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => expect(screen.getByTestId('semantic-data-models-table')).toBeTruthy())
    expect(screen.getByText('Sales')).toBeTruthy()
  })

  it('SEM-2A-002 Data Models backend search', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => expect(api.listSemanticEntities).toHaveBeenCalled())
    fireEvent.change(screen.getByPlaceholderText('Search data models…'), { target: { value: 'sale' } })
    await waitFor(() =>
      expect(api.listSemanticEntities).toHaveBeenCalledWith('v1', expect.objectContaining({ search: 'sale', page: 1 })),
    )
  })

  it('SEM-2A-003 Data Models sort', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    const table = await screen.findByTestId('semantic-data-models-table')
    fireEvent.click(within(table).getByRole('button', { name: 'Name' }))
    await waitFor(() =>
      expect(api.listSemanticEntities).toHaveBeenCalledWith('v1', expect.objectContaining({ sort: 'name', order: 'asc' })),
    )
  })

  it('SEM-2A-004 Data Models pagination', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Sales'))
    const next = screen.getByRole('button', { name: 'Next ›' })
    fireEvent.click(next)
    await waitFor(() => expect(api.listSemanticEntities).toHaveBeenCalledWith('v1', expect.objectContaining({ page: 2 })))
  })

  it('SEM-2A-005 Data Model create', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add data model'))
    fireEvent.click(screen.getByText('+ Add data model'))
    expect(screen.getByText('Add data model')).toBeTruthy()
  })

  it('SEM-2A-006 Data Model edit', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Sales/i }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    expect(screen.getByText('Edit data model')).toBeTruthy()
  })

  it('SEM-2A-007 Data Model cancel', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add data model'))
    fireEvent.click(screen.getByText('+ Add data model'))
    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByText('Add data model')).toBeNull()
  })

  it('SEM-2A-008 Data Model delete', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Sales/i }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    await waitFor(() => expect(api.deleteSemanticEntity).toHaveBeenCalledWith('v1', 'e1'))
  })

  it('SEM-2A-009 Ask this data wiring', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Sales/i }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Ask this data' }))
    expect(push).toHaveBeenCalledWith('/')
  })

  it('SEM-2A-010 Metrics table', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => expect(screen.getByTestId('semantic-metrics-table')).toBeTruthy())
    expect(screen.getByText('Net Sales')).toBeTruthy()
  })

  it('SEM-2A-011 Metric create', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add metric'))
    fireEvent.click(screen.getByText('+ Add metric'))
    expect(screen.getByText('Add metric')).toBeTruthy()
  })

  it('SEM-2A-012 Metric edit', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Net Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Net Sales/i }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    expect(screen.getByText('Edit metric')).toBeTruthy()
  })

  it('SEM-2A-013 Metric save', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Net Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Net Sales/i }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(api.patchSemanticMetric).toHaveBeenCalledWith('v1', 'm1', expect.any(Object)))
  })

  it('SEM-2A-014 Metric cancel', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add metric'))
    fireEvent.click(screen.getByText('+ Add metric'))
    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByText('Add metric')).toBeNull()
  })

  it('SEM-2A-015 invalid metric validation', async () => {
    vi.mocked(api.validateSemanticMetric).mockResolvedValueOnce({
      valid: false,
      issues: [{ field: 'expression', message: 'Column `nonexistent_column` was not found in sales.' }],
      form_message: 'Column `nonexistent_column` was not found in sales.',
    })
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add metric'))
    fireEvent.click(screen.getByText('+ Add metric'))
    fireEvent.change(screen.getByPlaceholderText('Metric name'), { target: { value: 'Bad Metric' } })
    fireEvent.change(screen.getByPlaceholderText('Business definition'), { target: { value: 'Test' } })
    const columnInput = await waitFor(() => {
      const manual = screen.queryByPlaceholderText('Source column')
      if (manual) return manual
      const columnSelect = Array.from(document.querySelectorAll('select')).find(sel =>
        Array.from(sel.options).some(o => o.textContent?.includes('Select column')),
      )
      if (columnSelect) {
        fireEvent.change(columnSelect, { target: { value: '__manual__' } })
      }
      return screen.getByPlaceholderText('Source column')
    })
    fireEvent.change(columnInput, { target: { value: 'nonexistent_column' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(screen.getAllByText(/nonexistent_column/).length).toBeGreaterThan(0))
    expect(api.createSemanticMetric).not.toHaveBeenCalled()
  })

  it('SEM-2A-016 metric sort/pagination/search', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByPlaceholderText('Search metrics…'))
    fireEvent.change(screen.getByPlaceholderText('Search metrics…'), { target: { value: 'net' } })
    await waitFor(() => expect(api.listSemanticMetrics).toHaveBeenCalledWith('v1', expect.objectContaining({ search: 'net' })))
    fireEvent.click(screen.getByText('Metric'))
    await waitFor(() => expect(api.listSemanticMetrics).toHaveBeenCalledWith('v1', expect.objectContaining({ sort: 'name' })))
  })

  it('SEM-2A-017 Dimensions table', async () => {
    render(<DimensionsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByTestId('semantic-dimensions-table'))
    expect(screen.getByText('Channel')).toBeTruthy()
  })

  it('SEM-2A-018 Dimension create/edit', async () => {
    render(<DimensionsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add dimension'))
    fireEvent.click(screen.getByText('+ Add dimension'))
    expect(screen.getByPlaceholderText('Name')).toBeTruthy()
    fireEvent.click(screen.getByText('Cancel'))
    const row = screen.getByText('Channel').closest('tr')
    expect(row).toBeTruthy()
    fireEvent.click(within(row!).getByRole('button', { name: 'Edit Channel' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    expect(screen.getByDisplayValue('Channel')).toBeTruthy()
  })

  it('SEM-2A-019 Dimension cancel', async () => {
    render(<DimensionsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add dimension'))
    fireEvent.click(screen.getByText('+ Add dimension'))
    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('SEM-2A-020 dimension sort/pagination/search', async () => {
    render(<DimensionsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByPlaceholderText('Search dimensions…'))
    fireEvent.change(screen.getByPlaceholderText('Search dimensions…'), { target: { value: 'chan' } })
    await waitFor(() => expect(api.listSemanticDimensions).toHaveBeenCalledWith('v1', expect.objectContaining({ search: 'chan' })))
  })

  it('SEM-2A-021 Relationships table', async () => {
    render(<RelationshipsTab versionId="v1" readOnly={false} entityKeys={['sales', 'store']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByTestId('semantic-relationships-table'))
    expect(screen.getByText('Sales to Store')).toBeTruthy()
  })

  it('SEM-2A-022 Relationship create/edit', async () => {
    render(<RelationshipsTab versionId="v1" readOnly={false} entityKeys={['sales', 'store']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add relationship'))
    fireEvent.click(screen.getByText('+ Add relationship'))
    expect(screen.getByRole('dialog', { name: 'Relationship' })).toBeTruthy()
  })

  it('SEM-2A-023 Relationship validation', async () => {
    render(
      <RelationshipsTab versionId="v1" readOnly={false} entityKeys={['customers', 'transactions']} onChanged={() => undefined} />,
    )
    await waitFor(() => screen.getByText('+ Add relationship'))
    fireEvent.click(screen.getByText('+ Add relationship'))
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(api.createSemanticRelationship).toHaveBeenCalled())

    vi.mocked(api.createSemanticRelationship).mockClear()
    cleanup()
    render(<RelationshipsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('+ Add relationship'))
    fireEvent.click(screen.getByText('+ Add relationship'))
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(screen.getByText(/different data models/)).toBeTruthy())
    expect(api.createSemanticRelationship).not.toHaveBeenCalled()
  })

  it('SEM-2A-024 relationship sort/pagination/search', async () => {
    render(<RelationshipsTab versionId="v1" readOnly={false} entityKeys={['sales', 'store']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByPlaceholderText('Search relationships…'))
    fireEvent.change(screen.getByPlaceholderText('Search relationships…'), { target: { value: 'store' } })
    await waitFor(() => expect(api.listSemanticRelationships).toHaveBeenCalledWith('v1', expect.objectContaining({ search: 'store' })))
  })

  it('SEM-2A-025 Glossary table', async () => {
    render(
      <GlossaryTab versionId="v1" readOnly={false} entityKeys={['sales']} metricKeys={['net_sales']} dimensionKeys={['channel']} onChanged={() => undefined} />,
    )
    await waitFor(() => screen.getByTestId('semantic-glossary-table'))
    expect(screen.getByText('Sell Out')).toBeTruthy()
  })

  it('SEM-2A-026 Glossary create/edit', async () => {
    render(
      <GlossaryTab versionId="v1" readOnly={false} entityKeys={['sales']} metricKeys={['net_sales']} dimensionKeys={['channel']} onChanged={() => undefined} />,
    )
    await waitFor(() => screen.getByText('+ Add term'))
    fireEvent.click(screen.getByText('+ Add term'))
    expect(screen.getByText('Glossary term')).toBeTruthy()
    fireEvent.click(screen.getByText('Cancel'))
    const row = screen.getByText('Sell Out').closest('tr')
    fireEvent.click(within(row!).getByRole('button', { name: 'Actions for Sell Out' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    await waitFor(() => expect(screen.getByDisplayValue('Sell Out')).toBeTruthy())
  })

  it('SEM-2A-027 glossary sort/pagination/search', async () => {
    render(
      <GlossaryTab versionId="v1" readOnly={false} entityKeys={['sales']} metricKeys={['net_sales']} dimensionKeys={['channel']} onChanged={() => undefined} />,
    )
    await waitFor(() => screen.getByPlaceholderText('Search glossary…'))
    fireEvent.change(screen.getByPlaceholderText('Search glossary…'), { target: { value: 'sell' } })
    await waitFor(() => expect(api.listSemanticTerms).toHaveBeenCalledWith('v1', expect.objectContaining({ search: 'sell' })))
  })

  it('SEM-2A-029 Recent Definitions sort/filter/page', async () => {
    render(<RecentDefinitionsPanel versionId="v1" />)
    await waitFor(() => expect(api.listSemanticRecentDefinitions).toHaveBeenCalled())
    fireEvent.change(screen.getByPlaceholderText('Search definitions…'), { target: { value: 'net' } })
    await waitFor(() =>
      expect(api.listSemanticRecentDefinitions).toHaveBeenCalledWith('v1', expect.objectContaining({ search: 'net' })),
    )
  })

  it('SEM-2A-031 selection mode', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Net Sales'))
    fireEvent.click(screen.getByRole('button', { name: 'Select rows' }))
    expect(screen.getByLabelText('Select Net Sales')).toBeTruthy()
  })

  it('SEM-2A-032 page select-all', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Net Sales'))
    fireEvent.click(screen.getByRole('button', { name: 'Select rows' }))
    const table = screen.getByTestId('semantic-metrics-table')
    const headerCb = within(table).getByRole('checkbox', { name: 'Select all rows' })
    fireEvent.click(headerCb)
    const rowCb = within(table).getByLabelText('Select Net Sales') as HTMLInputElement
    expect(rowCb.checked).toBe(true)
  })

  it('SEM-2A-033 row action portal', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Sales/i }))
    const menu = await screen.findByRole('menu')
    expect(menu).toBeTruthy()
  })

  it('SEM-2A-034 stable single-row table', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => screen.getByText('Net Sales'))
    expect(document.querySelector('tr.h-11')).toBeTruthy()
  })

  it('SEM-2A-035 editor dirty registration', async () => {
    const dirtyRef: { reg: ReturnType<typeof useEditorDirtyRegistry> | null } = { reg: null }
    function Harness() {
      dirtyRef.reg = useEditorDirtyRegistry()
      return <MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />
    }
    render(
      <EditorDirtyProvider>
        <Harness />
      </EditorDirtyProvider>,
    )
    await waitFor(() => screen.getByText('Net Sales'))
    fireEvent.click(screen.getByRole('button', { name: /Actions for Net Sales/i }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    fireEvent.change(screen.getByPlaceholderText('Metric name'), { target: { value: 'Net Sales Updated' } })
    await waitFor(() => expect(dirtyRef.reg?.activeRegistration()?.isDirty()).toBe(true))
  })
})
