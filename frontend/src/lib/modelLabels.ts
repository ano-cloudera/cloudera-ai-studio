import type { ModelInfo } from '../types/api'

export function providerDisplayName(provider: string): string {
  const key = provider.trim().toLowerCase()
  if (key === 'gemini') return 'Gemini'
  if (key === 'openai') return 'OpenAI'
  if (key === 'qwen') return 'Qwen'
  if (key === 'anthropic') return 'Anthropic'
  return provider.charAt(0).toUpperCase() + provider.slice(1)
}

export function friendlyUnavailableMessage(reason: string | null | undefined): string {
  if (!reason?.trim()) return 'Provider is not reachable.'
  const lower = reason.toLowerCase()
  if (lower.includes('api key')) return 'API key is not configured.'
  if (lower.includes('not configured')) return 'Provider is not configured.'
  if (lower.includes('reach') || lower.includes('connect') || lower.includes('timeout')) {
    return 'Provider is not reachable.'
  }
  return 'Provider is not reachable.'
}

/** Secondary line under provider name — not technical IDs. */
export function providerDeploymentHint(provider: string): string {
  const name = providerDisplayName(provider)
  const key = provider.trim().toLowerCase()
  if (key === 'qwen') return `${name} · Private AI`
  return `${name} · External API`
}

export function modelSelectionValue(model: ModelInfo): string {
  return `${model.provider}::${model.id}`
}

export function parseModelSelectionValue(value: string): { provider: ModelInfo['provider']; model: string } | null {
  const [provider, ...rest] = value.split('::')
  if (!provider || !rest.length) return null
  return { provider: provider as ModelInfo['provider'], model: rest.join('::') }
}

export function modelsForProvider(models: ModelInfo[], provider: string): ModelInfo[] {
  return models.filter(model => model.provider === provider)
}

export function uniqueProviders(models: ModelInfo[]): string[] {
  const seen = new Set<string>()
  const order: string[] = []
  for (const model of models) {
    if (!seen.has(model.provider)) {
      seen.add(model.provider)
      order.push(model.provider)
    }
  }
  return order
}
