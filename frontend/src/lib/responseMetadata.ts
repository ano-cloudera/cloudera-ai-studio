import type { ChatResponse } from '../types/api'
import { formatCompactTokens } from './formatTokens'

function titleCaseProvider(provider: string): string {
  const trimmed = provider.trim()
  if (!trimmed) return 'AI'
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1).toLowerCase()
}

function strategyLabel(strategy: ChatResponse['strategy']): string | null {
  if (strategy === 'governed') return 'Governed'
  if (strategy === 'exploratory_local') return 'Exploratory'
  if (strategy === 'conversational') return null
  return strategy.replace(/_/g, ' ')
}

export function formatDurationSeconds(totalMs: number | undefined): string | null {
  if (totalMs == null || !Number.isFinite(totalMs) || totalMs <= 0) return null
  const seconds = totalMs / 1000
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  return `${Math.round(seconds)}s`
}

/** The model that answered, as named in Settings -> AI Models ("nvidia/nemotron-3-super" shows as "nemotron-3-super");
 * without an assignment, the provider. */
export function answeringModelLabel(response: ChatResponse): string {
  const named = (response.model_resolution?.model_name || response.model_resolution?.model_key || '').trim()
  if (named) return named.split('/').filter(Boolean).pop() || named
  return titleCaseProvider(response.provider)
}

/** Human-readable footer line — no milliseconds. */
export function formatResponseMetadata(response: ChatResponse): string {
  const parts: string[] = [answeringModelLabel(response)]
  const strategy = strategyLabel(response.strategy)
  if (strategy) parts.push(strategy)
  const duration = formatDurationSeconds(response.timings?.total_ms)
  if (duration) parts.push(duration)
  const tokens = response.usage?.total_tokens
  if (tokens && tokens > 0) parts.push(`${formatCompactTokens(tokens)} tok`)
  if (response.cached_at) parts.push(response.cache_reason === 'data_source_unavailable' ? 'Saved answer' : 'Cached')
  return parts.join(' · ')
}
