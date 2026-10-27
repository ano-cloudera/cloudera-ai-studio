'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { PageCenter } from '../components/PageCenter'
import { ServiceErrorState } from '../components/ServiceErrorState'
import { appConfig } from '../config/appConfig'
import { api } from '../lib/api'
import { isAppApiError, safeErrorMessage, toAppApiError, type AppApiError } from '../lib/apiError'
import { SemanticModelCombobox } from '../components/semantic/SemanticModelCombobox'
import { ProductConfirmModal } from '../components/semantic/ProductConfirmModal'
import type {
  OssieImportSummary,
  OssieImportSource,
  SemanticArtifactPreview,
  SemanticDimensionRecord,
  SemanticEntityRecord,
  SemanticMetricRecord,
  SemanticModelRecord,
  SemanticRelationshipRecord,
  SemanticTermRecord,
  SemanticValidationResult,
  SemanticValidationRunRecord,
  SemanticVersionDiff,
  SemanticRuntimeDeploymentRecord,
  SemanticRuntimeStatus,
  SemanticVersionRecord,
  ValidatorHealth,
} from '../types/api'
import { connectorTypeLabel } from './connectors/connectorUi'
import { EntityConnectorSourceEditor } from './semantic/EntityConnectorSourceEditor'
import { buildVersionCompare } from './semantic/semanticLayerCompare'
import { SemanticOverviewPanel } from './semantic/SemanticOverviewPanel'
import { UnsavedChangesModal } from '../components/semantic/UnsavedChangesModal'
import { CreateSemanticModelWizard } from './semantic/CreateSemanticModelWizard'
import { DataModelsTab } from './semantic/authoring/DataModelsTab'
import { DimensionsTab, GlossaryTab, MetricsTab, RelationshipsTab } from './semantic/authoring/SemanticOtherTabs'
import { SemanticArtifactPreviewPanel } from './semantic/authoring/SemanticArtifactPreviewPanel'
import { SemanticImportOssiePanel } from './semantic/authoring/SemanticImportOssiePanel'
import { SemanticVersionHistoryTable } from './semantic/authoring/SemanticVersionHistoryTable'
import { useEditorDirtyRegistry } from './semantic/authoring/EditorDirtyContext'
import type { ConnectorRecord, SemanticOverviewPayload } from '../types/api'

const PRIMARY_TABS = [
  'overview',
  'entities',
  'metrics',
  'dimensions',
  'relationships',
  'glossary',
] as const

const ADVANCED_TABS = ['validation', 'versions', 'runtime', 'artifact', 'import'] as const

const TABS = [...PRIMARY_TABS, ...ADVANCED_TABS] as const

type Tab = (typeof TABS)[number]

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  entities: 'Data Models',
  metrics: 'Metrics',
  dimensions: 'Dimensions',
  relationships: 'Relationships',
  glossary: 'Glossary',
  validation: 'Model health',
  versions: 'Version history',
  runtime: 'Deployment details',
  artifact: 'Preview semantic artifact',
  import: 'Import OSSIE',
}

function physicalSource(entity: SemanticEntityRecord): string {
  const parts = [entity.catalog, entity.schema, entity.table_name || entity.view_name].filter(Boolean)
  return parts.join('.') || '—'
}

function entityConnectorLabel(entity: SemanticEntityRecord, connectors: ConnectorRecord[]): string {
  if (!entity.connection_id) return entity.source_type
  const conn = connectors.find(c => c.id === entity.connection_id)
  return conn ? `${connectorTypeLabel(conn.connector_type)} · ${conn.name}` : 'Data source'
}

function matchesSearch(needle: string, ...parts: (string | null | undefined)[]): boolean {
  if (!needle) return true
  const n = needle.toLowerCase()
  return parts.some(p => (p ?? '').toLowerCase().includes(n))
}

function parseSynonyms(text: string): string[] {
  return text
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
}

function synonymsText(values: string[] | undefined): string {
  return (values ?? []).join(', ')
}

