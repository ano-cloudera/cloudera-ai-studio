import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SemanticLayerPage } from '../SemanticLayerPage'
import { SemanticOverviewPanel } from './SemanticOverviewPanel'

vi.mock('../../lib/api', () => ({
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
      ],
    }),
    listSemanticEntities: vi.fn().mockResolvedValue({ entities: [], total: 0 }),
    listConnectors: vi.fn().mockResolvedValue({ connectors: [] }),
    listSemanticMetrics: vi.fn().mockResolvedValue({ metrics: [], total: 0 }),
    listSemanticDimensions: vi.fn().mockResolvedValue({ dimensions: [], total: 0 }),
    listSemanticRelationships: vi.fn().mockResolvedValue({ relationships: [], total: 0 }),
    listSemanticTerms: vi.fn().mockResolvedValue({ terms: [], total: 0 }),
    listSemanticRecentDefinitions: vi.fn().mockResolvedValue({ definitions: [], total: 0, page: 1, page_size: 10 }),
    getSemanticModelOverview: vi.fn().mockResolvedValue({
      model: { id: 'm1', name: 'Tempo Core', key: 'tempo_core', updated_at: null },
      state: 'Ready',
      counts: { entities: 1, metrics: 2, dimensions: 3, relationships: 4, terms: 5 },
      issue_count: 0,
      published_version_number: null,
    }),
    getSemanticValidatorHealth: vi.fn().mockResolvedValue({ status: 'ok' }),
    getSemanticRuntimeStatus: vi.fn().mockResolvedValue({ registry_active_version: null }),
    listSemanticRuntimeDeployments: vi.fn().mockResolvedValue({ deployments: [] }),
    previewSemanticArtifact: vi.fn().mockResolvedValue({ content_preview: 'preview' }),
    getOssieImportSource: vi.fn().mockResolvedValue({ ossie_file: '/tmp/x.yaml', exists: true }),
    listSemanticValidationRuns: vi.fn().mockResolvedValue({ runs: [] }),
  },
}))

describe('Phase 2A UX polish', () => {
  afterEach(cleanup)

  it('renders Preview, Version history, and Publish tabs', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getByTestId('semantic-tab-preview')).toBeTruthy())
    expect(screen.getByTestId('semantic-tab-version-history')).toBeTruthy()
    expect(screen.getByTestId('semantic-tab-publish-config')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Advanced ▾' })).toBeNull()
  })

  it('Publish tab shows publish actions only', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => screen.getByTestId('semantic-tab-publish-config'))
    fireEvent.click(screen.getByTestId('semantic-tab-publish-config'))
    expect(screen.getByTestId('semantic-publish-tab-panel')).toBeTruthy()
    expect(screen.getByTestId('semantic-save-publish')).toBeTruthy()
  })

  it('Overview summary renders five cards in one group', () => {
    render(
      <SemanticOverviewPanel
        versionId="v1"
        overview={{
          model: { id: 'm1', name: 'Tempo Core', key: 'tempo_core', updated_at: null },
          state: 'Ready',
          counts: { entities: 1, metrics: 2, dimensions: 3, relationships: 4, terms: 5 },
          issue_count: 0,
          published_version_number: null,
        }}
      />,
    )
    const group = screen.getByTestId('semantic-overview-summary')
    expect(group.children.length).toBe(5)
    expect(screen.queryByText(/^Tempo Core$/)).toBeNull()
    expect(screen.getByTestId('semantic-overview-readiness')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Model health' })).toBeNull()
  })

  it('Overview shows setup checklist instead of recent definitions table', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getByTestId('semantic-overview-checklist')).toBeTruthy())
    expect(screen.queryByTestId('semantic-recent-definitions')).toBeNull()
  })
})
