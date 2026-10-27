import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EditorDirtyProvider } from './EditorDirtyContext'
import { DataModelsTab } from './DataModelsTab'
import { MetricsTab } from './SemanticOtherTabs'
import { RecentDefinitionsPanel } from './RecentDefinitionsPanel'
import { UnsavedChangesModal } from '../../../components/semantic/UnsavedChangesModal'
import { useEditorDirtyRegistry } from './EditorDirtyContext'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

vi.mock('../../../lib/api', () => {
  const entities = [
    {
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
    },
  ]
  return {
  api: {
    listSemanticEntities: vi.fn().mockResolvedValue({ entities, total: 1, page: 1, page_size: 10 }),
    deleteSemanticEntity: vi.fn().mockResolvedValue({ deleted: true }),
    importSemanticEntity: vi.fn().mockResolvedValue({ entity: entities[0], import: { dimensions_created: 0, columns_discovered: 12, warnings: [] } }),
    patchSemanticEntity: vi.fn(),
    previewSemanticEntityImport: vi.fn().mockResolvedValue({ preview: { existing_entity: null, columns: [] } }),
    listSemanticMetrics: vi.fn().mockResolvedValue({ metrics: [], total: 0, page: 1, page_size: 10 }),
    listSemanticDimensions: vi.fn().mockResolvedValue({ dimensions: [], total: 0, page: 1, page_size: 10 }),
    createSemanticMetric: vi.fn(),
    patchSemanticMetric: vi.fn(),
    listSemanticRecentDefinitions: vi.fn().mockResolvedValue({
      definitions: [{ object_id: 'm1', object_kind: 'metric', name: 'Total Sales', type: 'Metric', definition: 'Sum', source: 'sales', status: 'Ready', modified_at: null }],
      total: 1,
      page: 1,
      page_size: 10,
    }),
    listConnectors: vi.fn().mockResolvedValue({ connectors: [{ id: 'c1', name: 'PG', connector_type: 'postgres', enabled: true }] }),
    listConnectorCatalogs: vi.fn().mockResolvedValue({ catalogs: [] }),
    listConnectorSchemas: vi.fn().mockResolvedValue({ schemas: [{ name: 'public' }] }),
    listConnectorTables: vi.fn().mockResolvedValue({ tables: [{ name: 'sales' }] }),
  },
  }
})

describe('SEM-2A authoring core', () => {
  afterEach(cleanup)

  it('SEM-2A-001 Data Models table render', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => expect(screen.getByTestId('semantic-data-models-table')).toBeTruthy())
    expect(screen.getByText('Sales')).toBeTruthy()
  })

  it('SEM-2A-005 Add Data Model drawer', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => expect(screen.getByText('+ Add data model')).toBeTruthy())
    fireEvent.click(screen.getByText('+ Add data model'))
    expect(screen.getByText('Add data model')).toBeTruthy()
  })

  it('SEM-2A-010 Metrics table', async () => {
    render(<MetricsTab versionId="v1" readOnly={false} entityKeys={['sales']} onChanged={() => undefined} />)
    await waitFor(() => expect(screen.getByTestId('semantic-metrics-table')).toBeTruthy())
  })

  it('SEM-2A-028 Recent Definitions', async () => {
    render(<RecentDefinitionsPanel versionId="v1" />)
    await waitFor(() => expect(screen.getByText('Total Sales')).toBeTruthy())
  })

  it('SEM-2A-030 selection mode hidden by default', async () => {
    render(<DataModelsTab versionId="v1" readOnly={false} connectors={[]} onChanged={() => undefined} />)
    await waitFor(() => expect(screen.getByText('Sales')).toBeTruthy())
    expect(screen.queryByLabelText(/Select Sales/)).toBeNull()
  })

  it('SEM-2A-036 Save and Continue invokes editor save', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    function Harness() {
      const { register } = useEditorDirtyRegistry()
      React.useEffect(() => {
        register({ isDirty: () => true, save, discard: () => undefined })
      }, [register])
      return <UnsavedChangesModal open onKeepEditing={() => undefined} onDiscard={() => undefined} onSaveAndContinue={async () => save()} />
    }
    render(
      <EditorDirtyProvider>
        <Harness />
      </EditorDirtyProvider>,
    )
    fireEvent.click(screen.getByText('Save and continue'))
    await waitFor(() => expect(save).toHaveBeenCalled())
  })
})