export function SemanticLayerPage() {
  const searchParams = useSearchParams()
  const editorDirty = useEditorDirtyRegistry()
  const [models, setModels] = useState<SemanticModelRecord[]>([])
  const [modelId, setModelId] = useState('')
  const [versions, setVersions] = useState<SemanticVersionRecord[]>([])
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const [error, setError] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [search, setSearch] = useState('')
  const [validation, setValidation] = useState<SemanticValidationResult | null>(null)
  const [validationMode, setValidationMode] = useState<'full' | 'structural' | 'source'>('full')
  const [validationProgress, setValidationProgress] = useState('')
  const [validationRuns, setValidationRuns] = useState<SemanticValidationRunRecord[]>([])
  const [validatorHealth, setValidatorHealth] = useState<ValidatorHealth | null>(null)
  const [publishDiff, setPublishDiff] = useState<SemanticVersionDiff | null>(null)
  const [artifact, setArtifact] = useState<SemanticArtifactPreview | null>(null)
  const [publishNotice, setPublishNotice] = useState('')
  const [runtimeStatus, setRuntimeStatus] = useState<SemanticRuntimeStatus | null>(null)
  const [runtimeDeployments, setRuntimeDeployments] = useState<SemanticRuntimeDeploymentRecord[]>([])
  const [runtimeDryRun, setRuntimeDryRun] = useState<{ result: string; checksum: string } | null>(null)
  const [runtimeNotice, setRuntimeNotice] = useState('')

  const [entities, setEntities] = useState<SemanticEntityRecord[]>([])
  const [metrics, setMetrics] = useState<SemanticMetricRecord[]>([])
  const [dimensions, setDimensions] = useState<SemanticDimensionRecord[]>([])
  const [relationships, setRelationships] = useState<SemanticRelationshipRecord[]>([])
  const [terms, setTerms] = useState<SemanticTermRecord[]>([])
  const [connectors, setConnectors] = useState<ConnectorRecord[]>([])
  const [entityKeys, setEntityKeys] = useState<string[]>([])
  const [metricKeys, setMetricKeys] = useState<string[]>([])
  const [dimensionKeys, setDimensionKeys] = useState<string[]>([])

  const [activeSnapshot, setActiveSnapshot] = useState<{
    entities: SemanticEntityRecord[]
    metrics: SemanticMetricRecord[]
    dimensions: SemanticDimensionRecord[]
    relationships: SemanticRelationshipRecord[]
    terms: SemanticTermRecord[]
  } | null>(null)

  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null)
  const [selectedMetricId, setSelectedMetricId] = useState<string | null>(null)
  const [selectedDimensionId, setSelectedDimensionId] = useState<string | null>(null)
  const [selectedRelationshipId, setSelectedRelationshipId] = useState<string | null>(null)
  const [selectedTermId, setSelectedTermId] = useState<string | null>(null)

  const [importSource, setImportSource] = useState<OssieImportSource | null>(null)
  const [importKey, setImportKey] = useState('tempo_core')
  const [importSummary, setImportSummary] = useState<OssieImportSummary | null>(null)

  const [createModelOpen, setCreateModelOpen] = useState(false)
  const [createModelName, setCreateModelName] = useState('')
  const [createModelKey, setCreateModelKey] = useState('')
  const [overview, setOverview] = useState<SemanticOverviewPayload | null>(null)
  const [publishProgress, setPublishProgress] = useState('')
  const [publishSuccess, setPublishSuccess] = useState<string | null>(null)
  const [publishIssues, setPublishIssues] = useState<Array<Record<string, unknown>>>([])
  const [unsavedModalOpen, setUnsavedModalOpen] = useState(false)
  const [pendingTab, setPendingTab] = useState<Tab | null>(null)
  const [pendingModelId, setPendingModelId] = useState<string | null>(null)
  const [pendingSaveAction, setPendingSaveAction] = useState<(() => Promise<void>) | null>(null)
  const [activationFailure, setActivationFailure] = useState<string | null>(null)
  const [confirmModal, setConfirmModal] = useState<{
    title: string
    message: string
    confirmLabel: string
    tone?: 'danger' | 'primary'
    onConfirm: () => Promise<void>
  } | null>(null)

  const model = useMemo(() => models.find(m => m.id === modelId) ?? null, [models, modelId])
  const draftVersion = useMemo(() => {
    const drafts = versions.filter(v => v.status === 'DRAFT')
    if (!drafts.length) return null
    return drafts.reduce((latest, row) =>
      (row.version_number ?? 0) >= (latest.version_number ?? 0) ? row : latest,
    )
  }, [versions])
  const activeVersion = useMemo(
    () => versions.find(v => v.status === 'ACTIVE') ?? versions.find(v => v.id === model?.active_version_id) ?? null,
    [versions, model],
  )
  const displayVersionId = draftVersion?.id ?? activeVersion?.id ?? null
  const isEditable = Boolean(draftVersion)

  const refreshModels = useCallback(async () => {
    const { models: rows } = await api.listSemanticModels()
    setModels(rows)
    setLoadError(null)
    setModelId(prev => prev || rows[0]?.id || '')
  }, [])

  const refreshVersions = useCallback(async (mid: string) => {
    const { versions: rows } = await api.listSemanticVersions(mid)
    setVersions(rows)
  }, [])

  const refreshRuntime = useCallback(async (modelKey?: string) => {
    const [status, deps] = await Promise.all([
      api.getSemanticRuntimeStatus(modelKey),
      api.listSemanticRuntimeDeployments(modelKey),
    ])
    setRuntimeStatus(status)
    setRuntimeDeployments(deps.deployments)
  }, [])

  const loadVersionObjects = useCallback(async (versionId: string) => {
    const [e, m, d, r, t] = await Promise.all([
      api.listSemanticEntities(versionId),
      api.listSemanticMetrics(versionId),
      api.listSemanticDimensions(versionId),
      api.listSemanticRelationships(versionId),
      api.listSemanticTerms(versionId),
    ])
    setEntities(e.entities)
    setMetrics(m.metrics)
    setDimensions(d.dimensions)
    setRelationships(r.relationships)
    setTerms(t.terms)
  }, [])

  useEffect(() => {
    setLoading(true)
    refreshModels()
      .catch(err => {
        const apiErr = toAppApiError(err)
        setLoadError(apiErr)
        setError(safeErrorMessage(err, 'Failed to load'))
      })
      .finally(() => setLoading(false))
  }, [refreshModels])

  useEffect(() => {
    const fromUrl = searchParams.get('model')
    if (!fromUrl) return
    if (models.some(m => m.id === fromUrl)) setModelId(fromUrl)
  }, [searchParams, models])

  useEffect(() => {
    if (!appConfig.features.connectors) return
    api.listConnectors().then(r => setConnectors(r.connectors)).catch(() => setConnectors([]))
  }, [])

  const connectorDataSources = useMemo(() => {
    const ids = new Set(entities.map(e => e.connection_id).filter(Boolean) as string[])
    return connectors.filter(c => ids.has(c.id))
  }, [entities, connectors])

  useEffect(() => {
    if (!modelId) {
      setOverview(null)
      return
    }
    api.getSemanticModelOverview(modelId).then(setOverview).catch(() => setOverview(null))
  }, [modelId, versions, validation, publishSuccess])

  useEffect(() => {
    if (!modelId) return
    setDirty(false)
    setValidation(null)
    setArtifact(null)
    setPublishDiff(null)
    refreshVersions(modelId).catch(err => setError(err instanceof Error ? err.message : 'Failed to load versions'))
  }, [modelId, refreshVersions])

  useEffect(() => {
    if (!model?.key) return
    refreshRuntime(model.key).catch(() => setRuntimeStatus(null))
  }, [model?.key, refreshRuntime, versions])

  useEffect(() => {
    api.getSemanticValidatorHealth().then(setValidatorHealth).catch(() => setValidatorHealth(null))
  }, [])

  useEffect(() => {
    if (tab !== 'validation' || !displayVersionId) return
    api.listSemanticValidationRuns(displayVersionId, 10).then(r => setValidationRuns(r.runs)).catch(() => undefined)
  }, [tab, displayVersionId, validation?.run_id])

  const refreshAuthoringKeys = useCallback(async () => {
    if (!displayVersionId) {
      setEntityKeys([])
      setMetricKeys([])
      setDimensionKeys([])
      return
    }
    const [e, m, d] = await Promise.all([
      api.listSemanticEntities(displayVersionId, { page: 1, page_size: 200 }),
      api.listSemanticMetrics(displayVersionId, { page: 1, page_size: 200 }),
      api.listSemanticDimensions(displayVersionId, { page: 1, page_size: 200 }),
    ])
    setEntityKeys(e.entities.map(x => x.key))
    setMetricKeys(m.metrics.map(x => x.key))
    setDimensionKeys(d.dimensions.map(x => x.key))
    await loadVersionObjects(displayVersionId)
    if (modelId) await refreshVersions(modelId)
    if (modelId) {
      const ov = await api.getSemanticModelOverview(modelId)
      setOverview(ov)
    }
  }, [displayVersionId, loadVersionObjects, modelId, refreshVersions])

  useEffect(() => {
    if (!displayVersionId) {
      setEntityKeys([])
      setMetricKeys([])
      setDimensionKeys([])
    } else {
      void refreshAuthoringKeys()
    }
  }, [displayVersionId, refreshAuthoringKeys])

  useEffect(() => {
    if (!displayVersionId) {
      setEntities([])
      setMetrics([])
      setDimensions([])
      setRelationships([])
      setTerms([])
      return
    }
    loadVersionObjects(displayVersionId).catch(err => setError(err instanceof Error ? err.message : 'Failed to load objects'))
  }, [displayVersionId, loadVersionObjects])

  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (dirty || editorDirty.isDirty()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty, editorDirty])

  useEffect(() => {
    if (!activeVersion?.id || activeVersion.id === displayVersionId) {
      setActiveSnapshot(null)
      return
    }
    Promise.all([
      api.listSemanticEntities(activeVersion.id),
      api.listSemanticMetrics(activeVersion.id),
      api.listSemanticDimensions(activeVersion.id),
      api.listSemanticRelationships(activeVersion.id),
      api.listSemanticTerms(activeVersion.id),
    ])
      .then(([e, m, d, r, t]) => {
        setActiveSnapshot({
          entities: e.entities,
          metrics: m.metrics,
          dimensions: d.dimensions,
          relationships: r.relationships,
          terms: t.terms,
        })
      })
      .catch(() => setActiveSnapshot(null))
  }, [activeVersion?.id, displayVersionId])

  function hasUnsavedEdits() {
    return dirty || editorDirty.isDirty()
  }

  function switchTab(next: Tab) {
    if (hasUnsavedEdits()) {
      setPendingTab(next)
      setPendingModelId(null)
      setUnsavedModalOpen(true)
      return
    }
    setAdvancedOpen(false)
    setTab(next)
  }

  function openAdvancedTab(next: Tab) {
    if (ADVANCED_TABS.includes(next as (typeof ADVANCED_TABS)[number])) {
      switchTab(next)
      return
    }
    setTab(next)
  }

  function requestModelChange(nextId: string) {
    if (hasUnsavedEdits()) {
      setPendingModelId(nextId)
      setPendingTab(null)
      setUnsavedModalOpen(true)
      return
    }
    setModelId(nextId)
  }

  async function handlePublishToAskData() {
    if (!model) return
    setSaving(true)
    setError('')
    setPublishSuccess(null)
    setPublishIssues([])
    setActivationFailure(null)
    const progressSteps = ['Preparing semantic model…', 'Checking definitions…', 'Publishing…', 'Activating for Ask Data…']
    let step = 0
    setPublishProgress(progressSteps[step])
    const timer = window.setInterval(() => {
      step = Math.min(step + 1, progressSteps.length - 1)
      setPublishProgress(progressSteps[step])
    }, 900)
    try {
      const vid = draftVersion?.id
      const result = await api.publishSemanticToAskData(model.id, vid ? { version_id: vid } : {})
      window.clearInterval(timer)
      setPublishProgress('')
      setPublishSuccess(`Published to Ask Data — Version ${result.version_number ?? ''} is now active.`)
      await refreshVersions(model.id)
      await refreshModels()
      if (model.key) await refreshRuntime(model.key)
      const ov = await api.getSemanticModelOverview(model.id)
      setOverview(ov)
      setDirty(false)
    } catch (err: unknown) {
      window.clearInterval(timer)
      setPublishProgress('')
      const detail = isAppApiError(err) ? (err.details as Record<string, unknown> | undefined) : undefined
      if (detail && Array.isArray(detail.issues)) {
        setPublishIssues(detail.issues as Array<Record<string, unknown>>)
        setError(`${(detail.issues as unknown[]).length} issue(s) need attention before publishing.`)
        setTab('validation')
      } else if (detail?.status === 'activation_failed' || (isAppApiError(err) && err.status === 502)) {
        setActivationFailure(
          String(detail?.message ?? 'Publish could not be activated. Your previous active semantic version is still used by Ask Data.'),
        )
        if (model.key) await refreshRuntime(model.key)
        setTab('runtime')
      } else {
        setError(isAppApiError(err) ? err.message : err instanceof Error ? err.message : 'Publish to Ask Data failed')
      }
    } finally {
      setSaving(false)
    }
  }

  function openPublishIssue(issue: Record<string, unknown>) {
    const type = String(issue.object_type ?? '')
    const key = String(issue.object_key ?? issue.object_name ?? '')
    if (type.includes('metric')) {
      switchTab('metrics')
      const row = metrics.find(m => m.key === key || m.name === key)
      if (row) setSelectedMetricId(row.id)
    } else if (type.includes('dimension')) {
      switchTab('dimensions')
      const row = dimensions.find(d => d.key === key || d.name === key)
      if (row) setSelectedDimensionId(row.id)
    } else if (type.includes('relationship')) {
      switchTab('relationships')
      const row = relationships.find(r => r.key === key || r.name === key)
      if (row) setSelectedRelationshipId(row.id)
    } else if (type.includes('entity')) {
      switchTab('entities')
      const row = entities.find(e => e.key === key || e.name === key)
      if (row) setSelectedEntityId(row.id)
    } else {
      switchTab('validation')
    }
  }

  async function ensureDraftVersionId(): Promise<string> {
    if (!model) throw new Error('No semantic model selected')
    if (draftVersion) return draftVersion.id
    if (activeVersion) {
      const { version } = await api.cloneSemanticVersion(activeVersion.id)
      await refreshVersions(model.id)
      return version.id
    }
    const { version } = await api.createSemanticVersion(model.id)
    await refreshVersions(model.id)
    return version.id
  }

  async function handleCreateDraft() {
    if (!model) return
    setSaving(true)
    setError('')
    try {
      await ensureDraftVersionId()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create draft')
    } finally {
      setSaving(false)
    }
  }

  async function runValidate(mode: 'full' | 'structural' | 'source' = validationMode) {
    const vid = draftVersion?.id ?? displayVersionId
    if (!vid) return
    setSaving(true)
    setValidationProgress(mode === 'structural' ? 'Validating structure…' : mode === 'source' ? 'Checking sources…' : 'Running full validation…')
    try {
      const result = await api.validateSemanticVersion(vid, { mode })
      setValidation(result)
      setValidationProgress('')
      const runs = await api.listSemanticValidationRuns(vid, 10)
      setValidationRuns(runs.runs)
      setTab('validation')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed')
      setValidationProgress('')
    } finally {
      setSaving(false)
    }
  }

  async function loadArtifactPreview() {
    const vid = draftVersion?.id ?? displayVersionId
    if (!vid) return
    setSaving(true)
    try {
      const preview = await api.previewSemanticArtifact(vid)
      setArtifact(preview)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Preview failed')
    } finally {
      setSaving(false)
    }
  }

  async function openArtifactPreviewTab() {
    setAdvancedOpen(false)
    switchTab('artifact')
    await loadArtifactPreview()
  }

  async function handlePublish() {
    if (!draftVersion) return
    setSaving(true)
    setError('')
    setPublishNotice('')
    try {
      const result = await api.validateSemanticVersion(draftVersion.id, { mode: 'full' })
      setValidation(result)
      if (!result.valid || result.readiness === 'NOT_READY') {
        setError('Publish blocked: fix validation errors first.')
        setTab('validation')
        return
      }
      if (activeVersion) {
        const diff = await api.getSemanticVersionDiff(draftVersion.id, activeVersion.id)
        setPublishDiff(diff)
        const breaking = diff.breaking_changes?.length ?? 0
        const msg = [
          `Readiness: ${result.readiness ?? 'unknown'}`,
          breaking ? `${breaking} potentially breaking change(s)` : 'No breaking changes detected',
          result.warnings.length ? `${result.warnings.length} warning(s)` : '',
          'Registry publish only — Ask Data runtime will not switch.',
        ]
          .filter(Boolean)
          .join('\n')
        setConfirmModal({
          title: 'Publish registry version?',
          message: msg,
          confirmLabel: 'Publish',
          onConfirm: async () => {
            await api.publishSemanticVersion(draftVersion.id)
            if (modelId) await refreshVersions(modelId)
            await refreshModels()
            setPublishNotice('Registry version is ACTIVE. Use Publish to Ask Data for Ask Data activation.')
            setDirty(false)
          },
        })
        return
      }
      await api.publishSemanticVersion(draftVersion.id)
      if (modelId) await refreshVersions(modelId)
      await refreshModels()
      setPublishNotice('Registry version is ACTIVE. Use Activate Runtime when ready — publish does not switch Ask Data.')
      setDirty(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setSaving(false)
    }
  }

  async function runRuntimeDryRun() {
    if (!activeVersion || !model?.key) return
    setSaving(true)
    setRuntimeDryRun(null)
    setRuntimeNotice('')
    setError('')
    try {
      const staged = await api.stageSemanticRuntime(activeVersion.id)
      const dry = await api.dryRunSemanticRuntimeActivation(staged.deployment.id)
      setRuntimeDryRun({ result: dry.result, checksum: dry.artifact_checksum })
      setRuntimeNotice('Dry run: artifact staged, validated, and smoke-tested. No runtime switch performed.')
      await refreshRuntime(model.key)
      setTab('runtime')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dry run failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleActivateRuntime() {
    if (!activeVersion || !model?.key) return
    const readiness = activeVersion.activation_readiness ?? validation?.readiness
    if (readiness === 'NOT_READY') {
      setError('Activation blocked: version is NOT_READY.')
      return
    }
    setSaving(true)
    setError('')
    setRuntimeNotice('')
    try {
      let deploymentId = runtimeDeployments.find(
        d => d.semantic_version_id === activeVersion.id && ['STAGED', 'READY', 'VALIDATING'].includes(d.status),
      )?.id
      if (!deploymentId) {
        const staged = await api.stageSemanticRuntime(activeVersion.id)
        deploymentId = staged.deployment.id
      }
      const dry = await api.dryRunSemanticRuntimeActivation(deploymentId)
      if (dry.result !== 'READY_TO_ACTIVATE') {
        setError('Activation blocked by pre-checks.')
        return
      }
      const breaking = publishDiff?.breaking_changes?.length ?? 0
      const msg = [
        `Semantic version: v${activeVersion.version_number}`,
        `Readiness: ${readiness ?? 'unknown'}`,
        `Artifact checksum: ${dry.artifact_checksum}`,
        `Current runtime: v${runtimeStatus?.runtime_active_version ?? 'legacy'}`,
        `Target runtime: v${activeVersion.version_number}`,
        breaking ? 'This version contains breaking semantic changes and may affect Ask Data behavior.' : '',
      ]
        .filter(Boolean)
        .join('\n')
      setConfirmModal({
        title: 'Activate runtime?',
        message: msg,
        confirmLabel: 'Activate',
        onConfirm: async () => {
          await api.activateSemanticRuntimeDeployment(deploymentId)
          setRuntimeNotice(`Runtime active: v${activeVersion.version_number}`)
          await refreshRuntime(model.key)
          setTab('runtime')
        },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed')
    } finally {
      setSaving(false)
    }
  }

  async function openImportTab() {
    setImportSummary(null)
    setAdvancedOpen(false)
    switchTab('import')
    try {
      const source = await api.getOssieImportSource()
      setImportSource(source)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load OSSIE source')
    }
  }

  async function runImport() {
    setSaving(true)
    setError('')
    try {
      const summary = await api.importOssieSemantics({ model_key: importKey.trim(), model_name: importKey.trim() })
      setImportSummary(summary)
      if (summary.semantic_model_id) {
        setModelId(summary.semantic_model_id)
        await refreshModels()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setSaving(false)
    }
  }

  async function saveEntity(entity: SemanticEntityRecord, patch: Partial<SemanticEntityRecord>) {
    const vid = await ensureDraftVersionId()
    await api.patchSemanticEntity(vid, entity.id, {
      name: patch.name,
      description: patch.description,
      source_type: patch.source_type,
      catalog: patch.catalog,
      db_schema: patch.schema,
      table_name: patch.table_name,
      view_name: patch.view_name,
      primary_key: patch.primary_key,
      connection_id: patch.connection_id,
    })
    await loadVersionObjects(vid)
    await refreshVersions(modelId)
    setDirty(false)
  }

  async function saveMetric(metric: SemanticMetricRecord, patch: Partial<SemanticMetricRecord> & { synonymsText?: string }) {
    const vid = await ensureDraftVersionId()
    await api.patchSemanticMetric(vid, metric.id, {
      name: patch.name,
      description: patch.description,
      business_definition: patch.business_definition,
      expression: patch.expression,
      aggregation: patch.aggregation,
      source_entity_key: patch.source_entity_key,
      format: patch.format,
      unit: patch.unit,
      synonyms: patch.synonymsText != null ? parseSynonyms(patch.synonymsText) : patch.synonyms,
    })
    await loadVersionObjects(vid)
    await refreshVersions(modelId)
    setDirty(false)
  }

  const headerStatusBadge = useMemo(() => {
    if (publishIssues.length) return 'Needs attention'
    const state = overview?.state
    if (state === 'Published' || state === 'Needs attention') return state
    if (overview?.published_version_number != null && state !== 'Draft' && state !== 'Ready') return state
    return null
  }, [overview, publishIssues.length])

  const compareSections = useMemo(() => {
    if (!draftVersion || !activeSnapshot) return []
    return buildVersionCompare({
      draftEntities: entities,
      activeEntities: activeSnapshot.entities,
      draftMetrics: metrics,
      activeMetrics: activeSnapshot.metrics,
      draftDimensions: dimensions,
      activeDimensions: activeSnapshot.dimensions,
      draftRelationships: relationships,
      activeRelationships: activeSnapshot.relationships,
      draftTerms: terms,
      activeTerms: activeSnapshot.terms,
    })
  }, [draftVersion, activeSnapshot, entities, metrics, dimensions, relationships, terms])

  const filteredEntities = entities.filter(e =>
    matchesSearch(search, e.name, e.key, e.description, physicalSource(e)),
  )
  const filteredMetrics = metrics.filter(m =>
    matchesSearch(search, m.name, m.key, m.business_definition, ...m.synonyms),
  )
  const filteredDimensions = dimensions.filter(d =>
    matchesSearch(search, d.name, d.key, d.description, ...d.synonyms),
  )
  const filteredRelationships = relationships.filter(r =>
    matchesSearch(search, r.name, r.key, r.from_entity_key, r.to_entity_key),
  )
  const filteredTerms = terms.filter(t => matchesSearch(search, t.term, t.key, t.definition, ...t.synonyms))

  if (loading && !models.length) {
    return (
      <PageCenter>
        <p className="text-sm text-slate-600">Loading semantic layer…</p>
      </PageCenter>
    )
  }

  if (loadError && !models.length && !loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <ServiceErrorState
          title="Unable to load Semantic Layer"
          message="We couldn't reach the backend service."
          error={loadError}
          onRetry={() => {
            setLoading(true)
            refreshModels()
              .catch(err => setLoadError(toAppApiError(err)))
              .finally(() => setLoading(false))
          }}
        />
      </div>
    )
  }

  const needsRuntimeActivation =
    Boolean(activeVersion && runtimeStatus) &&
    runtimeStatus!.registry_active_version != null &&
    runtimeStatus!.runtime_active_version != null &&
    runtimeStatus!.registry_active_version !== runtimeStatus!.runtime_active_version

  const lifecyclePrimary = (() => {
    if (!model) return null
    if (draftVersion) {
      if (!validation?.valid) {
        return { label: 'Validate', run: () => void runValidate() }
      }
      return { label: 'Publish', run: handlePublish }
    }
    if (activeVersion && needsRuntimeActivation) {
      if (!runtimeDryRun) {
        return { label: 'Validate for activation', run: runRuntimeDryRun }
      }
      return { label: 'Activate runtime', run: handleActivateRuntime }
    }
    if (!draftVersion) {
      return {
        label: activeVersion ? 'Create draft from published' : 'Create initial draft',
        run: handleCreateDraft,
      }
    }
    return null
  })()

  const lifecycleSteps = ['Draft', 'Validate', 'Publish', 'Activate'] as const
  const activeStepIndex = !draftVersion && !activeVersion ? 0 : !validation?.valid && draftVersion ? 1 : draftVersion && validation?.valid ? 2 : needsRuntimeActivation ? 3 : 2

  return (
    <PageCenter className="flex h-full flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="type-app-title text-xl">Semantic Layer</h1>
          <p className="text-sm text-slate-600">Configure trusted business definitions for Ask Data.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="semantic-create-model"
            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-cloudera-navy shadow-sm hover:bg-slate-50"
            onClick={() => setCreateModelOpen(true)}
          >
            Create semantic model
          </button>
        </div>
      </div>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div> : null}
      {publishSuccess ? (
        <div
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
          data-testid="semantic-publish-success"
        >
          {publishSuccess}
        </div>
      ) : null}
      {publishProgress ? (
        <div className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-900">{publishProgress}</div>
      ) : null}
      {activationFailure ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" data-testid="publish-activation-failure">
          <div className="font-semibold">Publish could not be activated</div>
          <p className="mt-1 text-xs">{activationFailure}</p>
          <div className="mt-2 flex gap-2">
            <button type="button" className="h-8 rounded-lg border border-red-200 bg-white px-2 text-xs font-semibold" onClick={() => void handlePublishToAskData()}>
              Retry activation
            </button>
            <button type="button" className="h-8 rounded-lg border border-red-200 bg-white px-2 text-xs font-semibold" onClick={() => openAdvancedTab('runtime')}>
              View deployment details
            </button>
          </div>
        </div>
      ) : null}
      {publishIssues.length ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950" data-testid="publish-needs-attention">
          <div className="font-semibold">{publishIssues.length} issue(s) need attention</div>
          <ul className="mt-2 space-y-1 text-xs">
            {publishIssues.slice(0, 8).map((issue, idx) => (
              <li key={idx}>
                <button type="button" className="text-left hover:underline" onClick={() => openPublishIssue(issue)}>
                  <span className="font-semibold">{String(issue.object_type ?? 'object')}: {String(issue.object_name ?? issue.object_key ?? 'Item')}</span>
                  <div>{String(issue.message ?? '')}</div>
                  {issue.code ? <div className="text-[10px] text-slate-500">{String(issue.code)}</div> : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {publishNotice ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">{publishNotice}</div>
      ) : null}

      <div
        className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
        data-testid="semantic-model-toolbar"
      >
        <SemanticModelCombobox models={models} value={modelId} onChange={requestModelChange} />
        {headerStatusBadge ? (
          <div
            data-testid="semantic-header-status-badge"
            className={`mb-3 shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
              headerStatusBadge === 'Needs attention' ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-800'
            }`}
          >
            {headerStatusBadge}
          </div>
        ) : null}
        <button
          type="button"
          data-testid="semantic-publish-ask-data"
          className="btn-primary mb-0.5 h-[52px] shrink-0 px-4 text-sm"
          disabled={saving || !model}
          onClick={() => void handlePublishToAskData()}
        >
          Publish to Ask Data
        </button>
      </div>

      {!model && !models.length ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-600">
          No semantic model yet. Import your existing OSSIE model or create a new semantic model.
        </div>
      ) : (
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3">
            {PRIMARY_TABS.map(t => (
              <button
                key={t}
                type="button"
                onClick={() => switchTab(t)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  tab === t ? 'bg-violet-50 text-cloudera-violet' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                {TAB_LABELS[t]}
              </button>
            ))}
            <div className="relative" data-testid="semantic-advanced-menu">
              <button
                type="button"
                data-testid="semantic-advanced-trigger"
                aria-expanded={advancedOpen}
                aria-haspopup="menu"
                onClick={() => setAdvancedOpen(open => !open)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  ADVANCED_TABS.includes(tab as (typeof ADVANCED_TABS)[number])
                    ? 'bg-violet-50 text-cloudera-violet'
                    : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                Advanced ▾
              </button>
              {advancedOpen ? (
                <>
                  <button
                    type="button"
                    className="fixed inset-0 z-20 cursor-default bg-transparent"
                    aria-label="Close Advanced menu"
                    onClick={() => setAdvancedOpen(false)}
                  />
                  <div
                    role="menu"
                    className="absolute left-0 top-full z-30 mt-1 min-w-[14rem] rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        setAdvancedOpen(false)
                        openAdvancedTab('validation')
                      }}
                    >
                      Model health
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      data-testid="semantic-advanced-version-history"
                      className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        setAdvancedOpen(false)
                        openAdvancedTab('versions')
                      }}
                    >
                      Version history
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      data-testid="semantic-advanced-deployment-details"
                      className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        setAdvancedOpen(false)
                        openAdvancedTab('runtime')
                      }}
                    >
                      Deployment details
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        void openArtifactPreviewTab()
                      }}
                    >
                      Preview semantic artifact
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      data-testid="semantic-advanced-import-ossie"
                      className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        void openImportTab()
                      }}
                    >
                      Import OSSIE
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          </div>

          {tab === 'overview' ? (
            <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
              <SemanticOverviewPanel overview={overview} versionId={displayVersionId} />
            </div>
          ) : null}

          {!isEditable && tab !== 'overview' && !ADVANCED_TABS.includes(tab as (typeof ADVANCED_TABS)[number]) ? (
            <p className="border-b border-slate-100 px-4 py-2 text-xs text-amber-800">ACTIVE version is read-only. Create a draft to edit.</p>
          ) : null}

          {tab === 'entities' ? (
            <DataModelsTab versionId={displayVersionId} readOnly={!isEditable} connectors={connectors} onChanged={() => void refreshAuthoringKeys()} />
          ) : null}

          {tab === 'metrics' ? (
            <MetricsTab versionId={displayVersionId} readOnly={!isEditable} entityKeys={entityKeys} onChanged={() => void refreshAuthoringKeys()} />
          ) : null}

          {tab === 'dimensions' ? (
            <DimensionsTab versionId={displayVersionId} readOnly={!isEditable} entityKeys={entityKeys} onChanged={() => void refreshAuthoringKeys()} />
          ) : null}

          {tab === 'relationships' ? (
            <RelationshipsTab versionId={displayVersionId} readOnly={!isEditable} entityKeys={entityKeys} onChanged={() => void refreshAuthoringKeys()} />
          ) : null}

          {tab === 'glossary' ? (
            <GlossaryTab versionId={displayVersionId} readOnly={!isEditable} entityKeys={entityKeys} metricKeys={metricKeys} dimensionKeys={dimensionKeys} onChanged={() => void refreshAuthoringKeys()} />
          ) : null}

          {tab === 'validation' ? (
            <div className="space-y-4 p-4 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">Readiness:</span>
                <ReadinessBadge readiness={validation?.readiness ?? null} />
                <select
                  className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
                  value={validationMode}
                  onChange={e => setValidationMode(e.target.value as typeof validationMode)}
                >
                  <option value="full">Full validation</option>
                  <option value="structural">Structural only</option>
                  <option value="source">Source only</option>
                </select>
                <button
                  type="button"
                  className="btn-primary h-8 px-3 text-xs"
                  disabled={!displayVersionId || saving}
                  onClick={() => runValidate(validationMode)}
                >
                  Run validation
                </button>
                {validationProgress ? <span className="text-xs text-slate-500">{validationProgress}</span> : null}
              </div>
              {validation?.summary ? (
                <div className="grid gap-2 md:grid-cols-4">
                  {[
                    ['Errors', validation.summary.error_count],
                    ['Warnings', validation.summary.warning_count],
                    ['Checks passed', validation.summary.checks_run],
                    ['Skipped', validation.summary.checks_skipped],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-lg border border-slate-100 p-2 text-xs">
                      <div className="text-slate-500">{label}</div>
                      <div className="text-lg font-semibold text-cloudera-navy">{value}</div>
                    </div>
                  ))}
                </div>
              ) : null}
              {validation?.issues_by_category
                ? Object.entries(validation.issues_by_category).map(([category, issues]) => (
                    <IssueGroup key={category} title={category} issues={issues} />
                  ))
                : null}
              {!validation?.issues_by_category && validation?.errors.length ? (
                <IssueGroup title="Errors" issues={validation.errors} />
              ) : null}
              {!validation?.issues_by_category && validation?.warnings.length ? (
                <IssueGroup title="Warnings" issues={validation.warnings} />
              ) : null}
              {validationRuns.length ? (
                <div>
                  <h3 className="font-semibold text-cloudera-navy">Recent validation runs</h3>
                  <ul className="mt-2 space-y-1 text-xs">
                    {validationRuns.map(run => (
                      <li key={run.id} className="rounded border border-slate-100 px-2 py-1">
                        {run.started_at} · {run.mode} · {run.status} · errors=
                        {(run.summary as { error_count?: number })?.error_count ?? '—'}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {publishDiff?.breaking_changes?.length ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs">
                  <div className="font-semibold">Pending publish — breaking changes</div>
                  {publishDiff.breaking_changes.slice(0, 5).map((c, idx) => (
                    <div key={idx}>{String(c.section)} · {String(c.key ?? c.field)}</div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {tab === 'runtime' ? (
            <div className="space-y-4 p-4 text-sm">
              {runtimeNotice ? <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-2 text-xs">{runtimeNotice}</div> : null}
              {runtimeDryRun ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs">
                  Dry run: {runtimeDryRun.result} · checksum {runtimeDryRun.checksum.slice(0, 12)}…
                </div>
              ) : null}
              <table className="w-full text-left">
                <thead className="app-table-head">
                  <tr>
                    <th className="py-2">Deployment</th>
                    <th className="py-2">Semantic version</th>
                    <th className="py-2">Status</th>
                    <th className="py-2">Activated</th>
                    <th className="py-2">Health</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {runtimeDeployments.map(d => (
                    <tr key={d.id} className="border-b border-slate-50">
                      <td className="py-2 font-mono text-xs">{d.id.slice(0, 8)}…</td>
                      <td className="py-2">v{d.registry_version_number}</td>
                      <td className="py-2">{d.status}</td>
                      <td className="py-2 text-xs">{d.activated_at ?? '—'}</td>
                      <td className="py-2">{d.health_status ?? '—'}</td>
                      <td className="py-2">
                        {['ACTIVE', 'SUPERSEDED'].includes(d.status) ? (
                          <button
                            type="button"
                            className="text-xs font-semibold text-emerald-800"
                            disabled={saving || runtimeStatus?.deployment?.deployment_id === d.id}
                            onClick={() => {
                              if (!model?.key) return
                              const cur = runtimeStatus?.runtime_active_version
                              const target = d.registry_version_number
                              setConfirmModal({
                                title: 'Rollback semantic model?',
                                message: `Ask Data will start using version ${target} (from v${cur ?? 'legacy'}).`,
                                confirmLabel: 'Rollback',
                                tone: 'danger',
                                onConfirm: async () => {
                                  setSaving(true)
                                  try {
                                    await api.rollbackSemanticRuntimeDeployment(d.id)
                                    setRuntimeNotice(`Rolled back to runtime v${target}`)
                                    await refreshRuntime(model.key)
                                  } catch (err) {
                                    setError(err instanceof Error ? err.message : 'Rollback failed')
                                  } finally {
                                    setSaving(false)
                                  }
                                },
                              })
                            }}
                          >
                            Rollback
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!runtimeDeployments.length ? (
                <p className="text-xs text-slate-600">
                  No active deployment yet.
                  <br />
                  Publish this semantic model to make it available in Ask Data.
                </p>
              ) : null}
            </div>
          ) : null}

          {tab === 'versions' ? (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden text-sm">
              <SemanticVersionHistoryTable
                versions={versions}
                runtimeStatus={runtimeStatus}
                saving={saving}
                onRollback={v => {
                  setConfirmModal({
                    title: 'Rollback semantic model?',
                    message: `Ask Data will start using version ${v.version_number}.`,
                    confirmLabel: 'Rollback',
                    tone: 'danger',
                    onConfirm: async () => {
                      await api.rollbackSemanticVersion(v.id)
                      if (modelId) await refreshVersions(modelId)
                      if (model?.key) await refreshRuntime(model.key)
                      const ov = modelId ? await api.getSemanticModelOverview(modelId) : null
                      if (ov) setOverview(ov)
                    },
                  })
                }}
              />
              {compareSections.length ? (
                <div className="shrink-0 border-t border-slate-100 p-4">
                  <h3 className="font-semibold text-cloudera-navy">Compare draft vs active</h3>
                  {compareSections.map(section => (
                    <div key={section.label} className="mt-2 rounded-lg border border-slate-100 p-2 text-xs">
                      <div className="font-semibold">{section.label}</div>
                      {section.added.length ? <div>Added: {section.added.join('; ')}</div> : null}
                      {section.changed.length ? <div>Changed: {section.changed.join('; ')}</div> : null}
                      {section.removed.length ? <div>Removed: {section.removed.join('; ')}</div> : null}
                      {!section.added.length && !section.changed.length && !section.removed.length ? (
                        <div className="text-slate-500">No differences</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {tab === 'artifact' ? (
            <SemanticArtifactPreviewPanel
              artifact={artifact}
              loading={saving && !artifact?.content_preview}
              onRefresh={() => void loadArtifactPreview()}
            />
          ) : null}

          {tab === 'import' ? (
            <SemanticImportOssiePanel
              importSource={importSource}
              importKey={importKey}
              onImportKeyChange={setImportKey}
              importSummary={importSummary}
              saving={saving}
              onImport={() => void runImport()}
            />
          ) : null}
        </section>
      )}

      <CreateSemanticModelWizard
        open={createModelOpen}
        connectors={connectors}
        onClose={() => setCreateModelOpen(false)}
        onCreated={async id => {
          setCreateModelOpen(false)
          await refreshModels()
          setModelId(id)
        }}
      />

      <UnsavedChangesModal
        open={unsavedModalOpen}
        saving={saving}
        onKeepEditing={() => {
          setUnsavedModalOpen(false)
          setPendingTab(null)
          setPendingModelId(null)
        }}
        onDiscard={() => {
          editorDirty.activeRegistration()?.discard()
          setDirty(false)
          setUnsavedModalOpen(false)
          if (pendingTab) setTab(pendingTab)
          if (pendingModelId) setModelId(pendingModelId)
          setPendingTab(null)
          setPendingModelId(null)
        }}
        onSaveAndContinue={async () => {
          try {
            const reg = editorDirty.activeRegistration()
            if (reg) await reg.save()
            else if (pendingSaveAction) await pendingSaveAction()
          } catch {
            return
          }
          setDirty(false)
          setUnsavedModalOpen(false)
          if (pendingTab) setTab(pendingTab)
          if (pendingModelId) setModelId(pendingModelId)
          setPendingTab(null)
          setPendingModelId(null)
        }}
      />

      <ProductConfirmModal
        open={!!confirmModal}
        title={confirmModal?.title ?? ''}
        message={confirmModal?.message ?? ''}
        confirmLabel={confirmModal?.confirmLabel ?? 'Confirm'}
        confirmTone={confirmModal?.tone}
        busy={saving}
        onCancel={() => setConfirmModal(null)}
        onConfirm={() => {
          if (!confirmModal) return
          void confirmModal.onConfirm().finally(() => setConfirmModal(null))
        }}
      />
    </PageCenter>
  )
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  )
}

function ReadinessBadge({ readiness }: { readiness: string | null }) {
  const label = readiness ?? 'Not validated'
  const cls =
    readiness === 'READY'
      ? 'bg-emerald-50 text-emerald-800'
      : readiness === 'READY_WITH_WARNINGS'
        ? 'bg-amber-50 text-amber-900'
        : readiness === 'NOT_READY'
          ? 'bg-red-50 text-red-800'
          : 'bg-slate-100 text-slate-700'
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>{label.replace(/_/g, ' ')}</span>
}

function IssueGroup({ title, issues }: { title: string; issues: SemanticValidationResult['errors'] }) {
  return (
    <div>
      <h3 className="font-semibold text-cloudera-navy">{title}</h3>
      <ul className="mt-1 space-y-1 text-xs">
        {issues.map((issue, idx) => (
          <li key={`${issue.code}-${idx}`} className="rounded border border-slate-100 px-2 py-1">
            <span className="font-semibold">{issue.severity}</span>
            {issue.object_key ? <span className="text-slate-500"> · {issue.object_type}/{issue.object_key}</span> : null}
            <div>{issue.message}</div>
            {issue.remediation ? <div className="text-slate-600">Remediation: {issue.remediation}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ObjectTable<T extends { id: string }>(props: {
  rows: T[]
  columns: string[]
  renderRow: (row: T) => string[]
  selectedId: string | null
  onSelect: (id: string) => void
  emptyMessage: string
}) {
  if (!props.rows.length) {
    return <div className="p-6 text-sm text-slate-600">{props.emptyMessage}</div>
  }
  return (
    <div className="overflow-x-auto p-4">
      <table className="w-full text-left text-sm">
        <thead className="app-table-head">
          <tr>
            {props.columns.map(c => (
              <th key={c} className="py-2 capitalize">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.map(row => (
            <tr
              key={row.id}
              className={`cursor-pointer border-b border-slate-50 ${props.selectedId === row.id ? 'bg-violet-50' : ''}`}
              onClick={() => props.onSelect(row.id)}
            >
              {props.renderRow(row).map((cell, idx) => (
                <td key={idx} className="py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EntityEditor(props: {
  entity: SemanticEntityRecord
  readOnly: boolean
  onDirty: () => void
  onSave: (patch: Partial<SemanticEntityRecord>) => Promise<void>
  saving: boolean
}) {
  const [form, setForm] = useState(props.entity)
  useEffect(() => setForm(props.entity), [props.entity])
  return (
    <div className="border-t border-slate-100 p-4 text-sm">
      <h3 className="font-semibold text-cloudera-navy">Edit entity</h3>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Name" value={form.name} readOnly={props.readOnly} onChange={v => { setForm({ ...form, name: v }); props.onDirty() }} />
        <Field label="Key" value={form.key} readOnly />
        <Field label="Description" value={form.description ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, description: v }); props.onDirty() }} />
        <EntityConnectorSourceEditor
          entity={props.entity}
          readOnly={props.readOnly}
          form={form}
          setForm={setForm}
          onDirty={props.onDirty}
        />
        <Field label="Primary key" value={form.primary_key ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, primary_key: v }); props.onDirty() }} />
        {!form.connection_id ? (
          <>
            <Field label="Catalog" value={form.catalog ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, catalog: v }); props.onDirty() }} />
            <Field label="Schema" value={form.schema ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, schema: v }); props.onDirty() }} />
            <Field label="Table" value={form.table_name ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, table_name: v }); props.onDirty() }} />
          </>
        ) : null}
      </div>
      {!props.readOnly ? (
        <button type="button" className="btn-primary mt-3 h-9 px-4 text-sm" disabled={props.saving} onClick={() => props.onSave(form)}>
          Save entity
        </button>
      ) : null}
    </div>
  )
}

function MetricEditor(props: {
  metric: SemanticMetricRecord
  entityKeys: string[]
  readOnly: boolean
  onDirty: () => void
  onSave: (patch: Partial<SemanticMetricRecord> & { synonymsText?: string }) => Promise<void>
  saving: boolean
}) {
  const [form, setForm] = useState({ ...props.metric, synonymsText: synonymsText(props.metric.synonyms) })
  useEffect(() => setForm({ ...props.metric, synonymsText: synonymsText(props.metric.synonyms) }), [props.metric])
  return (
    <div className="border-t border-slate-100 p-4 text-sm">
      <h3 className="font-semibold text-cloudera-navy">Edit metric</h3>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Name" value={form.name} readOnly={props.readOnly} onChange={v => { setForm({ ...form, name: v }); props.onDirty() }} />
        <Field label="Key" value={form.key} readOnly />
        <Field label="Business definition" value={form.business_definition ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, business_definition: v }); props.onDirty() }} />
        <label className="block">
          <span className="text-xs font-semibold text-slate-600">Source entity</span>
          <select
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            disabled={props.readOnly}
            value={form.source_entity_key}
            onChange={e => { setForm({ ...form, source_entity_key: e.target.value }); props.onDirty() }}
          >
            {props.entityKeys.map(k => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <Field label="Expression" value={form.expression} readOnly={props.readOnly} onChange={v => { setForm({ ...form, expression: v }); props.onDirty() }} />
        <Field label="Aggregation" value={form.aggregation ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, aggregation: v }); props.onDirty() }} />
        <Field label="Unit" value={form.unit ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, unit: v }); props.onDirty() }} />
        <Field label="Format" value={form.format ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, format: v }); props.onDirty() }} />
        <Field label="Synonyms (comma-separated)" value={form.synonymsText} readOnly={props.readOnly} onChange={v => { setForm({ ...form, synonymsText: v }); props.onDirty() }} />
      </div>
      {!props.readOnly ? (
        <button type="button" className="btn-primary mt-3 h-9 px-4 text-sm" disabled={props.saving} onClick={() => props.onSave(form)}>
          Save metric
        </button>
      ) : null}
    </div>
  )
}

function DimensionEditor(props: {
  dimension: SemanticDimensionRecord
  entityKeys: string[]
  readOnly: boolean
  onDirty: () => void
  onSave: (patch: Partial<SemanticDimensionRecord> & { synonymsText?: string }) => Promise<void>
  saving: boolean
}) {
  const [form, setForm] = useState({ ...props.dimension, synonymsText: synonymsText(props.dimension.synonyms) })
  useEffect(() => setForm({ ...props.dimension, synonymsText: synonymsText(props.dimension.synonyms) }), [props.dimension])
  return (
    <div className="border-t border-slate-100 p-4 text-sm">
      <h3 className="font-semibold text-cloudera-navy">Edit dimension</h3>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Name" value={form.name} readOnly={props.readOnly} onChange={v => { setForm({ ...form, name: v }); props.onDirty() }} />
        <Field label="Key" value={form.key} readOnly />
        <label className="block">
          <span className="text-xs font-semibold text-slate-600">Source entity</span>
          <select
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            disabled={props.readOnly}
            value={form.source_entity_key}
            onChange={e => { setForm({ ...form, source_entity_key: e.target.value }); props.onDirty() }}
          >
            {props.entityKeys.map(k => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <Field label="Source column" value={form.source_column} readOnly={props.readOnly} onChange={v => { setForm({ ...form, source_column: v }); props.onDirty() }} />
        <Field label="Data type" value={form.data_type ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, data_type: v }); props.onDirty() }} />
        <Field label="Synonyms" value={form.synonymsText} readOnly={props.readOnly} onChange={v => { setForm({ ...form, synonymsText: v }); props.onDirty() }} />
      </div>
      {!props.readOnly ? (
        <button type="button" className="btn-primary mt-3 h-9 px-4 text-sm" disabled={props.saving} onClick={() => props.onSave(form)}>
          Save dimension
        </button>
      ) : null}
    </div>
  )
}

function RelationshipEditor(props: {
  relationship: SemanticRelationshipRecord
  entityKeys: string[]
  readOnly: boolean
  onDirty: () => void
  onSave: (patch: Partial<SemanticRelationshipRecord>) => Promise<void>
  saving: boolean
}) {
  const [form, setForm] = useState(props.relationship)
  useEffect(() => setForm(props.relationship), [props.relationship])
  return (
    <div className="border-t border-slate-100 p-4 text-sm">
      <h3 className="font-semibold text-cloudera-navy">Edit relationship</h3>
      <p className="mt-1 text-xs text-slate-500">
        {form.from_entity_key} → {form.name} → {form.to_entity_key}
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Name" value={form.name} readOnly={props.readOnly} onChange={v => { setForm({ ...form, name: v }); props.onDirty() }} />
        <label className="block">
          <span className="text-xs font-semibold text-slate-600">From entity</span>
          <select className="mt-1 w-full rounded-lg border px-3 py-2" disabled={props.readOnly} value={form.from_entity_key} onChange={e => { setForm({ ...form, from_entity_key: e.target.value }); props.onDirty() }}>
            {props.entityKeys.map(k => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-slate-600">To entity</span>
          <select className="mt-1 w-full rounded-lg border px-3 py-2" disabled={props.readOnly} value={form.to_entity_key} onChange={e => { setForm({ ...form, to_entity_key: e.target.value }); props.onDirty() }}>
            {props.entityKeys.map(k => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </label>
        <Field label="Join type" value={form.join_type} readOnly={props.readOnly} onChange={v => { setForm({ ...form, join_type: v }); props.onDirty() }} />
        <Field label="Relationship type" value={form.relationship_type} readOnly={props.readOnly} onChange={v => { setForm({ ...form, relationship_type: v }); props.onDirty() }} />
        <Field label="Join expression" value={form.join_expression} readOnly={props.readOnly} onChange={v => { setForm({ ...form, join_expression: v }); props.onDirty() }} />
        <Field label="Description" value={form.description ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, description: v }); props.onDirty() }} />
      </div>
      {!props.readOnly ? (
        <button type="button" className="btn-primary mt-3 h-9 px-4 text-sm" disabled={props.saving} onClick={() => props.onSave(form)}>
          Save relationship
        </button>
      ) : null}
    </div>
  )
}

function TermEditor(props: {
  term: SemanticTermRecord
  metricKeys: string[]
  dimensionKeys: string[]
  entityKeys: string[]
  readOnly: boolean
  onDirty: () => void
  onSave: (patch: Partial<SemanticTermRecord> & { synonymsText?: string }) => Promise<void>
  saving: boolean
}) {
  const [form, setForm] = useState({ ...props.term, synonymsText: synonymsText(props.term.synonyms) })
  useEffect(() => setForm({ ...props.term, synonymsText: synonymsText(props.term.synonyms) }), [props.term])

  function toggleKey(field: 'related_metric_keys' | 'related_dimension_keys' | 'related_entity_keys', key: string) {
    const current = form[field]
    setForm({ ...form, [field]: current.includes(key) ? current.filter(k => k !== key) : [...current, key] })
    props.onDirty()
  }

  return (
    <div className="border-t border-slate-100 p-4 text-sm">
      <h3 className="font-semibold text-cloudera-navy">Edit glossary term</h3>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Term" value={form.term} readOnly={props.readOnly} onChange={v => { setForm({ ...form, term: v }); props.onDirty() }} />
        <Field label="Key" value={form.key} readOnly />
        <Field label="Definition" value={form.definition ?? ''} readOnly={props.readOnly} onChange={v => { setForm({ ...form, definition: v }); props.onDirty() }} />
        <Field label="Synonyms" value={form.synonymsText} readOnly={props.readOnly} onChange={v => { setForm({ ...form, synonymsText: v }); props.onDirty() }} />
      </div>
      <div className="mt-3">
        <span className="text-xs font-semibold text-slate-600">Related metrics</span>
        <div className="mt-1 flex flex-wrap gap-1">
          {props.metricKeys.map(k => (
            <button key={k} type="button" disabled={props.readOnly} className={`rounded-full border px-2 py-0.5 text-xs ${form.related_metric_keys.includes(k) ? 'border-cloudera-violet bg-violet-50' : ''}`} onClick={() => toggleKey('related_metric_keys', k)}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2">
        <span className="text-xs font-semibold text-slate-600">Related dimensions</span>
        <div className="mt-1 flex flex-wrap gap-1">
          {props.dimensionKeys.map(k => (
            <button key={k} type="button" disabled={props.readOnly} className={`rounded-full border px-2 py-0.5 text-xs ${form.related_dimension_keys.includes(k) ? 'border-cloudera-violet bg-violet-50' : ''}`} onClick={() => toggleKey('related_dimension_keys', k)}>
              {k}
            </button>
          ))}
        </div>
      </div>
      {!props.readOnly ? (
        <button type="button" className="btn-primary mt-3 h-9 px-4 text-sm" disabled={props.saving} onClick={() => props.onSave(form)}>
          Save term
        </button>
      ) : null}
    </div>
  )
}

function Field(props: { label: string; value: string; readOnly?: boolean; onChange?: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-slate-600">{props.label}</span>
      <input
        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
        value={props.value}
        readOnly={props.readOnly}
        onChange={e => props.onChange?.(e.target.value)}
      />
    </label>
  )
}
