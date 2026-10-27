import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SemanticLayerPage } from '../SemanticLayerPage'
import { UnsavedChangesModal } from '../../components/semantic/UnsavedChangesModal'
import { SemanticOverviewPanel } from './SemanticOverviewPanel'
import { CreateSemanticModelWizard } from './CreateSemanticModelWizard'
import { ContextModeBadge } from '../../components/chat/ContextModeBadge'
import { clarificationChoices } from '../../lib/clarificationPrompts'
import type { ChatResponse } from '../../types/api'

vi.mock('../../lib/api', () => ({
  api: {
    listSemanticModels: vi.fn().mockResolvedValue({
      models: [{ id: 'm1', workspace_id: 'w1', project_id: 'p1', name: 'Commercial', key: 'commercial', description: null, active_version_id: 'v1', created_at: '', updated_at: '' }],
    }),
    listSemanticVersions: vi.fn().mockResolvedValue({
      versions: [{ id: 'v-draft', semantic_model_id: 'm1', version_number: 2, status: 'DRAFT', created_by: null, created_at: '', updated_at: '', published_at: null, runtime_adapter: null, runtime_artifact_uri: null, runtime_artifact_checksum: null, runtime_artifact_version: null }],
    }),
    getSemanticModelOverview: vi.fn().mockResolvedValue({
      model: { id: 'm1', name: 'Commercial', key: 'commercial', updated_at: null },
      state: 'Draft',
      readiness: 'unknown',
      issue_count: 0,
      published_version_number: 1,
      draft_version_number: 2,
      counts: { entities: 3, metrics: 8, dimensions: 12, relationships: 2, terms: 1 },
      ready_to_publish: true,
    }),
    listSemanticEntities: vi.fn().mockResolvedValue({ entities: [] }),
    listSemanticMetrics: vi.fn().mockResolvedValue({ metrics: [] }),
    listSemanticDimensions: vi.fn().mockResolvedValue({ dimensions: [] }),
    listSemanticRelationships: vi.fn().mockResolvedValue({ relationships: [] }),
    listSemanticTerms: vi.fn().mockResolvedValue({ terms: [] }),
    listConnectors: vi.fn().mockResolvedValue({ connectors: [] }),
    getSemanticValidatorHealth: vi.fn().mockResolvedValue({ impala: { status: 'ok', label: 'Impala' }, trino: { status: 'ok', label: 'Trino' } }),
    listSemanticValidationRuns: vi.fn().mockResolvedValue({ runs: [] }),
    getSemanticRuntimeStatus: vi.fn().mockResolvedValue({ registry_active_version: 1, runtime_active_version: 1, runtime_status: 'ok', loader_mode: 'runtime', deployment: null }),
    listSemanticRuntimeDeployments: vi.fn().mockResolvedValue({ deployments: [] }),
    publishSemanticToAskData: vi.fn(),
    listSemanticRecentDefinitions: vi.fn().mockResolvedValue({ definitions: [], total: 0, page: 1, page_size: 10 }),
  },
}))

describe('SEM-FE2 Phase 2 UX', () => {
  afterEach(cleanup)

  it('SEM-FE2-001 overview summary renders', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getAllByText('Configure trusted business definitions for Ask Data.').length).toBeGreaterThan(0))
    expect(screen.getByRole('button', { name: 'Data Models' })).toBeTruthy()
    await waitFor(() => expect(screen.getAllByText('8').length).toBeGreaterThan(0))
  })

  it('SEM-FE2-002 overview hides runtime internals from primary view', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getByText('Commercial')).toBeTruthy())
    expect(screen.queryByText(/Registry active version/i)).toBeNull()
    expect(screen.queryByText(/Legacy OSSIE/i)).toBeNull()
  })

  it('SEM-FE2-003 Advanced contains Model Health', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Advanced ▾' })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Advanced ▾' }))
    expect(screen.getAllByText('Model health').length).toBeGreaterThan(0)
  })

  it('SEM-FE2-023 dirty-state custom modal', () => {
    const onDiscard = vi.fn()
    render(<UnsavedChangesModal open onKeepEditing={() => undefined} onDiscard={onDiscard} onSaveAndContinue={() => undefined} />)
    expect(screen.getByText('Unsaved changes')).toBeTruthy()
    fireEvent.click(screen.getByText('Discard changes'))
    expect(onDiscard).toHaveBeenCalled()
  })

  it('SEM-FE2-027 publish button visible', async () => {
    render(<SemanticLayerPage />)
    await waitFor(() => expect(screen.getAllByText('Publish to Ask Data').length).toBeGreaterThan(0))
  })

  it('SEM-FE2-030 raw-data chat badge', () => {
    const response = {
      context_mode: 'RAW_TABLE',
      clarification: { reason: 'x', message: 'm', options: [{ type: 'table', id: '1', name: 'public.sales' }] },
    } as ChatResponse
    render(<ContextModeBadge response={response} />)
    expect(screen.getByText(/Raw data/)).toBeTruthy()
  })

  it('SEM-FE2-031 governed-semantic chat badge', () => {
    const response = { context_mode: 'GOVERNED_SEMANTIC', data: { governed_metric: 'total_sales' } } as ChatResponse
    render(<ContextModeBadge response={response} />)
    expect(screen.getByText(/Governed semantic/)).toBeTruthy()
  })

  it('SEM-FE2-032 clarification choice rendering', () => {
    const response = {
      status: 'clarification_required',
      strategy: 'clarification',
      clarification: {
        reason: 'AMBIGUOUS_DATA_SOURCE',
        message: 'pick',
        options: [{ type: 'table', id: 'tr:1', name: 'Sales Sell In' }],
      },
      answer: { direct_answer: '', executive_summary: '', insights: [], business_implications: [], caveats: [], data_reference: '', chart_spec: null },
    } as ChatResponse
    const choices = clarificationChoices(response)
    expect(choices?.[0].label).toBe('Sales Sell In')
  })

  it('SEM-FE2-011 wizard step 1', () => {
    render(<CreateSemanticModelWizard open connectors={[]} onClose={() => undefined} onCreated={() => undefined} />)
    expect(screen.getByPlaceholderText('Commercial Sales')).toBeTruthy()
  })
})

describe('SemanticOverviewPanel', () => {
  it('SEM-FE2-028 overview readiness without duplicate publish CTA', () => {
    render(
      <SemanticOverviewPanel
        overview={{
          model: { id: 'm1', name: 'M', key: 'm', updated_at: null },
          state: 'Draft',
          readiness: 'READY',
          issue_count: 0,
          published_version_number: null,
          draft_version_number: 1,
          counts: { entities: 1, metrics: 1, dimensions: 1, relationships: 0, terms: 0 },
          ready_to_publish: true,
        }}
        versionId="v-draft"
      />,
    )
    expect(screen.getByText('Ready to publish')).toBeTruthy()
    expect(screen.queryByText('Publish to Ask Data')).toBeNull()
    expect(screen.getByTestId('semantic-overview-summary').children).toHaveLength(5)
  })
})
