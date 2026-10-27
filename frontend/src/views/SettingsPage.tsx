'use client'

import { useEffect, useMemo, useState } from 'react'
import { PageCenter } from '../components/PageCenter'
import { appConfig } from '../config/appConfig'
import {
  friendlyUnavailableMessage,
  modelSelectionValue,
  parseModelSelectionValue,
  providerDeploymentHint,
  providerDisplayName,
  uniqueProviders,
} from '../lib/modelLabels'
import { useModelSelection } from '../lib/modelSelection'
import type { ModelInfo } from '../types/api'
import { AiModelsSettingsPanel } from './settings/AiModelsSettingsPanel'
import { AskDataPresentationSettingsPanel } from './settings/AskDataPresentationSettingsPanel'
import { AskDataStarterSettingsPanel } from './settings/AskDataStarterSettingsPanel'

const SETTINGS_TABS = ['general', 'models', 'rag', 'features', 'advanced'] as const
type SettingsTab = (typeof SETTINGS_TABS)[number]

function ModelOptions({ models, groupByProvider }: { models: ModelInfo[]; groupByProvider: boolean }) {
  if (!groupByProvider) {
    return models.map(model => (
      <option key={modelSelectionValue(model)} value={modelSelectionValue(model)} disabled={!model.available}>
        {model.label}
      </option>
    ))
  }

  const providers = uniqueProviders(models)
  return providers.map(provider => {
    const group = models.filter(model => model.provider === provider)
    return (
      <optgroup key={provider} label={providerDisplayName(provider)}>
        {group.map(model => (
          <option key={modelSelectionValue(model)} value={modelSelectionValue(model)} disabled={!model.available}>
            {model.label}
          </option>
        ))}
      </optgroup>
    )
  })
}

type LegacyChatProps = {
  loading: boolean
  error: unknown
  models: ModelInfo[]
  hasAvailableModel: boolean
  groupByProvider: boolean
  draftValue: string
  setDraftValue: (value: string) => void
  canSave: boolean | '' | null | undefined
  saveModel: () => void
  draftDirty: boolean
  committedValue: string
  selectedModel: ModelInfo | null
  retryLoad: () => void
}

function LegacyChatModelControls({
  loading,
  error,
  models,
  hasAvailableModel,
  groupByProvider,
  draftValue,
  setDraftValue,
  canSave,
  saveModel,
  draftDirty,
  committedValue,
  selectedModel,
  retryLoad,
}: LegacyChatProps) {
  return (
    <>
      {loading && (
        <p className="type-chat-body text-slate-500" role="status">
          Loading models…
        </p>
      )}

      {!loading && error && (
        <div className="space-y-3 rounded-xl border border-rose-100 bg-rose-50/80 px-4 py-3">
          <p className="type-chat-body text-rose-900">Unable to load available models.</p>
          <button type="button" onClick={retryLoad} className="btn-secondary py-2 text-xs">
            Retry
          </button>
        </div>
      )}

      {!loading && !error && models.length > 0 && !hasAvailableModel && (
        <p className="type-chat-body text-slate-600">No AI models are currently available.</p>
      )}

      {!loading && !error && models.length > 0 && (
        <>
          <div className="space-y-2">
            <label className="sr-only" htmlFor="settings-ai-model">
              Chat model
            </label>
            <select
              id="settings-ai-model"
              aria-label="Chat model"
              disabled={!hasAvailableModel}
              className="input"
              value={hasAvailableModel ? draftValue : ''}
              onChange={event => setDraftValue(event.target.value)}
            >
              {!hasAvailableModel && <option value="">No models available</option>}
              {hasAvailableModel && !draftValue && <option value="">Select a model</option>}
              <ModelOptions models={models} groupByProvider={groupByProvider} />
            </select>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={!canSave} onClick={saveModel}>
              Save model
            </button>
            {draftDirty && <p className="type-chat-meta text-slate-500">Unsaved change — applies after Save.</p>}
            {!draftDirty && committedValue && (
              <p className="type-chat-meta text-emerald-700">Saved for new chat messages.</p>
            )}
          </div>

          {selectedModel && (
            <div className="space-y-2 border-t border-slate-100 pt-4">
              {selectedModel.available ? (
                <p className="type-chat-body flex items-center gap-2 text-emerald-700">
                  <span className="text-emerald-500" aria-hidden>
                    ●
                  </span>
                  Ready
                </p>
              ) : (
                <div className="type-chat-body space-y-1 text-slate-600">
                  <p className="flex items-center gap-2">
                    <span className="text-slate-400" aria-hidden>
                      ○
                    </span>
                    Unavailable
                  </p>
                  <p className="type-chat-meta pl-5 text-slate-500">{friendlyUnavailableMessage(selectedModel.reason)}</p>
                </div>
              )}
              <p className="type-chat-meta text-slate-500">Provider: {providerDisplayName(selectedModel.provider)}</p>
              <p className="type-chat-meta text-slate-400">{providerDeploymentHint(selectedModel.provider)}</p>
            </div>
          )}
        </>
      )}
    </>
  )
}

