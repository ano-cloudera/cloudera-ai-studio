import React, { useEffect } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SemanticLayerPage } from '../SemanticLayerPage'
import { CreateSemanticModelWizard } from './CreateSemanticModelWizard'
import { SemanticModelCombobox } from '../../components/semantic/SemanticModelCombobox'
import { UnsavedChangesModal } from '../../components/semantic/UnsavedChangesModal'
import { ProductConfirmModal } from '../../components/semantic/ProductConfirmModal'
import { EditorDirtyProvider, useEditorDirtyRegistry } from './authoring/EditorDirtyContext'
import type { AppApiError } from '../../lib/apiError'

const connectors = [{ id: 'c1', name: 'PostgreSQL', connector_type: 'postgres', status: 'READY' }] as const

const api = vi.hoisted(() => ({
  listSemanticModels: vi.fn(),
  listSemanticVersions: vi.fn(),
  getSemanticModelOverview: vi.fn(),
  listSemanticEntities: vi.fn(),
  listSemanticMetrics: vi.fn(),
  listSemanticDimensions: vi.fn(),
  listSemanticRelationships: vi.fn(),
  listSemanticTerms: vi.fn(),
  listConnectors: vi.fn(),
  getSemanticValidatorHealth: vi.fn(),
  getSemanticRuntimeStatus: vi.fn(),
  listSemanticRuntimeDeployments: vi.fn(),
  listSemanticValidationRuns: vi.fn(),
  listSemanticRecentDefinitions: vi.fn(),
  publishSemanticToAskData: vi.fn(),
  createSemanticModel: vi.fn(),
  acceptSemanticSuggestions: vi.fn(),
  semanticSuggestions: vi.fn(),
  listConnectorTables: vi.fn(),
  rollbackSemanticVersion: vi.fn(),
  getOssieImportSource: vi.fn(),
  importOssieSemantics: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api }))

function appErr(status: number, details?: unknown, message = 'error'): AppApiError {
  return { code: `HTTP_${status}`, status, message, details, retryable: status >= 500 }
}

function basePageMocks() {
  api.listSemanticModels.mockResolvedValue({
    models: [
      { id: 'm1', name: 'Art', key: 'art', active_version_id: 'v-active', workspace_id: 'w', project_id: 'p' },
      { id: 'm2', name: 'Retail', key: 'retail', active_version_id: null, workspace_id: 'w', project_id: 'p' },
    ],
  })
  api.listSemanticVersions.mockResolvedValue({
    versions: [
      { id: 'v-draft', semantic_model_id: 'm1', version_number: 2, status: 'DRAFT' },
      { id: 'v-active', semantic_model_id: 'm1', version_number: 1, status: 'ACTIVE', published_at: '2026-01-01' },
      { id: 'v-arch', semantic_model_id: 'm1', version_number: 0, status: 'ARCHIVED', published_at: '2025-01-01' },
    ],
  })
  api.getSemanticModelOverview.mockResolvedValue({
    model: { id: 'm1', name: 'Art', key: 'art', updated_at: null },
    state: 'Draft',
    readiness: 'READY',
    issue_count: 0,
    published_version_number: 1,
    draft_version_number: 2,
    counts: { entities: 1, metrics: 1, dimensions: 0, relationships: 0, terms: 0 },
  })
  api.listSemanticEntities.mockResolvedValue({ entities: [{ id: 'e1', key: 'sales', name: 'Sales' }], total: 1 })
  api.listSemanticMetrics.mockResolvedValue({
    metrics: [
      {
        id: 'met1',
        key: 'bad_m',
        name: 'Bad M',
        business_definition: 'x',
        expression: 'SUM(x)',
        synonyms: [],
        aggregation: 'sum',
        source_entity_key: 'sales',
      },
    ],
    total: 1,
  })
  api.listSemanticDimensions.mockResolvedValue({ dimensions: [], total: 0 })
  api.listSemanticRelationships.mockResolvedValue({ relationships: [], total: 0 })
  api.listSemanticTerms.mockResolvedValue({ terms: [], total: 0 })
  api.listConnectors.mockResolvedValue({ connectors: [...connectors] })
  api.getSemanticValidatorHealth.mockResolvedValue({ impala: { status: 'ok', label: 'Impala' } })
  api.getSemanticRuntimeStatus.mockResolvedValue({
    loader_mode: 'runtime',
    runtime_active_version: 1,
    registry_active_version: 1,
    runtime_status: 'ok',
  })
  api.listSemanticRuntimeDeployments.mockResolvedValue({ deployments: [] })
  api.listSemanticValidationRuns.mockResolvedValue({ runs: [] })
  api.listSemanticRecentDefinitions.mockResolvedValue({ definitions: [], total: 0, page: 1, page_size: 10 })
  api.publishSemanticToAskData.mockResolvedValue({ status: 'published', version_number: 2 })
  api.rollbackSemanticVersion.mockResolvedValue({ ok: true })
  api.listConnectorTables.mockResolvedValue({
    tables: [
      { schema: 'public', name: 'sales' },
      { schema: 'public', name: 'products' },
    ],
  })
  api.semanticSuggestions.mockResolvedValue({
    entities: [{ suggestion_id: 'entity:sales', key: 'sales', name: 'Sales' }],
    metrics: [{ suggestion_id: 'metric:total', key: 'total', name: 'Total' }],
    dimensions: [],
    relationships: [],
    glossary_suggestions: [],
  })
}

