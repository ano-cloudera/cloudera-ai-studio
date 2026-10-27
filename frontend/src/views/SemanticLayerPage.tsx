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
  SemanticArtifactPreview,
  SemanticDimensionRecord,
  SemanticEntityRecord,
  SemanticMetricRecord,
  SemanticModelRecord,
  SemanticRelationshipRecord,
  SemanticTermRecord,
  SemanticValidationResult,
  SemanticRuntimeStatus,
  SemanticVersionRecord,
} from '../types/api'
import { buildVersionCompare } from './semantic/semanticLayerCompare'
import { SemanticOverviewPanel } from './semantic/SemanticOverviewPanel'
import { SemanticVersionContextBar } from './semantic/SemanticVersionContextBar'
import { SemanticPreviewTabPanel } from './semantic/SemanticPreviewTabPanel'
import { SemanticPublishTabPanel } from './semantic/SemanticPublishTabPanel'
import { SemanticVersionHistoryTabPanel } from './semantic/SemanticVersionHistoryTabPanel'
import { SemanticSuggestionsApplyModal } from './semantic/SemanticSuggestionsApplyModal'
import { UnsavedChangesModal } from '../components/semantic/UnsavedChangesModal'
import { CreateSemanticModelWizard } from './semantic/CreateSemanticModelWizard'
import { DataModelsTab } from './semantic/authoring/DataModelsTab'
import { DimensionsTab, GlossaryTab, MetricsTab, RelationshipsTab } from './semantic/authoring/SemanticOtherTabs'
import { countMetricsWithExplicitBreakdown } from './semantic/authoring/metricAuthoring'
import { useEditorDirtyRegistry } from './semantic/authoring/EditorDirtyContext'
import type { ConnectorRecord, SemanticOverviewPayload } from '../types/api'

const PRIMARY_TABS = [
  'overview',
  'entities',
  'metrics',
  'dimensions',
  'relationships',
  'glossary',
  'version_history',
  'preview',
  'publish_config',
] as const

type Tab = (typeof PRIMARY_TABS)[number]

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  entities: 'Data Models',
  metrics: 'Metrics',
  dimensions: 'Dimensions',
  relationships: 'Relationships',
  glossary: 'Glossary',
  version_history: 'Version history',
  preview: 'Preview',
  publish_config: 'Publish',
}

