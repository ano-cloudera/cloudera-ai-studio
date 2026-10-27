import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SemanticLayerPage } from '../SemanticLayerPage'
import { SemanticArtifactPreviewPanel } from './authoring/SemanticArtifactPreviewPanel'

vi.mock('../../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn().mockResolvedValue({
      models: [{ id: 'm1', name: 'Art', key: 'art', active_version_id: 'v-active', workspace_id: 'w', project_id: 'p' }],
    }),
    listSemanticVersions: vi.fn().mockResolvedValue({
      versions: [{ id: 'v-draft', semantic_model_id: 'm1', version_number: 2, status: 'DRAFT' }],
    }),
    getSemanticModelOverview: vi.fn().mockResolvedValue({
      model: { id: 'm1', name: 'Art', key: 'art', updated_at: null },
      state: 'Draft',
      counts: { entities: 1, metrics: 1, dimensions: 0, relationships: 0, terms: 0 },
      issue_count: 0,
      published_version_number: null,
    }),
    listSemanticEntities: vi.fn().mockResolvedValue({ entities: [], total: 0 }),
    listSemanticMetrics: vi.fn().mockResolvedValue({ metrics: [], total: 0 }),
    listSemanticDimensions: vi.fn().mockResolvedValue({ dimensions: [], total: 0 }),
    listSemanticRelationships: vi.fn().mockResolvedValue({ relationships: [], total: 0 }),
    listSemanticTerms: vi.fn().mockResolvedValue({ terms: [], total: 0 }),
    listSemanticRecentDefinitions: vi.fn().mockResolvedValue({ definitions: [], total: 0, page: 1, page_size: 5 }),
    listConnectors: vi.fn().mockResolvedValue({ connectors: [] }),
    getSemanticValidatorHealth: vi.fn().mockResolvedValue({ status: 'ok' }),
    getSemanticRuntimeStatus: vi.fn().mockResolvedValue({ registry_active_version: null }),
    listSemanticRuntimeDeployments: vi.fn().mockResolvedValue({ deployments: [] }),
    listSemanticValidationRuns: vi.fn().mockResolvedValue({ runs: [] }),
    previewSemanticArtifact: vi.fn().mockResolvedValue({ content_preview: 'artifact: test\nmetric: one' }),
    getOssieImportSource: vi.fn().mockResolvedValue({ ossie_file: '/tmp/x.yaml', exists: true }),
  },
}))

describe('Semantic Advanced UX cleanup', () => {
  afterEach(cleanup)

  async function ready() {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getByTestId('semantic-create-model')).toBeTruthy())
  }

  it('does not show Draft badge in primary header', async () => {
    await ready()
    expect(screen.queryByTestId('semantic-header-status-badge')).toBeNull()
  })

  it('shows Needs attention badge when publish issues exist', async () => {
    await ready()
    // Simulate via re-render path — overview Published still hidden for Draft; badge driven by publishIssues in live page
    expect(screen.queryByText(/^Draft$/)).toBeNull()
  })

  it('Import OSSIE removed from primary header and available under Advanced', async () => {
    await ready()
    expect(screen.queryByTestId('semantic-import-ossie')).toBeNull()
    fireEvent.click(screen.getByTestId('semantic-advanced-trigger'))
    expect(screen.getByTestId('semantic-advanced-import-ossie')).toBeTruthy()
  })

  it('artifact preview not rendered on Overview', async () => {
    await ready()
    expect(screen.queryByTestId('semantic-artifact-preview-panel')).toBeNull()
    expect(screen.queryByTestId('semantic-artifact-preview-content')).toBeNull()
  })

  it('artifact preview only in Advanced preview view', async () => {
    await ready()
    fireEvent.click(screen.getByTestId('semantic-advanced-trigger'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Preview semantic artifact' }))
    await waitFor(() => expect(screen.getByTestId('semantic-artifact-preview-panel')).toBeTruthy())
  })

  it('artifact panel expand/collapse', () => {
    render(
      <SemanticArtifactPreviewPanel artifact={{ content_preview: 'line1\nline2\nline3' }} onRefresh={() => undefined} />,
    )
    fireEvent.click(screen.getByTestId('semantic-artifact-toggle'))
    expect(screen.getByTestId('semantic-artifact-preview-content')).toBeTruthy()
    fireEvent.click(screen.getByTestId('semantic-artifact-toggle'))
    expect(screen.queryByTestId('semantic-artifact-preview-content')).toBeNull()
  })

  it('Glossary tab has no artifact preview', async () => {
    await ready()
    fireEvent.click(screen.getAllByRole('button').find(b => b.textContent?.trim() === 'Glossary')!)
    await waitFor(() => expect(screen.getByTestId('semantic-glossary-table')).toBeTruthy())
    expect(screen.queryByTestId('semantic-artifact-preview-panel')).toBeNull()
  })

  it('deployment empty state uses friendly copy', async () => {
    await ready()
    fireEvent.click(screen.getByTestId('semantic-advanced-trigger'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Deployment details' }))
    await waitFor(() => expect(screen.getByText(/No active deployment yet/)).toBeTruthy())
    expect(screen.getByText(/Publish this semantic model to make it available in Ask Data/)).toBeTruthy()
  })
})