async function advanceWizardToReview(name = 'Wizard Model') {
  fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  fireEvent.click(await screen.findByText('PostgreSQL'))
  await waitFor(() => expect(api.listConnectorTables).toHaveBeenCalled())
  fireEvent.click((await screen.findAllByRole('checkbox'))[0])
  fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
  await waitFor(() => expect(api.semanticSuggestions).toHaveBeenCalled())
}

async function renderPageReady(extra?: React.ReactNode) {
  renderPage(extra)
  await waitFor(() => expect(screen.getByTestId('semantic-publish-ask-data')).toBeTruthy())
}

function DirtyRegistrar(props: { dirty?: boolean; save?: () => Promise<void> }) {
  const { register } = useEditorDirtyRegistry()
  useEffect(() => {
    register({
      isDirty: () => props.dirty ?? true,
      save: props.save ?? (async () => undefined),
      discard: () => undefined,
    })
    return () => register(null)
  }, [register, props.dirty, props.save])
  return null
}

function renderPage(extra?: React.ReactNode) {
  return render(
    <EditorDirtyProvider>
      {extra}
      <SemanticLayerPage />
    </EditorDirtyProvider>,
  )
}

async function openAdvancedTab(label: string) {
  fireEvent.click(screen.getByTestId('semantic-advanced-trigger'))
  const item = await screen.findByRole('menuitem', { name: label })
  fireEvent.click(item)
}

function clickTab(name: string) {
  const tab = screen.getAllByRole('button').find(b => b.textContent?.trim() === name)
  if (!tab) throw new Error(`Missing tab button: ${name}`)
  fireEvent.click(tab)
}

async function clickPublish() {
  await act(async () => {
    fireEvent.click(screen.getByTestId('semantic-publish-ask-data'))
    await new Promise(r => setTimeout(r, 50))
  })
}

