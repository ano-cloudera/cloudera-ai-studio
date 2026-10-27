import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AddToSemanticLayerModal } from './AddToSemanticLayerModal'

const connector = {
  id: 'c1',
  workspace_id: 'w1',
  project_id: 'p1',
  name: 'Demo PG',
  key: 'demo_pg',
  description: null,
  connector_type: 'postgres' as const,
  status: 'ACTIVE',
  enabled: true,
  config: {},
  secret_ref: null,
  credentials_configured: true,
  last_tested_at: null,
  last_test_status: 'SUCCESS',
  last_test_message: null,
  metadata: {},
  created_at: '',
  updated_at: '',
  created_by: null,
}

vi.mock('../../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn().mockResolvedValue({ models: [{ id: 'm1', name: 'Core', key: 'core' }] }),
    listSemanticVersions: vi.fn().mockResolvedValue({
      versions: [{ id: 'v-draft', status: 'DRAFT', version_number: 2, semantic_model_id: 'm1' }],
    }),
    previewSemanticEntityImport: vi.fn().mockResolvedValue({
      preview: {
        table_type: 'TABLE',
        columns: [],
        candidate_dimensions: [{ column: 'region', suggested_key: 'region', normalized_type: 'STRING' }],
        existing_entity: null,
        primary_key: null,
      },
    }),
    importSemanticEntity: vi.fn().mockResolvedValue({
      entity: { id: 'e1', key: 'customers', name: 'Customers' },
      import: { dimensions_created: 1, columns_discovered: 3, warnings: [] },
    }),
  },
}))

describe('AddToSemanticLayerModal', () => {
  afterEach(cleanup)

  it('creates entity from connector table with selected dimensions', async () => {
    const onImported = vi.fn()
    render(
      <AddToSemanticLayerModal
        connector={connector}
        catalog={null}
        schema="public"
        table="customers"
        onClose={() => undefined}
        onImported={onImported}
      />,
    )
    await waitFor(() => screen.getByText('Candidate dimensions'))
    fireEvent.click(screen.getByRole('button', { name: 'Create entity' }))
    const { api } = await import('../../lib/api')
    await waitFor(() => expect(api.importSemanticEntity).toHaveBeenCalled())
    expect(onImported).toHaveBeenCalledWith('e1')
  })
})
