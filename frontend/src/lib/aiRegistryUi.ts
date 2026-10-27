import type {
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

export const CAPABILITY_ROWS: {
  capability: AssignmentCapability
  label: string
  modelType: AiModelType
}[] = [
  { capability: 'CHAT_DEFAULT', label: 'Default Chat', modelType: 'CHAT' },
  { capability: 'ASK_DATA', label: 'Ask Data', modelType: 'CHAT' },
  { capability: 'RAG_GENERATION', label: 'RAG Generation', modelType: 'CHAT' },
  { capability: 'SKILLS', label: 'Skills', modelType: 'CHAT' },
  { capability: 'EMBEDDING', label: 'Embedding', modelType: 'EMBEDDING' },
  { capability: 'RERANKER', label: 'Reranker', modelType: 'RERANKER' },
]

const ENV_REF = /^env:\/\/[A-Za-z_][A-Za-z0-9_]*$/

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
    PROVIDER_IN_USE: 'This provider cannot be deleted because registered models still reference it.',
    MODEL_IN_USE: 'This model is assigned to one or more runtime capabilities. Remove those assignments before deleting it.',
    AUTHENTICATION_FAILED: 'Authentication failed. Check the secret reference and environment configuration.',
    SECRET_NOT_FOUND: 'Secret not configured. Set the environment variable referenced by secret_ref.',
    PROVIDER_UNREACHABLE: 'The provider could not be reached.',
    TEST_TIMEOUT: 'The connection test timed out.',
    MODEL_DISABLED: 'The model is disabled.',
    PROVIDER_DISABLED: 'The provider is disabled.',
    INVALID_ASSIGNMENT: 'This model type cannot be assigned to the selected capability.',
  }
  return map[code] || error.message || 'The request could not be completed.'
}

export function providerTypeLabel(type: AiProviderType): string {
  return PROVIDER_TYPE_OPTIONS.find(p => p.type === type)?.title ?? type
}
