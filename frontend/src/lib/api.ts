import type {
  ChatMode,
  ChatResponse,
  DocumentRecord,
  LibraryRecord,
  ModelInfo,
  ModelSelection,
  SuggestedQuestion,
  UsageSummary,
} from '../types/api'
import { parseApiError, type AppApiError } from './apiError'
import { semanticListQuery, type SemanticListParams } from './semanticListQuery'

export type { AppApiError }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const headers = new Headers(init?.headers)
  if (!isForm && !headers.has('Content-Type') && init?.body) {
    headers.set('Content-Type', 'application/json')
  }
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, headers })
  } catch {
    const err: AppApiError = {
      code: 'NETWORK_ERROR',
      status: 0,
      message: 'We could not reach the backend service.',
      retryable: true,
    }
    throw err
  }
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      /* ignore */
    }
    throw parseApiError(response.status, body, response.statusText)
  }
  return response.json() as Promise<T>
}


export const api = {
  deleteChatSession: async (sessionId: string): Promise<void> => {
    const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
    if (!response.ok && response.status !== 404) {
      throw new Error(`${response.status} ${response.statusText}`)
    }
  },
  models: () => request<{ models: ModelInfo[] }>('/models'),
  randomQueries: (limit = 1) => request<{ questions: SuggestedQuestion[] }>(`/random-queries?limit=${limit}`),
  askDataStarters: () => request<import('../types/api').AskDataStartersResponse>('/v1/ask-data/starters'),
  askDataPresentationConfig: () =>
    request<{ workspace_slug: string; presentation: import('./presentationTierConfig').PresentationTierConfig }>(
      '/v1/ask-data/presentation-config',
    ),
  getAskDataSettings: () =>
    request<{ settings: import('../types/api').AskDataSettingsPayload; workspace_slug: string }>(
      '/v1/ask-data/settings',
    ),
  putAskDataSettings: (body: import('../types/api').AskDataSettingsPayload) =>
    request<{ settings: import('../types/api').AskDataSettingsPayload; workspace_slug: string }>(
      '/v1/ask-data/settings',
      { method: 'PUT', body: JSON.stringify(body) },
    ),
  getAskDataSemanticCatalog: () =>
    request<import('../types/api').AskDataSemanticCatalogResponse>('/v1/ask-data/semantic-catalog'),
  postAskDataFeedback: (body: {
    request_id: string
    session_id: string
    rating: 'up' | 'down'
    comment?: string
  }) => request<{ ok: boolean }>('/v1/ask-data/feedback', { method: 'POST', body: JSON.stringify(body) }),
  usageSummary: (params: { days?: number; mtd?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.mtd) q.set('mtd', 'true')
    else if (params.days != null) q.set('days', String(params.days))
    const suffix = q.toString() ? `?${q}` : ''
    return request<UsageSummary>(`/usage/summary${suffix}`)
  },
  usageEvents: (days = 7, limit = 50) =>
    request<{ events: import('../types/api').UsageEvent[] }>(`/usage/events?days=${days}&limit=${limit}`),
  usageExportCsvUrl: (days = 30) => `/api/usage/export.csv?days=${days}`,
  listLibraries: () => request<{ libraries: LibraryRecord[] }>('/v1/libraries'),
  listLibrariesPaginated: (params: {
    page?: number
    page_size?: number
    search?: string
    sort?: 'name' | 'updated_at' | 'created_at' | 'document_count'
    order?: 'asc' | 'desc'
  } = {}) => {
    const q = new URLSearchParams()
    q.set('page', String(params.page ?? 1))
    q.set('page_size', String(params.page_size ?? 10))
    if (params.search) q.set('search', params.search)
    if (params.sort) q.set('sort', params.sort)
    if (params.order) q.set('order', params.order)
    return request<import('../types/api').PaginatedResult<LibraryRecord>>(`/v1/libraries?${q}`)
  },
  getLibrary: (libraryId: string) =>
    request<{ library: LibraryRecord }>(`/v1/libraries/${encodeURIComponent(libraryId)}`),
  createLibrary: (body: { name: string; description?: string }) =>
    request<{ library: LibraryRecord }>('/v1/libraries', { method: 'POST', body: JSON.stringify(body) }),
  renameLibrary: (libraryId: string, body: { name: string }) =>
    request<{ library: LibraryRecord }>(`/v1/libraries/${encodeURIComponent(libraryId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  updateLibrary: (libraryId: string, body: { name: string; description?: string | null }) =>
    request<{ library: LibraryRecord }>(`/v1/libraries/${encodeURIComponent(libraryId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteLibrary: (libraryId: string) =>
    request<{ deleted: boolean }>(`/v1/libraries/${encodeURIComponent(libraryId)}`, { method: 'DELETE' }),
  bulkDeleteLibraries: (body: { ids: string[] }) =>
    request<import('../types/api').BulkDeleteResponse>('/v1/libraries/bulk-delete', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listLibraryDocuments: (libraryId: string) =>
    request<{ documents: DocumentRecord[] }>(`/v1/libraries/${encodeURIComponent(libraryId)}/documents`),
  listLibraryDocumentsPaginated: (
    libraryId: string,
    params: {
      page?: number
      page_size?: number
      search?: string
      status?: string
      sort?:
        | 'original_filename'
        | 'mime_type'
        | 'size_bytes'
        | 'chunk_count'
        | 'status'
        | 'created_at'
        | 'updated_at'
      order?: 'asc' | 'desc'
    } = {},
  ) => {
    const q = new URLSearchParams()
    q.set('page', String(params.page ?? 1))
    q.set('page_size', String(params.page_size ?? 10))
    if (params.search) q.set('search', params.search)
    if (params.status && params.status !== 'all') q.set('status', params.status)
    if (params.sort) q.set('sort', params.sort)
    if (params.order) q.set('order', params.order)
    return request<import('../types/api').PaginatedResult<DocumentRecord>>(
      `/v1/libraries/${encodeURIComponent(libraryId)}/documents?${q}`,
    )
  },
  fetchDocument: (documentId: string) =>
    request<{ document: DocumentRecord }>(`/v1/documents/${encodeURIComponent(documentId)}`),
  renameDocument: (documentId: string, body: { original_filename: string }) =>
    request<{ document: DocumentRecord }>(`/v1/documents/${encodeURIComponent(documentId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  uploadLibraryDocument: async (libraryId: string, file: File): Promise<DocumentRecord> => {
    const form = new FormData()
    form.append('file', file)
    const response = await request<{ document: DocumentRecord }>(
      `/v1/libraries/${encodeURIComponent(libraryId)}/documents`,
      { method: 'POST', body: form },
    )
    return response.document
  },
  batchUploadLibraryDocuments: async (libraryId: string, files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<{ requested: number; accepted: DocumentRecord[]; rejected: { filename: string; code: string; message: string }[] }>(
      `/v1/libraries/${encodeURIComponent(libraryId)}/documents/batch-upload`,
      { method: 'POST', body: form },
    )
  },
  batchUploadChatAttachments: async (sessionId: string, files: File[]) => {
    const form = new FormData()
    form.append('session_id', sessionId)
    for (const file of files) form.append('files', file)
    return request<{
      requested: number
      accepted: import('./chatAttachments').ChatAttachmentRecord[]
      rejected: { filename: string; code: string; message: string }[]
    }>('/v1/chat/attachments/batch', { method: 'POST', body: form })
  },
  getChatAttachment: (attachmentId: string) =>
    request<{ attachment: import('./chatAttachments').ChatAttachmentRecord }>(
      `/v1/chat/attachments/${encodeURIComponent(attachmentId)}`,
    ),
  retryChatAttachment: (attachmentId: string) =>
    request<{ attachment: import('./chatAttachments').ChatAttachmentRecord }>(
      `/v1/chat/attachments/${encodeURIComponent(attachmentId)}/retry`,
      { method: 'POST' },
    ),
  deleteChatAttachment: (attachmentId: string) =>
    request<{ deleted: boolean }>(`/v1/chat/attachments/${encodeURIComponent(attachmentId)}`, { method: 'DELETE' }),
  saveChatAttachmentToKnowledge: (
    attachmentId: string,
    body: { library_id?: string; new_library_name?: string },
  ) =>
    request<{ saved: { library_id: string; document_id: string; attachment_id: string } }>(
      `/v1/chat/attachments/${encodeURIComponent(attachmentId)}/save-to-knowledge`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  deleteDocument: (documentId: string) =>
    request<{ deleted: boolean }>(`/v1/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),
  bulkDeleteDocuments: (body: { ids: string[]; library_id?: string }) =>
    request<import('../types/api').BulkDeleteResponse>('/v1/documents/bulk-delete', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  processDocument: (documentId: string) =>
    request<{ document: DocumentRecord }>(`/v1/documents/${encodeURIComponent(documentId)}/process`, { method: 'POST' }),
  listSkills: (params: { scope?: string; search?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.scope) q.set('scope', params.scope)
    if (params.search) q.set('search', params.search)
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ skills: import('../types/api').SkillRecord[] }>(`/v1/skills${suffix}`)
  },
  createSkill: (body: Record<string, unknown>) =>
    request<{ skill: import('../types/api').SkillRecord }>('/v1/skills', { method: 'POST', body: JSON.stringify(body) }),
  listSkillVersions: (skillId: string) =>
    request<{ versions: import('../types/api').SkillVersionRecord[] }>(`/v1/skills/${encodeURIComponent(skillId)}/versions`),
  createSkillVersion: (skillId: string, body: Record<string, unknown>) =>
    request<{ version: import('../types/api').SkillVersionRecord }>(`/v1/skills/${encodeURIComponent(skillId)}/versions`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  publishSkillVersion: (skillId: string, versionId: string) =>
    request<{ version: import('../types/api').SkillVersionRecord }>(
      `/v1/skills/${encodeURIComponent(skillId)}/versions/${encodeURIComponent(versionId)}/publish`,
      { method: 'POST' },
    ),
  executeSkill: (skillId: string, body: { input: string; conversation_id?: string; context?: Record<string, unknown> }) =>
    request<import('../types/api').SkillExecuteResult>(`/v1/skills/${encodeURIComponent(skillId)}/execute`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listTools: () => request<{ tools: import('../types/api').SkillToolRecord[] }>('/v1/tools'),
  listPrompts: (params: { scope?: string; search?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.scope) q.set('scope', params.scope)
    if (params.search) q.set('search', params.search)
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ prompts: import('../types/api').PromptRecord[] }>(`/v1/prompts${suffix}`)
  },
  createPrompt: (body: {
    name: string
    key: string
    scope: string
    description?: string
    workspace_id?: string
    project_id?: string
    initial_content?: string
  }) => request<{ prompt: import('../types/api').PromptRecord }>('/v1/prompts', { method: 'POST', body: JSON.stringify(body) }),
  getPrompt: (promptId: string) =>
    request<{ prompt: import('../types/api').PromptRecord }>(`/v1/prompts/${encodeURIComponent(promptId)}`),
  listPromptVersions: (promptId: string) =>
    request<{ versions: import('../types/api').PromptVersionRecord[] }>(
      `/v1/prompts/${encodeURIComponent(promptId)}/versions`,
    ),
  createPromptVersion: (promptId: string, body: { content: string; created_by?: string }) =>
    request<{ version: import('../types/api').PromptVersionRecord }>(
      `/v1/prompts/${encodeURIComponent(promptId)}/versions`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  publishPromptVersion: (promptId: string, versionId: string) =>
    request<{ version: import('../types/api').PromptVersionRecord }>(
      `/v1/prompts/${encodeURIComponent(promptId)}/versions/${encodeURIComponent(versionId)}/publish`,
      { method: 'POST' },
    ),
  rollbackPromptVersion: (promptId: string, versionId: string) =>
    request<{ version: import('../types/api').PromptVersionRecord }>(
      `/v1/prompts/${encodeURIComponent(promptId)}/versions/${encodeURIComponent(versionId)}/rollback`,
      { method: 'POST' },
    ),
  resolvePrompt: (promptKey: string, projectId?: string) =>
    request<import('../types/api').PromptResolveResult>('/v1/prompts/resolve', {
      method: 'POST',
      body: JSON.stringify({ prompt_key: promptKey, project_id: projectId }),
    }),
  retrievalSearch: (body: {
    query: string
    library_ids?: string[]
    document_ids?: string[]
    top_k?: number
  }) =>
    request<{
      query: string
      results: Array<Record<string, unknown>>
      citations: Array<Record<string, unknown>>
      metadata: Record<string, unknown>
    }>('/v1/retrieval/search', { method: 'POST', body: JSON.stringify(body) }),
  listSemanticModels: (params: { search?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.search) q.set('search', params.search)
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ models: import('../types/api').SemanticModelRecord[] }>(`/v1/semantic/models${suffix}`)
  },
  createSemanticModel: (body: { name: string; key: string; description?: string }) =>
    request<{ model: import('../types/api').SemanticModelRecord }>('/v1/semantic/models', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listSemanticVersions: (modelId: string) =>
    request<{ versions: import('../types/api').SemanticVersionRecord[] }>(
      `/v1/semantic/models/${encodeURIComponent(modelId)}/versions`,
    ),
  createSemanticVersion: (modelId: string) =>
    request<{ version: import('../types/api').SemanticVersionRecord }>(
      `/v1/semantic/models/${encodeURIComponent(modelId)}/versions`,
      { method: 'POST' },
    ),
  cloneSemanticVersion: (versionId: string) =>
    request<{ version: import('../types/api').SemanticVersionRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/clone`,
      { method: 'POST' },
    ),
  discardSemanticDraftVersion: (versionId: string) =>
    request<{ discarded: boolean; semantic_model_id: string; version_number: number }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/discard`,
      { method: 'POST' },
    ),
  validateSemanticVersion: (
    versionId: string,
    body: { mode?: 'structural' | 'source' | 'full'; source_mode?: 'metadata_only' | 'safe_query' } = {},
  ) =>
    request<import('../types/api').SemanticValidationResult>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/validate`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  getSemanticReadiness: (versionId: string) =>
    request<{
      semantic_version_id: string
      activation_readiness: string | null
      validated_at: string | null
      last_validation_run_id: string | null
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/readiness`),
  listSemanticValidationRuns: (versionId: string, limit = 20) =>
    request<{ runs: import('../types/api').SemanticValidationRunRecord[] }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/validation-runs?limit=${limit}`,
    ),
  getSemanticValidationRun: (runId: string) =>
    request<{ run: import('../types/api').SemanticValidationRunRecord; issues: import('../types/api').SemanticValidationIssue[] }>(
      `/v1/semantic/validation-runs/${encodeURIComponent(runId)}`,
    ),
  getSemanticVersionDiff: (versionId: string, againstVersionId: string) =>
    request<import('../types/api').SemanticVersionDiff>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/diff?against=${encodeURIComponent(againstVersionId)}`,
    ),
  getSemanticModelOverview: (modelId: string) =>
    request<import('../types/api').SemanticOverviewPayload>(
      `/v1/semantic/models/${encodeURIComponent(modelId)}/overview`,
    ),
  getSemanticValidatorHealth: () => request<import('../types/api').ValidatorHealth>('/v1/semantic/validators/health'),
  publishSemanticToAskData: (modelId: string, body: { version_id?: string } = {}) =>
    request<{ status: string; version_id?: string; version_number?: number; issues?: unknown[] }>(
      `/v1/semantic/models/${modelId}/publish-to-ask-data`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  semanticSuggestions: (body: { connection_id: string; tables: string[] }) =>
    request<Record<string, unknown>>('/v1/semantic/suggestions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  acceptSemanticSuggestions: (
    modelId: string,
    body: {
      version_id?: string
      bootstrap_tables?: Array<Record<string, unknown>>
      selections?: Array<Record<string, unknown>>
    },
  ) =>
    request<{ version_id: string; persisted: Array<Record<string, unknown>>; conflicts: unknown[]; counts: Record<string, number> }>(
      `/v1/semantic/models/${encodeURIComponent(modelId)}/suggestions/accept`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  listChatContextOptions: (params: { search?: string; limit?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.search) q.set('search', params.search)
    if (params.limit) q.set('limit', String(params.limit))
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ groups: import('../types/api').ChatContextOptionGroup[] }>(
      `/v1/chat/context-options${suffix}`,
    )
  },

  publishSemanticVersion: (versionId: string) =>
    request<{ version: import('../types/api').SemanticVersionRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/publish`,
      { method: 'POST' },
    ),
  rollbackSemanticVersion: (versionId: string) =>
    request<{ version: import('../types/api').SemanticVersionRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/rollback`,
      { method: 'POST' },
    ),
  getSemanticRuntimeStatus: (modelKey?: string) => {
    const q = modelKey ? `?model_key=${encodeURIComponent(modelKey)}` : ''
    return request<import('../types/api').SemanticRuntimeStatus>(`/v1/semantic/runtime/status${q}`)
  },
  listSemanticRuntimeDeployments: (modelKey?: string, limit = 50) => {
    const q = new URLSearchParams()
    if (modelKey) q.set('model_key', modelKey)
    q.set('limit', String(limit))
    return request<{ deployments: import('../types/api').SemanticRuntimeDeploymentRecord[] }>(
      `/v1/semantic/runtime/deployments?${q}`,
    )
  },
  getSemanticRuntimeDeployment: (deploymentId: string) =>
    request<{ deployment: import('../types/api').SemanticRuntimeDeploymentRecord; events: Array<Record<string, unknown>> }>(
      `/v1/semantic/runtime/deployments/${encodeURIComponent(deploymentId)}`,
    ),
  stageSemanticRuntime: (versionId: string) =>
    request<{ deployment: import('../types/api').SemanticRuntimeDeploymentRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/runtime/stage`,
      { method: 'POST' },
    ),
  validateSemanticRuntimeDeployment: (deploymentId: string) =>
    request<{ valid: boolean; message: string }>(
      `/v1/semantic/runtime/deployments/${encodeURIComponent(deploymentId)}/validate`,
      { method: 'POST' },
    ),
  dryRunSemanticRuntimeActivation: (deploymentId: string) =>
    request<{ dry_run: boolean; result: string; deployment_id: string; artifact_checksum: string }>(
      `/v1/semantic/runtime/deployments/${encodeURIComponent(deploymentId)}/activate?dry_run=true`,
      { method: 'POST' },
    ),
  activateSemanticRuntimeDeployment: (deploymentId: string) =>
    request<{ result: string; deployment_id: string; registry_version?: number; runtime_active_version?: number }>(
      `/v1/semantic/runtime/deployments/${encodeURIComponent(deploymentId)}/activate`,
      { method: 'POST' },
    ),
  rollbackSemanticRuntimeDeployment: (deploymentId: string) =>
    request<{ result: string; deployment_id: string }>(
      `/v1/semantic/runtime/deployments/${encodeURIComponent(deploymentId)}/rollback`,
      { method: 'POST' },
    ),
  previewSemanticArtifact: (versionId: string) =>
    request<import('../types/api').SemanticArtifactPreview>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/artifact-preview`,
      { method: 'POST' },
    ),
  getOssieImportSource: () => request<import('../types/api').OssieImportSource>('/v1/semantic/import/source'),
  importOssieSemantics: (body: { model_key: string; model_name?: string; dry_run?: boolean }) =>
    request<import('../types/api').OssieImportSummary>('/v1/semantic/import', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listSemanticEntities: (versionId: string, params: SemanticListParams = {}) =>
    request<{
      entities: import('../types/api').SemanticEntityRecord[]
      total?: number
      page?: number
      page_size?: number
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/entities${semanticListQuery(params)}`),
  deleteSemanticEntity: (versionId: string, entityId: string) =>
    request<{ deleted: boolean }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/entities/${encodeURIComponent(entityId)}`,
      { method: 'DELETE' },
    ),
  bulkDeleteSemanticEntities: (versionId: string, body: { ids: string[] }) =>
    request<import('../types/api').BulkDeleteResponse>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/entities/bulk-delete`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  createSemanticEntity: (versionId: string, body: Record<string, unknown>) =>
    request<{ entity: import('../types/api').SemanticEntityRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/entities`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  patchSemanticEntity: (versionId: string, entityId: string, body: Record<string, unknown>) =>
    request<{ entity: import('../types/api').SemanticEntityRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/entities/${encodeURIComponent(entityId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  previewSemanticEntityImport: (
    versionId: string,
    body: { connector_id: string; catalog?: string | null; schema?: string | null; table: string },
  ) =>
    request<{ preview: import('../types/api').SemanticEntityImportPreview }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/entities/import-preview`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  importSemanticEntity: (
    versionId: string,
    body: {
      connector_id: string
      catalog?: string | null
      schema?: string | null
      table: string
      name: string
      key: string
      description?: string | null
      dimension_columns?: string[]
    },
  ) =>
    request<import('../types/api').SemanticEntityImportResult>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/entities/import`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  getConnectorReferences: (connectorId: string) =>
    request<{ references: import('../types/api').ConnectorReferences }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/references`,
    ),
  listSemanticMetrics: (versionId: string, params: SemanticListParams = {}) =>
    request<{
      metrics: import('../types/api').SemanticMetricRecord[]
      total?: number
      page?: number
      page_size?: number
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/metrics${semanticListQuery(params)}`),
  deleteSemanticMetric: (versionId: string, metricId: string) =>
    request<{ deleted: boolean }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/metrics/${encodeURIComponent(metricId)}`,
      { method: 'DELETE' },
    ),
  bulkDeleteSemanticMetrics: (versionId: string, body: { ids: string[] }) =>
    request<import('../types/api').BulkDeleteResponse>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/metrics/bulk-delete`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  validateSemanticMetric: (
    versionId: string,
    body: {
      metric_id?: string | null
      name: string
      business_definition?: string | null
      expression: string
      aggregation?: string | null
      source_entity_key: string
    },
  ) =>
    request<{ valid: boolean; issues: Array<{ field: string; message: string }>; form_message?: string | null }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/metrics/validate`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  createSemanticMetric: (versionId: string, body: Record<string, unknown>) =>
    request<{ metric: import('../types/api').SemanticMetricRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/metrics`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  patchSemanticMetric: (versionId: string, metricId: string, body: Record<string, unknown>) =>
    request<{ metric: import('../types/api').SemanticMetricRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/metrics/${encodeURIComponent(metricId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  listSemanticDimensions: (versionId: string, params: SemanticListParams = {}) =>
    request<{
      dimensions: import('../types/api').SemanticDimensionRecord[]
      total?: number
      page?: number
      page_size?: number
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/dimensions${semanticListQuery(params)}`),
  deleteSemanticDimension: (versionId: string, dimensionId: string) =>
    request<{ deleted: boolean }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/dimensions/${encodeURIComponent(dimensionId)}`,
      { method: 'DELETE' },
    ),
  bulkDeleteSemanticDimensions: (versionId: string, body: { ids: string[] }) =>
    request<import('../types/api').BulkDeleteResponse>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/dimensions/bulk-delete`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  createSemanticDimension: (versionId: string, body: Record<string, unknown>) =>
    request<{ dimension: import('../types/api').SemanticDimensionRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/dimensions`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  patchSemanticDimension: (versionId: string, dimensionId: string, body: Record<string, unknown>) =>
    request<{ dimension: import('../types/api').SemanticDimensionRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/dimensions/${encodeURIComponent(dimensionId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  listSemanticRelationships: (versionId: string, params: SemanticListParams = {}) =>
    request<{
      relationships: import('../types/api').SemanticRelationshipRecord[]
      total?: number
      page?: number
      page_size?: number
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/relationships${semanticListQuery(params)}`),
  deleteSemanticRelationship: (versionId: string, relationshipId: string) =>
    request<{ deleted: boolean }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/relationships/${encodeURIComponent(relationshipId)}`,
      { method: 'DELETE' },
    ),
  bulkDeleteSemanticRelationships: (versionId: string, body: { ids: string[] }) =>
    request<import('../types/api').BulkDeleteResponse>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/relationships/bulk-delete`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  createSemanticRelationship: (versionId: string, body: Record<string, unknown>) =>
    request<{ relationship: import('../types/api').SemanticRelationshipRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/relationships`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  patchSemanticRelationship: (versionId: string, relationshipId: string, body: Record<string, unknown>) =>
    request<{ relationship: import('../types/api').SemanticRelationshipRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/relationships/${encodeURIComponent(relationshipId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  listSemanticTerms: (versionId: string, params: SemanticListParams = {}) =>
    request<{
      terms: import('../types/api').SemanticTermRecord[]
      total?: number
      page?: number
      page_size?: number
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/terms${semanticListQuery(params)}`),
  deleteSemanticTerm: (versionId: string, termId: string) =>
    request<{ deleted: boolean }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/terms/${encodeURIComponent(termId)}`,
      { method: 'DELETE' },
    ),
  bulkDeleteSemanticTerms: (versionId: string, body: { ids: string[] }) =>
    request<import('../types/api').BulkDeleteResponse>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/terms/bulk-delete`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  listSemanticRecentDefinitions: (versionId: string, params: SemanticListParams = {}) =>
    request<{
      definitions: import('../types/api').SemanticRecentDefinitionRecord[]
      total?: number
      page?: number
      page_size?: number
    }>(`/v1/semantic/versions/${encodeURIComponent(versionId)}/recent-definitions${semanticListQuery(params)}`),
  createSemanticTerm: (versionId: string, body: Record<string, unknown>) =>
    request<{ term: import('../types/api').SemanticTermRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/terms`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  patchSemanticTerm: (versionId: string, termId: string, body: Record<string, unknown>) =>
    request<{ term: import('../types/api').SemanticTermRecord }>(
      `/v1/semantic/versions/${encodeURIComponent(versionId)}/terms/${encodeURIComponent(termId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  listConnectors: (params: { connector_type?: string; enabled?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.connector_type) q.set('connector_type', params.connector_type)
    if (params.enabled != null) q.set('enabled', String(params.enabled))
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ connectors: import('../types/api').ConnectorRecord[] }>(`/v1/connectors${suffix}`)
  },
  getConnector: (connectorId: string) =>
    request<{ connector: import('../types/api').ConnectorRecord }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}`,
    ),
  createConnector: (body: import('../types/api').ConnectorCreateRequest) =>
    request<{ connector: import('../types/api').ConnectorRecord }>('/v1/connectors', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  patchConnector: (connectorId: string, body: import('../types/api').ConnectorUpdateRequest) =>
    request<{ connector: import('../types/api').ConnectorRecord }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  deleteConnector: (connectorId: string) =>
    request<{ deleted: boolean }>(`/v1/connectors/${encodeURIComponent(connectorId)}`, { method: 'DELETE' }),
  testConnector: (connectorId: string) =>
    request<import('../types/api').ConnectorTestResult>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/test`,
      { method: 'POST' },
    ),
  getConnectorCapabilities: (connectorId: string) =>
    request<{ capabilities: import('../types/api').ConnectorCapabilities }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/capabilities`,
    ),
  listConnectorCatalogs: (connectorId: string, refresh = false) =>
    request<{ catalogs: import('../types/api').CatalogInfo[]; resolved_context: Record<string, unknown> }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/catalogs?refresh=${refresh}`,
    ),
  listConnectorSchemas: (
    connectorId: string,
    params: { catalog?: string; limit?: number; offset?: number; refresh?: boolean } = {},
  ) => {
    const q = new URLSearchParams()
    if (params.catalog) q.set('catalog', params.catalog)
    if (params.limit != null) q.set('limit', String(params.limit))
    if (params.offset != null) q.set('offset', String(params.offset))
    if (params.refresh) q.set('refresh', 'true')
    const suffix = q.toString() ? `?${q}` : ''
    return request<{
      schemas: import('../types/api').SchemaInfo[]
      total: number
      limit: number
      offset: number
      resolved_context: Record<string, unknown>
    }>(`/v1/connectors/${encodeURIComponent(connectorId)}/schemas${suffix}`)
  },
  listConnectorTables: (
    connectorId: string,
    params: {
      catalog?: string
      schema?: string
      table_type?: string
      search?: string
      limit?: number
      offset?: number
      refresh?: boolean
    } = {},
  ) => {
    const q = new URLSearchParams()
    if (params.catalog) q.set('catalog', params.catalog)
    if (params.schema) q.set('schema', params.schema)
    if (params.table_type) q.set('table_type', params.table_type)
    if (params.search) q.set('search', params.search)
    if (params.limit != null) q.set('limit', String(params.limit))
    if (params.offset != null) q.set('offset', String(params.offset))
    if (params.refresh) q.set('refresh', 'true')
    const suffix = q.toString() ? `?${q}` : ''
    return request<{
      tables: import('../types/api').TableInfo[]
      total: number
      limit: number
      offset: number
      resolved_context: Record<string, unknown>
    }>(`/v1/connectors/${encodeURIComponent(connectorId)}/tables${suffix}`)
  },
  describeConnectorTable: (
    connectorId: string,
    body: { catalog?: string | null; schema?: string | null; table: string },
  ) =>
    request<{ table: import('../types/api').TableDetail }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/metadata/describe`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  previewConnectorTable: (
    connectorId: string,
    body: { catalog?: string | null; schema?: string | null; table: string; limit?: number },
  ) =>
    request<{ preview: import('../types/api').SamplePreview }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/metadata/preview`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  listAiProviders: (params: { provider_type?: string; enabled?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.provider_type) q.set('provider_type', params.provider_type)
    if (params.enabled != null) q.set('enabled', String(params.enabled))
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ providers: import('../types/api').AiProviderRecord[] }>(`/v1/ai/providers${suffix}`)
  },
  getAiProvider: (providerId: string) =>
    request<{ provider: import('../types/api').AiProviderRecord }>(
      `/v1/ai/providers/${encodeURIComponent(providerId)}`,
    ),
  createAiProvider: (body: Record<string, unknown>) =>
    request<{ provider: import('../types/api').AiProviderRecord }>('/v1/ai/providers', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateAiProvider: (providerId: string, body: Record<string, unknown>) =>
    request<{ provider: import('../types/api').AiProviderRecord }>(
      `/v1/ai/providers/${encodeURIComponent(providerId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  deleteAiProvider: (providerId: string) =>
    request<{ deleted: boolean }>(`/v1/ai/providers/${encodeURIComponent(providerId)}`, { method: 'DELETE' }),
  testAiProvider: (providerId: string) =>
    request<import('../types/api').AiProviderTestResult>(
      `/v1/ai/providers/${encodeURIComponent(providerId)}/test`,
      { method: 'POST' },
    ),
  listAiProviderRemoteModels: (providerId: string) =>
    request<{ provider_id: string; provider_type: string; models: import('../types/api').AiRemoteModel[] }>(
      `/v1/ai/providers/${encodeURIComponent(providerId)}/remote-models`,
    ),
  listAiModels: (params: { provider_id?: string; model_type?: string; enabled?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.provider_id) q.set('provider_id', params.provider_id)
    if (params.model_type) q.set('model_type', params.model_type)
    if (params.enabled != null) q.set('enabled', String(params.enabled))
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ models: import('../types/api').AiModelRecord[] }>(`/v1/ai/models${suffix}`)
  },
  createAiModel: (body: Record<string, unknown>) =>
    request<{ model: import('../types/api').AiModelRecord }>('/v1/ai/models', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateAiModel: (modelId: string, body: Record<string, unknown>) =>
    request<{ model: import('../types/api').AiModelRecord }>(`/v1/ai/models/${encodeURIComponent(modelId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteAiModel: (modelId: string) =>
    request<{ deleted: boolean }>(`/v1/ai/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' }),
  testAiModel: (modelId: string) =>
    request<import('../types/api').AiModelTestResult>(
      `/v1/ai/models/${encodeURIComponent(modelId)}/test`,
      { method: 'POST' },
    ),
  listModelAssignments: () =>
    request<{ assignments: import('../types/api').ModelAssignmentRecord[] }>('/v1/ai/assignments'),
  putModelAssignment: (capability: string, body: { model_id: string; enabled?: boolean }) =>
    request<{ assignment: import('../types/api').ModelAssignmentRecord }>(
      `/v1/ai/assignments/${encodeURIComponent(capability)}`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),
  deleteModelAssignment: (capability: string) =>
    request<{ assignment: import('../types/api').ModelAssignmentRecord }>(
      `/v1/ai/assignments/${encodeURIComponent(capability)}`,
      { method: 'DELETE' },
    ),
  chatStream: async function* (
    question: string,
    sessionId: string,
    selection: ModelSelection,
    signal?: AbortSignal,
    options?: {
      mode?: ChatMode
      library_ids?: string[]
      context_sources?: import('../types/api').ChatContextSourcePayload[]
    },
  ): AsyncGenerator<
    { type: 'progress'; stage: string; label: string; detail?: string | null }
    | { type: 'done'; response: ChatResponse }
  > {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        session_id: sessionId,
        provider: selection.provider,
        model: selection.model,
        ...(options?.mode && options.mode !== 'ask_data' ? { mode: options.mode } : {}),
        ...(options?.library_ids?.length ? { library_ids: options.library_ids } : {}),
        ...(options?.context_sources?.length ? { context_sources: options.context_sources } : {}),
      }),
      signal,
    })
    if (!response.ok || !response.body) throw new Error(`${response.status} ${response.statusText}`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let terminalReceived = false
    function* drain(flush: boolean) {
      const frames = buffer.split('\n\n')
      buffer = flush ? '' : (frames.pop() ?? '')
      for (const frame of frames) {
        const line = frame.split('\n').find(value => value.startsWith('data: '))
        if (!line) continue
        const event = JSON.parse(line.slice(6))
        if (event.type === 'done') terminalReceived = true
        yield event
      }
    }
    while (true) {
      const { done, value } = await reader.read()
      if (value) buffer += decoder.decode(value, { stream: true })
      yield* drain(done)
      if (done) {
        if (!terminalReceived) throw new Error('Stream ended without a terminal response')
        return
      }
    }
  },
}