function featureRows() {
  return [
    { key: 'Ask Data', on: appConfig.features.askData },
    { key: 'Knowledge', on: appConfig.features.documents },
    { key: 'Prompts', on: appConfig.features.prompts },
    { key: 'Skills', on: appConfig.features.skills },
    { key: 'Semantic Layer', on: appConfig.features.semanticLayer },
    { key: appConfig.navigationConnectors, on: appConfig.features.connectors },
    { key: 'Usage', on: appConfig.features.usage },
    { key: 'Settings', on: appConfig.features.settings },
  ]
}

export function SettingsPage() {
  const { models, selection, loading, error, select, retryLoad } = useModelSelection()
  const [tab, setTab] = useState<SettingsTab>('general')
  const [draftValue, setDraftValue] = useState('')

  const hasAvailableModel = models.some(model => model.available)
  const groupByProvider = uniqueProviders(models).length > 1

  const committedValue = selection ? `${selection.provider}::${selection.model}` : ''

  useEffect(() => {
    if (loading) return
    setDraftValue(committedValue)
  }, [loading, committedValue])

  const draftSelection = useMemo(() => parseModelSelectionValue(draftValue), [draftValue])

  const selectedModel = useMemo(
    () =>
      models.find(
        model => model.provider === draftSelection?.provider && model.id === draftSelection?.model,
      ) ?? null,
    [models, draftSelection],
  )

  const draftDirty = Boolean(draftValue && draftValue !== committedValue)
  const canSave =
    draftDirty &&
    draftSelection &&
    models.some(
      model =>
        model.available &&
        model.provider === draftSelection.provider &&
        model.id === draftSelection.model,
    )

  function saveModel() {
    if (!draftSelection || !canSave) return
    select(draftSelection)
  }

  return (
    <PageCenter>
      <h1 className="type-app-title text-xl sm:text-2xl">Settings</h1>
      <p className="type-chat-body mt-2 text-slate-600">Workspace configuration for this accelerator deployment.</p>

      <div className="mt-6 flex flex-wrap gap-2 border-b border-slate-200 pb-1">
        {SETTINGS_TABS.map(key => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded-t-lg px-3 py-2 text-sm font-semibold capitalize ${
              tab === key ? 'border-b-2 border-cloudera-violet text-cloudera-violet' : 'text-slate-500'
            }`}
          >
            {key === 'models' ? 'AI models' : key}
          </button>
        ))}
      </div>

      <section className="card mt-5 space-y-4 p-6 sm:p-7">
        {tab === 'general' ? (
          <>
            <h2 className="text-[15px] font-semibold text-cloudera-navy">General</h2>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">Application</dt>
                <dd className="font-medium text-cloudera-navy">{appConfig.headerTitle}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Project</dt>
                <dd className="font-medium text-cloudera-navy">{appConfig.projectName}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Tagline</dt>
                <dd className="font-medium text-cloudera-navy">{appConfig.sidebarTagline}</dd>
              </div>
            </dl>
            {appConfig.features.askData ? (
              <>
                <AskDataStarterSettingsPanel />
                <AskDataPresentationSettingsPanel />
              </>
            ) : null}
          </>
        ) : null}

        {tab === 'models' ? (
          <>
            {appConfig.features.aiModelRegistry ? (
              <AiModelsSettingsPanel />
            ) : null}

            {appConfig.features.aiModelRegistry ? null : (
              <div>
                <h2 className="text-[15px] font-semibold text-cloudera-navy">AI models</h2>
                <p className="type-chat-meta mt-1 text-slate-500">{appConfig.settingsModelHelper}</p>
              </div>
            )}

            {appConfig.features.aiModelRegistry ? (
              <details className="mt-6 rounded-xl border border-slate-200 bg-slate-50/40 px-4 py-3">
                <summary className="cursor-pointer text-sm font-semibold text-cloudera-navy">Legacy chat fallback</summary>
                <p className="type-chat-meta mt-2 text-slate-500">
                  Optional. Used only when a capability has no registry assignment. Prefer runtime assignments above.
                </p>
                <div className="mt-4 space-y-4">
                  <LegacyChatModelControls
                    loading={loading}
                    error={error}
                    models={models}
                    hasAvailableModel={hasAvailableModel}
                    groupByProvider={groupByProvider}
                    draftValue={draftValue}
                    setDraftValue={setDraftValue}
                    canSave={canSave}
                    saveModel={saveModel}
                    draftDirty={draftDirty}
                    committedValue={committedValue}
                    selectedModel={selectedModel}
                    retryLoad={retryLoad}
                  />
                </div>
              </details>
            ) : (
              <LegacyChatModelControls
                loading={loading}
                error={error}
                models={models}
                hasAvailableModel={hasAvailableModel}
                groupByProvider={groupByProvider}
                draftValue={draftValue}
                setDraftValue={setDraftValue}
                canSave={canSave}
                saveModel={saveModel}
                draftDirty={draftDirty}
                committedValue={committedValue}
                selectedModel={selectedModel}
                retryLoad={retryLoad}
              />
            )}
          </>
        ) : null}

        {tab === 'rag' ? (
          <>
            <h2 className="text-[15px] font-semibold text-cloudera-navy">RAG</h2>
            <p className="text-sm text-slate-600">
              Document libraries and retrieval are managed on the Knowledge page. Embedding and vector store settings are
              configured on the backend for this deployment.
            </p>
            <ul className="mt-3 list-inside list-disc text-sm text-slate-600">
              <li>Knowledge surface: {appConfig.features.documents ? 'Enabled' : 'Hidden'}</li>
              <li>Vector store and reranker: backend-managed</li>
            </ul>
          </>
        ) : null}

        {tab === 'features' ? (
          <>
            <h2 className="text-[15px] font-semibold text-cloudera-navy">Features</h2>
            <p className="text-sm text-slate-600">Navigation visibility is controlled by deployment feature flags (read-only).</p>
            <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
              {featureRows().map(row => (
                <li key={row.key} className="flex items-center justify-between px-4 py-3 text-sm">
                  <span className="font-medium text-cloudera-navy">{row.key}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      row.on ? 'bg-emerald-50 text-emerald-800' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {row.on ? 'On' : 'Off'}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {tab === 'advanced' ? (
          <>
            <h2 className="text-[15px] font-semibold text-cloudera-navy">Advanced</h2>
            <p className="text-sm text-slate-600">
              Operational limits (query timeout, row caps, cache TTL) are set via backend environment configuration for
              this PoC deployment.
            </p>
            <p className="type-chat-meta text-slate-500">
              Report panel: {appConfig.analysisReportPanel ? 'Enabled' : 'Disabled'}
            </p>
          </>
        ) : null}
      </section>
    </PageCenter>
  )
}
