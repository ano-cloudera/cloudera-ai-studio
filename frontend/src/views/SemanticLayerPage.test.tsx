import React from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SemanticLayerPage } from './SemanticLayerPage'

vi.mock('../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn().mockResolvedValue({
      models: [
        {
          id: 'm1',
          workspace_id: 'w1',
          project_id: 'p1',
          name: 'Tempo Core',
          key: 'tempo_core',
          description: null,
          active_version_id: 'v-active',
          created_at: '',
          updated_at: '',
        },
      ],
    }),
    listSemanticVersions: vi.fn().mockResolvedValue({
      versions: [
        {
          id: 'v-draft',
          semantic_model_id: 'm1',
          version_number: 2,
          status: 'DRAFT',
          created_by: null,
          created_at: '',
          updated_at: '',
          published_at: null,
          runtime_adapter: null,
          runtime_artifact_uri: null,
          runtime_artifact_checksum: null,
          runtime_artifact_version: null,
        },
        {
          id: 'v-active',
          semantic_model_id: 'm1',
          version_number: 1,
          status: 'ACTIVE',
          created_by: null,
          created_at: '',
          updated_at: '',
          published_at: '',
          runtime_adapter: 'ossie',
          runtime_artifact_uri: null,
          runtime_artifact_checksum: null,
          runtime_artifact_version: null,
        },
      ],
    }),
    listSemanticEntities: vi.fn().mockResolvedValue({
      entities: [
        {
          id: 'e1',
          key: 'sales',
          name: 'Sales',
          description: null,
          source_type: 'logical',
          catalog: null,
          schema: 'gold',
          table_name: 'sales',
          view_name: null,
          primary_key: null,
          connection_id: null,
          metadata: {},
        },
      ],
    }),
    listConnectors: vi.fn().mockResolvedValue({ connectors: [] }),
    listSemanticMetrics: vi.fn().mockResolvedValue({ metrics: [] }),
    listSemanticDimensions: vi.fn().mockResolvedValue({ dimensions: [] }),
    listSemanticRelationships: vi.fn().mockResolvedValue({ relationships: [] }),
    listSemanticTerms: vi.fn().mockResolvedValue({ terms: [] }),
    getOssieImportSource: vi.fn(),
    importOssieSemantics: vi.fn(),
    getSemanticValidatorHealth: vi.fn().mockResolvedValue({
      impala: { status: 'connected', label: 'Impala' },
      trino: { status: 'not_configured', label: 'Trino' },
    }),
    listSemanticValidationRuns: vi.fn().mockResolvedValue({ runs: [] }),
    getSemanticRuntimeStatus: vi.fn().mockResolvedValue({
      registry_active_version: 1,
      runtime_active_version: null,
      runtime_status: 'legacy_fallback',
      loader_mode: 'legacy',
      deployment: null,
    }),
    listSemanticRuntimeDeployments: vi.fn().mockResolvedValue({ deployments: [] }),
    getSemanticModelOverview: vi.fn().mockResolvedValue({
      model: { id: 'm1', name: 'Tempo Core', key: 'tempo_core', updated_at: null },
      state: 'Draft',
      readiness: 'unknown',
      issue_count: 0,
      published_version_number: 1,
      draft_version_number: 2,
      counts: { entities: 1, metrics: 0, dimensions: 0, relationships: 0, terms: 0 },
      ready_to_publish: false,
    }),
    publishSemanticToAskData: vi.fn(),
    listSemanticRecentDefinitions: vi.fn().mockResolvedValue({ definitions: [], total: 0, page: 1, page_size: 10 }),
  },
}))

describe('SemanticLayerPage', () => {
  afterEach(cleanup)

  it('renders overview and publish CTA', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getByText('Semantic Layer')).toBeTruthy())
    await waitFor(() => expect(screen.getAllByText('Configure trusted business definitions for Ask Data.').length).toBeGreaterThan(0))
    expect(screen.getAllByText('Publish to Ask Data').length).toBe(1)
    expect(screen.getAllByTestId('semantic-advanced-trigger').length).toBe(1)
  })
})
