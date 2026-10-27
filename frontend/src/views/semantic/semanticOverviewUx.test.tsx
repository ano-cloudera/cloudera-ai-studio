import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SemanticModelCombobox } from '../../components/semantic/SemanticModelCombobox'
import { SemanticLayerPage } from '../SemanticLayerPage'
import { SemanticOverviewPanel } from './SemanticOverviewPanel'

const { mockModels } = vi.hoisted(() => ({
  mockModels: [
    { id: '1', name: 'Art', key: 'art.0224cb', active_version_id: 'v-active' },
    { id: '2', name: 'Retail', key: 'retail.analytics', active_version_id: null },
  ],
}))

vi.mock('../../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn().mockResolvedValue({ models: mockModels }),
    listSemanticVersions: vi.fn().mockResolvedValue({
      versions: [
        { id: 'v1', semantic_model_id: '1', version_number: 1, status: 'DRAFT' },
        { id: 'v-active', semantic_model_id: '1', version_number: 1, status: 'ACTIVE', published_at: '' },
      ],
    }),
    getSemanticModelOverview: vi.fn().mockResolvedValue({
      model: { id: '1', name: 'Art', key: 'art.0224cb', updated_at: '2026-10-15T12:00:00Z' },
      state: 'Ready',
      counts: { entities: 3, metrics: 5, dimensions: 2, relationships: 1, terms: 4 },
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
    getSemanticRuntimeStatus: vi.fn().mockResolvedValue({
      registry_active_version: 1,
      runtime_active_version: null,
      runtime_status: 'legacy_fallback',
      loader_mode: 'legacy',
      deployment: null,
    }),
    listSemanticRuntimeDeployments: vi.fn().mockResolvedValue({ deployments: [] }),
    listSemanticValidationRuns: vi.fn().mockResolvedValue({ runs: [] }),
    previewSemanticArtifact: vi.fn().mockResolvedValue({ content_preview: '' }),
    getOssieImportSource: vi.fn().mockResolvedValue({ ossie_file: '/x', exists: true }),
  },
}))

describe('Semantic Overview UX refinement', () => {
  afterEach(cleanup)

  it('combobox trigger shows model name only at toolbar height', () => {
    render(<SemanticModelCombobox models={mockModels} value="1" onChange={() => undefined} />)
    const trigger = screen.getByTestId('semantic-model-combobox-trigger')
    expect(trigger.textContent).toContain('Art')
    expect(trigger.textContent).not.toContain('art.0224cb')
    expect(trigger.className).toMatch(/h-10/)
  })

  it('combobox filters and bounds result list', () => {
    const many = Array.from({ length: 60 }, (_, i) => ({
      id: `m${i}`,
      name: `Model ${i}`,
      key: `key.${i}`,
    })) as never[]
    render(<SemanticModelCombobox models={many} value="m0" onChange={() => undefined} />)
    fireEvent.click(screen.getByTestId('semantic-model-combobox-trigger'))
    expect(screen.getAllByRole('option').length).toBeLessThanOrEqual(50)
    fireEvent.change(screen.getByTestId('semantic-model-combobox-search'), { target: { value: 'Model 59' } })
    expect(screen.getByRole('option', { name: /Model 59/i })).toBeTruthy()
  })

  it('combobox Enter selects highlighted option', () => {
    const onChange = vi.fn()
    render(<SemanticModelCombobox models={mockModels} value="1" onChange={onChange} />)
    fireEvent.click(screen.getByTestId('semantic-model-combobox-trigger'))
    fireEvent.change(screen.getByTestId('semantic-model-combobox-search'), { target: { value: 'retail' } })
    fireEvent.keyDown(screen.getByTestId('semantic-model-combobox-search'), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('2')
  })

  it('toolbar aligns publish with combobox trigger height', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => screen.getByTestId('semantic-model-toolbar'))
    fireEvent.click(screen.getByTestId('semantic-tab-publish-config'))
    const publish = screen.getByTestId('semantic-save-publish')
    const trigger = screen.getByTestId('semantic-model-combobox-trigger')
    expect(publish.className).toMatch(/h-9/)
    expect(trigger.className).toMatch(/h-10/)
  })

  it('overview omits duplicate model title and uses compact readiness', () => {
    render(
      <SemanticOverviewPanel
        overview={{
          model: { id: '1', name: 'Art', key: 'art.0224cb', updated_at: '2026-10-15T12:00:00Z' },
          state: 'Ready',
          counts: { entities: 1, metrics: 2, dimensions: 3, relationships: 4, terms: 5 },
          issue_count: 0,
          published_version_number: null,
        }}
      />,
    )
    expect(screen.queryByText(/^Art$/)).toBeNull()
    expect(screen.getByTestId('semantic-overview-readiness').textContent).toMatch(/Ready to publish/)
    expect(screen.getByText(/Last modified/)).toBeTruthy()
    expect(screen.getByTestId('semantic-overview-summary').children.length).toBe(5)
    expect(screen.queryByTestId('semantic-recent-definitions-section')).toBeNull()
  })

  it('overview checklist renders when navigation is wired', () => {
    render(
      <SemanticOverviewPanel
        overview={{
          model: { id: '1', name: 'Art', key: 'art', updated_at: null },
          state: 'Ready',
          counts: { entities: 1, metrics: 2, dimensions: 3, relationships: 0, terms: 0 },
          issue_count: 0,
          published_version_number: null,
        }}
        onNavigateTab={() => undefined}
      />,
    )
    expect(screen.getByTestId('semantic-overview-checklist')).toBeTruthy()
  })
})
