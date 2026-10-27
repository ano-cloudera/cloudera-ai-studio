import type {
  AiModelRecord,
  AiModelType,
  AiProviderRecord,
  AiProviderType,
  AssignmentCapability,
  AssignmentSource,
  ModelAssignmentRecord,
} from '../types/api'
import type { AppApiError } from './apiError'

export const PROVIDER_TYPE_OPTIONS: {
  type: AiProviderType
  title: string
  blurb: string
}[] = [
  { type: 'OPENAI', title: 'OpenAI', blurb: 'Connect OpenAI models using an API credential.' },
  { type: 'GEMINI', title: 'Google Gemini', blurb: 'Connect Google Gemini models.' },
  { type: 'ANTHROPIC', title: 'Anthropic Claude', blurb: 'Connect Claude models using Anthropic.' },
  {
    type: 'OPENAI_COMPATIBLE',
    title: 'OpenAI Compatible',
    blurb: 'Connect private or third-party OpenAI-compatible endpoints (CAI, vLLM, LiteLLM, Qwen).',
  },
]

export type CapabilityGroup = 'conversation' | 'retrieval'

export const CAPABILITY_GROUPS: { id: CapabilityGroup; title: string; blurb: string }[] = [
  {
    id: 'conversation',
    title: 'Conversation & generation',
    blurb: 'Chat, Ask Data, and RAG answer generation.',
  },
  {
    id: 'retrieval',
    title: 'Retrieval pipeline',
    blurb: 'Registry placeholders for embedding and reranking; indexing still follows backend environment variables today.',
  },
]

export const CAPABILITY_ROWS: {
  capability: AssignmentCapability
  label: string
  modelType: AiModelType
  group: CapabilityGroup
  description: string
  optional?: boolean
  envBacked?: boolean
}[] = [
  {
    capability: 'CHAT_DEFAULT',
    label: 'Default Chat',
    modelType: 'CHAT',
    group: 'conversation',
    description: 'Primary model for workspace chat when no override is chosen.',
  },
  {
    capability: 'ASK_DATA',
    label: 'Ask Data',
    modelType: 'CHAT',
    group: 'conversation',
    description: 'Structured analytics and SQL-style questions over governed data.',
  },
  {
    capability: 'RAG_GENERATION',
    label: 'RAG Generation',
    modelType: 'CHAT',
    group: 'conversation',
    description: 'Final answer synthesis for knowledge libraries and citations.',
  },
  {
    capability: 'EMBEDDING',
    label: 'Embedding',
    modelType: 'EMBEDDING',
    group: 'retrieval',
    envBacked: true,
    description: 'Assign a registered embedding model (type Embedding). Vector indexing uses EMBEDDING_PROVIDER / EMBEDDING_MODEL in the environment.',
  },
  {
    capability: 'RERANKER',
    label: 'Reranker',
    modelType: 'RERANKER',
    group: 'retrieval',
    envBacked: true,
    description: 'Assign a registered reranker model (type Reranker), or keep RERANKER_PROVIDER=none in the environment.',
  },
]

export function modelTypeLabel(type: AiModelType): string {
  if (type === 'EMBEDDING') return 'Embedding'
  if (type === 'RERANKER') return 'Reranker'
  return 'Chat'
}

const ENV_REF = /^env:\/\/[A-Za-z_][A-Za-z0-9_]*$/
const PROVIDER_KEY = /^[a-z][a-z0-9_]{0,127}$/

export const AI_REGISTRY_TABLE_PAGE_SIZES = [5, 10, 20] as const

export function slugModelKey(modelId: string): string {
  return (
    modelId
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 64) || 'model'
  )
}

export function isValidSecretRef(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return false
  if (/^sk-|^AIza|^Bearer\s/i.test(trimmed)) return false
  return ENV_REF.test(trimmed)
}

/** Matches backend `validate_provider_key` — lowercase id, not the API key. */
export function isValidProviderKey(value: string): boolean {
  return PROVIDER_KEY.test(value.trim())
}

export function normalizeProviderKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 128)
}