const TAB_TEST_IDS: Partial<Record<Tab, string>> = {
  version_history: 'semantic-tab-version-history',
  preview: 'semantic-tab-preview',
  publish_config: 'semantic-tab-publish-config',
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
  const [editSessionActive, setEditSessionActive] = useState(false)
  const [welcomeModelId, setWelcomeModelId] = useState<string | null>(null)
  const [suggestionsApply, setSuggestionsApply] = useState<{
    connectionId: string
    tables: string[]
  } | null>(null)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [validation, setValidation] = useState<SemanticValidationResult | null>(null)
  const [artifact, setArtifact] = useState<SemanticArtifactPreview | null>(null)
  const [artifactLoading, setArtifactLoading] = useState(false)
  const [artifactLoadedForVersionId, setArtifactLoadedForVersionId] = useState<string | null>(null)
  const [publishNotice, setPublishNotice] = useState('')
  const [runtimeStatus, setRuntimeStatus] = useState<SemanticRuntimeStatus | null>(null)
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

  const [authoringFocus, setAuthoringFocus] = useState<{ kind: string; objectId: string } | null>(null)

  const [createModelOpen, setCreateModelOpen] = useState(false)
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
  const isEditing = Boolean(draftVersion && editSessionActive)
  const displayVersionId =
    isEditing && draftVersion ? draftVersion.id : activeVersion?.id ?? draftVersion?.id ?? null
  const isEditable = isEditing

  const previewVersionId = useMemo(
    () => draftVersion?.id ?? activeVersion?.id ?? null,
    [draftVersion?.id, activeVersion?.id],
  )

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
    const status = await api.getSemanticRuntimeStatus(modelKey)
    setRuntimeStatus(status)
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

  useEffect(() => {
    if (!publishSuccess) return
    const timer = window.setTimeout(() => setPublishSuccess(null), 6000)
    return () => window.clearTimeout(timer)
  }, [publishSuccess])

  useEffect(() => {
    setPublishSuccess(null)
  }, [modelId])

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
    setArtifactLoadedForVersionId(null)
    setEditSessionActive(false)
    refreshVersions(modelId).catch(err => setError(err instanceof Error ? err.message : 'Failed to load versions'))
  }, [modelId, refreshVersions])

  useEffect(() => {
    if (draftVersion && !activeVersion) {
      setEditSessionActive(true)
    }
  }, [draftVersion?.id, activeVersion?.id])

  useEffect(() => {
    if (!model?.key) return
    refreshRuntime(model.key).catch(() => setRuntimeStatus(null))
  }, [model?.key, refreshRuntime, versions])

  const loadArtifactPreview = useCallback(async () => {
    if (!previewVersionId) return
    setArtifactLoading(true)
    setError('')
    try {
      const preview = await api.previewSemanticArtifact(previewVersionId)
      setArtifact(preview)
      setArtifactLoadedForVersionId(previewVersionId)
    } catch (err) {
      setArtifact(null)
      setArtifactLoadedForVersionId(null)
      setError(err instanceof Error ? err.message : 'Preview failed')
    } finally {
      setArtifactLoading(false)
    }
  }, [previewVersionId])

  useEffect(() => {
    if (tab !== 'preview' || !previewVersionId) return
    if (artifactLoadedForVersionId === previewVersionId && artifact?.content_preview) return
    void loadArtifactPreview()
  }, [tab, previewVersionId, artifactLoadedForVersionId, artifact?.content_preview, loadArtifactPreview])

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
    setTab(next)
  }

  function openPublishTab() {
    switchTab('publish_config')
  }

  function openPreviewTab() {
    switchTab('preview')
  }

  function navigateFromOverview(
    target: 'entities' | 'metrics' | 'dimensions' | 'relationships' | 'glossary' | 'preview' | 'publish_config',
  ) {
    if (target === 'publish_config') {
      openPublishTab()
      return
    }
    if (target === 'preview') {
      openPreviewTab()
      return
    }
    switchTab(target)
  }

  function confirmRollbackVersion(v: SemanticVersionRecord) {
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
  }

  async function handleEdit() {
    if (!model) return
    setSaving(true)
    setError('')
    try {
      if (!draftVersion) {
        await ensureDraftVersionId()
      }
      setEditSessionActive(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start editing')
    } finally {
      setSaving(false)
    }
  }

  function handleCancelEdit() {
    if (hasUnsavedEdits()) {
      setPendingTab(null)
      setPendingModelId(null)
      setPendingSaveAction(async () => {
        setEditSessionActive(false)
      })
      setUnsavedModalOpen(true)
      return
    }
    setEditSessionActive(false)
  }

  const finalizeAfterDiscardDraft = useCallback(async () => {
    setArtifact(null)
    setArtifactLoadedForVersionId(null)
    setValidation(null)
    setEditSessionActive(false)
    setAuthoringFocus(null)
    setDirty(false)
    setTab('overview')
    setError('')
    if (!modelId) return
    const { versions: rows } = await api.listSemanticVersions(modelId)
    setVersions(rows)
    const active = rows.find(v => v.status === 'ACTIVE') ?? null
    if (active) {
      await loadVersionObjects(active.id)
    } else {
      setEntities([])
      setMetrics([])
      setDimensions([])
      setRelationships([])
      setTerms([])
    }
    await refreshModels()
    const ov = await api.getSemanticModelOverview(modelId)
    setOverview(ov)
  }, [loadVersionObjects, modelId, refreshModels])

  function discardDraftErrorMessage(err: unknown): string {
    const apiErr = toAppApiError(err)
    if (apiErr.status === 404 && apiErr.code === 'HTTP_404') {
      return 'Discard draft is not available on this API yet. Restart the backend so semantic routes are up to date, then try again.'
    }
    return safeErrorMessage(err, 'Could not discard draft')
  }

  async function handleDiscardEdit() {
    if (!draftVersion) return
    const draftId = draftVersion.id
    const draftNum = draftVersion.version_number
    const hasPublished = Boolean(activeVersion)
    setConfirmModal({
      title: 'Discard draft?',
      message: hasPublished
        ? [
            `Delete draft v${draftNum} and return to published v${activeVersion!.version_number}.`,
            'Unsaved editor changes will be lost. This cannot be undone.',
          ].join('\n')
        : [
            `Delete draft v${draftNum}. There is no published version yet.`,
            'Unsaved editor changes will be lost. This cannot be undone.',
          ].join('\n'),
      confirmLabel: 'Discard draft',
      tone: 'danger',
      onConfirm: async () => {
        editorDirty.activeRegistration()?.discard()
        setSaving(true)
        setError('')
        try {
          await api.discardSemanticDraftVersion(draftId)
          await finalizeAfterDiscardDraft()
        } catch (err) {
          const apiErr = toAppApiError(err)
          if (apiErr.status === 404 && apiErr.code === 'not_found') {
            await finalizeAfterDiscardDraft()
            return
          }
          setError(discardDraftErrorMessage(err))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  async function handleToolbarSave() {
    const reg = editorDirty.activeRegistration()
    if (reg?.isDirty()) {
      setSaving(true)
      try {
        await reg.save()
        setDirty(false)
        setArtifactLoadedForVersionId(null)
        openPreviewTab()
        void loadArtifactPreview()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Save failed')
      } finally {
        setSaving(false)
      }
      return
    }
    openPreviewTab()
    void loadArtifactPreview()
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

  async function executeFullPublish(versionId: string) {
    if (!model) return
    setSaving(true)
    setError('')
    setPublishSuccess(null)
    setPublishIssues([])
    setActivationFailure(null)
    setPublishNotice('')
    const progressSteps = ['Preparing semantic model…', 'Checking definitions…', 'Publishing…', 'Activating Ask Data…']
    let step = 0
    setPublishProgress(progressSteps[step])
    const timer = window.setInterval(() => {
      step = Math.min(step + 1, progressSteps.length - 1)
      setPublishProgress(progressSteps[step])
    }, 900)
    try {
      const result = await api.publishSemanticToAskData(model.id, { version_id: versionId })
      window.clearInterval(timer)
      setPublishProgress('')
      setPublishSuccess(
        `Published — Version ${result.version_number ?? ''} is live in the registry and active in Ask Data.`,
      )
      await refreshVersions(model.id)
      await refreshModels()
      if (model.key) await refreshRuntime(model.key)
      const ov = await api.getSemanticModelOverview(model.id)
      setOverview(ov)
      setEditSessionActive(false)
      setDirty(false)
    } catch (err: unknown) {
      window.clearInterval(timer)
      setPublishProgress('')
      const detail = isAppApiError(err) ? (err.details as Record<string, unknown> | undefined) : undefined
      if (detail && Array.isArray(detail.issues)) {
        setPublishIssues(detail.issues as Array<Record<string, unknown>>)
        setError(`${(detail.issues as unknown[]).length} issue(s) need attention before publishing.`)
        openPublishTab()
      } else if (detail?.status === 'activation_failed' || (isAppApiError(err) && err.status === 502)) {
        setActivationFailure(
          String(detail?.message ?? 'Publish could not be activated. Your previous active semantic version is still used by Ask Data.'),
        )
        if (model.key) await refreshRuntime(model.key)
        openPublishTab()
      } else {
        setError(isAppApiError(err) ? err.message : err instanceof Error ? err.message : 'Publish failed')
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
      if (row) setAuthoringFocus({ kind: 'metric', objectId: row.id })
    } else if (type.includes('dimension')) {
      switchTab('dimensions')
      const row = dimensions.find(d => d.key === key || d.name === key)
      if (row) setAuthoringFocus({ kind: 'dimension', objectId: row.id })
    } else if (type.includes('relationship')) {
      switchTab('relationships')
      const row = relationships.find(r => r.key === key || r.name === key)
      if (row) setAuthoringFocus({ kind: 'relationship', objectId: row.id })
    } else if (type.includes('entity')) {
      switchTab('entities')
      const row = entities.find(e => e.key === key || e.name === key)
      if (row) setAuthoringFocus({ kind: 'entity', objectId: row.id })
    } else if (type.includes('term') || String(issue.category ?? '').toUpperCase() === 'GLOSSARY') {
      switchTab('glossary')
      const row = terms.find(t => t.key === key || t.term === key)
      if (row) setAuthoringFocus({ kind: 'glossary', objectId: row.id })
    } else {
      openPublishTab()
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

  async function handlePublish() {
    if (!model) return
    const draftId = draftVersion?.id
    const activateActiveId =
      !draftVersion && showPublishToAskData && activeVersion?.id ? activeVersion.id : null

    if (!draftId && !activateActiveId) {
      setError('Nothing to publish. Edit the model, save your draft, and review Preview first.')
      return
    }

    setError('')

    if (draftId && activeVersion) {
      setConfirmModal({
        title: 'Publish?',
        message: [
          `Draft v${draftVersion!.version_number} will become the live registry version.`,
          'Ask Data will use this version after publish.',
        ].join('\n'),
        confirmLabel: 'Publish',
        onConfirm: async () => {
          await executeFullPublish(draftId)
        },
      })
      return
    }

    await executeFullPublish(draftId ?? activateActiveId!)
  }

  async function handlePublishRetry() {
    const versionId = draftVersion?.id ?? activeVersion?.id
    if (!versionId) {
      setError('Nothing to publish.')
      return
    }
    await executeFullPublish(versionId)
  }

  const toolbarVersionBadge = useMemo((): { label: string; className: string } | null => {
    if (publishIssues.length) {
      return { label: 'Needs attention', className: 'bg-amber-50 text-amber-900' }
    }
    if (isEditing && draftVersion) {
      return { label: `Editing · v${draftVersion.version_number}`, className: 'bg-violet-100 text-violet-900' }
    }
    if (draftVersion && !editSessionActive) {
      return { label: `Draft saved · v${draftVersion.version_number}`, className: 'bg-slate-100 text-slate-800' }
    }
    if (activeVersion) {
      return { label: `Published v${activeVersion.version_number}`, className: 'bg-emerald-50 text-emerald-800' }
    }
    if (draftVersion) {
      return { label: `Draft v${draftVersion.version_number}`, className: 'bg-violet-100 text-violet-900' }
    }
    return null
  }, [publishIssues.length, isEditing, editSessionActive, draftVersion, activeVersion])

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

  const needsRuntimeActivation =
    Boolean(activeVersion && runtimeStatus) &&
    runtimeStatus!.registry_active_version != null &&
    runtimeStatus!.runtime_active_version != null &&
    runtimeStatus!.registry_active_version !== runtimeStatus!.runtime_active_version

  const showPublishToAskData = useMemo(() => {
    if (!model || !activeVersion) return false
    if (needsRuntimeActivation) return true
    const reg = runtimeStatus?.registry_active_version
    const run = runtimeStatus?.runtime_active_version
    if (run == null) return true
    if (reg != null && run != null && reg !== run) return true
    return false
  }, [model, activeVersion, needsRuntimeActivation, runtimeStatus])

  const publishMode = useMemo((): 'draft' | 'activate' | 'none' => {
    if (draftVersion) return 'draft'
    if (showPublishToAskData && activeVersion) return 'activate'
    return 'none'
  }, [draftVersion, showPublishToAskData, activeVersion])

  const canPublish = publishMode !== 'none'

  const metricsWithExplicitBreakdown = useMemo(
    () => countMetricsWithExplicitBreakdown(metrics),
    [metrics],
  )

  const checklistPreviewReviewed = useMemo(() => {
    if (validation?.valid) return true
    if (
      previewVersionId &&
      artifactLoadedForVersionId === previewVersionId &&
      Boolean(artifact?.content_preview)
    ) {
      return true
    }
    if (!draftVersion && activeVersion && (overview?.issue_count ?? 0) === 0) {
      return overview?.state === 'Published' || overview?.readiness === 'READY'
    }
    return false
  }, [
    validation?.valid,
    previewVersionId,
    artifactLoadedForVersionId,
    artifact?.content_preview,
    draftVersion,
    activeVersion,
    overview?.issue_count,
    overview?.state,
    overview?.readiness,
  ])

  const checklistPublishComplete = useMemo(
    () =>
      Boolean(
        !draftVersion &&
          activeVersion &&
          !showPublishToAskData &&
          (overview?.state === 'Published' || overview?.published_version_number != null),
      ),
    [draftVersion, activeVersion, showPublishToAskData, overview?.state, overview?.published_version_number],
  )

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
            <button type="button" className="h-8 rounded-lg border border-red-200 bg-white px-2 text-xs font-semibold" onClick={() => void handlePublishRetry()}>
              Retry publish
            </button>
            <button type="button" className="h-8 rounded-lg border border-red-200 bg-white px-2 text-xs font-semibold" onClick={() => openPublishTab()}>
              Open Publish tab
            </button>
          </div>
        </div>
      ) : null}
      {publishIssues.length ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950" data-testid="publish-needs-attention">
          <div className="font-semibold">{publishIssues.length} issue(s) need attention</div>
          <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs">
            {publishIssues.slice(0, 14).map((issue, idx) => (
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
        className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm"
        data-testid="semantic-model-toolbar"
      >
        <div className="min-w-[240px] flex-1">
          <SemanticModelCombobox models={models} value={modelId} onChange={requestModelChange} />
        </div>
        {isEditing ? (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="semantic-edit-cancel"
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
              disabled={saving}
              onClick={() => handleCancelEdit()}
            >
              Cancel
            </button>
            <button
              type="button"
              data-testid="semantic-edit-discard"
              className="h-10 rounded-lg border border-red-200 bg-white px-4 text-sm font-semibold text-red-800 shadow-sm hover:bg-red-50 disabled:opacity-50"
              disabled={saving}
              onClick={() => void handleDiscardEdit()}
            >
              Discard draft
            </button>
            <button
              type="button"
              data-testid="semantic-edit-save"
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-cloudera-navy shadow-sm hover:bg-slate-50 disabled:opacity-50"
              disabled={saving}
              onClick={() => void handleToolbarSave()}
            >
              Save
            </button>
          </div>
        ) : (
          <button
            type="button"
            data-testid="semantic-lifecycle-primary"
            className="btn-primary h-10 shrink-0 rounded-lg px-4 text-sm disabled:opacity-50"
            disabled={saving || !model}
            onClick={() => void handleEdit()}
          >
            Edit
          </button>
        )}
      </div>

      {model ? (
        <SemanticVersionContextBar
          draftVersion={draftVersion}
          activeVersion={activeVersion}
          isEditable={isEditing}
          needsRuntimeActivation={needsRuntimeActivation}
          publishNeedsAttention={publishIssues.length > 0}
          statusPill={toolbarVersionBadge}
          onDiscardDraft={draftVersion ? () => void handleDiscardEdit() : undefined}
          discardDisabled={saving}
        />
      ) : null}

      {!model && !models.length ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-600">
          No semantic model yet. Import your existing OSSIE model or create a new semantic model.
        </div>
      ) : (
        <section className="flex min-h-[min(32rem,70vh)] min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex shrink-0 flex-wrap gap-2 border-b border-slate-100 px-4 py-3">
            {PRIMARY_TABS.map(t => (
              <button
                key={t}
                type="button"
                data-testid={TAB_TEST_IDS[t]}
                onClick={() => switchTab(t)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  tab === t ? 'bg-violet-50 text-cloudera-violet' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                {TAB_LABELS[t]}
              </button>
            ))}
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {tab === 'overview' ? (
            <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
              <SemanticOverviewPanel
                overview={overview}
                editingDraftVersionNumber={isEditing ? draftVersion?.version_number ?? null : null}
                showWelcomeChecklist={Boolean(welcomeModelId && modelId === welcomeModelId)}
                isEditable={isEditing}
                metricsWithExplicitBreakdown={metricsWithExplicitBreakdown}
                publishIssueCount={publishIssues.length || (overview?.issue_count ?? 0)}
                previewReviewed={checklistPreviewReviewed}
                publishComplete={checklistPublishComplete}
                onDismissWelcome={() => setWelcomeModelId(null)}
                onNavigateTab={navigateFromOverview}
              />
            </div>
          ) : null}

          {tab === 'entities' ? (
            <DataModelsTab
              versionId={displayVersionId}
              readOnly={!isEditable}
              connectors={connectors}
              onChanged={() => void refreshAuthoringKeys()}
              onEntityImported={ctx => setSuggestionsApply(ctx)}
            />
          ) : null}

          {tab === 'metrics' ? (
            <MetricsTab
              versionId={displayVersionId}
              readOnly={!isEditable}
              entityKeys={entityKeys}
              onChanged={() => void refreshAuthoringKeys()}
              focusObjectId={authoringFocus?.kind === 'metric' ? authoringFocus.objectId : null}
              onFocusObjectConsumed={() => setAuthoringFocus(null)}
            />
          ) : null}

          {tab === 'dimensions' ? (
            <DimensionsTab
              versionId={displayVersionId}
              readOnly={!isEditable}
              entityKeys={entityKeys}
              onChanged={() => void refreshAuthoringKeys()}
              focusObjectId={authoringFocus?.kind === 'dimension' ? authoringFocus.objectId : null}
              onFocusObjectConsumed={() => setAuthoringFocus(null)}
            />
          ) : null}

          {tab === 'relationships' ? (
            <RelationshipsTab
              versionId={displayVersionId}
              readOnly={!isEditable}
              entityKeys={entityKeys}
              onChanged={() => void refreshAuthoringKeys()}
              focusObjectId={authoringFocus?.kind === 'relationship' ? authoringFocus.objectId : null}
              onFocusObjectConsumed={() => setAuthoringFocus(null)}
            />
          ) : null}

          {tab === 'glossary' ? (
            <GlossaryTab
              versionId={displayVersionId}
              readOnly={!isEditable}
              entityKeys={entityKeys}
              metricKeys={metricKeys}
              dimensionKeys={dimensionKeys}
              onChanged={() => void refreshAuthoringKeys()}
              focusObjectId={authoringFocus?.kind === 'glossary' ? authoringFocus.objectId : null}
              onFocusObjectConsumed={() => setAuthoringFocus(null)}
            />
          ) : null}

          {tab === 'version_history' ? (
            <SemanticVersionHistoryTabPanel
              versions={versions}
              runtimeStatus={runtimeStatus}
              saving={saving}
              onRollbackVersion={confirmRollbackVersion}
            />
          ) : null}

          {tab === 'preview' ? (
            <SemanticPreviewTabPanel
              artifact={artifact}
              artifactLoading={artifactLoading}
              previewVersionId={previewVersionId}
              saving={saving}
              onRefreshArtifact={() => void loadArtifactPreview()}
              onGoToPublish={() => openPublishTab()}
              compareSections={compareSections}
            />
          ) : null}

          {tab === 'publish_config' ? (
            <SemanticPublishTabPanel
              saving={saving}
              canPublish={canPublish}
              publishMode={publishMode}
              onPublish={() => void handlePublish()}
              onGoToPreview={() => openPreviewTab()}
            />
          ) : null}
          </div>
        </section>
      )}

      {model && draftVersion && suggestionsApply ? (
        <SemanticSuggestionsApplyModal
          open
          modelId={model.id}
          versionId={draftVersion.id}
          connectionId={suggestionsApply.connectionId}
          tables={suggestionsApply.tables}
          onClose={() => setSuggestionsApply(null)}
          onApplied={() => {
            void refreshAuthoringKeys()
            if (modelId) {
              void api.getSemanticModelOverview(modelId).then(setOverview)
            }
          }}
        />
      ) : null}

      <CreateSemanticModelWizard
        open={createModelOpen}
        connectors={connectors}
        onClose={() => setCreateModelOpen(false)}
        onCreated={async id => {
          setCreateModelOpen(false)
          await refreshModels()
          setModelId(id)
          setWelcomeModelId(id)
          setEditSessionActive(true)
          switchTab('overview')
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
          if (pendingSaveAction) void pendingSaveAction()
          if (pendingTab) setTab(pendingTab)
          if (pendingModelId) setModelId(pendingModelId)
          setPendingTab(null)
          setPendingModelId(null)
          setPendingSaveAction(null)
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