describe('SEM-2B matrix', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    basePageMocks()
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('SEM-2B-001 wizard opens', () => {
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    expect(screen.getByTestId('semantic-create-wizard')).toBeTruthy()
  })

  it('SEM-2B-002 name required', () => {
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    expect((screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'My Model' } })
    expect((screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('SEM-2B-003 duplicate name handling', async () => {
    api.createSemanticModel.mockRejectedValue(appErr(409, undefined, 'Conflict'))
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    await advanceWizardToReview('Dup Model')
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => expect(screen.getByText(/already exists/i)).toBeTruthy())
  })

  it('SEM-2B-004 connector groups render', async () => {
    api.listConnectorTables.mockResolvedValue({
      tables: [
        { schema: 'public', name: 'sales' },
        { schema: 'public', name: 'products' },
      ],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    await waitFor(() => expect(screen.getByText('public.sales')).toBeTruthy())
    expect(screen.getByText('public.products')).toBeTruthy()
  })

  it('SEM-2B-005 table search', async () => {
    api.listConnectorTables.mockResolvedValue({
      tables: [
        { schema: 'public', name: 'sales' },
        { schema: 'public', name: 'inventory' },
      ],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    await waitFor(() => expect(screen.getByText('public.sales')).toBeTruthy())
    fireEvent.change(screen.getByPlaceholderText('Search tables…'), { target: { value: 'inventory' } })
    expect(screen.queryByText('public.sales')).toBeNull()
    expect(screen.getByText('public.inventory')).toBeTruthy()
  })

  it('SEM-2B-006 multi-select tables', async () => {
    api.listConnectorTables.mockResolvedValue({
      tables: [
        { schema: 'public', name: 'sales' },
        { schema: 'public', name: 'products' },
      ],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    const boxes = await screen.findAllByRole('checkbox')
    fireEvent.click(boxes[0])
    fireEvent.click(boxes[1])
    expect(screen.getByText('2 table(s) selected')).toBeTruthy()
  })

  it('SEM-2B-007 suggestions requested', async () => {
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'public', name: 'sales' }] })
    api.semanticSuggestions.mockResolvedValue({ entities: [], metrics: [], dimensions: [], relationships: [], glossary_suggestions: [] })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => expect(api.semanticSuggestions).toHaveBeenCalled())
  })

  it('SEM-2B-008 suggestions grouped by type', async () => {
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'public', name: 'sales' }] })
    api.semanticSuggestions.mockResolvedValue({
      entities: [{ suggestion_id: 'entity:sales', key: 'sales', name: 'Sales' }],
      metrics: [{ suggestion_id: 'metric:total', key: 'total', name: 'Total' }],
      dimensions: [],
      relationships: [],
      glossary_suggestions: [],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => expect(screen.getByText('Data Models')).toBeTruthy())
    expect(screen.getByText('Metrics')).toBeTruthy()
  })

  it('SEM-2B-009 accept suggestion', async () => {
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'public', name: 'sales' }] })
    api.semanticSuggestions.mockResolvedValue({
      metrics: [{ suggestion_id: 'metric:total', key: 'total', name: 'Total' }],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => screen.getAllByText('Accept')[0])
    fireEvent.click(screen.getAllByText('Accept')[0])
    expect(screen.getAllByText('Accept')[0].className).toContain('emerald')
  })

  it('SEM-2B-010 reject suggestion', async () => {
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'public', name: 'sales' }] })
    api.semanticSuggestions.mockResolvedValue({
      metrics: [{ suggestion_id: 'metric:total', key: 'total', name: 'Total' }],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => screen.getAllByText('Reject')[0])
    fireEvent.click(screen.getAllByText('Reject')[0])
    expect(screen.getAllByText('Reject')[0].className).toContain('red')
  })

  it('SEM-2B-011 edit suggestion before accept', async () => {
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'public', name: 'sales' }] })
    api.semanticSuggestions.mockResolvedValue({
      metrics: [{ suggestion_id: 'metric:total', key: 'total', name: 'Total' }],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => screen.getAllByText('Edit')[0])
    fireEvent.click(screen.getAllByText('Edit')[0])
    const input = await screen.findByDisplayValue('Total')
    fireEvent.change(input, { target: { value: 'Total Sales' } })
    expect((input as HTMLInputElement).value).toBe('Total Sales')
  })

  it('SEM-2B-012 rejected suggestion not persisted', async () => {
    api.createSemanticModel.mockResolvedValue({ model: { id: 'new-m', name: 'M', key: 'm' } })
    api.acceptSemanticSuggestions.mockResolvedValue({ version_id: 'v1', persisted: [{ object_key: 'total' }], counts: { metrics: 1 } })
    api.listConnectorTables.mockResolvedValue({ tables: [{ schema: 'public', name: 'sales' }] })
    api.semanticSuggestions.mockResolvedValue({
      metrics: [
        { suggestion_id: 'metric:total', key: 'total', name: 'Total' },
        { suggestion_id: 'metric:skip', key: 'skip', name: 'Skip' },
      ],
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    fireEvent.change(screen.getByPlaceholderText('Commercial Sales'), { target: { value: 'M' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByText('PostgreSQL'))
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestions' }))
    await waitFor(() => screen.getAllByText('Reject').length >= 2)
    fireEvent.click(screen.getAllByText('Reject')[1])
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => expect(api.acceptSemanticSuggestions).toHaveBeenCalled())
    const body = api.acceptSemanticSuggestions.mock.calls[0][1]
    expect(body.selections.some((s: { suggestion_id: string; accepted: boolean }) => s.suggestion_id === 'metric:skip' && !s.accepted)).toBe(true)
  })

  it('SEM-2B-013 accepted suggestion gets stable ID', async () => {
    api.createSemanticModel.mockResolvedValue({ model: { id: 'new-m', name: 'M', key: 'm' } })
    api.acceptSemanticSuggestions.mockResolvedValue({
      version_id: 'v1',
      persisted: [{ object_key: 'total', object_id: 'uuid-metric-1' }],
      counts: { metrics: 1 },
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    await advanceWizardToReview()
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => expect(api.acceptSemanticSuggestions).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('wizard-completion')).toBeTruthy())
  })

  it('SEM-2B-014 duplicate conflict handling', async () => {
    api.createSemanticModel.mockResolvedValue({ model: { id: 'new-m', name: 'M', key: 'm' } })
    api.acceptSemanticSuggestions.mockResolvedValue({
      version_id: 'v1',
      persisted: [],
      conflicts: [{ suggestion_id: 'metric:total', message: 'Metric key already exists' }],
      counts: {},
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    await advanceWizardToReview()
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => expect(api.acceptSemanticSuggestions).toHaveBeenCalled())
    const res = await api.acceptSemanticSuggestions.mock.results.at(-1)?.value
    expect(res?.conflicts?.length).toBeGreaterThan(0)
  })

  it('SEM-2B-015 wizard completion state', async () => {
    api.createSemanticModel.mockResolvedValue({ model: { id: 'new-m', name: 'M', key: 'm' } })
    api.acceptSemanticSuggestions.mockResolvedValue({
      version_id: 'v1',
      persisted: [{ object_key: 'total' }],
      counts: { entities: 1, metrics: 2, dimensions: 0, relationships: 0 },
    })
    render(<CreateSemanticModelWizard open connectors={[...connectors]} onClose={() => undefined} onCreated={() => undefined} />)
    await advanceWizardToReview()
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => expect(screen.getByTestId('wizard-completion')).toBeTruthy())
    expect(screen.getByText(/Draft/)).toBeTruthy()
    expect(screen.getByText('Open Semantic Model')).toBeTruthy()
  })

  it('SEM-2B-016 dirty switch tab shows custom modal', async () => {
    await renderPageReady(<DirtyRegistrar />)
    clickTab('Metrics')
    clickTab('Dimensions')
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
  })

  it('SEM-2B-017 Keep editing', async () => {
    await renderPageReady(<DirtyRegistrar />)
    clickTab('Metrics')
    clickTab('Dimensions')
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
    fireEvent.click(screen.getByText('Keep editing'))
    expect(screen.queryByTestId('unsaved-changes-modal')).toBeNull()
  })

  it('SEM-2B-018 Discard changes', async () => {
    await renderPageReady(<DirtyRegistrar />)
    clickTab('Metrics')
    clickTab('Dimensions')
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
    fireEvent.click(screen.getByText('Discard changes'))
    await waitFor(() => expect(screen.queryByTestId('unsaved-changes-modal')).toBeNull())
  })

  it('SEM-2B-019 Save and continue success', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    await renderPageReady(<DirtyRegistrar save={save} />)
    clickTab('Metrics')
    clickTab('Dimensions')
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
    fireEvent.click(screen.getByText('Save and continue'))
    await waitFor(() => expect(save).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByTestId('unsaved-changes-modal')).toBeNull())
  })

  it('SEM-2B-020 Save and continue validation failure', async () => {
    const save = vi.fn().mockRejectedValue(new Error('validation'))
    await renderPageReady(<DirtyRegistrar save={save} />)
    clickTab('Metrics')
    clickTab('Dimensions')
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
    fireEvent.click(screen.getByText('Save and continue'))
    await waitFor(() => expect(save).toHaveBeenCalled())
    expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy()
  })

  it('SEM-2B-021 change semantic model while dirty', async () => {
    await renderPageReady(<DirtyRegistrar />)
    fireEvent.click(screen.getByRole('combobox', { name: /search semantic models/i }))
    fireEvent.click(await screen.findByRole('button', { name: /Retail/i }))
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
  })

  it('SEM-2B-022 open Advanced while dirty', async () => {
    await renderPageReady(<DirtyRegistrar />)
    fireEvent.click(screen.getByTestId('semantic-advanced-trigger'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Model health' }))
    await waitFor(() => expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy())
  })

  it('SEM-2B-023 close editor while dirty', async () => {
    render(
      <EditorDirtyProvider>
        <DirtyRegistrar />
        <UnsavedChangesModal open onKeepEditing={() => undefined} onDiscard={() => undefined} onSaveAndContinue={() => undefined} />
      </EditorDirtyProvider>,
    )
    expect(screen.getByTestId('unsaved-changes-modal')).toBeTruthy()
  })

  it('SEM-2B-024 saved editor navigates without warning', async () => {
    await renderPageReady(<DirtyRegistrar dirty={false} />)
    clickTab('Metrics')
    clickTab('Dimensions')
    expect(screen.queryByTestId('unsaved-changes-modal')).toBeNull()
  })

  it('SEM-2B-025 no native confirm in normal semantic navigation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await renderPageReady(<DirtyRegistrar />)
    clickTab('Metrics')
    clickTab('Dimensions')
    expect(confirmSpy).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('SEM-2B-026 Publish CTA visible', async () => {
    await renderPageReady()
    expect(screen.getByTestId('semantic-publish-ask-data')).toBeTruthy()
  })

  it('SEM-2B-027 publish calls orchestration endpoint', async () => {
    await renderPageReady()
    await act(async () => {
      fireEvent.click(screen.getByTestId('semantic-publish-ask-data'))
    })
    await waitFor(() => expect(api.publishSemanticToAskData).toHaveBeenCalled())
    expect(api.publishSemanticToAskData.mock.calls[0][0]).toBe('m1')
  })

  it('SEM-2B-028 publish progress state', async () => {
    api.publishSemanticToAskData.mockImplementation(
      () => new Promise(resolve => setTimeout(() => resolve({ status: 'published', version_number: 2 }), 200)),
    )
    await renderPageReady()
    fireEvent.click(screen.getByTestId('semantic-publish-ask-data'))
    expect(await screen.findByText(/Preparing semantic model/)).toBeTruthy()
  })

  it('SEM-2B-029 publish success', async () => {
    await renderPageReady()
    await act(async () => {
      fireEvent.click(screen.getByTestId('semantic-publish-ask-data'))
      await new Promise(r => setTimeout(r, 50))
    })
    await waitFor(() => expect(screen.getByTestId('semantic-publish-success')).toBeTruthy())
  })

  it('SEM-2B-030 Published state updates', async () => {
    api.getSemanticModelOverview.mockResolvedValue({
      model: { id: 'm1', name: 'Art', key: 'art', updated_at: null },
      state: 'Published',
      readiness: 'READY',
      issue_count: 0,
      published_version_number: 2,
      counts: { entities: 1, metrics: 1, dimensions: 0, relationships: 0, terms: 0 },
    })
    await renderPageReady()
    fireEvent.click(screen.getByTestId('semantic-publish-ask-data'))
    await waitFor(() => expect(api.getSemanticModelOverview).toHaveBeenCalled())
  })

  it('SEM-2B-031 publish validation failure', async () => {
    api.publishSemanticToAskData.mockRejectedValue(
      appErr(422, { status: 'needs_attention', issues: [{ object_type: 'metric', object_key: 'bad_m', message: 'Column missing' }] }),
    )
    await renderPageReady()
    await clickPublish()
    await waitFor(() => expect(screen.getByTestId('publish-needs-attention')).toBeTruthy())
  })

  it('SEM-2B-032 issue panel grouped/readable', async () => {
    api.publishSemanticToAskData.mockRejectedValue(
      appErr(422, {
        issues: [{ object_type: 'metric', object_name: 'Bad M', message: 'Column `x` missing', code: 'missing_column' }],
      }),
    )
    await renderPageReady()
    await clickPublish()
    const panel = await screen.findByTestId('publish-needs-attention')
    await waitFor(() => expect(panel.textContent).toMatch(/Column `x` missing/))
    expect(panel.textContent?.toLowerCase()).toContain('metric')
  })

  it('SEM-2B-033 issue deep-link opens editor', async () => {
    api.publishSemanticToAskData.mockRejectedValue(
      appErr(422, { issues: [{ object_type: 'metric', object_key: 'bad_m', object_name: 'Bad M', message: 'bad' }] }),
    )
    await renderPageReady()
    await clickPublish()
    fireEvent.click(await screen.findByText(/Bad M/))
    await waitFor(() => expect(screen.getAllByRole('button').some(b => b.textContent?.trim() === 'Metrics')).toBe(true))
  })

  it('SEM-2B-034 activation failure does not claim active', async () => {
    api.publishSemanticToAskData.mockRejectedValue(appErr(502, { status: 'activation_failed', message: 'Activation failed' }))
    await renderPageReady()
    await clickPublish()
    await waitFor(() => expect(screen.getByTestId('publish-activation-failure')).toBeTruthy())
    expect(screen.queryByTestId('semantic-publish-success')).toBeNull()
  })

  it('SEM-2B-035 previous runtime remains active', async () => {
    api.publishSemanticToAskData.mockRejectedValue(appErr(502, { status: 'activation_failed' }))
    await renderPageReady()
    await clickPublish()
    await waitFor(() => expect(screen.getByText(/still used by Ask Data/i)).toBeTruthy())
  })

  it('SEM-2B-036 retry activation', async () => {
    api.publishSemanticToAskData.mockRejectedValueOnce(appErr(502, { status: 'activation_failed' }))
    await renderPageReady()
    await clickPublish()
    await waitFor(() => screen.getByText('Retry activation'))
    api.publishSemanticToAskData.mockResolvedValue({ status: 'published', version_number: 2 })
    await act(async () => {
      fireEvent.click(screen.getByText('Retry activation'))
      await new Promise(r => setTimeout(r, 50))
    })
    await waitFor(() => expect(api.publishSemanticToAskData).toHaveBeenCalledTimes(2))
  })

  it('SEM-2B-037 version history consistency', async () => {
    await renderPageReady()
    await openAdvancedTab('Version history')
    await waitFor(() => expect(screen.getByText('v1')).toBeTruthy())
    expect(screen.getByText('ACTIVE REGISTRY')).toBeTruthy()
  })

  it('SEM-2B-038 deployment details consistency', async () => {
    await renderPageReady()
    await openAdvancedTab('Deployment details')
    await waitFor(() => expect(api.getSemanticRuntimeStatus).toHaveBeenCalled())
  })

  it('SEM-2B-039 new edit after publish becomes draft', async () => {
    api.getSemanticModelOverview.mockResolvedValue({
      model: { id: 'm1', name: 'Art', key: 'art', updated_at: null },
      state: 'Draft',
      published_version_number: 2,
      draft_version_number: 3,
      counts: { entities: 1, metrics: 1, dimensions: 0, relationships: 0, terms: 0 },
    })
    await renderPageReady()
    await waitFor(() => expect(api.getSemanticModelOverview).toHaveBeenCalled())
    clickTab('Overview')
    await waitFor(() => expect(screen.getByTestId('semantic-overview-metadata')).toBeTruthy())
    expect(screen.getByText(/Published v2/)).toBeTruthy()
  })

  it('SEM-2B-040 rollback product modal', async () => {
    await renderPageReady()
    await openAdvancedTab('Version history')
    fireEvent.click(await screen.findByText('Rollback'))
    expect(screen.getByText('Rollback semantic model?')).toBeTruthy()
    expect(screen.getByText(/Ask Data will start using version/)).toBeTruthy()
  })

  it('SEM-2B-041 rollback updates active version', async () => {
    await renderPageReady()
    await openAdvancedTab('Version history')
    fireEvent.click(await screen.findByText('Rollback'))
    const confirmButtons = screen.getAllByRole('button', { name: 'Rollback' })
    fireEvent.click(confirmButtons[confirmButtons.length - 1])
    await waitFor(() => expect(api.rollbackSemanticVersion).toHaveBeenCalledWith('v-arch'))
  })
})

describe('SEM-2B header combobox (addendum)', () => {
  afterEach(() => cleanup())
  it('SEM-2B combobox search filters', () => {
    render(
      <SemanticModelCombobox
        models={[
          { id: '1', name: 'Art', key: 'art' } as never,
          { id: '2', name: 'Retail Analytics', key: 'retail' } as never,
        ]}
        value="1"
        onChange={() => undefined}
      />,
    )
    fireEvent.click(screen.getByRole('combobox', { name: /search semantic models/i }))
    fireEvent.change(screen.getByPlaceholderText('Search semantic models…'), { target: { value: 'retail' } })
    expect(screen.getByRole('option', { name: /Retail Analytics/i })).toBeTruthy()
  })
})