export function defaultSecretRefForProvider(type: AiProviderType): string {
  switch (type) {
    case 'GEMINI':
      return 'env://GEMINI_API_KEY'
    case 'OPENAI':
      return 'env://OPENAI_API_KEY'
    case 'ANTHROPIC':
      return 'env://ANTHROPIC_API_KEY'
    default:
      return ''
  }
}

export function providerStatusLabel(provider: AiProviderRecord): string {
  if (!provider.enabled) return 'Disabled'
  const s = (provider.status || 'NOT_TESTED').toUpperCase()
  if (s === 'READY') return 'Ready'
  if (s === 'FAILED') return 'Failed'
  return 'Not tested'
}

export function providerStatusClass(provider: AiProviderRecord): string {
  if (!provider.enabled) return 'bg-slate-100 text-slate-600'
  const s = (provider.status || '').toUpperCase()
  if (s === 'READY') return 'bg-emerald-50 text-emerald-800'
  if (s === 'FAILED') return 'bg-rose-50 text-rose-800'
  return 'bg-amber-50 text-amber-900'
}

export function modelStatusLabel(model: AiModelRecord): string {
  if (!model.enabled) return 'Disabled'
  const s = (model.status || 'NOT_TESTED').toUpperCase()
  if (s === 'READY') return 'Ready'
  if (s === 'FAILED') return 'Failed'
  return 'Not tested'
}

export function modelStatusClass(model: AiModelRecord): string {
  if (!model.enabled) return 'bg-slate-100 text-slate-600'
  const s = (model.status || '').toUpperCase()
  if (s === 'READY') return 'bg-emerald-50 text-emerald-800'
  if (s === 'FAILED') return 'bg-rose-50 text-rose-800'
  return 'bg-amber-50 text-amber-900'
}

/** Models registered under the wrong type (e.g. embedding model saved as Chat). */
export function modelsLikelyWrongTypeForCapability(
  models: AiModelRecord[],
  expected: AiModelType,
): AiModelRecord[] {
  if (expected === 'EMBEDDING') {
    return models.filter(
      m =>
        m.enabled &&
        m.model_type !== 'EMBEDDING' &&
        /embed/i.test(`${m.name} ${m.model_id}`),
    )
  }
  if (expected === 'RERANKER') {
    return models.filter(
      m =>
        m.enabled &&
        m.model_type !== 'RERANKER' &&
        /rerank/i.test(`${m.name} ${m.model_id}`),
    )
  }
  return []
}

export function assignmentSourceLabel(source: AssignmentSource): string {
  if (source === 'PROJECT') return 'Project assignment'
  if (source === 'WORKSPACE') return 'Inherited from workspace'
  return 'Legacy runtime configuration'
}

export function assignmentHealthMessage(row: ModelAssignmentRecord): string | null {
  const health = (row.health || '').toUpperCase()
  if (health === 'MODEL_DISABLED') return 'Assigned model is disabled.'
  if (health === 'PROVIDER_DISABLED') return 'Assigned provider is disabled.'
  if (health === 'DEGRADED') return 'Last provider test failed; runtime may be degraded.'
  return null
}

export function aiRegistryErrorMessage(error: AppApiError): string {
  const code = error.code.toUpperCase()
  const map: Record<string, string> = {
    PROVIDER_IN_USE: 'This provider could not be deleted.',
    MODEL_IN_USE: 'This model could not be deleted.',
    AUTHENTICATION_FAILED: 'Authentication failed. Check the secret reference and environment configuration.',
    SECRET_NOT_FOUND: 'Secret not configured. Set the environment variable referenced by secret_ref.',
    PROVIDER_UNREACHABLE: 'The provider could not be reached.',
    TEST_TIMEOUT: 'The connection test timed out.',
    MODEL_DISABLED: 'The model is disabled.',
    PROVIDER_DISABLED: 'The provider is disabled.',
    INVALID_ASSIGNMENT:
      'Invalid provider or model key. Use lowercase letters, numbers, and underscores (e.g. gemini).',
  }
  return map[code] || error.message || 'The request could not be completed.'
}

export function providerTypeLabel(type: AiProviderType): string {
  return PROVIDER_TYPE_OPTIONS.find(p => p.type === type)?.title ?? type
}
