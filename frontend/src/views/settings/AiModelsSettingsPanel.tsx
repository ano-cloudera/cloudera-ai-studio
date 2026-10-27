'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { ProviderTypeIcon } from '../../components/ai/ProviderTypeIcon'
import { TablePagination } from '../../components/knowledge/TablePagination'
import { Bot, Plus, Sparkles } from 'lucide-react'
import { EmptyState } from '../../components/EmptyState'
import { ServiceErrorState } from '../../components/ServiceErrorState'
import { api } from '../../lib/api'
import { toAppApiError, type AppApiError } from '../../lib/apiError'
import {
  AI_REGISTRY_TABLE_PAGE_SIZES,
  aiRegistryErrorMessage,
  assignmentHealthMessage,
  assignmentSourceLabel,
  CAPABILITY_ROWS,
  isValidSecretRef,
  providerStatusClass,
  providerStatusLabel,
  PROVIDER_TYPE_OPTIONS,
  providerTypeLabel,
  slugModelKey,
} from '../../lib/aiRegistryUi'
import type {
  AiModelRecord,
  AiModelType,
  AiProviderRecord,
  AiProviderType,
  AiRemoteModel,
  AssignmentCapability,
  ModelAssignmentRecord,
} from '../../types/api'

type ProviderDraft = {
  name: string
  key: string
  provider_type: AiProviderType
  base_url: string
  secret_ref: string
  enabled: boolean
  test_strategy: string
}

const emptyProviderDraft = (type: AiProviderType): ProviderDraft => ({
  name: '',
  key: '',
  provider_type: type,
  base_url: '',
  secret_ref: '',
  enabled: true,
  test_strategy: 'AUTO',
})

export function AiModelsSettingsPanel() {
  const [providers, setProviders] = useState<AiProviderRecord[]>([])
  const [models, setModels] = useState<AiModelRecord[]>([])
  const [assignments, setAssignments] = useState<ModelAssignmentRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const [banner, setBanner] = useState('')
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null)
  const [testingModelId, setTestingModelId] = useState<string | null>(null)

  const [providerModal, setProviderModal] = useState<'closed' | 'pick' | 'form'>('closed')
  const [providerDraft, setProviderDraft] = useState<ProviderDraft>(emptyProviderDraft('GEMINI'))
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null)
  const [savingProvider, setSavingProvider] = useState(false)

  const [modelModalOpen, setModelModalOpen] = useState(false)
  const [modelDraft, setModelDraft] = useState({
    provider_id: '',
    name: '',
    key: '',
    model_id: '',
    model_type: 'CHAT' as const,
    enabled: true,
  })
  const [savingModel, setSavingModel] = useState(false)
  const [providersPage, setProvidersPage] = useState(1)
  const [providersPageSize, setProvidersPageSize] = useState(5)
  const [modelsPage, setModelsPage] = useState(1)
  const [modelsPageSize, setModelsPageSize] = useState(5)
  const [selectedProviderIds, setSelectedProviderIds] = useState<Set<string>>(() => new Set())
  const [selectedModelIds, setSelectedModelIds] = useState<Set<string>>(() => new Set())
  const [batchDeletingProviders, setBatchDeletingProviders] = useState(false)
  const [batchDeletingModels, setBatchDeletingModels] = useState(false)

  const [remoteModels, setRemoteModels] = useState<AiRemoteModel[]>([])
  const [loadingRemoteModels, setLoadingRemoteModels] = useState(false)
  const [selectedRemoteIds, setSelectedRemoteIds] = useState<Set<string>>(() => new Set())
  const [remoteFilter, setRemoteFilter] = useState('')
  const [modelRegisterType, setModelRegisterType] = useState<AiModelType>('CHAT')
  const [manualModelEntry, setManualModelEntry] = useState(false)

  const refresh = useCallback(async () => {
    setLoadError(null)
    const [p, m, a] = await Promise.all([api.listAiProviders(), api.listAiModels(), api.listModelAssignments()])
    setProviders(p.providers)
    setModels(m.models)
    setAssignments(a.assignments)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await refresh()
      } catch (err) {
        if (!cancelled) setLoadError(toAppApiError(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [refresh])

  const modelsByProvider = useMemo(() => {
    const map = new Map<string, number>()
    for (const model of models) {
      map.set(model.provider_id, (map.get(model.provider_id) || 0) + 1)
    }
    return map
  }, [models])

  const assignmentByCap = useMemo(() => {
    const map = new Map<AssignmentCapability, ModelAssignmentRecord>()
    for (const row of assignments) map.set(row.capability, row)
    return map
  }, [assignments])

  const pagedProviders = useMemo(() => {
    const start = (providersPage - 1) * providersPageSize
    return providers.slice(start, start + providersPageSize)
  }, [providers, providersPage, providersPageSize])

  const pagedModels = useMemo(() => {
    const start = (modelsPage - 1) * modelsPageSize
    return models.slice(start, start + modelsPageSize)
  }, [models, modelsPage, modelsPageSize])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(providers.length / providersPageSize) || 1)
    if (providersPage > totalPages) setProvidersPage(totalPages)
  }, [providers.length, providersPage, providersPageSize])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(models.length / modelsPageSize) || 1)
    if (modelsPage > totalPages) setModelsPage(totalPages)
  }, [models.length, modelsPage, modelsPageSize])

  async function handleTestProvider(id: string) {
    setBanner('')
    setTestingProviderId(id)
    try {
      const result = await api.testAiProvider(id)
      if (result.status === 'READY') {
        setBanner(`Connection successful (${Math.round(result.latency_ms)} ms).`)
      } else {
        setBanner(result.message || 'Provider test failed.')
      }
      await refresh()
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    } finally {
      setTestingProviderId(null)
    }
  }

  async function handleTestModel(id: string) {
    setBanner('')
    setTestingModelId(id)
    try {
      const result = await api.testAiModel(id)
      setBanner(result.status === 'READY' ? `Model test passed (${Math.round(result.latency_ms)} ms).` : result.message || 'Model test failed.')
      await refresh()
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    } finally {
      setTestingModelId(null)
    }
  }

  async function saveProvider() {
    setBanner('')
    if (!providerDraft.name.trim() || !providerDraft.key.trim()) {
      setBanner('Provider name and key are required.')
      return
    }
    if (providerDraft.provider_type === 'OPENAI_COMPATIBLE' && !providerDraft.base_url.trim()) {
      setBanner('Base URL is required for OpenAI-compatible providers.')
      return
    }
    if (providerDraft.provider_type !== 'OPENAI_COMPATIBLE' && !providerDraft.secret_ref.trim()) {
      setBanner('Secret reference is required.')
      return
    }
    if (providerDraft.secret_ref.trim() && !isValidSecretRef(providerDraft.secret_ref)) {
      setBanner('Use a secret reference such as env://GEMINI_API_KEY. Plaintext API keys are not stored.')
      return
    }
    setSavingProvider(true)
    try {
      const body = {
        name: providerDraft.name.trim(),
        key: providerDraft.key.trim(),
        provider_type: providerDraft.provider_type,
        base_url: providerDraft.base_url.trim() || null,
        secret_ref: providerDraft.secret_ref.trim() || null,
        enabled: providerDraft.enabled,
        config_json:
          providerDraft.provider_type === 'OPENAI_COMPATIBLE'
            ? { test_strategy: providerDraft.test_strategy || 'AUTO' }
            : {},
      }
      if (editingProviderId) {
        await api.updateAiProvider(editingProviderId, body)
      } else {
        await api.createAiProvider(body)
      }
      setProviderModal('closed')
      setEditingProviderId(null)
      await refresh()
      setBanner('Provider saved.')
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    } finally {
      setSavingProvider(false)
    }
  }

  async function saveModel() {
    setBanner('')
    if (!modelDraft.provider_id || !modelDraft.name.trim() || !modelDraft.key.trim() || !modelDraft.model_id.trim()) {
      setBanner('All model fields are required.')
      return
    }
    setSavingModel(true)
    try {
      await api.createAiModel({
        provider_id: modelDraft.provider_id,
        name: modelDraft.name.trim(),
        key: modelDraft.key.trim(),
        model_id: modelDraft.model_id.trim(),
        model_type: modelDraft.model_type,
        enabled: modelDraft.enabled,
      })
      setModelModalOpen(false)
      await refresh()
      setBanner('Model registered.')
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    } finally {
      setSavingModel(false)
    }
  }

  async function toggleProvider(provider: AiProviderRecord) {
    setBanner('')
    try {
      await api.updateAiProvider(provider.id, { enabled: !provider.enabled })
      await refresh()
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    }
  }

  async function deleteProvider(provider: AiProviderRecord) {
    if (!window.confirm(`Delete provider "${provider.name}"?`)) return
    setBanner('')
    try {
      await api.deleteAiProvider(provider.id)
      setSelectedProviderIds(prev => {
        const next = new Set(prev)
        next.delete(provider.id)
        return next
      })
      await refresh()
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    }
  }

  async function deleteModel(model: AiModelRecord) {
    if (!window.confirm(`Delete model "${model.name}"?`)) return
    setBanner('')
    try {
      await api.deleteAiModel(model.id)
      setSelectedModelIds(prev => {
        const next = new Set(prev)
        next.delete(model.id)
        return next
      })
      await refresh()
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    }
  }

  function toggleProviderRow(id: string) {
    setSelectedProviderIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleModelRow(id: string) {
    setSelectedModelIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAllProvidersOnPage(checked: boolean) {
    setSelectedProviderIds(prev => {
      const next = new Set(prev)
      for (const row of pagedProviders) {
        if (checked) next.add(row.id)
        else next.delete(row.id)
      }
      return next
    })
  }

  function toggleAllModelsOnPage(checked: boolean) {
    setSelectedModelIds(prev => {
      const next = new Set(prev)
      for (const row of pagedModels) {
        if (checked) next.add(row.id)
        else next.delete(row.id)
      }
      return next
    })
  }

  async function deleteSelectedProviders() {
    const ids = [...selectedProviderIds]
    if (!ids.length) return
    if (!window.confirm(`Delete ${ids.length} selected provider(s)? Models under them may block deletion.`)) return
    setBanner('')
    setBatchDeletingProviders(true)
    try {
      const results = await Promise.allSettled(ids.map(id => api.deleteAiProvider(id)))
      const failed = results.filter(r => r.status === 'rejected').length
      setSelectedProviderIds(new Set())
      await refresh()
      setBanner(failed ? `Deleted ${ids.length - failed} provider(s). ${failed} could not be deleted (in use or blocked).` : `Deleted ${ids.length} provider(s).`)
    } finally {
      setBatchDeletingProviders(false)
    }
  }

  async function deleteSelectedModels() {
    const ids = [...selectedModelIds]
    if (!ids.length) return
    if (!window.confirm(`Delete ${ids.length} selected model(s)?`)) return
    setBanner('')
    setBatchDeletingModels(true)
    try {
      const results = await Promise.allSettled(ids.map(id => api.deleteAiModel(id)))
      const failed = results.filter(r => r.status === 'rejected').length
      setSelectedModelIds(new Set())
      await refresh()
      setBanner(failed ? `Deleted ${ids.length - failed} model(s). ${failed} could not be deleted (assigned or in use).` : `Deleted ${ids.length} model(s).`)
    } finally {
      setBatchDeletingModels(false)
    }
  }

  async function loadRemoteModelsForProvider(providerId: string) {
    if (!providerId) {
      setRemoteModels([])
      setSelectedRemoteIds(new Set())
      return
    }
    setBanner('')
    setLoadingRemoteModels(true)
    try {
      const result = await api.listAiProviderRemoteModels(providerId)
      setRemoteModels(result.models)
      setSelectedRemoteIds(new Set())
    } catch (err) {
      setRemoteModels([])
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    } finally {
      setLoadingRemoteModels(false)
    }
  }

  function toggleRemoteModel(id: string) {
    setSelectedRemoteIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filteredRemoteModels = useMemo(() => {
    const q = remoteFilter.trim().toLowerCase()
    if (!q) return remoteModels
    return remoteModels.filter(m => m.id.toLowerCase().includes(q) || (m.display_name || '').toLowerCase().includes(q))
  }, [remoteModels, remoteFilter])

  const registeredModelIdsForProvider = useMemo(() => {
    const set = new Set<string>()
    for (const m of models) {
      if (m.provider_id === modelDraft.provider_id) set.add(m.model_id)
    }
    return set
  }, [models, modelDraft.provider_id])

  async function registerSelectedRemoteModels() {
    const ids = [...selectedRemoteIds]
    if (!ids.length || !modelDraft.provider_id) {
      setBanner('Select at least one model from the provider catalog.')
      return
    }
    setBanner('')
    setSavingModel(true)
    try {
      const results = await Promise.allSettled(
        ids.map(id =>
          api.createAiModel({
            provider_id: modelDraft.provider_id,
            name: remoteModels.find(m => m.id === id)?.display_name?.trim() || id,
            key: slugModelKey(id),
            model_id: id,
            model_type: modelRegisterType,
            enabled: true,
          }),
        ),
      )
      const failed = results.filter(r => r.status === 'rejected').length
      setModelModalOpen(false)
      setSelectedRemoteIds(new Set())
      await refresh()
      setBanner(failed ? `Registered ${ids.length - failed} model(s). ${failed} failed (duplicate key or validation).` : `Registered ${ids.length} model(s).`)
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    } finally {
      setSavingModel(false)
    }
  }

  async function assignCapability(capability: AssignmentCapability, modelId: string) {
    setBanner('')
    try {
      await api.putModelAssignment(capability, { model_id: modelId })
      await refresh()
      setBanner('Assignment updated.')
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    }
  }

  async function clearAssignment(capability: AssignmentCapability) {
    setBanner('')
    try {
      await api.deleteModelAssignment(capability)
      await refresh()
      setBanner('Project assignment removed.')
    } catch (err) {
      setBanner(aiRegistryErrorMessage(toAppApiError(err)))
    }
  }

  if (loading) {
    return <p className="type-chat-body text-slate-500">Loading AI registry…</p>
  }

  if (loadError) {
    return (
      <ServiceErrorState
        title="Could not load AI providers"
        message={loadError.message}
        onRetry={() => {
          setLoading(true)
          refresh()
            .catch(err => setLoadError(toAppApiError(err)))
            .finally(() => setLoading(false))
        }}
      />
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-[15px] font-semibold text-cloudera-navy">AI Models</h2>
        <p className="type-chat-meta mt-1 text-slate-500">
          Manage AI providers, models, and runtime assignments for this project.
        </p>
      </div>

      {banner ? (
        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700" role="status">
          {banner}
        </p>
      ) : null}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-cloudera-navy">Providers</h3>
          <div className="flex flex-wrap items-center gap-2">
            {selectedProviderIds.size > 0 ? (
              <button
                type="button"
                className="rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700"
                disabled={batchDeletingProviders}
                onClick={() => void deleteSelectedProviders()}
              >
                {batchDeletingProviders ? 'Deleting…' : `Delete selected (${selectedProviderIds.size})`}
              </button>
            ) : null}
            <button
              type="button"
              className="btn-primary inline-flex items-center gap-1 px-3 py-2 text-sm"
              onClick={() => {
                setEditingProviderId(null)
                setProviderDraft(emptyProviderDraft('GEMINI'))
                setProviderModal('pick')
              }}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Register provider
            </button>
          </div>
        </div>

        {providers.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="h-8 w-8" aria-hidden />}
            title="Register your first AI provider"
            description="Connect OpenAI, Gemini, Claude, or an OpenAI-compatible endpoint."
            action={
              <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => setProviderModal('pick')}>
                Register provider
              </button>
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="app-table-head">
                <tr>
                  <th className="w-10 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all providers on this page"
                      checked={pagedProviders.length > 0 && pagedProviders.every(p => selectedProviderIds.has(p.id))}
                      onChange={e => toggleAllProvidersOnPage(e.target.checked)}
                    />
                  </th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Credentials</th>
                  <th className="px-3 py-2">Models</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pagedProviders.map(provider => (
                  <tr key={provider.id}>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label={`Select provider ${provider.name}`}
                        checked={selectedProviderIds.has(provider.id)}
                        onChange={() => toggleProviderRow(provider.id)}
                      />
                    </td>
                    <td className="px-3 py-2 font-medium text-cloudera-navy">{provider.name}</td>
                    <td className="px-3 py-2">{providerTypeLabel(provider.provider_type)}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${providerStatusClass(provider)}`}>
                        {providerStatusLabel(provider)}
                      </span>
                    </td>
                    <td className="px-3 py-2">{provider.secret_configured ? 'Configured' : 'Not configured'}</td>
                    <td className="px-3 py-2">{modelsByProvider.get(provider.id) ?? 0}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
                          disabled={testingProviderId === provider.id}
                          onClick={() => handleTestProvider(provider.id)}
                        >
                          {testingProviderId === provider.id ? 'Testing…' : 'Test'}
                        </button>
                        <button
                          type="button"
                          className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
                          onClick={() => {
                            setEditingProviderId(provider.id)
                            setProviderDraft({
                              name: provider.name,
                              key: provider.key,
                              provider_type: provider.provider_type,
                              base_url: provider.base_url || '',
                              secret_ref: provider.secret_ref || '',
                              enabled: provider.enabled,
                              test_strategy: String(provider.config_json?.test_strategy || 'AUTO'),
                            })
                            setProviderModal('form')
                          }}
                        >
                          Edit
                        </button>
                        <button type="button" className="rounded-lg border border-slate-200 px-2 py-1 text-xs" onClick={() => toggleProvider(provider)}>
                          {provider.enabled ? 'Disable' : 'Enable'}
                        </button>
                        <button type="button" className="rounded-lg border border-rose-200 px-2 py-1 text-xs text-rose-700" onClick={() => deleteProvider(provider)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <TablePagination
              page={providersPage}
              pageSize={providersPageSize}
              total={providers.length}
              pageSizeOptions={AI_REGISTRY_TABLE_PAGE_SIZES}
              onPageChange={setProvidersPage}
              onPageSizeChange={size => {
                setProvidersPageSize(size)
                setProvidersPage(1)
              }}
            />
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-cloudera-navy">Registered models</h3>
          <div className="flex flex-wrap items-center gap-2">
            {selectedModelIds.size > 0 ? (
              <button
                type="button"
                className="rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700"
                disabled={batchDeletingModels}
                onClick={() => void deleteSelectedModels()}
              >
                {batchDeletingModels ? 'Deleting…' : `Delete selected (${selectedModelIds.size})`}
              </button>
            ) : null}
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-1 px-3 py-2 text-sm"
              disabled={!providers.length}
              onClick={() => {
                const providerId = providers[0]?.id || ''
                setModelDraft({
                  provider_id: providerId,
                  name: '',
                  key: '',
                  model_id: '',
                  model_type: 'CHAT',
                  enabled: true,
                })
                setManualModelEntry(false)
                setRemoteFilter('')
                setModelRegisterType('CHAT')
                setModelModalOpen(true)
                void loadRemoteModelsForProvider(providerId)
              }}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Register model
            </button>
          </div>
        </div>
        {models.length === 0 ? (
          <p className="text-sm text-slate-600">No models registered yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="app-table-head">
                <tr>
                  <th className="w-10 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all models on this page"
                      checked={pagedModels.length > 0 && pagedModels.every(m => selectedModelIds.has(m.id))}
                      onChange={e => toggleAllModelsOnPage(e.target.checked)}
                    />
                  </th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Model ID</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Provider</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pagedModels.map(model => {
                  const provider = providers.find(p => p.id === model.provider_id)
                  return (
                    <tr key={model.id}>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          aria-label={`Select model ${model.name}`}
                          checked={selectedModelIds.has(model.id)}
                          onChange={() => toggleModelRow(model.id)}
                        />
                      </td>
                      <td className="px-3 py-2 font-medium">{model.name}</td>
                      <td className="px-3 py-2 font-mono text-xs">{model.model_id}</td>
                      <td className="px-3 py-2">{model.model_type}</td>
                      <td className="px-3 py-2">{provider?.name ?? '—'}</td>
                      <td className="px-3 py-2">{model.enabled ? model.status || 'Not tested' : 'Disabled'}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-2">
                          <button type="button" className="rounded-lg border px-2 py-1 text-xs" disabled={testingModelId === model.id} onClick={() => handleTestModel(model.id)}>
                            {testingModelId === model.id ? 'Testing…' : 'Test'}
                          </button>
                          <button type="button" className="rounded-lg border px-2 py-1 text-xs text-rose-700" onClick={() => deleteModel(model)}>
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <TablePagination
              page={modelsPage}
              pageSize={modelsPageSize}
              total={models.length}
              pageSizeOptions={AI_REGISTRY_TABLE_PAGE_SIZES}
              onPageChange={setModelsPage}
              onPageSizeChange={size => {
                setModelsPageSize(size)
                setModelsPage(1)
              }}
            />
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-cloudera-navy">Runtime assignments</h3>
          <p className="type-chat-meta mt-1 text-slate-500">
            Primary way to choose which registered model powers chat, RAG, skills, embeddings, and reranking.
          </p>
        </div>
        <div className="space-y-2">
          {CAPABILITY_ROWS.map(row => {
            const effective = assignmentByCap.get(row.capability)
            const compatible = models.filter(m => m.model_type === row.modelType && m.enabled)
            const healthMsg = effective ? assignmentHealthMessage(effective) : null
            return (
              <div key={row.capability} className="rounded-xl border border-slate-200 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-cloudera-navy">{row.label}</p>
                    <p className="type-chat-meta text-slate-500">{effective?.model_name || 'No registry model'}</p>
                    {effective ? (
                      <p className="type-chat-meta mt-1 text-slate-500">{assignmentSourceLabel(effective.source)}</p>
                    ) : null}
                    {effective?.source === 'LEGACY_FALLBACK' ? (
                      <p className="mt-2 rounded-lg bg-slate-50 px-2 py-1 text-xs text-slate-600">
                        This capability currently uses legacy environment configuration.
                      </p>
                    ) : null}
                    {healthMsg ? (
                      <p className="mt-2 text-xs font-semibold text-rose-700" role="alert">
                        Configuration error: {healthMsg}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      aria-label={`Assign model for ${row.label}`}
                      className="input max-w-[14rem] py-1.5 text-sm"
                      value=""
                      onChange={e => {
                        const id = e.target.value
                        if (id) void assignCapability(row.capability, id)
                        e.target.value = ''
                      }}
                    >
                      <option value="">Change assignment…</option>
                      {compatible.map(m => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                    {effective?.source === 'PROJECT' ? (
                      <button type="button" className="text-xs text-slate-600 underline" onClick={() => clearAssignment(row.capability)}>
                        Remove project assignment
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {providerModal !== 'closed' ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl">
            {providerModal === 'pick' ? (
              <>
                <h3 className="text-lg font-semibold text-cloudera-navy">Register provider</h3>
                <p className="mt-1 text-sm text-slate-600">Choose a provider type.</p>
                <div className="mt-4 grid gap-2">
                  {PROVIDER_TYPE_OPTIONS.map(opt => (
                    <button
                      key={opt.type}
                      type="button"
                      className="flex items-start gap-3 rounded-xl border border-slate-200 px-3 py-3 text-left hover:border-cloudera-violet"
                      onClick={() => {
                        setProviderDraft(emptyProviderDraft(opt.type))
                        setProviderModal('form')
                      }}
                    >
                      <ProviderTypeIcon providerType={opt.type} size={28} className="mt-0.5" />
                      <span>
                        <span className="font-semibold text-cloudera-navy">{opt.title}</span>
                        <span className="mt-1 block text-xs text-slate-500">{opt.blurb}</span>
                      </span>
                    </button>
                  ))}
                </div>
                <button type="button" className="btn-secondary mt-4 w-full" onClick={() => setProviderModal('closed')}>
                  Cancel
                </button>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold">{editingProviderId ? 'Edit provider' : 'Register provider'}</h3>
                <div className="mt-4 space-y-3 text-sm">
                  <label className="block">
                    <span className="text-slate-600">Provider name</span>
                    <input className="input mt-1 w-full" value={providerDraft.name} onChange={e => setProviderDraft(d => ({ ...d, name: e.target.value }))} />
                  </label>
                  <label className="block">
                    <span className="text-slate-600">Key</span>
                    <input className="input mt-1 w-full font-mono text-xs" value={providerDraft.key} onChange={e => setProviderDraft(d => ({ ...d, key: e.target.value }))} disabled={Boolean(editingProviderId)} />
                  </label>
                  {providerDraft.provider_type === 'OPENAI_COMPATIBLE' ? (
                    <label className="block">
                      <span className="text-slate-600">Base URL</span>
                      <input className="input mt-1 w-full font-mono text-xs" placeholder="https://host/v1" value={providerDraft.base_url} onChange={e => setProviderDraft(d => ({ ...d, base_url: e.target.value }))} />
                    </label>
                  ) : providerDraft.provider_type === 'OPENAI' || providerDraft.provider_type === 'ANTHROPIC' ? (
                    <label className="block">
                      <span className="text-slate-600">Base URL (optional)</span>
                      <input className="input mt-1 w-full font-mono text-xs" value={providerDraft.base_url} onChange={e => setProviderDraft(d => ({ ...d, base_url: e.target.value }))} />
                    </label>
                  ) : null}
                  <label className="block">
                    <span className="text-slate-600">Secret reference</span>
                    <input className="input mt-1 w-full font-mono text-xs" placeholder="env://GEMINI_API_KEY" value={providerDraft.secret_ref} onChange={e => setProviderDraft(d => ({ ...d, secret_ref: e.target.value }))} />
                    <span className="type-chat-meta mt-1 block text-slate-500">Example: env://GEMINI_API_KEY — never paste raw API keys.</span>
                  </label>
                  {providerDraft.provider_type === 'OPENAI_COMPATIBLE' ? (
                    <label className="block">
                      <span className="text-slate-600">Test strategy</span>
                      <select className="input mt-1 w-full" value={providerDraft.test_strategy} onChange={e => setProviderDraft(d => ({ ...d, test_strategy: e.target.value }))}>
                        <option value="AUTO">Auto</option>
                        <option value="MODELS_ENDPOINT">Models endpoint</option>
                        <option value="CHAT_SMOKE">Chat smoke</option>
                      </select>
                    </label>
                  ) : null}
                </div>
                <div className="mt-4 flex gap-2">
                  <button type="button" className="btn-primary flex-1" disabled={savingProvider} onClick={() => void saveProvider()}>
                    {savingProvider ? 'Saving…' : 'Save'}
                  </button>
                  <button type="button" className="btn-secondary flex-1" onClick={() => setProviderModal('closed')}>
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}

      {modelModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <Bot className="h-5 w-5" aria-hidden />
              Register models
            </h3>
            <p className="mt-1 text-sm text-slate-600">
              Load the provider catalog, select one or more models, then register them for runtime assignments.
            </p>
            <div className="mt-4 space-y-3 text-sm">
              <label className="block">
                <span className="text-slate-600">Provider</span>
                <select
                  className="input mt-1 w-full"
                  value={modelDraft.provider_id}
                  onChange={e => {
                    const providerId = e.target.value
                    setModelDraft(d => ({ ...d, provider_id: providerId }))
                    void loadRemoteModelsForProvider(providerId)
                  }}
                >
                  {providers.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex flex-wrap items-end gap-3">
                <label className="block min-w-[10rem] flex-1">
                  <span className="text-slate-600">Model type (for selected)</span>
                  <select
                    className="input mt-1 w-full"
                    value={modelRegisterType}
                    onChange={e => setModelRegisterType(e.target.value as AiModelType)}
                  >
                    <option value="CHAT">Chat</option>
                    <option value="EMBEDDING">Embedding</option>
                    <option value="RERANKER">Reranker</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="btn-secondary px-3 py-2"
                  disabled={loadingRemoteModels || !modelDraft.provider_id}
                  onClick={() => void loadRemoteModelsForProvider(modelDraft.provider_id)}
                >
                  {loadingRemoteModels ? 'Loading…' : 'Refresh catalog'}
                </button>
              </div>

              {!manualModelEntry ? (
                <div className="rounded-xl border border-slate-200">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Provider catalog</span>
                    <button type="button" className="text-xs text-cloudera-violet underline" onClick={() => setManualModelEntry(true)}>
                      Enter model ID manually
                    </button>
                  </div>
                  <div className="border-b border-slate-100 px-3 py-2">
                    <input
                      className="input w-full py-1.5 text-sm"
                      placeholder="Filter models…"
                      value={remoteFilter}
                      onChange={e => setRemoteFilter(e.target.value)}
                    />
                  </div>
                  <div className="max-h-56 overflow-y-auto px-1 py-1">
                    {loadingRemoteModels ? (
                      <p className="px-3 py-4 text-slate-500">Fetching models from provider…</p>
                    ) : filteredRemoteModels.length === 0 ? (
                      <p className="px-3 py-4 text-slate-500">
                        No models returned. Check credentials, test the provider, or use manual entry.
                      </p>
                    ) : (
                      <ul className="divide-y divide-slate-50">
                        {filteredRemoteModels.map(remote => {
                          const already = registeredModelIdsForProvider.has(remote.id)
                          return (
                            <li key={remote.id} className="flex items-start gap-2 px-2 py-2">
                              <input
                                type="checkbox"
                                className="mt-1"
                                disabled={already}
                                checked={selectedRemoteIds.has(remote.id)}
                                onChange={() => toggleRemoteModel(remote.id)}
                                aria-label={`Register ${remote.id}`}
                              />
                              <div className="min-w-0 flex-1">
                                <p className="truncate font-mono text-xs text-cloudera-navy">{remote.id}</p>
                                {remote.display_name && remote.display_name !== remote.id ? (
                                  <p className="truncate text-xs text-slate-500">{remote.display_name}</p>
                                ) : null}
                                {already ? <p className="text-xs text-emerald-700">Already registered</p> : null}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </div>
                  {selectedRemoteIds.size > 0 ? (
                    <p className="border-t border-slate-100 px-3 py-2 text-xs text-slate-600">{selectedRemoteIds.size} selected</p>
                  ) : null}
                </div>
              ) : (
                <div className="space-y-3 rounded-xl border border-slate-200 p-3">
                  <button type="button" className="text-xs text-cloudera-violet underline" onClick={() => setManualModelEntry(false)}>
                    Back to provider catalog
                  </button>
                  <label className="block">
                    <span className="text-slate-600">Display name</span>
                    <input className="input mt-1 w-full" value={modelDraft.name} onChange={e => setModelDraft(d => ({ ...d, name: e.target.value }))} />
                  </label>
                  <label className="block">
                    <span className="text-slate-600">Key</span>
                    <input className="input mt-1 w-full font-mono text-xs" value={modelDraft.key} onChange={e => setModelDraft(d => ({ ...d, key: e.target.value }))} />
                  </label>
                  <label className="block">
                    <span className="text-slate-600">Model ID</span>
                    <input className="input mt-1 w-full font-mono text-xs" value={modelDraft.model_id} onChange={e => setModelDraft(d => ({ ...d, model_id: e.target.value }))} />
                  </label>
                  <label className="block">
                    <span className="text-slate-600">Model type</span>
                    <select
                      className="input mt-1 w-full"
                      value={modelDraft.model_type}
                      onChange={e => setModelDraft(d => ({ ...d, model_type: e.target.value as typeof d.model_type }))}
                    >
                      <option value="CHAT">Chat</option>
                      <option value="EMBEDDING">Embedding</option>
                      <option value="RERANKER">Reranker</option>
                    </select>
                  </label>
                </div>
              )}
            </div>
            <div className="mt-4 flex gap-2">
              {manualModelEntry ? (
                <button type="button" className="btn-primary flex-1" disabled={savingModel} onClick={() => void saveModel()}>
                  {savingModel ? 'Saving…' : 'Register one model'}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-primary flex-1"
                  disabled={savingModel || selectedRemoteIds.size === 0}
                  onClick={() => void registerSelectedRemoteModels()}
                >
                  {savingModel ? 'Registering…' : `Register selected (${selectedRemoteIds.size || 0})`}
                </button>
              )}
              <button type="button" className="btn-secondary flex-1" onClick={() => setModelModalOpen(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
